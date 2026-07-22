#!/usr/bin/env python3
"""
checkpoint.py — Disk-based task ledger for exhaustive extraction tasks.
Pure stdlib. The ledger IS the agent's memory: candidates, progress, and
per-source sweep state live in .notebook/tasks/<slug>.json, so a small model
never has to hold them in context and any session can resume with one command.

Usage:
  python checkpoint.py <folder> init "find all recipes"    create (or resume)
  python checkpoint.py <folder> list                       list tasks
  python checkpoint.py <folder> <task> add S2#014 S3#001   add candidate chunks
  python checkpoint.py <folder> <task> next 5              next pending candidates
  python checkpoint.py <folder> <task> done S2#014 --note "banitsa"
  python checkpoint.py <folder> <task> skip S2#014 --note "grocery list, not a recipe"
  python checkpoint.py <folder> <task> sweep S2 S3         mark sources fully skimmed
  python checkpoint.py <folder> <task> status              compact resume brief
  python checkpoint.py <folder> <task> notes               all done/skip labels (for dedupe)

Rules the ledger enforces for you:
- 'add' rejects chunk IDs that don't exist in the index (catches typos and
  hallucinated IDs).
- a task is COMPLETE only when every source is swept AND no candidate is pending.
"""

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

NOTEBOOK_DIR = ".notebook"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:48] or "task"


def nb_dir(folder: Path) -> Path:
    d = folder / NOTEBOOK_DIR
    if not d.is_dir():
        sys.exit(f"No {NOTEBOOK_DIR}/ in {folder}. Run build_index.py first.")
    return d


def tasks_dir(folder: Path) -> Path:
    d = nb_dir(folder) / "tasks"
    d.mkdir(exist_ok=True)
    return d


def load_sources(folder: Path):
    sj = nb_dir(folder) / "sources.json"
    if not sj.exists():
        sys.exit("sources.json missing — run build_index.py first.")
    with open(sj, encoding="utf-8") as f:
        data = json.load(f)
    sources = data.get("sources", data) if isinstance(data, dict) else data
    if isinstance(sources, dict):
        sources = list(sources.values())
    return [s.get("id") for s in sources if s.get("id")]


def load_chunk_ids(folder: Path):
    cj = nb_dir(folder) / "chunks.jsonl"
    ids = set()
    if cj.exists():
        with open(cj, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ids.add(json.loads(line)["id"])
                    except Exception:
                        pass
    return ids


def task_path(folder: Path, slug: str) -> Path:
    return tasks_dir(folder) / f"{slug}.json"


def load_task(folder: Path, slug: str):
    p = task_path(folder, slug)
    if not p.exists():
        avail = ", ".join(f.stem for f in tasks_dir(folder).glob("*.json")) or "none"
        sys.exit(f"Unknown task '{slug}'. Existing tasks: {avail}\n"
                 f"Create one: checkpoint.py <folder> init \"task name\"")
    with open(p, encoding="utf-8") as f:
        t = json.load(f)
    # sync: sources added to the index after task creation become pending
    for sid in load_sources(folder):
        t["sources"].setdefault(sid, "pending")
    return t


def save_task(folder: Path, t):
    t["updated"] = now()
    p = task_path(folder, t["slug"])
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=1)
    tmp.replace(p)


def counts(t):
    c = t["candidates"]
    done = sum(1 for v in c.values() if v["status"] == "done")
    skipped = sum(1 for v in c.values() if v["status"] == "skipped")
    pending = [k for k, v in c.items() if v["status"] == "pending"]
    swept = [s for s, st in t["sources"].items() if st == "swept"]
    unswept = [s for s, st in t["sources"].items() if st != "swept"]
    return done, skipped, pending, swept, unswept


def sort_ids(ids):
    def key(i):
        m = re.match(r"S(\d+)#(\d+)$", i)
        return (int(m.group(1)), int(m.group(2))) if m else (10 ** 9, 0)
    return sorted(ids, key=key)


