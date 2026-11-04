<div align="center">

# ⚽ Final Whistle

**👉 Live: [final-whistle-kohl.vercel.app](https://final-whistle-kohl.vercel.app)**

### Who's actually going to win the league?
**Final Whistle plays out the rest of the season thousands of times so you don't have to guess.**

![Status](https://img.shields.io/badge/status-in%20development-orange)
![Season](https://img.shields.io/badge/season-2026%2F27-blue)
![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-61DAFB?logo=react&logoColor=black)

</div>

---

## 🏆 The idea

Every fan has an opinion. *"We're definitely finishing top four." "They're going down for sure."*

Final Whistle swaps gut feeling for numbers. It looks at every result so far, works out how strong each team really is, and then **simulates every remaining match of the season 10,000 times**. What comes out is the real odds:

- 🥇 **Title race:** each team's chance of lifting the trophy
- 📊 **Final table:** where every club is likely to finish
- 🇪🇺 **Europe:** who's on course for Champions League places
- ⬇️ **Relegation:** who's in real danger
- 🆚 **Match predictions:** home win, draw or away win for upcoming games
- ⭐ **Champions League:** who survives the league phase, and who's lifting the trophy in the final

## 🌍 Competitions

| | Competition |
|---|---|
| 🏴󠁧󠁢󠁥󠁮󠁧󠁿 | Premier League |
| 🇪🇸 | La Liga |
| 🇩🇪 | Bundesliga |
| 🇮🇹 | Serie A |
| ⭐ | UEFA Champions League |

## 🤝 The promise

Most "predictions" online are vibes with a percentage sign stuck on. Final Whistle has some ground rules:

- **No made-up numbers.** Every percentage comes from real match data and a model run you can trace.
- **Always timestamped.** You'll always see when a forecast was made and how fresh the data is.
- **Honest about uncertainty.** A 70% favourite still loses 3 times in 10. That's football.
- **It shows its record.** Predictions get checked against what actually happened, misses included.

## 🛣️ Roadmap

- [x] Pick a data source that covers all five competitions for 2026/27
- [x] Project foundations
- [x] Pull in fixtures, results and tables (6,400+ matches so far)
- [x] Team strength ratings and match predictions (first version, still being tested)
- [x] League season simulator (title, Europe and relegation odds; being tested)
- [x] Champions League simulator (league phase, then knockouts, built from UEFA's official rules)
- [x] Test predictions against past seasons (they beat simple baselines; full report in `docs/backtest-report.md`)
- [x] Data API for the dashboard
- [x] The dashboard 🎨
- [x] Live online, refreshed daily 🚀
- [ ] Go live 🚀

## 🔧 Under the hood

Python and FastAPI do the number-crunching, React draws the dashboard, and match data comes from [football-data.org](https://www.football-data.org/).

Curious how it works in detail? The full project spec is in [`README.md`](../README.md), and the docs are in [`docs/`](../docs).

---

<div align="center">

*Built for fans who like their hot takes backed by data.* 📈

<sub>An independent fan project, not affiliated with any league, club, UEFA or data provider.<br>Not a betting tool.</sub>

</div>
