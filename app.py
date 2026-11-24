import datetime as dt
import time
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="NBA Edge", page_icon="🏀", layout="wide")

BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NBAEdge/1.0)"}


def fetch_json(url, params=None):
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(
                url, params=params, headers=HEADERS, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as error:
            last_error = error
            time.sleep(2 * (attempt + 1))
    raise last_error


@st.cache_data(ttl=600, show_spinner=False)
def scoreboard(start, end):
    first = dt.datetime.strptime(start, "%Y%m%d").date()
    last = dt.datetime.strptime(end, "%Y%m%d").date()

    events_by_id = {}
    day = first

    while day <= last:
        date_key = day.strftime("%Y%m%d")
        payload = fetch_json(
            f"{BASE}/scoreboard",
            {"dates": date_key, "limit": 500}
        )

        for event in payload.get("events", []):
            event_id = event.get("id")
            if event_id:
                events_by_id[event_id] = event

        day += dt.timedelta(days=1)

    return list(events_by_id.values())


@st.cache_data(ttl=14400, show_spinner=False)
def summary(event_id):
    return fetch_json(f"{BASE}/summary", {"event": event_id})


@st.cache_data(ttl=900, show_spinner=False)
def injury_feed():
    return fetch_json(f"{BASE}/injuries")


def minutes_value(value):
    try:
        if ":" in str(value):
            minutes, seconds = str(value).split(":")[:2]
            return float(minutes) + float(seconds) / 60
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.0


def parse_game(data, date):
    rows = []
    teams = data.get("boxscore", {}).get("players", [])

    for team in teams:
        team_name = team.get("team", {}).get("displayName", "")
        opponent = next(
            (x.get("team", {}).get("displayName", "")
             for x in teams if x is not team),
            ""
        )

        for group in team.get("statistics", []):
            labels = group.get("labels", [])

            for item in group.get("athletes", []):
                athlete = item.get("athlete", {})
                name = athlete.get("displayName")
                if not name:
                    continue

                stats = dict(zip(labels, item.get("stats", [])))

                rows.append({
                    "player": name,
                    "date": date,
                    "team": team_name,
                    "opponent": opponent,
                    "minutes": minutes_value(
                        stats.get("MIN", stats.get("MP", 0))
                    ),
                    "points": pd.to_numeric(
                        stats.get("PTS", 0), errors="coerce"
                    ),
                    "rebounds": pd.to_numeric(
                        stats.get("REB", 0), errors="coerce"
                    ),
                    "assists": pd.to_numeric(
                        stats.get("AST", 0), errors="coerce"
                    ),
                })

    return rows


@st.cache_data(ttl=14400, show_spinner=False)
def recent_logs(days):
    today = dt.date.today()
    start = today - dt.timedelta(days=days)

    events = scoreboard(
        start.strftime("%Y%m%d"),
        today.strftime("%Y%m%d")
    )

    completed = [
        event for event in events
        if event.get("status", {}).get("type", {}).get("completed")
    ]

    rows = []
    failures = 0

    for event in completed:
        try:
            rows.extend(
                parse_game(
                    summary(event["id"]),
                    event.get("date", "")[:10]
                )
            )
        except Exception:
            failures += 1

    df = pd.DataFrame(rows)

    if not df.empty:
        for column in ["minutes", "points", "rebounds", "assists"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["player", "date"])
        df = df[df["minutes"] > 0]

    return df, len(completed), failures


def load_demo_data():
    df = pd.read_csv("sample_game_logs.csv")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df, 0, 0


def player_stats(df, name):
    player = df[df.player == name].sort_values("date")

    if player.empty:
        return None

    last5 = player.tail(5)
    last10 = player.tail(10)
    last20 = player.tail(20)

    result = {
        "games": len(player),
        "last10": last10,
        "last20": last20,
    }

    for stat in ["points", "rebounds", "assists", "minutes"]:
        result[stat] = (
            0.60 * last5[stat].mean()
            + 0.40 * last10[stat].mean()
        )
        result[f"{stat}_5"] = last5[stat].mean()
        result[f"{stat}_10"] = last10[stat].mean()
        result[f"{stat}_20"] = last20[stat].mean()

    result["joint88"] = (
        (player.rebounds >= 8) & (player.assists >= 8)
    ).mean()

    result["reb8"] = (player.rebounds >= 8).mean()
    result["ast8"] = (player.assists >= 8).mean()

    return result


def injury_table(data):
    rows = []

    for team in data.get("injuries", []):
        team_name = team.get("team", {}).get("displayName", "")

        for injury in team.get("injuries", []):
            rows.append({
                "Team": team_name,
                "Player": injury.get("athlete", {}).get(
                    "displayName", ""
                ),
                "Status": injury.get("status", ""),
                "Details": injury.get(
                    "shortComment",
                    injury.get("longComment", "")
                ),
            })

    return pd.DataFrame(rows)


def break_even(odds):
    if odds < 0:
        return abs(odds) / (abs(odds) + 100)
    return 100 / (odds + 100)


def injury_replacements(df, injuries):
    rows = []

    if injuries.empty:
        return pd.DataFrame()

    for _, injury in injuries.iterrows():
        team = injury["Team"]
        injured_player = injury["Player"]
        status = injury["Status"]

        if not team or not injured_player:
            continue

        team_df = df[df["team"] == team].copy()

        if team_df.empty:
            continue

        for player in team_df["player"].unique():
            if player.lower() == injured_player.lower():
                continue

            games = team_df[team_df["player"] == player].sort_values("date")
            recent = games.tail(5)
            previous = games.iloc[-10:-5]

            recent_min = recent["minutes"].mean()
            previous_min = previous["minutes"].mean() if not previous.empty else recent_min

            min_change = recent_min - previous_min
            rebounds = recent["rebounds"].mean()
            assists = recent["assists"].mean()

            score = recent_min + (min_change * 1.5) + (rebounds * 0.5) + (assists * 0.5)

            rows.append({
                "Team": team,
                "Injured Player": injured_player,
                "Status": status,
                "Replacement Candidate": player,
                "Recent MIN": round(recent_min, 1),
                "Previous MIN": round(previous_min, 1),
                "MIN Change": round(min_change, 1),
                "Recent REB": round(rebounds, 1),
                "Recent AST": round(assists, 1),
                "Ranking Score": round(score, 1),
            })

    result = pd.DataFrame(rows)

    if not result.empty:
        result = result.sort_values(
            ["Injured Player", "Ranking Score"],
            ascending=[True, False]
        )
        result = result.groupby("Injured Player").head(3)

    return result

st.title("🏀 NBA EDGE")
st.caption("NBA player analytics and betting research dashboard")

with st.sidebar:
    st.header("Data settings")

    days = st.selectbox(
        "Recent game history",
        [7, 14, 30],
        index=1,
        format_func=lambda n: f"Last {n} days"
    )

    if st.button("Refresh data now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption("Data refreshes automatically when the cache expires.")


# Load real ESPN data first. Use clearly labeled demo data if ESPN fails.
data_mode = "LIVE ESPN DATA"

try:
    with st.spinner("Connecting to ESPN and loading NBA game logs..."):
        df, game_count, failures = recent_logs(days)

    if df.empty:
        raise ValueError("ESPN returned no player game logs.")

except Exception as error:
    data_mode = "DEMO DATA ONLY"
    game_count = 0
    failures = 0

    try:
        df, game_count, failures = load_demo_data()
    except Exception:
        st.error("Could not load ESPN data or the backup demo file.")
        st.caption(f"Technical detail: {type(error).__name__}")
        st.stop()


if data_mode == "DEMO DATA ONLY":
    st.error(
        "DEMO MODE: These are fictional sample players and statistics. "
        "Do NOT use this data to make betting decisions."
    )
else:
    st.success(
        f"LIVE ESPN DATA: {game_count} completed games loaded."
    )

if failures:
    st.warning(
        f"{failures} game summaries failed. Some player histories may be incomplete."
    )

if df.empty:
    st.error("No player data is available.")
    st.stop()

players = sorted(df.player.dropna().unique())

st.caption(f"Players available: {len(players)}")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Player Props",
    "8 + 8 Finder",
    "Injury Report",
    "Vegas Comparison",
    "Schedule",
    "Data Notes",
])


