# Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE.
# SPDX-License-Identifier: MIT
"""Release gate (RR-B-15). Run locally: python scripts/check_release.py

Local coverage: required files, forbidden tracked paths, forbidden-content
leak sentinels, Python headers and SPDX, UTF-8 BOM in parser-critical files,
machine-local path strings (RR-B-34), version consistency across the
version-bearing sources (including the docs/index.html page strings), and SKILL.md frontmatter lint.

CI (.github/workflows/validate.yml) runs the equivalent checks inline and is
the authority. CI must not execute checkout code, so the two implementations
are kept in sync by hand, not by shared code. Both sides skip `.github/` in
the content scan because workflow files legitimately discuss secret
plumbing.

Exits non-zero on any failure.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

REQUIRED = [
    "LICENSE",
    "COPYRIGHT",
    "NOTICE",
    "README.md",
    "CHANGELOG.md",
    "RELEASE-INFO.txt",
    "CITATION.cff",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".gitignore",
    "SKILLS.md",
    "docs/skill-usage.md",
    "docs/other-agents.md",
    "docs/DISTRIBUTION.md",
    "docs/index.html",
    "docs/.nojekyll",
    "install.py",
    "install.sh",
    "install.ps1",
    "test_lit_fetch.py",
    "skills/lit-capture/SKILL.md",
    "skills/lit-capture/lit_fetch.py",
    "scripts/check_release.py",
    "scripts/configure_repo.sh",
    ".claude-plugin/marketplace.json",
    ".claude-plugin/plugin.json",
    ".cursor-plugin/marketplace.json",
    ".cursor-plugin/plugin.json",
    ".agents/plugins/marketplace.json",
    "gemini-extension.json",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/improvement.yml",
    ".github/pull_request_template.md",
]

FORBIDDEN_PATH_PARTS = [
    "__pycache__",
    ".venv",
    ".worktrees",
    ".pytest_cache",
    ".ruff_cache",
    ".bak",
]

# keep in sync with .github/workflows/validate.yml (Forbidden content)
FORBIDDEN_CONTENT = [
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"CONFIDENTIAL\s+[-—]\s+Not for external distribution"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
]

# RR-B-34: machine-local profile paths with a real-looking user segment
MACHINE_LOCAL = [
    re.compile(r"[Cc]:[/\\]Users[/\\][A-Za-z0-9_.-]+"),
    re.compile(r"/Users/[A-Za-z0-9_.-]+/"),
    re.compile(r"/home/[A-Za-z0-9_.-]+/"),
    re.compile(r"[Cc]:[/\\]Users[/\\][A-Za-z0-9_.-]+[/\\](?:OneDrive|AppData)"),
]

HEADER_SENTINEL = "Copyright (c) 2026 JG Systems Consulting Ltd"

TEXT_SUFFIXES = (".py", ".md", ".txt", ".yml", ".yaml", ".json", ".cff", ".html",
                 ".sh", ".ps1", ".css")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError("git ls-files failed or empty")
    return out.stdout.splitlines()


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")


def check_required() -> bool:
    missing = [f for f in REQUIRED if not pathlib.Path(f).is_file()]
    if missing:
        fail("required files missing: " + ", ".join(missing))
        return False
    return True


def check_forbidden_paths(tracked: list[str]) -> bool:
    bad = [f for f in tracked if any(p in f for p in FORBIDDEN_PATH_PARTS)]
    if bad:
        fail("forbidden tracked paths: " + ", ".join(bad[:20]))
        return False
    return True


def _content_files(tracked: list[str]) -> list[str]:
    return [
        f for f in tracked
        if not f.startswith(".github/")
        and f.endswith(TEXT_SUFFIXES)
        and pathlib.Path(f).is_file()
    ]


def check_forbidden_content(tracked: list[str]) -> bool:
    hits = []
    for f in _content_files(tracked):
        text = pathlib.Path(f).read_text(encoding="utf-8", errors="ignore")
        if any(rx.search(text) for rx in FORBIDDEN_CONTENT):
            hits.append(f)
    if hits:
        fail("leak sentinel in: " + ", ".join(hits[:20]))
        return False
    return True


def check_machine_local(tracked: list[str]) -> bool:
    hits = []
    for f in _content_files(tracked):
        text = pathlib.Path(f).read_text(encoding="utf-8", errors="ignore")
        if any(rx.search(text) for rx in MACHINE_LOCAL):
            hits.append(f)
    if hits:
        fail("machine-local path string in: " + ", ".join(hits[:20]))
        return False
    return True


def check_headers(tracked: list[str]) -> bool:
    missing = []
    for f in tracked:
        if not f.endswith(".py"):
            continue
        head = pathlib.Path(f).read_text(encoding="utf-8", errors="ignore")[:600]
        if HEADER_SENTINEL not in head or "SPDX-License-Identifier" not in head:
            missing.append(f)
    if missing:
        fail("python header/SPDX missing: " + ", ".join(missing[:20]))
        return False
    return True


def check_bom() -> bool:
    hits = []
    for pat in ("*.toml", "*.json", "*.yaml", "*.yml", "*.cff"):
        for p in pathlib.Path(".").rglob(pat):
            if ".git" in p.parts or not p.is_file():
                continue
            if p.read_bytes()[:3] == b"\xef\xbb\xbf":
                hits.append(p.as_posix())
    if hits:
        fail("UTF-8 BOM in: " + ", ".join(hits))
        return False
    return True


def _read(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


def check_versions() -> bool:
    def changelog_top() -> str | None:
        m = re.search(r"^##\s*\[?v?(\d+\.\d+\.\d+)", _read("CHANGELOG.md"), re.M)
        return m.group(1) if m else None

    def release_info() -> str | None:
        m = re.search(r"^Version:\s*(\d+\.\d+\.\d+)", _read("RELEASE-INFO.txt"), re.M)
        return m.group(1) if m else None

    def citation() -> str | None:
        m = re.search(r"^version:\s*[\"']?(\d+\.\d+\.\d+)",
                      _read("CITATION.cff"), re.M)
        return m.group(1) if m else None

    def plugin(path: str) -> str | None:
        p = pathlib.Path(path)
        if not p.is_file():
            return None
        return json.loads(p.read_text(encoding="utf-8")).get("version")

    vals = {
        "CHANGELOG": changelog_top(),
        "RELEASE-INFO": release_info(),
        "CITATION.cff": citation(),
        "claude plugin.json": plugin(".claude-plugin/plugin.json"),
        "cursor plugin.json": plugin(".cursor-plugin/plugin.json"),
        "gemini-extension.json": plugin("gemini-extension.json"),
    }
    print("versions:", vals)
    uniq = {v for v in vals.values() if v}
    if None in vals.values() or len(uniq) != 1:
        fail("version mismatch across sources")
        return False
    print(f"versions agree at {uniq.pop()}")
    return True


def check_site_version() -> bool:
    """docs/index.html version strings must equal RELEASE-INFO.txt (RR: site drift 1.1.0 vs 1.2.1)."""
    m = re.search(r"^Version:\s*(\d+\.\d+\.\d+)", _read("RELEASE-INFO.txt"), re.M)
    if not m:
        fail("RELEASE-INFO.txt: no Version line")
        return False
    expected = m.group(1)
    page = _read("docs/index.html")
    loci = {
        "softwareVersion": r'"softwareVersion":"(\d+\.\d+\.\d+)"',
        "masthead REV": r"REV <b>(\d+\.\d+\.\d+)</b>",
        "footer Rev": r'<span class="label">Rev</span><b>(\d+\.\d+\.\d+)</b>',
    }
    bad = []
    for name, pat in loci.items():
        v = re.search(pat, page)
        val = v.group(1) if v else None
        if val != expected:
            bad.append(f"{name}={val!r} (expected {expected})")
    if bad:
        fail("site page version mismatch or missing pattern: " + "; ".join(bad))
        return False
    print(f"site page versions agree at {expected}")
    return True


def check_skills() -> bool:
    ok = True
    skills = sorted(pathlib.Path("skills").glob("*/SKILL.md"))
    if not skills:
        fail("no skills/*/SKILL.md found")
        return False
    for p in skills:
        t = p.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", t, re.S)
        if not m:
            fail(f"{p}: missing YAML frontmatter")
            ok = False
            continue
        fm, body = m.group(1), t[m.end():]
        nm = re.search(r"^name:\s*(\S+)", fm, re.M)
        if not nm:
            fail(f"{p}: frontmatter missing name")
            ok = False
            continue
        name = nm.group(1).strip().strip('"').strip("'")
        if name != p.parent.name:
            fail(f"{p}: name {name!r} != dir {p.parent.name!r}")
            ok = False
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            fail(f"{p}: name not kebab-case: {name}")
            ok = False
        if not re.search(r"^description:\s*\S", fm, re.M):
            fail(f"{p}: frontmatter missing description")
            ok = False
        if "## When to use" not in body:
            fail(f"{p}: missing '## When to use'")
            ok = False
        if not re.search(r"Prerequisites|Requirements|^compatibility:", body, re.M):
            fail(f"{p}: missing prerequisites marker")
            ok = False
    if not ok:
        fail("SKILL.md frontmatter lint failed")
    return ok


def main() -> int:
    tracked = tracked_files()
    checks = [
        check_required(),
        check_forbidden_paths(tracked),
        check_forbidden_content(tracked),
        check_machine_local(tracked),
        check_headers(tracked),
        check_bom(),
        check_versions(),
        check_site_version(),
        check_skills(),
    ]
    if all(checks):
        print("release gate: PASS")
        return 0
    print("release gate: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
