# Moonshots Archive

Searchable site for the last five [Moonshots with Peter Diamandis](https://www.youtube.com/playlist?list=PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU) episodes. Built as a live demo for a WSU faculty seminar.

Channel: [youtube.com/@peterdiamandis](https://www.youtube.com/@peterdiamandis)

## Quick start

```bash
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`). The five processed episodes are already in `data/episodes.json` / `public/episodes.json`, so the UI works without re-scraping.

## What’s on the site

- Episode cards with YouTube thumbnails
- Detail view: extractive summary, top 10 verbatim quotes (with timestamps), YouTube link
- Live client-side search over titles, summaries, and quotes
- Large type and high contrast for a seminar room

Summaries and quotes are **copied from the episode transcript**. They are not model-invented paraphrases.

## Data pipeline

```bash
# 1. Fetch metadata + English captions for the five demo IDs
npm run scrape

# Or: last N videos from the official playlist (newest first)
npm run scrape:playlist
# equivalent: python3 scripts/scrape.py --playlist --limit 5

# 2. Build extractive summaries + quotes → data/episodes.json
npm run process

# Both steps
npm run data
```

| Script | What it does |
| --- | --- |
| `scripts/scrape.py` | Primary: **yt-dlp** (`--write-info-json --write-auto-sub --sub-lang en`). Playlist mode resolves IDs from the YouTube playlist page when yt-dlp is bot-checked. Caption fallback: `youtube-transcript-api` if installed, then public timed transcripts for the same episodes. Writes `data/raw/<id>.info.json` and `data/raw/<id>.en.vtt`. |
| `scripts/process.py` | Parses VTT, scores real caption sentences, writes a 300–500 word **extractive** summary and 10 quotes with timestamps. Copies JSON to `data/episodes.json` and `public/episodes.json`. |

Optional system dependency:

```bash
pip install yt-dlp
```

YouTube often blocks cloud IPs. The scraper still completes via oEmbed + playlist HTML + timed-transcript fallbacks so a seminar machine can rebuild `episodes.json` without cookies. On a normal laptop, yt-dlp is the preferred path.

### Demo episode IDs (newest first)

1. `vAgEf4jX_1o` — OpenAI Agents Hijack a German Website, Jensen Declares AGI Arrived, and OpenAI Solves Navier-Stokes
2. `1DB_QDiviH4` — Anthropic's Fable 5.1 Hits 60.9% on Humanity's Last Exam, GPT-6 Astra Drops, & the Cybercab Takeover
3. `JywXvB8PpTs` — OpenAI Cuts Off Elon's Cursor, Humanity's First Star Probe, and Trump's Nuclear Mars Ship \| EP #285
4. `tfBEWh9ibfU` — NVIDIA's $96.2B Quarter, China's 200,000 Fake Accounts, & OpenAI's New Chip \| EP #284
5. `0mOXQ4_kY04` — Sam Altman: Singularity Slow-Down, Emad Runs 18 Grokbots, Waymo Slashes Hardware 83% \| EP #283

## App scripts

| Command | Purpose |
| --- | --- |
| `npm install` | Install UI dependencies |
| `npm run dev` | Vite + React + TypeScript dev server |
| `npm run build` | Production build |
| `npm run preview` | Serve the production build |
| `npm run scrape` | Scrape the five IDs above |
| `npm run scrape:playlist` | Scrape last 5 from the playlist |
| `npm run process` | Generate `data/episodes.json` |
| `npm run data` | scrape + process |

## Stack

Vite, React 19, TypeScript, React Router. No backend — search runs in the browser against `public/episodes.json`.

`docs/` is a static GitHub Pages snapshot of an earlier vanilla demo. Use `npm run dev` for the seminar app.
