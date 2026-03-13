"""
AMD Finance Newsletter Generator
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

    Use forward slashes in the path. The .env file is in .gitignore and will
    NEVER be committed to GitHub. Your API key is always safe.
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
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, PageBreak
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

# ---------------------------------------------------------------------------
# CONFIG — loaded from .env file. Do NOT put your API key in this script.
# ---------------------------------------------------------------------------
# Try multiple strategies to load the .env file — handles Python 3.14
# dotenv compatibility issues and different working directory scenarios.
_SCRIPT_DIR = Path(__file__).resolve().parent

# Strategy 1: explicit path to .env next to this script (most reliable)
_env_path = _SCRIPT_DIR / ".env"
if _env_path.exists():
    # Read and parse manually — bypasses any python-dotenv version issues
    with open(_env_path, "r", encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
else:
    # Strategy 2: fall back to load_dotenv for any other .env location
    load_dotenv(dotenv_path=_env_path)

API_KEY    = os.environ.get("PROJECT_API_KEY", "")
REPO_PATH  = os.environ.get("REPO_PATH", "")
# Auto-detect REPO_PATH from script location if not set in .env
if not REPO_PATH:
    REPO_PATH = str(_SCRIPT_DIR)
    os.environ["REPO_PATH"] = REPO_PATH
OUTPUT_DIR = Path(REPO_PATH) / "newsletters"
GIT_REMOTE = "origin"
GIT_BRANCH  = "main"
MODEL       = "GPT-oss-20B"
MAX_TOKENS  = 3500
TEMPERATURE = 0.5
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Colour palette
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
    """Remove markdown and replace special characters ReportLab cannot render."""
    text = re.sub(r"[#*`]+", "", text)
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2022", "-").replace("\u00b7", "-")
    text = text.encode("ascii", "replace").decode("ascii")
    text = re.sub(r"\?{2,}", " ", text)
    return text.strip()


def call_llm(client, prompt: str, section_name: str) -> str:
    log.info("Generating section: %s", section_name)
    system = (
        "You are a senior financial analyst and technology journalist. "
        "Write clear, professional newsletter content in plain prose. "
        "Do not use markdown, bullet points, asterisks, dashes for lists, "
        "or any special formatting characters."
    )
    response = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
    )
    choice = response.choices[0]
    log.info("  %s - finish: %s | tokens: prompt=%s completion=%s",
             section_name, choice.finish_reason,
             response.usage.prompt_tokens, response.usage.completion_tokens)
    content = choice.message.content
    if not content:
        return f"Content for {section_name} could not be generated."
    return clean_text(content)


def generate_content(client, date_str: str) -> dict:
    sections = {}

    sections["tldr"] = call_llm(client, f"""
Write a TL;DR summary for an AMD investor newsletter dated {date_str}.
Give 3 to 5 short punchy sentences that a busy executive can read in 20 seconds.
Cover AMD financial performance, gaming market conditions, and Intel and Nvidia competition.
Each sentence should be a standalone insight. No filler. Plain prose only. No markdown.
""", "TLDR")

    sections["editors_note"] = call_llm(client, f"""
Write a concise editor's note of 2 to 3 short paragraphs for the AMD Weekly Finance Newsletter
dated {date_str}. Briefly introduce this week's key themes: AMD's financial performance,
the global gaming market, and competitive dynamics with Intel and Nvidia.
Keep it under 150 words. Plain prose only. No markdown.
""", "Editor's Note")

    sections["financials"] = call_llm(client, f"""
Write a detailed financial analysis section of 4 to 5 paragraphs for an AMD investor newsletter
dated {date_str}. Cover AMD's most recent quarterly earnings including revenue, gross margin,
and EPS. Discuss year-over-year and quarter-over-quarter growth across AMD's business segments
including Data Center, Client, Gaming, and Embedded. Include key guidance and forward-looking
statements from AMD management, stock performance context, analyst sentiment, and any significant
recent news affecting AMD's financial outlook. Plain prose only. No markdown. No bullet points.
Be specific with figures where possible, noting if estimates are used.
""", "AMD Financials & Earnings")

    sections["gaming"] = call_llm(client, f"""
Write a global gaming market analysis section of 3 to 4 paragraphs for an AMD investor newsletter
dated {date_str}. Cover the current state of the global PC gaming hardware market and consumer
spending trends. Discuss regional demand patterns for gaming CPUs including North America, Europe,
and Asia-Pacific. Explain how gaming market trends are influencing AMD Ryzen CPU demand across
product tiers. Include Steam platform growth and active user trends. Provide a near-term outlook
for gaming hardware demand. Plain prose only. No markdown. No bullet points.
""", "Global Gaming Market Trends")

    sections["competitors"] = call_llm(client, f"""
Write a competitor analysis section of 4 to 5 paragraphs for an AMD investor newsletter
dated {date_str}. Cover Intel's current CPU market position, recent product launches, financial
health, and strategic challenges. Discuss Nvidia's dominance in the GPU and AI accelerator market
and any overlap with AMD's business. Analyse AMD's competitive advantages and vulnerabilities
versus both Intel and Nvidia. Include market share trends in desktop, laptop, and data center
CPU segments, and key upcoming product launches from all three companies. Plain prose only.
No markdown. No bullet points.
""", "Competitor Analysis")

    sections["takeaways"] = call_llm(client, f"""
