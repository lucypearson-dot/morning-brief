import feedparser
import requests
import os
import sys
import json
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import anthropic

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "lucy.pearson@iklcomputing.co.uk")
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SECTIONS = {
    "Foreign Policy": {
        "feeds": ["https://feeds.bbci.co.uk/news/world/rss.xml"],
        "keywords": ["foreign", "diplomacy", "diplomatic", "treaty", "summit",
            "sanction", "conflict", "troops", "alliance", "embassy",
            "united nations", "war", "ceasefire", "president"],
    },
    "Russia & Ukraine": {
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ],
        "keywords": ["russia", "russian", "putin", "kremlin", "moscow",
            "ukraine", "ukrainian", "kyiv", "zelensky", "donbas"],
    },
    "NATO": {
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
            "https://www.rusi.org/rss/latest-publications.xml",
            "https://www.rusi.org/rss/latest-commentary.xml",
        ],
        "keywords": ["nato", "north atlantic", "article 5", "rutte", "stoltenberg",
            "collective defence", "collective defense", "military alliance"],
    },
    "Analyst Views": {
        "feeds": [
            "https://markgaleotti.substack.com/feed",
            "https://www.rusi.org/rss/latest-commentary.xml",
            "https://www.rusi.org/rss/latest-publications.xml",
        ],
        "keywords": ["webber"],
        "n": 3,
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

def get_stories(config, default_n=2):
    n = config.get("n", default_n)
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

def ai_enhance(section_name, stories):
    if not stories:
        return None, stories
    articles_text = "\n\n".join(
        f"{i+1}. {title}\n{summary}"
        for i, (title, _, summary) in enumerate(stories)
    )
    prompt = f"""You are writing a concise morning intelligence brief for a foreign policy professional.

Section: {section_name}

Articles:
{articles_text}

Respond with valid JSON only (no markdown fences):
{{
  "synthesis": "A 2-3 sentence analytical paragraph synthesising the key developments in this section right now.",
  "summaries": ["A sharper 1-2 sentence summary of article 1.", "A sharper 1-2 sentence summary of article 2."]
}}

Be factual, analytical and direct. Number of summaries must match number of articles ({len(stories)})."""

    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        data = json.loads(message.content[0].text)
        synthesis = data.get("synthesis", "")
        new_summaries = data.get("summaries", [])
        enhanced = [
            (title, link, new_summaries[i] if i < len(new_summaries) else summary)
            for i, (title, link, summary) in enumerate(stories)
        ]
        return synthesis, enhanced
    except Exception:
        return None, stories

def build_html(sections_data, today):
    section_html = ""
    for section, (synthesis, stories) in sections_data.items():
        section_html += f"""
        <tr>
          <td style="padding:24px 0 8px 0;">
            <h2 style="margin:0;font-size:16px;font-weight:700;color:#111827;
                text-transform:uppercase;letter-spacing:0.05em;
                border-bottom:2px solid #2563eb;padding-bottom:6px;">{section}</h2>
          </td>
        </tr>"""
        if synthesis:
            section_html += f"""
        <tr><td style="padding:12px 0 0 0;">
            <p style="margin:0;font-size:14px;color:#374151;line-height:1.7;
                background:#f9fafb;border-left:3px solid #2563eb;
                padding:10px 14px;border-radius:0 4px 4px 0;">{synthesis}</p>
        </td></tr>"""
        for title, link, summary in stories:
            section_html += f"""
        <tr>
          <td style="padding:12px 0 0 0;">
            <a href="{link}" style="font-size:15px;font-weight:600;color:#1d4ed8;
                text-decoration:none;line-height:1.4;">{title}</a>
            <p style="margin:4px 0 0 0;font-size:13px;color:#6b7280;line-height:1.6;">{summary}</p>
            <p style="margin:4px 0 0 0;">
              <a href="{link}" style="font-size:12px;color:#9ca3af;">Read more →</a>
            </p>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f3f4f6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:32px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;
          box-shadow:0 1px 3px rgba(0,0,0,0.1);overflow:hidden;">
        <tr>
          <td style="background:#1e3a5f;padding:28px 32px;">
            <h1 style="margin:0;font-size:22px;font-weight:700;color:#ffffff;">
              Morning Brief
            </h1>
            <p style="margin:4px 0 0 0;font-size:14px;color:#93c5fd;">{today}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 32px 32px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {section_html}
            </table>
          </td>
        </tr>
        <tr>
          <td style="background:#f9fafb;padding:16px 32px;border-top:1px solid #e5e7eb;">
            <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
              Automated Morning Brief · Generated {today}
            </p>
          </td>
        </tr>
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

today = datetime.now(timezone.utc).strftime("%A %-d %B %Y")
sections_data = {}
for section, config in SECTIONS.items():
    stories = get_stories(config)
    synthesis, enhanced = ai_enhance(section, stories)
    sections_data[section] = (synthesis, enhanced)

html = build_html(sections_data, today)
ok, detail = send_email(f"Morning Brief — {today}", html)
if not ok:
    print(f"Failed to send email: {detail}", file=sys.stderr)
    sys.exit(1)
print("Brief sent successfully.")
