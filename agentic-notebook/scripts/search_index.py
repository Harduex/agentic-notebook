#!/usr/bin/env python3
"""
search_index.py — Retrieve passages from a .notebook/ index. Pure stdlib.

Usage:
  python search_index.py <folder> "query terms"            BM25 search (top 8)
  python search_index.py <folder> "q1" "q2" "q3"           synonym sweep: each query runs separately
  python search_index.py <folder> "query" --k 12           more results
  python search_index.py <folder> "query" --sources S1,S3  restrict to sources
  python search_index.py <folder> --grep "exact phrase"    substring/regex scan
  python search_index.py <folder> --get S2#014             print a full chunk
  python search_index.py <folder> --get S2#014 --context 1 ...with neighbors
  python search_index.py <folder> --full                   print full text with --get SOURCE_ID (e.g. --get S2 --full)

Search output lines look like:
  1. S2#014 · Deep Work · p.41-p.42 · score 12.3
     ...snippet around the best-matching passage...

Retrieval tips for agents: run 2-4 differently-worded queries per question
(synonyms, entity names, the user's exact phrasing) — pass them in one call
as multiple positional arguments — then --get the most promising chunks to
read them in full before answering. A concept often lives under a different
name per source ("loudness war" vs "volume war"): sweep the synonyms before
concluding a source is silent.

Search is multilingual: any script works (Cyrillic, Greek, Arabic, Hebrew,
Devanagari, ...; Chinese/Japanese/Korean match via character bigrams), e.g.
  python search_index.py <folder> "войната за сила на звука"
Query in the sources' language; only light English stemming is applied, so
for inflected languages sweep morphological variants ("война" / "войната").
"""

import os
import sys
from pathlib import Path

# --- Environment bootstrap: re-exec inside <skill>/.venv if present --------
# A user/agent may create a virtual environment at <skill>/.venv to hold
# optional dependencies (pymupdf, easyocr, ...) on machines where the system
# Python can't install packages. Detect it and hand execution over.
_venv = Path(__file__).resolve().parent.parent / ".venv"
_venv_py = _venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
try:
    # sys.prefix equals the venv dir when running inside it — comparing
    # executables fails on Linux, where venv pythons are symlinks.
    _needs_venv = (_venv_py.exists()
                   and Path(sys.prefix).resolve() != _venv.resolve())
except OSError:
    _needs_venv = False
if _needs_venv:
    import subprocess as _sp
    raise SystemExit(_sp.call([str(_venv_py)] + sys.argv))
# ---------------------------------------------------------------------------
import argparse
import json
import math
import pickle
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

NOTEBOOK_DIR = ".notebook"

_TOKEN = re.compile(r"[^\W_]+")  # letters/digits in any script (re is Unicode)
TOKENIZER_VERSION = 3  # bump when tokenize()/stemming changes, to refresh caches

# Scripts written without spaces between words: whole-run tokens are useless,
# so these are indexed as overlapping character bigrams (Lucene CJKAnalyzer
# approach). Ranges are inclusive codepoints.
_CJK_RANGES = (
    (0x0E00, 0x0E7F),    # Thai
    (0x0E80, 0x0EFF),    # Lao
    (0x1000, 0x109F),    # Myanmar
    (0x1780, 0x17FF),    # Khmer
    (0x2E80, 0x2FDF),    # CJK Radicals Supplement + Kangxi Radicals
    (0x3040, 0x309F),    # Hiragana
    (0x30A0, 0x30FF),    # Katakana
    (0x3400, 0x4DBF),    # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0xAC00, 0xD7AF),    # Hangul Syllables
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0x20000, 0x2FA1F),  # CJK Unified Ideographs Extensions B-F
)


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).lower()
    # Fold diacritics only when the base character is Latin/Greek/Cyrillic
    # (codepoints below U+0530, a pragmatic cutoff). Elsewhere combining
    # marks are meaning-bearing — Indic vowel signs, Arabic/Hebrew points —
    # and stripping them collapses distinct words.
    out, base = [], ""
    for c in text:
        if unicodedata.combining(c):
            if base and ord(base) < 0x0530:
                continue
        else:
            base = c
        out.append(c)
    return "".join(out)


