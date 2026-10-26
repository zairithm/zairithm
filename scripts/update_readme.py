#!/usr/bin/env python3
"""Refreshes the dynamic parts of the profile: banner, build log, milestones, recent repos.

Runs daily from GitHub Actions. Only touches text between <!--KEY:START--> and <!--KEY:END-->,
so everything else in README.md stays exactly as you wrote it.
"""
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
BANNER = ROOT / "assets" / "banner.svg"
CACHE = ROOT / "assets" / "stats.json"
MILESTONES = ROOT / "milestones.json"
PROJECTS = ROOT / "projects.json"

USER = os.environ.get("GH_USER", "zairithm")
LC_USER = os.environ.get("LC_USER", "zairithm")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

IST = timezone(timedelta(hours=5, minutes=30))
START = datetime(2026, 10, 26, tzinfo=IST)   # Week 1 of the roadmap
SUMMER_ENDS = datetime(2027, 8, 1, tzinfo=IST)
TOTAL_WEEKS = 29

PHASES = [
    (1, 5, "foundations"),
    (6, 10, "intermediate rust"),
    (11, 14, "solana + web3 rust"),
    (15, 16, "gate break"),
    (17, 23, "gsoc sprint"),
    (24, 29, "hackathon + advanced rust"),
]
WEEKS = [
    "setup and first rust programs", "ownership and borrowing", "structs, enums and match",
    "collections and error handling", "generics, traits and lifetimes", "tests, iterators and closures",
    "smart pointers and a cli tool", "concurrency", "async rust with tokio", "backend with axum",
    "solana basics", "an escrow program in anchor", "spl tokens and bounties", "resume and gsoc scouting",
    "gate exam (rust on pause)", "gate exam (rust on pause)", "picking a gsoc org", "first open-source pr",
    "more open-source prs", "writing the gsoc proposal", "submitting the gsoc proposal",
    "backup gsoc proposal", "gsoc deadline week", "hackathon kickoff", "hackathon core build",
    "hackathon build and tests", "gsoc results week", "hackathon submission", "wrap up and write",
]


# ---------- data ----------
def get_json(url, data=None, headers=None):
    h = {"User-Agent": f"{USER}-profile-readme"}
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def gh(path):
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return get_json("https://api.github.com" + path, headers=h)


def fetch_leetcode():
    q = {
        "query": "query($u: String!) { matchedUser(username: $u) { submitStatsGlobal { acSubmissionNum { difficulty count } } } }",
        "variables": {"u": LC_USER},
    }
    d = get_json("https://leetcode.com/graphql", data=q, headers={"Referer": "https://leetcode.com"})
    rows = d["data"]["matchedUser"]["submitStatsGlobal"]["acSubmissionNum"]
    n = {r["difficulty"]: r["count"] for r in rows}
    return {"total": n.get("All", 0), "easy": n.get("Easy", 0), "medium": n.get("Medium", 0), "hard": n.get("Hard", 0)}


def fetch_merged_prs():
    q = urllib.parse.quote(f"author:{USER} type:pr is:merged -user:{USER}")
    d = gh(f"/search/issues?q={q}&sort=updated&order=desc&per_page=3")
    latest = [
        {"repo": i["repository_url"].split("/repos/")[1], "title": i["title"], "url": i["html_url"]}
        for i in d.get("items", [])
    ]
    return {"count": d.get("total_count", 0), "latest": latest}


def fetch_recent_repos():
    out = []
    for r in gh(f"/users/{USER}/repos?sort=pushed&per_page=15"):
        if r.get("fork") or r["name"].lower() == USER.lower():
            continue
        out.append({
            "name": r["name"], "url": r["html_url"], "lang": r.get("language") or "",
            "desc": (r.get("description") or "").strip(), "pushed": r["pushed_at"],
        })
        if len(out) == 5:
            break
    return out


def fetch_repo_names():
    return sorted(r["name"] for r in gh(f"/users/{USER}/repos?per_page=100"))


