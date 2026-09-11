# Moonshots Archive

Searchable archive of the last five [Moonshots with Peter Diamandis](https://www.youtube.com/playlist?list=PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU) episodes. WSU faculty seminar demo.

Channel: [youtube.com/@peterdiamandis](https://www.youtube.com/@peterdiamandis)

**GitHub Pages** serves `docs/` (copy of `site/`). Full transcripts live on each episode and are included in search. Opening a hit expands that episode.

## Quick start (Pages-ready static site)

```bash
python3 -m http.server 4173 --directory docs
# or: npm start
# or: make serve
```

Open http://localhost:4173

`data/episodes.json` is the source catalog (5 episodes, summary + 10 caption quotes + full `transcript`). It is copied to `site/episodes.json`, `docs/episodes.json`, and `public/episodes.json`.

## Refresh captions (yt-dlp)

```bash
# last 5 from playlist PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU
npm run scrape
# or
make scrape

# then attach transcripts + sync site/docs/public (does not replace curated summaries/quotes)
npm run process
# or
make process

# both
npm run data
make data
```

`scripts/scrape.py` uses **yt-dlp** first (`--write-info-json --write-auto-sub --sub-lang en`). If YouTube bot-checks the IP, it falls back to oEmbed + playlist HTML + timed transcripts. Writes `raw/<id>.info.json`, `.en.vtt`, and `.txt`.

| Command | Purpose |
| --- | --- |
| `npm start` / `make serve` | Serve `docs/` (Pages-identical) |
| `npm run dev` | Serve `site/` |
| `npm run scrape` / `make scrape` | yt-dlp last 5 from the playlist |
| `npm run scrape:ids` / `make scrape-ids` | Scrape the five pinned demo IDs |
| `npm run process` / `make process` | Refresh `transcript` fields and sync copies |
| `npm run data` / `make data` | scrape + process |
| `npm run pages` | Same as process (sync Pages files) |
| `npm run dev:vite` | Optional Vite + React UI on the same JSON |

Optional: `pip install yt-dlp`

## Demo episode IDs (newest first)

1. `vAgEf4jX_1o`
2. `1DB_QDiviH4`
3. `JywXvB8PpTs` — EP #285
4. `tfBEWh9ibfU` — EP #284
5. `0mOXQ4_kY04` — EP #283
