"""
Ford Raptor Price Trend Report Generator
"""

import os
import re
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import openai
import git
from dotenv import load_dotenv

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY


# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent

_env = _SCRIPT_DIR / ".env"

if _env.exists():
    with open(_env) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)
else:
    load_dotenv(dotenv_path=_env)

API_KEY = os.environ.get("PROJECT_API_KEY", "")
REPO_PATH = os.environ.get("REPO_PATH", str(_SCRIPT_DIR))

OUTPUT_DIR = Path(REPO_PATH) / "reports"

GIT_REMOTE = "origin"
GIT_BRANCH = "main"

MODEL = "GPT-oss-20B"
MAX_TOKENS = 3500
TEMPERATURE = 0.4

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# COLORS
# ---------------------------------------------------------------------

FORD_BLUE = colors.HexColor("#003478")
GREY = colors.HexColor("#666666")
BORDER = colors.HexColor("#DDDDDD")


# ---------------------------------------------------------------------
# AMD LLM CLIENT (UNCHANGED)
# ---------------------------------------------------------------------

def make_client():
    return openai.OpenAI(
        base_url="https://llm-api.amd.com/OnPrem",
        api_key="dummy",
        default_headers={
            "Ocp-Apim-Subscription-Key": API_KEY,
            "user": "raptor-price-bot",
        },
    )


# ---------------------------------------------------------------------
# TEXT SANITIZATION
# ---------------------------------------------------------------------

def clean_text(text: str):
    """Sanitize LLM output so ReportLab never crashes."""

    if not text:
        return ""

    # remove html tags
    text = re.sub(r"<[^>]+>", "", text)

    # remove markdown
    text = re.sub(r"[#*`]", "", text)

    # normalize unicode punctuation
    text = text.replace("\u2014", "-")
    text = text.replace("\u2013", "-")
    text = text.replace("\u2018", "'")
    text = text.replace("\u2019", "'")
    text = text.replace("\u201c", '"')
    text = text.replace("\u201d", '"')

    # force ascii
    text = text.encode("ascii", "replace").decode("ascii")

    # escape HTML characters so ReportLab doesn't interpret them
    text = escape(text)

    return text.strip()


# ---------------------------------------------------------------------
# LLM CALL
# ---------------------------------------------------------------------

def call_llm(client, prompt, section):

    log.info("Generating %s", section)

    system = (
        "You are an automotive market analyst specializing in pickup truck "
        "pricing and resale value trends."
    )

    response = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content

    return clean_text(content)


# ---------------------------------------------------------------------
# REPORT CONTENT
# ---------------------------------------------------------------------

def generate_content(client, date):

    sections = {}

    sections["summary"] = call_llm(client, f"""
Write a short executive summary for a Ford Raptor price report dated {date}.
Explain whether prices are trending up or down.
""", "Summary")

    sections["history"] = call_llm(client, f"""
Explain Ford Raptor MSRP changes from 2017 through 2025 and resale value trends.
""", "Historical Prices")

    sections["used"] = call_llm(client, f"""
Analyze used Ford Raptor prices across the United States including depreciation
and dealer markup behavior.
""", "Used Market")

    sections["regional"] = call_llm(client, f"""
Explain regional Raptor price differences focusing on Texas, California,
and Midwest markets.
""", "Regional Markets")

    sections["competition"] = call_llm(client, f"""
Explain how competitor trucks affect Raptor pricing including Ram TRX,
Chevy Silverado ZR2 and Toyota TRD Pro.
""", "Competition")

    sections["outlook"] = call_llm(client, f"""
Provide a short 12 month outlook for Ford Raptor pricing.
""", "Outlook")

    return sections


# ---------------------------------------------------------------------
# PDF STYLES
# ---------------------------------------------------------------------

def styles():

    return {

        "title": ParagraphStyle(
            "title",
            fontSize=24,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=TA_CENTER
        ),

        "section": ParagraphStyle(
            "section",
            fontSize=14,
            fontName="Helvetica-Bold",
            textColor=FORD_BLUE,
            spaceBefore=16,
            spaceAfter=6
        ),

        "body": ParagraphStyle(
            "body",
            fontSize=10,
            leading=16,
            alignment=TA_JUSTIFY
        ),

        "footer": ParagraphStyle(
            "footer",
            fontSize=8,
            textColor=GREY,
            alignment=TA_CENTER
        )
    }


# ---------------------------------------------------------------------
# PARAGRAPH SPLITTER
# ---------------------------------------------------------------------

def split_paragraphs(text):

    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


# ---------------------------------------------------------------------
# PDF BUILDER
# ---------------------------------------------------------------------

def build_pdf(sections, output, date):

    s = styles()

    doc = SimpleDocTemplate(
        str(output),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
        title=f"Ford Raptor Price Report - {date}",
        author="Raptor Price Tracker Bot",
    )

    story = []

    width = letter[0] - 1.5 * inch

    masthead = Table([
        [Paragraph("FORD RAPTOR", s["title"])],
        [Paragraph("PRICE TREND REPORT", s["title"])],
        [Paragraph(date, s["footer"])]
    ], colWidths=[width])

    masthead.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), FORD_BLUE),
        ("TOPPADDING",(0,0),(-1,-1),16),
        ("BOTTOMPADDING",(0,0),(-1,-1),16)
    ]))

    story.append(masthead)
    story.append(Spacer(1,12))

    sections_order = [
        ("EXECUTIVE SUMMARY","summary"),
        ("HISTORICAL PRICE TRENDS","history"),
        ("USED MARKET ANALYSIS","used"),
        ("REGIONAL MARKET DIFFERENCES","regional"),
        ("COMPETITOR IMPACT","competition"),
        ("PRICE OUTLOOK","outlook")
    ]

    for title,key in sections_order:

        story.append(Paragraph(title, s["section"]))
        story.append(HRFlowable(width=width, thickness=1, color=FORD_BLUE))

        for p in split_paragraphs(sections[key]):
            story.append(Paragraph(p, s["body"]))

        story.append(Spacer(1,12))

    story.append(HRFlowable(width=width, thickness=0.5, color=BORDER))

    story.append(Paragraph(
        f"Ford Raptor Price Report | Generated {date}",
        s["footer"]
    ))

    doc.build(story)


# ---------------------------------------------------------------------
# GIT PUSH
# ---------------------------------------------------------------------

def commit_and_push(file):

    repo = git.Repo(REPO_PATH)

    repo.git.add(str(file.resolve()))

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    repo.index.commit(f"raptor price report [{timestamp}]")

    repo.remote(name=GIT_REMOTE).push()


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():

    if not API_KEY:
        print("Missing PROJECT_API_KEY in .env")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    date = datetime.now(timezone.utc).strftime("%B %d, %Y")
    file_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output = OUTPUT_DIR / f"raptor_price_report_{file_date}.pdf"

    client = make_client()

    sections = generate_content(client, date)

    build_pdf(sections, output, date)

    commit_and_push(output)

    log.info("Report generated: %s", output)


if __name__ == "__main__":
    main()
