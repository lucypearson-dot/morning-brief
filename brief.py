import feedparser
import requests
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

FEEDS = {
    "Foreign Policy": "https://www.telegraph.co.uk/news/world/rss.xml",
    "UK Politics": "https://www.telegraph.co.uk/politics/rss.xml",
    "Economy": "https://www.telegraph.co.uk/business/rss.xml",
}


def get_top_stories(url, n=3):
    feed = feedparser.parse(url)
    stories = []
    for entry in feed.entries[:n]:
        stories.append(f"• {entry.title}")
    return stories if stories else ["• No stories found"]


today = datetime.utcnow().strftime("%A %-d %B %Y")
lines = [f"🌍 *Morning Brief — {today}*\n"]

for section, url in FEEDS.items():
    stories = get_top_stories(url)
    lines.append(f"*{section}*")
    lines.extend(stories)
    lines.append("")

message = "\n".join(lines).strip()

response = requests.post(
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
    json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    },
)

if not response.ok:
    raise RuntimeError(f"Telegram API error: {response.text}")

print("Brief sent successfully.")
