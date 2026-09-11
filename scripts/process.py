#!/usr/bin/env python3
"""Merge scraped captions into data/episodes.json and sync static copies.

Preserves curated summaries and the existing 10 quotes per episode.
Refreshes the `transcript` field from raw captions so search stays complete.
Copies the catalog to site/, docs/ (GitHub Pages), and public/.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "episodes.json"
RAW_DIRS = [ROOT / "raw", ROOT / "data" / "raw"]
SYNC_TARGETS = [
    ROOT / "site" / "episodes.json",
    ROOT / "docs" / "episodes.json",
    ROOT / "public" / "episodes.json",
]
PLAYLIST = "https://www.youtube.com/playlist?list=PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU"


def vtt_to_text(path: Path) -> str:
    chunks: list[str] = []
    last = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
            continue
        text = re.sub(r"<[^>]+>", "", line)
        text = re.sub(r"\s+", " ", text).strip()
        if text and text != last:
            chunks.append(text)
            last = text
    return " ".join(chunks)


def load_transcript(video_id: str) -> str:
    for folder in RAW_DIRS:
        txt = folder / f"{video_id}.txt"
        if txt.exists():
            return re.sub(r"\s+", " ", txt.read_text(encoding="utf-8")).strip()
        for pattern in (f"{video_id}.en.vtt", f"{video_id}.en-orig.vtt"):
            vtt = folder / pattern
            if vtt.exists():
                return vtt_to_text(vtt)
        matches = sorted(folder.glob(f"{video_id}*.vtt"))
        if matches:
            return vtt_to_text(matches[0])
    return ""


def sync_copies(payload: dict) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(text, encoding="utf-8")
    for dest in SYNC_TARGETS:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    # Keep the Pages UI files in lockstep with site/.
    for name in ("index.html", "app.js", "styles.css"):
        src = ROOT / "site" / name
        docs = ROOT / "docs" / name
        if src.exists():
            shutil.copy2(src, docs)


def main() -> int:
    parser = argparse.ArgumentParser(description="Attach transcripts and sync static copies")
    parser.add_argument(
        "--replace-transcripts",
        action="store_true",
        help="Overwrite existing transcript text from raw captions",
    )
    args = parser.parse_args()

    if not DATA_PATH.exists():
        raise SystemExit(f"Missing {DATA_PATH}. Need the curated episode catalog.")

    catalog = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    episodes = catalog.get("episodes") or []
    if not episodes:
        raise SystemExit("data/episodes.json has no episodes")

    for ep in episodes:
        vid = ep["id"]
        text = load_transcript(vid)
        if text and (args.replace_transcripts or not ep.get("transcript")):
            ep["transcript"] = text
        if not ep.get("transcript"):
            print(f"WARNING: no transcript for {vid}")
        else:
            print(f"{vid}  transcript={len(ep['transcript'])} chars  quotes={len(ep.get('quotes') or [])}")
        # Do not invent or replace summaries/quotes.

    catalog["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    catalog.setdefault("playlist", PLAYLIST)
    sync_copies(catalog)
    print(f"\nSynced {len(episodes)} episodes → data/, site/, docs/, public/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
