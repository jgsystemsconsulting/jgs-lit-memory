<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Using the pack with other agents

Skills follow the open [Agent Skills](https://agentskills.io) `SKILL.md`
format. Some agents read that format natively (the skill folder is copied
unchanged). Others need a format transform.

`install.py` handles both. Default agent is **zcode** (flat
`~/.zcode/skills/<skill>/`). That default is the binding delivery form for
this pack: `lit_fetch.py` ships inside the skill folder, so the flat ZCode
path (`~/.zcode/skills/lit-capture/lit_fetch.py`) is the one quoted in
`skills/lit-capture/SKILL.md`. The namespaced Claude Code target
(`$CLAUDE_CONFIG_DIR/skills/jgs/<skill>/`) ships as a first-class
`--agent claude` path. A pre-existing flat mirror (for example
`~/.claude/skills/lit-capture/`) keeps working; it is the documented
flat-install fallback.

```bash
python install.py --list-agents
python install.py --agent claude --dry-run
python install.py --agent all
python install.py --agent cursor
```

## Per-agent targets

| Agent | `--agent` | Format | Default target |
|-------|-----------|--------|----------------|
| ZCode | `zcode` (default) | native (folder) | `~/.zcode/skills/<skill>/` |
| Claude Code | `claude` | native (folder) | `~/.claude/skills/jgs/<skill>/` (honours `$CLAUDE_CONFIG_DIR`) |
| OpenClaw | `openclaw` | native (folder) | `~/.openclaw/skills/jgs/<skill>/` |
| GitHub Copilot CLI | `copilot` | native (folder) | `~/.copilot/skills/jgs/<skill>/` |
| OpenAI Codex CLI | `codex` | native (folder) | `~/.agents/skills/jgs/<skill>/` |
| Gemini CLI | `gemini` | extension | `~/.gemini/extensions/jgs-<skill>/` |
| Cursor | `cursor` | transform (project rule) | `./.cursor/rules/<skill>.mdc` (project-local) |

`--agent all` covers the user-global agents (zcode, claude, openclaw,
copilot, codex, gemini). Cursor is project-local: run `--agent cursor` in
the repo you want rules in.

## Native vs transform

Native agents get the whole skill folder (`SKILL.md` plus
`lit_fetch.py`). Transform agents (Cursor) get `SKILL.md` inlined into one
`.mdc` rule; the script is not transformed, so Cursor installs reference the
cloned repo's copy or a native install elsewhere. Gemini gets an extension
directory with `GEMINI.md`, `SKILL.md`, `gemini-extension.json`, and
`lit_fetch.py`; the installed script lives at
`~/.gemini/extensions/jgs-lit-capture/lit_fetch.py` (or
`DIR/jgs-lit-capture/lit_fetch.py` under `--dest DIR`).

Existing `--dest` and `--link` flags still work. `--dest` overrides the
dest root for the chosen agent. For `zcode`, `--dest DIR` writes
`DIR/<skill>/`, which is what the CI packaging smoke uses.
