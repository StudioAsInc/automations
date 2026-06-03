# gh-automations

Automated workflows for managing my GitHub account and organizations. All automation lives here — issues, PRs, CI, dependencies, security, and housekeeping across every repo I own.

## Workflows

### `jules-gh-automation.yml` — AI Repo Maintenance

Runs daily at 00:00 UTC. Sends a prompt to a persistent [Jules AI](https://jules.google.com) session via the Jules REST API. Jules then scans and acts on every repo across my personal account and all organizations.

**Covers:**
- Issue triage and labeling; closing duplicates
- PR review — stale, conflicting, or missing descriptions
- Stale issue comments (14+ days inactive)
- CI failure analysis and auto-fix commits
- Secret scanning and dependency CVE patching
- Creating missing README / LICENSE / .gitignore
- Deleting merged branches older than 2 days

**Secrets required:**

| Secret | Description |
|---|---|
| `JULES_API_KEY` | Jules API key from [jules.google.com](https://jules.google.com) |
| `GH_TOKEN` | GitHub PAT with `repo` and `read:org` scopes |

**Manual trigger:** Actions → "Run workflow" with an optional custom prompt.

---

> More automations will be added as needed.
