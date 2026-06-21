import feedparser
import requests
import os
import sys
import json
import html as html_lib
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from openai import OpenAI

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "lucy.pearson@iklcomputing.co.uk")
STAR_SIGN = "virgo"
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
    71: ("Light snow", "&#127784;"), 73: ("Snow", "&#127784;"), 75: ("Heavy snow", "&#127784;"),
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
    "Russian Press": "&#128240;",
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
    "Russian Press": {
        "feeds": [
            "https://www.mk.ru/rss/news/",
            "https://www.pravda.ru/export.xml",
            "https://www.kommersant.ru/RSS/news.xml",
            "https://www.themoscowtimes.com/rss/news",
        ],
        "keywords": [
            # Russian-language political terms (matched before translation)
            "Ð¿Ð¾Ð»Ð¸ÑÐ¸Ðº", "Ð²ÑÐ±Ð¾ÑÑ", "ÐºÑÐµÐ¼Ð»Ñ", "Ð¿ÑÑÐ¸Ð½", "ÑÐ°Ð½ÐºÑÐ¸", "Ð²Ð¾Ð¹Ð½Ð°",
            "Ð¼Ð¸Ð½Ð¸ÑÑÑ", "Ð´ÑÐ¼Ð°", "Ð¿Ð°ÑÐ»Ð°Ð¼ÐµÐ½Ñ", "Ð¿ÑÐµÐ·Ð¸Ð´ÐµÐ½Ñ", "Ð¿ÑÐ°Ð²Ð¸ÑÐµÐ»ÑÑÑÐ²",
            "Ð´ÐµÐ¿ÑÑÐ°Ñ", "Ð¿Ð°ÑÑÐ¸Ñ", "Ð½Ð°ÑÐ¾", "ÑÐºÑÐ°Ð¸Ð½", "Ð¼Ð¸Ð´", "Ð·Ð°ÐºÐ¾Ð½",
            "Ð¿ÐµÑÐµÐ³Ð¾Ð²Ð¾Ñ", "Ð´Ð¸Ð¿Ð»Ð¾Ð¼Ð°Ñ", "Ð²Ð¾Ð¾ÑÑÐ¶", "Ð°ÑÐ¼Ð¸Ñ", "Ð¾Ð¿Ð¿Ð¾Ð·Ð¸Ñ",
            # English terms for Moscow Times
            "politics", "political", "election", "kremlin", "sanction",
            "parliament", "president", "government", "nato", "ukraine",
            "minister", "duma", "diplomat", "military", "opposition",
            "treaty", "ceasefire", "war", "putin", "zelensky",
        ],
        "n": 4, "color": "#b91c1c",
        "translate": True,
        "strict": True,
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


def translate_articles(stories):
    """Batch-translate article titles and summaries to English using GPT."""
    if not stories:
        return stories
    payload = [{"i": i, "title": t, "summary": s}
               for i, (t, url, s, thumb) in enumerate(stories)]
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": (
                "Translate the following news article titles and summaries to English. "
                "If text is already in English keep it unchanged. "
                "Return a JSON array with objects containing 'i', 'title', 'summary'. "
                "No commentary, only the JSON array.\n\n"
                + json.dumps(payload, ensure_ascii=False)
            )}],
            max_tokens=2500,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        translated = list(stories)
        for item in result:
            idx = item["i"]
            _, url, _, thumb = stories[idx]
            translated[idx] = (item["title"], url, item["summary"], thumb)
        return translated
    except Exception:
        return stories


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
    if not config.get("strict") and len(combined) < n:
        for item in fallback:
            if item not in combined:
                combined.append(item)
            if len(combined) >= n:
                break
    if config.get("translate"):
        combined = translate_articles(combined)
    return combined


def ai_enhance(section_name, stories):
    if not stories:
        return None, []
    story_text = "\n\n".join(
        f"TITLE: {t}\nSUMMARY: {s}" for t, url, s, thumb in stories
    )
    prompts = {
        "synthesis": (
            "5-7 sentences giving Lucy a thorough, substantive briefing on this section. "
            "Tell her what is happening, why it matters, what the key tensions or developments are, "
            "and what she should watch. Like a knowledgeable PA who has read everything and is "
            "walking her through it. Direct, warm, no jargon. Use 'you' not 'one'. "
            "Do NOT start your response with the section name or repeat it."
        ),
        "headline": "Rewrite this headline to be sharper and more informative. Max 12 words.",
        "body": "In 2 sentences, explain why this story matters to someone tracking geopolitics and policy.",
    }
    try:
        # Synthesis
        synth_resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": (
                f"You are a knowledgeable PA briefing Lucy on today's '{section_name}' news.\n\n"
                f"{story_text}\n\n{prompts['synthesis']}"
            )}],
            max_tokens=800,
        )
        synthesis = synth_resp.choices[0].message.content.strip()

        # Enhance individual stories
        enhanced = []
        for title, url, summary, thumbnail in stories:
            try:
                h_resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": (
                        f"TITLE: {title}\nSUMMARY: {summary}\n\n{prompts['headline']}"
                    )}],
                    max_tokens=60,
                )
                b_resp = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": (
                        f"TITLE: {title}\nSUMMARY: {summary}\n\n{prompts['body']}"
                    )}],
                    max_tokens=120,
                )
                enh_title = h_resp.choices[0].message.content.strip()
                enh_body = b_resp.choices[0].message.content.strip()
                enhanced.append((enh_title, url, enh_body, thumbnail))
            except Exception:
                enhanced.append((title, url, summary, thumbnail))
        return synthesis, enhanced
    except Exception:
        return None, list(stories)


