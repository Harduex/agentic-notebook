#!/usr/bin/env python3
"""
verify_citations.py — Audit the Sources footer of a grounded answer or artifact.

Checks that every anchor quote genuinely appears in the source it cites.
This is the automated "click the citation" step: a citation that fails here
would break a reader's trust, so fix or remove it before delivering.

Expected footer line format (one per citation):
  [1] S2 · deep-work.pdf · p.41 · "the ability to focus without distraction"
  [2] S1 · atomic-habits.epub · ch.3 · "habits are the compound interest of self-improvement"

Usage:
  python verify_citations.py <folder> <answer.md>
  cat answer.md | python verify_citations.py <folder> -

Exit code 0 = all citations verified; 1 = at least one problem.
Matching is forgiving: case, whitespace, curly quotes/dashes, hyphenation and
"..." ellipses inside the quote are normalized before comparison.
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
import json
import re
import sys
import unicodedata
from pathlib import Path

NOTEBOOK_DIR = ".notebook"

CITE_LINE = re.compile(
    r"""^\s*\[(\d+)\]\s+          # [1]
        (S\d+)\s*[·|]\s*          # S2 ·
        ([^·|]+?)\s*[·|]\s*       # title/filename ·
        ([^·|]*?)\s*[·|]\s*       # location ·
        [\"\u201c](.+?)[\"\u201d]\s*$   # "anchor quote"
    """, re.VERBOSE)


def canon(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = (text.replace("\u2019", "'").replace("\u2018", "'")
                .replace("\u201c", '"').replace("\u201d", '"')
                .replace("\u2014", "-").replace("\u2013", "-")
                .replace("\u00ad", ""))
    text = re.sub(r"-\s+", "", text)      # de-hyphenate line breaks
    text = re.sub(r"[^a-z0-9' ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def load_source_texts(folder: Path):
    cj = folder / NOTEBOOK_DIR / "chunks.jsonl"
    if not cj.exists():
        sys.exit(f"No index at {cj}. Run build_index.py first.")
    texts = {}
    with open(cj, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            texts.setdefault(c["source_id"], []).append(c["text"])
    return {sid: canon(" ".join(parts)) for sid, parts in texts.items()}


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    folder = Path(sys.argv[1]).resolve()
    if not folder.is_dir():
        sys.exit(f"Folder not found: {folder}\n"
                 "If the path contains spaces, wrap it in quotes, e.g.\n"
                 f'  python {Path(__file__).name} "C:\\path with spaces\\books" ...')
    raw = (sys.stdin.read() if sys.argv[2] == "-"
           else Path(sys.argv[2]).read_text(encoding="utf-8", errors="replace"))
    corpus = load_source_texts(folder)

    citations = []
    for line in raw.splitlines():
        m = CITE_LINE.match(line)
        if m:
            citations.append(m.groups())

    if not citations:
        print("NO_CITATIONS_FOUND -- footer lines must look like:\n"
              '  [1] S2 · title · p.41 · "anchor quote"')
        sys.exit(1)

    # which inline markers are used in the body?
    body = raw.split("Sources", 1)[0]
    used_nums = set(re.findall(r"\[(\d+)\]", body))

    failures = 0
    for num, sid, title, loc, quote in citations:
        if sid not in corpus:
            print(f"FAIL [{num}] unknown source id {sid}")
            failures += 1
            continue
        pieces = [canon(p) for p in re.split(r"\s*(?:\.\.\.|\u2026)\s*", quote) if p.strip()]
        ok = all(len(p) >= 3 and p in corpus[sid] for p in pieces)
        if ok:
            extra = "" if num in used_nums or not used_nums else "  (note: [%s] never cited in body)" % num
            print(f"PASS [{num}] {sid} · {loc or '-'} · \"{quote[:70]}\"{extra}")
        else:
            print(f"FAIL [{num}] {sid} -- quote not found in that source: \"{quote[:80]}\"")
            print("      Fix: --grep a distinctive fragment to find the real passage, "
                  "correct the quote/source, or delete the claim.")
            failures += 1

    dangling = used_nums - {n for n, *_ in citations}
    for n in sorted(dangling, key=int):
        print(f"FAIL [{n}] cited inline but missing from the Sources footer")
        failures += 1

    # Uncited-section scan: a whole section asserting content with zero
    # citation markers is the slip the quote-check above cannot see.
    # Warnings only — intros/conclusions may legitimately have none.
    section, buf = "(preamble)", []
    sections = []
    for line in body.splitlines():
        h = re.match(r"^#{1,4}\s+(.*)", line)
        if h:
            sections.append((section, " ".join(buf)))
            section, buf = h.group(1).strip(), []
        else:
            buf.append(line)
    sections.append((section, " ".join(buf)))
    first_text_idx = next((i for i, (_, t) in enumerate(sections) if t.strip()), 0)
    for i, (name, text) in enumerate(sections):
        if i <= first_text_idx:
            continue  # the opening/framing section legitimately has no citations
        if len(text.split()) > 40 and not re.search(r"\[\d+\]", text):
            print(f'WARN section "{name}" ({len(text.split())} words) has no '
                  f"citations -- cite it, fence it as inference, or cut it")

    print(f"\n{len(citations)} citations checked · {failures} problem(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
