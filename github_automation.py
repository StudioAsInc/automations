import subprocess
import json
import datetime
import os

def run_gh_cmd(cmd):
    result = subprocess.run(["gh"] + cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running gh {' '.join(cmd)}: {result.stderr}")
        return None
    return result.stdout

def get_repos():
    repos_json = run_gh_cmd(["repo", "list", "--limit", "1000", "--json", "nameWithOwner"])
    if not repos_json: return []
    personal_repos = [r["nameWithOwner"] for r in json.loads(repos_json)]

    orgs_stdout = run_gh_cmd(["org", "list"])
    orgs = orgs_stdout.splitlines() if orgs_stdout else []

    all_repos = personal_repos
    for org in orgs:
        org_repos_json = run_gh_cmd(["repo", "list", org, "--limit", "1000", "--json", "nameWithOwner"])
        if org_repos_json:
            all_repos.extend([r["nameWithOwner"] for r in json.loads(org_repos_json)])

    return list(set(all_repos))

def triage_issues(repo):
    issues_json = run_gh_cmd(["issue", "list", "-R", repo, "--json", "number,title,labels"])
    if not issues_json: return
    issues = json.loads(issues_json)
    for issue in issues:
        if not issue["labels"]:
            print(f"Triaging issue #{issue['number']} in {repo}")
            label = "enhancement"
            if "bug" in issue["title"].lower(): label = "bug"
            run_gh_cmd(["issue", "edit", str(issue["number"]), "-R", repo, "--add-label", label])
            run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo, "--body", f"Hello! Acknowledged this issue and added the '{label}' label. A human will review this soon."])

def manage_stale_issues(repo):
    issues_json = run_gh_cmd(["issue", "list", "-R", repo, "--json", "number,updatedAt"])
    if not issues_json: return
    issues = json.loads(issues_json)
    now = datetime.datetime.now(datetime.timezone.utc)
    for issue in issues:
        updated_at = datetime.datetime.fromisoformat(issue["updatedAt"].replace("Z", "+00:00"))
        if (now - updated_at).days > 14:
            print(f"Commenting on stale issue #{issue['number']} in {repo}")
            run_gh_cmd(["issue", "comment", str(issue["number"]), "-R", repo, "--body", "This issue hasn't had any activity for over 14 days. Is this still relevant?"])

def review_prs(repo):
    prs_json = run_gh_cmd(["pr", "list", "-R", repo, "--json", "number,title,body,mergeable,updatedAt"])
    if not prs_json: return
    prs = json.loads(prs_json)
    now = datetime.datetime.now(datetime.timezone.utc)
    for pr in prs:
        status = "PR status summary: "
        if pr["mergeable"] == "CONFLICTING": status += "Has merge conflicts. "
        if not pr["body"]: status += "Missing description. "
        updated_at = datetime.datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
        if (now - updated_at).days > 7: status += "This PR is stale. "

        if status != "PR status summary: ":
            print(f"Reviewing PR #{pr['number']} in {repo}")
            run_gh_cmd(["pr", "comment", str(pr["number"]), "-R", repo, "--body", status])

def main():
    repos = get_repos()
    for repo in repos:
        print(f"--- Processing {repo} ---")
        triage_issues(repo)
        manage_stale_issues(repo)
        review_prs(repo)

if __name__ == "__main__":
    main()
