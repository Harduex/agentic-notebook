#!/usr/bin/env python3
"""Unit tests for checkpoint.py disk task ledger.

Stdlib only. Run with:
  python3 skills/agentic-notebook-mini/scripts/test_checkpoint.py
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(SCRIPTS))

import checkpoint


class TestCheckpointLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.nb = self.folder / ".notebook"
        self.nb.mkdir()

        # Write dummy sources.json
        sources = {
            "sources": [
                {"id": "S1", "path": "doc1.txt", "title": "Doc 1"},
                {"id": "S2", "path": "doc2.txt", "title": "Doc 2"}
            ]
        }
        (self.nb / "sources.json").write_text(json.dumps(sources), encoding="utf-8")

        # Write dummy chunks.jsonl
        chunks = [
            {"id": "S1#001", "source_id": "S1", "text": "Recipe 1: Salad"},
            {"id": "S1#002", "source_id": "S1", "text": "Recipe 2: Soup"},
            {"id": "S2#001", "source_id": "S2", "text": "Recipe 3: Cake"}
        ]
        with open(self.nb / "chunks.jsonl", "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c) + "\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_and_add(self):
        checkpoint.cmd_init(self.folder, "find recipes")
        t = checkpoint.load_task(self.folder, "find-recipes")
        self.assertEqual(t["slug"], "find-recipes")
        self.assertIn("S1", t["sources"])
        self.assertIn("S2", t["sources"])

        # Add valid chunk IDs and invalid ones
        checkpoint.cmd_add(self.folder, t, ["S1#001", "S1#002", "S9#999"])
        t = checkpoint.load_task(self.folder, "find-recipes")
        self.assertIn("S1#001", t["candidates"])
        self.assertIn("S1#002", t["candidates"])
        self.assertNotIn("S9#999", t["candidates"])

    def test_mark_done_and_skip(self):
        checkpoint.cmd_init(self.folder, "extract items")
        t = checkpoint.load_task(self.folder, "extract-items")
        checkpoint.cmd_add(self.folder, t, ["S1#001", "S1#002"])

        t = checkpoint.load_task(self.folder, "extract-items")
        checkpoint.cmd_mark(self.folder, t, ["S1#001"], "done", "Salad dish")
        checkpoint.cmd_mark(self.folder, t, ["S1#002"], "skipped", "Not a recipe")

        t = checkpoint.load_task(self.folder, "extract-items")
        self.assertEqual(t["candidates"]["S1#001"]["status"], "done")
        self.assertEqual(t["candidates"]["S1#001"]["note"], "Salad dish")
        self.assertEqual(t["candidates"]["S1#002"]["status"], "skipped")

    def test_sweep_and_completion(self):
        checkpoint.cmd_init(self.folder, "task completion")
        t = checkpoint.load_task(self.folder, "task-completion")
        checkpoint.cmd_add(self.folder, t, ["S1#001"])

        t = checkpoint.load_task(self.folder, "task-completion")
        checkpoint.cmd_mark(self.folder, t, ["S1#001"], "done", "Finished")

        t = checkpoint.load_task(self.folder, "task-completion")
        checkpoint.cmd_sweep(self.folder, t, ["S1", "S2"])

        t = checkpoint.load_task(self.folder, "task-completion")
        done, skipped, pending, swept, unswept = checkpoint.counts(t)
        self.assertEqual(len(pending), 0)
        self.assertEqual(len(unswept), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
