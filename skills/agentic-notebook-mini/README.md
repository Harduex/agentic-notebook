# agentic-notebook-mini

A variant of [agentic-notebook](https://github.com/Harduex/agentic-notebook)
built for **small local models (7-14B) with limited context (32k-130k)** —
e.g. Ornith-1.0-9B, Qwen, Gemma or Llama class models running on a single
consumer GPU via llama.cpp / Ollama / LM Studio / vLLM, driven by OpenCode,
Claude Code, or any skills-capable agent.

Same promise as the original — grounded answers from your documents, with
citations you can verify — but every part of the workflow is redesigned
around one constraint: **the model cannot afford to hold much in context, and
cannot be trusted to self-regulate how much it reads.**

## What's different

| | agentic-notebook | agentic-notebook-mini |
|---|---|---|
| Search output | verbose, per query, ~380-char snippets | **compact by default**: queries AND greps fused in one call (reciprocal-rank fusion, grep hits boosted), deduped, one line per chunk, with per-source COVERAGE and new-vs-seen SATURATION footers (`--long` restores verbose) |
| Default k | 8 per query | fused top 10 across all probes |
| Source skimming | read chunks / `--full` | **`--toc S2`** — one line per chunk, paginated; the cheap way to sweep a whole source |
| Source overview | read the registry | **`--list`** — one-line table of all sources |
| Full-source dumps | allowed | **refused over ~2,500 words** (guard rail; `--force` to override) |
| Task state | in the model's context | **`checkpoint.py` ledger on disk** — candidates, per-source sweep state, labels; any session resumes with one command; search feeds it directly via `--add-to` (no retyping chunk IDs) |
| Instructions | judgment-based ("2-4 searches", "promising chunks") | **hard quotas + copy-paste commands** ("ONE batched search of 3-5 queries", "read 2-4 hits, max") |
| Exhaustive "find all X" tasks | ad hoc | **first-class Mode B**: grep triage → semantic pass → extract-and-forget loop → per-source TOC sweep → COMPLETE gate |
| Context overflow | model degrades mid-task | **context guard**: stop cleanly at ~25 tool calls, checkpoint, "say *continue TASK* in a fresh chat" |

The `.notebook/` index format is **identical** — both skills can work on the
same folder interchangeably, and `build_index.py`, `verify_citations.py`,
`ocr_pdf.py` are the original scripts unchanged.

## Install

Same repo layout as the original, so the skills CLI picks it up:

```
npx skills add Harduex/agentic-notebook   # choose agentic-notebook-mini
```

Or copy the `agentic-notebook-mini/` folder next to wherever your original
skill lives (e.g. `.opencode/skills/` for a project, or your agent's global
skills directory). Both skills can be installed side by side; ask the agent
for "notebook mini" explicitly when you want this one.

## Why small models fail at the original workflow (and what this fixes)

1. **They answer from snippets.** Verbose search output looks like enough
   evidence. → Compact output carries too little text to fake an answer
   from; the tool itself says "read before citing: --get".
2. **They can't judge "enough searching".** They stop after one query or
   never stop. → Fixed quotas: one batched call of 3-5 queries, read 2-4
   chunks, one refinement round, done.
3. **They forget mid-task.** Long extractions overflow context and the model
   silently drops items. → The ledger owns the state; the model processes 5
   candidates at a time and can be killed and resumed at any point with zero
   loss.
4. **They hallucinate chunk IDs and quotes.** → `checkpoint.py add` rejects
   IDs that don't exist in the index; `verify_citations.py` greps every
   anchor quote and fails the answer if one doesn't match.
5. **They re-read to reassure themselves,** burning context. → Explicit
   bans + `notes` command that replays extraction labels without reopening
   anything.

## Running on a 12 GB GPU (e.g. Ornith-1.0-9B)

Model-agnostic notes; check your model's card for specifics:

- A 9B at **Q4_K_M** is ~5.5-6 GB of weights, which leaves roughly 5-6 GB
  for KV cache on a 12 GB card. At 130k context that usually requires
  **quantized KV cache** (llama.cpp: `--cache-type-k q8_0 --cache-type-v
  q8_0`; Ollama: `OLLAMA_KV_CACHE_TYPE=q8_0`) and **flash attention** on.
- If it still doesn't fit, prefer **64k context + this skill's checkpointing**
  over a bigger window: the workflow is built to not need a huge context.
- Sampling: follow the model card (Ornith-1.0 official: temperature 0.6,
  top_p 0.95, top_k 20; temp 1.0 reproduces its benchmark setup). Avoid very
  low temperatures — community GGUF repacks report repetition loops on this
  model around temp 0.1 — and avoid high repetition penalties: both corrupt
  the repeated command strings and tool-call JSON this workflow lives on.
- Reasoning models that emit `<think>` blocks: make sure your server's
  reasoning parser is enabled (e.g. vLLM `--reasoning-parser qwen3`) so
  thinking doesn't leak into answers; consider limiting think length if your
  runtime supports it — TOC sweeps don't need deep thought.
- OpenCode: point it at your local OpenAI-compatible endpoint and keep the
  tool set lean; every registered tool's schema costs context on every turn.

## Files

```
agentic-notebook-mini/
├── SKILL.md                     the workflow (small-model optimized)
├── references/studio.md         slim artifact templates
└── scripts/
    ├── build_index.py           unchanged from agentic-notebook
    ├── search_index.py          fused compact search (+--add-to), --toc, --list, size guard
    ├── checkpoint.py            NEW: disk task ledger for find-all tasks
    ├── verify_citations.py      unchanged
    └── ocr_pdf.py               unchanged
```

MIT, same as the original.
