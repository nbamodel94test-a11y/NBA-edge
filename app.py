import datetime as dt
import time
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="NBA Edge", page_icon="🏀", layout="wide")
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NBAEdge/1.0)"}

def fetch_json(url, params=None):
    r = requests.get(url, params=params, headers=HEADERS, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=600, show_spinner=False)
def scoreboard(start, end):
    return fetch_json(f"{BASE}/scoreboard", {"dates": f"{start}-{end}", "limit": 500}).get("events", [])

@st.cache_data(ttl=14400, show_spinner=False)
def summary(event_id):
    return fetch_json(f"{BASE}/summary", {"event": event_id})

@st.cache_data(ttl=900, show_spinner=False)
def injury_feed():
    return fetch_json(f"{BASE}/injuries")

def minutes_value(v):
    try:
        if ":" in str(v):
            m, s = str(v).split(":")[:2]
            return float(m) + float(s) / 60
        return float(v or 0)
    except (ValueError, TypeError):
        return 0.0

def parse_game(data, date):
    out = []
    teams = data.get("boxscore", {}).get("players", [])
    for team in teams:
        team_name = team.get("team", {}).get("displayName", "")
        opponent = next((x.get("team", {}).get("displayName", "") for x in teams if x is not team), "")
        for group in team.get("statistics", []):
            labels = group.get("labels", [])
            for item in group.get("athletes", []):
                athlete = item.get("athlete", {})
                name = athlete.get("displayName")
                if not name:
                    continue
                stats = dict(zip(labels, item.get("stats", [])))
                out.append({
                    "player": name, "date": date, "team": team_name, "opponent": opponent,
                    "minutes": minutes_value(stats.get("MIN", stats.get("MP", 0))),
                    "points": pd.to_numeric(stats.get("PTS", 0), errors="coerce"),
                    "rebounds": pd.to_numeric(stats.get("REB", 0), errors="coerce"),
                    "assists": pd.to_numeric(stats.get("AST", 0), errors="coerce"),
                })
    return out

@st.cache_data(ttl=14400, show_spinner=False)
def recent_logs(days):
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    events = scoreboard(start.strftime("%Y%m%d"), today.strftime("%Y%m%d"))
    done = [e for e in events if e.get("status", {}).get("type", {}).get("completed")]
    rows, failures = [], 0
    bar = st.progress(0, text="Loading completed NBA box scores…")
    for i, event in enumerate(done):
        try:
            rows.extend(parse_game(summary(event["id"]), event.get("date", "")[:10]))
        except Exception:
            failures += 1
        bar.progress((i + 1) / max(len(done), 1), text=f"Loading game {i+1} of {len(done)}")
        time.sleep(0.12)
    bar.empty()
    df = pd.DataFrame(rows)
    if not df.empty:
        for c in ["minutes", "points", "rebounds", "assists"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["player", "date"])
        df = df[df["minutes"] > 0]
    return df, len(done), failures

def player_stats(df, name):
    p = df[df.player == name].sort_values("date")
    if p.empty:
        return None
    a, b, c = p.tail(5), p.tail(10), p.tail(20)
    result = {"games": len(p), "last10": b, "last20": c}
    for stat in ["points", "rebounds", "assists", "minutes"]:
        result[stat] = .60 * a[stat].mean() + .40 * b[stat].mean()
        result[f"{stat}_5"] = a[stat].mean()
        result[f"{stat}_10"] = b[stat].mean()
        result[f"{stat}_20"] = c[stat].mean()
    result["joint88"] = ((p.rebounds >= 8) & (p.assists >= 8)).mean()
    result["reb8"] = (p.rebounds >= 8).mean()
    result["ast8"] = (p.assists >= 8).mean()
    return result

def injury_table(data):
    rows = []
    for team in data.get("injuries", []):
        team_name = team.get("team", {}).get("displayName", "")
        for injury in team.get("injuries", []):
            rows.append({
                "Team": team_name,
                "Player": injury.get("athlete", {}).get("displayName", ""),
                "Status": injury.get("status", ""),
                "Details": injury.get("shortComment", injury.get("longComment", "")),
            })
    return pd.DataFrame(rows)

def break_even(odds):
    return abs(odds) / (abs(odds) + 100) if odds < 0 else 100 / (odds + 100)

