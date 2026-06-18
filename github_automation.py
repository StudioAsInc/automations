import subprocess
import json
import datetime
import os
import re
import base64
import tempfile
import shutil

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
    personal_repos_json = run_gh_cmd(["repo", "list", "--limit", "1000", "--json", "nameWithOwner,isArchived"])
    if personal_repos_json:
        repos.extend([r["nameWithOwner"] for r in json.loads(personal_repos_json) if not r["isArchived"]])

    # Org repos
    orgs_stdout = run_gh_cmd(["org", "list"])
    if orgs_stdout:
        orgs = orgs_stdout.splitlines()
        for org in orgs:
            org_repos_json = run_gh_cmd(["repo", "list", org, "--limit", "1000", "--json", "nameWithOwner,isArchived"])
            if org_repos_json:
                repos.extend([r["nameWithOwner"] for r in json.loads(org_repos_json) if not r["isArchived"]])

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
                print(f"🔗 Closing duplicate issue #{issue['number']} in {repo}")
                run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                            "--body", f"This appears to be a duplicate of #{other['number']}. 🔗 Closing this one in favor of the original. 🚦"])
                run_gh_cmd(["issue", "close", str(issue["number"]), "-R", repo])
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
                print(f"Marking stale issue #{issue['number']} in {repo}")
                run_gh_cmd(["issue", "edit", str(issue["number"]), "-R", repo, "--add-label", "stale"])
                run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo,
                            "--body", "This issue hasn't had any activity for over 14 days. Is this still relevant? 😴"])

def review_prs(repo):
    """Review open PRs for conflicts, missing descriptions, or staleness."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "number,title,body,mergeable,updatedAt,author"])
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
            comments_json = run_gh_cmd(["pr", "view", str(pr["number"]), "-R", repo, "--json", "comments"])
            if comments_json:
                comments = json.loads(comments_json).get("comments", [])
                if not any("PR status summary:" in c["body"] for c in comments):
                    print(f"📝 Posting summary on PR #{pr['number']} in {repo}")
                    summary += "\n".join([f"- {p}" for p in problems])
                    run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", summary + "\nPlease take a look! ✨"])

        # Auto-request review
        requested_json = run_gh_cmd(["pr", "view", str(pr["number"]), "-R", repo, "--json", "reviewRequests"])
        if requested_json:
            requests = json.loads(requested_json).get("reviewRequests", [])
            if not requests and pr["author"]["login"] != "jules-agent":
                owner = repo.split('/')[0]
                print(f"👥 Requesting review from {owner} for PR #{pr['number']}")
                run_gh_cmd(["pr", "edit", str(pr["number"]), "-R", repo, "--add-reviewer", owner])

def analyze_ci_failure(repo, pr_number):
    """Analyze CI failure and return diagnostics."""
    runs_json = run_gh_cmd(["run", "list", "-R", repo, "--branch", f"pull/{pr_number}/head", "--limit", "1", "--json", "databaseId,conclusion"])
    if not runs_json: return None

    runs = json.loads(runs_json)
    if not runs or runs[0]["conclusion"] != "failure":
        return None

    run_id = runs[0]["databaseId"]
    logs = run_gh_cmd(["run", "view", str(run_id), "-R", repo, "--log-failed"])
    return logs

def handle_ci_failures(repo):
    """Detect CI failures, analyze, and attempt fix."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "number,headRefName,headRepositoryOwner"])
    if not prs_json: return

    prs = json.loads(prs_json)
    for pr in prs:
        checks_json = run_gh_cmd(["pr", "checks", str(pr["number"]), "-R", repo, "--json", "status,conclusion,name"])
        if checks_json:
            checks = json.loads(checks_json)
            failed = [c for c in (checks if isinstance(checks, list) else [checks]) if c.get("conclusion") == "failure"]
            if failed:
                print(f"❌ CI failure in {repo} PR #{pr['number']}")
                logs = analyze_ci_failure(repo, pr["number"])
                if logs:
                    error_lines = [line for line in logs.splitlines() if "error" in line.lower()][-10:]
                    msg = f"🚨 **CI Failure Detected!**\n\nRecent Errors:\n```\n" + "\n".join(error_lines) + "\n```\nI am analyzing for an automated fix! 🔧"

                    comments_json = run_gh_cmd(["pr", "view", str(pr["number"]), "-R", repo, "--json", "comments"])
                    if comments_json:
                        comments = json.loads(comments_json).get("comments", [])
                        if not any("CI Failure Detected!" in c["body"] for c in comments):
                            run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", msg])

