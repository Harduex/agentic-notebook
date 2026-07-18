# agentic-notebook

![Agentic Notebook Logo](https://repository-images.githubusercontent.com/1305016617/04708d5e-9754-40a9-bc09-58cf82a24614)

Turn any folder of documents into a NotebookLM-style research notebook for your AI agent — grounded answers, verifiable citations, no invented sources.

Point your agent at a folder of PDFs, books, papers, or notes. The skill indexes everything, and from then on the agent answers questions **only from those sources**, citing the exact file, page, and quote behind every claim — and can turn the sources into study guides, briefing docs, FAQs, timelines, mind maps, flashcards, quizzes, data tables, and podcast or video scripts.

## Install

```bash
npx skills add Harduex/agentic-notebook
```

Works with Claude Code, Gemini CLI, Cursor, Codex, Copilot, OpenCode, and any other agent supported by the [skills CLI](https://github.com/vercel-labs/skills). Claude Code users can alternatively install it as a plugin:

```
/plugin marketplace add Harduex/agentic-notebook
/plugin install agentic-notebook@harduex
```

## Use

Ask your agent something like:

> Act as a notebook over ./my-books — what do these authors disagree about on mastering loudness?

The first run indexes the folder into a local `.notebook/` workspace inside it. After that: grounded Q&A with citations you can check (`[1] book.pdf · p.41 · "exact quote from the page"`), honest "the sources don't cover this" answers when they don't, and one-request artifacts — "make me a study guide from these", "give me a two-host podcast script", "build a comparison table across the papers".

## What it handles

- PDF (including scanned books, via built-in OCR), EPUB, DOCX, PPTX, Markdown, HTML, CSV, plain text, code, subtitles
- Audio, video, and image sources when your agent can transcribe or read them
- Everything stays local — sources are read in place, and all outputs live in the folder's `.notebook/` directory

## Requirements

- Python 3.9+ — the bundled scripts are standard-library first; PDF libraries are auto-detected when present
- Optional, for scanned books: `tesseract` (or `easyocr`)

The scripts are plain, readable Python and only ever write inside the target folder's `.notebook/`. Read them before installing — as you should with any skill that ships scripts.

## License

[MIT](LICENSE)
