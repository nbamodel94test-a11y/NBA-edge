import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

st.set_page_config(page_title="NBA Edge", page_icon="🏀", layout="wide")

REQUIRED = ["player", "date", "minutes", "points", "rebounds", "assists"]

def load_data(uploaded):
    if uploaded is not None:
        df = pd.read_csv(uploaded)
        source = "Uploaded CSV"
    else:
        path = Path(__file__).parent / "sample_game_logs.csv"
        df = pd.read_csv(path)
        source = "DEMO DATA — fictional examples, not real NBA statistics"
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        st.error("Your CSV is missing these required columns: " + ", ".join(missing))
        st.stop()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ["minutes", "points", "rebounds", "assists"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["player", "date", "minutes", "points", "rebounds", "assists"])
    return df.sort_values("date"), source

def player_summary(df, player):
    p = df[df.player == player].sort_values("date")
    if p.empty:
        return None
    last5, last10 = p.tail(5), p.tail(10)
    n = min(len(p), 10)
    # Transparent baseline: 60% recent 5-game mean + 40% last-10 mean.
    # Not yet opponent-, pace-, injury- or minutes-adjusted.
    result = {}
    for stat in ["points", "rebounds", "assists", "minutes"]:
        result[stat] = 0.60 * last5[stat].mean() + 0.40 * last10[stat].mean()
    result["games"] = len(p)
    result["8_8_rate"] = ((p.rebounds >= 8) & (p.assists >= 8)).mean()
    result["reb8_rate"] = (p.rebounds >= 8).mean()
    result["ast8_rate"] = (p.assists >= 8).mean()
    result["last10"] = last10
    result["n10"] = len(last10)
    return result

st.title("🏀 NBA EDGE")
st.caption("Personal NBA analytics dashboard | Starter build v0.1")
df, source = load_data(st.sidebar.file_uploader("Upload player game-log CSV", type=["csv"]))
st.sidebar.caption(source)
players = sorted(df.player.dropna().unique().tolist())
if not players:
    st.warning("No player rows found. Upload a CSV with the required columns.")
    st.stop()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Player Props", "8 + 8 Finder", "Injury Impact", "Vegas Comparison", "Game Script"
])

with tab1:
    st.subheader("Player projection workspace")
    player = st.selectbox("Player", players, key="prop_player")
    s = player_summary(df, player)
    if s:
        cols = st.columns(4)
        for col, label, key in zip(cols, ["Points", "Rebounds", "Assists", "Minutes"],
                                   ["points", "rebounds", "assists", "minutes"]):
            col.metric(label, f"{s[key]:.1f}")
        st.info("Baseline formula: 60% last-five average + 40% last-ten average. This is a starting benchmark, not a calibrated probability model.")
        hist = s["last10"][["date", "minutes", "points", "rebounds", "assists"]].copy()
        st.dataframe(hist.sort_values("date", ascending=False), use_container_width=True, hide_index=True)
        st.caption(f"{s['games']} game logs available for this player; {s['n10']} in the recent window.")

with tab2:
    st.subheader("Players with 8 rebounds AND 8 assists potential")
    rows = []
    for name in players:
        s = player_summary(df, name)
        if s:
            rows.append({
                "Player": name,
                "Projected REB": round(s["rebounds"], 1),
                "Projected AST": round(s["assists"], 1),
                "Historical 8+ REB & 8+ AST": f"{s['8_8_rate']:.0%}",
                "8+ REB rate": f"{s['reb8_rate']:.0%}",
                "8+ AST rate": f"{s['ast8_rate']:.0%}",
                "Games": s["games"]
            })
    table = pd.DataFrame(rows).sort_values(["Projected REB", "Projected AST"], ascending=False)
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption("Joint 8/8 frequency is calculated from the same games, not by multiplying separate rebound and assist rates. Small samples are highly uncertain.")

with tab3:
    st.subheader("Manual injury / role-change adjustment")
    st.write("This first version lets you test a minutes change. Later we will automatically estimate who inherits minutes and usage when teammates sit.")
    player = st.selectbox("Player", players, key="inj_player")
    s = player_summary(df, player)
    base_min = float(s["minutes"])
    expected_min = st.slider("Expected minutes tonight", 0.0, 48.0, float(min(48, round(base_min))), 0.5)
    factor = expected_min / max(base_min, 1)
    c1, c2, c3 = st.columns(3)
    c1.metric("Baseline minutes", f"{base_min:.1f}")
    c2.metric("Minutes adjustment", f"{expected_min-base_min:+.1f}")
    c3.metric("Adjusted points estimate", f"{s['points']*factor:.1f}")
    st.warning("This is a simple per-minute scaling illustration. It does not yet model role changes, usage redistribution, lineup combinations, or teammate-specific injury effects.")

with tab4:
    st.subheader("Compare your projection with a sportsbook line")
    player = st.selectbox("Player", players, key="vegas_player")
    stat = st.selectbox("Market", ["points", "rebounds", "assists"], key="vegas_stat")
    s = player_summary(df, player)
    line = st.number_input("Sportsbook line", min_value=0.0, max_value=100.0, value=7.5, step=0.5)
    odds = st.number_input("American odds", min_value=-1000, max_value=1000, value=-110, step=5)
    projection = s[stat]
    st.metric("Baseline projection", f"{projection:.1f}", f"{projection-line:+.1f} vs line")
    st.write("Odds break-even probability (before any push treatment):")
    breakeven = abs(odds)/(abs(odds)+100) if odds < 0 else 100/(odds+100)
    st.metric("Break-even", f"{breakeven:.1%}")
    st.info("Probability and expected value are intentionally withheld in v0.1. We need a validated player-stat distribution and push handling before presenting those numbers.")

with tab5:
    st.subheader("Game environment inputs")
    st.write("A first workspace for the game-script model. These inputs will feed the blowout and overtime simulation in a later version.")
    a, b = st.columns(2)
    with a:
        spread = st.number_input("Favorite's point spread (enter positive number)", min_value=0.0, max_value=40.0, value=5.5, step=0.5)
        total = st.number_input("Projected game total", min_value=150.0, max_value=300.0, value=225.5, step=0.5)
    with b:
        ot = st.slider("Your initial overtime assumption", 0, 20, 5)
        close_game = st.slider("Expected closeness (1 = mismatch, 10 = very close)", 1, 10, 6)
    st.metric("Game total input", f"{total:.1f}")
    st.metric("Spread input", f"{spread:.1f}")
    st.metric("Manual OT assumption", f"{ot}%")
    st.caption("No blowout or overtime probability is calculated yet. We will estimate those from historical score margins, spreads, totals, pace and team strength after the data layer is in place.")

st.divider()
st.caption("NBA Edge v0.1 • Demo rows are fictional. No live injury feed, odds feed, or automated NBA data connection is active yet.")
