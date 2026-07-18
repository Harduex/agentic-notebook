# Audio & Video Overviews — the performed-explanation pipeline

The Audio Overview is NotebookLM's most famous feature: two hosts having what
feels like a real, warm, occasionally digressive conversation about the
sources. The realism is not a voice trick — it is a **multi-stage writing
pipeline**, and the pipeline is what this reference reproduces. Run every
stage; the stages are cheap and skipping them is audible.

Default deliverable: a production-ready script at
`.notebook/studio/audio-overview-YYYY-MM-DD.md`. If a TTS capability exists
(see "Producing actual audio"), also render the audio.

## The four formats

Ask which format the user wants if they didn't say; default to Deep Dive.

| Format | Feel | Length target (spoken) |
|---|---|---|
| **Deep Dive** | Two co-hosts explore the material together — the classic | 10–15 min (~1,600–2,400 words) |
| **Brief** | One or two hosts, essentials only, no banter arc | 1–2 min (~180–320 words) |
| **Critique** | Hosts give an expert review of the material — strengths, weaknesses, gaps | 5–10 min |
| **Debate** | Hosts take opposing sides of a genuine tension *in the sources* | 5–10 min |

Honor customization exactly as NotebookLM's "focus" box does: topic focus
("only chapter 3"), audience ("I'm new to this" / "expert listeners"),
persona tweaks ("one host is a skeptical engineer"), language, length. The
user's focus note steers emphasis — it never licenses unsourced content.

## The pipeline (Deep Dive shown; adapt for others)

**Stage 0 — Production brief (internal).** Fix the parameters: format,
audience, length, focus, source scope. Decide the *one thing* a listener
should retain — everything in the episode serves it.

**Stage 1 — Research pass.** Retrieve broadly across the scoped sources (this
is a whole-notebook artifact: source-by-source coverage, not a few lucky
chunks). Collect: the 4–7 ideas that matter, the 3–5 best concrete
specifics (numbers, examples, stories — audio lives on specifics), real
tensions or surprises, and terms needing plain-language translation. Note
chunk IDs as you go; you'll need them for the citation appendix.

**Stage 2 — Outline.** Episode arc: cold-open hook (a surprising specific,
never "welcome to our podcast about...") → what-this-is framing → 3–5
segments, each with its own mini-arc (setup → insight → example → so-what) →
recap of the one thing → a closing thought or open question. Then **revise the
outline** once: cut the weakest segment, reorder for momentum, make sure each
segment hands off to the next.

**Stage 3 — Full script.** Write the dialogue. Two voices with fixed,
complementary roles:

- **Host A — the guide.** Enthusiastic, drives the structure, explains,
  wields the analogies.
- **Host B — the curious proxy.** Asks what the listener would ask, requests
  examples, summarizes back ("so what you're saying is..."), pushes on weak
  points, occasionally supplies a connection A didn't make.

Craft rules that make it sound like NotebookLM: exchanges are short (1–4
sentences; a monologue over ~70 words must be interrupted); explanations move
concrete-first; every technical term is translated in-flow ("attention
residue — basically, the part of your brain still chewing on the last task");
analogies are the primary teaching tool; hosts refer to the material as "the
sources", "this book", "the author" (they are discussing documents, not
omniscient); signpost transitions conversationally ("Okay, so that's the
mechanism — but here's where it gets weird").

**Stage 4 — Critique pass.** Reread as a harsh producer. Check against: Does
the cold open hook in ≤2 exchanges? Is anything factually unsupported by the
sources (cut or fix — grounding audit happens *here*, against your Stage 1
chunk notes)? Does B ask at least one question per segment? Any exchange that
teaches nothing and charms nothing? Jargon that slipped through? Does the
recap actually land the one thing? Write the defect list down.

**Stage 5 — Revision.** Fix every defect. Re-check length against the target
(spoken pace ≈ 160 wpm).

**Stage 6 — Disfluency pass (the magic).** A sterile script reads as robotic
no matter the voice. Go through the final script adding *sparing, natural*
human texture: brief acknowledgments ("Right.", "Okay, wait—"), false starts
("It's— well, it's more like a tax"), mid-thought pivots, small laughs
[laughs], overlapping affirmations ("Exactly."), thinking sounds ("Hmm,",
"you know,"). Density: roughly one touch every 2–4 exchanges — under-season;
too many reads as parody. Never add disfluencies that change meaning.

**Script file format:**

```markdown
# Audio Overview (Deep Dive): <topic>
Format: Deep Dive · Target length: ~12 min · Audience: general

HOST A: You know what stopped me cold in these sources? One number: ...
HOST B: Okay, that can't be right. Where's that from?
HOST A: Chapter two. And the author's explanation is actually weirder than the number...

...

## Production notes
- One thing to retain: ...
- Pronunciations: Csikszentmihalyi = "cheek-sent-me-high"
- Segment map with timings

## Citation appendix
Every factual beat → source. [1] S2 · deep-work.pdf · p.41 · "..."
(Keep citations OUT of the spoken lines; this appendix is the grounding audit trail.)
```

Run the citation appendix through `verify_citations.py` like any artifact.

## Interactive mode (join the conversation)

NotebookLM lets listeners interrupt the hosts with questions. Emulate it on
request: stay in character as both hosts, take the user's question, and
answer it grounded in the sources with the same two-voice dynamic — then
offer to "resume the episode" where it left off. Grounding rules do not relax
in character; a host who doesn't know says so in voice ("Honestly? The
sources don't get into that.").

## Producing actual audio

Check the environment before promising audio: a TTS CLI (`edge-tts`, `piper`,
`say`), a TTS API the user has connected, or a platform voice tool. If one
exists, render Host A and Host B with two clearly distinct voices, stitch
segments in order (e.g. with `ffmpeg` if present), and deliver the audio file
alongside the script. If none exists, deliver the script and say exactly
that: it's written to be read aloud or fed to any two-voice TTS.

## Video Overview

NotebookLM's video overview is a narrated slideshow: simple visuals, tight
narration, one idea per scene. Reuse pipeline stages 0–2, then produce a
scene-by-scene script (typically 6–12 scenes for 3–7 minutes):

```markdown
## Scene 4 — The forgetting curve (0:52–1:24)
VISUAL: Line chart, retention % vs days; second flatter line appears on review.
  Style: single accent color, minimal labels ("Day 1", "Day 7").
ON-SCREEN TEXT: "Each review flattens the curve"
NARRATION: Here's the pattern the whole book hangs on. Memory decays fast —
  most of it in the first days. But each well-timed review resets the curve at
  a shallower slope. [cited in appendix]
```

Rules: narration ≈ 140–150 wpm and never a wall of text; VISUAL directions
must be producible from the sources (charts only from real source data —
cite the numbers in the appendix); scene 1 is a hook, the last scene is the
takeaway. If slide/HTML capabilities exist, additionally render the deck
(one slide per scene, narration in speaker notes) so the user has a playable
approximation; otherwise the script itself is the deliverable.
