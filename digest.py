#!/usr/bin/env python3
"""
RSS Daily Digest - Recommended by Andrej Karpathy
Fetches 92 top HN blogs via RSS, summarizes with Claude, generates HTML, emails it.
"""

import os
import sys
import json
import time
import smtplib
import feedparser
import anthropic
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# CONFIG (auto-strip whitespace/newlines from secrets)
# ============================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GMAIL_USER       = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
RECIPIENT_EMAIL  = os.environ.get("RECIPIENT_EMAIL", "").strip() or GMAIL_USER
LOOKBACK_HOURS   = int(os.environ.get("LOOKBACK_HOURS", "24"))
MAX_ARTICLES     = int(os.environ.get("MAX_ARTICLES", "30"))
MODEL            = os.environ.get("MODEL", "claude-sonnet-4-20250514")

# Debug: print masked key info
if ANTHROPIC_API_KEY:
    print(f"[DEBUG] API Key loaded: {ANTHROPIC_API_KEY[:10]}...{ANTHROPIC_API_KEY[-4:]} (length={len(ANTHROPIC_API_KEY)})")
else:
    print("[ERROR] ANTHROPIC_API_KEY is empty!")

# All 92 feeds from Karpathy's recommendation
FEEDS = [
    ("Simon Willison", "https://simonwillison.net/atom/everything/"),
    ("Jeff Geerling", "https://www.jeffgeerling.com/blog.xml"),
    ("Sean Goedecke", "https://www.seangoedecke.com/rss.xml"),
    ("Krebs on Security", "https://krebsonsecurity.com/feed/"),
    ("Daring Fireball", "https://daringfireball.net/feeds/main"),
    ("Eric Migicovsky", "https://ericmigi.com/rss.xml"),
    ("antirez", "http://antirez.com/rss"),
    ("Ibrahim Diallo", "https://idiallo.com/feed.rss"),
    ("Maurycy", "https://maurycyz.com/index.xml"),
    ("Pluralistic (Doctorow)", "https://pluralistic.net/feed/"),
    ("Terence Eden", "https://shkspr.mobi/blog/feed/"),
    ("lcamtuf", "https://lcamtuf.substack.com/feed"),
    ("Mitchell Hashimoto", "https://mitchellh.com/feed.xml"),
    ("Dynomight", "https://dynomight.net/feed.xml"),
    ("CKS (Univ of Toronto)", "https://utcc.utoronto.ca/~cks/space/blog/?atom"),
    ("Xe Iaso", "https://xeiaso.net/blog.rss"),
    ("The Old New Thing", "https://devblogs.microsoft.com/oldnewthing/feed"),
    ("Ken Shirriff", "https://www.righto.com/feeds/posts/default"),
    ("Armin Ronacher", "https://lucumr.pocoo.org/feed.atom"),
    ("Skyfall", "https://skyfall.dev/rss.xml"),
    ("Gary Marcus", "https://garymarcus.substack.com/feed"),
    ("Rachel by the Bay", "https://rachelbythebay.com/w/atom.xml"),
    ("Dan Abramov", "https://overreacted.io/rss.xml"),
    ("Tim Shutt", "https://timsh.org/rss/"),
    ("John D. Cook", "https://www.johndcook.com/blog/feed/"),
    ("Giles Thomas", "https://gilesthomas.com/feed/rss.xml"),
    ("matklad", "https://matklad.github.io/feed.xml"),
    ("Derek Thompson", "https://www.theatlantic.com/feed/author/derek-thompson/"),
    ("Evan Hahn", "https://evanhahn.com/feed.xml"),
    ("Terrible Software", "https://terriblesoftware.org/feed/"),
    ("Rakhim", "https://rakhim.exotext.com/rss.xml"),
    ("Joan Westenberg", "https://joanwestenberg.com/rss"),
    ("Xania", "https://xania.org/feed"),
    ("Micah Lee", "https://micahflee.com/feed/"),
    ("Andrew Nesbitt", "https://nesbitt.io/feed.xml"),
    ("Construction Physics", "https://www.construction-physics.com/feed"),
    ("Tedium", "https://feed.tedium.co/"),
    ("Susam Pal", "https://susam.net/feed.xml"),
    ("Entropic Thoughts", "https://entropicthoughts.com/feed.xml"),
    ("Hillel Wayne", "https://buttondown.com/hillelwayne/rss"),
    ("Dwarkesh Patel", "https://www.dwarkeshpatel.com/feed"),
    ("Fernando Borretti", "https://borretti.me/feed.xml"),
    ("Ed Zitron", "https://www.wheresyoured.at/rss/"),
    ("Jay D.", "https://jayd.ml/feed.xml"),
    ("Max Woolf", "https://minimaxir.com/index.xml"),
    ("geohot", "https://geohot.github.io/blog/feed.xml"),
    ("Paul Graham", "http://www.aaronsw.com/2002/feeds/pgessays.rss"),
    ("The Digital Antiquarian", "https://www.filfre.net/feed/"),
    ("Jim Nielsen", "https://blog.jim-nielsen.com/feed.xml"),
    ("Dave Farquhar", "https://dfarq.homeip.net/feed/"),
    ("jyn", "https://jyn.dev/atom.xml"),
    ("Geoffrey Litt", "https://www.geoffreylitt.com/feed.xml"),
    ("Doug Brown", "https://www.downtowndougbrown.com/feed/"),
    ("Brutecat", "https://brutecat.com/rss.xml"),
    ("Eli Bendersky", "https://eli.thegreenplace.net/feeds/all.atom.xml"),
    ("Abort, Retry, Fail?", "https://www.abortretry.fail/feed"),
    ("Fabien Sanglard", "https://fabiensanglard.net/rss.xml"),
    ("Old VCR", "https://oldvcr.blogspot.com/feeds/posts/default"),
    ("Bogdan", "https://bogdanthegeek.github.io/blog/index.xml"),
    ("Hugo Tunius", "https://hugotunius.se/feed.xml"),
    ("Gwern", "https://gwern.substack.com/feed"),
    ("Bert Hubert", "https://berthub.eu/articles/index.xml"),
    ("Chad Nauseam", "https://chadnauseam.com/rss.xml"),
    ("Simone", "https://simone.org/feed/"),
    ("IT Notes (Dragas)", "https://it-notes.dragas.net/feed/"),
    ("Beej", "https://beej.us/blog/rss.xml"),
    ("Hey Paris", "https://hey.paris/index.xml"),
    ("Daniel Wirtz", "https://danielwirtz.com/rss.xml"),
    ("Mat Duggan", "https://matduggan.com/rss/"),
    ("Refactoring English", "https://refactoringenglish.com/index.xml"),
    ("Works on My Machine", "https://worksonmymachine.substack.com/feed"),
    ("Philip Laine", "https://philiplaine.com/index.xml"),
    ("Steve Blank", "https://steveblank.com/feed/"),
    ("Max Bernstein", "https://bernsteinbear.com/feed.xml"),
    ("Daniel Delaney", "https://danieldelaney.net/feed"),
    ("Troy Hunt", "https://www.troyhunt.com/rss/"),
    ("Herman", "https://herman.bearblog.dev/feed/"),
    ("Tom Renner", "https://tomrenner.com/index.xml"),
    ("Pixelmelt", "https://blog.pixelmelt.dev/rss/"),
    ("Martin Alderson", "https://martinalderson.com/feed.xml"),
    ("Daniel Hooper", "https://danielchasehooper.com/feed.xml"),
    ("Simon Tatham", "https://www.chiark.greenend.org.uk/~sgtatham/quasiblog/feed.xml"),
    ("Grant Slatton", "https://grantslatton.com/rss.xml"),
    ("Experimental History", "https://www.experimental-history.com/feed"),
    ("Anil Dash", "https://anildash.com/feed.xml"),
    ("Aresluna", "https://aresluna.org/main.rss"),
    ("Michael Stapelberg", "https://michael.stapelberg.ch/feed.xml"),
    ("Miguel Grinberg", "https://blog.miguelgrinberg.com/feed"),
    ("Keygen", "https://keygen.sh/blog/feed.xml"),
    ("Matthew Garrett", "https://mjg59.dreamwidth.org/data/rss"),
    ("computer.rip", "https://computer.rip/rss.xml"),
    ("Ted Unangst", "https://www.tedunangst.com/flak/rss"),
]