def _stem(t: str) -> str:
    """Very light English-only suffix folding so 'wars' matches 'war',
    'mixing' matches 'mix'. Applied only to ASCII tokens — other languages
    get recall via query-side morphological variants instead."""
    if not t.isascii():
        return t
    for suf in ("ing", "ed", "es"):
        if t.endswith(suf) and len(t) > len(suf) + 2:
            t = t[: -len(suf)]
            break
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        t = t[:-1]
    return t


def tokenize(text: str):
    # No stopword list: BM25's IDF already drives ubiquitous terms to ~0 in
    # any language, and a uniform rule beats an English-only special case.
    out = []
    for raw in _TOKEN.findall(normalize(text)):
        i = 0
        while i < len(raw):  # split each match into CJK / non-CJK segments
            cjk = _is_cjk(raw[i])
            j = i + 1
            while j < len(raw) and _is_cjk(raw[j]) == cjk:
                j += 1
            seg = raw[i:j]
            i = j
            if cjk:
                # character bigrams; a lone character stays a unigram
                if len(seg) == 1:
                    out.append(seg)
                else:
                    out.extend(seg[k:k + 2] for k in range(len(seg) - 1))
            elif len(seg) > 1:
                out.append(_stem(seg))
    return out


def load_chunks(folder: Path):
    cj = folder / NOTEBOOK_DIR / "chunks.jsonl"
    if not cj.exists():
        sys.exit(f"No index at {cj}. Run build_index.py first.")
    chunks = []
    with open(cj, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks, cj


def load_or_build_cache(folder: Path, chunks, cj: Path):
    cache_dir = folder / NOTEBOOK_DIR / "cache"
    cache_dir.mkdir(exist_ok=True)
    key = f"t{TOKENIZER_VERSION}_{cj.stat().st_mtime_ns}_{cj.stat().st_size}"
    pkl = cache_dir / "bm25.pkl"
    if pkl.exists():
        try:
            with open(pkl, "rb") as f:
                data = pickle.load(f)
            if data.get("key") == key:
                return data
        except Exception:
            pass
    toks = [tokenize(c["text"]) for c in chunks]
    df = Counter()
    for t in toks:
        df.update(set(t))
    data = {"key": key, "tokens": toks, "df": dict(df),
            "avgdl": (sum(len(t) for t in toks) / max(1, len(toks)))}
    try:
        with open(pkl, "wb") as f:
            pickle.dump(data, f)
    except Exception:
        pass
    return data


def bm25_search(query, chunks, cache, k=8, sources=None, k1=1.5, b=0.75):
    qtoks = tokenize(query)
    if not qtoks:
        return []
    N = len(chunks)
    df, toks, avgdl = cache["df"], cache["tokens"], cache["avgdl"]
    # Language-agnostic stopword effect: drop query terms present in more
    # than half the corpus (near-zero IDF anyway) — unless that would drop
    # every term. Applied here, not in tokenize(), so the cache stays raw.
    rare = [t for t in qtoks if df.get(t, 0) <= 0.5 * N]
    if rare:
        qtoks = rare
    idf = {t: math.log(1 + (N - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5)) for t in set(qtoks)}
    qphrase = normalize(query)
    scored = []
    for i, c in enumerate(chunks):
        if sources and c["source_id"] not in sources:
            continue
        tf = Counter(toks[i])
        dl = len(toks[i]) or 1
        score = 0.0
        for t in qtoks:
            f = tf.get(t, 0)
            if f:
                score += idf[t] * (f * (k1 + 1)) / (f + k1 * (1 - b + b * dl / avgdl))
        if score and len(qphrase) > 6 and qphrase in normalize(c["text"]):
            score *= 1.6  # exact-phrase bonus
        if score:
            scored.append((score, i))
    scored.sort(key=lambda x: -x[0])
    return [(s, chunks[i]) for s, i in scored[:k]]


def snippet(text, query, width=380):
    qtoks = tokenize(query)
    low = normalize(text)
    pos = min((low.find(t) for t in qtoks if low.find(t) >= 0), default=0)
    start = max(0, pos - width // 3)
    out = text[start:start + width].replace("\n", " ")
    prefix = "..." if start > 0 else ""
    suffix = "..." if start + width < len(text) else ""
    return f"{prefix}{out}{suffix}"


def cmd_search(folder, query, k, sources):
    chunks, cj = load_chunks(folder)
    cache = load_or_build_cache(folder, chunks, cj)
    results = bm25_search(query, chunks, cache, k=k, sources=sources)
    if not results:
        print("NO_RESULTS -- try different wording, fewer/other keywords, or --grep "
              "for exact strings. If still nothing, the answer may not be in the sources.")
        return
    for rank, (score, c) in enumerate(results, 1):
        loc = c.get("loc") or "-"
        print(f"{rank}. {c['id']} · {c['source']} · {loc} · score {score:.1f}")
        print(f"   {snippet(c['text'], query)}\n")


def cmd_grep(folder, pattern, sources, limit=25):
    chunks, _ = load_chunks(folder)
    # Plain phrases (no regex metacharacters) match across line breaks and
    # variable spacing — essential for PDF/OCR text where any phrase may be
    # wrapped mid-line. Real regexes are used verbatim.
    is_plain = not re.search(r"[\\^$.|?*+()\[\]{}]", pattern)
    try:
        rx = re.compile(re.escape(pattern).replace(r"\ ", r"\s+") if is_plain
                        else pattern, re.IGNORECASE)
        matcher = lambda t: rx.search(t)
    except re.error:
        pat = pattern.lower()
        matcher = lambda t: (t.lower().find(pat) >= 0) or None
    hits = 0
    for c in chunks:
        if sources and c["source_id"] not in sources:
            continue
        m = matcher(c["text"])
        if m:
            hits += 1
            if hasattr(m, "start"):
                s = max(0, m.start() - 90)
                frag = c["text"][s:m.end() + 200].replace("\n", " ")
            else:
                idx = c["text"].lower().find(pattern.lower())
                frag = c["text"][max(0, idx - 90):idx + 200].replace("\n", " ")
            print(f"{c['id']} · {c['source']} · {c.get('loc') or '-'}")
            print(f"   ...{frag}...\n")
            if hits >= limit:
                print(f"(stopped at {limit} matches)")
                break
    if not hits:
        print("NO_MATCHES")


def cmd_get(folder, cid, context, full):
    chunks, _ = load_chunks(folder)
    if full:  # dump a whole source
        sel = [c for c in chunks if c["source_id"] == cid or c["id"] == cid]
        if not sel:
            sys.exit(f"Unknown source {cid}")
        sid = sel[0]["source_id"]
        for c in chunks:
            if c["source_id"] == sid:
                print(f"\n===== {c['id']} · {c.get('loc') or '-'} =====")
                print(c["text"])
        return
    idx = next((i for i, c in enumerate(chunks) if c["id"] == cid), None)
    if idx is None:
        sys.exit(f"Unknown chunk id {cid}")
    lo, hi = max(0, idx - context), min(len(chunks) - 1, idx + context)
    for i in range(lo, hi + 1):
        c = chunks[i]
        if c["source_id"] != chunks[idx]["source_id"]:
            continue
        marker = ">>>" if i == idx else "   "
        print(f"\n{marker} ===== {c['id']} · {c['source']} · {c.get('loc') or '-'} =====")
        print(c["text"])


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("query", nargs="*", default=[],
                    help="One or more queries; each runs as its own search")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--sources", help="Comma-separated source IDs, e.g. S1,S3")
    ap.add_argument("--grep", help="Exact substring or regex scan")
    ap.add_argument("--get", help="Chunk ID (S2#014) or, with --full, a source ID (S2)")
    ap.add_argument("--context", type=int, default=0, help="Neighbor chunks around --get")
    ap.add_argument("--full", action="store_true", help="With --get: dump whole source")
    args = ap.parse_args()
    folder = Path(args.folder).resolve()
    if not folder.is_dir():
        sys.exit(f"Folder not found: {folder}\n"
                 "If the path contains spaces, wrap it in quotes, e.g.\n"
                 f'  python {Path(__file__).name} "C:\\path with spaces\\books" ...')
    sources = set(args.sources.split(",")) if args.sources else None

    if args.get:
        cmd_get(folder, args.get, args.context, args.full)
    elif args.grep:
        cmd_grep(folder, args.grep, sources)
    elif args.query:
        for i, q in enumerate(args.query):
            if len(args.query) > 1:
                print(f"{'' if i == 0 else chr(10)}--- query: {q} ---")
            cmd_search(folder, q, args.k, sources)
    else:
        ap.print_help()


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
