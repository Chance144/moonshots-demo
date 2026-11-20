#!/usr/bin/env python3
"""Fetch Moonshots episode metadata and English captions.

Primary path: yt-dlp (metadata + original English auto-captions).
Fallbacks for cloud / bot-checked IPs:
  - playlist RSS if the playlist page listing fails
  - yt-dlp player clients default, android, web_embedded, ios
    (retry with backoff on HTTP 429 or the bot check)
  - youtube-transcript-api for original English auto-captions
  - YouTube oEmbed for metadata
  - public timed transcripts (podscripts.co) matching the same episodes

Machine-translated English tracks are rejected. Nothing here invents a transcript.

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
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Existing seminar raw captions live in /raw; keep writing there.
RAW_DIR = ROOT / "raw"
ALT_RAW_DIR = ROOT / "data" / "raw"

PLAYLIST_ID = "PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU"
PLAYLIST_URL = f"https://www.youtube.com/playlist?list={PLAYLIST_ID}"
PLAYLIST_RSS_URL = (
    f"https://www.youtube.com/feeds/videos.xml?playlist_id={PLAYLIST_ID}"
)
# Rotate through these. android and web_embedded have each cleared the bot
# check on a past run; "default" is yt-dlp's built-in client set.
PLAYER_CLIENTS = ("default", "android", "web_embedded", "ios")
# Initial pass plus one retry pass. Back off only after 429 / bot-check.
CLIENT_PASSES = 2
ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"
MEDIA_NS = "http://search.yahoo.com/mrss/"
EN_AUTO_LANGS = ("en-orig", "en-US-orig", "en-GB-orig", "en", "en-US", "en-GB")
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


class ListingError(Exception):
    """Playlist listing failed and the caller should try another source."""


def _one_line(text: str, limit: int = 300) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return "unknown error"
    if len(cleaned) > limit:
        return cleaned[: limit - 1] + "…"
    return cleaned


def looks_like_bot_check(text: str) -> bool:
    lowered = (text or "").lower().replace("’", "'").replace("‘", "'")
    return "sign in to confirm" in lowered and "not a bot" in lowered


def looks_like_rate_limit(text: str) -> bool:
    lowered = (text or "").lower()
    if "too many requests" in lowered or "http error 429" in lowered:
        return True
    return bool(re.search(r"\b429\b", lowered) and "error" in lowered)


def _last_error_line(stderr: str, stdout: str) -> str:
    lines = [line.strip() for line in f"{stderr}\n{stdout}".splitlines() if line.strip()]
    for line in reversed(lines):
        lowered = line.lower()
        if "error" in lowered or "429" in line or "bot" in lowered:
            return _one_line(line)
    return _one_line(lines[-1] if lines else "")


def format_attempts(title: str, attempts: list[tuple[str, str]]) -> str:
    lines = [title]
    if not attempts:
        lines.append("  - (no method recorded)")
    for method, reason in attempts:
        lines.append(f"  - {method}: {_one_line(reason)}")
    return "\n".join(lines)


def _track_is_translation(track: dict) -> bool:
    """True for a machine-translated caption track, including translated 'en'."""
    url = track.get("url") or track.get("baseUrl") or ""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if query.get("tlang"):
        return True
    name = (track.get("name") or "").lower()
    if " from " in name:
        return True
    langs = [value.lower() for value in query.get("lang", [])]
    code = (track.get("language_code") or track.get("languageCode") or "").lower()
    if code.startswith("en") and langs and not any(value.startswith("en") for value in langs):
        return True
    return False


def _snapshot(video_id: str) -> dict[str, int]:
    snap: dict[str, int] = {}
    for path in RAW_DIR.glob(f"{video_id}*"):
        try:
            snap[path.name] = path.stat().st_mtime_ns
        except OSError:
            continue
    return snap


def _new_files(video_id: str, before: dict[str, int]) -> list[Path]:
    found: list[Path] = []
    for path in RAW_DIR.glob(f"{video_id}*"):
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            continue
        if path.name not in before or mtime > before[path.name]:
            found.append(path)
    return found


def _discard_subs(paths: list[Path], keep: Path | None = None) -> None:
    keep_name = keep.name if keep else None
    for path in paths:
        if path.suffix != ".vtt" or path.name == keep_name:
            continue
        try:
            path.unlink()
        except OSError:
            pass


def _matching_vtt(video_id: str, lang: str, created: list[Path]) -> Path | None:
    want = f"{video_id}.{lang}.vtt"
    for path in created:
        if path.suffix == ".vtt" and (path.name == want or f".{lang}." in path.name):
            return path
    return None


def choose_caption_file(
    info: dict, video_id: str, created: list[Path]
) -> tuple[Path | None, str]:
    """Prefer original English auto-captions; reject machine-translated 'en'."""
    autos = info.get("automatic_captions") or {}
    rejected: list[str] = []
    missing: list[str] = []
    for lang in EN_AUTO_LANGS:
        tracks = [track for track in (autos.get(lang) or []) if isinstance(track, dict)]
        if not tracks:
            continue
        if any(_track_is_translation(track) for track in tracks):
            rejected.append(lang)
            continue
        path = _matching_vtt(video_id, lang, created)
        if path and path.stat().st_size > 0:
            return path, ""
        missing.append(lang)
    if rejected:
        reason = "rejected machine-translated 'en' track(s): " + ", ".join(dict.fromkeys(rejected))
        if missing:
            reason += "; not saved: " + ", ".join(missing)
        return None, reason
    if missing:
        return None, "English auto-captions were not saved (" + ", ".join(missing) + ")"
    return None, "no English automatic captions"


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


def _record_from_info(video_id: str, info: dict) -> dict:
    return {
        "id": video_id,
        "title": info.get("title") or "",
        "description": info.get("description") or "",
        "channel": info.get("channel") or info.get("uploader") or "Peter H. Diamandis",
        "publishedAt": (info.get("upload_date") or "")[:8],
        "durationSeconds": int(info.get("duration") or 0) or None,
        "thumbnail": info.get("thumbnail")
        or f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        "youtubeUrl": f"https://www.youtube.com/watch?v={video_id}",
        "transcriptPath": None,
        "transcriptSource": "yt-dlp",
    }


def _ytdlp_once(ytdlp: str, video_id: str, client: str) -> tuple[int, str, str]:
    cmd = [
        ytdlp,
        "--skip-download",
        "--write-info-json",
        "--write-auto-sub",
        "--sub-langs",
        "en-orig,en",
        "--sub-format",
        "vtt",
        "--no-playlist",
        "--no-warnings",
        "--force-overwrites",
        "--retries",
        "0",
        "--extractor-retries",
        "0",
        "--extractor-args",
        f"youtube:player_client={client}",
        "--output",
        str(RAW_DIR / f"{video_id}.%(ext)s"),
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stderr or "", result.stdout or ""


def _backoff_seconds(pass_index: int) -> float:
    return float(min(8, 2 ** (pass_index + 1)))


def _will_retry(pass_index: int, client: str, retryable: set[str]) -> bool:
    later = [name for name in PLAYER_CLIENTS if name in retryable]
    if client in later and later.index(client) < len(later) - 1:
        return True
    return pass_index + 1 < CLIENT_PASSES and bool(retryable)


def scrape_ytdlp(video_id: str, attempts: list[tuple[str, str]]) -> dict | None:
    """Metadata plus original English auto-captions, rotating player clients."""
    ytdlp = find_ytdlp()
    if not ytdlp:
        attempts.append(("yt-dlp", "not on PATH"))
        print("  yt-dlp not on PATH; skipping primary extractor")
        return None

    best: dict | None = None
    retryable = set(PLAYER_CLIENTS)
    for pass_index in range(CLIENT_PASSES):
        if not retryable:
            break
        for client in PLAYER_CLIENTS:
            if client not in retryable:
                continue
            label = f"yt-dlp client={client} attempt={pass_index + 1}"
            print(f"  {label}")
            before = _snapshot(video_id)
            code, stderr, stdout = _ytdlp_once(ytdlp, video_id, client)
            created = _new_files(video_id, before)
            blob = f"{stderr}\n{stdout}"
            if code != 0:
                reason = _last_error_line(stderr, stdout)
                if code and reason == "unknown error":
                    reason = f"exit {code}"
                attempts.append((label, reason))
                print(f"  {label} failed: {reason}")
                _discard_subs(created)
                if looks_like_bot_check(blob) or looks_like_rate_limit(blob):
                    if _will_retry(pass_index, client, retryable):
                        delay = _backoff_seconds(pass_index)
                        print(f"  backing off {delay:.0f}s after {label}")
                        time.sleep(delay)
                else:
                    retryable.discard(client)
                continue

            info_path = RAW_DIR / f"{video_id}.info.json"
            if not info_path.exists():
                attempts.append((label, "exit 0 but no info json"))
                print(f"  {label} failed: exit 0 but no info json")
                retryable.discard(client)
                continue
            try:
                info = json.loads(info_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                attempts.append((label, f"invalid info json: {exc}"))
                print(f"  {label} failed: invalid info json")
                retryable.discard(client)
                continue

            record = _record_from_info(video_id, info)
            path, caption_reason = choose_caption_file(info, video_id, created)
            if path:
                _discard_subs(created, keep=path)
                record["transcriptPath"] = str(path)
                record["transcriptSource"] = "yt-dlp"
                attempts.append((label, "ok"))
                print(f"  {label} ok captions={path.name}")
                return record

            _discard_subs(created)
            attempts.append((label, caption_reason))
            print(f"  {label} metadata only: {caption_reason}")
            if best is None:
                best = record
            # A different client can still expose the original track.
            retryable.discard(client)
    return best


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
    try:
        html_text = http_get(PLAYLIST_URL)
    except urllib.error.HTTPError as exc:
        raise ListingError(f"HTTP {exc.code} {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ListingError(f"{exc.__class__.__name__}: {exc}") from exc
    if looks_like_bot_check(html_text):
        raise ListingError("Sign in to confirm you're not a bot")
    if looks_like_rate_limit(html_text):
        raise ListingError("HTTP 429")
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
    if not items:
        raise ListingError("playlist page returned no video ids")
    return items[:limit] if limit else items


def parse_playlist_rss(xml_text: str, limit: int | None = None) -> list[dict]:
    """Newest-first videos from a YouTube playlist Atom feed."""
    if looks_like_bot_check(xml_text):
        raise ListingError("Sign in to confirm you're not a bot")
    if looks_like_rate_limit(xml_text):
        raise ListingError("HTTP 429")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ListingError(f"invalid RSS XML: {exc}") from exc

    items: list[dict] = []
    seen: set[str] = set()
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        vid = (entry.findtext(f"{{{YT_NS}}}videoId") or "").strip()
        if not re.fullmatch(r"[\w-]{11}", vid) or vid in seen:
            continue
        seen.add(vid)
        title = html.unescape((entry.findtext(f"{{{ATOM_NS}}}title") or "").strip())
        published = (entry.findtext(f"{{{ATOM_NS}}}published") or "").strip()
        desc_el = entry.find(f"{{{MEDIA_NS}}}group/{{{MEDIA_NS}}}description")
        description = ""
        if desc_el is not None and desc_el.text:
            description = html.unescape(desc_el.text).strip()
        thumb_el = entry.find(f"{{{MEDIA_NS}}}group/{{{MEDIA_NS}}}thumbnail")
        thumbnail = thumb_el.get("url") if thumb_el is not None else ""
        author_el = entry.find(f"{{{ATOM_NS}}}author/{{{ATOM_NS}}}name")
        channel = author_el.text.strip() if author_el is not None and author_el.text else ""
        items.append(
            {
                "id": vid,
                "durationSeconds": None,
                "title": title,
                "publishedAt": published,
                "description": description,
                "thumbnail": thumbnail,
                "channel": channel,
            }
        )
    if not items:
        raise ListingError("RSS feed returned no videos")
    items.sort(key=lambda row: row.get("publishedAt") or "", reverse=True)
    return items[:limit] if limit else items


def playlist_rss(limit: int | None = None) -> list[dict]:
    try:
        xml_text = http_get(PLAYLIST_RSS_URL)
    except urllib.error.HTTPError as exc:
        raise ListingError(f"HTTP {exc.code} {exc.reason}") from exc
    except Exception as exc:  # noqa: BLE001
        raise ListingError(f"{exc.__class__.__name__}: {exc}") from exc
    return parse_playlist_rss(xml_text, limit)


def _english_code(code: str) -> bool:
    lowered = (code or "").lower().replace("_", "-")
    return lowered == "en" or lowered.startswith("en-")


def _transcript_is_translation(transcript: object) -> bool:
    url = getattr(transcript, "_url", "") or ""
    code = getattr(transcript, "language_code", "") or ""
    name = getattr(transcript, "language", "") or ""
    return _track_is_translation(
        {"url": url, "language_code": code, "name": name}
    )


def _cue_from_item(item: object) -> dict | None:
    if isinstance(item, dict):
        start = item.get("start", 0)
        duration = item.get("duration", 2)
        text = item.get("text") or ""
    else:
        start = getattr(item, "start", 0)
        duration = getattr(item, "duration", 2)
        text = getattr(item, "text", "") or ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    if not text:
        return None
    start_f = float(start or 0)
    return {"start": start_f, "end": start_f + float(duration or 0), "text": text}


def youtube_transcript_api(video_id: str) -> tuple[list[dict] | None, str]:
    """Original English auto-captions. Never requests a translated 'en' track."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
    except ImportError:
        return None, "not installed"
    try:
        listing = YouTubeTranscriptApi().list(video_id)
    except Exception as exc:  # noqa: BLE001
        return None, f"{exc.__class__.__name__}: {exc}"

    generated: list[object] = []
    manual: list[object] = []
    rejected: list[str] = []
    for transcript in listing:
        code = getattr(transcript, "language_code", "") or ""
        if not _english_code(code):
            continue
        if _transcript_is_translation(transcript):
            rejected.append(code)
            continue
        if getattr(transcript, "is_generated", False):
            generated.append(transcript)
        else:
            manual.append(transcript)

    # Auto-captions first. Manual English is still original speech, not a translation.
    pool = generated or manual
    if not pool:
        if rejected:
            return None, (
                "rejected machine-translated 'en' track(s): "
                + ", ".join(dict.fromkeys(rejected))
            )
        return None, "no original English auto-captions"

    def rank(transcript: object) -> tuple[int, str]:
        code = (getattr(transcript, "language_code", "") or "").lower()
        return (0 if code in {"en", "en-orig"} else 1, code)

    chosen = sorted(pool, key=rank)[0]
    try:
        fetched = chosen.fetch()
    except Exception as exc:  # noqa: BLE001
        return None, f"{exc.__class__.__name__}: {exc}"
    cues = [cue for item in fetched if (cue := _cue_from_item(item))]
    if not cues:
        return None, "original English track was empty"
    return cues, ""


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
    iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", value or "")
    if iso:
        return f"{iso.group(1)}-{iso.group(2)}-{iso.group(3)}"
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