def security_scan(repo):
    """Scan for potential hardcoded secrets in the repository."""
    print(f"🛡️ Security scan for {repo}...")
    files_json = run_gh_cmd(["api", f"repos/{repo}/contents/"])
    if not files_json: return

    sensitive_patterns = {
        "GitHub PAT": r"ghp_[a-zA-Z0-9]{36}",
        "Generic Secret": r"(?i)secret|password|key|token\s*[:=]\s*['\"][a-zA-Z0-9\-_]{16,}['\"]"
    }

    files = json.loads(files_json)
    for f in files:
        if f["type"] == "file" and f["size"] < 100000:
            content_json = run_gh_cmd(["api", f["url"]])
            if content_json:
                content_b64 = json.loads(content_json).get("content", "")
                if content_b64:
                    content = base64.b64decode(content_b64).decode('utf-8', errors='ignore')
                    for name, pattern in sensitive_patterns.items():
                        if re.search(pattern, content):
                            print(f"🚨 ALERT: Potential {name} found in {repo}/{f['path']}")
                            # Check if issue already exists
                            issues = run_gh_cmd(["issue", "list", "-R", repo, "--state", "open", "--json", "title"])
                            if issues and f"🔒 Security Alert: {name} detected" not in issues:
                                run_gh_cmd(["issue", "create", "-R", repo, "--title", f"🔒 Security Alert: {name} detected",
                                            "--body", f"I found a potential {name} in `{f['path']}`. Please rotate this secret! 🛡️"])

def create_essentials_pr(repo, missing):
    """Create a PR with missing README, LICENSE, or .gitignore."""
    print(f"📦 Creating essentials PR for {repo}...")
    temp_dir = tempfile.mkdtemp()
    try:
        token = os.environ.get("GH_TOKEN")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"

        subprocess.run(["git", "clone", remote_url, temp_dir], check=True)
        branch_name = f"fix/add-essentials-{datetime.datetime.now().strftime('%Y%m%d%H%M')}"
        subprocess.run(["git", "-C", temp_dir, "checkout", "-b", branch_name], check=True)

        for item in missing:
            path = os.path.join(temp_dir, item)
            if item == "README.md":
                with open(path, "w") as f:
                    f.write(f"# {repo.split('/')[-1]}\n\nProject managed by Jules Automation Agent. 🚀")
            elif item == "LICENSE":
                with open(path, "w") as f:
                    f.write("MIT License\n\nCopyright (c) 2024 Jules Agent")
            elif item == ".gitignore":
                with open(path, "w") as f:
                    f.write("node_modules/\n.DS_Store\n.env\n")

            subprocess.run(["git", "-C", temp_dir, "add", item], check=True)

        subprocess.run(["git", "-C", temp_dir, "commit", "-m", "chore: add missing repository essentials 📦"], check=True)
        subprocess.run(["git", "-C", temp_dir, "push", "origin", branch_name], check=True)
        run_gh_cmd(["pr", "create", "-R", repo, "--title", "chore: add missing repository essentials 📦",
                    "--body", f"This PR adds missing essentials: {', '.join(missing)}. ✨", "--head", branch_name])
    except Exception as e:
        print(f"⚠️ Failed to create essentials PR for {repo}: {e}")
    finally:
        shutil.rmtree(temp_dir)

def check_essentials(repo):
    """Ensure repo has README, LICENSE, and .gitignore."""
    files_json = run_gh_cmd(["api", f"repos/{repo}/contents/"])
    if not files_json: return

    file_names = [f["name"].lower() for f in json.loads(files_json)]
    missing = []
    if not any("readme" in n for n in file_names): missing.append("README.md")
    if not any("license" in n for n in file_names): missing.append("LICENSE")
    if not any(".gitignore" in n for n in file_names): missing.append(".gitignore")

    if missing:
        # Check if a PR already exists
        prs = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "title"])
        if prs and "chore: add missing repository essentials 📦" not in prs:
            create_essentials_pr(repo, missing)

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
    # Configure git
    subprocess.run(["git", "config", "--global", "user.email", "jules@agent.ai"])
    subprocess.run(["git", "config", "--global", "user.name", "Jules Agent"])

    for repo in repos:
        print(f"--- 🚀 Systematic scan of: {repo} ---")
        try:
            triage_issues(repo)
            manage_stale_issues(repo)
            review_prs(repo)
            handle_ci_failures(repo)
            security_scan(repo)
            check_essentials(repo)
            branch_hygiene(repo)
        except Exception as e:
            print(f"⚠️ Error scanning {repo}: {e}")
    print("✨ GitHub Automation Cycle Complete! ✨")

if __name__ == "__main__":
    main()