with tab1:
    st.subheader("Player projection workspace")

    name = st.selectbox("Select player", players, key="player")
    stats = player_stats(df, name)

    columns = st.columns(4)

    for column, label, key in zip(
        columns,
        ["Points", "Rebounds", "Assists", "Minutes"],
        ["points", "rebounds", "assists", "minutes"]
    ):
        column.metric(label, f"{stats[key]:.1f}")

    st.caption(
        "Projection baseline: 60% last-five average + 40% last-ten average."
    )

    st.subheader("Recent game log")

    st.dataframe(
        stats["last20"][
            ["date", "team", "opponent", "minutes",
             "points", "rebounds", "assists"]
        ].sort_values("date", ascending=False),
        use_container_width=True,
        hide_index=True
    )

    averages = pd.DataFrame({
        "Stat": ["Points", "Rebounds", "Assists", "Minutes"],
        "Last 5": [
            stats[f"{key}_5"]
            for key in ["points", "rebounds", "assists", "minutes"]
        ],
        "Last 10": [
            stats[f"{key}_10"]
            for key in ["points", "rebounds", "assists", "minutes"]
        ],
        "Last 20": [
            stats[f"{key}_20"]
            for key in ["points", "rebounds", "assists", "minutes"]
        ],
    })

    st.subheader("Recent averages")
    st.dataframe(
        averages.round(1),
        use_container_width=True,
        hide_index=True
    )


