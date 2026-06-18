import feedparser
import requests
import os
import sys
import re
from datetime import datetime
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAPH_COOKIE = os.environ.get("TELEGRAPH_COOKIE", "")

SECTIONS = {
    "Foreign Policy": {
        "feeds": [
            "https://www.telegraph.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ],
        "keywords": [
            "foreign", "diplomacy", "diplomatic", "treaty", "summit",
            "sanction", "conflict", "minister", "president", "war", "troops",
            "alliance", "bilateral", "embassy", "united nations",
        ],
    },
    "Russia": {
        "feeds": [
            "https://www.telegraph.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ],
        "keywords": [
            "russia", "russian", "putin", "kremlin", "moscow",
            "ukraine", "ukrainian", "kyiv", "zelensky", "wagner",
        ],
    },
    "NATO": {
        "feeds": [
            "https://www.telegraph.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
        ],
        "keywords": [
            "nato", "north atlantic", "article 5", "defence alliance",
            "military alliance", "stoltenberg", "rutte", "collective defence",
        ],
    },
    "UK Politics": {
        "feeds": [
            "https://www.telegraph.co.uk/politics/rss.xml",
            "https://feeds.bbci.co.uk/news/politics/rss.xml",
        ],
        "keywords": [],
    },
    "Economy": {
        "feeds": [
            "https://www.telegraph.co.uk/business/rss.xml",
            "https://feeds.bbci.co.uk/news/business/rss.xml",
        ],
        "keywords": [],
    },
}

JUNK_PATTERNS = re.compile(
    r"(copy link|twitter|facebook|whatsapp|sign up|subscribe|newsletter"
    r"|advertisement|related articles|read more|click here)",
    re.IGNORECASE,
)


def send_telegram(text):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
    )
    return response.ok


def clean_summary(text):
    if not text:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", text.replace("...", ""))
    clean = [
        s.strip() for s in sentences
        if len(s.strip()) > 30 and not JUNK_PATTERNS.search(s)
    ]
    if not clean:
        return None
    summary = " ".join(clean[:2])
    if not summary.endswith((".", "!", "?")):
        summary += "."
    return summary[:300]


def fetch_article_text(url, session):
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code in (401, 403):
            return None, "auth_error"
        soup = BeautifulSoup(resp.text, "html.parser")
        if soup.find(class_=lambda c: c and "paywall" in c.lower()):
            return None, "cookie_expired"
        article = soup.find("article") or soup.find(class_=lambda c: c and "article" in c.lower())
        if not article:
            return None, "parse_error"
        paragraphs = article.find_all("p", limit=6)
        text = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        return text[:1200] if text else None, "ok"
    except Exception as e:
        return None, f"error: {e}"


def rss_summary(entry):
    raw = entry.get("summary") or entry.get("description") or ""
    soup = BeautifulSoup(raw, "html.parser")
    return soup.get_text(strip=True)


def matches_keywords(title, summary, keywords):
    if not keywords:
        return True
    haystack = (title + " " + summary).lower()
    return any(kw in haystack for kw in keywords)


def get_stories(section_config, session, n=2):
    keywords = section_config["keywords"]
    seen = set()
    candidates = []

    for feed_url in section_config["feeds"]:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if entry.link in seen:
                continue
            seen.add(entry.link)
            raw_rss = rss_summary(entry)
            if matches_keywords(entry.title, raw_rss, keywords):
                candidates.append(entry)
        if len(candidates) >= n * 3:
            break

    stories = []
    for entry in candidates[:n * 3]:
        if len(stories) >= n:
            break
        body, status = fetch_article_text(entry.link, session)
        summary = clean_summary(body) or clean_summary(rss_summary(entry)) or "(summary unavailable)"
        stories.append((entry.title, entry.link, summary, status))

    return stories


session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})
if TELEGRAPH_COOKIE:
    session.headers["Cookie"] = TELEGRAPH_COOKIE

today = datetime.utcnow().strftime("%A %-d %B %Y")
lines = [f"\U0001f30d *Morning Brief \u2014 {today}*\n"]
cookie_issue = False

for section, config in SECTIONS.items():
    stories = get_stories(config, session)
    lines.append(f"*{section}*")
    if not stories:
        lines.append("  No stories found today.")
    for title, link, summary, status in stories:
        lines.append(f"\u2022 *{title}*")
        lines.append(f"  {summary}")
        lines.append(f"  [Read more]({link})")
        if status in ("auth_error", "cookie_expired"):
            cookie_issue = True
    lines.append("")

message = "\n".join(lines).strip()

if not send_telegram(message):
    print("Failed to send brief", file=sys.stderr)
    sys.exit(1)

if cookie_issue:
    send_telegram(
        "\u26a0\ufe0f *Telegraph cookie may have expired.*\n\n"
        "To refresh:\n"
        "1. Log in to telegraph.co.uk in Chrome\n"
        "2. DevTools \u2192 Application \u2192 Cookies\n"
        "3. Copy tmg_refresh value\n"
        "4. Update TELEGRAPH_COOKIE secret in GitHub repo"
    )

print("Brief sent successfully.")