# ============================================================
# 1. FETCH RSS
# ============================================================
def fetch_single_feed(name, url, cutoff):
    """Fetch a single feed and return recent articles."""
    articles = []
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": "RSS-Digest/1.0"})
        for entry in feed.entries:
            published = None
            for attr in ("published_parsed", "updated_parsed"):
                t = getattr(entry, attr, None)
                if t:
                    from time import mktime
                    published = datetime.fromtimestamp(mktime(t), tz=timezone.utc)
                    break
            if not published:
                continue
            if published >= cutoff:
                articles.append({
                    "source": name,
                    "title":  entry.get("title", "Untitled"),
                    "link":   entry.get("link", ""),
                    "published": published.strftime("%Y-%m-%d %H:%M"),
                    "summary": (entry.get("summary") or entry.get("description") or "")[:2000],
                })
    except Exception as e:
        print(f"  [WARN] Failed to fetch {name}: {e}")
    return articles


def fetch_all_feeds():
    """Fetch all feeds in parallel, return articles from last LOOKBACK_HOURS."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    all_articles = []
    print(f"Fetching {len(FEEDS)} feeds (cutoff: {cutoff.strftime('%Y-%m-%d %H:%M UTC')})...")

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(fetch_single_feed, name, url, cutoff): name
            for name, url in FEEDS
        }
        for future in as_completed(futures):
            articles = future.result()
            if articles:
                all_articles.extend(articles)
                print(f"  ✓ {futures[future]}: {len(articles)} new article(s)")

    all_articles.sort(key=lambda x: x["published"], reverse=True)
    if len(all_articles) > MAX_ARTICLES:
        print(f"  Capping from {len(all_articles)} to {MAX_ARTICLES} articles")
        all_articles = all_articles[:MAX_ARTICLES]

    print(f"Total: {len(all_articles)} articles to summarize")
    return all_articles

# ============================================================
# 2. SUMMARIZE WITH CLAUDE (structured JSON + bilingual)
# ============================================================
def summarize_articles(articles):
    """Use Claude to generate a structured bilingual daily digest as JSON."""
    if not articles:
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    articles_text = ""
    for i, a in enumerate(articles, 1):
        articles_text += f"""
