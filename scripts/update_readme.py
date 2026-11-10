#!/usr/bin/env python3
"""Keeps the Projects and Recent activity sections of the profile README current.

Runs daily from GitHub Actions. Only touches text between <!--KEY:START--> and <!--KEY:END-->,
so everything else in README.md stays exactly as written.

Projects: an entry from projects.json is listed when its repository is public, or when it is
marked "always". Public repositories link to the code; the repository's own description is
used when it has one.
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CACHE = ROOT / "assets" / "stats.json"
PROJECTS = ROOT / "projects.json"

USER = os.environ.get("GH_USER", "zairithm")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def gh(path):
    h = {"Accept": "application/vnd.github+json", "User-Agent": f"{USER}-profile-readme"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request("https://api.github.com" + path, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def fetch_repos():
    """All public, non-fork repositories except the profile repo, most recently pushed first."""
    out = []
    for r in gh(f"/users/{USER}/repos?sort=pushed&per_page=100"):
        if r.get("fork") or r["name"].lower() == USER.lower():
            continue
        out.append({
            "name": r["name"], "url": r["html_url"], "lang": r.get("language") or "",
            "desc": (r.get("description") or "").strip(), "pushed": r["pushed_at"],
        })
    return out


def put(text, key, content):
    pat = re.compile(rf"(<!--{key}:START-->)(.*?)(<!--{key}:END-->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def projects_block(repos):
    live = {r["name"].lower(): r for r in (repos or [])}
    rows = ["| Project | Description | Links |", "|---|---|---|"]
    for p in json.loads(PROJECTS.read_text(encoding="utf-8")):
        repo = live.get(p["repo"].lower())
        if not repo and not p.get("always"):
            continue
        links = []
        if repo:
            name = f"[{p['repo']}]({repo['url']})"
            about = repo["desc"] or p["about"]
            links.append(f"[Code]({repo['url']})")
        else:
            name, about = p["repo"], p["about"]
        if p.get("demo"):
            links.append(f"[Demo]({p['demo']})")
        rows.append(f"| **{name}** | {about} | {' · '.join(links)} |")
    return "\n".join(rows)


def ago(iso, now):
    days = (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def recent_block(repos, now):
    out = []
    for r in (repos or [])[:5]:
        bits = [f"[{r['name']}]({r['url']})"]
        if r["lang"]:
            bits.append(r["lang"])
        bits.append(f"updated {ago(r['pushed'], now)}")
        out.append("- " + " · ".join(bits))
    # the whole section, heading included, stays hidden until there is something to show
    return "#### Recent activity\n\n" + "\n".join(out) + "\n" if out else ""


def main():
    now = datetime.now(timezone.utc)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    try:
        cache = {"repos": fetch_repos()}
    except Exception as err:  # keep the last good value if the API is down
        print(f"[warn] repos: {err}")
    repos = cache.get("repos")

    old = README.read_text(encoding="utf-8")
    new = put(old, "PROJECTS", projects_block(repos))
    new = put(new, "RECENT", recent_block(repos, now))
    if new != old:
        README.write_text(new, encoding="utf-8")
    CACHE.write_text(json.dumps(cache, indent=2) + "\n", encoding="utf-8")
    print(f"{len(repos or [])} public repos")


if __name__ == "__main__":
    main()
