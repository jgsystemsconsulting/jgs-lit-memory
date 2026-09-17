#!/usr/bin/env bash
# Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE.
# SPDX-License-Identifier: MIT
# Idempotent platform configuration (RR-B-21/23) via the gh CLI. The standard
# requires platform state to be applied by a checked-in script, not clicked.
set -euo pipefail

OWNER="jgsystemsconsulting"
REPO="jgs-lit-memory"
DESCRIPTION="Capture scholarly papers from OpenAlex into a per-project local corpus (.lit) with the lit-capture skill. Works with ZCode, Claude Code, Cursor, Codex, Gemini CLI, and Copilot."
HOMEPAGE="https://jgsystemsconsulting.github.io/jgs-lit-memory/"
# >=6 topics: product class + one per supported agent host + domain tags (RR-B-21)
TOPICS=(agent-skills claude-code cursor gemini-cli openai-codex github-copilot zcode openalex literature-review openalex-api)
CI_CHECK="validate"
BRANCH="$(gh api "repos/$OWNER/$REPO" --jq .default_branch)"

gh repo edit "$OWNER/$REPO" --description "$DESCRIPTION"
[ -n "$HOMEPAGE" ] && gh repo edit "$OWNER/$REPO" --homepage "$HOMEPAGE"
for t in "${TOPICS[@]}"; do gh repo edit "$OWNER/$REPO" --add-topic "$t"; done

# Pages from main /docs (RR-B-20)
gh api -X POST "repos/$OWNER/$REPO/pages" -f "source[branch]=$BRANCH" \
  -f "source[path]=/docs" >/dev/null 2>&1 \
  || gh api -X PUT "repos/$OWNER/$REPO/pages" -f "source[branch]=$BRANCH" \
       -f "source[path]=/docs" >/dev/null

# Branch protection: PR + green CI, no force-push/deletion; solo-maintainer
# shape (enforce_admins off, 0 required approvals) per RR-B-23.
gh api -X PUT "repos/$OWNER/$REPO/branches/$BRANCH/protection" \
  --input - <<JSON
{
  "required_status_checks": {"strict": true, "contexts": ["$CI_CHECK"]},
  "enforce_admins": false,
  "required_pull_request_reviews": {"required_approving_review_count": 0},
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON

echo "verify:"
gh repo view "$OWNER/$REPO" --json description,homepageUrl,repositoryTopics
gh api "repos/$OWNER/$REPO/pages" --jq '{url: .html_url, status: .status}'
gh api "repos/$OWNER/$REPO/branches/$BRANCH/protection" --jq \
  '{checks: .required_status_checks.contexts, force: .allow_force_pushes.enabled, del: .allow_deletions.enabled}'
