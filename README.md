# agentic-notebook

![Agentic Notebook Logo](https://repository-images.githubusercontent.com/1305016617/04708d5e-9754-40a9-bc09-58cf82a24614)

Turn any folder of documents into a NotebookLM-style research notebook for your AI agent — grounded answers, verifiable citations, no invented sources.

Point your agent at a folder of PDFs, books, papers, or notes. The skill indexes everything, and from then on the agent answers questions **only from those sources**, citing the exact file, page, and quote behind every claim — and can turn the sources into study guides, briefing docs, FAQs, timelines, mind maps, flashcards, quizzes, data tables, and podcast or video scripts.

## Available Skills

This repository includes two skill variants:

| Skill | Optimized For | Key Features |
|---|---|---|
| **`agentic-notebook`** | Frontier & large models (Claude 3.5/3.7, Gemini, GPT-4o) | High-context research, rich studio artifacts, full interactive Q&A and analysis |
| **`agentic-notebook-mini`** | Small local models (7–14B: Ollama, llama.cpp, LM Studio, vLLM) | Context-frugal multi-query + grep search, disk task ledger (`checkpoint.py`), `--toc` skimming, `--list`, size limits, strict command quotas |

Both skills share the exact same `.notebook/` index format — you can build an index with one and query it with the other interchangeably.

## Install

**Which variant?** Use **`agentic-notebook`** for frontier / large models (Claude, Gemini, GPT). Use **`agentic-notebook-mini`** if you run a small local model (7–14B via Ollama, llama.cpp, LM Studio, vLLM) or otherwise work in a tight context budget. Both share the same index format, so you can switch later.

### skills CLI

Works with Claude Code, Gemini CLI, Cursor, Codex, Copilot, OpenCode, and any other agent supported by the [skills CLI](https://github.com/vercel-labs/skills).

```bash
npx skills add Harduex/agentic-notebook   # pick the variant when prompted
```

### Claude Code plugin

```
/plugin marketplace add Harduex/agentic-notebook

/plugin install agentic-notebook@harduex        # frontier / large models
/plugin install agentic-notebook-mini@harduex   # small local models (7–14B)
```

## Use

Ask your agent something like:

> Act as a notebook over ./my-books — what do these authors disagree about on mastering loudness?

Or for local/small model setups:

> Use notebook mini over ./my-notes — find all recipes and save them to a study guide.

The first run indexes the folder into a local `.notebook/` workspace inside it. After that: grounded Q&A with citations you can check (`[1] book.pdf · p.41 · "exact quote from the page"`), honest "the sources don't cover this" answers when they don't, and one-request artifacts — "make me a study guide from these", "give me a two-host podcast script", "build a comparison table across the papers".

## Mini Variant (`agentic-notebook-mini`) Highlights

For 7B–14B models (e.g. Ornith, Qwen, Gemma, Llama), context budget is precious. `agentic-notebook-mini` fixes common small-model failure modes:

- **Disk Task Ledger (`checkpoint.py`)**: For exhaustive extraction tasks ("find all X"), task state lives on disk. Candidates, per-source sweep status, and labels are stored in `.notebook/tasks/<slug>.json`. Work can be interrupted and resumed at any point with one command.
- **Fused Compact Search**: Combines multiple semantic queries and exact string greps into a single deduplicated CLI call with reciprocal-rank fusion and per-source coverage indicators.
- **Source Skimming (`--toc`)**: View line-by-line outlines of whole sources in cheap, paginated batches instead of loading full text into context.
- **Safety Guards**: Refuses full-source text dumps on large files (>2,500 words) and enforces verbatim citation checks with `verify_citations.py`.

## What it handles

- PDF (including scanned books, via built-in OCR), EPUB, DOCX, PPTX, Markdown, HTML, CSV, plain text, code, subtitles
- Audio, video, and image sources when your agent can transcribe or read them
- Everything stays local — sources are read in place, and all outputs live in the folder's `.notebook/` directory
- A `.noteignore` file at the folder root excludes files from indexing (simple gitignore-style globs: `drafts/`, `*.log`); adding a pattern later prunes the already-indexed matches on the next run

## Repository Structure

```
agentic-notebook/
├── skills/
│   ├── agentic-notebook/        # Original skill for frontier / large models
│   │   ├── SKILL.md
│   │   └── scripts/
│   └── agentic-notebook-mini/   # Mini variant for small local 7-14B models
│       ├── SKILL.md
│       ├── README.md
│       └── scripts/             # Includes checkpoint.py disk task ledger
└── .claude-plugin/              # Claude Code marketplace manifests
```

## Multilingual

Search and indexing work across scripts and languages — Cyrillic, Greek, accented Latin (accent-insensitive both ways), RTL scripts like Arabic and Hebrew, Indic scripts, and Chinese/Japanese/Korean (matched via character bigrams, chunked by character count). Non-English scanned books OCR with `--ocr-lang`, e.g. `--ocr-lang deu+eng`.

## Requirements

- Python 3.9+ — the bundled scripts are standard-library first; PDF libraries are auto-detected when present
- Optional, for scanned books: `tesseract` (or `easyocr`)

The scripts are plain, readable Python and only ever write inside the target folder's `.notebook/`. Read them before installing — as you should with any skill that ships scripts.

## License

[MIT](LICENSE)

