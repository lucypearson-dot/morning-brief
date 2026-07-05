import feedparser
import requests
import os
import sys
import json
import html as html_lib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from openai import OpenAI

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
TO_EMAIL = os.environ.get("TO_EMAIL", "lucy.pearson@iklcomputing.co.uk")
LONDON = ZoneInfo("Europe/London")
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
            "политик", "выбор", "кремл", "путин", "санкц", "войн",
            "министр", "дум", "парламент", "президент", "правительств",
            "депутат", "парти", "нато", "украин", "мид", "закон",
            "переговор", "дипломат", "вооруж", "арми", "оппозици",
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
                # Solihull (these coordinates were previously mislabelled "Coventry" below)
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
                enh_title = h_resp.choices[0].message.content.strip()
                enhanced.append((enh_title, url, summary, thumbnail))
            except Exception:
                enhanced.append((title, url, summary, thumbnail))
        return synthesis, enhanced
    except Exception:
        return None, list(stories)


def ai_top_brief(sections_data, weather):
    weather_str = ""
    if weather:
        weather_str = (
            f"Weather in Solihull: {weather['temp']}°C, {weather['desc']}, "
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


CREAM = "#FDF3DD"
MINT = "#DFF3EF"
INK = "#1a1a2e"
MONO = "'Space Mono',ui-monospace,Menlo,monospace"
DISPLAY = "'Space Grotesk',-apple-system,BlinkMacSystemFont,sans-serif"


def build_html(sections_data, top_brief, weather, today):
    # ---- weather line (short, sits under the intro paragraph) ----
    weather_html = ""
    if weather:
        weather_html = f"""
          <p style="margin:14px 0 0;font-size:15px;color:#57534e;font-family:{MONO};">
            <span aria-hidden="true">{weather['icon']}</span> It's
            <strong style="font-size:20px;color:{INK};">{weather['temp']}&deg;C</strong>
            and {weather['desc'].lower()} in Solihull &nbsp;&#183;&nbsp;
            &#8593;{weather['hi']}&deg; &#8595;{weather['lo']}&deg; &nbsp;&#183;&nbsp; {weather['precip']}% rain
          </p>"""

    # ---- "sections covered" checklist (2 columns, so 7 sections don't push
    # a full extra screen of scrolling before any actual news appears) ----
    section_names = list(SECTIONS)
    checklist_rows = ""
    for i in range(0, len(section_names), 2):
        row_names = section_names[i:i + 2]
        cells = ""
        for section_name in row_names:
            included = bool(sections_data.get(section_name, (None, []))[1])
            accent = SECTIONS[section_name]["color"] if included else "#6b625b"
            text_style = "none" if included else "line-through"
            mark = "&#10003;" if included else "&#10007;"
            cells += f"""
        <td width="50%" style="padding:5px 8px 5px 0;font-family:{MONO};font-size:15px;vertical-align:top;">
          <span style="color:{accent};font-weight:700;">{mark}</span>
          <span style="color:{'#1c1917' if included else '#6b625b'};text-decoration:{text_style};margin-left:10px;">
            {html_lib.escape(section_name)}
          </span>
        </td>"""
        if len(row_names) == 1:
            cells += '<td width="50%"></td>'
        checklist_rows += f"<tr>{cells}</tr>"

    # ---- news sections ----
    sections_html = ""
    first_section = True
    for section_name, (synthesis, stories) in sections_data.items():
        if not stories:
            continue
        color = SECTIONS[section_name]["color"]
        icon = SECTION_ICONS.get(section_name, "&#128240;")
        safe_section = html_lib.escape(section_name)

        # A firmer break between whole sections, distinct from the lighter
        # per-article dividers, so the eye knows a new topic has started.
        section_break = "" if first_section else """
<tr><td style="padding:0 24px;"><hr style="border:none;border-top:2px solid #e7e5e4;margin:0;"></td></tr>"""
        first_section = False

        synthesis_html = ""
        if synthesis:
            safe_synth = html_lib.escape(synthesis)
            synthesis_html = f"""
    <tr>
      <td style="padding:0 24px 18px;">
        <div style="background:#faf9f7;border-left:3px solid {color};
            border-radius:0 8px 8px 0;padding:14px 16px;">
          <p style="margin:0;font-size:18px;font-weight:600;color:{INK};line-height:1.35;">
            {safe_synth}
          </p>
        </div>
      </td>
    </tr>"""

        # A plain stacked list of links per section, rather than a photo +
        # headline + summary card per story - quicker to scan, click through
        # for the detail instead of reading a summary here.
        articles_html = ""
        for title, url, body, thumbnail in stories:
            title_attr = html_lib.escape(title, quote=True)
            safe_title = html_lib.escape(title)
            safe_url = html_lib.escape(url, quote=True)

            articles_html += f"""
    <tr>
      <td style="padding:0 24px;border-bottom:1px solid #f1f5f9;">
        <h3 style="margin:0;font-size:17px;font-weight:600;line-height:1.4;">
          <a href="{safe_url}" title="{title_attr}"
             style="display:block;padding:12px 0;color:{INK};text-decoration:none;">
            <span aria-hidden="true" style="color:{color};font-weight:700;">&#8594;</span>
            {safe_title}
          </a>
        </h3>
      </td>
    </tr>"""
        articles_html += """
    <tr><td style="padding:0 24px 20px;"></td></tr>"""

        sections_html += f"""
{section_break}
<tr>
  <td align="center" style="padding:34px 24px 18px;">
    <table role="presentation" cellpadding="0" cellspacing="0">
      <tr>
        <td style="background:{color};border-radius:999px;padding:10px 22px;text-align:center;">
          <h2 style="margin:0;display:inline;font-size:15px;font-weight:700;color:#ffffff;
              letter-spacing:0.04em;text-transform:uppercase;font-family:{MONO};">
            <span style="font-size:16px;" aria-hidden="true">{icon}</span> {safe_section}
          </h2>
        </td>
      </tr>
    </table>
  </td>
</tr>
{synthesis_html}
{articles_html}"""

    # ---- full HTML ----
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning Brief &#8211; {today}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700;800&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
  body {{ margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; }}
  h1, h2, h3 {{ text-wrap: balance; }}
  p {{ text-wrap: pretty; }}
  @media only screen and (max-width: 620px) {{
    .email-outer {{ padding: 0 !important; }}
    .hd h1 {{ font-size: 34px !important; }}
  }}
</style>
</head>
<body>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
    style="background:#f1f5f9;min-height:100vh;">
  <tr>
    <td class="email-outer" align="center" style="padding:24px 16px;">
      <table class="email-card" role="presentation" width="100%" cellpadding="0" cellspacing="0"
          style="background:#ffffff;max-width:620px;overflow:hidden;">

        <!-- Header -->
        <tr>
          <td class="hd" align="center" style="background:{CREAM};padding:36px 24px 6px;">
            <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 auto;">
              <tr>
                <td width="52" height="52" style="width:52px;height:52px;border:2px solid {INK};
                    border-radius:16px;text-align:center;vertical-align:middle;font-size:22px;
                    line-height:52px;color:{INK};" aria-hidden="true">&#9788;</td>
              </tr>
            </table>
            <p style="margin:16px 0 0;font-size:12px;font-weight:700;letter-spacing:0.2em;
                color:#57534e;text-transform:uppercase;font-family:{MONO};">{today}</p>
            <h1 style="margin:6px 0 0;font-size:44px;font-weight:800;color:{INK};
                font-family:{DISPLAY};letter-spacing:-1px;">Morning Brief</h1>
          </td>
        </tr>

        <!-- Intro -->
        <tr>
          <td align="center" style="background:{CREAM};padding:14px 30px 32px;">
            <p style="margin:0;font-size:17px;line-height:1.4;color:#3f3a34;text-align:center;">
              {html_lib.escape(top_brief) if top_brief else f"Good morning, Lucy &#8212; here's what's crossed the wires."}
            </p>
            {weather_html}
          </td>
        </tr>

        <!-- Sections covered checklist -->
        <tr>
          <td style="background:{CREAM};padding:0 24px 34px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                style="background:{MINT};border-radius:12px;padding:18px 22px;">
              <tr>
                <td style="font-family:{MONO};font-size:11px;font-weight:700;letter-spacing:0.14em;
                    color:#0f766e;text-transform:uppercase;padding-bottom:8px;">
                  In today's brief
                </td>
              </tr>
              {checklist_rows}
            </table>
          </td>
        </tr>

        <!-- News sections -->
        {sections_html}

        <!-- Footer -->
        <tr>
          <td align="center" style="padding:30px 20px;background:{CREAM};">
            <div aria-hidden="true" style="width:36px;height:36px;border:2px solid {INK};border-radius:11px;
                margin:0 auto 12px;text-align:center;line-height:36px;font-size:15px;color:{INK};">&#9788;</div>
            <p style="margin:0;font-size:14px;color:#57534e;text-align:center;font-family:{MONO};">
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


# ---- main ----
now_london = datetime.now(LONDON)
today = now_london.strftime("%A %-d %B %Y")

# GitHub delays "schedule" runs unpredictably (we've seen 2-4.5 hour delays),
# so the workflow polls every 15 minutes from 5am-10am UTC instead of trying
# to land on one exact minute. Only skip if it's still before 7am London -
# once past that, send on the first run that gets here (the workflow's cache
# check stops it from sending a second time same day). Manual runs always go through.
if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" and now_london.hour < 7:
    print(f"Skipping: London time is {now_london.strftime('%H:%M')}, before 7am.")
    sys.exit(0)

weather = get_weather()
sections_data = {}
for section, config in SECTIONS.items():
    stories = get_stories(config)
    synthesis, enhanced = ai_enhance(section, stories)
    sections_data[section] = (synthesis, enhanced)
top_brief = ai_top_brief(sections_data, weather)
html = build_html(sections_data, top_brief, weather, today)

payload = {
    "from": "Morning Brief <onboarding@resend.dev>",
    "to": [TO_EMAIL],
    "subject": f"☀ Morning Brief – {today}",
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

with open(".sent-marker", "w") as f:
    f.write(now_london.isoformat())
