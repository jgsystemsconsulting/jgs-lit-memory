<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Security Policy

## Reporting a vulnerability

Report security issues privately via GitHub security advisories on this
repository (Security, Advisories, New advisory), or open a pull request with
the fix when that is safe. Do not open a public issue for a suspected
vulnerability.

We aim to acknowledge reports within 5 business days. Include the affected
version (see RELEASE-INFO.txt), reproduction steps, and impact.

## Scope notes

This pack writes only inside the project it is run in: the `.lit/` corpus
directory (JSON records, JSONL edges, Markdown findings, an inbox queue, and
a generated `.lit/SKILL.md`). The one network component, `lit_fetch.py`,
calls `api.openalex.org` over HTTPS and nothing else. It holds no secrets:
the optional OpenAlex API key is read from `--api-key` or the
`OPENALEX_API_KEY` environment variable and is never written into the corpus.
The pack does not phone home and ships no binaries.

## General support

Non-security questions: open a bug report using the issue form. Do not use
the advisory channel for ordinary defects.