def _fill_hint(record: dict, hint: dict) -> None:
    if hint.get("durationSeconds") and not record.get("durationSeconds"):
        record["durationSeconds"] = hint["durationSeconds"]
    if hint.get("title") and not record.get("title"):
        record["title"] = hint["title"]
    if hint.get("description") and not record.get("description"):
        record["description"] = hint["description"]
    if hint.get("publishedAt") and not record.get("publishedAt"):
        record["publishedAt"] = hint["publishedAt"]
    if hint.get("channel") and not record.get("channel"):
        record["channel"] = hint["channel"]
    if hint.get("thumbnail") and not record.get("thumbnail"):
        record["thumbnail"] = hint["thumbnail"]


def scrape_one(video_id: str, hint: dict | None = None) -> dict:
    hint = hint or {}
    print(f"\n== {video_id}")
    attempts: list[tuple[str, str]] = []
    record = scrape_ytdlp(video_id, attempts)

    if not record:
        try:
            record = oembed(video_id)
            record["durationSeconds"] = hint.get("durationSeconds")
            record["publishedAt"] = ""
            record["transcriptPath"] = None
            record["transcriptSource"] = "oembed"
            attempts.append(("oEmbed", "ok"))
        except Exception as exc:  # noqa: BLE001
            attempts.append(("oEmbed", f"{exc.__class__.__name__}: {exc}"))
            print(f"  oEmbed failed: {exc.__class__.__name__}: {exc}")
            record = {
                "id": video_id,
                "title": hint.get("title") or "",
                "description": hint.get("description") or "",
                "channel": hint.get("channel") or "Peter H. Diamandis",
                "publishedAt": hint.get("publishedAt") or "",
                "durationSeconds": hint.get("durationSeconds"),
                "thumbnail": hint.get("thumbnail")
                or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                "youtubeUrl": f"https://www.youtube.com/watch?v={video_id}",
                "transcriptPath": None,
                "transcriptSource": "metadata-only",
            }
    _fill_hint(record, hint)

    cues = None
    vtt_path = RAW_DIR / f"{video_id}.en.vtt"
    source: str | None
    if record.get("transcriptPath") and Path(record["transcriptPath"]).exists():
        source = "yt-dlp"
    else:
        cues, reason = youtube_transcript_api(video_id)
        if cues:
            write_vtt(vtt_path, cues)
            record["transcriptPath"] = str(vtt_path)
            source = "youtube-transcript-api"
            attempts.append(("youtube-transcript-api", "ok"))
        else:
            attempts.append(("youtube-transcript-api", reason))
            print(f"  youtube-transcript-api failed: {_one_line(reason)}")
            try:
                fallback = scrape_transcript_page(video_id, record.get("title") or "")
            except Exception as exc:  # noqa: BLE001
                fallback = None
                attempts.append(("podscripts", f"{exc.__class__.__name__}: {exc}"))
                print(f"  podscripts failed: {exc.__class__.__name__}: {exc}")
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
                attempts.append(("podscripts", "ok"))
            else:
                if not any(method == "podscripts" for method, _reason in attempts):
                    attempts.append(
                        ("podscripts", "no matching transcript page or empty transcript")
                    )
                source = None

    if not record.get("transcriptPath"):
        source = "metadata-only"
        report = format_attempts(
            f"FAILED {video_id}: no usable transcript. Methods tried:",
            attempts,
        )
        report += "\nNo transcript or quotes were fabricated."
        print(report, file=sys.stderr)
        record["transcriptError"] = report

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
    wrote_txt = False
    if vtt and vtt.exists():
        body = vtt_to_plaintext(vtt)
        txt_path.write_text(body, encoding="utf-8")
        record["transcriptTextPath"] = str(txt_path)
        wrote_txt = True
    ALT_RAW_DIR.mkdir(parents=True, exist_ok=True)
    for src in (out_info, vtt, txt_path if wrote_txt else None):
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

    listing_source = "ids"
    catalog: list[dict] = []
    if args.ids:
        video_ids = [v.strip() for v in args.ids.split(",") if v.strip()]
        mode = "ids"
    else:
        # Default (and --playlist): last N from PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU
        mode = "playlist"
        listing_failures: list[tuple[str, str]] = []
        try:
            catalog = playlist_catalog(args.limit)
            listing_source = "html"
            print(f"Playlist page: {len(catalog)} newest videos")
        except ListingError as exc:
            listing_failures.append(("playlist HTML", str(exc)))
            print(f"Playlist page failed ({exc}); trying RSS feed")
            try:
                catalog = playlist_rss(args.limit)
                listing_source = "rss"
                print(f"RSS feed: {len(catalog)} newest videos")
            except ListingError as rss_exc:
                listing_failures.append((f"RSS feed {PLAYLIST_RSS_URL}", str(rss_exc)))
                print(
                    format_attempts(
                        "FAILED playlist listing. Methods tried:",
                        listing_failures,
                    ),
                    file=sys.stderr,
                )
                return 1
        video_ids = [row["id"] for row in catalog]

    hint_by_id = {row["id"]: row for row in catalog}
    print(f"Scraping {len(video_ids)} episode(s) [{mode}/{listing_source}]")
    records = [scrape_one(vid, hint_by_id.get(vid)) for vid in video_ids]
    manifest = {
        "mode": mode,
        "listing": listing_source,
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
