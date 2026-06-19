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

WEATHER_CODES = {
    0: ("Clear sky", "&#9728;"), 1: ("Mainly clear", "&#127780;"),
    2: ("Partly cloudy", "&#9925;"), 3: ("Overcast", "&#9729;"),
    45: ("Fog", "&#127787;"), 48: ("Fog", "&#127787;"),
    51: ("Light drizzle", "&#127746;"), 53: ("Drizzle", "&#127746;"), 55: ("Drizzle", "&#127746;"),
    61: ("Light rain", "&#127783;"), 63: ("Rain", "&#127783;"), 65: ("Heavy rain", "&#127783;"),
    71: ("Light snow", "&#127784;"), 73: ("Snow", "&#127784;"), 75: ("Heavy snow", "&#10052;"),
    80: ("Showers", "&#127746;"), 81: ("Showers", "&#127746;"), 82: ("Heavy showers", "&#9928;"),
    95: ("Thunderstorm", "&#9928;"),
}

SECTIONS = {
    "Foreign Policy": {
        "feeds": ["https://feeds.bbci.co.uk/news/world/rss.xml"],
        "keywords": ["foreign", "diplomacy", "diplomatic", "treaty", "summit",
            "sanction", "conflict", "troops", "alliance", "embassy",
            "united nations", "war", "ceasefire", "president"],
        "n": 3, "color": "#1d4ed8",
    },
    "Russia & Ukraine": {
        "feeds": [
            "https://feeds.bbci.co.uk/news/world/europe/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ],
        "keywords": ["russia", "russian", "putin", "kremlin", "moscow",
            "ukraine", "ukrainian", "kyiv", "zelensky", "donbas"],
        "n": 3, "color": "#dc2626",
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
        "n": 3, "color": "#0369a1",
    },
    "Analyst Views": {
        "feeds": [
            "https://markgaleotti.substack.com/feed",
            "https://www.rusi.org/rss/latest-commentary.xml",
            "https://www.rusi.org/rss/latest-publications.xml",
        ],
        "keywords": ["webber"],
        "n": 3, "color": "#7c3aed",
    },
    "UK Politics": {
        "feeds": ["https://feeds.bbci.co.uk/news/politics/rss.xml"],
        "keywords": [],
        "n": 3, "color": "#0f766e",
    },
    "Economy": {
        "feeds": ["https://feeds.bbci.co.uk/news/business/rss.xml"],
        "keywords": [],
        "n": 2, "color": "#b45309",
    },
    "Health": {
        "feeds": ["https://feeds.bbci.co.uk/news/health/rss.xml"],
        "keywords": [],
        "n": 2, "color": "#059669",
    },
    "Skincare & Wellness": {
        "feeds": [
            "https://www.theguardian.com/lifeandstyle/health-and-wellbeing/rss",
            "https://www.theguardian.com/fashion/rss",
        ],
        "keywords": ["skin", "skincare", "moisturiser", "moisturizer", "spf",
            "sunscreen", "retinol", "serum", "wellness", "beauty", "acne",
            "collagen", "vitamin c", "hyaluronic"],
        "n": 2, "color": "#db2777",
    },
    "Food & Drink": {
        "feeds": ["https://www.theguardian.com/food/rss"],
        "keywords": [],
        "n": 2, "color": "#d97706",
    },
}

def get_weather():
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": 52.4128,
                "longitude": -1.7780,
                "current": "temperature_2m,precipitation_probability,weathercode,windspeed_10m",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "Europe/London",
                "forecast_days": 1,
            },
            timeout=10
        )
        data = resp.json()
        cur = data["current"]
        temp = round(cur["temperature_2m"])
        precip = cur.get("precipitation_probability", 0) or 0
        code = cur.get("weathercode", 0) or 0
        wind = round(cur.get("windspeed_10m", 0) or 0)
        daily = data.get("daily", {})
        hi = round(daily.get("temperature_2m_max", [temp])[0])
        lo = round(daily.get("temperature_2m_min", [temp])[0])
        desc, icon = WEATHER_CODES.get(code, ("Variable", "&#127781;"))
        return {"temp": temp, "hi": hi, "lo": lo, "desc": desc, "icon": icon,
                "precip": precip, "wind": wind}
    except Exception:
        return None

def get_summary(entry):
    raw = entry.get("summary") or entry.get("description") or ""
    text = BeautifulSoup(raw, "html.parser").get_text(strip=True)
    return text[:400] if text else "Summary unavailable."

def matches(title, summary, keywords):
    if not keywords:
        return True
    haystack = (title + " " + summary).lower()
    return any(kw in haystack for kw in keywords)

def get_stories(config, default_n=3):
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
    prompt = f"""You are Lucy's personal assistant giving her a morning briefing. Section: {section_name}.

Articles:
{articles_text}

Respond with valid JSON only (no markdown fences):
{{
  "synthesis": "One direct sentence — like a PA walking into the room and telling Lucy what's happening here. Use 'you' not 'one'. Conversational, punchy, no jargon.",
  "summaries": ["One crisp sentence: the key fact from article 1, nothing else.", "One crisp sentence: the key fact from article 2, nothing else."]
}}

Number of summaries must equal {len(stories)}. Be ruthlessly concise."""

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

