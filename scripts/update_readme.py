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
def stats_bits(lc, prs):
    """Only real numbers. A zero is left out instead of shown on the profile."""
    bits = []
    if lc and lc.get("total"):
        bits.append(f"{lc['total']} leetcode solved")
    if prs and prs.get("count"):
        bits.append(f"{prs['count']} PR{'s' if prs['count'] != 1 else ''} merged upstream")
    return bits


def build_block(n, phase, title, lc, prs):
    lines = ["```console", "$ cargo build --release -p zaid"]
    if n <= TOTAL_WEEKS:
        filled = round(n / TOTAL_WEEKS * 28)
        bar = ("=" * max(filled - 1, 0) + ">").ljust(28)
        lines.append(f"   Compiling rust v0.{n}.0 (roadmap week {n} of {TOTAL_WEEKS})")
        lines.append(f"    Building [{bar}] {phase}: {title}")
        if n < TOTAL_WEEKS:
            lines.append(f"        Next week {n + 1}: {WEEKS[n]}")
    else:
        lines.append(f"   Compiling rust v1.0.0 ({phase})")
        lines.append(f"    Building {title}")
    bits = stats_bits(lc, prs)
    if bits:
        lines.append(f"    Finished {', '.join(bits)}")
    lines.append("```")
    return "\n".join(lines)


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


UPCOMING_SHOWN = 3   # planned Rust projects listed by name; the rest are summed up in one line


def project_row(p, names, n):
    repo, week = p["repo"], p.get("week", 0)
    have = {x.lower() for x in (names or [])}
    if repo.lower() in have:
        name, status = f"[**{repo}**](https://github.com/{USER}/{repo})", "✅ live"
    elif names is None:
        name, status = f"**{repo}**", "⏳ syncing"
    elif not week:
        name, status = f"**{repo}**", "⏳ code coming soon"
    elif week <= n:
        name, status = f"**{repo}**", "🔨 building now"
    elif week > TOTAL_WEEKS:
        name, status = f"**{repo}**", "🗓️ summer 2027"
    else:
        name, status = f"**{repo}**", f"🗓️ week {week}"
    if p.get("demo"):
        status += f" · [demo]({p['demo']})"
    return f"| {p.get('emoji', '')} | {name} | {p['about']} | {status} |"


def projects_block(names, n):
    if not PROJECTS.exists():
        return ""
    items = json.loads(PROJECTS.read_text())
    have = {x.lower() for x in (names or [])}
    head = ["| | Project | What it does | Status |", "|---|---|---|---|"]

    rust = sorted((p for p in items if p.get("week", 0)), key=lambda p: p["week"])
    earlier = [p for p in items if not p.get("week", 0)]

    # started or live first, then only the next few planned ones
    shown = [p for p in rust if p["week"] <= n or p["repo"].lower() in have]
    planned = [p for p in rust if p not in shown]
    shown += planned[:UPCOMING_SHOWN]
    rest = planned[UPCOMING_SHOWN:]

    out = ["### 🦀 Rust", ""] + head + [project_row(p, names, n) for p in shown]
    if rest:
        later = ", ".join(f"`{p['repo']}`" for p in rest)
        out += ["", f"<sub>Later on the roadmap: {later}.</sub>"]
    if earlier:
        out += ["", "### 🧠 AI/ML and Web3", ""] + head + [project_row(p, names, n) for p in earlier]
    return "\n".join(out)


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
    return "\n".join(out) if out else "_First public Rust repositories are on the way._"


def banner_svg(n, label, title, lc, prs):
    e = html.escape
    title = title if len(title) <= 40 else title[:39] + "…"
    now_txt = f"{label}: {title}" if n <= TOTAL_WEEKS else title
    bits = stats_bits(lc, prs)

    def kv(key, value):
        return f'<tspan class="b">  {key:<10}</tspan> {value}'

    sep = ' <tspan class="m">·</tspan> '
    rows = [
        ('<tspan class="m">zaid@rust:~$</tspan> cargo run --release', ""),
        ('<tspan class="h">    Finished</tspan> `release` profile [optimized] target(s)', ""),
        ('<tspan class="h">     Running</tspan> `target/release/zaid`', ""),
        ("", ""),
        ('<tspan class="n">Mo Zaid</tspan>  <tspan class="c">Rust developer</tspan>', " n"),
        (kv("backend", sep.join(["tokio", "axum"])), ""),
        (kv("on-chain", sep.join(["solana", "anchor"])), ""),
        (kv("also", sep.join(["python", "pytorch", "solidity"])), ""),
        (kv("now", e(now_txt)), ""),
    ]
    if bits:
        rows.append((kv("stats", sep.join(e(b) for b in bits)), ""))
    rows.append(('<tspan class="m">zaid@rust:~$</tspan> <tspan class="cur">█</tspan>', ""))

    lines, y = [], 64
    for i, (inner, extra) in enumerate(rows, 1):
        y += 8 if extra else 0          # a little air around the name line
        lines.append(f'<text xml:space="preserve" class="t l l{i}{extra}" x="28" y="{y}">{inner}</text>')
        y += 26 + (8 if extra else 0)
    delay_css = "".join(f".l{i}{{animation-delay:{0.1 + (i - 1) * 0.22:.2f}s}}" for i in range(1, len(rows) + 1))
    h = y + 2
    body = "\n  ".join(lines)
    aria = f"Mo Zaid, Rust developer. Backend with Tokio and Axum, on-chain with Solana and Anchor, also Python, PyTorch and Solidity. Now: {e(now_txt)}."
    if bits:
        aria += " " + e(", ".join(bits)) + "."
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 {h}" width="820" height="{h}" role="img" aria-label="{aria}">
  <style>
    .t{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono","DejaVu Sans Mono",monospace;font-size:16px;fill:#D9DEE0}}
    .n{{fill:#FFFFFF;font-weight:700;font-size:22px}}
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
