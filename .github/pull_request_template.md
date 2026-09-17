<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

## Summary

One concern per PR. Link the issue if there is one.

## Type

- [ ] Code
- [ ] Docs
- [ ] Tests
- [ ] Packaging / installer
- [ ] Release files

## Checklist

- [ ] One concern only.
- [ ] `lit_fetch.py` stays a single stdlib-only file with atomic writes; no new dependencies.
- [ ] `skills/lit-capture/SKILL.md` keeps `## When to use` and a Prerequisites marker; the capture procedure stays a procedure, not an API reference.
- [ ] Human-facing prose carries no em dashes; versions in touched files agree with RELEASE-INFO.txt.
- [ ] This PR contains no secrets, tokens, keys, or credentials.
- [ ] I have the right to license this contribution under the repo licence (see LICENSE).

## Tests run

- [ ] `python test_lit_fetch.py`
- [ ] `python scripts/check_release.py`
