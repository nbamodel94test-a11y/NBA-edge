# NBA Edge — Starter v0.1

This is the first working shell of your personal NBA analytics dashboard.

## What is included
- Player game-log dashboard
- Transparent last-5 / last-10 baseline projections
- Historical same-game 8+ rebounds AND 8+ assists frequency
- Manual expected-minutes adjustment
- Sportsbook line and break-even odds calculator
- Game-environment input workspace

## Important
The included `sample_game_logs.csv` contains **fictional demo data** so you can see the dashboard work. It is not real NBA data and should never be used to make bets.

## Install (Windows or Mac)
1. Install Python 3.11 or newer from https://www.python.org/downloads/
   - Windows: check "Add Python to PATH" during installation.
2. Download and unzip this project.
3. Open Terminal (Mac) or Command Prompt (Windows).
4. Move into the unzipped folder:
   `cd path/to/nba_edge_starter`
5. Install packages:
   `python -m pip install -r requirements.txt`
6. Start the dashboard:
   `python -m streamlit run app.py`
7. A browser tab should open automatically. If not, copy the local URL shown in the terminal into your browser.

## CSV format for real game logs
Your CSV must contain these columns:
- `player`
- `date`
- `minutes`
- `points`
- `rebounds`
- `assists`

Optional columns such as `team` and `opponent` are welcome; they are not used yet.

Example:
`player,date,minutes,points,rebounds,assists`

Use the sidebar uploader to load a CSV.

## Next development milestones
1. Connect a reliable free historical NBA data source.
2. Build a proper minutes and player-stat projection model.
3. Add injury news and teammate replacement analysis.
4. Add probability distributions, calibration and backtesting.
5. Add game spread / total, blowout and overtime simulation.
6. Save daily projections and results in a database.
