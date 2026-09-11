#!/usr/bin/env python3
"""Turn scraped captions into episode summaries + verbatim quotes.

Summaries are extractive: every sentence is copied from the transcript.
Quotes are likewise verbatim caption sentences with their timestamps.
Nothing is invented.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_PATH = ROOT / "data" / "episodes.json"
PUBLIC_PATH = ROOT / "public" / "episodes.json"

HOSTS = {
    "peter": "Peter Diamandis",
    "dave": "Dave Blundin",
    "alex": "Alexander Wissner-Gross",
    "salim": "Salim Ismail",
    "emad": "Emad Mostaque",
    "philip": "Philip Johnston",
    "matt": "Matt Pines",
}

AD_PATTERNS = re.compile(
    r"(blitzy|fountain life|metatrends|megaphone\.fm|ad choices|"
    r"hit the subscribe|please hit subscribe|qr\.diamandis|"
    r"moonshots\.com/ama|this episode is brought to you|"
    r"go to blitzy|schedule a call with fountain)",
    re.I,
)
INTRO_NOISE = re.compile(
    r"(welcome to moonshots|i'm here with my moonshot|number one podcast|"
    r"front row seat|if you're new to moonshots|please hit the subscribe)",
    re.I,
)
WORD_RE = re.compile(r"[A-Za-z0-9']+")
LYRICS = re.compile(
    r"(moonshots mate|glow trotting|intelligence wants to be free|"
    r"no dystopia here|dice and spear|mtp system thinking|"
    r"efficiency maxing|s-i voice|got his mind on the truth)",
    re.I,
)
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])")


def parse_vtt(path: Path) -> list[dict]:
    cues: list[dict] = []
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", text)
    ts_re = re.compile(
        r"(\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+-->\s+(\d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    )
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip() and ln.strip() != "WEBVTT"]
        if not lines:
            continue
        match = None
        payload: list[str] = []
        for ln in lines:
            if "-->" in ln:
                match = ts_re.search(ln)
                continue
            if ln.isdigit():
                continue
            clean = re.sub(r"<[^>]+>", "", ln)
            clean = re.sub(r"&nbsp;", " ", clean)
            payload.append(clean)
        if not match or not payload:
            continue
        start = vtt_clock(match.group(1))
        end = vtt_clock(match.group(2))
        body = re.sub(r"\s+", " ", " ".join(payload)).strip()
        if body:
            cues.append({"start": start, "end": end, "text": body})
    # Deduplicate overlapping auto-caption repeats.
    deduped: list[dict] = []
    seen = ""
    for cue in cues:
        if cue["text"] == seen:
            continue
        deduped.append(cue)
        seen = cue["text"]
    return deduped


def vtt_clock(value: str) -> float:
    h, m, rest = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


def format_ts(seconds: float) -> str:
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def parse_info(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


KNOWN_EPISODE_NUMBERS = {
    "vAgEf4jX_1o": 287,
    "1DB_QDiviH4": 286,
    "JywXvB8PpTs": 285,
    "tfBEWh9ibfU": 284,
    "0mOXQ4_kY04": 283,
}

ADULT = re.compile(
    r"\b(porn|sexual partners|sexual encounters|girlfriends? and boyfriends?|mocap suit)\b",
    re.I,
)
JUNK_MORE = re.compile(
    r"(longevity calling|abundance waves|multidimensional brains|"
    r"wasn't that great|hit pause on the rest of my life|"
    r"hitchhiker's guide|subscriber love|moonshots\.com|"
    r"i read all the comments|please register now|"
    r"for those who can see in the|upper sub-diagram|"
    r"left-slash-lower|navel gazing)",
    re.I,
)


def episode_number(title: str, video_id: str = "") -> int | None:
    if video_id in KNOWN_EPISODE_NUMBERS:
        return KNOWN_EPISODE_NUMBERS[video_id]
    match = re.search(r"EP\s*#?\s*(\d+)|#(\d{3,})", title, re.I)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def title_terms(title: str) -> set[str]:
    stop = {
        "with",
        "from",
        "that",
        "this",
        "and",
        "the",
        "for",
        "into",
        "your",
        "you",
        "off",
        "hits",
        "last",
    }
    terms = {t for t in tokenize(title) if len(t) > 2 and t not in stop}
    for num in re.findall(r"\d+(?:\.\d+)?", title):
        terms.add(num)
        terms.add(num.replace(".", ""))
    for t in list(terms):
        if t.endswith("s") and len(t) > 4:
            terms.add(t[:-1])
    return terms


def sentences_from_cues(cues: list[dict]) -> list[dict]:
    # Merge caption fragments into sentences, keeping the start time of the first fragment.
    buf = ""
    start = None
    out: list[dict] = []
    for cue in cues:
        piece = cue["text"].strip()
        if not piece:
            continue
        if start is None:
            start = cue["start"]
        if buf and not buf.endswith((" ", "\n")):
            buf += " "
        buf += piece
        while True:
            match = SENTENCE_SPLIT.search(buf)
            if not match:
                break
            sent = buf[: match.start()].strip()
            buf = buf[match.end() :].strip()
            if sent:
                out.append({"text": clean_sentence(sent), "start": start})
            start = cue["start"]
        if buf.endswith((".", "!", "?")) and len(buf.split()) >= 6:
            out.append({"text": clean_sentence(buf), "start": start})
            buf = ""
            start = None
    if buf and len(buf.split()) >= 8:
        out.append({"text": clean_sentence(buf), "start": start or 0})
    return [s for s in out if s["text"]]


def clean_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" ,", ",").replace(" .", ".")
    return text


def tokenize(text: str) -> list[str]:
    text = re.sub(r"(\d),(\d)", r"\1\2", text)
    extras = []
    for num in re.findall(r"\d+\.\d+", text):
        extras.append(num.replace(".", ""))
        extras.append(num.split(".", 1)[0])
    words: list[str] = []
    for raw in WORD_RE.findall(text):
        w = raw.lower()
        if w.endswith("'s") or w.endswith("’s"):
            w = w[:-2]
        words.append(w)
    words.extend(extras)
    if "cyber" in words and "cab" in words:
        words.append("cybercab")
    if "grokbot" in words:
        words.append("grokbots")
    if "grokbots" in words:
        words.append("grokbot")
    return words


def is_junk(text: str) -> bool:
    if AD_PATTERNS.search(text) or JUNK_MORE.search(text) or LYRICS.search(text) or ADULT.search(text):
        return True
    if INTRO_NOISE.search(text) and len(text.split()) < 28:
        return True
    if len(text.split()) < 8:
        return True
    if text.count("http") or "www." in text.lower():
        return True
    letters = re.sub(r"[^A-Za-z]", "", text)
    if letters and sum(ch.isupper() for ch in letters) / len(letters) > 0.35 and len(text.split()) < 20:
        return True
    return False


def infer_speaker(text: str) -> str | None:
    lower = text.lower()
    # Only label when the caption itself names the speaker clearly.
    named = re.match(
        r"^(peter|dave|alex|salim|emad|philip|matt)(?:\s+(diamandis|blundin|ismail|mostaque|johnston|pines|wissner[-\s]gross))?\s*[:,—-]\s+",
        text,
        re.I,
    )
    if named:
        return HOSTS.get(named.group(1).lower())
    for key, label in HOSTS.items():
        if lower.startswith(f"{key} said") or lower.startswith(f"{label.lower()} said"):
            return label
    return None


def score_sentence(sent: dict, df: Counter, n_docs: int, title_toks: set[str]) -> float:
    text = sent["text"]
    words = tokenize(text)
    if is_junk(text):
        return -1.0
    n = len(words)
    if n < 10 or n > 55:
        length_score = 0.15
    elif 16 <= n <= 40:
        length_score = 1.0
    else:
        length_score = 0.6

    tf = Counter(words)
    info = 0.0
    for w, c in tf.items():
        if len(w) < 4:
            continue
        idf = math.log((n_docs + 1) / (1 + df[w])) + 1
        info += c * idf
    info /= math.sqrt(n)

    overlap = len(set(words) & title_toks)
    bonus = overlap * 1.6
    if re.search(r"\d", text):
        bonus += 0.7
    if re.search(
        r"\b(AGI|ASI|OpenAI|NVIDIA|Anthropic|Fable|Astra|Waymo|Grok|Cybercab|Navier|wiki|DSEWiki)\b",
        text,
    ):
        bonus += 0.55
    if re.search(r"\b(I think|the point is|what's happening|this is|you know)\b", text, re.I):
        bonus -= 0.05
    if text.endswith("?"):
        bonus -= 0.35
    t = sent["start"]
    if t < 45:
        bonus += 0.35  # cold-open recap often states the headlines
    elif t < 180:
        bonus -= 0.15
    if 180 <= t <= 7000:
        bonus += 0.1
    return info * 0.25 + length_score + bonus


def mmr_select(candidates: list[dict], k: int, lambda_div: float = 0.72) -> list[dict]:
    selected: list[dict] = []
    remaining = candidates[:]
    while remaining and len(selected) < k:
        best = None
        best_val = -1e9
        for item in remaining:
            if not selected:
                val = item["score"]
            else:
                overlap = max(jaccard(item["tokens"], other["tokens"]) for other in selected)
                val = lambda_div * item["score"] - (1 - lambda_div) * overlap * 3
            if val > best_val:
                best_val = val
                best = item
        selected.append(best)  # type: ignore[arg-type]
        remaining.remove(best)  # type: ignore[arg-type]
    return selected


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def word_count_text(text: str) -> int:
    return len(text.split())


def build_summary(sentences: list[dict], title_toks: set[str]) -> tuple[str, int]:
    usable = [s for s in sentences if s["score"] > 0.2 and not is_junk(s["text"])]
    if not usable:
        usable = [s for s in sentences if not is_junk(s["text"])]

    on_title = [s for s in usable if len(s["tokens"] & title_toks) >= 1]
    on_title.sort(key=lambda x: (-len(x["tokens"] & title_toks), -x["score"], x["start"]))
    buckets: dict[int, list[dict]] = {}
    for s in usable:
        buckets.setdefault(int(s["start"] // 480), []).append(s)

    seeds: list[dict] = []
    early = [s for s in on_title if s["start"] <= 360][:6]
    densest = sorted(on_title, key=lambda x: (-len(x["tokens"] & title_toks), -x["score"]))[:5]
    seeds.extend(early)
    seeds.extend(densest)
    seeds.extend(on_title[:8])
    pinned_ids = {id(s) for s in early + densest}
    for key in sorted(buckets):
        ranked = sorted(buckets[key], key=lambda x: x["score"], reverse=True)
        seeds.extend(ranked[:1])
    # Unique by identity
    uniq: list[dict] = []
    seen: set[int] = set()
    for s in seeds:
        if id(s) in seen:
            continue
        seen.add(id(s))
        uniq.append(s)
    seeds = mmr_select(sorted(uniq, key=lambda x: x["score"], reverse=True), k=min(16, len(uniq)))

    chosen = {id(s): s for s in seeds}
    rest = [s for s in usable if id(s) not in chosen]
    rest.sort(key=lambda x: x["score"], reverse=True)

    ordered = sorted(chosen.values(), key=lambda x: x["start"])
    for s in early + densest:
        if id(s) not in {id(x) for x in ordered}:
            ordered.append(s)
    ordered.sort(key=lambda x: x["start"])

    def count(items: list[dict]) -> int:
        return word_count_text(" ".join(i["text"] for i in items))

    for extra in rest:
        if count(ordered) >= 340:
            break
        if any(jaccard(extra["tokens"], s["tokens"]) > 0.5 for s in ordered):
            continue
        ordered.append(extra)
        ordered.sort(key=lambda x: x["start"])

    while count(ordered) > 500 and len(ordered) > 5:
        candidates = [
            s
            for s in ordered
            if id(s) not in pinned_ids and len(s["tokens"] & title_toks) == 0
        ] or [s for s in ordered if id(s) not in pinned_ids] or ordered
        weakest = min(candidates, key=lambda x: x["score"])
        ordered.remove(weakest)

    while count(ordered) < 300 and rest:
        nxt = rest.pop(0)
        if nxt in ordered:
            continue
        if any(jaccard(nxt["tokens"], s["tokens"]) > 0.55 for s in ordered):
            continue
        ordered.append(nxt)
        ordered.sort(key=lambda x: x["start"])
        if count(ordered) > 500:
            ordered.remove(nxt)
            break

    paras: list[list[str]] = []
    current: list[str] = []
    last_t = None
    for s in ordered:
        if last_t is not None and s["start"] - last_t > 720 and current:
            paras.append(current)
            current = []
        current.append(s["text"])
        last_t = s["start"]
    if current:
        paras.append(current)
    summary = "\n\n".join(" ".join(p) for p in paras)
    return summary, word_count_text(summary)


def build_quotes(sentences: list[dict], title_toks: set[str], k: int = 10) -> list[dict]:
    def quoteable(s: dict) -> bool:
        text = s["text"]
        n = len(s["tokens"])
        if not text.endswith((".", "!", "?")):
            return False
        if not (10 <= n <= 42):
            return False
        if is_junk(text):
            return False
        return True

    ranked = [s for s in sentences if quoteable(s) and s["score"] > 0.6]
    if len(ranked) < k:
        ranked = [s for s in sentences if quoteable(s)]
    for s in ranked:
        s["score"] = s["score"] + (0.9 if s["tokens"] & title_toks else 0)
    picked = mmr_select(sorted(ranked, key=lambda x: x["score"], reverse=True), k=k)
    picked.sort(key=lambda x: x["start"])
    quotes = []
    for s in picked[:k]:
        quotes.append(
            {
                "text": s["text"],
                "timestamp": format_ts(s["start"]),
                "seconds": int(s["start"]),
                "speaker": infer_speaker(s["text"]),
            }
        )
    return quotes


def process_episode(info: dict, cues: list[dict]) -> dict:
    sentences = sentences_from_cues(cues)
    df: Counter = Counter()
    for s in sentences:
        toks = set(tokenize(s["text"]))
        s["tokens"] = toks
        df.update(toks)
    n_docs = max(1, len(sentences))
    title_toks = title_terms(info.get("title") or "")
    for s in sentences:
        s["score"] = score_sentence(s, df, n_docs, title_toks)

    summary, word_count = build_summary(sentences, title_toks)
    quotes = build_quotes(sentences, title_toks)

    duration = info.get("durationSeconds")
    if not duration and cues:
        duration = int(cues[-1]["end"] or cues[-1]["start"])

    title = info.get("title") or ""
    video_id = info["id"]
    return {
        "id": video_id,
        "title": title,
        "episodeNumber": episode_number(title, video_id),
        "publishedAt": info.get("publishedAt") or "",
        "durationSeconds": duration,
        "durationLabel": format_ts(duration or 0) if duration else "",
        "channel": info.get("channel") or "Peter H. Diamandis",
        "thumbnail": info.get("thumbnail")
        or f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        "youtubeUrl": info.get("youtubeUrl") or f"https://www.youtube.com/watch?v={video_id}",
        "description": info.get("description") or "",
        "summary": summary,
        "summaryWordCount": word_count,
        "quotes": quotes,
        "transcriptSource": info.get("transcriptSource"),
        "transcriptCueCount": len(cues),
    }


def main() -> int:
    infos = sorted(RAW_DIR.glob("*.info.json"))
    infos = [p for p in infos if p.name != "manifest.json"]
    if not infos:
        raise SystemExit("No data/raw/*.info.json files. Run npm run scrape first.")

    # Preserve scrape/newest-first order from manifest when present.
    order: list[str] | None = None
    manifest_path = RAW_DIR / "manifest.json"
    if manifest_path.exists():
        order = json.loads(manifest_path.read_text()).get("ids")

    by_id = {}
    for path in infos:
        info = parse_info(path)
        vid = info.get("id") or path.stem.replace(".info", "")
        vtt = RAW_DIR / f"{vid}.en.vtt"
        if not vtt.exists():
            alt = next(RAW_DIR.glob(f"{vid}*.vtt"), None)
            if not alt:
                print(f"skip {vid}: no VTT")
                continue
            vtt = alt
        cues = parse_vtt(vtt)
        episode = process_episode(info, cues)
        print(
            f"{vid}  words={episode['summaryWordCount']}  "
            f"quotes={len(episode['quotes'])}  source={episode['transcriptSource']}"
        )
        if episode["summaryWordCount"] < 280 or episode["summaryWordCount"] > 560:
            print(f"  NOTE: summary word count {episode['summaryWordCount']} outside 300–500 target")
        by_id[vid] = episode

    ids = order or list(by_id)
    episodes = [by_id[i] for i in ids if i in by_id]
    payload = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Moonshots with Peter Diamandis",
        "playlist": "https://www.youtube.com/playlist?list=PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU",
        "channel": "https://www.youtube.com/@peterdiamandis",
        "note": (
            "Summaries and quotes are extractive — copied from the episode transcript. "
            "They are not model-invented paraphrases."
        ),
        "episodes": episodes,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    OUT_PATH.write_text(text, encoding="utf-8")
    PUBLIC_PATH.write_text(text, encoding="utf-8")
    print(f"\nWrote {len(episodes)} episodes → {OUT_PATH} and {PUBLIC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
