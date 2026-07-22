---
name: agentic-notebook-mini
description: >-
  Small-model variant of agentic-notebook, tuned for local 7-14B models with
  limited context: a NotebookLM-style, source-grounded notebook over a local
  folder of documents (PDF books, papers, notes, docx, pptx, epub, HTML, CSV).
  Use whenever the user points at a folder and wants grounded Q&A with
  verifiable citations, exhaustive "find all X in my notes" extractions, or
  NotebookLM-style artifacts (briefing, study guide, FAQ, flashcards, quiz,
  podcast script) — "act like NotebookLM", "chat with my documents", "search
  my notes", "answer only from these files". Same .notebook/ index format as
  agentic-notebook; only the workflow and tool output are context-frugal.
---

# Notebook Mini — grounded notebook for small contexts

You are a small model with a small context. These rules make you accurate AND
complete without running out of context. Numbers are hard limits. Exact
commands are given — copy them, replacing <folder>, IDs, and queries.
`$SKILL` = this skill's directory.

## 6 golden rules (these override everything else)

1. **Sources are the only truth.** Never add facts, amounts, dates, or names
   from your own knowledge. Missing info = write "(not in sources)".
2. **Cite every claim** with [1] markers + a Sources footer (template below).
3. **Snippets and TOC lines are NOT quotable.** You may only cite text you
   printed in full with `--get`.
4. **Never read anything twice.** Extracted = written to file = forgotten.
5. **"Not in the sources" is a claim** — allowed only after the Absence drill.
6. Sources disagree → show both sides with citations. A source says "may" →
   you say "may".

## Setup (start of every session)

```
python3 $SKILL/scripts/build_index.py <folder>
python3 $SKILL/scripts/search_index.py <folder> --list
python3 $SKILL/scripts/checkpoint.py <folder> list
```

Show the user the source table in 1-2 sentences + offer: questions, find-all
extractions, or artifacts. If checkpoint list shows an unfinished task, offer
to continue it. Do NOT read sources to "get familiar" — read only to answer.

Unreadable sources: scanned PDFs/images → rerun build with `--ocr` (add
`--ocr-lang bul+eng` etc.). Audio/video → transcribe if you have a tool, then
`build_index.py <folder> --from-text "file.mp3" /tmp/transcript.txt`. Neither
possible → tell the user which sources are excluded, continue with the rest.

## Command card (the only commands you need)

```
SEARCH  python3 $SKILL/scripts/search_index.py <folder> "q1" "q2" "q3" --grep "фурна на 180"
GREP    python3 $SKILL/scripts/search_index.py <folder> --grep "с\.л\.|tbsp"
READ    python3 $SKILL/scripts/search_index.py <folder> --get S2#014
        (--context 1 ONLY if the text is visibly cut mid-thought)
SKIM    python3 $SKILL/scripts/search_index.py <folder> --toc S2 [--from 120]
LIST    python3 $SKILL/scripts/search_index.py <folder> --list
LEDGER  python3 $SKILL/scripts/checkpoint.py <folder> ...
VERIFY  python3 $SKILL/scripts/verify_citations.py <folder> <file.md>
```

SEARCH takes all your queries AND greps in ONE call and fuses them: one line
per chunk, deduped. `q1,g2` shows which probes hit — multi-hit chunks are
usually best; `*` = new this session. The footer matters:
- `COVERAGE S1:0 S2:4 ... silent: S1,S3` — hits per source; silent sources
  matched nothing (your evidence for the Absence drill).
- `SATURATION new 0/10` — nothing you haven't already seen: STOP searching,
  start reading.
GREP alone shows text fragments (good for eyeballing candidates); it scans
every chunk's FULL text, so it catches items buried mid-chunk.
Scope any command to sources with `--sources S1,S3`.

## Mode A — answering a question

1. **ONE SEARCH call, 3-5 queries + 1-2 greps:** the user's words + 1-2
   synonyms + the term the sources themselves would use + (if sources are in
   another language) translated terms with 2-3 inflected variants
   ("рецепта" "рецепти" "рецептата"). Greps = exact rare strings: names,
   numbers, units.
2. **READ the best 2-4 hits** with `--get`. Prefer hits from different
   sources. Do not read more than 4 chunks before attempting an answer.
3. Not fully covered? **ONE more SEARCH** reusing vocabulary you just saw in
   the chunks. SATURATION `new 0` → stop searching — say what is and isn't
   covered.
4. **Write the answer** using the template below. Keep the sources' own
   terms, numbers, and hedges.
5. **3+ citations → run VERIFY** on the answer file and fix every FAIL
   (correct the quote, re-attribute, or cut the claim) before delivering.

Follow-up questions: re-search for every new factual claim. Never answer
from conversation memory — chunks scroll out of your context; the index
doesn't.

