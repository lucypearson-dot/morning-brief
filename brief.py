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

SECTION_ICONS = {
    "Foreign Policy": "&#127758;",
    "Russia & Ukraine": "&#9876;",
    "NATO": "&#128737;",
    "Analyst Views": "&#128203;",
    "UK Politics": "&#127963;",
    "Economy": "&#128200;",
    "Health": "&#129658;",
    "Skincare & Wellness": "&#10024;",
    "Food & Drink": "&#127869;",
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

def get_thumbnail(entry):
    try:
        if hasattr(entry, 'media_thumbnail') and entry.media_thumbnail:
            return entry.media_thumbnail[0].get('url', '')
        if hasattr(entry, 'media_content') and entry.media_content:
            for m in entry.media_content:
                if m.get('url') and 'image' in m.get('type', ''):
                    return m['url']
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enc in entry.enclosures:
                if 'image' in enc.get('type', ''):
                    return enc.get('href', '')
    except Exception:
        pass
    return ''

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
            thumbnail = get_thumbnail(entry)
            if matches(entry.title, summary, keywords):
                hits.append((entry.title, entry.link, summary, thumbnail))
            else:
                fallback.append((entry.title, entry.link, summary, thumbnail))
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
        for i, (title, _, summary, _thumb) in enumerate(stories)
    )
    prompt = f"""You are Lucy's personal assistant giving her a morning briefing. Section: {section_name}.

Articles:
{articles_text}

Respond with valid JSON only (no markdown fences):
{{
  "synthesis": "2-3 sentences summarising the key developments in this section right now — like a PA giving Lucy a quick verbal briefing on everything happening here. Direct, warm, no jargon. Use 'you' not 'one'.",
  "summaries": ["One crisp sentence: the single most important fact from article 1.", "One crisp sentence: the single most important fact from article 2."]
}}

Number of summaries must equal {len(stories)}."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
        )
        data = json.loads(response.choices[0].message.content)
        synthesis = data.get("synthesis", "")
        new_summaries = data.get("summaries", [])
        enhanced = [
            (title, link, new_summaries[i] if i < len(new_summaries) else summary, thumb)
            for i, (title, link, summary, thumb) in enumerate(stories)
        ]
        return synthesis, enhanced
    except Exception:
        return None, stories

def ai_top_brief(sections_data, weather):
    lines = []
    for section, (_, stories) in sections_data.items():
        for title, _, summary, _thumb in stories:
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
          <td style="background:#f8fafc;border-bottom:1px solid #e2e8f0;padding:18px 32px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-size:38px;width:52px;">{weather['icon']}</td>
                <td style="padding-left:14px;">
                  <span style="font-size:28px;font-weight:700;color:#0f172a;">{weather['temp']}&deg;C</span>
                  <span style="font-size:19px;color:#64748b;margin-left:10px;">{weather['desc']}</span>
                  <span style="font-size:17px;color:#94a3b8;margin-left:10px;">H:{weather['hi']}&deg; L:{weather['lo']}&deg;</span>
                </td>
                <td align="right" style="font-size:17px;color:#64748b;">
                  {weather['precip']}% rain &nbsp;&#183;&nbsp; {weather['wind']} km/h wind<br>
                  <span style="font-size:16px;color:#94a3b8;">Solihull, UK</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    brief_html = ""
    if top_brief:
        brief_html = f"""
        <tr>
          <td style="padding:26px 32px 8px;">
            <div style="background:#0f172a;border-radius:10px;padding:24px 28px;">
              <p style="margin:0 0 10px;font-size:13px;font-weight:700;color:#60a5fa;
                  text-transform:uppercase;letter-spacing:0.1em;">&#128338; Your Brief</p>
              <p style="margin:0;font-size:20px;color:#f1f5f9;line-height:1.8;">{top_brief}</p>
            </div>
          </td>
        </tr>"""

    section_html = ""
    for section, (synthesis, stories) in sections_data.items():
        color = SECTIONS[section]["color"]
        icon = SECTION_ICONS.get(section, "&#9679;")

        # Section header block with colored background and AI summary as headline
        section_html += f"""
        <tr>
          <td style="padding:32px 32px 0;">
            <div style="background:{color}18;border-left:5px solid {color};border-radius:0 8px 8px 0;padding:18px 20px;">
              <p style="margin:0 0 8px;font-size:13px;font-weight:700;color:{color};
                  text-transform:uppercase;letter-spacing:0.1em;">{icon}&nbsp; {section}</p>"""
        if synthesis:
            section_html += f"""
              <p style="margin:0;font-size:20px;font-weight:600;color:#1e293b;line-height:1.65;">{synthesis}</p>"""
        section_html += """
            </div>
          </td>
        </tr>"""

        for title, link, summary, thumbnail in stories:
            if thumbnail:
                article_inner = f"""
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding-right:16px;vertical-align:top;">
                  <a href="{link}" style="font-size:20px;font-weight:700;color:#1e293b;
                      text-decoration:none;line-height:1.4;display:block;">{title}</a>
                  <p style="margin:8px 0 0;font-size:18px;color:#475569;line-height:1.75;">{summary}</p>
                  <a href="{link}" style="display:inline-block;margin-top:10px;font-size:16px;
                      color:{color};font-weight:600;text-decoration:none;">Read &rarr;</a>
                </td>
                <td width="140" valign="top" style="padding-top:3px;">
                  <a href="{link}">
                    <img src="{thumbnail}" width="140" height="95"
                      style="border-radius:8px;display:block;object-fit:cover;"
                      alt="">
                  </a>
                </td>
              </tr>
            </table>"""
            else:
                article_inner = f"""
                  <a href="{link}" style="font-size:20px;font-weight:700;color:#1e293b;
                      text-decoration:none;line-height:1.4;display:block;">{title}</a>
                  <p style="margin:8px 0 0;font-size:18px;color:#475569;line-height:1.75;">{summary}</p>
                  <a href="{link}" style="display:inline-block;margin-top:10px;font-size:16px;
                      color:{color};font-weight:600;text-decoration:none;">Read &rarr;</a>"""
            section_html += f"""
        <tr>
          <td style="padding:18px 32px 0;">{article_inner}
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
  <table width="660" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.12);">
    <tr>
      <td style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);padding:30px 32px;">
        <p style="margin:0;font-size:14px;font-weight:700;color:#3b82f6;text-transform:uppercase;letter-spacing:0.12em;">&#9728; Morning Brief</p>
        <h1 style="margin:8px 0 0;font-size:34px;font-weight:800;color:#ffffff;line-height:1.2;">{today}</h1>
      </td>
    </tr>
    {weather_html}
    {brief_html}
    <tr><td style="padding:0 32px;">
      <hr style="border:none;border-top:1px solid #e2e8f0;margin:26px 0 0;">
    </td></tr>
    {section_html}
    <tr>
      <td style="padding:36px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;margin-top:32px;">
        <p style="margin:0;font-size:15px;color:#94a3b8;text-align:center;">
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
