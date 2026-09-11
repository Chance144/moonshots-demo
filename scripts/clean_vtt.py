#!/usr/bin/env python3
"""Convert YouTube auto-caption VTT files to cleaned plain text."""
import re, html, argparse
from pathlib import Path

TAG_RE = re.compile(r"<[^>]+>")
TS_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})"
)


def parse_vtt(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace").replace("\ufeff", "")
    cues = []
    for block in re.split(r"\n\n+", text):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ts_idx is None:
            continue
        m = TS_RE.match(lines[ts_idx].strip())
        if not m:
            continue
        start = (
            int(m.group(1)) * 3600
            + int(m.group(2)) * 60
            + int(m.group(3))
            + int(m.group(4)) / 1000
        )
        body = html.unescape("\n".join(lines[ts_idx + 1 :]))
        body = TAG_RE.sub("", body).replace(">>", " ")
        body = re.sub(r"\s+", " ", body).strip()
        if body:
            cues.append((start, body))
    return cues


def dedupe_cues(cues):
    cleaned, last = [], ""
    for start, body in cues:
        if body == last:
            continue
        if last.startswith(body) and len(body) < len(last):
            continue
        if body.startswith(last) and last:
            cleaned[-1] = (cleaned[-1][0], body)
            last = body
            continue
        cleaned.append((start, body))
        last = body
    return cleaned


def cues_to_plain(cues):
    parts, prev = [], ""
    for _, body in cues:
        if not prev:
            parts.append(body)
            prev = body
            continue
        if body.startswith(prev):
            addition = body[len(prev) :].strip()
            if addition:
                parts.append(addition)
            prev = body
        elif body in prev:
            continue
        else:
            max_ol = min(len(prev), len(body))
            ol = 0
            for n in range(max_ol, 0, -1):
                if prev[-n:] == body[:n]:
                    ol = n
                    break
            addition = body[ol:].strip()
            if addition:
                parts.append(addition)
            prev = body
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vtt", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    plain = cues_to_plain(dedupe_cues(parse_vtt(args.vtt)))
    out = args.output or args.vtt.with_suffix(".txt")
    out.write_text(plain + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(plain.split())} words)")


if __name__ == "__main__":
    main()
