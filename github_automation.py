import subprocess
import json
import datetime
import os
import re

# Jules GitHub Automation Agent Script 🤖
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
    issues_json = run_gh_cmd(["issue", "list", "-R", repo, "--state", "open", "--json", "number,title,labels,body"])
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

            run_gh_cmd(["issue", "edit", str(issue["number"]), "-R", repo, "--add-label", label])
            run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                        "--body", f"Hello! 👋 I've acknowledged this issue and added the '{label}' label. A human will review this soon! 🚀"])

        # Duplicate check (Simple title match)
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
            summary = "👋 PR status summary:\n" + "\n".join([f"- {p}" for p in problems])
            run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", summary + "\nPlease take a look! ✨"])

def handle_ci_failures(repo):
    """Detect CI failures and leave a diagnostic comment."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "number"])
    if not prs_json: return

    prs = json.loads(prs_json)
    for pr in prs:
        checks_json = run_gh_cmd(["pr", "checks", str(pr["number"]), "-R", repo, "--json", "status,conclusion,name,link"])
        if checks_json:
            checks = json.loads(checks_json)
            failed = [c for c in (checks if isinstance(checks, list) else [checks]) if c.get("conclusion") == "failure"]
            if failed:
                print(f"❌ CI failure in {repo} PR #{pr['number']}")
                msg = "🚨 **CI Failure Detected!**\nThe following checks failed:\n"
                for f in failed:
                    msg += f"- {f['name']} ({f['link']})\n"
                # Avoid duplicate comments
                comments = run_gh_cmd(["pr", "view", str(pr["number"]), "-R", repo, "--json", "comments"])
                if comments and "CI Failure Detected!" not in comments:
                    run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", msg + "\nI am analyzing the logs... 🔍"])

def scan_security_and_essentials(repo):
    """Identify missing essentials and metadata-level security concerns."""
    # Check for missing LICENSE/README/.gitignore
    files_stdout = run_gh_cmd(["api", f"repos/{repo}/contents", "--jq", ".[].name"])
    if files_stdout:
        files = [f.lower() for f in files_stdout.splitlines()]
        missing = []
        if not any(f.startswith("readme") for f in files): missing.append("README.md")
        if not any(f.startswith("license") for f in files): missing.append("LICENSE")
        if ".gitignore" not in files: missing.append(".gitignore")
        if missing:
            print(f"📦 Repo {repo} is missing: {', '.join(missing)}")

def branch_hygiene(repo):
    """Delete merged branches older than 2 days."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "merged", "--limit", "50", "--json", "headRefName,mergedAt"])
    if not prs_json: return

    prs = json.loads(prs_json)
    now = datetime.datetime.now(datetime.timezone.utc)
    for pr in prs:
        if pr["mergedAt"]:
            merged_at = datetime.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
            if (now - merged_at).days > 2:
                branch = pr["headRefName"]
                if branch not in ["main", "master", "develop", "dev"]:
                    print(f"🧹 Deleting old merged branch '{branch}' in {repo}")
                    run_gh_cmd(["api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch}"])

def main():
    repos = get_all_repos()
    for repo in repos:
        print(f"--- 🚀 Systematic scan of: {repo} ---")
        triage_issues(repo)
        manage_stale_issues(repo)
        review_prs(repo)
        handle_ci_failures(repo)
        branch_hygiene(repo)
        scan_security_and_essentials(repo)
    print("✨ GitHub Automation Cycle Complete! ✨")

if __name__ == "__main__":
    main()