def ai_top_brief(sections_data, weather):
    lines = []
    for section, (_, stories) in sections_data.items():
        for title, _, summary in stories:
            lines.append(f"[{section}] {title}: {summary[:100]}")
    if not lines:
        return None
    weather_line = ""
    if weather:
        weather_line = f"Weather: {weather['desc']}, {weather['temp']}C in Solihull (high {weather['hi']}C, {weather['precip']}% rain chance)."
    prompt = f"""You are Lucy's personal assistant. She is a foreign policy professional based in Solihull, UK. Brief her in 3-4 sentences max — like walking into her office and telling her the most important things she needs to know right now. Be direct, warm and conversational. No "Good morning". No bullet points. Use "you". Cover the 2-3 biggest stories across all areas, and weave in a practical weather note if relevant.

{weather_line}

Today's headlines:
{chr(10).join(lines[:20])}

Write the briefing now. Plain text only, no labels."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None

def build_html(sections_data, top_brief, weather, today):
    weather_html = ""
    if weather:
        weather_html = f"""
        <tr>
          <td style="background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:14px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:28px;width:44px;">{weather['icon']}</td>
                <td style="padding-left:12px;">
                  <span style="font-size:22px;font-weight:700;color:#0f172a;">{weather['temp']}&deg;C</span>
                  <span style="font-size:15px;color:#64748b;margin-left:8px;">{weather['desc']}</span>
                  <span style="font-size:14px;color:#94a3b8;margin-left:10px;">H:{weather['hi']}&deg; L:{weather['lo']}&deg;</span>
                </td>
                <td align="right" style="font-size:14px;color:#64748b;">
                  {weather['precip']}% rain &nbsp;&#183;&nbsp; {weather['wind']} km/h wind<br>
                  <span style="font-size:13px;color:#94a3b8;">Solihull, UK</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    brief_html = ""
    if top_brief:
        brief_html = f"""
        <tr>
          <td style="padding:24px 32px 8px;">
            <div style="background:#0f172a;border-radius:10px;padding:20px 24px;">
              <p style="margin:0 0 6px;font-size:11px;font-weight:700;color:#60a5fa;
                  text-transform:uppercase;letter-spacing:0.1em;">Your Brief</p>
              <p style="margin:0;font-size:16px;color:#f1f5f9;line-height:1.75;">{top_brief}</p>
            </div>
          </td>
        </tr>"""

    section_html = ""
    for section, (synthesis, stories) in sections_data.items():
        color = SECTIONS[section]["color"]
        section_html += f"""
        <tr>
          <td style="padding:28px 32px 0;">
            <h2 style="margin:0 0 4px;font-size:11px;font-weight:700;color:{color};
                text-transform:uppercase;letter-spacing:0.1em;
                padding-left:10px;border-left:3px solid {color};">{section}</h2>"""
        if synthesis:
            section_html += f"""
            <p style="margin:8px 0 0;font-size:15px;color:#374151;line-height:1.7;
                font-style:italic;padding-left:13px;">{synthesis}</p>"""
        section_html += "</td></tr>"

        for title, link, summary in stories:
            section_html += f"""
        <tr>
          <td style="padding:14px 32px 0;">
            <a href="{link}" style="font-size:16px;font-weight:700;color:#1e293b;
                text-decoration:none;line-height:1.4;display:block;">{title}</a>
            <p style="margin:5px 0 0;font-size:14px;color:#64748b;line-height:1.65;">{summary}</p>
            <a href="{link}" style="display:inline-block;margin-top:6px;font-size:13px;
                color:{color};font-weight:600;text-decoration:none;">Read &rarr;</a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning Brief</title>
</head>
<body style="margin:0;padding:0;background:#e2e8f0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#e2e8f0;padding:28px 0;">
  <tr><td align="center">
  <table width="640" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.1);">

    <tr>
      <td style="background:#0f172a;padding:26px 32px;">
        <p style="margin:0;font-size:12px;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:0.12em;">Morning Brief</p>
        <h1 style="margin:6px 0 0;font-size:28px;font-weight:800;color:#ffffff;line-height:1.2;">{today}</h1>
      </td>
    </tr>

    {weather_html}
    {brief_html}

    <tr><td style="padding:0 32px;">
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0 0;">
    </td></tr>

    {section_html}

    <tr>
      <td style="padding:32px;background:#f8fafc;border-top:1px solid #e2e8f0;margin-top:32px;">
        <p style="margin:0;font-size:13px;color:#94a3b8;text-align:center;">
          Generated automatically every weekday morning &middot; Solihull, UK
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
weather = get_weather()
sections_data = {}
for section, config in SECTIONS.items():
    stories = get_stories(config)
    synthesis, enhanced = ai_enhance(section, stories)
    sections_data[section] = (synthesis, enhanced)

top_brief = ai_top_brief(sections_data, weather)
html = build_html(sections_data, top_brief, weather, today)
ok, detail = send_email(f"Morning Brief — {today}", html)
if not ok:
    print(f"Failed: {detail}", file=sys.stderr)
    sys.exit(1)
print("Brief sent successfully.")