st.title("🏀 NBA EDGE")
st.caption("Personal NBA analytics dashboard • Real ESPN box-score data")
with st.sidebar:
    st.header("Data settings")
    days = st.selectbox("Recent game history", [7, 14, 30], index=1,
                        format_func=lambda n: f"Last {n} days")
    if st.button("Refresh data now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.caption("ESPN feeds refresh automatically; cached data reduces loading and request volume.")

try:
    with st.spinner("Connecting to ESPN and collecting recent box scores…"):
        df, game_count, failures = recent_logs(days)
except Exception as e:
    st.error("ESPN data could not be loaded. The feed may be temporarily unavailable. Try Refresh data later.")
    st.caption(f"Technical detail: {type(e).__name__}")
    st.stop()

if df.empty:
    st.warning("No completed-game player logs returned. Try a longer history window or refresh later.")
    st.stop()

players = sorted(df.player.dropna().unique())
st.success(f"Loaded real player box scores from {game_count} completed games • {len(players)} players")
if failures:
    st.warning(f"{failures} game summaries failed to load; some player histories may be incomplete.")

t1, t2, t3, t4, t5, t6 = st.tabs([
    "Player Props", "8 + 8 Finder", "Injury Report", "Vegas Comparison", "Schedule", "Data Notes"
])

with t1:
    st.subheader("Player projection workspace")
    name = st.selectbox("Player", players, key="player")
    s = player_stats(df, name)
    cols = st.columns(4)
    for col, label, key in zip(cols, ["Points", "Rebounds", "Assists", "Minutes"],
                               ["points", "rebounds", "assists", "minutes"]):
        col.metric(label, f"{s[key]:.1f}")
    st.caption("Baseline = 60% last-five average + 40% last-ten average. This is a benchmark, not a calibrated probability.")
    st.subheader("Recent game log")
    st.dataframe(s["last20"][["date", "team", "opponent", "minutes", "points", "rebounds", "assists"]]
                 .sort_values("date", ascending=False), use_container_width=True, hide_index=True)
    averages = pd.DataFrame({
        "Stat": ["Points", "Rebounds", "Assists", "Minutes"],
        "Last 5": [s[f"{k}_5"] for k in ["points", "rebounds", "assists", "minutes"]],
        "Last 10": [s[f"{k}_10"] for k in ["points", "rebounds", "assists", "minutes"]],
        "Last 20": [s[f"{k}_20"] for k in ["points", "rebounds", "assists", "minutes"]],
    })
    st.subheader("Recent averages")
    st.dataframe(averages.round(1), use_container_width=True, hide_index=True)

with t2:
    st.subheader("Players who can reach 8+ rebounds AND 8+ assists")
    max_games = max(1, min(15, int(df.groupby("player").size().max())))
    min_games = st.slider("Minimum games in loaded history", 1, max_games, min(3, max_games))
    rows = []
    for name in players:
        s = player_stats(df, name)
        if s["games"] >= min_games:
            team = df[df.player == name].sort_values("date").iloc[-1]["team"]
            rows.append({
                "Player": name, "Team": team, "Proj REB": round(s["rebounds"], 1),
                "Proj AST": round(s["assists"], 1), "8+ REB & 8+ AST": f"{s['joint88']:.0%}",
                "8+ REB": f"{s['reb8']:.0%}", "8+ AST": f"{s['ast8']:.0%}", "Games": s["games"]
            })
    result = pd.DataFrame(rows)
    if not result.empty:
        st.dataframe(result.sort_values(["8+ REB & 8+ AST", "Proj REB", "Proj AST"],
                                        ascending=False), use_container_width=True, hide_index=True)
    st.caption("The joint 8/8 rate counts games where the same player reached both thresholds.")

with t3:
    st.subheader("ESPN injury report")
    try:
        injuries = injury_table(injury_feed())
        if injuries.empty:
            st.info("No league-wide injury rows were returned by ESPN.")
        else:
            st.dataframe(injuries, use_container_width=True, hide_index=True)
    except Exception:
        st.warning("The injury feed is temporarily unavailable. Confirm player status before relying on projections.")
    st.divider()
    st.write("Automatic teammate replacement rankings are a next step. This version displays injuries but does not yet estimate who inherits minutes, rebounds, assists or usage.")

with t4:
    st.subheader("Compare your projection with a sportsbook line")
    name = st.selectbox("Player", players, key="vegas_player")
    stat = st.selectbox("Market", ["points", "rebounds", "assists"])
    s = player_stats(df, name)
    line = st.number_input("Sportsbook line", 0.0, 100.0, 7.5, 0.5)
    odds = st.number_input("American odds", -1000, 1000, -110, 5)
    st.metric("Baseline projection", f"{s[stat]:.1f}", f"{s[stat]-line:+.1f} vs line")
    st.metric("Odds break-even probability", f"{break_even(odds):.1%}")
    st.info("Over/under probability and expected value are not shown until a stat distribution is validated and backtested.")

with t5:
    st.subheader("NBA schedule: today through next three days")
    try:
        today = dt.date.today()
        events = scoreboard(today.strftime("%Y%m%d"), (today + dt.timedelta(days=3)).strftime("%Y%m%d"))
        rows = []
        for event in events:
            comp = (event.get("competitions") or [{}])[0]
            teams = comp.get("competitors", [])
            away = next((x for x in teams if x.get("homeAway") == "away"), {})
            home = next((x for x in teams if x.get("homeAway") == "home"), {})
            status = event.get("status", {}).get("type", {}).get("shortDetail", "")
            rows.append({
                "Date / Time": event.get("date", "")[:16].replace("T", " "),
                "Matchup": f"{away.get('team', {}).get('abbreviation', '?')} @ {home.get('team', {}).get('abbreviation', '?')}",
                "Status": status,
                "Score": f"{away.get('score', '')} - {home.get('score', '')}" if status else ""
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No games returned for this date range.")
    except Exception:
        st.warning("Schedule feed unavailable. Refresh later.")

with t6:
    st.subheader("Data and model limitations")
    st.markdown("""
- Real completed-game player box scores are retrieved from ESPN.
- Select 7, 14 or 30 days of recent history.
- The ESPN injury report is displayed when available.
- Still to build: automatic injury-replacement ranking, odds imports, calibrated over/under probabilities, blowout and overtime probabilities, and backtesting.
- ESPN's public endpoints are unofficial and may change, rate-limit requests or omit data. Verify injury news and sportsbook lines separately.
- No projection is a guarantee or a recommendation to place a bet.
    """)
st.divider()
st.caption(f"NBA Edge v0.2 • Data window: {df.date.min().date()} to {df.date.max().date()} • Feed may be incomplete.")
