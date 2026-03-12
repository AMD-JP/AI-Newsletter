"""
Jacob's Newsletter Generator
==================================

Calls the AMD LLM Gateway to generate a weekly finance newsletter covering:
  - AMD financials & earnings
  - Global gaming market trends
  - Competitor analysis (Intel / Nvidia)

Outputs a professionally formatted PDF saved to newsletters/ and pushed to GitHub.

Requirements:
    pip install openai==1.101.0 gitpython reportlab python-dotenv

Setup:
    Create a file called .env in the same folder as this script containing:

        PROJECT_API_KEY=your-amd-gateway-key-here
        REPO_PATH=C:/Users/YOUR_USERNAME/AI-Newsletter
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
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent

_env_path = _SCRIPT_DIR / ".env"
if _env_path.exists():
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
else:
    load_dotenv(dotenv_path=_env_path)

API_KEY    = os.environ.get("PROJECT_API_KEY", "")
REPO_PATH  = os.environ.get("REPO_PATH", "")

if not REPO_PATH:
    REPO_PATH = str(_SCRIPT_DIR)

OUTPUT_DIR = Path(REPO_PATH) / "newsletters"
GIT_REMOTE = "origin"
GIT_BRANCH = "main"

MODEL       = "GPT-oss-20B"
MAX_TOKENS  = 3500
TEMPERATURE = 0.5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

log = logging.getLogger(__name__)

# Branding colors
AMD_RED    = colors.HexColor("#ED1C24")
AMD_DARK   = colors.HexColor("#1A1A1A")
AMD_GREY   = colors.HexColor("#4A4A4A")
AMD_LIGHT  = colors.HexColor("#F5F5F5")
AMD_BORDER = colors.HexColor("#DDDDDD")


def make_client():
    return openai.OpenAI(
        base_url="https://llm-api.amd.com/OnPrem",
        api_key="dummy",
        default_headers={
            "Ocp-Apim-Subscription-Key": API_KEY,
            "user": "newsletter-bot",
        },
    )


def clean_text(text: str) -> str:
    text = re.sub(r"[#*`]+", "", text)
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2022", "-")
    text = text.encode("ascii", "replace").decode("ascii")
    return text.strip()


def call_llm(client, prompt: str, section_name: str) -> str:
    log.info("Generating %s", section_name)

    response = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system",
             "content": "You are a senior financial analyst writing a professional newsletter."},
            {"role": "user", "content": prompt},
        ],
    )

    content = response.choices[0].message.content
    return clean_text(content) if content else ""


def generate_content(client, date_str: str) -> dict:

    sections = {}

    sections["tldr"] = call_llm(client, f"""
Write a TLDR summary for Jacob's Newsletter dated {date_str}.
Give 3 to 5 short sentences summarizing AMD financial performance,
gaming market conditions, and Intel and Nvidia competition.
""", "TLDR")

    sections["editors_note"] = call_llm(client, f"""
Write a short editor's note introducing this week's topics:
AMD financial performance, gaming trends, and competitor analysis.
Keep under 150 words.
""", "Editor's Note")

    sections["financials"] = call_llm(client, f"""
Write 4 paragraphs analyzing AMD's recent financial performance,
including revenue, margins, and segment growth.
Include context on stock performance and analyst outlook.
""", "Financials")

    sections["gaming"] = call_llm(client, f"""
Write 3 paragraphs about global PC gaming hardware market trends,
Steam user growth, and demand for Ryzen CPUs.
""", "Gaming Market")

    sections["competitors"] = call_llm(client, f"""
Write 4 paragraphs analyzing AMD versus Intel and Nvidia.
Discuss CPU market share, AI hardware, and upcoming products.
""", "Competitor Analysis")

    sections["takeaways"] = call_llm(client, f"""
Write 4 sentences summarizing key investor takeaways for AMD.
""", "Key Takeaways")

    return sections


def build_styles():

    return {

        "masthead_title": ParagraphStyle(
            "masthead_title",
            fontSize=24,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=TA_CENTER,
        ),

        "masthead_sub": ParagraphStyle(
            "masthead_sub",
            fontSize=11,
            textColor=colors.HexColor("#FFCCCC"),
            alignment=TA_CENTER,
        ),

        "section_heading": ParagraphStyle(
            "section_heading",
            fontSize=14,
            fontName="Helvetica-Bold",
            textColor=AMD_RED,
            spaceBefore=18,
            spaceAfter=6,
        ),

        "body": ParagraphStyle(
            "body",
            fontSize=10,
            leading=16,
            alignment=TA_JUSTIFY,
        ),

        "footer": ParagraphStyle(
            "footer",
            fontSize=8,
            textColor=AMD_GREY,
            alignment=TA_CENTER,
        ),
    }


def split_paragraphs(text):
    return [p.strip() for p in text.split("\n") if p.strip()]


def build_pdf(sections, output_path, date_str):

    styles = build_styles()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
        title=f"Jacob's Newsletter - {date_str}",
        author="Jacob's Newsletter Bot",
    )

    story = []
    width = letter[0] - 1.5 * inch

    masthead = Table([
        [Paragraph("JACOB'S", styles["masthead_title"])],
        [Paragraph("NEWSLETTER", styles["masthead_title"])],
        [Paragraph(f"Technology & Market Intelligence | {date_str}", styles["masthead_sub"])],
    ], colWidths=[width])

    masthead.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), AMD_RED),
        ("TOPPADDING", (0,0), (-1,-1), 16),
        ("BOTTOMPADDING", (0,0), (-1,-1), 16),
    ]))

    story.append(masthead)
    story.append(Spacer(1,12))

    for title,key in [
        ("EDITOR'S NOTE","editors_note"),
        ("AMD FINANCIALS","financials"),
        ("GLOBAL GAMING MARKET","gaming"),
        ("COMPETITOR ANALYSIS","competitors"),
        ("KEY TAKEAWAYS","takeaways")
    ]:

        story.append(Paragraph(title, styles["section_heading"]))
        story.append(HRFlowable(width=width, thickness=1, color=AMD_RED))

        for p in split_paragraphs(sections[key]):
            story.append(Paragraph(p, styles["body"]))

        story.append(Spacer(1,12))

    story.append(HRFlowable(width=width, thickness=0.5, color=AMD_BORDER))

    story.append(Paragraph(
        f"Jacob's Newsletter | Generated {date_str} | Powered by AMD LLM Gateway",
        styles["footer"]
    ))

    doc.build(story)


def commit_and_push(output_path):

    repo = git.Repo(REPO_PATH)

    repo.git.add(str(output_path.resolve()))

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    repo.index.commit(
        f"publish: Jacob's Newsletter [{timestamp}]"
    )

    repo.remote(name=GIT_REMOTE).push()


def main():

    if not API_KEY:
        print("Missing PROJECT_API_KEY in .env")
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    file_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output_path = OUTPUT_DIR / f"jacobs_newsletter_{file_date}.pdf"

    client = make_client()

    sections = generate_content(client, date_str)

    build_pdf(sections, output_path, date_str)

    commit_and_push(output_path)

    log.info("Newsletter published → %s", output_path)


if __name__ == "__main__":
    main()
