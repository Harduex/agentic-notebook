# Grounding & citations — the full contract, with worked examples

NotebookLM's defining behavior is not that it summarizes well; it's that a
user can click any claim and land on the passage that supports it, and that
when the sources are silent, the tool says so. This file turns that behavior
into concrete practice.

## Why this is strict

A grounded system that is 95% grounded is not "mostly trustworthy" — it is
untrustworthy, because the user can't tell which 5% to distrust. The user
chose a source-grounded workflow precisely because they need verifiability
(research, study, legal/medical review, journalism, their own manuscript).
Every uncited fact and every unverifiable citation quietly converts the tool
back into the thing they were avoiding.

## What needs a citation (granularity)

Cite at the level of the **claim**, not the sentence. One sentence with three
distinct facts from three passages gets three markers; three sentences
restating one cited passage need only the one marker at the end of the
restatement.

Needs a citation: facts, figures, dates, names, quotes, positions/arguments
attributed to a source, definitions taken from a source, events, claims about
what a document contains ("chapter 4 covers...").

Doesn't need one: your transitional prose, structure ("There are three themes
here:"), restatements immediately following a cited claim, clearly-labeled
inference, and the user's own words.

**Labeled inference** is your synthesis on top of cited material:

> Source S1 measures attention residue after task-switching [1]; S3 documents
> notification frequency among knowledge workers [2]. **Reading these
> together**, the sources imply — though neither states — that open-plan
> notification culture imposes a continuous residue tax.

The signal phrases ("reading across the sources", "this suggests", "neither
source states this, but") are the fence. Without a fence, everything reads as
sourced.

## The footer, precisely

```
Sources
[1] S2 · deep-work.pdf · p.41 · "the ability to focus without distraction is becoming increasingly rare"
[2] S1 · atomic-habits.epub · ch.3 · "habits are the compound interest of self-improvement"
[3] S4 · lecture-notes.md · - · "the professor emphasized retrieval practice over rereading"
```

- `[N]` numbers appear in order of first inline use; reuse a number for the
  same passage.
- The **anchor quote is verbatim** — copied character-for-character from the
  chunk (5–15 words; ellipsis `...` allowed to bridge a short gap). Its whole
  job is to be findable: `search_index.py --grep "compound interest of
  self-improvement"` must hit. Paraphrased anchors defeat the system.
- Location is the chunk's `loc`. When a chunk spans pages (`p.41-p.42`), cite
  the span. `-` when the source has no locations.
- Chunk IDs (`S2#014`) are your internal handles; the footer shows
  human-readable locations, not chunk IDs.

Run `verify_citations.py` on anything with 3+ citations or anything
long-lived (artifacts, notes). Treat a FAIL as a defect in the *claim*, not
just the footnote: find the real passage, or re-scope the claim to what the
sources actually support, or delete it.

## Worked behaviors

**Fully answerable:**

> **User:** What does the author say causes the forgetting curve to flatten?
>
> **You:** Spaced repetition. The author argues that each successive review at
> an expanding interval "resets the curve at a shallower slope" [1], and
> credits Ebbinghaus's original experiments as the basis [2]. Notably, the
> claim is limited to factual recall — the book explicitly declines to extend
> it to motor skills [3].
>
> Sources
> [1] S2 · make-it-stick.pdf · p.63 · "resets the curve at a shallower slope"
> ...

**Not in the sources (the refusal that builds trust):**

> **User:** What does the book say about ADHD medication?
>
> **You:** The sources don't discuss ADHD medication. The closest material is
> a section on attention and stimulant *caffeine* use during study sessions
> [1] — want me to pull that out?

Notice the shape: plain statement of absence → nearest in-source neighbor →
offer. No apology theater, no hallucinated bridge. (And never pad the refusal
with general knowledge about ADHD medication unless the user then asks for
outside knowledge explicitly.)

**Partially answerable:**

> The sources cover the *what* but not the *when*: both books describe the
> policy's mechanism in detail [1][2], but neither gives a date for its
> adoption. If you add a source that covers the legislative history, I can
> fill that gap.

**Sources conflict:**

> The sources disagree here. S1 reports the trial showed a 23% improvement
> [1], while S3, citing the same trial, reports 17% and attributes the
> difference to the intention-to-treat analysis [2]. The sources themselves
> don't resolve this; S3 is the later publication.

**User asks for outside knowledge:**

> **Outside the sources:** [answer from general knowledge, clearly fenced]
>
> Back in your sources, the related material is... [1]

Keep the fence even mid-paragraph; the reader must always know which regime
each sentence lives in. Return to grounded mode by default on the next turn.

**User's premise contradicts the sources:**

> Actually, the manuscript says the opposite — Elara *refuses* the council's
> offer in chapter 9 [1]. Were you thinking of Bren, who accepts a similar
> offer earlier [2]?

## Absence is a claim: verifying "not covered"

"This source doesn't cover X" is a factual assertion like any other — it just
can't carry a citation, which makes it the easiest place to be confidently
wrong. Two failure modes to guard against:

- **Vocabulary lock-in.** Concepts travel under different names per source: a
  cultural critic writes "the volume war" where an engineer writes "the
  loudness war" or "hypercompression"; one book's "spaced repetition" is
  another's "distributed practice." Searching only your own term for the
  concept finds only the sources that share your vocabulary.
- **Scope conflation.** "No technical settings" is not "not covered." A book
  with no numbers may still take a strong position, tell the history, or
  critique the practice — and a question about "how to think about X"
  includes exactly that.

So before writing "not covered" (in prose, or as a `—` / *Not covered* cell):
run a *scoped* sweep against that specific source — 3+ differently-worded
queries covering synonyms, the source's likely register (technical, cultural,
historical), and key entity names, e.g.
`search_index.py <folder> "loudness war" "volume war" "hypercompression" "dynamic range" --sources S5`.
Two force-multipliers for the sweep: `--grep "volume war"` (substring match,
so it catches the exact phrase however the ranker scores it), and skimming
the source's opening / chapter-title chunks (`--get S5#000 --context 2`) when
a source plausibly touches the topic — a table of contents refutes "not
covered" faster than any query. And one hard rule: **a partial hit forbids a
verdict from a distance.** If the sweep lands even tangential hits in a
source, read around them (`--get <hit> --context 2`) — and when hits
*cluster* in one region of a source, skim the whole containing chapter or
section, not just the adjacent chunks: two hits at p.108 and p.112 put the
target chapter in your hands even when the key passage sits at p.124, beyond
any fixed context window. Landing pages from the target and not looking
sideways is how "not covered" gets written about a chapter that covers it.

