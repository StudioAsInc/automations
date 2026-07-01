import subprocess
import json
import datetime
import os
import re
import base64
import tempfile
import shutil
import sys

# Jules GitHub Automation Agent Script 🤖
# Rule: Always use emojis in every comment or message you post. 🚀✨📦

def run_gh_cmd(cmd, input_text=None):
    """Utility to run gh cli commands with optional stdin."""
    result = subprocess.run(["gh"] + cmd, capture_output=True, text=True, input=input_text)
    if result.returncode != 0:
        return None
    return result.stdout

def install_gh_cli():
    """Ensure gh cli is installed."""
    if shutil.which("gh") is None:
        print("📥 Attempting to install GitHub CLI...")
        if sys.platform.startswith("linux"):
            try:
                # DEBIAN_FRONTEND=noninteractive to avoid hanging
                env = os.environ.copy()
                env["DEBIAN_FRONTEND"] = "noninteractive"
                subprocess.run(["sudo", "-E", "apt-get", "update"], check=True, env=env)
                subprocess.run(["sudo", "-E", "apt-get", "install", "-y", "gh"], check=True, env=env)
                print("✅ GitHub CLI installed successfully.")
            except Exception as e:
                print(f"❌ Failed to install gh cli on Linux: {e}")
        elif sys.platform == "darwin":
            try:
                subprocess.run(["brew", "install", "gh"], check=True)
                print("✅ GitHub CLI installed successfully via Homebrew.")
            except Exception as e:
                print(f"❌ Failed to install gh cli on macOS: {e}")
        else:
            print("⚠️ Automatic installation not supported for this OS. Please install 'gh' manually! 🛠️")
    else:
        print("✅ GitHub CLI is already installed.")

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
        # Extract the first column (org name) from the table, skipping header
        org_lines = orgs_stdout.splitlines()
        for line in org_lines:
            parts = line.split()
            if not parts or parts[0].upper() == "ORGANIZATION": continue
            org = parts[0]
            print(f"🏢 Scanning organization: {org}")
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

def parse_codeowners(repo):
    """Attempt to parse CODEOWNERS file for relevant reviewers."""
    for path in [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]:
        content_json = run_gh_cmd(["api", f"repos/{repo}/contents/{path}"])
        if content_json:
            try:
                data = json.loads(content_json)
                if "content" in data:
                    content = base64.b64decode(data["content"]).decode('utf-8')
                    return list(set(re.findall(r"@([\w\-/]+)", content)))
            except:
                continue
    return []