---
Article {i}:
Source: {a['source']}
Title: {a['title']}
Link: {a['link']}
Published: {a['published']}
Content preview: {a['summary'][:800]}
---
"""

    prompt = f"""You are a senior tech analyst creating a bilingual (English + Chinese) daily digest.

Here are {len(articles)} new blog posts from top tech blogs (curated by Andrej Karpathy):

{articles_text}

Return a JSON object with this exact structure:
{{
  "highlights": [
    {{
      "title": "article title",
      "source": "author/blog name",
      "date": "YYYY-MM-DD",
      "link": "article url",
      "summary_en": "one-line English summary",
      "summary_cn": "一句话中文摘要"
    }}
  ],
  "categories": [
    {{
      "name": "Category Name",
      "articles": [
        {{
          "title": "article title",
          "source": "author/blog name",
          "date": "YYYY-MM-DD",
          "link": "article url",
          "summary_en": "one-line English summary + why it matters",
          "summary_cn": "中文摘要 + 为什么重要"
        }}
      ]
    }}
  ],
  "takeaway_en": "One paragraph synthesis of today's most important theme in English",
  "takeaway_cn": "今日最重要主题的中文总结段落"
}}

Rules:
- highlights: pick the 3-5 most important/interesting articles
- categories: group ALL articles into categories like AI/ML, Software Engineering, Security, Systems/Infrastructure, etc.
- Every article must appear in exactly one category
- Every article MUST have both English and Chinese summaries
- Keep summaries concise (1-2 sentences)
- Return ONLY valid JSON, no markdown code fences, no extra text"""

    for attempt in range(3):
        try:
            print(f"Summarizing with Claude (attempt {attempt + 1}/3)...")
            response = client.messages.create(
                model=MODEL,
                max_tokens=16000,
                messages=[{"role": "user", "content": prompt}],
            )

            # Check if response was truncated due to token limit
            if response.stop_reason == "max_tokens":
                print(f"[WARN] Response truncated at max_tokens (attempt {attempt + 1})")
                if attempt < 2:
                    print("  Retrying...")
                    time.sleep(5)
                    continue
                else:
                    raise RuntimeError("Claude response was truncated after 3 attempts. Try reducing MAX_ARTICLES.")

            text = response.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            if text.startswith("json"):
                text = text[4:].strip()
            return json.loads(text)

        except anthropic.AuthenticationError as e:
            print(f"[ERROR] Authentication failed: {e}")
            print(f"[DEBUG] Key starts with: {ANTHROPIC_API_KEY[:12]}...")
            print("[HINT] Please check your ANTHROPIC_API_KEY secret in GitHub Settings.")
            raise
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
            print(f"[WARN] Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                wait = 10 * (attempt + 1)
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
        except json.JSONDecodeError as e:
            print(f"[WARN] JSON parse failed (attempt {attempt + 1}): {e}")
            if attempt < 2:
                print("  Retrying...")
                time.sleep(5)
            else:
                raise

# ============================================================
# 3. GENERATE HTML
# ============================================================
def esc(text):
    """Escape HTML special characters."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))

