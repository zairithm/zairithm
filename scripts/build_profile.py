#!/usr/bin/env python3
"""Builds the profile cards in ./cards and refreshes the README.

Runs daily from GitHub Actions (and can be run by hand: python scripts/build_profile.py).

cards/hero.svg           name, role, one line about me, stack chips, photo or monogram
cards/contributions.svg  last 12 months of contributions with streaks, drawn from the GitHub API
cards/stack.svg          tools I use
cards/repo-N.svg         one card per public repository (up to 3); none until a repo is public

Every card carries its own dark and light colours and follows the viewer's theme.
Numbers that are still zero are left out rather than shown.
To use a photo instead of the "MZ" monogram, add assets/photo.jpg (square works best).
"""
import base64
import html
import json
import os
import re
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CARDS = ROOT / "cards"
DATA = ROOT / "data" / "profile.json"
PHOTO = ROOT / "assets" / "photo.jpg"

USER = os.environ.get("GH_USER", "zairithm")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

NAME = "Mo Zaid"
ROLE = "Rust Developer"
ABOUT = "I build backend apps and Solana projects in Rust."
PLACE = "Aligarh, India"
CHIPS = ["Rust", "Tokio", "Axum", "Solana", "Anchor"]
STACK = [
    ("Rust", ["Rust", "Cargo", "Tokio", "Axum", "Serde", "Solana", "Anchor"]),
    ("Also", ["Python", "PyTorch", "Solidity", "C++", "Git", "Linux"]),
]

W = 840
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,'Cascadia Code',Menlo,Consolas,monospace"

# One palette, two themes. Accent is a deep rust orange.
THEME = f"""
  .bg{{fill:#0E1013}} .line{{stroke:#24282E}} .fg{{fill:#ECEEF1}} .mute{{fill:#8B929B}} .acc{{fill:#F0663A}}
  .chip{{fill:#171A1F;stroke:#2A2F36}} .ring{{stroke:#F0663A}} .mono{{fill:#1B1F25}}
  .c0{{fill:#171A1F}} .c1{{fill:#5A2A1C}} .c2{{fill:#9A3F22}} .c3{{fill:#D2552C}} .c4{{fill:#FF8A5C}}
  .sans{{font-family:{SANS}}} .code{{font-family:{MONO}}}
  @media (prefers-color-scheme: light){{
    .bg{{fill:#FFFFFF}} .line{{stroke:#E3E6EA}} .fg{{fill:#14171A}} .mute{{fill:#5F6670}} .acc{{fill:#C8461D}}
    .chip{{fill:#F5F6F8;stroke:#E1E4E8}} .ring{{stroke:#C8461D}} .mono{{fill:#F2F3F5}}
    .c0{{fill:#EEF0F2}} .c1{{fill:#F9D3C3}} .c2{{fill:#F2A07E}} .c3{{fill:#E06A3E}} .c4{{fill:#B63E16}}
  }}
  .rise{{opacity:0;animation:rise .6s ease-out forwards}}
  @keyframes rise{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
  @media (prefers-reduced-motion: reduce){{.rise{{animation:none;opacity:1}}}}
"""

e = html.escape


# ---------- data ----------
def request(url, body=None):
    h = {"User-Agent": f"{USER}-profile", "Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_calendar():
    q = """query($u:String!){ user(login:$u){ contributionsCollection{ contributionCalendar{
          totalContributions weeks{ contributionDays{ date contributionCount contributionLevel } } } } } }"""
    d = request("https://api.github.com/graphql", {"query": q, "variables": {"u": USER}})
    cal = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[{"date": x["date"], "n": x["contributionCount"], "lvl": x["contributionLevel"]}
              for x in w["contributionDays"]] for w in cal["weeks"]]
    return {"total": cal["totalContributions"], "weeks": weeks}


def fetch_repos():
    out = []
    for r in request(f"https://api.github.com/users/{USER}/repos?sort=pushed&per_page=100"):
        if r.get("fork") or r.get("archived") or r["name"].lower() == USER.lower():
            continue
        out.append({"name": r["name"], "url": r["html_url"], "desc": (r.get("description") or "").strip(),
                    "lang": r.get("language") or "", "stars": r["stargazers_count"], "pushed": r["pushed_at"]})
    out.sort(key=lambda r: r["pushed"], reverse=True)   # newest first...
    out.sort(key=lambda r: r["stars"], reverse=True)    # ...then most-starred on top (stable sort)
    return out


# ---------- helpers ----------
def text_w(s, size, mono=False):
    """Rough text width, good enough to size chips."""
    return len(s) * size * (0.6 if mono else 0.56)


def chip_row(items, x, y, size=13, mono=True, gap=8, cls="rise", delay0=0.0):
    out, cx = [], x
    for i, it in enumerate(items):
        w = text_w(it, size, mono) + 22
        out.append(
            f'<g class="{cls}" style="animation-delay:{delay0 + i * 0.05:.2f}s">'
            f'<rect class="chip" x="{cx:.0f}" y="{y}" width="{w:.0f}" height="28" rx="6"/>'
            f'<text class="fg {"code" if mono else "sans"}" x="{cx + 11:.0f}" y="{y + 18.5}" font-size="{size}">{e(it)}</text></g>')
        cx += w + gap
    return "".join(out)