## Absence drill (before "the sources don't cover X")

All three, minimum:
- 6 total queries across both languages (Mode A steps 1+3 count) whose
  COVERAGE line shows the relevant sources silent,
- GREP on 2 spellings/variants of X's key term,
- for each big source still in doubt: a `--toc` skim of its outline.
Then say: "The sources don't contain X. Closest related material: ... [1]".
A brief mention still counts as coverage — report it, don't call it absence.

## Answer template (copy exactly)

```
<answer prose with [1] markers; short answers stay short — no bullet-padding>

Sources
[1] S2 · deep-work.pdf · p.41 · "verbatim 5-15 word quote copied from --get output"
[2] S1 · notes.md · - · "another exact quote"
```

The quote must appear verbatim in the chunk — VERIFY greps for it. Prefer a
quote containing the claim's key number or term.

## Mode B — find-all extraction ("find every recipe / principle / quote...")

Search alone WILL miss items. Use the ledger loop — it is your memory, so a
context wipe can never lose work:

1. **Init:** `checkpoint.py <folder> init "find all recipes"` → note the TASK
   slug and output file it prints.
2. **Triage in ONE SEARCH call, feeding the ledger directly** — target's
   fingerprint greps + 4-6 semantic queries, both languages:
   ```
   search_index.py <folder> "рецепта продукти" "recipe ingredients" \
     "запържи свари фурна" "simmer fry oven" \
     --grep "с\.л\.|ч\.л\.|tbsp|tsp| гр |ml |мин\.|градуса|°C" \
     --add-to TASK
   ```
   recipes → units/times regex above; principles →
   `--grep "always|never|винаги|никога|note to self|I will|my rule"`.
   `--add-to` pushes the fused top AND every grep hit into the ledger —
   no retyping IDs. Do not read anything yet. Wrong candidates get skipped
   later; adding is free.
3. **Process loop, one chunk at a time:**
   `checkpoint.py <folder> TASK next 5`, then for each ID:
   - `--get ID` (add `--context 1` only if the item is visibly cut off),
   - append the finding to the output file — never rewrite it:
     ```
     cat >> <folder>/.notebook/studio/TASK.md << 'XEOF'
     ## <label>
     <the finding, faithful to the source>
     [n] S2 · file · loc · "verbatim anchor quote"
     XEOF
     ```
   - `checkpoint.py <folder> TASK done ID --note "<label>"`
     (not a match → `skip ID --note "why"`).
   Then forget it. Never reopen the output file, never re-get a done chunk.
4. **Fullness sweep — this is what search misses.** For EVERY source:
   `--toc S#` (batches, `--from N`). TOC lines show each chunk's start plus
   a `nums:N` flag for digit-dense chunks. `checkpoint.py <folder> TASK add
   <IDs>` for any line whose start looks target-shaped AND any high-`nums`
   chunk you can't rule out (step 2's grep already covered mid-chunk literal
   patterns; `nums` catches the rest). Then
   `checkpoint.py <folder> TASK sweep S#`. Process new candidates via step 3.
5. **Finish:** `status` must print COMPLETE. Then `notes` → merge duplicate
   labels in the output file (same dish/principle found twice = one entry,
   both citations). Then VERIFY the output file and fix every FAIL.

Found a new lead mid-task (a dish name, a term)? SEARCH it with
`--add-to TASK` — do not chase it in your head.

## Context guard

STOP CLEANLY and hand over when any of these happens:
- you have made ~25 tool calls since the last clean point,
- earlier turns of this conversation look summarized or missing,
- the user's task will clearly not fit in one session.

Stopping cleanly = the ledger is already saved; just run
`checkpoint.py <folder> TASK status`, then tell the user:
"X done, Y pending — say **continue TASK** in a fresh chat."
Resuming = `init` or `status` + `next 5`. Read nothing else. Never try to
finish in one breath at the cost of truncating your own work.

## Studio artifacts (briefing, study guide, FAQ, flashcards, quiz, podcast...)

Only when asked. Read `$SKILL/references/studio.md` first (short), build the
artifact from targeted searches/reads (for "over everything" artifacts, run a
Mode B ledger over the key claims first), save to
`<folder>/.notebook/studio/<name>-<date>.md`, VERIFY it, then show or link it.

## Bans (violating any of these = start the step over)

- `--get S# --full` on sources over ~2,500 words (the tool refuses; use
  `--toc` + targeted `--get` instead — never `--force` unless the user asks)
- repeating a search or grep you already ran this session (SATURATION new 0
  = you are repeating yourself)
- citing from a snippet, a TOC line, or your memory of a chunk
- filling gaps (amounts, dates, names) from your own knowledge
- re-reading the output file or done chunks "to check" — use `notes`
- answering follow-ups without re-searching
- padding: no bullet lists for one-fact answers, no restating the question