def generate_html(digest_data, articles, output_path="digest.html"):
    """Generate a beautifully formatted HTML digest (Style 1: Minimalist)."""
    today = datetime.now().strftime("%Y-%m-%d")
    weekday = datetime.now().strftime("%A")

    # Build highlights HTML
    highlights_html = ""
    for h in digest_data.get("highlights", []):
        cn_part = ""
        if h.get("summary_cn"):
            cn_part = f'<div class="cn">{esc(h["summary_cn"])}</div>'
        highlights_html += f"""
    <div class="highlight-item">
      <h3><a href="{esc(h.get('link', '#'))}">{esc(h['title'])}</a></h3>
      <div class="source">{esc(h.get('source', ''))} · {esc(h.get('date', ''))}</div>
      <p>{esc(h.get('summary_en', ''))}</p>
      {cn_part}
    </div>"""

    # Build categories HTML
    categories_html = ""
    for cat in digest_data.get("categories", []):
        articles_in_cat = ""
        for a in cat.get("articles", []):
            cn_part = ""
            if a.get("summary_cn"):
                cn_part = f'<div class="cn-note">{esc(a["summary_cn"])}</div>'
            articles_in_cat += f"""
      <div class="article">
        <div class="title"><a href="{esc(a.get('link', '#'))}">{esc(a['title'])}</a></div>
        <div class="meta">{esc(a.get('source', ''))} · {esc(a.get('date', ''))}</div>
        <div class="summary">{esc(a.get('summary_en', ''))}</div>
        {cn_part}
      </div>"""
        categories_html += f"""
    <div class="category">
      <div class="category-name">{esc(cat['name'])}</div>
      {articles_in_cat}
    </div>"""

    # Takeaway
    takeaway_en = esc(digest_data.get("takeaway_en", ""))
    takeaway_cn = esc(digest_data.get("takeaway_cn", ""))
    takeaway_cn_html = ""
    if takeaway_cn:
        takeaway_cn_html = f'<div class="cn-takeaway">{takeaway_cn}</div>'

    # Full article index
    index_html = ""
    for i, a in enumerate(articles, 1):
        index_html += f"""
    <div class="index-item">{i}. [{esc(a['source'])}] <a href="{esc(a['link'])}">{esc(a['title'])}</a></div>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Tech Digest - {today}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: 'Georgia', 'Times New Roman', serif; background: #f9f7f4; color: #2c2c2c; line-height: 1.7; }}
  .container {{ max-width: 680px; margin: 0 auto; padding: 40px 24px; }}

  .header {{ text-align: center; padding-bottom: 32px; border-bottom: 3px double #333; margin-bottom: 36px; }}
  .header h1 {{ font-size: 32px; font-weight: 400; letter-spacing: 4px; text-transform: uppercase; color: #1a1a1a; }}
  .header .date {{ font-size: 14px; color: #888; margin-top: 8px; letter-spacing: 2px; }}
  .header .stats {{ font-size: 13px; color: #999; margin-top: 4px; }}

  .section-title {{ font-size: 13px; text-transform: uppercase; letter-spacing: 3px; color: #b5838d; margin-bottom: 20px; font-weight: 600; }}

  .highlight-item {{ margin-bottom: 20px; padding-left: 16px; border-left: 2px solid #b5838d; }}
  .highlight-item h3 {{ font-size: 17px; font-weight: 600; color: #1a1a1a; margin-bottom: 4px; }}
  .highlight-item h3 a {{ color: #1a1a1a; text-decoration: none; border-bottom: 1px solid #ccc; }}
  .highlight-item h3 a:hover {{ color: #b5838d; border-color: #b5838d; }}
  .highlight-item .source {{ font-size: 12px; color: #999; }}
  .highlight-item p {{ font-size: 15px; color: #555; margin-top: 6px; }}
  .highlight-item .cn {{ font-size: 13px; color: #8b7355; margin-top: 4px; font-style: italic; }}

  .category {{ margin-bottom: 32px; }}
  .category-name {{ font-size: 18px; font-weight: 600; color: #1a1a1a; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 1px solid #ddd; }}

  .article {{ margin-bottom: 16px; }}
  .article .title {{ font-size: 15px; font-weight: 600; }}
  .article .title a {{ color: #2c2c2c; text-decoration: none; border-bottom: 1px solid #ccc; }}
  .article .title a:hover {{ color: #b5838d; border-color: #b5838d; }}
  .article .meta {{ font-size: 12px; color: #999; margin-top: 2px; }}
  .article .summary {{ font-size: 14px; color: #555; margin-top: 4px; }}
  .article .cn-note {{ font-size: 13px; color: #8b7355; margin-top: 3px; font-style: italic; }}

  .divider {{ border: none; border-top: 1px solid #e0dcd5; margin: 36px 0; }}

  .takeaway {{ background: #f0ebe3; padding: 24px; border-radius: 4px; margin: 32px 0; }}
  .takeaway p {{ font-size: 15px; color: #444; }}
  .takeaway .cn-takeaway {{ font-size: 14px; color: #8b7355; margin-top: 12px; padding-top: 12px; border-top: 1px solid #d9d0c3; font-style: italic; }}

  .index-section {{ margin-top: 36px; }}
  .index-item {{ font-size: 13px; color: #666; margin-bottom: 4px; }}
  .index-item a {{ color: #666; text-decoration: none; border-bottom: 1px solid #ddd; }}
  .index-item a:hover {{ color: #b5838d; }}

  .footer {{ text-align: center; padding-top: 32px; border-top: 3px double #333; margin-top: 36px; }}
  .footer p {{ font-size: 12px; color: #aaa; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Daily Tech Digest</h1>
    <div class="date">{today} &mdash; {weekday}</div>
    <div class="stats">{len(articles)} articles from {len(FEEDS)} blogs &middot; Curated via Karpathy's HN RSS</div>
  </div>

  <div class="section-title">Today's Highlights / 今日亮点</div>
  {highlights_html}

  <hr class="divider">

  <div class="section-title">By Category / 分类浏览</div>
  {categories_html}

  <hr class="divider">

  <div class="section-title">Key Takeaway / 今日要点</div>
  <div class="takeaway">
    <p>{takeaway_en}</p>
    {takeaway_cn_html}
  </div>

  <hr class="divider">

  <div class="index-section">
    <div class="section-title">Full Article Index / 完整文章索引</div>
    {index_html}
  </div>

  <div class="footer">
    <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} &middot;
    RSS source: Andrej Karpathy &middot; Powered by Claude</p>
  </div>
</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"HTML generated: {output_path}")
    return output_path

# ============================================================
# 4. SEND EMAIL
# ============================================================
def send_email(html_path):
    """Send the digest HTML via Gmail SMTP."""
    today = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart("alternative")
    msg["From"]    = GMAIL_USER
    msg["To"]      = RECIPIENT_EMAIL
    msg["Subject"] = f"Daily Tech Digest - {today}"

    # Read HTML content for inline display
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Plain text fallback
    body_text = f"Your daily tech digest is attached ({today}). Open the HTML attachment for the best reading experience."
    msg.attach(MIMEText(body_text, "plain"))

    # Inline HTML body
    msg.attach(MIMEText(html_content, "html"))

    print(f"Sending email to {RECIPIENT_EMAIL}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print("Email sent successfully!")

# ============================================================
# MAIN
# ============================================================
def main():
    print("=" * 60)
    print(f"RSS Daily Digest - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1. Fetch
    articles = fetch_all_feeds()
    if not articles:
        print("No new articles found. Skipping.")
        return

    # 2. Summarize (returns structured JSON)
    digest_data = summarize_articles(articles)
    if not digest_data:
        print("Summarization failed. Skipping.")
        return

    # 3. Generate HTML
    html_path = generate_html(digest_data, articles)

    # 4. Send email (if configured)
    if GMAIL_USER and GMAIL_APP_PASSWORD:
        send_email(html_path)
    else:
        print("Email not configured. HTML saved locally.")

    print("Done!")


if __name__ == "__main__":
    main()
