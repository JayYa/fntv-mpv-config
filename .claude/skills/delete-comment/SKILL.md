---
name: delete-comment
description: Sweep the remaining code comments, sort each one, delete it, and lower the comment ratchet.
disable-model-invocation: true
---

# Delete comments

The project bans comments in its own Python and Lua. `check_comments.py` enforces the ban with a ratchet against `comment-baseline.json`: a file's count may only fall. This sweep makes it fall. Reply in Chinese, and write ADRs and issues in Chinese like the existing ones.

## 1. List

Run `python check_comments.py --list`. The list is the work: every comment on it gets a verdict. Upstream code (thumbfast, `types/`) and Lua licence headers are already excluded; leave them alone.

## 2. Sort

Read each comment with its surrounding code and give it exactly one verdict:

- **Tautology**: restates what the code, a name, a test name or `GLOSSARY.md` already says.
- **Stale**: describes code, behaviour or history that no longer holds.
- **Excuse**: covers for a hack: a misleading name, a magic value, dead code, a lint suppression, a workaround that should not exist. The comment is why the hack survives review.
- **Decision record**: explains a non-obvious choice a future reader would otherwise "fix": a platform constraint, a deliberate deviation, an external contract. Check `docs/adr/` first; an existing ADR may already hold it, making the comment a tautology.

When unsure between tautology and decision record, ask whether deleting it would let someone reintroduce a bug. Yes means decision record.

## 3. Act

- **Tautology / Stale**: delete the comment.
- **Excuse**: delete the comment and file one issue per hack (see `docs/agents/issue-tracker.md`, label `ready-for-agent`): what the hack is, where, and the fix. If deleting the comment would break the build (a `noqa` guarding real lint), file the issue and leave the comment for whoever fixes the hack; the baseline keeps counting it.
- **Decision record**: write `docs/adr/NNNN-slug.md` (next number, format of the existing ADRs: title, the decision and its reason, optional Consequences), then delete the comment. Related comments that record one decision share one ADR.

Run `ruff check .` and `python run_tests.py` after the deletions; a deleted comment never changes behaviour, so any failure is an editing slip.

## 4. Ratchet

Run `python check_comments.py --update`, then `python check_comments.py`. Done when the check passes and the baseline holds only comments you deliberately left (each one with an issue).

## 5. Report

A table of every comment with its verdict and action, the issues filed, the ADRs written, and the lines shed (`git diff --shortstat`).
