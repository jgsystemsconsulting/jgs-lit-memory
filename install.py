#!/usr/bin/env python3
# Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE.
# SPDX-License-Identifier: MIT
"""Install in-repo skills into a coding agent (RR-S-02/03/15).

Default (zcode): copy each skills/<name>/ package into ~/.zcode/skills/<name>/
(flat). That default is the binding delivery form for this pack.

  python install.py                         # ZCode, flat ~/.zcode/skills
  python install.py --agent claude          # namespaced ~/.claude/skills/jgs/
  python install.py --agent all             # every user-global agent
  python install.py --dry-run
  python install.py --list-agents
  python install.py --dest DIR              # override dest root (any agent)
  python install.py --link                  # symlink native installs when OS allows

Stdlib only. Exit 0 on success, 1 on error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

NS = "jgs"
HOME = Path.home()
ROOT = Path(__file__).resolve().parent


def read_release_version() -> str:
    path = ROOT / "RELEASE-INFO.txt"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise SystemExit(f"cannot read version from RELEASE-INFO.txt: {e}") from e
    m = re.search(r"^Version:\s*(\d+\.\d+\.\d+)\s*$", text, re.M)
    if not m:
        raise SystemExit("cannot read version from RELEASE-INFO.txt")
    return m.group(1)


def claude_home() -> Path:
    cfg = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(cfg) if cfg else HOME / ".claude"


def discover_skills(skills_root: Path) -> list[Path]:
    if not skills_root.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(skills_root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            found.append(child)
    return found


def _skill_parts(src: Path) -> tuple[str, str]:
    text = (src / "SKILL.md").read_text(encoding="utf-8")
    desc, body = "", text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            front = text[3:end]
            body = text[end + 4:].lstrip("\n")
            for line in front.splitlines():
                if line.strip().startswith("description:"):
                    desc = line.split(":", 1)[1].strip().strip('"').strip("'")
    return desc, body


def render_mdc(src: Path) -> str:
    desc, body = _skill_parts(src)
    return (
        f"---\ndescription: {desc}\nalwaysApply: false\n---\n\n"
        f"<!-- jgs-lit-memory: '{src.name}' transformed for Cursor. -->\n\n"
        f"{body}"
    )


def replace_dir(dest: Path) -> None:
    if dest.exists():
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)


def install_native(
    src: Path, dest: Path, *, link: bool, dry: bool
) -> None:
    if dry:
        print(f"  would install {src.name} -> {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if (dest / "SKILL.md").is_file() or dest.is_symlink():
            replace_dir(dest)
        else:
            raise SystemExit(f"refusing to overwrite non-skill path: {dest}")
    if link:
        try:
            os.symlink(src.resolve(), dest, target_is_directory=True)
            print(f"  linked {src.name} -> {dest}")
            return
        except OSError as exc:
            print(
                f"notice: --link failed ({exc}); falling back to copy for {src.name}",
                file=sys.stderr,
            )
    shutil.copytree(src, dest)
    print(f"  installed {src.name} -> {dest}")


def install_cursor(src: Path, dest: Path, *, dry: bool) -> None:
    if dry:
        print(f"  would write {src.name} -> {dest}")
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_mdc(src), encoding="utf-8")
    print(f"  wrote {src.name} -> {dest}")


def install_gemini(src: Path, dest: Path, *, dry: bool) -> None:
    desc, body = _skill_parts(src)
    manifest = {
        "name": f"{NS}-{src.name}",
        "version": read_release_version(),
        "description": desc,
    }
    if dry:
        print(f"  would install extension {src.name} -> {dest}")
        return
    if dest.exists():
        known = (
            dest.is_symlink()
            or (
                dest.is_dir()
                and (
                    (dest / "gemini-extension.json").is_file()
                    or (
                        (dest / "GEMINI.md").is_file()
                        and (dest / "SKILL.md").is_file()
                    )
                    or not any(dest.iterdir())
                )
            )
        )
        if known:
            replace_dir(dest)
        else:
            raise SystemExit(
                f"refusing to overwrite non-Gemini-extension path: {dest}"
            )
    dest.mkdir(parents=True)
    (dest / "GEMINI.md").write_text(body, encoding="utf-8")
    shutil.copy2(src / "SKILL.md", dest / "SKILL.md")
    shutil.copy2(src / "lit_fetch.py", dest / "lit_fetch.py")
    (dest / "gemini-extension.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  installed extension {src.name} -> {dest}")


def agent_dest(agent: str, skill: Path, dest_root: Path | None) -> Path:
    name = skill.name
    if dest_root is not None:
        if agent == "cursor":
            return dest_root / f"{name}.mdc"
        if agent == "gemini":
            return dest_root / f"{NS}-{name}"
        if agent == "zcode":
            return dest_root / name
        return dest_root / NS / name
    if agent == "zcode":
        return HOME / ".zcode" / "skills" / name
    if agent == "claude":
        return claude_home() / "skills" / NS / name
    if agent == "openclaw":
        return HOME / ".openclaw" / "skills" / NS / name
    if agent == "copilot":
        return HOME / ".copilot" / "skills" / NS / name
    if agent == "codex":
        return HOME / ".agents" / "skills" / NS / name
    if agent == "gemini":
        return HOME / ".gemini" / "extensions" / f"{NS}-{name}"
    if agent == "cursor":
        return Path.cwd() / ".cursor" / "rules" / f"{name}.mdc"
    raise SystemExit(f"unknown agent: {agent}")


AGENTS = {
    "zcode": {"kind": "native", "in_all": True, "label": "ZCode (flat ~/.zcode/skills)"},
    "claude": {"kind": "native", "in_all": True, "label": "Claude Code (namespaced jgs/)"},
    "openclaw": {"kind": "native", "in_all": True, "label": "OpenClaw"},
    "copilot": {"kind": "native", "in_all": True, "label": "GitHub Copilot CLI"},
    "codex": {"kind": "native", "in_all": True, "label": "OpenAI Codex CLI"},
    "gemini": {"kind": "gemini", "in_all": True, "label": "Gemini CLI (extension)"},
    "cursor": {"kind": "cursor", "in_all": False, "label": "Cursor (project-local rules)"},
}


def install_one_agent(
    agent: str,
    skills: list[Path],
    dest_root: Path | None,
    *,
    link: bool,
    dry: bool,
) -> None:
    spec = AGENTS[agent]
    print(f"[{agent}] {spec['label']} ({spec['kind']})")
    for skill in skills:
        dest = agent_dest(agent, skill, dest_root)
        kind = spec["kind"]
        if kind == "native":
            install_native(skill, dest, link=link, dry=dry)
        elif kind == "cursor":
            install_cursor(skill, dest, dry=dry)
        elif kind == "gemini":
            install_gemini(skill, dest, dry=dry)
        else:
            raise SystemExit(f"unhandled kind {kind}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skills-root",
        type=Path,
        default=ROOT / "skills",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Override dest root. Default depends on --agent "
        "(zcode: ~/.zcode/skills).",
    )
    parser.add_argument(
        "--link",
        action="store_true",
        help="Try symlink for native installs; on failure, copy",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned installs; write nothing",
    )
    parser.add_argument(
        "--agent",
        default="zcode",
        help="zcode|claude|openclaw|copilot|codex|gemini|cursor|all "
        "(default: zcode)",
    )
    parser.add_argument(
        "--list-agents",
        action="store_true",
        help="List supported agents and their default targets, then exit",
    )
    args = parser.parse_args(argv)

    if args.list_agents:
        sample = ROOT / "skills" / "lit-capture"
        for name, spec in AGENTS.items():
            dest = agent_dest(name, sample, None)
            scope = "user-global" if spec["in_all"] else "project-local"
            print(f"{name:9} {spec['kind']:7} {scope:14} {dest}")
        return 0

    skills = discover_skills(args.skills_root)
    if not skills:
        print("no skills to install")
        return 0

    if args.agent == "all":
        chosen = [n for n, a in AGENTS.items() if a["in_all"]]
    elif args.agent in AGENTS:
        chosen = [args.agent]
    else:
        parser.error(f"unknown agent '{args.agent}' (see --list-agents)")

    for agent in chosen:
        install_one_agent(
            agent, skills, args.dest, link=args.link, dry=args.dry_run
        )
    if args.dry_run:
        print(f"dry-run: {len(skills)} skill(s), {len(chosen)} agent(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