When the concept sweep still comes back empty against a source that
plausibly should cover the topic, run the **entity pivot**: harvest the
distinctive proper nouns — people, products, named works — from the sources
that *do* cover the topic, and grep those names across the silent source.
Content written in a different register shares entities even when it shares
no terminology: a cultural history of the loudness war may never say
"loudness war", "hypercompression", or "dynamic range", yet still name Mike
Dorrough's audio processor and the records (*Californication*, Oasis) that a
technical book's metering chapters also orbit. Concept vocabulary is
register-bound; names travel. This is the keyword-retrieval answer to what
embedding search gets for free, and it is the difference between "not
covered" and a found chapter. Only an empty sweep earns the claim. When a
sweep finds partial coverage, say precisely what kind: "S5 takes no technical
position but critiques the practice culturally [n]."

## Who said it: anthologies, interviews, and quoted voices

Some sources are containers of other people's positions — interview
collections, edited anthologies, books built on quotes. Two rules:

- **Attribute the voice, not just the container.** "Owsinski quotes Bruce
  Swedien monitoring at very low level [n]" — never flatten it to "Owsinski
  recommends...". The container-author's own stance (in their narration) and
  their interviewees' stances are separate positions. Attribution nests: when
  a source quotes another writer, carry both layers — "Byrne, citing Greg
  Milner, names the records that started it [n]".
- **Mine the quoted voices deliberately.** In a positions-comparison task, an
  interview book is not one position but many; the disagreements *between its
  interviewees* are often the richest contradictions in the whole notebook.
  Search for the recurring names, not just the topic.

## Traps to avoid

- **Training-data bleed on famous sources.** If the folder contains *Thinking,
  Fast and Slow*, you already "know" things about it — but the user's edition
  is the ground truth, and your memory of secondary commentary is not in the
  notebook. Retrieve anyway; cite what's actually on the page.
- **Citation laundering:** citing a real chunk that is merely *near* the topic
  while the claim itself came from your head. The verify script can't catch
  this (the anchor quote will pass) — only your discipline can. The test: does
  the cited passage, read alone, actually support the sentence it's attached
  to?
- **Confidence inflation:** the source hedges ("preliminary evidence
  suggests"), your answer asserts. Carry the hedge.
- **Momentum answers:** in turn 14 of a chat you "remember" what the sources
  say and stop retrieving. Retrieval is per-claim, not per-session.
- **Numeric drift:** re-type numbers from the chunk you are looking at, never
  from memory of a chunk you saw earlier.
- **Empty-retrieval overreach:** search found nothing, so you answer from the
  gist of the Notebook Guide. The guide is your own writing, not a source.
- **The back-matter citation:** anchoring a claim to a book's own index,
  table of contents, or bibliography ("Hypercompression, fatiguing to the ear
  265" is an index *entry*, not evidence). These lines verify mechanically
  but support nothing — treat any hit in front/back matter as a pointer:
  follow it to the referenced page and cite that. Tell-tale signs: a trailing
  page number in the anchor, `loc` at the very start or end of the book,
  headings like "Index" or "Contents" in the chunk.
- **The uncited section:** a whole section of an artifact — often the last one
  written, when momentum is high — asserting techniques or facts with zero
  markers and no inference fence. It reads as sourced and isn't.
  `verify_citations.py` WARNs on citation-free sections; treat each warning as
  a decision to make explicitly: cite it, fence it, or cut it.