def ai_horoscope(sign):
    today_str = datetime.now(timezone.utc).strftime("%A %-d %B %Y")
    prompt = (
        f"Write a daily horoscope for {sign.capitalize()} for {today_str}.\n"
        "4-5 sentences. Make it feel genuinely specific to today â weave in themes relevant to "
        f"{sign} like analytical thinking, attention to detail, health, work, relationships, or "
        "personal growth. Be warm, encouraging and grounded. Give it real personality. "
        "Don't start with the sign name or the date. Plain text only."
    )
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


def ai_top_brief(sections_data, weather):
    weather_str = ""
    if weather:
        weather_str = (
            f"Weather in Coventry: {weather['temp']}Â°C, {weather['desc']}, "
            f"wind {weather['wind']}km/h, {weather['precip']}% rain chance."
        )
    summaries = []
    for section, (synthesis, stories) in sections_data.items():
        if synthesis:
            summaries.append(f"{section}: {synthesis[:200]}")
    combined = "\n".join(summaries)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": (
                f"You are Lucy's personal PA. Write a warm, direct 3-4 sentence morning overview "
                f"summarising the key themes across today's news sections. {weather_str}\n\n"
                f"Section summaries:\n{combined}\n\n"
                "Be conversational and highlight the 2-3 most important threads connecting the day's news. "
                "Use 'you' not 'one'. No bullet points."
            )}],
            max_tokens=300,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return None


def build_html(sections_data, top_brief, weather, horoscope, today):
    # ââ weather block ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    weather_html = ""
    if weather:
        weather_html = f"""
<tr>
  <td style="padding:0 20px 20px;">
    <div style="background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%);
        border-radius:12px;padding:20px 24px;color:#ffffff;">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
        <div>
          <span style="font-size:32px;font-weight:800;">{weather['temp']}Â°C</span>
          <span style="font-size:22px;margin-left:8px;">{weather['icon']}</span>
          <div style="font-size:22px;margin-top:4px;">{weather['desc']}</div>
          <div style="font-size:18px;margin-top:6px;color:#93c5fd;">
            &#8593;{weather['hi']}Â° &#8595;{weather['lo']}Â° &nbsp;Â·&nbsp;
            &#127783; {weather['precip']}% &nbsp;Â·&nbsp; &#128168; {weather['wind']} km/h
          </div>
        </div>
        <div style="font-size:18px;color:#bfdbfe;text-align:right;">
          Coventry
        </div>
      </div>
    </div>
  </td>
</tr>"""

    # ââ PA brief block âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    brief_html = ""
    if top_brief:
        brief_html = f"""
<tr>
  <td style="padding:0 20px 20px;">
    <div style="background:#f0f9ff;border-left:5px solid #2563eb;
        border-radius:0 10px 10px 0;padding:20px 22px;">
      <p style="margin:0 0 8px;font-size:13px;font-weight:700;color:#1e40af;
          text-transform:uppercase;letter-spacing:0.08em;">&#128101; Morning Brief</p>
      <p style="margin:0;font-size:18px;color:#1e293b;line-height:1.7;">{html_lib.escape(top_brief)}</p>
    </div>
  </td>
</tr>"""

    # ââ horoscope block ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    horoscope_html = ""
    if horoscope:
        horoscope_html = f"""
<tr>
  <td style="padding:0 20px 12px;">
    <div style="background:#fdf4ff;border-left:5px solid #a855f7;
        border-radius:0 10px 10px 0;padding:20px 22px;">
      <p style="margin:0 0 10px;font-size:14px;font-weight:700;color:#7c3aed;
          text-transform:uppercase;letter-spacing:0.08em;">&#9999;&#65039; Virgo &nbsp;&#183;&nbsp; {today}</p>
      <p style="margin:0;font-size:18px;color:#3b0764;line-height:1.8;">{html_lib.escape(horoscope)}</p>
    </div>
  </td>
</tr>"""

    # ââ news sections ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    sections_html = ""
    for section_name, (synthesis, stories) in sections_data.items():
        if not stories:
            continue
        color = SECTIONS[section_name]["color"]
        icon = SECTION_ICONS.get(section_name, "&#128240;")
        safe_section = html_lib.escape(section_name)

        synthesis_html = ""
        if synthesis:
            safe_synth = html_lib.escape(synthesis)
            synthesis_html = f"""
    <tr>
      <td style="padding:0 20px 16px;">
        <p style="margin:0;font-size:18px;font-weight:600;color:#1e293b;line-height:1.7;">
          {safe_synth}
        </p>
      </td>
    </tr>"""

        articles_html = ""
        for title, url, body, thumbnail in stories:
            title_attr = html_lib.escape(title, quote=True)
            safe_title = html_lib.escape(title)
            safe_body = html_lib.escape(body)
            safe_url = html_lib.escape(url, quote=True)

            thumb_html = ""
            if thumbnail:
                safe_thumb = html_lib.escape(thumbnail, quote=True)
                thumb_html = f"""
          <td class="thumb" width="110" style="padding:0 0 0 16px;vertical-align:top;">
            <a href="{safe_url}" tabindex="-1" aria-hidden="true">
              <img src="{safe_thumb}" width="110" height="74"
                   alt="{title_attr}"
                   style="display:block;border-radius:8px;object-fit:cover;width:110px;height:74px;">
            </a>
          </td>"""

            articles_html += f"""
    <tr>
      <td style="padding:0 20px 20px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="vertical-align:top;">
              <a href="{safe_url}" style="text-decoration:none;color:#1e293b;"
                 aria-label="Read: {title_attr}">
                <p style="margin:0 0 8px;font-size:24px;font-weight:700;line-height:1.4;
                    color:#1e293b;">{safe_title}</p>
              </a>
              <p style="margin:0 0 10px;font-size:18px;color:#374151;line-height:1.6;">
                {safe_body}
              </p>
              <a href="{safe_url}"
                 aria-label="Read: {title_attr}"
                 style="font-size:16px;color:{color};font-weight:600;text-decoration:none;
                        display:inline-block;padding:10px 0;">
                Read &#8594;
              </a>
            </td>{thumb_html}
          </tr>
        </table>
      </td>
    </tr>
    <tr><td style="padding:0 20px;"><hr style="border:none;border-top:1px solid #f1f5f9;margin:0 0 16px;"></td></tr>"""

        sections_html += f"""
<tr>
  <td style="background:{color};padding:14px 20px;">
    <h2 style="margin:0;font-size:18px;font-weight:700;color:#ffffff;letter-spacing:0.04em;">
      {icon} {safe_section}
    </h2>
  </td>
</tr>
{synthesis_html}
{articles_html}"""

    # ââ full HTML ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning Brief &#8211; {today}</title>
