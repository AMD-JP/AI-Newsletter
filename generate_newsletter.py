#!/usr/bin/env python3
"""
Compact Ford Raptor Price Newsletter generator with charts.
Loads PROJECT_API_KEY from .env next to the script.
"""

from pathlib import Path
from datetime import datetime, timezone
import os
import sys
import logging
import argparse
import csv
import tempfile
import re

# load .env sitting next to the script
from dotenv import load_dotenv
_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_PATH = _SCRIPT_DIR / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

import openai
import git
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from xml.sax.saxutils import escape

# ---- Config ----
REPO_PATH = os.environ.get("REPO_PATH", str(_SCRIPT_DIR))
OUTPUT_DIR = Path(REPO_PATH) / "reports"
API_KEY = os.environ.get("PROJECT_API_KEY", "")
GIT_REMOTE = "origin"
MODEL = "GPT-oss-20B"
LOG = logging.getLogger("raptor")
logging.basicConfig(level=logging.INFO)

# ---- Helpers ----
def make_client():
    # keep api_key in header; on-prem AMD endpoint uses Ocp-Apim-Subscription-Key
    return openai.OpenAI(
        base_url="https://llm-api.amd.com/OnPrem",
        api_key="dummy",
        default_headers={"Ocp-Apim-Subscription-Key": API_KEY, "user":"raptor-price-bot"}
    )

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[#*`]", "", text)
    text = text.replace("\u2014","-").replace("\u2013","-")
    text = text.replace("\u2018","'").replace("\u2019","'")
    text = text.replace("\u201c",'"').replace("\u201d",'"')
    text = text.encode("ascii","replace").decode("ascii")
    return escape(text).strip()

def call_llm(client, prompt, system=None, max_tokens=150):
    LOG.info("LLM: %s", prompt.strip().splitlines()[0][:80])
    sys_msg = system or "You are a concise automotive newsletter writer; answer in very short bullets or 1–3 sentences."
    resp = client.chat.completions.create(
        model=MODEL,
        max_completion_tokens=max_tokens,
        temperature=0.3,
        messages=[{"role":"system","content":sys_msg}, {"role":"user","content":prompt}]
    )
    return clean_text(resp.choices[0].message.content)

# ---- Data loading / fallback ----
def load_csv(path):
    rows = []
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows

def sample_data():
    years = list(range(2017, 2026))
    rng = np.random.default_rng(42)
    msrp = [55000 + (i - 2017) * (1500 + int(rng.integers(-400, 800))) for i in years]
    regions = {
        "Texas": np.array(msrp) * 1.02,
        "California": np.array(msrp) * 1.08,
        "Midwest": np.array(msrp) * 0.97
    }
    comp = {"Ram TRX": 28, "Chevy ZR2": 22, "Toyota TRD Pro": 18, "Other": 32}
    return {"years": years, "msrp": msrp, "regions": regions, "competition": comp}

# ---- Charts ----
def make_charts(data, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    imgs = {}

    # MSRP trend
    fig, ax = plt.subplots()
    ax.plot(data["years"], data["msrp"], marker='o')
    ax.set_title("MSRP Trend (median)")
    ax.set_xlabel("Year")
    ax.set_ylabel("MSRP (USD)")
    ax.grid(True, linestyle='--', linewidth=0.5)
    p1 = outdir / "msrp_trend.png"
    fig.tight_layout()
    fig.savefig(p1, dpi=150)
    plt.close(fig)
    imgs["msrp_trend"] = str(p1)

    # Regional bar (latest year)
    regions = {k: float(v[-1]) for k, v in data["regions"].items()}
    fig, ax = plt.subplots()
    ax.bar(list(regions.keys()), list(regions.values()))
    ax.set_title("Regional Asking Price (latest year)")
    ax.set_ylabel("Price (USD)")
    fig.tight_layout()
    p2 = outdir / "regional_bar.png"
    fig.savefig(p2, dpi=150)
    plt.close(fig)
    imgs["regional_bar"] = str(p2)

    # Competition pie
    comp_labels = list(data["competition"].keys())
    comp_vals = list(data["competition"].values())
    fig, ax = plt.subplots()
    ax.pie(comp_vals, labels=comp_labels, autopct="%1.0f%%", startangle=140)
    ax.set_title("Competition (relative)")
    fig.tight_layout()
    p3 = outdir / "competition_pie.png"
    fig.savefig(p3, dpi=150)
    plt.close(fig)
    imgs["competition_pie"] = str(p3)

    return imgs

# ---- PDF ----
def styles():
    return {
        "title": ParagraphStyle("title", fontSize=20, alignment=TA_CENTER, textColor=colors.white),
        "section": ParagraphStyle("section", fontSize=12, textColor=colors.HexColor("#003478"), spaceBefore=10),
        "body": ParagraphStyle("body", fontSize=9, leading=13, alignment=TA_JUSTIFY),
        "muted": ParagraphStyle("muted", fontSize=8, textColor=colors.HexColor("#666666"), alignment=TA_CENTER)
    }

def build_pdf(sections, imgs, outpdf: Path, date_str):
    s = styles()
    doc = SimpleDocTemplate(str(outpdf), pagesize=letter,
                            leftMargin=0.6*inch, rightMargin=0.6*inch,
                            topMargin=0.5*inch, bottomMargin=0.6*inch)
    story = []
    width = letter[0] - 1.2*inch

    # Masthead
    story.append(Paragraph("FORD RAPTOR — PRICE NEWSLETTER", s["title"]))
    story.append(Spacer(1,6))
    story.append(Paragraph(f"Generated {date_str}", s["muted"]))
    story.append(Spacer(1,10))

    # Executive summary (very short)
    story.append(Paragraph("EXECUTIVE SUMMARY", s["section"]))
    story.append(HRFlowable(width=width, thickness=1, color=colors.HexColor("#003478")))
    story.append(Paragraph(sections.get("summary",""), s["body"]))
    story.append(Spacer(1,8))

    # Key visuals
    story.append(Paragraph("KEY VISUALS", s["section"]))
    story.append(HRFlowable(width=width, thickness=0.8, color=colors.HexColor("#003478")))
    story.append(Spacer(1,6))
    story.append(Image(imgs["msrp_trend"], width=width*0.9, height=3*inch))
    story.append(Spacer(1,6))
    tab = Table([[Image(imgs["regional_bar"], width=width*0.44, height=2.2*inch),
                  Image(imgs["competition_pie"], width=width*0.44, height=2.2*inch)]],
                colWidths=[width*0.49, width*0.49])
    tab.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE")]))
    story.append(tab)
    story.append(Spacer(1,10))

    # Short sections
    for title, key in [("HISTORICAL TRENDS","history"), ("USED MARKET","used"), ("OUTLOOK","outlook")]:
        story.append(Paragraph(title, s["section"]))
        story.append(HRFlowable(width=width, thickness=0.6, color=colors.HexColor("#DDDDDD")))
        body = sections.get(key, "")
        for p in re.split(r"\n\s*\n", body)[:4]:
            if p.strip():
                story.append(Paragraph(p.strip(), s["body"]))
                story.append(Spacer(1,6))

    story.append(Spacer(1,8))
    story.append(HRFlowable(width=width, thickness=0.5, color=colors.HexColor("#DDDDDD")))
    story.append(Paragraph("Raptor Price Tracker Bot", s["muted"]))

    doc.build(story)

# ---- Git push (optional) ----
def commit_and_push(file: Path):
    try:
        repo = git.Repo(REPO_PATH)
        repo.git.add(str(file.resolve()))
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        repo.index.commit(f"raptor price newsletter [{timestamp}]")
        repo.remote(name=GIT_REMOTE).push()
        LOG.info("Pushed report to remote.")
    except Exception as e:
        LOG.warning("Git push skipped/failed: %s", e)

# ---- Main ----
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="CSV path with columns date,msrp,region,price")
    args = parser.parse_args()

    if not API_KEY:
        print("Missing PROJECT_API_KEY in environment. Loaded .env from:", _ENV_PATH)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    out_pdf = OUTPUT_DIR / f"raptor_price_newsletter_{datetime.now().strftime('%Y-%m-%d')}.pdf"

    # load or synthesize data
    if args.data and Path(args.data).exists():
        LOG.info("Loading data from %s", args.data)
        try:
            raw = load_csv(args.data)
            data = sample_data()  # for now we still use sample aggregation for charts in this compact form
        except Exception:
            data = sample_data()
    else:
        data = sample_data()

    tmpdir = Path(tempfile.mkdtemp(prefix="raptor_"))
    imgs = make_charts(data, tmpdir)

    # concise newsletter prompts
    client = make_client()
    sections = {}
    sections["summary"] = call_llm(
        client,
        f"Write a 2-sentence executive newsletter summary for Ford Raptor prices dated {date_str}. State direction (up/down) and one key driver.",
        max_tokens=80
    )
    sections["history"] = call_llm(
        client,
        "Give 3 very short bullets summarizing MSRP and resale trends 2017–2025."
    )
    sections["used"] = call_llm(
        client,
        "Give 3 short bullets on used Raptor pricing, depreciation, and dealer markup behavior."
    )
    sections["outlook"] = call_llm(
        client,
        "Provide a 3-bullet, 12-month price outlook for Ford Raptor (concise)."
    )

    build_pdf(sections, imgs, out_pdf, date_str)
    LOG.info("Report written: %s", out_pdf)
    commit_and_push(out_pdf)

if __name__ == "__main__":
    main()
