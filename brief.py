import feedparser
import requests
import os
import sys
from datetime import datetime
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAPH_COOKIE = os.environ.get("TELEGRAPH_COOKIE", "")

FEEDS = {
    "Foreign Policy": "https://www.telegraph.co.uk/news/world/rss.xml",
    "Russia": "https://www.telegraph.co.uk/russia/rss.xml",
    "UK Politics": "https://www.telegraph.co.uk/politics/rss.xml",
    "Economy": "https://www.telegraph.co.uk/business/rss.xml",
}


def send_telegram(text):
    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
    )
    return response.ok


def fetch_article_text(url, session):
    """Fetch full article text from Telegraph. Returns (text, status)."""
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code in (401, 403):
            return None, "auth_error"
        soup = BeautifulSoup(resp.text, "html.parser")

        # Check for paywall indicator
        if soup.find(class_=lambda c: c and "paywall" in c.lower()):
            return None, "cookie_expired"

        # Extract article body paragraphs
        article = soup.find("article") or soup.find(class_=lambda c: c and "article" in c.lower())
        if not article:
            return None, "parse_error"

        paragraphs = article.find_all("p", limit=6)
        text = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        return text[:1200] if text else None, "ok"
    except Exception as e:
        return None, f"error: {e}"


def summarise(body):
    """Return a 2-sentence summary."""
    if not body:
        return "(summary unavailable)"
    sentences = body.replace("...", "").split(". ")
    summary = ". ".join(sentences[:2]).strip()
    if not summary.endswith("."):
        summary += "."
    return summary[:300]


def get_stories(url, session, n=2):
    feed = feedparser.parse(url)
    stories = []
    for entry in feed.entries[:n]:
        body, status = fetch_article_text(entry.link, session)
        stories.append((entry.title, entry.link, summarise(body), status))
    return stories


# Build authenticated session
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})
if TELEGRAPH_COOKIE:
    session.headers["Cookie"] = TELEGRAPH_COOKIE

# Compose brief
today = datetime.utcnow().strftime("%A %-d %B %Y")
lines = [f"🌍 *Morning Brief — {today}*\n"]
cookie_issue = False

for section, url in FEEDS.items():
    stories = get_stories(url, session)
    lines.append(f"*{section}*")
    for title, link, summary, status in stories:
        lines.append(f"• *{title}*")
        lines.append(f"  {summary}")
        lines.append(f"  [Read more]({link})")
        if status in ("auth_error", "cookie_expired"):
            cookie_issue = True
    lines.append("")

message = "\n".join(lines).strip()

if not send_telegram(message):
    print("Failed to send brief", file=sys.stderr)
    sys.exit(1)

# Alert if cookie needs refreshing
if cookie_issue:
    send_telegram(
        "⚠️ *Telegraph cookie has expired.*\n\n"
        "To restore full article summaries:\n"
        "1. Log in to telegraph.co.uk in Chrome\n"
        "2. DevTools → Application → Cookies → telegraph.co.uk\n"
        "3. Copy the `sso\\_token` value\n"
        "4. Update the `TELEGRAPH\\_COOKIE` secret in your GitHub repo"
    )

print("Brief sent successfully.")