<style>
  body {{ margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
  @media only screen and (max-width: 620px) {{
    .email-outer {{ padding: 0 !important; }}
    .email-card {{ border-radius: 0 !important; box-shadow: none !important; }}
    .hd {{ padding: 22px 18px !important; }}
    .hd h1 {{ font-size: 26px !important; }}
    .thumb {{ display: none !important; width: 0 !important; padding: 0 !important; overflow: hidden !important; }}
  }}
</style>
</head>
<body>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    style="background:#f1f5f9;min-height:100vh;">
  <tr>
    <td class="email-outer" align="center" style="padding:24px 16px;">
      <table class="email-card" role="presentation" width="100%" cellpadding="0" cellspacing="0"
          style="background:#ffffff;max-width:620px;border-radius:14px;overflow:hidden;
                 box-shadow:0 4px 24px rgba(0,0,0,0.12);">

        <!-- Header -->
        <tr>
          <td class="hd" style="background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 100%);
              padding:28px 24px;">
            <h1 style="margin:0;font-size:30px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">
              &#9788; Morning Brief
            </h1>
            <p style="margin:6px 0 0;font-size:16px;color:#94a3b8;">{today}</p>
          </td>
        </tr>

        <!-- Weather -->
        {weather_html}

        <!-- PA brief -->
        {brief_html}

        <!-- Horoscope -->
        {horoscope_html}

        <!-- Divider -->
        <tr><td style="padding:0 20px 20px;">
          <hr style="border:none;border-top:2px solid #e2e8f0;margin:0;">
        </td></tr>

        <!-- News sections -->
        {sections_html}

        <!-- Footer -->
        <tr>
          <td style="padding:24px 20px;background:#f8fafc;border-top:1px solid #e2e8f0;">
            <p style="margin:0;font-size:16px;color:#64748b;text-align:center;">
              Delivered by Morning Brief &nbsp;&#183;&nbsp; {today}
            </p>
          </td>
        </tr>

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""
    return html


# ââ main âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
today = datetime.now(timezone.utc).strftime("%A %-d %B %Y")
weather = get_weather()
horoscope = ai_horoscope(STAR_SIGN)
sections_data = {}
for section, config in SECTIONS.items():
    stories = get_stories(config)
    synthesis, enhanced = ai_enhance(section, stories)
    sections_data[section] = (synthesis, enhanced)
top_brief = ai_top_brief(sections_data, weather)
html = build_html(sections_data, top_brief, weather, horoscope, today)

payload = {
    "from": "Morning Brief <onboarding@resend.dev>",
    "to": [TO_EMAIL],
    "subject": f"â Morning Brief â {today}",
    "html": html,
}
resp = requests.post(
    "https://api.resend.com/emails",
    headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
    json=payload,
    timeout=30,
)
resp.raise_for_status()
print(f"Sent to {TO_EMAIL}: {resp.json()}")
