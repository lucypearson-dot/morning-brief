import feedparser
import requests
import os
import sys
import re
from datetime import datetime
from bs4 import BeautifulSoup

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "lucy.pearson@iklcomputing.co.uk")

SECTIONS = {
    "Foreign Policy": {
        "feeds": ["https://feeds.bbci.co.uk/news/world/rss.xml"],
        "keywords": [
            "foreign", "diplomacy", "diplomatic", "treaty", "summit",
            "sanction", "conflict", "troops", "alliance", "embassy",
            "united nations", "war", "ceasefire", "president",
        ],
    },
    "Russia & Ukraine": {
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ],
        "keywords": [
            "russia", "russian", "putin", "kremlin", "moscow",
            "ukraine", "ukrainian", "kyiv", "zelensky", "donbas",
        ],
    },
    "NATO": {
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
        ],
        "keywords": [
            "nato", "north atlantic", "article 5", "rutte", "stoltenberg",
            "collective defence", "collective defense", "military alliance",
        ],
    },
    "UK Politics": {
        "feeds": ["https://feeds.bbci.co.uk/news/politics/rss.xml"],
        "keywords": [],
    },
    "Economy": {
        "feeds": ["https://feeds.bbci.co.uk/news/business/rss.xml"],
        "keywords": [],
    },
}


def get_summary(entry):
    raw = entry.get("summary") or entry.get("description") or ""
    text = BeautifulSoup(raw, "html.parser").get_text(strip=True)
    return text[:400] if text else "Summary unavailable."


def matches(title, summary, keywords):
    if not keywords:
        return True
    haystack = (title + " " + summary).lower()
    return any(kw in haystack for kw in keywords)


def get_stories(config, n=2):
    keywords = config["keywords"]
    seen = set()
    hits, fallback = [], []

    for feed_url in config["feeds"]:
        feed = feedparser.parse(feed_url)
        for entry in feed.entries:
            if entry.link in seen:
                continue
            seen.add(entry.link)
            summary = get_summary(entry)
            if matches(entry.title, summary, keywords):
                hits.append((entry.title, entry.link, summary))
            else:
                fallback.append((entry.title, entry.link, summary))

    combined = hits[:n]
    if len(combined) < n:
        for item in fallback:
            if item not in combined:
                combined.append(item)
            if len(combined) >= n:
                break

    return combined[:n]


def build_html(sections_data, today):
    section_html = ""
    for section, stories in sections_data.items():
        section_html += f"""
        <tr><td style="padding:24px 0 8px 0;">
            <h2 style="margin:0;font-size:13px;font-weight:700;text-transform:uppercase;
                letter-spacing:1.5px;color:#6b7280;">{section}</h2>
            <hr style="border:none;border-top:1px solid #e5e7eb;margin:8px 0 0 0;">
        </td></tr>"""
        for title, link, summary in stories:
            section_html += f"""
        <tr><td style="padding:16px 0 0 0;">
            <a href="{link}" style="font-size:17px;font-weight:700;color:#111827;
                text-decoration:none;line-height:1.3;">{title}</a>
            <p style="margin:6px 0 0 0;font-size:14px;color:#4b5563;line-height:1.6;">{summary}</p>
            <a href="{link}" style="display:inline-block;margin-top:8px;font-size:13px;
                color:#2563eb;text-decoration:none;font-weight:500;">Read more &rarr;</a>
        </td></tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,
    'Segoe UI',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
          style="background:#ffffff;border-radius:8px;overflow:hidden;
          box-shadow:0 1px 3px rgba(0,0,0,0.08);max-width:600px;width:100%;">
        <tr><td style="background:#111827;padding:24px 32px;">
            <p style="margin:0;font-size:11px;font-weight:600;letter-spacing:2px;
                text-transform:uppercase;color:#9ca3af;">Morning Brief</p>
            <h1 style="margin:4px 0 0 0;font-size:22px;font-weight:700;color:#ffffff;">
                {today}</h1>
        </td></tr>
        <tr><td style="padding:8px 32px 32px 32px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            {section_html}
          </table>
        </td></tr>
        <tr><td style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
            <p style="margin:0;font-size:12px;color:#9ca3af;">
                Sources: BBC News &bull; Delivered via GitHub Actions
            </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_email(subject, html):
    resp = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Morning Brief <onboarding@resend.dev>",
            "to": [TO_EMAIL],
            "subject": subject,
            "html": html,
        },
    )
    return resp.ok, resp.text


today = datetime.utcnow().strftime("%A %-d %B %Y")

sections_data = {}
for section, config in SECTIONS.items():
    sections_data[section] = get_stories(config)

html = build_html(sections_data, today)
ok, detail = send_email(f"Morning Brief — {today}", html)

if not ok:
    print(f"Failed to send email: {detail}", file=sys.stderr)
    sys.exit(1)

print("Brief sent successfully.")
