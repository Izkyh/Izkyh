#!/usr/bin/env python3
"""
Kartu statistik GitHub yang minimalis -> assets/stats-light.svg & assets/stats-dark.svg

Tanpa layanan pihak ketiga: data diambil langsung dari GitHub GraphQL API.

Env:
  GH_TOKEN          token (GITHUB_TOKEN di Actions, atau PAT agar kontribusi privat ikut dihitung)
  GH_LOGIN          username GitHub
  STATS_TZ          zona waktu IANA untuk menentukan "hari ini" (default: UTC)
  STATS_LANG        en | id (default: en)
  STATS_HIDE_LANGS  bahasa yang tidak ditampilkan, pisahkan koma, mis. "HTML,CSS"

Jalankan dengan --demo untuk merender data contoh tanpa memanggil API.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent.parent / "assets"
API = "https://api.github.com/graphql"

LABELS = {
    "en": dict(
        since="on GitHub since", updated="Updated", commits="Commits",
        contributions="Contributions", current="Current streak", longest="Longest streak",
        in_year="in {y}", all_time="all time", days="days", since_date="since {d}",
        activity="Activity · last 52 weeks", languages="Languages", repos="repos",
        stars="stars", prs="pull requests", other="Other", contribs="contributions",
        months=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        sep=",",
    ),
    "id": dict(
        since="di GitHub sejak", updated="Diperbarui", commits="Commit",
        contributions="Kontribusi", current="Streak saat ini", longest="Streak terpanjang",
        in_year="tahun {y}", all_time="sepanjang waktu", days="hari", since_date="sejak {d}",
        activity="Aktivitas · 52 minggu terakhir", languages="Bahasa", repos="repo",
        stars="bintang", prs="pull request", other="Lainnya", contribs="kontribusi",
        months=["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
        sep=".",
    ),
}

THEMES = {
    "light": dict(bg="#ffffff", ink="#1f2328", muted="#656d76", line="#d0d7de", faint="#eaeef2"),
    "dark": dict(bg="#0d1117", ink="#e6edf3", muted="#8d96a0", line="#30363d", faint="#21262d"),
}
SERIF = "Georgia, 'Iowan Old Style', 'Times New Roman', serif"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
SHADES = [1.0, 0.72, 0.5, 0.34, 0.22, 0.12]


# ---------------------------------------------------------------- data

USER_Q = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name login createdAt
    pullRequests { totalCount }
    repositories(ownerAffiliations: [OWNER], isFork: false, first: 100, after: $cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def gql(query: str, variables: dict, token: str) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "profile-stats-card",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        payload = json.load(r)
    if payload.get("errors"):
        sys.exit("GitHub API error: " + json.dumps(payload["errors"], indent=2))
    return payload["data"]


def iso(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(login: str, token: str, today: dt.date) -> dict:
    profile, cursor, stars, repos_total = None, None, 0, 0
    langs: dict[str, int] = defaultdict(int)
    while True:
        u = gql(USER_Q, {"login": login, "cursor": cursor}, token)["user"]
        if u is None:
            sys.exit(f"User '{login}' tidak ditemukan.")
        profile = profile or u
        repos = u["repositories"]
        repos_total = repos["totalCount"]
        for n in repos["nodes"]:
            stars += n["stargazerCount"]
            for e in n["languages"]["edges"]:
                langs[e["node"]["name"]] += e["size"]
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    created = dt.datetime.fromisoformat(profile["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    years = list(range(created.year, now.year + 1))
    days: dict[dt.date, int] = {}
    commits_by_year: dict[int, int] = {}
    total = 0

    # contributionsCollection maksimal 1 tahun per rentang -> satu alias per tahun
    for i in range(0, len(years), 4):
        chunk = years[i:i + 4]
        parts = []
        for y in chunk:
            start = max(created, dt.datetime(y, 1, 1, tzinfo=dt.timezone.utc))
            end = min(now, dt.datetime(y, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
            parts.append(
                f'y{y}: contributionsCollection(from: "{iso(start)}", to: "{iso(end)}") {{'
                " totalCommitContributions"
                " contributionCalendar { totalContributions"
                " weeks { contributionDays { date contributionCount } } } }"
            )
        q = "query($login: String!) { user(login: $login) { " + " ".join(parts) + " } }"
        u = gql(q, {"login": login}, token)["user"]
        for y in chunk:
            c = u[f"y{y}"]
            commits_by_year[y] = c["totalCommitContributions"]
            total += c["contributionCalendar"]["totalContributions"]
            for w in c["contributionCalendar"]["weeks"]:
                for d in w["contributionDays"]:
                    days[dt.date.fromisoformat(d["date"])] = d["contributionCount"]

    return dict(
        name=profile["name"] or profile["login"], login=profile["login"],
        since=created.year, repos=repos_total, stars=stars,
        prs=profile["pullRequests"]["totalCount"],
        commits_year=commits_by_year.get(today.year, 0),
        total=total, days=days, langs=dict(langs),
    )


def demo(today: dt.date) -> dict:
    rnd = random.Random(7)
    days, d = {}, today - dt.timedelta(days=900)
    while d <= today:
        busy = 0.55 + 0.35 * ((d.toordinal() // 40) % 2)
        days[d] = rnd.choice([1, 2, 3, 4, 6, 9]) if rnd.random() < busy else 0
        d += dt.timedelta(days=1)
    for k in range(17):  # streak yang sedang berjalan
        days[today - dt.timedelta(days=k)] = max(days[today - dt.timedelta(days=k)], 2)
    return dict(
        name="Nama Kamu", login="username", since=2019, repos=24, stars=138, prs=61,
        commits_year=1284, total=sum(days.values()) + 812, days=days,
        langs={"TypeScript": 520_000, "PHP": 210_000, "Python": 140_000,
               "Go": 60_000, "Shell": 22_000, "Dockerfile": 9_000},
    )


# ---------------------------------------------------------------- metrics

def streaks(days: dict[dt.date, int], today: dt.date):
    cur_len, cur_start = 0, None
    d = today if days.get(today, 0) > 0 else today - dt.timedelta(days=1)
    while days.get(d, 0) > 0:
        cur_len, cur_start = cur_len + 1, d
        d -= dt.timedelta(days=1)

    best = (0, None, None)
    run, run_start = 0, None
    for d in sorted(k for k in days if k <= today):
        if days[d] > 0:
            if run == 0 or d - prev != dt.timedelta(days=1):
                run, run_start = 0, d
            run += 1
            if run > best[0]:
                best = (run, run_start, d)
        else:
            run = 0
        prev = d
    return (cur_len, cur_start), best


def weekly(days: dict[dt.date, int], today: dt.date, n: int = 52):
    start = today - dt.timedelta(days=7 * n - 1)
    return [sum(days.get(start + dt.timedelta(days=w * 7 + i), 0) for i in range(7))
            for w in range(n)], start


def top_langs(langs: dict[str, int], hide: set[str], k: int = 5):
    items = sorted(((n, s) for n, s in langs.items() if n.lower() not in hide),
                   key=lambda x: -x[1])
    total = sum(s for _, s in items) or 1
    top = [(n, s / total) for n, s in items[:k]]
    rest = 1 - sum(p for _, p in top)
    if rest > 0.005:
        top.append((None, rest))
    return top


# ---------------------------------------------------------------- render

def num(n: int, L: dict) -> str:
    return f"{n:,}".replace(",", L["sep"])


def date_txt(d: dt.date, L: dict, year: bool = False) -> str:
    s = f"{d.day} {L['months'][d.month - 1]}"
    return f"{s} {d.year}" if year else s


def smooth_path(pts):
    if len(pts) < 2:
        return ""
    p = [f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        mx = (x0 + x1) / 2
        p.append(f"C{mx:.1f},{y0:.1f} {mx:.1f},{y1:.1f} {x1:.1f},{y1:.1f}")
    return " ".join(p)


def render(s: dict, theme: str, L: dict, today: dt.date, hide: set[str]) -> str:
    c = THEMES[theme]
    W, H, P = 840, 352, 36
    out = []
    a = out.append

    (cur, cur_start), (best, best_start, best_end) = streaks(s["days"], today)
    weeks, wk_start = weekly(s["days"], today)
    langs = top_langs(s["langs"], hide)

    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'role="img" aria-labelledby="title">')
    a(f'<title id="title">GitHub stats — {escape(s["login"])}</title>')
    a("<style>"
      f".serif{{font-family:{SERIF};}} .sans{{font-family:{SANS};}}"
      f".ink{{fill:{c['ink']};}} .muted{{fill:{c['muted']};}}"
      f".cap{{font-family:{SANS};font-size:10.5px;font-weight:600;letter-spacing:1.6px;fill:{c['muted']};}}"
      "</style>")
    a(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{c["bg"]}" stroke="{c["line"]}"/>')

    # header
    a(f'<text x="{P}" y="60" class="serif ink" font-size="25">{escape(s["name"])}</text>')
    a(f'<text x="{P}" y="83" class="sans muted" font-size="12.5">@{escape(s["login"])} · '
      f'{L["since"]} {s["since"]}</text>')
    a(f'<text x="{W - P}" y="60" class="sans muted" font-size="11.5" text-anchor="end">'
      f'{L["updated"]} {date_txt(today, L, True)}</text>')
    a(f'<text x="{W - P}" y="83" class="sans muted" font-size="12.5" text-anchor="end">'
      f'{num(s["repos"], L)} {L["repos"]} · {num(s["stars"], L)} {L["stars"]} · '
      f'{num(s["prs"], L)} {L["prs"]}</text>')
    a(f'<line x1="{P}" y1="106.5" x2="{W - P}" y2="106.5" stroke="{c["line"]}"/>')

    # metrics
    if best:
        same_year = best_start.year == best_end.year
        best_sub = f"{date_txt(best_start, L, not same_year)} – {date_txt(best_end, L, True)}"
    else:
        best_sub = "—"
    metrics = [
        (L["commits"], num(s["commits_year"], L), L["in_year"].format(y=today.year)),
        (L["contributions"], num(s["total"], L), L["all_time"]),
        (L["current"], num(cur, L),
         f'{L["days"]} · {L["since_date"].format(d=date_txt(cur_start, L))}' if cur else "—"),
        (L["longest"], num(best, L), f'{L["days"]} · {best_sub}' if best else "—"),
    ]
    col = (W - 2 * P) / 4
    for i, (label, value, sub) in enumerate(metrics):
        x = P + i * col + (22 if i else 0)
        if i:
            a(f'<line x1="{P + i * col:.1f}" y1="128" x2="{P + i * col:.1f}" y2="208" stroke="{c["line"]}"/>')
        a(f'<text x="{x:.1f}" y="139" class="cap">{escape(label.upper())}</text>')
        a(f'<text x="{x:.1f}" y="183" class="serif ink" font-size="36">{value}</text>')
        a(f'<text x="{x:.1f}" y="205" class="sans muted" font-size="11.5">{escape(sub)}</text>')
    a(f'<line x1="{P}" y1="230.5" x2="{W - P}" y2="230.5" stroke="{c["line"]}"/>')

    # activity sparkline
    x0, x1, top, base = P, P + 440, 276, 314
    a(f'<text x="{x0}" y="260" class="cap">{escape(L["activity"].upper())}</text>')
    a(f'<text x="{x1}" y="260" class="sans muted" font-size="11.5" text-anchor="end">'
      f'{num(sum(weeks), L)} {L["contribs"]}</text>')
    peak = max(weeks) or 1
    step = (x1 - x0) / (len(weeks) - 1)
    pts = [(x0 + i * step, base - (v / peak) * (base - top)) for i, v in enumerate(weeks)]
    line = smooth_path(pts)
    a(f'<line x1="{x0}" y1="{base + .5}" x2="{x1}" y2="{base + .5}" stroke="{c["faint"]}"/>')
    a(f'<path d="{line} L{x1},{base} L{x0},{base} Z" fill="{c["ink"]}" fill-opacity="0.06"/>')
    a(f'<path d="{line}" fill="none" stroke="{c["ink"]}" stroke-width="1.6" '
      f'stroke-linecap="round" stroke-linejoin="round"/>')
    lx, ly = pts[-1]
    a(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="{c["bg"]}" stroke="{c["ink"]}" stroke-width="1.6"/>')
    a(f'<text x="{x0}" y="334" class="sans muted" font-size="10.5">{date_txt(wk_start, L, True)}</text>')
    a(f'<text x="{x1}" y="334" class="sans muted" font-size="10.5" text-anchor="end">'
      f'{date_txt(today, L, True)}</text>')

    # languages
    lx0, lx1 = x1 + 56, W - P
    a(f'<text x="{lx0}" y="260" class="cap">{escape(L["languages"].upper())}</text>')
    if langs:
        bw, gap, x = lx1 - lx0, 2, lx0
        a(f'<clipPath id="bar"><rect x="{lx0}" y="272" width="{bw}" height="6" rx="3"/></clipPath>')
        a('<g clip-path="url(#bar)">')
        for i, (_, p) in enumerate(langs):
            w = bw * p
            a(f'<rect x="{x:.1f}" y="272" width="{max(w - gap, 1):.1f}" height="6" '
              f'fill="{c["ink"]}" fill-opacity="{SHADES[i]}"/>')
            x += w
        a("</g>")
        cw = (lx1 - lx0 - 20) / 2
        for i, (name, p) in enumerate(langs):
            cx = lx0 + (i // 3) * (cw + 20)
            cy = 299 + (i % 3) * 18
            label = name or L["other"]
            a(f'<circle cx="{cx + 3.5:.1f}" cy="{cy - 4}" r="3.5" fill="{c["ink"]}" fill-opacity="{SHADES[i]}"/>')
            a(f'<text x="{cx + 13:.1f}" y="{cy}" class="sans ink" font-size="12">{escape(label)}</text>')
            a(f'<text x="{cx + cw:.1f}" y="{cy}" class="sans muted" font-size="12" text-anchor="end">'
              f'{p * 100:.0f}%</text>')
    else:
        a(f'<text x="{lx0}" y="296" class="sans muted" font-size="12">—</text>')

    a("</svg>")
    return "\n".join(out)


def main() -> None:
    lang = os.environ.get("STATS_LANG", "en").lower()
    L = LABELS.get(lang, LABELS["en"])
    today = dt.datetime.now(ZoneInfo(os.environ.get("STATS_TZ", "UTC"))).date()
    hide = {h.strip().lower() for h in os.environ.get("STATS_HIDE_LANGS", "").split(",") if h.strip()}

    if "--demo" in sys.argv:
        stats = demo(today)
    else:
        token, login = os.environ.get("GH_TOKEN"), os.environ.get("GH_LOGIN")
        if not token or not login:
            sys.exit("Set GH_TOKEN dan GH_LOGIN (atau jalankan dengan --demo).")
        stats = fetch(login, token, today)

    OUT.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        (OUT / f"stats-{theme}.svg").write_text(render(stats, theme, L, today, hide), encoding="utf-8")
    print(f"OK -> {OUT}/stats-light.svg, stats-dark.svg")


if __name__ == "__main__":
    main()
