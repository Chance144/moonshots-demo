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

`scripts/scrape.py` lists playlist `PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU`, then fetches metadata and English auto-captions. If that page is blocked, listing uses the RSS feed `https://www.youtube.com/feeds/videos.xml?playlist_id=PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU`. yt-dlp rotates player clients `default`, `android`, `web_embedded`, and `ios`, and backs off before retrying on HTTP 429 or YouTube's "Sign in to confirm you're not a bot" check. Captions then fall back to `youtube-transcript-api`. Original English auto-captions are kept; machine-translated `en` tracks are rejected. If every method fails, the script reports each attempt and does not invent a transcript or quote. Writes `raw/<id>.info.json`, `.en.vtt` or `.en-orig.vtt`, and `.txt`.

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

Optional: `pip install yt-dlp youtube-transcript-api`

## Demo episode IDs (newest first)

1. `s5BFumpCH_Q` — AMA #293
2. `LNBzLTLuLUo` — EP #292
3. `DrV4WwNEAZE` — EP #291
4. `2uiIEdmL040` — EP #290
5. `H5ZLorBJCDk` — AMA #289

## Auto-refresh

- **Tender routine** (primary): every day at 8:00 AM PT — scrapes the latest 5 Moonshots, adds summaries/quotes/transcripts for new episodes, keeps five on the catalog, pushes to `main` (GitHub Pages).
