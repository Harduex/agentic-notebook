# Agent instructions — agentic-notebook

## Releasing: bump the marketplace pin (cross-repo)

This plugin is published through the **`harduex`** Claude Code marketplace,
whose manifest lives in a *different* repo:
[`Harduex/skills`](https://github.com/Harduex/skills) at
`.claude-plugin/marketplace.json`. That manifest references this repo by a
**pinned commit `sha`**, so commits here do **not** reach marketplace users
until that pin is updated.

**After releasing a new version here (a new commit on `main`), you MUST either:**

- update the `agentic-notebook` entry's `sha` in
  `Harduex/skills/.claude-plugin/marketplace.json` to the new release commit,
  then commit and push that repo; **or**
- if that repo is not checked out, ask the maintainer to bump the sha.

A release is not done until the marketplace pin points at it — users stay on the
old commit otherwise. This plugin is versioned independently; it is **not** part
of the skills repo's `bundles.json` shared version, so do not run its
`bump_version.py` for changes here.
