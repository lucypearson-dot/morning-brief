import feedparser
import requests
import os
import sys
import json
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from openai import OpenAI

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "lucy.pearson@iklcomputing.co.uk")
client = OpenAI(
    base_url="https://models.inference.ai.azure.com",
    api_key=os.environ["GITHUB_TOKEN"],
)

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
    prompt = f"""You are Lucy's personal assistant. Lucy is a foreign policy professional. You're briefing her on this section of her morning news.

Section: {section_name}

Articles:
{articles_text}

Respond with valid JSON only (no markdown fences):
{{
  "synthesis": "One punchy sentence — like a PA speaking to their boss — telling Lucy what's happening here and what to watch. Use 'you' not 'one'. Be direct. No formal language.",
  "summaries": ["Sharp one-sentence summary of article 1 — the key fact only.", "Sharp one-sentence summary of article 2 — the key fact only."]
}}

Number of summaries must match number of articles ({len(stories)}). Cut all filler words."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        data = json.loads(response.choices[0].message.content)
        synthesis = data.get("synthesis", "")
        new_summaries = data.get("summaries", [])
        enhanced = [
            (title, link, new_summaries[i] if i < len(new_summaries) else summary)
            for i, (title, link, summary) in enumerate(stories)
        ]
        return synthesis, enhanced
    except Exception:
        return None, stories

def ai_top_brief(sections_data):
    all_headlines = []
    for section, (_, stories) in sections_data.items():
        for title, _, summary in stories:
            all_headlines.append(f"[{section}] {title}: {summary[:120]}")
    if not all_headlines:
        return None
    combined = "\n".join(all_headlines[:16])
    prompt = f"""You are Lucy's personal assistant. She's a foreign policy professional. Based on today's headlines, write her a 2-3 sentence morning briefing — like a PA walking into her office and telling her the 2-3 most important things she needs to know right now. Be direct and conversational. Use "you". No "Good morning". No filler. Just the key things.

Today's headlines:
{combined}

Reply with just the briefing text. No JSON. No labels."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None

def build_html(sections_data, top_brief, today):
    top_html = ""
    if top_brief:
        top_html = f"""
        <tr>
          <td style="padding:20px 0 0 0;">
            <div style="background:#1e3a5f;border-radius:6px;padding:16px 20px;">
              <p style="margin:0 0 4px 0;font-size:11px;font-weight:600;color:#93c5fd;
                  text-transform:uppercase;letter-spacing:0.08em;">Your brief</p>
              <p style="margin:0;font-size:15px;color:#ffffff;line-height:1.7;">{top_brief}</p>
            </div>
          </td>
        </tr>"""

    section_html = ""
    for section, (synthesis, stories) in sections_data.items():
        section_html += f"""
        <tr>
          <td style="padding:24px 0 8px 0;">
            <h2 style="margin:0;font-size:13px;font-weight:700;color:#6b7280;
                text-transform:uppercase;letter-spacing:0.08em;
                border-bottom:1px solid #e5e7eb;padding-bottom:6px;">{section}</h2>
          </td>
        </tr>"""
        if synthesis:
            section_html += f"""
        <tr><td style="padding:8px 0 0 0;">
            <p style="margin:0;font-size:14px;color:#111827;line-height:1.6;
                font-style:italic;">{synthesis}</p>
        </td></tr>"""
        for title, link, summary in stories:
            section_html += f"""
        <tr>
          <td style="padding:10px 0 0 0;">
            <a href="{link}" style="font-size:14px;font-weight:600;color:#1d4ed8;
                text-decoration:none;line-height:1.4;">{title}</a>
            <p style="margin:3px 0 0 0;font-size:13px;color:#6b7280;line-height:1.5;">{summary}</p>
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
          <td style="background:#0f172a;padding:20px 28px;">
            <p style="margin:0;font-size:12px;font-weight:600;color:#64748b;
                text-transform:uppercase;letter-spacing:0.08em;">Morning Brief</p>
            <p style="margin:2px 0 0 0;font-size:20px;font-weight:700;color:#ffffff;">{today}</p>
          </td>
        </tr>
        <tr>
          <td style="padding:0 28px 28px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              {top_html}
              {section_html}
            </table>
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

top_brief = ai_top_brief(sections_data)
html = build_html(sections_data, top_brief, today)
ok, detail = send_email(f"Morning Brief — {today}", html)
if not ok:
    print(f"Failed to send email: {detail}", file=sys.stderr)
    sys.exit(1)
print("Brief sent successfully.")
