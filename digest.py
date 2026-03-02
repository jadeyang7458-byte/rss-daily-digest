#!/usr/bin/env python3
"""
RSS Daily Digest - Recommended by Andrej Karpathy
Fetches 92 top HN blogs via RSS, summarizes with Claude, generates PDF, emails it.
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
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, 
    PageBreak, Table, TableStyle
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

# ============================================================
# CONFIG (auto-strip whitespace/newlines from secrets)
# ============================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "").strip() or GMAIL_USER
LOOKBACK_HOURS = int(os.environ.get("LOOKBACK_HOURS", "24"))
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "30"))  # cap to control cost
MODEL = os.environ.get("MODEL", "claude-sonnet-4-20250514")

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
                    "title": entry.get("title", "Untitled"),
                    "link": entry.get("link", ""),
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

    # Sort by time (newest first) and cap
    all_articles.sort(key=lambda x: x["published"], reverse=True)
    if len(all_articles) > MAX_ARTICLES:
        print(f"  Capping from {len(all_articles)} to {MAX_ARTICLES} articles")
        all_articles = all_articles[:MAX_ARTICLES]

    print(f"Total: {len(all_articles)} articles to summarize")
    return all_articles


# ============================================================
# 2. SUMMARIZE WITH CLAUDE (with retry)
# ============================================================
def summarize_articles(articles):
    """Use Claude to generate a structured daily digest."""
    if not articles:
        return "No new articles found in the last 24 hours."

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

    prompt = f"""You are a senior tech analyst creating a daily digest for an AI product manager.

Here are {len(articles)} new blog posts from top tech blogs (curated by Andrej Karpathy from HN's most popular blogs in 2025):

{articles_text}

Please create a structured daily digest with:

1. **Today's Highlights** (3-5 bullet points of the most important/interesting articles)
2. **By Category** - Group articles into categories like:
   - AI/ML
   - Software Engineering
   - Security
   - Startups/Business
   - Systems/Infrastructure
   - Other
   For each article: one-line summary + why it matters + link
3. **Key Takeaway** - One paragraph synthesis of today's most important theme

Write in a concise, scannable style. Use plain text (no markdown symbols like ** or #).
For each article include the source name and a one-sentence summary.
Keep the total under 3000 words.
Language: Write primarily in English, but add brief Chinese annotations (用中文简注) for the most important 3-5 articles to help bilingual readers."""

    # Retry up to 3 times
    for attempt in range(3):
        try:
            print(f"Summarizing with Claude (attempt {attempt + 1}/3)...")
            response = client.messages.create(
                model=MODEL,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
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


# ============================================================
# 3. GENERATE PDF
# ============================================================
def generate_pdf(digest_text, articles, output_path="digest.pdf"):
    """Generate a nicely formatted PDF digest."""
    today = datetime.now().strftime("%Y-%m-%d")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    styles.add(ParagraphStyle(
        "DigestTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=HexColor("#1a1a2e"),
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "DigestSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=HexColor("#666666"),
        alignment=TA_CENTER,
        spaceAfter=16,
    ))
    styles.add(ParagraphStyle(
        "SectionHead",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=HexColor("#16213e"),
        spaceBefore=14,
        spaceAfter=8,
        borderWidth=0,
        borderPadding=0,
    ))
    styles.add(ParagraphStyle(
        "BodyText2",
        parent=styles["Normal"],
        fontSize=10,
        leading=15,
        textColor=HexColor("#333333"),
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "FooterStyle",
        parent=styles["Normal"],
        fontSize=8,
        textColor=HexColor("#999999"),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "StatsStyle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=HexColor("#555555"),
        spaceAfter=4,
    ))

    story = []

    # --- Header ---
    story.append(Paragraph("Daily Tech Digest", styles["DigestTitle"]))
    story.append(Paragraph(
        f"{today} | {len(articles)} articles from 92 blogs | Curated via Karpathy's HN RSS list",
        styles["DigestSubtitle"],
    ))
    story.append(HRFlowable(
        width="100%", thickness=1.5,
        color=HexColor("#e94560"), spaceAfter=12
    ))

    # --- Digest body ---
    for line in digest_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue

        # Detect section headers (lines that are ALL CAPS or start with number + period)
        is_header = (
            line.isupper()
            or line.startswith("TODAY'S")
            or line.startswith("BY CATEGORY")
            or line.startswith("KEY TAKEAWAY")
            or (len(line) < 60 and line.endswith(":"))
        )

        # Escape XML special chars for reportlab
        safe = (line
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

        if is_header:
            story.append(Paragraph(safe, styles["SectionHead"]))
        else:
            story.append(Paragraph(safe, styles["BodyText2"]))

    # --- Article index ---
    story.append(Spacer(1, 16))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=HexColor("#cccccc"), spaceAfter=10
    ))
    story.append(Paragraph("Full Article Index", styles["SectionHead"]))

    for i, a in enumerate(articles, 1):
        safe_title = (a["title"]
                      .replace("&", "&amp;")
                      .replace("<", "&lt;")
                      .replace(">", "&gt;"))
        safe_link = a["link"].replace("&", "&amp;")
        text = (
            f'{i}. [{a["source"]}] {safe_title} '
            f'<font color="#0066cc"><link href="{safe_link}">{safe_link}</link></font>'
        )
        story.append(Paragraph(text, styles["StatsStyle"]))

    # --- Footer ---
    story.append(Spacer(1, 20))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=HexColor("#cccccc"), spaceAfter=6
    ))
    story.append(Paragraph(
        f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} | "
        "RSS source: github.com/emschwartz (via Andrej Karpathy) | "
        "Powered by Claude",
        styles["FooterStyle"],
    ))

    doc.build(story)
    print(f"PDF generated: {output_path}")
    return output_path


# ============================================================
# 4. SEND EMAIL
# ============================================================
def send_email(pdf_path):
    """Send the digest PDF via Gmail SMTP."""
    today = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL
    msg["Subject"] = f"Daily Tech Digest - {today}"

    body = f"""Hi,

Your daily tech digest is attached ({today}).

This digest covers the latest articles from 92 top tech blogs 
recommended by Andrej Karpathy, summarized by Claude.

Happy reading!
"""
    msg.attach(MIMEText(body, "plain"))

    # Attach PDF
    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "pdf")
        part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename=tech-digest-{today}.pdf",
        )
        msg.attach(part)

    # Send
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

    # 2. Summarize
    digest_text = summarize_articles(articles)

    # 3. Generate PDF
    pdf_path = generate_pdf(digest_text, articles)

    # 4. Send email (if configured)
    if GMAIL_USER and GMAIL_APP_PASSWORD:
        send_email(pdf_path)
    else:
        print("Email not configured. PDF saved locally.")

    print("Done!")


if __name__ == "__main__":
    main()