def print_status(folder: Path, t):
    done, skipped, pending, swept, unswept = counts(t)
    print(f"TASK {t['slug']} · \"{t['task']}\" · updated {t['updated']}")
    print(f"output file: {t['output']}   (append findings here, never rewrite)")
    print(f"sources: {len(swept)}/{len(t['sources'])} swept"
          + (f" · NOT swept: {' '.join(sort_ids(unswept))}" if unswept else ""))
    print(f"candidates: {len(t['candidates'])} total · {done} done · "
          f"{skipped} skipped · {len(pending)} pending")
    if pending:
        shown = sort_ids(pending)[:15]
        more = len(pending) - len(shown)
        print("pending: " + " ".join(shown) + (f" +{more} more" if more else ""))
    if not pending and not unswept:
        print("COMPLETE — all sources swept, no pending candidates. Final steps: "
              "1) 'notes' to check for duplicate labels, 2) verify_citations.py "
              "on the output file.")
    elif pending:
        print(f"NEXT: checkpoint.py <folder> {t['slug']} next 5")
    else:
        print(f"NEXT: sweep remaining sources with --toc, e.g. "
              f"search_index.py <folder> --toc {sort_ids(unswept)[0]}")


def cmd_init(folder: Path, name: str):
    slug = slugify(name)
    p = task_path(folder, slug)
    if p.exists():
        t = load_task(folder, slug)
        print(f"RESUMING existing task (created {t['created']}):")
        print_status(folder, t)
        save_task(folder, t)
        return
    t = {
        "task": name, "slug": slug, "created": now(), "updated": now(),
        "output": f"{NOTEBOOK_DIR}/studio/{slug}.md",
        "sources": {sid: "pending" for sid in load_sources(folder)},
        "candidates": {},
    }
    (nb_dir(folder) / "studio").mkdir(exist_ok=True)
    save_task(folder, t)
    print(f"TASK created: {slug}")
    print(f"output file: {t['output']}")
    print(f"sources to cover: {' '.join(sort_ids(t['sources']))}")
    print("workflow: add <IDs from grep/search> -> next 5 -> (--get, append "
          "finding to output, done ID --note label) -> sweep each source via "
          "--toc -> status shows COMPLETE.")


def cmd_list(folder: Path):
    files = sorted(tasks_dir(folder).glob("*.json"))
    if not files:
        print("No tasks. Create one: checkpoint.py <folder> init \"task name\"")
        return
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                t = json.load(fh)
            done, skipped, pending, swept, unswept = counts(t)
            state = "COMPLETE" if not pending and not unswept else "in progress"
            print(f"{t['slug']} · \"{t['task']}\" · {done} done / "
                  f"{len(pending)} pending / {len(unswept)} sources unswept · {state}")
        except Exception:
            print(f"{f.stem} · (unreadable)")


def cmd_add(folder: Path, t, ids):
    known = load_chunk_ids(folder)
    added, dup, unknown = [], [], []
    for cid in ids:
        cid = cid.strip().strip(",")
        if not cid:
            continue
        if known and cid not in known:
            unknown.append(cid)
        elif cid in t["candidates"]:
            dup.append(cid)
        else:
            t["candidates"][cid] = {"status": "pending", "note": ""}
            added.append(cid)
    save_task(folder, t)
    print(f"added {len(added)}" + (f": {' '.join(sort_ids(added))}" if added else ""))
    if dup:
        print(f"already tracked ({len(dup)}): {' '.join(sort_ids(dup))}")
    if unknown:
        print(f"REJECTED — not in index ({len(unknown)}): {' '.join(unknown)} "
              f"(copy IDs exactly from search/grep output)")
    _, _, pending, _, _ = counts(t)
    print(f"pending now: {len(pending)}")


