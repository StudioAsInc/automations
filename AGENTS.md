# Agents

This repository uses AI agents to automate GitHub maintenance tasks.

## Jules — Autonomous GitHub Maintenance Agent

- **Session:** https://jules.google.com/session/1044530857172478402
- **Trigger:** Daily at 00:00 UTC via `.github/workflows/jules-gh-automation.yml`
- **Prompt:** [`JULES_GH_AUTOMATION_PROMPT.md`](./JULES_GH_AUTOMATION_PROMPT.md)

### What it does

Scans all repos across the personal account and all organizations, then autonomously:

- Triages and labels issues; closes duplicates
- Reviews PRs for staleness, conflicts, and missing descriptions
- Comments on issues inactive for 14+ days
- Analyzes and fixes CI failures
- Scans for secrets and CVEs, opens fix PRs
- Creates missing README / LICENSE / .gitignore
- Deletes merged branches older than 2 days

### Auth

Jules authenticates with GitHub via the `GH_TOKEN` environment variable (injected as a repo secret).

### Git Workflow

- **Never push directly to `main`.** Always create a branch and open a PR.
- **Branch naming:** `jules/<type>/<short-description>` — e.g. `jules/fix/ci-failure-api`, `jules/security/cve-lodash`, `jules/chore/add-readme-monorepo`
- **PR naming:** `[Jules] <Type>: <concise description>` — e.g. `[Jules] Fix: resolve CI failure in api workflow`, `[Jules] Security: patch CVE-2024-1234 in lodash`
