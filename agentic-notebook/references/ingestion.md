# Ingestion — building and maintaining the source index

The goal of ingestion is NotebookLM's opening move: every file becomes a
**source** with a stable ID, and every source becomes retrievable, citable
text. `scripts/build_index.py` does the mechanical part; this document covers
what it can't do alone and how to handle the awkward cases.

## What the script handles by itself

| Type | Extensions | Method (first that works) | Location labels |
|---|---|---|---|
| Plain text / code / subtitles | .txt .md .rst .tex .py .js .srt .vtt ... | direct read | `¶` (none) |
| HTML | .html .htm .xhtml | tag-stripping (stdlib) | none |
| PDF | .pdf | pymupdf → pdfplumber → pypdf → `pdftotext` CLI → OCR (with `--ocr`) | `p.N` |
| Word | .docx | python-docx → raw XML from the zip | none |
| PowerPoint | .pptx | python-pptx (incl. speaker notes) → raw XML | `slide N` |
| EPUB | .epub | zip + spine order + tag-stripping | `ch.N` |
| CSV/TSV | .csv .tsv | rows as `cell | cell | cell` lines | none |
| JSON | .json .jsonl | pretty-printed text | none |

Chunking: ~230-word passages (max ~340), aligned to paragraph boundaries,
never splitting mid-sentence, with page/slide/chapter spans recorded in each
chunk's `loc`. Chunk IDs (`S3#017`) are stable for a given file version;
re-indexing an *unchanged* file never renumbers it.

## Scanned sources: the OCR chain

The script flags sources it cannot turn into text:

- `needs_extraction` — image-only PDFs, PDFs whose text layer averages under
  ~15 words/page (a "suspected scan": bad library scans often carry a
  garbage or cover-only text layer, which the indexer discards rather than
  pretending it's the book), images, legacy formats (.doc, .xls, .ppt), and
  any parser failure. The status report shows the reason per file.
- `needs_transcription` — audio and video files.

Work down this chain:

**1. Built-in OCR (`--ocr`).** If the `tesseract` CLI exists — or you can
install it (`apt-get install tesseract-ocr`, plus language packs like
`tesseract-ocr-deu`, `tesseract-ocr-bul`, `tesseract-ocr-jpn`) — re-run:

```bash
python3 $SKILL/scripts/build_index.py <folder> --ocr --ocr-lang eng      # default
python3 $SKILL/scripts/build_index.py <folder> --ocr --ocr-lang eng+bul  # mixed-language books
```

Every flagged PDF/image is rasterized (PyMuPDF → `pdftoppm` → pypdfium2,
whichever exists), OCR'd page by page at 300 dpi (`--ocr-dpi` to change), and
indexed with real page numbers — so citations to a 400-page scan still say
`p.213`. Expect roughly 1–3 seconds per page; a full book takes minutes, so
tell the user before OCR-ing a large shelf, and mention progress is printed
as it runs.

**Engines.** Two OCR engines are supported, selectable with
`--ocr-engine auto|tesseract|easyocr` (default `auto`):

- `tesseract` — the classic CLI; fast on CPU, fine on clean book scans.
- `easyocr` — neural OCR (`pip install easyocr`), GPU-accelerated when
  PyTorch sees CUDA; noticeably better on difficult, low-quality, or
  photographed scans, slower on CPU. In `auto` mode easyocr is preferred
  whenever installed, with automatic per-page fallback to tesseract if a page
  fails.

**Constrained environments (common on Windows).** If the system Python can't
take package installs, create a virtual environment *inside the skill folder*
— `python -m venv <skill>/.venv` — and pip-install optional dependencies
(easyocr, pymupdf, ...) there: every script auto-detects `<skill>/.venv` and
re-executes inside it, so invocation stays identical. The venv is
machine-local; never ship it inside a packaged `.skill` — and note the
corollary: **reinstalling or upgrading the skill replaces the skill folder
and deletes the `.venv` inside it.** After a skill upgrade, recreate the venv
before relying on optional engines, or the scripts silently fall back to the
system Python. On Windows, tesseract
installed via scoop is picked up automatically, including its language-data
directory (`TESSDATA_PREFIX` is auto-configured when unset).

The standalone tool does one file at a time and supports page
ranges — useful to spot-check quality before committing to a whole book, or
to OCR just the chapters that matter:

```bash
python3 $SKILL/scripts/ocr_pdf.py treatise.pdf --pages 1-30 -o /tmp/treatise.txt
python3 $SKILL/scripts/build_index.py <folder> --from-text "treatise.pdf" /tmp/treatise.txt
```

**OCR quality caveats — set expectations honestly.** OCR reads clean
book prose well but degrades on: musical notation and figures (notation comes
out as noise; the surrounding prose is what gets captured), complex
multi-column layouts, marginalia, tables (rows may scramble), handwriting
(mostly hopeless), and low-resolution scans — easyocr narrows but does not close these gaps. Two consequences for grounded
work: (a) anchor quotes are quotes of the *OCR text* — the verifier checks
against the index, so citations stay internally consistent, but for
high-stakes claims spot-check the actual scan page; (b) if a user's question
hinges on figures, examples, or notation, say the OCR captured only the prose
and offer to read the specific pages with your own vision capabilities.

**2. Your own extraction.** No tesseract, or its output for a source is
garbage? Become the extractor:

- **Scanned PDFs & images** — if you can read PDFs/images natively (vision),
  read the file and transcribe its text faithfully. Preserve reading order;
  don't "clean up" wording — the text you produce will be quoted in
  citations, so it must be what the document actually says. For tables,
  linearize rows (`cell | cell`). This route often beats tesseract on messy
  layouts, notation-heavy pages, and handwriting.
- **Audio/video** — use a transcription tool if one exists in the
  environment (whisper, a cloud API the user has connected, etc.). Include
  speaker labels when discernible.
- **Legacy Office / anything else** — try `libreoffice --headless
  --convert-to` if installed; otherwise your own reading.

Write the extracted text to a temp file, marking structure with
`[[page 12]]` / `[[slide 3]]` / `[[chapter 4]]` lines wherever you know the
boundary (these become citation locations), then register it:

```bash
python3 $SKILL/scripts/build_index.py <folder> --from-text "scans/report_1987.pdf" /tmp/report_1987.txt
```

The source keeps its file path and gets a normal ID; it is now searchable and
citable like everything else. If the underlying file later changes on disk,
the hash mismatch will flag it again. `--from-text` always wins over `--ocr`:
a source you extracted by hand is never silently re-OCR'd.

**3. Report what's excluded.** If neither route works for a source, tell the
user precisely which sources are out (and therefore which topics can't be
answered), and continue with the rest.

## Re-indexing and change management

Run `build_index.py <folder>` again whenever files are added, changed, or
removed — it is incremental and cheap. Concretely:

- **New file dropped in** → gets the next free ID; existing IDs never shift.
- **File edited** → re-extracted and re-chunked; its old chunk IDs may map to
  different text, so citations you produced *before* the change may no longer
  verify — if the user edits sources mid-session, re-verify anything you
  reuse.
- **File deleted** → source removed from the registry (agent-added
  `--from-text` sources without a backing file survive).
- `--status` shows the registry at any time and re-lists what still needs
  extraction.

## Big corpora (folders of books)

A 400-page book is ~1,500 chunks; twenty books is ~30k chunks. The index and
BM25 search handle this fine — *you* are the bottleneck if you try to read
instead of retrieve. Tactics:

- Always search before reading. Multiple query phrasings beat one clever one.
- Use `--sources` scoping aggressively once you know which book is relevant.
- For per-book overviews (Notebook Guide, briefing docs), read each book's
  first ~5 and last ~5 chunks plus its table of contents if present, and probe
  3–4 searches for its central terms. That reliably yields an honest summary
  without a cover-to-cover read.
- For whole-notebook synthesis, go source-by-source (mini-summary each, with
  chunk references), then merge — never sample a few random chunks across the
  corpus and generalize.

## Judgment calls

- **Duplicates** (same book as .pdf and .epub): index both, but tell the user
  and suggest removing one; prefer citing the higher-fidelity copy.
- **Encrypted/corrupt files**: the registry records `error: ...`; report it
  and move on.
- **Non-English sources**: everything works; search is keyword-based, so query
  in the source's language too when retrieving.
- **The folder has a `.notebook/` from a previous session**: reuse it — run
  the indexer once to catch changes, skim `sources.json` and the existing
  `notebook-guide.md`, and pick up where things left off rather than
  regenerating the guide.
- **Gigantic single files** (>250 MB) are skipped with a note; split them or
  extract the relevant part with the user.
