"""
Ford Raptor Price Trend Report Generator
========================================

Uses the AMD LLM Gateway to generate a weekly report tracking
price trends for Ford F-150 Raptor trucks over time.

The report analyzes:
    - New vehicle MSRP changes
    - Used market price trends
    - Regional demand differences
    - Competitor trucks (TRX, ZR2, etc.)

Outputs a PDF saved to /reports and pushes to GitHub.

Requirements:
    pip install openai==1.101.0 gitpython reportlab python-dotenv
"""

import os
import re
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

import openai
import git
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY


# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent

_env_path = _SCRIPT_DIR / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)
else:
    load_dotenv(dotenv_path=_env_path)

API_KEY = os.environ.get("PROJECT_API_KEY", "")
REPO_PATH = os.environ.get("REPO_PATH", "")

if not REPO_PATH:
    REPO_PATH = str(_SCRIPT_DIR)

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
DARK = colors.HexColor("#1A1A1A")
LIGHT = colors.HexColor("#F5F5F5")
GREY = colors.HexColor("#666666")
BORDER = colors.HexColor("#DDDDDD")


# ---------------------------------------------------------------------
# LLM CLIENT (UNCHANGED)
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
# TEXT CLEANER
# ---------------------------------------------------------------------

def clean_text(text: str):
    text = re.sub(r"[#*`]+", "", text)
    text = text.encode("ascii", "replace").decode("ascii")
    return text.strip()


# ---------------------------------------------------------------------
# LLM CALL
# ---------------------------------------------------------------------

def call_llm(client, prompt, name):

    log.info("Generating %s", name)

    system = (
        "You are an automotive market analyst specializing in pickup truck pricing "
        "and used vehicle market trends."
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
# CONTENT GENERATION
# ---------------------------------------------------------------------

def generate_content(client, date):

    sections = {}

    sections["summary"] = call_llm(client, f"""
Write a short executive summary for a Ford Raptor Price Report dated {date}.
Summarize the overall direction of Ford Raptor prices in both new and used markets.
""", "Summary")

    sections["historical"] = call_llm(client, f"""
Write an analysis of Ford F-150 Raptor pricing trends from 2017 through 2025.
Discuss MSRP changes across generations and how resale values have changed.
""", "Historical Prices")

    sections["used_market"] = call_llm(client, f"""
Write a section analyzing used Ford Raptor price trends in the U.S.
Discuss supply levels, dealer markups, and depreciation curves.
""", "Used Market")

    sections["regional"] = call_llm(client, f"""
Explain regional price differences for Ford Raptors in the United States.
Focus on Texas, California, and Midwest markets.
""", "Regional Demand")

    sections["competition"] = call_llm(client, f"""
Analyze how competitor trucks influence Raptor prices including:
Ram TRX, Chevy Silverado ZR2, and Toyota TRD Pro trucks.
""", "Competition")

    sections["outlook"] = call_llm(client, f"""
Write a forward-looking outlook for Ford Raptor pricing over the next 12 months.
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

    for title,key in [
        ("EXECUTIVE SUMMARY","summary"),
        ("HISTORICAL PRICE TRENDS","historical"),
        ("USED MARKET ANALYSIS","used_market"),
        ("REGIONAL MARKET DIFFERENCES","regional"),
        ("COMPETITOR IMPACT","competition"),
        ("PRICE OUTLOOK","outlook")
    ]:

        story.append(Paragraph(title, s["section"]))
        story.append(HRFlowable(width=width, thickness=1, color=FORD_BLUE))

        for p in sections[key].split("\n"):
            story.append(Paragraph(p.strip(), s["body"]))

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