def wrap(s, width, lines):
    words, out, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1][: width - 1].rstrip() + "…"
    return out


def svg(w, h, label, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{e(label)}"><title>{e(label)}</title><style>{THEME}</style>'
            f'<rect class="bg line" x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" stroke-width="1"/>'
            f'{body}</svg>\n')


# ---------- cards ----------
def hero_card():
    h = 230
    cx, cy, r = W - 120, h / 2, 70
    if PHOTO.exists():
        b64 = base64.b64encode(PHOTO.read_bytes()).decode()
        face = (f'<clipPath id="p"><circle cx="{cx}" cy="{cy}" r="{r - 6}"/></clipPath>'
                f'<image href="data:image/jpeg;base64,{b64}" x="{cx - r + 6}" y="{cy - r + 6}" '
                f'width="{2 * r - 12}" height="{2 * r - 12}" clip-path="url(#p)" preserveAspectRatio="xMidYMid slice"/>')
    else:
        initials = "".join(p[0] for p in NAME.split()[:2]).upper()
        face = (f'<circle class="mono" cx="{cx}" cy="{cy}" r="{r - 6}"/>'
                f'<text class="fg sans" x="{cx}" y="{cy + 15}" font-size="42" font-weight="600" '
                f'text-anchor="middle" letter-spacing="1">{e(initials)}</text>')
    body = f"""
  <text class="code rise" x="40" y="52" font-size="12" letter-spacing="2.5"><tspan class="acc">{e(ROLE.upper())}</tspan><tspan class="mute">  ·  {e(PLACE.upper())}</tspan></text>
  <text class="fg sans rise" x="38" y="106" font-size="46" font-weight="700" letter-spacing="-1" style="animation-delay:.1s">{e(NAME)}</text>
  <text class="mute sans rise" x="40" y="140" font-size="17" style="animation-delay:.2s">{e(ABOUT)}</text>
  {chip_row(CHIPS, 40, 166, delay0=.3)}
  <g class="rise" style="animation-delay:.15s">
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" class="ring" stroke-width="2" stroke-dasharray="6 6" opacity=".55"/>
    {face}
  </g>"""
    return svg(W, h, f"{NAME}, {ROLE} from {PLACE}. {ABOUT}", body)


def streaks(days):
    today = date.today()
    days = [d for d in days if date.fromisoformat(d["date"]) <= today]
    longest = run = 0
    for d in days:
        run = run + 1 if d["n"] else 0
        longest = max(longest, run)
    current = 0
    for i, d in enumerate(reversed(days)):
        if d["n"]:
            current += 1
        elif i == 0:  # today with nothing yet does not break the streak
            continue
        else:
            break
    best = max(days, key=lambda d: d["n"]) if days else None
    return current, longest, best


def contributions_card(cal):
    weeks = cal["weeks"][-53:]
    cell, gap = 11, 3
    step = cell + gap
    gx, gy = (W - len(weeks) * step + gap) / 2, 78
    lvl = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
    cols, months, last_m = [], [], None
    for i, wk in enumerate(weeks):
        x = gx + i * step
        first = date.fromisoformat(wk[0]["date"])
        if first.month != last_m and first.day <= 7 and i < len(weeks) - 2:
            months.append(f'<text class="mute code" x="{x:.1f}" y="{gy - 10}" font-size="10">{first:%b}</text>')
            last_m = first.month
        rects = []
        for d in wk:
            row = date.fromisoformat(d["date"]).isoweekday() % 7  # Sunday on top, like GitHub
            rects.append(f'<rect class="c{lvl.get(d["lvl"], 0)}" x="{x:.1f}" y="{gy + row * step}" '
                         f'width="{cell}" height="{cell}" rx="2.5"><title>{d["n"]} on {d["date"]}</title></rect>')
        # columns sweep in left to right
        cols.append(f'<g class="rise" style="animation-delay:{i * 0.018:.3f}s">{"".join(rects)}</g>')

    days = [d for wk in weeks for d in wk]
    current, longest, best = streaks(days)
    total = cal["total"]
    stats = []
    if total:
        stats.append(("Contributions", f"{total:,}"))
    if current:
        stats.append(("Current streak", f"{current} day{'s' if current != 1 else ''}"))
    if longest > 1:
        stats.append(("Longest streak", f"{longest} days"))
    if best and best["n"] > 1:
        stats.append(("Busiest day", f"{best['n']} on {date.fromisoformat(best['date']):%d %b}"))

    sy = gy + 7 * step + 34
    legend_x = W - 40 - 5 * 15 - 70
    legend = (f'<text class="mute code" x="{legend_x}" y="{sy - 14}" font-size="10">Less</text>'
              + "".join(f'<rect class="c{k}" x="{legend_x + 32 + k * 15}" y="{sy - 23}" width="11" height="11" rx="2.5"/>'
                        for k in range(5))
              + f'<text class="mute code" x="{legend_x + 32 + 5 * 15 + 4}" y="{sy - 14}" font-size="10">More</text>')
    stat_svg = ""
    if stats:
        col_w = (W - 80) / len(stats)
        for i, (k, v) in enumerate(stats):
            x = 40 + i * col_w
            stat_svg += (f'<g class="rise" style="animation-delay:{1.0 + i * 0.1:.1f}s">'
                         f'<text class="mute code" x="{x:.0f}" y="{sy + 22}" font-size="10" letter-spacing="1.5">{e(k.upper())}</text>'
                         f'<text class="fg sans" x="{x:.0f}" y="{sy + 48}" font-size="22" font-weight="600">{e(v)}</text></g>')
        h = sy + 74
    else:
        h = sy + 10
    body = (f'<text class="acc code" x="40" y="40" font-size="12" letter-spacing="2.5">CONTRIBUTIONS</text>'
            f'<text class="mute code" x="{W - 40}" y="40" font-size="12" text-anchor="end">last 12 months</text>'
            + "".join(months) + "".join(cols) + legend
            + (f'<line class="line" x1="40" x2="{W - 40}" y1="{sy}" y2="{sy}" stroke-width="1"/>' if stats else "")
            + stat_svg)
    label = "Contribution graph for the last 12 months. " + ". ".join(f"{k}: {v}" for k, v in stats)
    return svg(W, int(h), label, body)


