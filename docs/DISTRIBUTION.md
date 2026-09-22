<!--
Copyright (c) 2026 JG Systems Consulting Ltd. All Rights Reserved.
See LICENSE for terms.
-->

# Distribution ledger · jgs-lit-memory

One row per place this product is, or could be, distributed and discovered
(`RR-B-36`, release-repo-standard). Statuses: `submitted` (URL + date, filed
by the maintainer), `in progress`, `deferred`, `deliberate N/A`, `planned`.
A non-submitted row MUST carry the decision and its date so the question
stays closed until its premises change. Revisit at every release: move
statuses, re-date reasons whose premises changed, never drop a row silently.
An agent never marks a row `submitted`; filing is the maintainer's action
and this ledger records it.

Last reviewed: 1.2.1 / 2026-09-22

## In-host marketplaces (manifests shipped, RR-B-29a / RR-S-08)

| Channel | Manifest | Status | Decision / reason | Date |
|---|---|---|---|---|
| Claude Code: `/plugin marketplace add jgsystemsconsulting/jgs-lit-memory` | `.claude-plugin/` | works at repo level | Manifest shipped; installable from the repo today. | 2026-09-17 |
| Claude Code: anthropics/claude-plugins-official directory | `.claude-plugin/` | planned | Submit after repo publish; curated review, human web form. | 2026-09-17 |
| Cursor: cursor.com/marketplace/publish | `.cursor-plugin/` | planned | MIT licence qualifies (§0.3). Submit after repo publish; manually reviewed form. | 2026-09-17 |
| OpenAI Codex CLI: Plugin Directory | `.agents/plugins/` (plus legacy `.claude-plugin/` back-compat) | planned | Submit after repo publish; maintainer action. | 2026-09-17 |
| Gemini CLI: geminicli.com/extensions gallery | `gemini-extension.json` | planned | Auto-indexed crawler: needs the `gemini-cli-extension` topic, root manifest, and a tag. Topic and tag are applied at publish; listing follows the daily crawl. | 2026-09-17 |

## Web directories & catalogues

| Channel | Artifact | Status | Decision / reason | Date |
|---|---|---|---|---|
| GitHub About + topics + Release | `scripts/configure_repo.sh` | in progress | Applied by the checked-in script at publish (RR-B-21 description, homepage, 15 topics incl. one per host). Description and topic set re-reviewed for search on 2026-09-17: `openalex-api` dropped (redundant), `claude-skills` / `skill-md` / `gemini-cli-extension` / `academic-research` / `research-tools` / `literature-search` added; `zotero` / `bibliography` deliberately excluded (not a reference manager; intent mismatch). | 2026-09-17 |
| Org catalogue (labs.jgsystemsconsulting.com) | site entry | planned | RR-B-19 product entry; links install + licensing. Maintainer adds at next site update. | 2026-09-17 |
| Community lists: awesome-claude-skills, awesome-gemini-cli-extensions | PR entry | deferred | MIT qualifies, but both lists are discretionary and manually reviewed. Revisit after first external usage signal rather than at first release. | 2026-09-17 |

## Feedback-loop notes

- `RR-S-17` (in-pack feedback utility skill) is a deliberate exception for
  this pack: single-skill personal research tool, single maintainer.
  Feedback flows through the RR-B-32 issue forms (bug + improvement) named
  in the README. Revisit if external adoption grows. 2026-09-17.
- MCP aggregator directories (RR-M-07) do not apply: no MCP surface. The
  product speaks plain HTTPS to OpenAlex.
