#!/usr/bin/env python3
"""Fetch Moonshots episode metadata and English captions.

Primary path: yt-dlp (metadata + auto-captions).
Fallbacks for cloud / bot-checked IPs:
  - YouTube oEmbed + playlist/watch HTML for metadata
  - youtube-transcript-api if installed
  - public timed transcripts (podscripts.co) matching the same episodes

Usage:
  python3 scripts/scrape.py --ids vAgEf4jX_1o,1DB_QDiviH4,...
  python3 scripts/scrape.py --playlist --limit 5
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Existing seminar raw captions live in /raw; keep writing there.
RAW_DIR = ROOT / "raw"
ALT_RAW_DIR = ROOT / "data" / "raw"

PLAYLIST_URL = (
    "https://www.youtube.com/playlist?list=PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU"
)
PODSCRIPTS_SHOW = (
    "https://podscripts.co/podcasts/moonshots-with-peter-diamandis"
)
CHANNEL_URL = "https://www.youtube.com/@peterdiamandis"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# Last-five demo IDs → known public transcript pages (same episodes).
TRANSCRIPT_FALLBACKS = {
    "vAgEf4jX_1o": (
        "https://podscripts.co/podcasts/moonshots-with-peter-diamandis/"
        "why-jensen-huang-believes-weve-reached-agi-and-inside-openais-german-website-hijack-287"
    ),
    "1DB_QDiviH4": (
        "https://podscripts.co/podcasts/moonshots-with-peter-diamandis/"
        "gpt-6-astra-saturates-arc-agi-3-teslas-30k-cybercab-floods-austin-anthropic-proves-fermats-last-theorem-ep-286"
    ),
    "JywXvB8PpTs": (
        "https://podscripts.co/podcasts/moonshots-with-peter-diamandis/"
        "humanitys-first-star-probe-architect-labs-beats-nvidia-34x-musk-wants-satellites-to-cool-earth-ep-285"
    ),
    "tfBEWh9ibfU": (
        "https://podscripts.co/podcasts/moonshots-with-peter-diamandis/"
        "nvidias-962b-quarter-chinas-200000-fake-accounts-openais-new-chip-ep-284"
    ),
    "0mOXQ4_kY04": (
        "https://podscripts.co/podcasts/moonshots-with-peter-diamandis/"
        "sam-altman-singularity-slow-down-emad-runs-18-grokbots-waymo-slashes-hardware-83-ep-283"
    ),
}

DEFAULT_IDS = list(TRANSCRIPT_FALLBACKS.keys())


def http_get(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "ignore")


def seconds_to_ts(total: float) -> str:
    total = max(0, int(total))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.000"


def parse_clock(value: str) -> int | None:
    parts = value.strip().split(":")
    if not parts or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if len(nums) == 3:
        return nums[0] * 3600 + nums[1] * 60 + nums[2]
    if len(nums) == 2:
        return nums[0] * 60 + nums[1]
    return None


def vtt_to_plaintext(path: Path) -> str:
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


def write_vtt(path: Path, cues: list[dict]) -> None:
    lines = ["WEBVTT", ""]
    for i, cue in enumerate(cues):
        start = float(cue["start"])
        end = float(cue.get("end") or start + max(1.5, len(cue["text"].split()) * 0.4))
        if i + 1 < len(cues):
            end = min(end, float(cues[i + 1]["start"]) or end)
        if end <= start:
            end = start + 1.0
        lines.append(f"{seconds_to_ts(start)} --> {seconds_to_ts(end)}")
        lines.append(cue["text"].strip())
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def find_ytdlp() -> str | None:
    env = os.environ.get("YT_DLP")
    if env and Path(env).exists():
        return env
    found = shutil.which("yt-dlp")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "yt-dlp"
    if local.exists():
        return str(local)
    return None


def scrape_ytdlp(video_id: str) -> dict | None:
    ytdlp = find_ytdlp()
    if not ytdlp:
        print("  yt-dlp not on PATH; skipping primary extractor")
        return None
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        ytdlp,
        "--skip-download",
        "--write-info-json",
        "--write-auto-sub",
        "--sub-lang",
        "en",
        "--sub-format",
        "vtt",
        "--no-playlist",
        "--no-warnings",
        "--output",
        str(RAW_DIR / f"{video_id}.%(ext)s"),
        url,
    ]
    print(f"  yt-dlp {' '.join(cmd[1:8])} …")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip().splitlines()
        print(f"  yt-dlp failed: {err[-1] if err else 'unknown error'}")
        return None

    info_path = RAW_DIR / f"{video_id}.info.json"
    if not info_path.exists():
        return None
    info = json.loads(info_path.read_text(encoding="utf-8"))
    vtt = next(RAW_DIR.glob(f"{video_id}*.en*.vtt"), None) or next(
        RAW_DIR.glob(f"{video_id}*.vtt"), None
    )
    return {
        "id": video_id,
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "channel": info.get("channel") or info.get("uploader") or "Peter H. Diamandis",
        "publishedAt": (info.get("upload_date") or "")[:8],
        "durationSeconds": int(info.get("duration") or 0) or None,
        "thumbnail": info.get("thumbnail")
        or f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        "youtubeUrl": url,
        "transcriptPath": str(vtt) if vtt else None,
        "transcriptSource": "yt-dlp",
    }


def oembed(video_id: str) -> dict:
    url = (
        "https://www.youtube.com/oembed?url="
        + urllib.parse.quote(f"https://www.youtube.com/watch?v={video_id}", safe="")
        + "&format=json"
    )
    data = json.loads(http_get(url))
    return {
        "id": video_id,
        "title": data.get("title") or "",
        "channel": data.get("author_name") or "Peter H. Diamandis",
        "thumbnail": data.get("thumbnail_url")
        or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "youtubeUrl": f"https://www.youtube.com/watch?v={video_id}",
        "description": "",
    }


def playlist_catalog(limit: int | None = None) -> list[dict]:
    """Newest-first IDs + durations from the public playlist page."""
    html_text = http_get(PLAYLIST_URL)
    ordered: list[str] = []
    seen: set[str] = set()
    for vid in re.findall(r'"videoId":"([\w-]{11})"', html_text):
        if vid not in seen:
            seen.add(vid)
            ordered.append(vid)
    durations: dict[str, int] = {}
    for vid, clock in re.findall(
        r'"animationActivationTargetId":"([\w-]{11})".{0,80}?"text":"(\d+:\d+(?::\d+)?)"',
        html_text,
    ):
        secs = parse_clock(clock)
        if secs:
            durations[vid] = secs
    # Badge text sits near the id in either order; also scan overlay clocks.
    for vid in ordered:
        if vid in durations:
            continue
        window = html_text[max(0, html_text.find(vid) - 200) : html_text.find(vid) + 2500]
        clocks = re.findall(r'"text":"(\d+:\d{2}(?::\d{2})?)"', window)
        for clock in clocks:
            secs = parse_clock(clock)
            if secs and secs > 60:
                durations[vid] = secs
                break
    items = [{"id": vid, "durationSeconds": durations.get(vid)} for vid in ordered]
    return items[:limit] if limit else items


def youtube_transcript_api(video_id: str) -> list[dict] | None:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError:
        return None
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en"])
        cues = []
        for item in fetched:
            start = float(getattr(item, "start", item.get("start") if isinstance(item, dict) else 0))
            duration = float(
                getattr(item, "duration", item.get("duration") if isinstance(item, dict) else 2)
            )
            text = getattr(item, "text", item.get("text") if isinstance(item, dict) else "")
            cues.append({"start": start, "end": start + duration, "text": text})
        return cues or None
    except Exception as exc:  # noqa: BLE001
        print(f"  youtube-transcript-api blocked or failed: {exc.__class__.__name__}")
        return None


def parse_podscripts(page: str) -> tuple[list[dict], dict]:
    date_match = re.search(r"Episode Date:\s*([A-Za-z]+ \d{1,2}, \d{4})", page)
    published = date_match.group(1) if date_match else ""
    desc_match = re.search(
        r"(?:The mates[^\n<]{40,800}|In this episode[^\n<]{40,800})",
        page,
    )
    description = html.unescape(re.sub(r"<[^>]+>", " ", desc_match.group(0))) if desc_match else ""
    description = re.sub(r"\s+", " ", description).strip()

    cues: list[dict] = []
    current_start = 0.0
    # Walk the transcript in document order.
    token_re = re.compile(
        r'Starting point is (\d{2}:\d{2}:\d{2})|class="[^"]*transcript-text"[^>]*>(.*?)</span>',
        re.S,
    )
    for kind in token_re.finditer(page):
        clock, body = kind.group(1), kind.group(2)
        if clock:
            parsed = parse_clock(clock)
            if parsed is not None:
                current_start = float(parsed)
            continue
        text = html.unescape(re.sub(r"<[^>]+>", " ", body or ""))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cues.append({"start": current_start, "end": current_start + 4, "text": text})
    return cues, {"publishedAt": published, "description": description}


def podscripts_index() -> list[tuple[str, str]]:
    page = http_get(PODSCRIPTS_SHOW)
    pairs = re.findall(
        r'href="(/podcasts/moonshots-with-peter-diamandis/[^"]+)"',
        page,
    )
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for rel in pairs:
        if rel in seen or rel.rstrip("/").endswith("moonshots-with-peter-diamandis"):
            continue
        seen.add(rel)
        title = rel.rsplit("/", 1)[-1].replace("-", " ")
        out.append((f"https://podscripts.co{rel}", title))
    return out


def slug_tokens(value: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", value.lower()) if t not in {"with", "from", "that", "this"}}


def match_podscripts(title: str, index: list[tuple[str, str]] | None = None) -> str | None:
    index = index or podscripts_index()
    want = slug_tokens(title)
    best: tuple[int, str] | None = None
    for url, slug in index:
        have = slug_tokens(slug)
        score = len(want & have)
        if score >= 3 and (best is None or score > best[0]):
            best = (score, url)
    return best[1] if best else None


def scrape_transcript_page(video_id: str, title: str) -> tuple[list[dict], dict, str] | None:
    url = TRANSCRIPT_FALLBACKS.get(video_id) or match_podscripts(title)
    if not url:
        return None
    print(f"  transcript fallback: {url}")
    page = http_get(url)
    cues, meta = parse_podscripts(page)
    if not cues:
        return None
    return cues, meta, url


def normalize_published(value: str) -> str:
    if re.fullmatch(r"\d{8}", value or ""):
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    months = {
        "january": "01",
        "february": "02",
        "march": "03",
        "april": "04",
        "may": "05",
        "june": "06",
        "july": "07",
        "august": "08",
        "september": "09",
        "october": "10",
        "november": "11",
        "december": "12",
    }
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", value or "")
    if not m:
        return value or ""
    mon = months.get(m.group(1).lower())
    if not mon:
        return value
    return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"


def scrape_one(video_id: str, duration_hint: int | None = None) -> dict:
    print(f"\n== {video_id}")
    record = scrape_ytdlp(video_id)
    source = "yt-dlp" if record and record.get("transcriptPath") else None

    if not record:
        record = oembed(video_id)
        record["durationSeconds"] = duration_hint
        record["publishedAt"] = ""
        record["transcriptPath"] = None
        record["transcriptSource"] = "oembed"

    if duration_hint and not record.get("durationSeconds"):
        record["durationSeconds"] = duration_hint

    cues = None
    vtt_path = RAW_DIR / f"{video_id}.en.vtt"
    if record.get("transcriptPath") and Path(record["transcriptPath"]).exists():
        source = "yt-dlp"
    else:
        cues = youtube_transcript_api(video_id)
        if cues:
            write_vtt(vtt_path, cues)
            record["transcriptPath"] = str(vtt_path)
            source = "youtube-transcript-api"
        else:
            fallback = scrape_transcript_page(video_id, record.get("title") or "")
            if fallback:
                cues, extra, src_url = fallback
                write_vtt(vtt_path, cues)
                record["transcriptPath"] = str(vtt_path)
                record["transcriptPage"] = src_url
                if extra.get("description") and not record.get("description"):
                    record["description"] = extra["description"]
                if extra.get("publishedAt"):
                    record["publishedAt"] = extra["publishedAt"]
                source = "podscripts"
            else:
                print("  WARNING: no captions found")
                source = record.get("transcriptSource") or "metadata-only"

    record["publishedAt"] = normalize_published(record.get("publishedAt") or "")
    record["transcriptSource"] = source
    record["channelUrl"] = CHANNEL_URL
    record["playlistUrl"] = PLAYLIST_URL
    if not record.get("thumbnail"):
        record["thumbnail"] = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
    else:
        # Prefer the stable max-res still for seminar cards.
        record["thumbnail"] = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"

    out_info = RAW_DIR / f"{video_id}.info.json"
    out_info.write_text(json.dumps(record, indent=2), encoding="utf-8")
    # Plain-text transcript for the searchable episode database.
    vtt = Path(record["transcriptPath"]) if record.get("transcriptPath") else None
    txt_path = RAW_DIR / f"{video_id}.txt"
    if vtt and vtt.exists():
        body = vtt_to_plaintext(vtt)
        txt_path.write_text(body, encoding="utf-8")
        record["transcriptTextPath"] = str(txt_path)
    ALT_RAW_DIR.mkdir(parents=True, exist_ok=True)
    for src in (out_info, vtt, txt_path if txt_path.exists() else None):
        if src and src.exists():
            shutil.copy2(src, ALT_RAW_DIR / src.name)
    cue_count = len(cues) if cues else ("vtt" if record.get("transcriptPath") else 0)
    print(f"  saved {out_info.name}  transcript={source} cues={cue_count}")
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Moonshots episodes")
    parser.add_argument("--ids", help="Comma-separated YouTube video IDs")
    parser.add_argument("--playlist", action="store_true", help="Use the Moonshots playlist")
    parser.add_argument("--limit", type=int, default=5, help="Last N playlist episodes (newest first)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    duration_by_id: dict[str, int] = {}
    if args.ids:
        video_ids = [v.strip() for v in args.ids.split(",") if v.strip()]
        mode = "ids"
    else:
        # Default (and --playlist): last N from PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU
        mode = "playlist"
        try:
            catalog = playlist_catalog(args.limit)
            video_ids = [row["id"] for row in catalog]
            duration_by_id = {
                row["id"]: row["durationSeconds"]
                for row in catalog
                if row.get("durationSeconds")
            }
            print(f"Playlist mode: {len(video_ids)} newest videos")
        except Exception as exc:  # noqa: BLE001
            print(f"Playlist page failed ({exc}); falling back to default last 5 IDs")
            video_ids = DEFAULT_IDS[: args.limit]

    print(f"Scraping {len(video_ids)} episode(s) [{mode}]")
    records = [scrape_one(vid, duration_by_id.get(vid)) for vid in video_ids]
    manifest = {
        "mode": mode,
        "playlist": PLAYLIST_URL,
        "channel": CHANNEL_URL,
        "ids": video_ids,
        "records": records,
    }
    (RAW_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    missing = [r["id"] for r in records if not r.get("transcriptPath")]
    if missing:
        print(f"\nMissing transcripts: {', '.join(missing)}", file=sys.stderr)
        return 2
    print(f"\nWrote {len(records)} records to {RAW_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