def stack_card():
    rows, y = [], 70
    for i, (label, items) in enumerate(STACK):
        rows.append(f'<text class="mute code rise" x="40" y="{y + 18.5}" font-size="11" letter-spacing="1.5" '
                    f'style="animation-delay:{i * .15:.2f}s">{e(label.upper())}</text>')
        rows.append(chip_row(items, 120, y, delay0=i * .15 + .05))
        y += 44
    body = '<text class="acc code" x="40" y="40" font-size="12" letter-spacing="2.5">STACK</text>' + "".join(rows)
    label = "Stack. " + ". ".join(f"{k}: {', '.join(v)}" for k, v in STACK)
    return svg(W, y + 18, label, body)


def repo_card(r, i):
    w, h = 272, 160
    lines = wrap(r["desc"] or "No description yet.", 34, 3)
    desc = "".join(f'<text class="mute sans" x="22" y="{78 + j * 20}" font-size="13">{e(t)}</text>' for j, t in enumerate(lines))
    meta = " · ".join(x for x in [r["lang"], f"★ {r['stars']}" if r["stars"] else ""] if x)
    name = r["name"] if len(r["name"]) <= 24 else r["name"][:23] + "…"
    body = (f'<g class="rise" style="animation-delay:{i * .1:.1f}s">'
            f'<text class="acc code" x="22" y="32" font-size="11" letter-spacing="2">{i + 1:02d}</text>'
            f'<text class="fg sans" x="22" y="56" font-size="18" font-weight="600">{e(name)}</text>{desc}'
            f'<text class="mute code" x="22" y="{h - 20}" font-size="11">{e(meta)}</text></g>')
    return svg(w, h, f"{r['name']}: {r['desc']}", body)


# ---------- readme ----------
def put(text, key, content):
    pat = re.compile(rf"(<!--{key}:START-->)(.*?)(<!--{key}:END-->)", re.S)
    return pat.sub(lambda m: f"{m.group(1)}{content}{m.group(3)}", text)


def main():
    CARDS.mkdir(exist_ok=True)
    DATA.parent.mkdir(exist_ok=True)
    data = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {}
    for key, fn in (("calendar", fetch_calendar), ("repos", fetch_repos)):
        try:
            data[key] = fn()
        except Exception as err:  # keep the last good copy if the API is down
            print(f"[warn] {key}: {err}")
    DATA.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")

    (CARDS / "hero.svg").write_text(hero_card(), encoding="utf-8")
    (CARDS / "stack.svg").write_text(stack_card(), encoding="utf-8")
    if data.get("calendar"):
        (CARDS / "contributions.svg").write_text(contributions_card(data["calendar"]), encoding="utf-8")

    repos = (data.get("repos") or [])[:3]
    for old in CARDS.glob("repo-*.svg"):
        old.unlink()
    imgs = []
    for i, r in enumerate(repos):
        (CARDS / f"repo-{i + 1}.svg").write_text(repo_card(r, i), encoding="utf-8")
        imgs.append(f'<a href="{r["url"]}"><img src="./cards/repo-{i + 1}.svg" width="32.4%" '
                    f'alt="{e(r["name"])}: {e(r["desc"])}" /></a>')
    readme = README.read_text(encoding="utf-8")
    readme = put(readme, "REPOS", ("\n" + "".join(imgs) + "<br>\n") if imgs else "")
    README.write_text(readme, encoding="utf-8")
    print(f"cards built; {len(repos)} repo cards; {data.get('calendar', {}).get('total', 0)} contributions")


if __name__ == "__main__":
    main()
