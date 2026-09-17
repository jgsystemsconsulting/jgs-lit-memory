<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Contributing

This pack is MIT-licensed. Fork it, adapt the capture procedure for your own
workflow, and send a pull request if the change belongs upstream.

## Local setup

Python 3.9+, no extra packages.

```bash
python test_lit_fetch.py        # offline suite; network is faked
python scripts/check_release.py # local release gate
```

`scripts/check_release.py` is the local release gate: required files,
forbidden tracked paths, leak sentinels, Python headers and SPDX, UTF-8 BOM
in parser-critical files, version consistency across the version-bearing
sources, and SKILL.md frontmatter lint. `.github/workflows/validate.yml`
runs the equivalent checks inline as the CI authority; it reads files only
and never executes repo code.

`python skills/lit-capture/lit_fetch.py --check` is the live endpoint smoke
test. It calls OpenAlex; set `OPENALEX_API_KEY` for the full daily budget.

## Pull requests

- One concern per PR.
- `lit_fetch.py` stays a single stdlib-only file with atomic writes. Do not
  add dependencies or a package layout.
- The capture procedure lives in `skills/lit-capture/SKILL.md`; keep it a
  procedure for the agent, not a second API reference.
- Human-facing prose carries no em dashes; match the existing register.
- Match existing style: plain asserts in tests, stdlib only.

## Licence on contributions

By opening a pull request you license your contribution under the MIT
License in LICENSE, and you confirm you have the right to do so.