def cmd_mark(folder: Path, t, ids, status, note):
    ok, missing = [], []
    for cid in ids:
        cid = cid.strip().strip(",")
        if cid in t["candidates"]:
            t["candidates"][cid]["status"] = status
            if note:
                t["candidates"][cid]["note"] = note
            ok.append(cid)
        else:
            missing.append(cid)
    save_task(folder, t)
    done, skipped, pending, swept, unswept = counts(t)
    print(f"{status}: {' '.join(sort_ids(ok))}" + (f" ({note})" if note else ""))
    if missing:
        print(f"not tracked (add first): {' '.join(missing)}")
    print(f"pending: {len(pending)} · done: {done} · skipped: {skipped}")
    if not pending:
        if unswept:
            print(f"candidates drained — now sweep sources: {' '.join(sort_ids(unswept))}")
        else:
            print("COMPLETE — run status for final steps.")


def cmd_sweep(folder: Path, t, sids):
    ok, missing = [], []
    for sid in sids:
        sid = sid.strip().strip(",")
        if sid in t["sources"]:
            t["sources"][sid] = "swept"
            ok.append(sid)
        else:
            missing.append(sid)
    save_task(folder, t)
    done, skipped, pending, swept, unswept = counts(t)
    print(f"swept: {' '.join(sort_ids(ok))}")
    if missing:
        print(f"unknown source IDs: {' '.join(missing)}")
    print(f"sources swept: {len(swept)}/{len(t['sources'])}"
          + (f" · remaining: {' '.join(sort_ids(unswept))}" if unswept else " · ALL SWEPT"))


def cmd_next(folder: Path, t, n):
    _, _, pending, _, unswept = counts(t)
    if not pending:
        print("0 pending candidates."
              + (f" Sweep remaining sources: {' '.join(sort_ids(unswept))}"
                 if unswept else " Task is COMPLETE — run status."))
        return
    batch = sort_ids(pending)[:n]
    print(f"NEXT {len(batch)} of {len(pending)} pending:")
    for cid in batch:
        print(cid)
    print("for each: --get ID -> append the finding + citation to "
          f"{t['output']} (bash >>) -> done ID --note \"label\". "
          "One at a time. Never re-read done chunks.")


def cmd_notes(folder: Path, t):
    rows = [(cid, v) for cid, v in t["candidates"].items()
            if v["status"] in ("done", "skipped")]
    if not rows:
        print("No done/skipped candidates yet.")
        return
    print(f"{len(rows)} labels (use to spot duplicates before finalizing):")
    for cid, v in sorted(rows, key=lambda r: (r[1]["status"], r[0])):
        print(f"{v['status']} · {cid} · {v['note'] or '(no note)'}")


def main():
    argv = sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        sys.exit(1)
    folder = Path(argv[0]).resolve()
    if not folder.is_dir():
        sys.exit(f"Folder not found: {folder}")
    # --note extraction (applies to done/skip)
    note = ""
    if "--note" in argv:
        i = argv.index("--note")
        if i + 1 < len(argv):
            note = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
        else:
            argv = argv[:i]

    cmd = argv[1]
    if cmd == "init":
        if len(argv) < 3:
            sys.exit('Usage: checkpoint.py <folder> init "task name"')
        cmd_init(folder, " ".join(argv[2:]))
    elif cmd == "list":
        cmd_list(folder)
    else:
        slug, action = slugify(argv[1]), (argv[2] if len(argv) > 2 else "status")
        rest = argv[3:]
        t = load_task(folder, slug)
        if action == "add":
            if not rest:
                sys.exit("Usage: ... add S2#014 [S3#001 ...]")
            cmd_add(folder, t, rest)
        elif action == "done":
            cmd_mark(folder, t, rest, "done", note)
        elif action == "skip":
            cmd_mark(folder, t, rest, "skipped", note)
        elif action == "sweep":
            cmd_sweep(folder, t, rest)
        elif action == "next":
            n = int(rest[0]) if rest and rest[0].isdigit() else 5
            cmd_next(folder, t, n)
        elif action == "notes":
            cmd_notes(folder, t)
        elif action == "status":
            print_status(folder, t)
            save_task(folder, t)
        else:
            sys.exit(f"Unknown action '{action}'. "
                     "Actions: add done skip sweep next notes status")


if __name__ == "__main__":
    main()