Write a Key Takeaways closing section of 3 to 5 sentences for an AMD investor newsletter
dated {date_str}. Summarise the most important investor-relevant insights from this week's
analysis of AMD financials, gaming market trends, and competitive positioning.
End with one forward-looking sentence about what to watch in the coming weeks.
Plain prose only. No markdown.
""", "Key Takeaways")

    return sections


def build_styles():
    styles = {
        "masthead_title": ParagraphStyle(
            "masthead_title", fontSize=24, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_CENTER, spaceAfter=4,
        ),
        "masthead_sub": ParagraphStyle(
            "masthead_sub", fontSize=11, fontName="Helvetica",
            textColor=colors.HexColor("#FFCCCC"), alignment=TA_CENTER, spaceAfter=0,
        ),
        "section_heading": ParagraphStyle(
            "section_heading", fontSize=14, fontName="Helvetica-Bold",
            textColor=AMD_RED, spaceBefore=18, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body", fontSize=10, fontName="Helvetica", textColor=AMD_DARK,
            leading=16, spaceAfter=8, alignment=TA_JUSTIFY,
        ),
        "editors_note": ParagraphStyle(
            "editors_note", fontSize=10, fontName="Helvetica-Oblique",
            textColor=AMD_GREY, leading=15, spaceAfter=8, alignment=TA_JUSTIFY,
        ),
        "takeaway_box": ParagraphStyle(
            "takeaway_box", fontSize=10, fontName="Helvetica", textColor=AMD_DARK,
            leading=15, spaceAfter=6, alignment=TA_JUSTIFY,
        ),
        "tldr_label": ParagraphStyle(
            "tldr_label", fontSize=11, fontName="Helvetica-Bold",
            textColor=colors.white, alignment=TA_LEFT,
        ),
        "tldr_body": ParagraphStyle(
            "tldr_body", fontSize=10, fontName="Helvetica", textColor=AMD_DARK,
            leading=16, spaceAfter=6, alignment=TA_JUSTIFY,
        ),
        "footer": ParagraphStyle(
            "footer", fontSize=8, fontName="Helvetica",
            textColor=AMD_GREY, alignment=TA_CENTER,
        ),
        "disclaimer": ParagraphStyle(
            "disclaimer", fontSize=7, fontName="Helvetica-Oblique",
            textColor=AMD_GREY, alignment=TA_CENTER, leading=10,
        ),
    }
    return styles


def split_paragraphs(text: str) -> list:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def build_pdf(sections: dict, output_path: Path, date_str: str) -> None:
    log.info("Building PDF: %s", output_path)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.5 * inch, bottomMargin=0.75 * inch,
        title=f"AMD Finance Newsletter - {date_str}",
        author="AMD Finance Newsletter Bot",
    )
    styles = build_styles()
    story  = []
    W      = letter[0] - 1.5 * inch

    # Masthead
    masthead = Table([
        [Paragraph("AMD WEEKLY FINANCE", styles["masthead_title"])],
        [Paragraph("NEWSLETTER", styles["masthead_title"])],
        [Paragraph(f"Market Intelligence &amp; Competitive Analysis  |  {date_str}", styles["masthead_sub"])],
    ], colWidths=[W])
    masthead.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AMD_RED),
        ("TOPPADDING",    (0, 0), (-1, -1), 16),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
        ("LEFTPADDING",   (0, 0), (-1, -1), 20),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 20),
    ]))
    story.append(masthead)
    story.append(Spacer(1, 10))

    # Coverage tags
    tags = ["AMD FINANCIALS & EARNINGS", "GLOBAL GAMING TRENDS", "INTEL & NVIDIA ANALYSIS"]
    tag_table = Table([[Paragraph(t, ParagraphStyle(
        "tag", fontSize=8, fontName="Helvetica-Bold",
        textColor=AMD_RED, alignment=TA_CENTER
    )) for t in tags]], colWidths=[W / 3] * 3)
    tag_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), AMD_LIGHT),
        ("BOX",           (0, 0), (-1, -1), 0.5, AMD_BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, AMD_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tag_table)
    story.append(Spacer(1, 14))

    # TLDR box
    tldr_rows = [[Paragraph("TL;DR  -  This Week at a Glance", styles["tldr_label"])]]
    for p in split_paragraphs(sections["tldr"]):
        tldr_rows.append([Paragraph(p, styles["tldr_body"])])
    tldr_table = Table(tldr_rows, colWidths=[W])
    tldr_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), AMD_DARK),
        ("BACKGROUND",    (0, 1), (-1, -1), AMD_LIGHT),
        ("BOX",           (0, 0), (-1, -1), 1, AMD_DARK),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 14),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
    ]))
    story.append(tldr_table)
    story.append(Spacer(1, 14))

    # Editor's Note
    story.append(Paragraph("EDITOR'S NOTE", styles["section_heading"]))
    story.append(HRFlowable(width=W, thickness=1, color=AMD_RED, spaceAfter=8))
    for p in split_paragraphs(sections["editors_note"]):
        story.append(Paragraph(p, styles["editors_note"]))

    # AMD Financials
    story.append(Paragraph("AMD FINANCIALS &amp; EARNINGS", styles["section_heading"]))
    story.append(HRFlowable(width=W, thickness=1, color=AMD_RED, spaceAfter=8))
    for p in split_paragraphs(sections["financials"]):
        story.append(Paragraph(p, styles["body"]))

    # Gaming Market
    story.append(PageBreak())
    story.append(Paragraph("GLOBAL GAMING MARKET TRENDS", styles["section_heading"]))
    story.append(HRFlowable(width=W, thickness=1, color=AMD_RED, spaceAfter=8))
    for p in split_paragraphs(sections["gaming"]):
        story.append(Paragraph(p, styles["body"]))

    # Competitor Analysis
    story.append(Paragraph("COMPETITOR ANALYSIS: INTEL &amp; NVIDIA", styles["section_heading"]))
    story.append(HRFlowable(width=W, thickness=1, color=AMD_RED, spaceAfter=8))
    for p in split_paragraphs(sections["competitors"]):
        story.append(Paragraph(p, styles["body"]))

    # Key Takeaways
    story.append(PageBreak())
    story.append(Paragraph("KEY TAKEAWAYS", styles["section_heading"]))
    story.append(HRFlowable(width=W, thickness=1, color=AMD_RED, spaceAfter=8))
    kt_rows = [[Paragraph(p, styles["takeaway_box"])]
               for p in split_paragraphs(sections["takeaways"])]
    if kt_rows:
        kt_table = Table(kt_rows, colWidths=[W])
        kt_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), AMD_LIGHT),
            ("BOX",           (0, 0), (-1, -1), 1, AMD_RED),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING",   (0, 0), (-1, -1), 14),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 14),
        ]))
        story.append(kt_table)

    story.append(Spacer(1, 24))

    # Footer
    story.append(HRFlowable(width=W, thickness=0.5, color=AMD_BORDER, spaceAfter=8))
    story.append(Paragraph(
        f"AMD Weekly Finance Newsletter  |  Generated {date_str}  |  Powered by AMD LLM Gateway",
        styles["footer"]
    ))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This newsletter is generated automatically for informational purposes only and does not "
        "constitute financial advice. All figures and projections are based on publicly available "
        "information and AI-generated analysis. Past performance is not indicative of future results.",
        styles["disclaimer"]
    ))
    doc.build(story)
    log.info("PDF saved: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)


def commit_and_push(output_path: Path) -> None:
    """Commit ONLY the newsletter PDF and push to GitHub.
    Never stages the script or any other files.
    """
    repo = git.Repo(REPO_PATH)

    # Stage only the specific PDF — nothing else ever gets touched
    abs_path = str(output_path.resolve())
    repo.git.add(abs_path)
    log.info("Staged: %s", abs_path)

    # Check if there is actually something to commit
    if not repo.index.diff("HEAD") and not any(
        "newsletters" in f for f in repo.untracked_files
    ):
        log.info("No changes to commit — newsletter already up to date.")
        return

    # Pull remote using merge strategy to avoid rebase conflicts
    origin = repo.remote(name=GIT_REMOTE)
    log.info("Pulling latest remote changes...")
    repo.git.fetch(GIT_REMOTE)
    repo.git.merge(f"{GIT_REMOTE}/{GIT_BRANCH}", "--no-edit", "--strategy-option=theirs")

    # Re-stage PDF after merge
    repo.git.add(abs_path)

    timestamp  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commit_msg = f"chore(newsletter): publish AMD finance newsletter [{timestamp}]"
    repo.index.commit(commit_msg)
    log.info("Committed: %s", commit_msg)

    push_result = origin.push(refspec=f"HEAD:{GIT_BRANCH}")
    for info in push_result:
        if info.flags & info.ERROR:
            raise RuntimeError(f"Git push failed: {info.summary}")

    log.info("Pushed to %s/%s", GIT_REMOTE, GIT_BRANCH)


def main() -> None:
    if not API_KEY:
        log.error(
            "PROJECT_API_KEY not found. "
            "Create a .env file in this folder with: PROJECT_API_KEY=your-key-here"
        )
        sys.exit(1)

    if not REPO_PATH or not Path(REPO_PATH).is_dir():
        log.error(
            "REPO_PATH not set or folder does not exist. "
            "Add REPO_PATH=C:/Users/YOUR_USERNAME/AI-Newsletter to your .env file"
        )
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)

    date_str    = datetime.now(timezone.utc).strftime("%B %d, %Y")
    file_date   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = OUTPUT_DIR / f"amd_finance_newsletter_{file_date}.pdf"

    try:
        client   = make_client()
        sections = generate_content(client, date_str)
        build_pdf(sections, output_path, date_str)
        commit_and_push(output_path)
        log.info("Done. Newsletter published to %s", output_path)
    except Exception as exc:
        log.exception("Newsletter generation failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