# ---------- helpers ----------
def week_info(now):
    n = max(1, (now - START).days // 7 + 1)
    if n <= TOTAL_WEEKS:
        phase = next(p for a, b, p in PHASES if a <= n <= b)
        return n, phase, WEEKS[n - 1], f"week {n} of {TOTAL_WEEKS}"
    if now < SUMMER_ENDS:
        return n, "summer", "shipping gsoc / internship work", "summer build"
    return n, "job hunt", "interviews and placements", "release mode"


def ago(iso, now):
    t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    days = (now - t).days
    return "today" if days <= 0 else "yesterday" if days == 1 else f"{days} days ago"


def put(text, key, content):
    pat = re.compile(rf"(<!--{key}:START-->)(.*?)(<!--{key}:END-->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(3)}", text)


def strip_block(text, key):
    return put(text, key, "")


# ---------- sections ----------
def build_block(n, phase, title, lc, prs):
    filled = round(min(n, TOTAL_WEEKS) / TOTAL_WEEKS * 28)
    bar = ("=" * max(filled - 1, 0) + ">").ljust(28)
    lc_line = (f"leetcode {lc['total']} solved ({lc['easy']} easy, {lc['medium']} medium, {lc['hard']} hard)"
               if lc else "leetcode syncing")
    step = f"{min(n, TOTAL_WEEKS)}/{TOTAL_WEEKS}"
    return "\n".join([
        "```console",
        "$ cargo build --release -p zaid",
        "   Compiling ai-ml   v1.0.0   python, pytorch, tensorflow, scikit-learn, pandas",
        "   Compiling web3    v1.0.0   solidity, hardhat, ethers.js, ipfs",
        f"   Compiling rust    v0.{min(n, TOTAL_WEEKS)}.0   rust book, rustlings, tokio, axum, solana + anchor",
        f"   Compiling dsa     v0.{lc['total'] if lc else 0}.0   c++, leetcode",
        f"    Building [{bar}] {step}  {phase}: {title}",
        f"    Finished {lc_line}, {prs['count'] if prs else 0} PRs merged upstream",
        "```",
    ])


def tests_block(lc, prs):
    items = json.loads(MILESTONES.read_text())
    lines, passed = [], 0
    for m in items:
        done = bool(m.get("done"))
        auto = m.get("auto") or {}
        if "leetcode" in auto and lc:
            done = lc["total"] >= auto["leetcode"]
        if "merged_prs" in auto and prs:
            done = prs["count"] >= auto["merged_prs"]
        passed += done
        name = m["test"]
        lines.append(f"test {name} {'.' * max(3, 38 - len(name))} {'ok' if done else 'todo'}")
    todo = len(items) - passed
    return "\n".join(
        ["```console", "$ cargo test -p zaid", f"running {len(items)} tests"] + lines +
        ["", f"test result: {passed} passed; {todo} todo; 0 failed", "```"]
    )


def projects_block(names, n):
    if not PROJECTS.exists():
        return ""
    have = {x.lower() for x in (names or [])}
    rows = ["| | Project | What it does | Status |", "|---|---|---|---|"]
    for p in json.loads(PROJECTS.read_text()):
        repo, week = p["repo"], p.get("week", 0)
        if repo.lower() in have:
            name, status = f"[**{repo}**](https://github.com/{USER}/{repo})", "✅ live"
            if p.get("demo"):
                status += f" · [demo]({p['demo']})"
        elif names is None:
            name, status = f"**{repo}**", "⏳ syncing"
        elif not week:
            name, status = f"**{repo}**", "⏳ code coming soon"
        elif week and week <= n:
            name, status = f"**{repo}**", "🔨 building now"
        elif week > TOTAL_WEEKS:
            name, status = f"**{repo}**", "🗓️ summer 2027"
        else:
            name, status = f"**{repo}**", f"🗓️ planned, week {week}"
        rows.append(f"| {p.get('emoji', '')} | {name} | {p['about']} | {status} |")
    return "\n".join(rows)


def ensure_projects_markers(text):
    if "<!--PROJECTS:START-->" in text:
        return text
    pat = re.compile(r"(## Things I.ve built\n)(.*?)(\n## Milestones)", re.S)
    return pat.sub(lambda m: m.group(1) + "\n<!--PROJECTS:START-->\n<!--PROJECTS:END-->\n" + m.group(3), text, count=1)


def recent_block(repos, prs, now):
    out = []
    for r in repos or []:
        bits = [f"[**{r['name']}**]({r['url']})"]
        if r["lang"]:
            bits.append(f"`{r['lang']}`")
        bits.append(f"pushed {ago(r['pushed'], now)}")
        line = "- " + " · ".join(bits)
        if r["desc"]:
            line += f"  \n  {r['desc']}"
        out.append(line)
    if prs and prs["latest"]:
        out.append("\n**Latest merged PRs to other projects**")
        out += [f"- [{p['title']}]({p['url']}) in `{p['repo']}`" for p in prs["latest"]]
    return "\n".join(out) if out else "_Nothing public yet. First Rust commits are on the way._"


def banner_svg(n, label, title, lc, prs):
    e = html.escape
    title = title if len(title) <= 46 else title[:45] + "…"
    lc_txt = f"{lc['total']} leetcode solved" if lc else "leetcode syncing"
    pr_txt = f"{prs['count'] if prs else 0} PRs merged upstream"

    def row(i, inner):
        return f'<text xml:space="preserve" class="t l l{i}" x="28" y="{64 + (i - 1) * 26}">{inner}</text>'

    lines = [
        row(1, '<tspan class="w">warning</tspan>: this developer is still compiling'),
        row(2, f'<tspan class="b">  --&gt;</tspan> zairithm/journey.rs:{n}:1'),
        row(3, '<tspan class="b">   |</tspan>'),
        row(4, '<tspan class="b"> 1 |</tspan> <tspan class="k">let</tspan> zaid = '
               '<tspan class="ty">Builder</tspan>::new().ai().blockchain().rust();'),
        row(5, '<tspan class="b">   |</tspan>' + " " * 44 + f'<tspan class="c">^^^^^^ {e(label)}</tspan>'),
        row(6, '<tspan class="b">   |</tspan>'),
        row(7, f'<tspan class="b">   =</tspan> <tspan class="h">help</tspan>: now learning {e(title)}'),
        row(8, f'<tspan class="b">   =</tspan> <tspan class="h">note</tspan>: {e(lc_txt)}, {e(pr_txt)}'),
        row(9, '<tspan class="m">zaid@rust:~$</tspan> <tspan class="cur">█</tspan>'),
    ]
    delays = [0.1, 0.4, 0.6, 0.9, 1.4, 1.6, 1.9, 2.2, 2.6]
    delay_css = "".join(f".l{i + 1}{{animation-delay:{d}s}}" for i, d in enumerate(delays))
    h = 64 + 8 * 26 + 28
    body = "\n  ".join(lines)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 {h}" width="820" height="{h}" role="img" aria-label="warning: this developer is still compiling. Mo Zaid, {e(label)}, now learning {e(title)}. {e(lc_txt)}, {e(pr_txt)}.">
  <style>
    .t{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono","DejaVu Sans Mono",monospace;font-size:16px;fill:#D9DEE0}}
    .w{{fill:#F0955F;font-weight:700}} .b{{fill:#7FA7C9}} .h{{fill:#7FCABF;font-weight:700}}
    .k{{fill:#C792EA}} .ty{{fill:#7FCABF}} .c{{fill:#F0955F}} .m{{fill:#8A969D}}
    .l{{opacity:0;animation:in .35s ease forwards}} {delay_css}
    .cur{{animation:blink 1s steps(1) infinite 3s}}
    @keyframes in{{to{{opacity:1}}}} @keyframes blink{{50%{{opacity:0}}}}
    @media (prefers-reduced-motion: reduce){{.l{{animation:none;opacity:1}} .cur{{animation:none}}}}
  </style>
  <rect width="820" height="{h}" rx="10" fill="#14191C" stroke="#323C42"/>
  <circle cx="24" cy="20" r="5" fill="#E5814C"/><circle cx="42" cy="20" r="5" fill="#C9A227"/><circle cx="60" cy="20" r="5" fill="#2A665F"/>
  <text class="t m" x="790" y="25" text-anchor="end" style="font-size:12px">zairithm — rustc</text>
  {body}
</svg>
'''


# ---------- main ----------
def main():
    now = datetime.now(IST)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    for key, fn in (("leetcode", fetch_leetcode), ("prs", fetch_merged_prs),
                    ("repos", fetch_recent_repos), ("repo_names", fetch_repo_names)):
        try:
            cache[key] = fn()
        except Exception as err:  # keep the last good value if an API is down
            print(f"[warn] {key}: {err}")

    lc, prs, repos = cache.get("leetcode"), cache.get("prs"), cache.get("repos")
    n, phase, title, label = week_info(now)

    old = README.read_text()
    new = ensure_projects_markers(old)
    new = put(new, "PROJECTS", projects_block(cache.get("repo_names"), n))
    new = put(new, "BUILD", build_block(n, phase, title, lc, prs))
    new = put(new, "TESTS", tests_block(lc, prs))
    new = put(new, "RECENT", recent_block(repos, prs, now))
    first_run = "<!--UPDATED:START-->\n<!--UPDATED:END-->" in old
    if first_run or strip_block(new, "UPDATED") != strip_block(old, "UPDATED"):
        new = put(new, "UPDATED", f"<sub>This profile updates itself every morning. Last change: {now:%d %b %Y}.</sub>")
        README.write_text(new)

    BANNER.write_text(banner_svg(n, label, title, lc, prs))
    CACHE.write_text(json.dumps(cache, indent=2))
    print(f"week {n} | {phase} | {title}")


if __name__ == "__main__":
    main()
