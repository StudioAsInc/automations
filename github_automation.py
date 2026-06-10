import subprocess
import json
import datetime
import os
import re

# Rule: Always use emojis in every comment or message you post.

def run_gh_cmd(cmd):
    """Utility to run gh cli commands."""
    result = subprocess.run(["gh"] + cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Error running gh {' '.join(cmd)}: {result.stderr}")
        return None
    return result.stdout

def get_all_repos():
    """Fetches all repositories from personal account and all organizations."""
    print("🔍 Fetching all repositories...")
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
    """Triage new/unlabeled issues."""
    issues_json = run_gh_cmd(["issue", "list", "-R", repo, "--state", "open", "--json", "number,title,labels"])
    if not issues_json: return

    issues = json.loads(issues_json)
    for issue in issues:
        if not issue["labels"]:
            print(f"🏷️ Triaging issue #{issue['number']} in {repo}")
            label = "enhancement"
            if "bug" in issue["title"].lower():
                label = "bug"

            run_gh_cmd(["issue", "edit", str(issue["number"]), "-R", repo, "--add-label", label])
            run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                        "--body", f"Hello! 👋 I've acknowledged this issue and added the '{label}' label. A human will review this soon! 🚀"])

def manage_stale_issues(repo):
    """Comment on issues with no activity for 14+ days."""
    issues_json = run_gh_cmd(["issue", "list", "-R", repo, "--state", "open", "--json", "number,updatedAt"])
    if not issues_json: return

    issues = json.loads(issues_json)
    now = datetime.datetime.now(datetime.timezone.utc)
    for issue in issues:
        updated_at = datetime.datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00"))
        if (now - updated_at).days > 14:
            print(f"😴 Commenting on stale issue #{issue['number']} in {repo}")
            run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                        "--body", "This issue hasn't had any activity for over 14 days. Is this still relevant? 🤔"])

def review_prs(repo):
    """Review open PRs for conflicts, missing descriptions, or staleness."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "number,title,body,mergeable,updatedAt"])
    if not prs_json: return

    prs = json.loads(prs_json)
    now = datetime.datetime.now(datetime.timezone.utc)
    for pr in prs:
        summary = "👋 PR status summary:\n"
        is_problematic = False

        if pr["mergeable"] == "CONFLICTING":
            summary += "- ⚠️ This PR has merge conflicts.\n"
            is_problematic = True
        if not pr.get("body") or len(pr["body"].strip()) < 10:
            summary += "- 📝 This PR is missing a proper description.\n"
            is_problematic = True

        updated_at = datetime.datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
        if (now - updated_at).days > 7:
            summary += "- ⌛ This PR is stale (no activity for 7+ days).\n"
            is_problematic = True

        if is_problematic:
            print(f"📝 Posting summary on PR #{pr['number']} in {repo}")
            run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", summary + "\nPlease take a look! ✨"])

def branch_hygiene(repo):
    """Delete merged branches that are more than 2 days old."""
    # This is tricky via gh cli without cloning. We can list merged PRs and their head branches.
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "merged", "--limit", "50", "--json", "headRefName,mergedAt"])
    if not prs_json: return

    prs = json.loads(prs_json)
    now = datetime.datetime.now(datetime.timezone.utc)
    for pr in prs:
        merged_at = datetime.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
        if (now - merged_at).days > 2:
            branch = pr["headRefName"]
            if branch not in ["main", "master", "develop"]:
                print(f"🧹 Attempting to delete merged branch '{branch}' in {repo}")
                # Use API to delete the ref
                run_gh_cmd(["api", "-X", "DELETE", f"repos/{repo}/git/refs/heads/{branch}"])

def check_essentials(repo):
    """Check for missing README, LICENSE, or .gitignore."""
    # This usually requires checking the file tree.
    # For a truly autonomous agent, we might clone or use the API to list files.
    files_json = run_gh_cmd(["api", f"repos/{repo}/contents", "--jq", ".[].name"])
    if not files_json: return

    files = files_json.splitlines()
    missing = []
    if not any(f.lower().startswith("readme") for f in files): missing.append("README.md")
    if not any(f.lower().startswith("license") for f in files): missing.append("LICENSE")
    if ".gitignore" not in files: missing.append(".gitignore")

    if missing:
        print(f"📦 Repo {repo} is missing essentials: {', '.join(missing)}")
        # In a real run, we would clone, create, and open a PR here.

def main():
    repos = get_all_repos()
    for repo in repos:
        print(f"--- 🚀 Processing Repo: {repo} ---")
        triage_issues(repo)
        manage_stale_issues(repo)
        review_prs(repo)
        branch_hygiene(repo)
        check_essentials(repo)

if __name__ == "__main__":
    main()