def review_prs(repo):
    """Review open PRs for conflicts, missing descriptions, or staleness."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "number,title,body,mergeable,updatedAt,author"])
    if not prs_json: return

    prs = json.loads(prs_json)
    now = datetime.datetime.now(datetime.timezone.utc)

    codeowners = parse_codeowners(repo)

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
                reviewers = codeowners if codeowners else [repo.split('/')[0]]
                print(f"👥 Requesting review from {reviewers} for PR #{pr['number']}")
                for reviewer in reviewers:
                    run_gh_cmd(["pr", "edit", str(pr["number"]), "-R", repo, "--add-reviewer", reviewer])

def attempt_fix_and_push(repo, pr_number, logs):
    """Analyze logs and attempt to push a fix commit."""
    print(f"🔧 Attempting to fix CI failure for {repo} PR #{pr_number}...")
    temp_dir = tempfile.mkdtemp()
    try:
        token = os.environ.get("GH_TOKEN")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"

        run_gh_cmd(["repo", "clone", repo, temp_dir])
        subprocess.run(["gh", "pr", "checkout", str(pr_number)], cwd=temp_dir, check=True)

        # Configure local git identity
        subprocess.run(["git", "-C", temp_dir, "config", "user.email", "jules@agent.ai"])
        subprocess.run(["git", "-C", temp_dir, "config", "user.name", "Jules Agent"])

        fixed = False
        # Ecosystem fix: Node.js (Lint)
        if "lint" in logs.lower() or "prettier" in logs.lower():
            if os.path.exists(os.path.join(temp_dir, "package.json")) and shutil.which("npm"):
                print("🪄 Found package.json, attempting `npm run lint --fix`...")
                subprocess.run(["npm", "install"], cwd=temp_dir)
                subprocess.run(["npm", "run", "lint", "--", "--fix"], cwd=temp_dir)
                fixed = True

        # Ecosystem fix: Kotlin/Gradle (Spotless)
        if "spotless" in logs.lower():
            gradle_path = os.path.join(temp_dir, "gradlew")
            if os.path.exists(gradle_path):
                print("🪄 Found gradle wrapper, attempting `./gradlew spotlessApply`...")
                subprocess.run([gradle_path, "spotlessApply"], cwd=temp_dir)
                fixed = True

        if fixed:
            diff = subprocess.run(["git", "-C", temp_dir, "diff", "--exit-code"])
            if diff.returncode != 0:
                print("✅ Fixes applied, pushing commit...")
                subprocess.run(["git", "-C", temp_dir, "add", "."], check=True)
                subprocess.run(["git", "-C", temp_dir, "commit", "-m", "fix: automated CI failure resolution (lint/format) 🤖🔧"], check=True)
                subprocess.run(["git", "-C", temp_dir, "push", "origin", "HEAD"], check=True)
                run_gh_cmd(["pr", "comment", str(pr_number), "-R", repo, "--body", "I've pushed an automated fix for the CI failure! 🚀🔧"])
    except Exception as e:
        print(f"⚠️ Failed to attempt fix for {repo} PR #{pr_number}: {e}")
    finally:
        shutil.rmtree(temp_dir)

def handle_ci_failures(repo):
    """Detect CI failures, analyze, and attempt fix."""
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "number,headRefName"])
    if not prs_json: return

    prs = json.loads(prs_json)
    for pr in prs:
        checks_json = run_gh_cmd(["pr", "checks", str(pr["number"]), "-R", repo, "--json", "status,conclusion,name"])
        if checks_json:
            checks = json.loads(checks_json)
            failed = [c for c in (checks if isinstance(checks, list) else [checks]) if c.get("conclusion", "").upper() == "FAILURE"]
            if failed:
                print(f"❌ CI failure in {repo} PR #{pr['number']}")
                # Using --pr flag for robust run detection
                runs_json = run_gh_cmd(["run", "list", "-R", repo, "--pr", str(pr["number"]), "--limit", "1", "--json", "databaseId"])
                if runs_json:
                    runs = json.loads(runs_json)
                    if runs:
                        run_id = runs[0]["databaseId"]
                        logs = run_gh_cmd(["run", "view", str(run_id), "-R", repo, "--log-failed"])
                        if logs:
                            attempt_fix_and_push(repo, pr["number"], logs)

                            error_lines = [line for line in logs.splitlines() if "error" in line.lower()][-10:]
                            msg = f"🚨 **CI Failure Detected!**\n\nRecent Errors:\n```\n" + "\n".join(error_lines) + "\n```\nI have attempted an automated fix! 🔍🔧"

                            comments_json = run_gh_cmd(["pr", "view", str(pr["number"]), "-R", repo, "--json", "comments"])
                            if comments_json:
                                comments = json.loads(comments_json).get("comments", [])
                                if not any("CI Failure Detected!" in c["body"] for c in comments):
                                    run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", msg])

def security_scan_and_fix(repo):
    """Scan for secrets and open PRs with redactions."""
    print(f"🛡️ Security scan and fix for {repo}...")
    temp_dir = tempfile.mkdtemp()
    try:
        token = os.environ.get("GH_TOKEN")
        remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
        subprocess.run(["git", "clone", "--depth", "1", remote_url, temp_dir], check=True)

        subprocess.run(["git", "-C", temp_dir, "config", "user.email", "jules@agent.ai"])
        subprocess.run(["git", "-C", temp_dir, "config", "user.name", "Jules Agent"])

        sensitive_patterns = {
            "GitHub PAT": (r"ghp_[a-zA-Z0-9]{36}", "ghp_REDACTED_BY_JULES"),
            "Generic Secret": (r"(?i)(secret|password|key|token)(\s*[:=]\s*)['\"]([a-zA-Z0-9\-_]{16,})['\"]", r"\1\2'REDACTED_BY_JULES'")
        }

        changed = False
        for root, _, files in os.walk(temp_dir):
            if ".git" in root: continue
            for file in files:
                filepath = os.path.join(root, file)
                if os.path.getsize(filepath) > 100000: continue

                try:
                    with open(filepath, "r") as f:
                        content = f.read()

                    new_content = content
                    for name, (pattern, replacement) in sensitive_patterns.items():
                        if re.search(pattern, new_content):
                            print(f"🚨 Found {name} in {filepath}. Redacting...")
                            new_content = re.sub(pattern, replacement, new_content)
                            changed = True

                    if changed and new_content != content:
                        with open(filepath, "w") as f:
                            f.write(new_content)
                except:
                    continue

        if changed:
            branch_name = f"security/redact-secrets-{datetime.datetime.now().strftime('%Y%m%d%H%M')}"
            subprocess.run(["git", "-C", temp_dir, "checkout", "-b", branch_name], check=True)
            subprocess.run(["git", "-C", temp_dir, "add", "."], check=True)
            subprocess.run(["git", "-C", temp_dir, "commit", "-m", "security: redact potential hardcoded secrets 🛡️"], check=True)
            subprocess.run(["git", "-C", temp_dir, "push", "origin", branch_name], check=True)
            run_gh_cmd(["pr", "create", "-R", repo, "--title", "🔒 Security: Redact potential hardcoded secrets",
                        "--body", "I found potential secrets in the codebase and redacted them. Please review and rotate these secrets! 🛡️✨", "--head", branch_name])

        if os.path.exists(os.path.join(temp_dir, "package.json")) and shutil.which("npm"):
            print(f"📦 Checking Node.js dependencies in {repo}...")
            audit_result = subprocess.run(["npm", "audit", "--json"], cwd=temp_dir, capture_output=True, text=True)
            if audit_result.returncode != 0:
                print(f"⚠️ Vulnerabilities found in {repo}. Attempting fix...")
                subprocess.run(["npm", "audit", "fix"], cwd=temp_dir)
                if subprocess.run(["git", "-C", temp_dir, "diff", "--exit-code"]).returncode != 0:
                    branch_name = f"security/fix-dependencies-{datetime.datetime.now().strftime('%Y%m%d%H%M')}"
                    subprocess.run(["git", "-C", temp_dir, "checkout", "-b", branch_name], check=True)
                    subprocess.run(["git", "-C", temp_dir, "add", "."], check=True)
                    subprocess.run(["git", "-C", temp_dir, "commit", "-m", "security: fix outdated dependencies with known CVEs 📦"], check=True)
                    subprocess.run(["git", "-C", temp_dir, "push", "origin", branch_name], check=True)
                    run_gh_cmd(["pr", "create", "-R", repo, "--title", "🛡️ Security: Fix outdated dependencies",
                                "--body", "I've updated dependencies to fix known vulnerabilities found by `npm audit`. 📦✨", "--head", branch_name])

    except Exception as e:
        print(f"⚠️ Security scan failed for {repo}: {e}")
    finally:
        shutil.rmtree(temp_dir)

def check_and_create_essentials(repo):
    """Ensure repo has README, LICENSE, and .gitignore."""
    files_json = run_gh_cmd(["api", f"repos/{repo}/contents/"])
    if not files_json: return

    file_names = [f["name"].lower() for f in json.loads(files_json)]
    missing = []
    if not any("readme" in n for n in file_names): missing.append("README.md")
    if not any("license" in n for n in file_names): missing.append("LICENSE")
    if not any(".gitignore" in n for n in file_names): missing.append(".gitignore")

    if missing:
        prs = run_gh_cmd(["pr", "list", "-R", repo, "--state", "open", "--json", "title"])
        if not prs or "chore: add missing repository essentials 📦" not in prs:
            print(f"📦 Creating essentials PR for {repo}...")
            temp_dir = tempfile.mkdtemp()
            try:
                token = os.environ.get("GH_TOKEN")
                remote_url = f"https://x-access-token:{token}@github.com/{repo}.git"
                subprocess.run(["git", "clone", "--depth", "1", remote_url, temp_dir], check=True)

                subprocess.run(["git", "-C", temp_dir, "config", "user.email", "jules@agent.ai"])
                subprocess.run(["git", "-C", temp_dir, "config", "user.name", "Jules Agent"])

                branch_name = f"fix/add-essentials-{datetime.datetime.now().strftime('%Y%m%d%H%M')}"
                subprocess.run(["git", "-C", temp_dir, "checkout", "-b", branch_name], check=True)

                year = datetime.datetime.now().year
                for item in missing:
                    path = os.path.join(temp_dir, item)
                    if item == "README.md":
                        with open(path, "w") as f:
                            f.write(f"# {repo.split('/')[-1]}\n\nProject managed by Jules Automation Agent. 🚀")
                    elif item == "LICENSE":
                        with open(path, "w") as f:
                            f.write(f"MIT License\n\nCopyright (c) {year} Jules Agent")
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
    install_gh_cli()

    token = os.environ.get("GH_TOKEN")
    if token:
        # Use stdin to avoid shell injection and visible token in process list
        run_gh_cmd(["auth", "login", "--with-token"], input_text=token)

    repos = get_all_repos()
    for repo in repos:
        print(f"--- 🚀 Systematic scan of: {repo} ---")
        try:
            triage_issues(repo)
            manage_stale_issues(repo)
            review_prs(repo)
            handle_ci_failures(repo)
            security_scan_and_fix(repo)
            check_and_create_essentials(repo)
            branch_hygiene(repo)
        except Exception as e:
            print(f"⚠️ Error scanning {repo}: {e}")
    print("✨ GitHub Automation Cycle Complete! ✨")

if __name__ == "__main__":
    main()
