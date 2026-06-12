import subprocess
import json
import datetime
import os
import re

# Rule: Always use emojis in every comment or message you post. 🚀✨📦

def run_gh_cmd(cmd):
    """Utility to run gh cli commands."""
    result = subprocess.run(["gh"] + cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    return result.stdout

def get_all_repos():
    """Fetches all repositories from personal account and all organizations."""
    print("🔍 Scanning GitHub account and organizations...")
    repos = []

    # Personal repos
    personal_repos_json = run_gh_cmd(["repo", "list", "--limit", "1000", "--json", "nameWithOwner"])
    if personal_repos_json:
        repos.extend([r["nameWithOwner"] for r in json.loads(personal_repos_json)])

    # Org repos
    orgs_stdout = run_gh_cmd(["org", "list"])
    if orgs_stdout:
        orgs = orgs_stdout.splitlines()
        for org in orgs:
            org_repos_json = run_gh_cmd(["repo", "list", org, "--limit", "1000", "--json", "nameWithOwner"])
            if org_repos_json:
                repos.extend([r["nameWithOwner"] for r in json.loads(org_repos_json)])

    return list(set(repos))

def triage_issues(repo):
    """Triage new/unlabeled issues and manage duplicates."""
    issues_json = run_gh_cmd(["issue", "list", "-R", repo, "--state", "open", "--json", "number,title,labels,body,createdAt"])
    if not issues_json: return

    issues = json.loads(issues_json)
    for issue in issues:
        # Triage unlabeled
        if not issue["labels"]:
            print(f"🏷️ Triaging issue #{issue['number']} in {repo}")
            label = "enhancement"
            title_lower = issue["title"].lower()
            if any(word in title_lower for word in ["bug", "fix", "error", "crash", "fail"]):
                label = "bug"
            elif any(word in title_lower for word in ["docs", "readme", "documentation"]):
                label = "documentation"

            run_gh_cmd(["issue", "edit", str(issue["number"]), "-R", repo, "--add-label", label])
            run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                        "--body", f"Hello! 👋 I've acknowledged this issue and added the '{label}' label. A human will review this soon! 🚀"])

        # Duplicate check (Title similarity)
        for other in issues:
            if other["number"] < issue["number"] and other["title"].strip().lower() == issue["title"].strip().lower():
                print(f"🔗 Flagging duplicate issue #{issue['number']} in {repo}")
                run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                            "--body", f"This appears to be a duplicate of #{other['number']}. 🔗\n\nI will wait for human approval before closing. 🚦"])
                break

def manage_stale_issues(repo):
    """Comment on issues with no activity for 14+ days and add 'stale' label."""
    issues_json = run_gh_cmd(["issue", "list", "-R", repo, "--state", "open", "--json", "number,updatedAt,labels"])
    if not issues_json: return

    issues = json.loads(issues_json)
    now = datetime.datetime.now(datetime.timezone.utc)
    for issue in issues:
        updated_at = datetime.datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00"))
        if (now - updated_at).days > 14:
            if not any(l["name"] == "stale" for l in issue["labels"]):
                print(f"😴 Marking issue #{issue['number']} in {repo} as stale")
                run_gh_cmd(["issue", "edit", str(issue["number"]), "-R", repo, "--add-label", "stale"])
                run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                            "--body", "This issue hasn't had any activity for over 14 days. Is this still relevant? 😴"])

def review_prs(repo):
    """Review open PRs for conflicts, missing descriptions, or staleness."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "number,title,body,mergeable,updatedAt"])
    if not prs_json: return

    prs = json.loads(prs_json)
    now = datetime.datetime.now(datetime.timezone.utc)

    for pr in prs:
        summary = "👋 PR status summary:\n"
        problems = []

        if pr["mergeable"] == "CONFLICTING":
            problems.append("⚠️ This PR has merge conflicts.")
        if not pr.get("body") or len(pr["body"].strip()) < 10:
            problems.append("📝 This PR is missing a proper description.")

        updated_at = datetime.datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
        if (now - updated_at).days > 7:
            problems.append("⌛ This PR is stale (no activity for 7+ days).")

        if problems:
            print(f"📝 Posting summary on PR #{pr['number']} in {repo}")
            summary += "\n".join([f"- {p}" for p in problems])
            run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", summary + "\nPlease take a look! ✨"])

def main():
    repos = get_all_repos()
    for repo in repos:
        print(f"--- 🚀 Systematic scan of: {repo} ---")
        triage_issues(repo)
        manage_stale_issues(repo)
        review_prs(repo)
    print("✨ GitHub Automation Cycle Complete! ✨")

if __name__ == "__main__":
    main()