with tab2:
    st.subheader("8+ Rebounds AND 8+ Assists Finder")

    max_games = max(1, min(15, int(df.groupby("player").size().max())))

    min_games = st.slider(
        "Minimum games in loaded history",
        1,
        max_games,
        min(3, max_games)
    )

    rows = []

    for name in players:
        stats = player_stats(df, name)

        if stats["games"] >= min_games:
            team = (
                df[df.player == name]
                .sort_values("date")
                .iloc[-1]["team"]
            )

            rows.append({
                "Player": name,
                "Team": team,
                "Proj REB": round(stats["rebounds"], 1),
                "Proj AST": round(stats["assists"], 1),
                "8+ REB & 8+ AST": f"{stats['joint88']:.0%}",
                "8+ REB": f"{stats['reb8']:.0%}",
                "8+ AST": f"{stats['ast8']:.0%}",
                "Games": stats["games"],
            })

    result = pd.DataFrame(rows)

    if not result.empty:
        st.dataframe(
            result.sort_values(
                ["8+ REB & 8+ AST", "Proj REB", "Proj AST"],
                ascending=False
            ),
            use_container_width=True,
            hide_index=True
        )

    st.caption(
        "The joint percentage counts games where the same player reached "
        "both 8 rebounds and 8 assists."
    )


with tab3:
    st.subheader("ESPN Injury Report")

    try:
        injuries = injury_table(injury_feed())

        if injuries.empty:
            st.info("No league-wide injury rows were returned.")
        else:
            st.dataframe(
                injuries,
                use_container_width=True,
                hide_index=True
            )

            st.divider()
            st.subheader("Potential Injury Replacements")

            replacements = injury_replacements(df, injuries)

            if replacements.empty:
                st.info(
                    "No replacement candidates could be matched "
                    "to the current player game logs."
                )
            else:
                st.caption(
                    "Top 3 teammates per injured player, ranked using "
                    "recent minutes, minutes trend, rebounds and assists."
                )

                st.dataframe(
                    replacements,
                    use_container_width=True,
                    hide_index=True
                )

                st.warning(
                    "These are statistical role candidates, not confirmed "
                    "injury replacements. The score does not measure usage "
                    "or prove that a player's role will increase."
                )

    except Exception as error:
        st.warning("The ESPN injury feed is temporarily unavailable.")

with tab4:
    st.subheader("Vegas Line Comparison")

    name = st.selectbox("Select player", players, key="vegas_player")
    stat = st.selectbox(
        "Market",
        ["points", "rebounds", "assists"]
    )

    stats = player_stats(df, name)

    line = st.number_input(
        "Sportsbook line",
        min_value=0.0,
        max_value=100.0,
        value=7.5,
        step=0.5
    )

    odds = st.number_input(
        "American odds",
        min_value=-1000,
        max_value=1000,
        value=-110,
        step=5
    )

    st.metric(
        "Baseline projection",
        f"{stats[stat]:.1f}",
        f"{stats[stat] - line:+.1f} vs line"
    )

    st.metric(
        "Odds break-even probability",
        f"{break_even(odds):.1%}"
    )

    st.warning(
        "Over/under probability and expected value are not calculated yet. "
        "We need to validate and backtest the model before showing betting edges."
    )


with tab5:
    st.subheader("NBA Schedule: Today through next three days")

    try:
        today = dt.date.today()

        events = scoreboard(
            today.strftime("%Y%m%d"),
            (today + dt.timedelta(days=3)).strftime("%Y%m%d")
        )

        rows = []

        for event in events:
            competition = (event.get("competitions") or [{}])[0]
            teams = competition.get("competitors", [])

            away = next(
                (x for x in teams if x.get("homeAway") == "away"),
                {}
            )
            home = next(
                (x for x in teams if x.get("homeAway") == "home"),
                {}
            )

            status = event.get("status", {}).get(
                "type", {}
            ).get("shortDetail", "")

            rows.append({
                "Date / Time": event.get("date", "")[:16].replace("T", " "),
                "Matchup": (
                    f"{away.get('team', {}).get('abbreviation', '?')} "
                    f"@ {home.get('team', {}).get('abbreviation', '?')}"
                ),
                "Status": status,
                "Score": (
                    f"{away.get('score', '')} - {home.get('score', '')}"
                ),
            })

        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No games returned for this date range.")

    except Exception:
        st.warning("Schedule feed unavailable. Try refreshing later.")


with tab6:
    st.subheader("Data and Model Notes")

    st.markdown("""
    - ESPN is the primary source for completed-game box scores.
    - The dashboard supports 7, 14 and 30-day history windows.
    - The ESPN injury report is displayed when available.
    - Demo data is fictional and must never be used for betting.
    - Automatic injury-replacement rankings are still being developed.
    - Vegas odds imports, calibrated over/under probabilities,
      blowout predictions, overtime predictions and backtesting
      are future features.
    - Always verify injuries and sportsbook lines independently.
    """)

st.divider()
st.caption(
    f"NBA Edge v0.3 | Data mode: {data_mode} | "
    f"Data window: {df.date.min().date()} to {df.date.max().date()}"
)
