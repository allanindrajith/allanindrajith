#!/usr/bin/env python3
"""Generate self-hosted Pixel Studio SVG assets for GitHub profile README.

Zero external dependencies (Python 3.9+ stdlib only).
Pulls live GitHub profile, commits, repos, and contribution calendar via GitHub API,
plus live Vilnius/Lithuania weather via Open-Meteo.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html
import json
import math
import os
import subprocess
import sys
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

USERNAME = os.environ.get("GITHUB_USERNAME", "allanindrajith")
FEATURED_REPOS = ["hivework", "code-clinic", "FinTrack", "taptale"]
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "pixel-studio"

# Vilnius, Lithuania coordinates
LAT = 54.6872
LON = 25.2797
TZ = ZoneInfo("Europe/Vilnius")

# 5x7 crisp bitmap pixel font (uppercase, digits, symbols)
FONT_5X7: dict[str, list[str]] = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10011", "10101", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["01110", "10000", "11110", "10001", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    ">": ["10000", "01000", "00100", "00010", "00100", "01000", "10000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
}

LANG_META: dict[str, tuple[str, str, str]] = {
    "TypeScript": ("#3178c6", "#162d47", "TS"),
    "JavaScript": ("#f1e05a", "#3a3312", "JS"),
    "Python": ("#3572a5", "#16293d", "PY"),
    "Swift": ("#f05138", "#3d1a14", "SW"),
    "Rust": ("#dea584", "#38261c", "RS"),
    "Svelte": ("#ff3e00", "#3d170b", "SV"),
    "HTML": ("#e34c26", "#381810", "HT"),
    "CSS": ("#563d7c", "#211830", "CS"),
    "Go": ("#00add8", "#0c2d38", "GO"),
    "Shell": ("#89e051", "#1d3313", "SH"),
}


def get_github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    try:
        out = subprocess.check_output(["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL)
        return out.strip()
    except Exception:
        return ""


def http_json(url: str, headers: dict[str, str] | None = None, payload: dict | None = None) -> dict | list:
    req_headers = {"User-Agent": "pixel-studio-readme-generator"}
    if headers:
        req_headers.update(headers)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=req_headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_bytes(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "pixel-studio-readme-generator"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        ctype = resp.headers.get("Content-Type", "image/png").split(";")[0].strip()
        return resp.read(), ctype


def fetch_github_data(token: str) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    query = """
    query($login: String!) {
      user(login: $login) {
        name
        login
        bio
        websiteUrl
        location
        avatarUrl(size: 160)
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
          totalCount
          nodes {
            name
            description
            stargazerCount
            url
            isPrivate
            primaryLanguage { name color }
            languages(first: 6, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name color } }
            }
          }
        }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
      }
    }
    """
    gql = http_json(
        "https://api.github.com/graphql",
        headers={**headers, "Content-Type": "application/json"},
        payload={"query": query, "variables": {"login": USERNAME}},
    )
    user = gql["data"]["user"]

    # Fetch recent public push commits for the scrolling monitor
    commits: list[str] = []
    try:
        events = http_json(f"https://api.github.com/users/{USERNAME}/events/public?per_page=30", headers=headers)
        for ev in events:
            if ev.get("type") == "PushEvent":
                repo_name = ev.get("repo", {}).get("name", "").split("/")[-1]
                for c in ev.get("payload", {}).get("commits", []):
                    msg = (c.get("message") or "").splitlines()[0].strip()
                    if msg:
                        commits.append(f"{repo_name}: {msg}")
    except Exception:
        pass

    # Fallback: fetch latest commits from top recently updated public repos
    if len(commits) < 6:
        public_repos = [r for r in user["repositories"]["nodes"] if not r.get("isPrivate")]
        for r in public_repos[:6]:
            if len(commits) >= 8:
                break
            try:
                rc = http_json(
                    f"https://api.github.com/repos/{USERNAME}/{r['name']}/commits?per_page=2",
                    headers=headers,
                )
                for item in rc:
                    msg = (item.get("commit", {}).get("message") or "").splitlines()[0].strip()
                    if msg:
                        line = f"{r['name']}: {msg}"
                        if line not in commits:
                            commits.append(line)
            except Exception:
                continue

    if not commits:
        commits = [f"{USERNAME}: shipping clean code"]

    return {"user": user, "commits": commits[:8]}


def fetch_weather() -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&current=temperature_2m,weather_code,is_day"
        f"&timezone=Europe%2FVilnius"
    )
    try:
        data = http_json(url)
        cur = data.get("current", {})
        return {
            "temp": cur.get("temperature_2m", 5),
            "code": int(cur.get("weather_code", 2)),
            "is_day": bool(cur.get("is_day", 0)),
        }
    except Exception:
        now = dt.datetime.now(TZ)
        return {"temp": 4, "code": 2, "is_day": 7 <= now.hour < 19}


def compute_streaks(weeks: list[dict]) -> tuple[int, int]:
    days = [d for w in weeks for d in w["contributionDays"]]
    best = 0
    run = 0
    for d in days:
        if d["contributionCount"] > 0:
            run += 1
            best = max(best, run)
        else:
            run = 0

    # Current streak (allow today to be 0 if yesterday had contributions)
    cur = 0
    idx = len(days) - 1
    if idx >= 0 and days[idx]["contributionCount"] == 0:
        idx -= 1
    while idx >= 0 and days[idx]["contributionCount"] > 0:
        cur += 1
        idx -= 1
    return cur, best


def render_pixel_text(text: str, x: float, y: float, scale: int, fill: str, letter_gap: int = 1) -> tuple[str, float]:
    rects: list[str] = []
    cx = x
    for ch in text.upper():
        glyph = FONT_5X7.get(ch, FONT_5X7[" "])
        gw = len(glyph[0])
        for row_i, row in enumerate(glyph):
            for col_i, bit in enumerate(row):
                if bit == "1":
                    rx = cx + col_i * scale
                    ry = y + row_i * scale
                    rects.append(f'<rect x="{rx}" y="{ry}" width="{scale}" height="{scale}" fill="{fill}"/>')
        cx += (gw + letter_gap) * scale
    total_w = max(0.0, cx - x - letter_gap * scale)
    return "\n".join(rects), total_w


def measure_pixel_text(text: str, scale: int, letter_gap: int = 1) -> float:
    w = 0
    for ch in text.upper():
        glyph = FONT_5X7.get(ch, FONT_5X7[" "])
        w += (len(glyph[0]) + letter_gap) * scale
    return max(0.0, w - letter_gap * scale)


def build_desk_hero(user: dict, commits: list[str], weather: dict) -> str:
    w, h = 900, 410
    now = dt.datetime.now(TZ)
    is_day = weather["is_day"]
    wcode = weather["code"]
    is_rain = wcode in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    is_snow = wcode in {71, 73, 75, 77, 85, 86}
    is_cloudy = wcode in {2, 3, 45, 48} or is_rain or is_snow

    # Aggregate top languages for bookshelf books
    lang_sizes: dict[str, tuple[int, str]] = {}
    for repo in user["repositories"]["nodes"]:
        if repo.get("isPrivate"):
            continue
        for edge in repo.get("languages", {}).get("edges", []):
            lname = edge["node"]["name"]
            lcolor = edge["node"].get("color") or LANG_META.get(lname, ("#58a6ff", "", ""))[0]
            prev = lang_sizes.get(lname, (0, lcolor))[0]
            lang_sizes[lname] = (prev + edge["size"], lcolor)
    top_langs = sorted(lang_sizes.items(), key=lambda kv: kv[1][0], reverse=True)[:5]
    if not top_langs:
        top_langs = [("TypeScript", (50, "#3178c6")), ("JavaScript", (30, "#f1e05a")), ("Python", (20, "#3572a5"))]

    # Wallpaper stripes
    stripes = []
    for sx in range(0, w, 36):
        stripes.append(f'<rect x="{sx}" y="0" width="18" height="316" fill="#1a2238"/>')

    # Window sky
    sky_top = "#4b7ec9" if is_day else "#0d1424"
    sky_bot = "#7ba7e0" if is_day else "#151e34"
    window_fx = []
    if is_day:
        # Pixel sun
        window_fx.append('<rect x="196" y="72" width="24" height="24" fill="#f7d560"/>')
        window_fx.append('<rect x="200" y="68" width="16" height="32" fill="#f7d560"/>')
        window_fx.append('<rect x="192" y="76" width="32" height="16" fill="#f7d560"/>')
    else:
        # Pixel crescent moon + stars
        window_fx.append('<rect x="202" y="72" width="10" height="24" fill="#f4eed7"/>')
        window_fx.append('<rect x="202" y="88" width="22" height="8" fill="#f4eed7"/>')
        for sx, sy, op in [(74, 70, 0.8), (94, 88, 0.5), (144, 76, 0.9), (168, 108, 0.6), (86, 126, 0.7), (180, 74, 0.8)]:
            window_fx.append(f'<rect class="twinkle" x="{sx}" y="{sy}" width="4" height="4" fill="#dce6ff" opacity="{op}"/>')

    if is_cloudy:
        cloud_fill = "#cbd5e1" if is_day else "#475569"
        cloud_hi = "#e2e8f0" if is_day else "#64748b"
        window_fx.append(
            f'<g class="cloud">'
            f'<rect x="116" y="84" width="40" height="12" fill="{cloud_fill}"/>'
            f'<rect x="124" y="78" width="24" height="8" fill="{cloud_hi}"/>'
            f'<rect x="70" y="114" width="32" height="10" fill="{cloud_fill}"/>'
            f'<rect x="76" y="108" width="20" height="8" fill="{cloud_hi}"/>'
            f'<rect x="182" y="108" width="44" height="12" fill="{cloud_fill}"/>'
            f'<rect x="190" y="102" width="26" height="8" fill="{cloud_hi}"/>'
            f"</g>"
        )

    if is_rain:
        for rx, ry in [(80, 128), (112, 102), (144, 120), (196, 126), (222, 114)]:
            window_fx.append(f'<rect class="rain" x="{rx}" y="{ry}" width="3" height="10" fill="#60a5fa"/>')
    elif is_snow:
        for rx, ry in [(82, 128), (116, 104), (148, 122), (196, 126), (220, 114)]:
            window_fx.append(f'<rect class="rain" x="{rx}" y="{ry}" width="4" height="4" fill="#f8fafc"/>')

    # Wall name plaque
    name_str = (user.get("name") or USERNAME).upper()
    name_scale = 4
    name_w = measure_pixel_text(name_str, name_scale, letter_gap=1)
    plaque_w = max(310, int(name_w) + 36)
    plaque_x = (w - plaque_w) // 2
    name_svg, _ = render_pixel_text(name_str, plaque_x + (plaque_w - name_w) / 2, 46, name_scale, "#1e1b18", letter_gap=1)

    # Wall clock (real Vilnius time)
    cx, cy = 748, 66
    hour_angle = math.radians(((now.hour % 12) + now.minute / 60.0) * 30.0 - 90.0)
    min_angle = math.radians(now.minute * 6.0 - 90.0)
    hx = cx + math.cos(hour_angle) * 12
    hy = cy + math.sin(hour_angle) * 12
    mx = cx + math.cos(min_angle) * 18
    my = cy + math.sin(min_angle) * 18

    # Bookshelf books (top shelf)
    books_svg = []
    bx = 678
    book_heights = [40, 44, 48, 42, 36]
    book_widths = [24, 20, 22, 18, 16]
    for i, (lname, (_, lcolor)) in enumerate(top_langs):
        bw = book_widths[i % len(book_widths)]
        bh = book_heights[i % len(book_heights)]
        by = 172 - bh
        books_svg.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" fill="{lcolor}"/>')
        books_svg.append(f'<rect x="{bx}" y="{by}" width="3" height="{bh}" fill="#ffffff" opacity="0.22"/>')
        books_svg.append(f'<rect x="{bx + bw - 3}" y="{by}" width="3" height="{bh}" fill="#000000" opacity="0.25"/>')
        books_svg.append(f'<rect x="{bx + 3}" y="{by + 7}" width="{bw - 6}" height="3" fill="#ffffff" opacity="0.3"/>')
        books_svg.append(f'<title>{html.escape(lname)}</title>')
        bx += bw + 4

    # Scrolling commits on monitor
    commit_lines = commits[:6] + ["$ git log --oneline"] + commits[:3]
    term_rows = []
    for idx, line in enumerate(commit_lines):
        short = line if len(line) <= 34 else line[:33] + "…"
        is_cmd = short.startswith("$ ")
        col = "#a7f3d0" if is_cmd else ("#7dd3fc" if idx % 2 == 0 else "#cbd5e1")
        term_rows.append(
            f'<text x="348" y="{134 + idx * 17}" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" '
            f'font-size="11" fill="{col}">{html.escape(short)}</text>'
        )

    # Floor planks
    floor_svg = ['<rect x="0" y="316" width="900" height="94" fill="#3a2518"/>']
    for fy in (316, 336, 360, 386):
        floor_svg.append(f'<rect x="0" y="{fy}" width="900" height="3" fill="#26170e"/>')
    floor_svg.append('<rect x="0" y="308" width="900" height="8" fill="#4b3121"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" shape-rendering="crispEdges">
  <defs>
    <clipPath id="screen-clip"><rect x="340" y="114" width="228" height="122" rx="2"/></clipPath>
    <clipPath id="win-clip"><rect x="64" y="60" width="184" height="120"/></clipPath>
    <clipPath id="hero-round"><rect x="0" y="0" width="{w}" height="{h}" rx="12"/></clipPath>
    <linearGradient id="sky-grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{sky_top}"/>
      <stop offset="100%" stop-color="{sky_bot}"/>
    </linearGradient>
    <style>
      @keyframes scrollLog {{
        0% {{ transform: translateY(0px); }}
        100% {{ transform: translateY(-96px); }}
      }}
      @keyframes floatZ {{
        0%, 100% {{ transform: translateY(0px); opacity: 0.25; }}
        50% {{ transform: translateY(-8px); opacity: 0.9; }}
      }}
      @keyframes steam {{
        0%, 100% {{ transform: translateY(0px); opacity: 0.25; }}
        50% {{ transform: translateY(-6px); opacity: 0.7; }}
      }}
      @keyframes drift {{
        0%, 100% {{ transform: translateX(0px); }}
        50% {{ transform: translateX(6px); }}
      }}
      @keyframes twinkle {{
        0%, 100% {{ opacity: 0.35; }}
        50% {{ opacity: 1; }}
      }}
      @keyframes fall {{
        0% {{ transform: translateY(-6px); opacity: 0; }}
        50% {{ opacity: 0.9; }}
        100% {{ transform: translateY(20px); opacity: 0; }}
      }}
      .log-scroll {{ animation: scrollLog 14s linear infinite; }}
      .zzz {{ animation: floatZ 3.2s ease-in-out infinite; }}
      .steam {{ animation: steam 2.8s ease-in-out infinite; }}
      .cloud {{ animation: drift 9s ease-in-out infinite; }}
      .twinkle {{ animation: twinkle 3.6s ease-in-out infinite; }}
      .rain {{ animation: fall 1.4s linear infinite; }}
    </style>
  </defs>

  <g clip-path="url(#hero-round)">
    <!-- Wall -->
    <rect x="0" y="0" width="{w}" height="316" fill="#151c2f"/>
    {"".join(stripes)}

    <!-- Floor -->
    {"".join(floor_svg)}

    <!-- Window -->
    <rect x="56" y="52" width="200" height="136" fill="#101522"/>
    <rect x="64" y="60" width="184" height="120" fill="url(#sky-grad)"/>
    <g clip-path="url(#win-clip)">
      {"".join(window_fx)}
    </g>
    <!-- Window mullions & sill -->
    <rect x="152" y="60" width="8" height="120" fill="#101522"/>
    <rect x="64" y="116" width="184" height="8" fill="#101522"/>
    <rect x="48" y="188" width="216" height="12" fill="#5e3d24"/>
    <rect x="48" y="188" width="216" height="4" fill="#784f30"/>

    <!-- Name Plaque -->
    <rect x="{plaque_x - 4}" y="30" width="{plaque_w + 8}" height="58" fill="#0d111b"/>
    <rect x="{plaque_x}" y="34" width="{plaque_w}" height="50" fill="#f3e6cf"/>
    <rect x="{plaque_x + 4}" y="38" width="{plaque_w - 8}" height="42" fill="#efe0c5"/>
    {name_svg}

    <!-- Wall Clock -->
    <circle cx="{cx}" cy="{cy}" r="28" fill="#0d111b"/>
    <circle cx="{cx}" cy="{cy}" r="24" fill="#f3e6cf"/>
    <line x1="{cx}" y1="{cy}" x2="{hx:.1f}" y2="{hy:.1f}" stroke="#1e1b18" stroke-width="4" stroke-linecap="square"/>
    <line x1="{cx}" y1="{cy}" x2="{mx:.1f}" y2="{my:.1f}" stroke="#1e1b18" stroke-width="3" stroke-linecap="square"/>
    <rect x="{cx - 2}" y="{cy - 2}" width="4" height="4" fill="#b45309"/>

    <!-- Bookshelves -->
    {"".join(books_svg)}
    <rect x="668" y="172" width="160" height="12" fill="#6b4426"/>
    <rect x="668" y="172" width="160" height="4" fill="#825533"/>
    <rect x="668" y="236" width="160" height="12" fill="#6b4426"/>
    <rect x="668" y="236" width="160" height="4" fill="#825533"/>

    <!-- Potted Plant (left) -->
    <rect x="148" y="274" width="44" height="46" fill="#9c5530"/>
    <rect x="144" y="266" width="52" height="10" fill="#b8663a"/>
    <rect x="166" y="218" width="8" height="48" fill="#2ea043"/>
    <rect x="144" y="242" width="22" height="10" fill="#3fb950"/>
    <rect x="174" y="234" width="24" height="10" fill="#3fb950"/>
    <rect x="150" y="220" width="20" height="10" fill="#56d364"/>
    <rect x="170" y="212" width="18" height="10" fill="#2ea043"/>

    <!-- Desk Lamp (left of monitor) -->
    <rect x="292" y="128" width="40" height="16" fill="#e5c158"/>
    <rect x="296" y="124" width="32" height="6" fill="#f3d678"/>
    <rect x="308" y="144" width="8" height="92" fill="#475569"/>
    <rect x="296" y="234" width="32" height="8" fill="#334155"/>
    <polygon points="292,144 332,144 344,234 278,234" fill="#f5d97e" opacity="0.09"/>

    <!-- Monitor -->
    <rect x="330" y="104" width="248" height="142" fill="#364154"/>
    <rect x="334" y="108" width="240" height="134" fill="#1e2533"/>
    <rect x="340" y="114" width="228" height="122" fill="#0d1320"/>
    <g clip-path="url(#screen-clip)">
      <g class="log-scroll">
        {"".join(term_rows)}
      </g>
    </g>
    <!-- Monitor stand -->
    <rect x="444" y="246" width="20" height="14" fill="#334155"/>
    <rect x="424" y="258" width="60" height="6" fill="#475569"/>

    <!-- Coffee Mug (right of monitor) -->
    <rect x="556" y="216" width="24" height="26" fill="#e5e7eb"/>
    <rect x="580" y="220" width="8" height="16" fill="#cbd5e1"/>
    <rect x="580" y="224" width="4" height="8" fill="#151c2f"/>
    <rect x="560" y="216" width="16" height="4" fill="#6b4426"/>
    <g class="steam">
      <rect x="562" y="204" width="3" height="8" fill="#cbd5e1"/>
      <rect x="570" y="200" width="3" height="10" fill="#cbd5e1"/>
    </g>

    <!-- Desk -->
    <rect x="272" y="242" width="364" height="16" fill="#7c4f2c"/>
    <rect x="272" y="242" width="364" height="4" fill="#946138"/>
    <rect x="284" y="258" width="16" height="62" fill="#59371d"/>
    <rect x="608" y="258" width="16" height="62" fill="#59371d"/>

    <!-- Chair -->
    <rect x="466" y="236" width="56" height="36" fill="#2c3545"/>
    <rect x="470" y="240" width="48" height="28" fill="#374256"/>
    <rect x="490" y="272" width="8" height="42" fill="#1f2733"/>
    <rect x="472" y="310" width="44" height="8" fill="#1f2733"/>

    <!-- Sleeping Cat (right floor) -->
    <rect x="676" y="302" width="82" height="16" fill="#d98a3c"/>
    <rect x="684" y="294" width="64" height="10" fill="#e59a4c"/>
    <!-- Cat head & ears -->
    <rect x="738" y="284" width="24" height="22" fill="#e59a4c"/>
    <rect x="740" y="278" width="6" height="6" fill="#d98a3c"/>
    <rect x="754" y="278" width="6" height="6" fill="#d98a3c"/>
    <rect x="744" y="294" width="4" height="2" fill="#26170e"/>
    <rect x="752" y="294" width="4" height="2" fill="#26170e"/>
    <!-- Cat tail -->
    <rect x="664" y="308" width="14" height="6" fill="#c27429"/>
    <g class="zzz" fill="#94a3b8" font-family="ui-monospace,monospace" font-size="14" font-weight="700">
      <text x="770" y="274">Z</text>
    </g>
  </g>
</svg>'''


def build_about_card(user: dict, total_stars: int, avatar_data_uri: str) -> str:
    w, h = 900, 206
    name = html.escape(user.get("name") or USERNAME)
    bio_raw = (user.get("bio") or "Software engineer building modern applications.").strip()
    bio_lines = textwrap.wrap(bio_raw, width=62)[:2]
    loc = html.escape(user.get("location") or "Lithuania")
    followers = user["followers"]["totalCount"]
    repos = user["repositories"]["totalCount"]

    bio_svg = "\n".join(
        f'<text x="38" y="{114 + i * 24}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="16" fill="#c9d1d9">{html.escape(line)}</text>'
        for i, line in enumerate(bio_lines)
    )

    avatar_el = (
        f'<image href="{avatar_data_uri}" x="738" y="42" width="120" height="120" preserveAspectRatio="xMidYMid slice" style="image-rendering:pixelated"/>'
        if avatar_data_uri
        else '<rect x="738" y="42" width="120" height="120" fill="#21262d"/>'
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">
  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="#11161f" stroke="#242c38" stroke-width="1.5"/>
  <text x="38" y="44" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="14" font-weight="700" letter-spacing="1.5" fill="#3fb950">&gt; ABOUT</text>
  <text x="38" y="84" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="28" font-weight="700" fill="#f0f6fc">{name}</text>
  {bio_svg}
  <text x="38" y="176" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="13.5" fill="#8b949e">{loc}  ·  {followers} followers  ·  {repos} repositories  ·  ★ {total_stars} stars</text>
  <rect x="733" y="37" width="130" height="130" fill="#e6edf3"/>
  <rect x="736" y="40" width="124" height="124" fill="#0d1117"/>
  {avatar_el}
</svg>'''


def build_stats_hud(commits: int, prs: int, stars: int, best_streak: int) -> str:
    w, h = 900, 108
    items = [
        (str(commits), "COMMITS"),
        (str(prs), "PULL REQS"),
        (str(stars), "STARS"),
        (f"{best_streak}D", "BEST STREAK"),
    ]
    blocks = []
    col_w = (w - 76) / 4
    for i, (val, label) in enumerate(items):
        bx = 38 + i * col_w
        num_svg, _ = render_pixel_text(val, bx, 26, scale=4, fill="#f0f6fc", letter_gap=1)
        blocks.append(num_svg)
        blocks.append(
            f'<text x="{bx}" y="82" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" '
            f'font-size="13" letter-spacing="1.5" fill="#8b949e">{label}</text>'
        )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" shape-rendering="crispEdges">
  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="#11161f" stroke="#242c38" stroke-width="1.5"/>
  {"".join(blocks)}
</svg>'''


def build_projects_header() -> str:
    w, h = 900, 46
    hdr_svg, _ = render_pixel_text("> PROJECTS", 4, 10, scale=4, fill="#3fb950", letter_gap=1)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" shape-rendering="crispEdges">
  {hdr_svg}
</svg>'''


def build_pixel_sprite(seed_text: str, fg: str, bg: str, ox: int, oy: int, size: int = 96) -> str:
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    cell = size // 8
    rects = [f'<rect x="{ox}" y="{oy}" width="{size}" height="{size}" rx="10" fill="{bg}"/>']
    # 8x8 symmetric pixel identicon (inner 6x6 padded by 1 cell)
    bit_i = 0
    for r in range(1, 7):
        for c in range(1, 4):
            byte = digest[bit_i // 8]
            on = (byte >> (bit_i % 8)) & 1
            bit_i += 1
            if on:
                for col in (c, 7 - c):
                    rects.append(
                        f'<rect x="{ox + col * cell}" y="{oy + r * cell}" width="{cell}" height="{cell}" fill="{fg}"/>'
                    )
    return "\n".join(rects)


def build_project_card(repo: dict) -> str:
    w, h = 440, 168
    name = repo["name"]
    desc_raw = (repo.get("description") or "No description provided.").strip()
    desc_lines = textwrap.wrap(desc_raw, width=35)[:3]
    if len(desc_lines) == 3 and len(desc_raw) > sum(len(x) for x in desc_lines) + 2:
        desc_lines[2] = desc_lines[2].rstrip(" .")[:32] + "…"
    stars = repo.get("stargazerCount", 0)
    lang = (repo.get("primaryLanguage") or {}).get("name") or "Code"
    fg, bg, abbr = LANG_META.get(lang, ("#58a6ff", "#16263b", lang[:2].upper()))

    sprite = build_pixel_sprite(name, fg, bg, ox=22, oy=36, size=96)
    desc_svg = "\n".join(
        f'<text x="142" y="{66 + i * 20}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" '
        f'font-size="13.5" fill="#8b949e">{html.escape(line)}</text>'
        for i, line in enumerate(desc_lines)
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" shape-rendering="crispEdges">
  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="#11161f" stroke="#242c38" stroke-width="1.5"/>
  {sprite}
  <text x="142" y="42" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="700" fill="#f0f6fc">{html.escape(name)}</text>
  {desc_svg}
  <text x="142" y="142" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="13.5" fill="#3fb950">★ {stars}</text>
  <rect x="304" y="128" width="22" height="18" rx="3" fill="{fg}"/>
  <text x="315" y="141" text-anchor="middle" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="10.5" font-weight="700" fill="#0d1117">{html.escape(abbr)}</text>
  <text x="333" y="142" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="13.5" fill="#8b949e">{html.escape(lang)}</text>
</svg>'''


def build_activity_card(weeks: list[dict], cur_streak: int, best_streak: int, year_total: int) -> str:
    w, h = 900, 224
    recent_weeks = weeks[-26:]
    levels = ["#1b222c", "#0e4429", "#006d32", "#26a641", "#39d353"]

    def cell_color(c: int) -> str:
        if c <= 0:
            return levels[0]
        if c <= 2:
            return levels[1]
        if c <= 5:
            return levels[2]
        if c <= 10:
            return levels[3]
        return levels[4]

    grid = []
    gx, gy = 38, 66
    cell, gap = 16, 4
    for wi, wk in enumerate(recent_weeks):
        for di, day in enumerate(wk["contributionDays"]):
            col = cell_color(day["contributionCount"])
            grid.append(
                f'<rect x="{gx + wi * (cell + gap)}" y="{gy + di * (cell + gap)}" '
                f'width="{cell}" height="{cell}" rx="2" fill="{col}"/>'
            )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" shape-rendering="crispEdges">
  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="12" fill="#11161f" stroke="#242c38" stroke-width="1.5"/>
  <text x="38" y="44" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="14" font-weight="700" letter-spacing="1.5" fill="#3fb950">&gt; ACTIVITY</text>
  {"".join(grid)}
  <text x="612" y="84" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="12" letter-spacing="1.2" fill="#8b949e">CURRENT STREAK</text>
  <text x="612" y="108" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="20" font-weight="700" fill="#f0f6fc">{cur_streak} days</text>
  <text x="612" y="138" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="12" letter-spacing="1.2" fill="#8b949e">BEST STREAK</text>
  <text x="612" y="162" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="20" font-weight="700" fill="#f0f6fc">{best_streak} days</text>
  <text x="612" y="190" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="12" letter-spacing="1.2" fill="#8b949e">THIS YEAR</text>
  <text x="612" y="212" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="20" font-weight="700" fill="#f0f6fc">{year_total}</text>
</svg>'''


def pick_projects(repos: list[dict]) -> list[dict]:
    by_name = {r["name"].lower(): r for r in repos if not r.get("isPrivate")}
    picked = []
    for fname in FEATURED_REPOS:
        if fname.lower() in by_name:
            picked.append(by_name[fname.lower()])
    for r in repos:
        if len(picked) >= 4:
            break
        if not r.get("isPrivate") and r not in picked and r["name"].lower() != USERNAME.lower():
            picked.append(r)
    return picked[:4]


def main() -> int:
    token = get_github_token()
    if not token:
        print("Error: GITHUB_TOKEN or authenticated `gh` CLI required.", file=sys.stderr)
        return 1

    data = fetch_github_data(token)
    user = data["user"]
    commits = data["commits"]
    weather = fetch_weather()

    repos = user["repositories"]["nodes"]
    total_stars = sum(r.get("stargazerCount", 0) for r in repos if not r.get("isPrivate"))
    cc = user["contributionsCollection"]
    weeks = cc["contributionCalendar"]["weeks"]
    cur_streak, best_streak = compute_streaks(weeks)

    avatar_data_uri = ""
    try:
        raw, ctype = http_bytes(user["avatarUrl"])
        avatar_data_uri = f"data:{ctype};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        pass

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "desk-hero.svg").write_text(build_desk_hero(user, commits, weather), encoding="utf-8")
    (OUT_DIR / "about.svg").write_text(build_about_card(user, total_stars, avatar_data_uri), encoding="utf-8")
    (OUT_DIR / "stats-hud.svg").write_text(
        build_stats_hud(
            cc["totalCommitContributions"],
            cc["totalPullRequestContributions"],
            total_stars,
            best_streak,
        ),
        encoding="utf-8",
    )
    (OUT_DIR / "projects-header.svg").write_text(build_projects_header(), encoding="utf-8")

    featured = pick_projects(repos)
    for idx, repo in enumerate(featured):
        (OUT_DIR / f"project-{idx}.svg").write_text(build_project_card(repo), encoding="utf-8")

    (OUT_DIR / "activity.svg").write_text(
        build_activity_card(weeks, cur_streak, best_streak, cc["contributionCalendar"]["totalContributions"]),
        encoding="utf-8",
    )

    print(f"Generated {len(list(OUT_DIR.glob('*.svg')))} SVGs in {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
