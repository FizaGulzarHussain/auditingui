from __future__ import annotations
import io
import re
import time
import json
import socket
import random
import requests
import pandas as pd
import streamlit as st
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from pypdf import PdfWriter

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────

def _get_secret(key: str, default=None):
    """Safely read a Streamlit secret, returning default if secrets aren't configured."""
    try:
        val = st.secrets.get(key, default)
        return val
    except Exception:
        return default

def locationiq_autocomplete(query: str, api_key: str) -> tuple[list[dict], str]:
    """Query LocationIQ Autocomplete API for city/country/region suggestions.

    Uses the LocationIQ /v1/autocomplete endpoint which returns place
    predictions for cities, countries, and administrative areas.

    Returns (suggestions, error_message). suggestions is a list of
    {"description": str, "place_id": str} dicts. error_message is "" on
    success, or a human-readable reason so the UI can tell the rep why
    nothing showed up instead of silently doing nothing.
    """
    if not api_key:
        return [], "no_key"
    if not query or len(query.strip()) < 2:
        return [], ""
    try:
        resp = requests.get(
            "https://api.locationiq.com/v1/autocomplete",
            params={
                "key": api_key,
                "q": query.strip(),
                "limit": 5,
                "dedupe": 1,
                "tag": "place:city,place:country,place:state,place:region",
            },
            timeout=6,
        )
        if resp.status_code != 200:
            try:
                err = resp.json().get("error", resp.text[:200])
            except Exception:
                err = resp.text[:200]
            return [], f"HTTP {resp.status_code}: {err}"
        data = resp.json()
        suggestions = []
        for item in data:
            display = item.get("display_name", "")
            place_id = str(item.get("place_id", ""))
            if display:
                suggestions.append({"description": display, "place_id": place_id})
        return suggestions, ""
    except Exception as exc:
        return [], f"request_failed: {exc}"

def send_email_smtp(to_addr: str, subject: str, body: str) -> tuple[bool, str]:
    try:
        smtp_host   = _get_secret("SMTP_HOST", "smtp.gmail.com")
        smtp_port   = int(_get_secret("SMTP_PORT", 587))
        smtp_user   = _get_secret("SMTP_USER")
        smtp_pass   = _get_secret("SMTP_PASSWORD")
        if not smtp_user or not smtp_pass:
            return False, "SMTP credentials not configured. Add SMTP_USER and SMTP_PASSWORD to your secrets.toml."

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = to_addr
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_addr, msg.as_string())
        return True, "Sent successfully"
    except KeyError:
        return False, "SMTP credentials not configured."
    except Exception as e:
        return False, str(e)

st.set_page_config(
    page_title="fast.site — Lead Finder",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# PROFESSIONAL LIGHT THEME CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Reset & Base ─────────────────────────────────────── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
.stApp { background: #F0F2F8 !important; }
/* Keep the header bar (it holds the sidebar expand/collapse control) but
   make it blend into the background instead of fully hiding it — fully
   hiding it (display:none) also hides the sidebar toggle, so once the
   sidebar collapses there's no way to bring it back. */
header[data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
    height: 2.75rem !important;
}
header[data-testid="stHeader"] * { visibility: visible !important; }
#root > div:first-child { margin-top: 0 !important; }
.block-container {
    padding: 0 2.5rem 3rem 2.5rem !important;
    padding-top: 0.75rem !important;
    margin-top: 0 !important;
    max-width: 1180px !important;
}

/* ── Typography ───────────────────────────────────────── */
h1 {
    font-size: 1.75rem !important; font-weight: 800 !important;
    color: #0D1526 !important; letter-spacing: -0.6px !important;
    margin-bottom: 0.2rem !important;
}
h2 { font-size: 1.2rem !important; font-weight: 700 !important; color: #0D1526 !important; letter-spacing: -0.3px !important; }
h3 { font-size: 1rem !important; font-weight: 600 !important; color: #1E2D4A !important; }
h4 { font-size: 0.92rem !important; font-weight: 700 !important; color: #1E2D4A !important;
     letter-spacing: 0.04em !important; text-transform: uppercase !important; margin-bottom: 0.6rem !important; }
p, li, label, .stMarkdown { color: #2D3F5C !important; font-size: 0.93rem !important; line-height: 1.65 !important; }
small, .stCaption, [data-testid="stCaptionContainer"] { color: #7A8BA8 !important; font-size: 0.8rem !important; }

/* ── Inputs ───────────────────────────────────────────── */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    background: #FFFFFF !important;
    border: 1.5px solid #D4DCE9 !important;
    border-radius: 9px !important;
    color: #0D1526 !important;
    font-size: 0.93rem !important;
    padding: 0.6rem 0.9rem !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.13) !important;
    outline: none !important;
}
.stTextInput label, .stNumberInput label, .stRadio > label {
    font-weight: 600 !important; font-size: 0.82rem !important;
    color: #4A5C78 !important; letter-spacing: 0.02em !important;
    text-transform: uppercase !important; margin-bottom: 5px !important;
}

/* ── Buttons — unified blue system ───────────────────── */
.stButton, [data-testid="stDownloadButton"] {
    display: flex !important; align-items: stretch !important;
}
.stButton > button, [data-testid="stDownloadButton"] > button {
    width: 100% !important; min-height: 2.85rem !important;
    display: flex !important; align-items: center !important;
    justify-content: center !important; cursor: pointer !important;
    border-radius: 10px !important; font-weight: 700 !important;
    font-size: 0.92rem !important; letter-spacing: 0.02em !important;
    transition: all 0.18s ease !important;
    /* Force text to always be visible — never inherit transparent */
    color: #1D4ED8 !important;
}
/* Ensure inner <p> and <span> inside buttons are also visible */
.stButton > button p,
.stButton > button span,
[data-testid="stDownloadButton"] > button p,
[data-testid="stDownloadButton"] > button span {
    color: inherit !important;
}

/* Primary buttons — blue with bright white text */
.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #2563EB 0%, #1A45C0 100%) !important;
    color: #FFFFFF !important; border: none !important;
    box-shadow: 0 3px 10px rgba(37,99,235,0.40), 0 1px 3px rgba(37,99,235,0.25) !important;
    padding: 0.65rem 1.5rem !important;
    text-shadow: 0 1px 2px rgba(0,0,0,0.15) !important;
}
.stButton > button[kind="primary"] p,
.stButton > button[kind="primary"] span,
button[data-testid="baseButton-primary"] p,
button[data-testid="baseButton-primary"] span {
    color: #FFFFFF !important;
}
.stButton > button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(135deg, #1D4ED8 0%, #1535A8 100%) !important;
    color: #FFFFFF !important;
    box-shadow: 0 8px 22px rgba(37,99,235,0.45), 0 2px 5px rgba(37,99,235,0.25) !important;
    transform: translateY(-2px) !important;
}
.stButton > button[kind="primary"]:active,
button[data-testid="baseButton-primary"]:active {
    transform: translateY(0px) !important;
    box-shadow: 0 2px 6px rgba(37,99,235,0.3) !important;
}
.stButton > button[kind="primary"]:disabled,
button[data-testid="baseButton-primary"]:disabled {
    background: #C5D5F0 !important; border: none !important; color: #7A95C5 !important;
    box-shadow: none !important; cursor: not-allowed !important; opacity: 1 !important;
}

/* Secondary buttons — clear dark text on white */
.stButton > button:not([kind="primary"]) {
    background: #FFFFFF !important; color: #1D4ED8 !important;
    border: 2px solid #93B0E8 !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.07) !important;
    padding: 0.65rem 1.2rem !important;
}
.stButton > button:not([kind="primary"]) p,
.stButton > button:not([kind="primary"]) span {
    color: #1D4ED8 !important;
}
.stButton > button:not([kind="primary"]):hover {
    border-color: #2563EB !important; background: #EFF6FF !important;
    color: #1535A8 !important;
    box-shadow: 0 4px 12px rgba(37,99,235,0.18) !important;
    transform: translateY(-2px) !important;
}
.stButton > button:not([kind="primary"]):hover p,
.stButton > button:not([kind="primary"]):hover span {
    color: #1535A8 !important;
}
.stButton > button:not([kind="primary"]):disabled {
    color: #A0B0C8 !important; border-color: #DDE4F0 !important;
    background: #F8FAFC !important; box-shadow: none !important;
}

/* Download buttons — always bold white on blue */
[data-testid="stDownloadButton"] > button {
    background: linear-gradient(135deg, #2563EB 0%, #1A45C0 100%) !important;
    color: #FFFFFF !important; border: none !important; font-weight: 700 !important;
    box-shadow: 0 3px 10px rgba(37,99,235,0.40) !important;
    text-shadow: 0 1px 2px rgba(0,0,0,0.15) !important;
}
[data-testid="stDownloadButton"] > button p,
[data-testid="stDownloadButton"] > button span {
    color: #FFFFFF !important;
}
[data-testid="stDownloadButton"] > button:hover {
    background: linear-gradient(135deg, #1D4ED8 0%, #1535A8 100%) !important;
    color: #FFFFFF !important;
    box-shadow: 0 8px 22px rgba(37,99,235,0.45) !important;
    transform: translateY(-2px) !important;
}

/* ── Streamlit native tooltip / help icon ─────────────── */
[data-testid="stTooltipIcon"] { color: #2563EB !important; opacity: 1 !important; }

/* Tooltip popup container — every selector Streamlit uses */
div[role="tooltip"],
[data-testid="stTooltipContent"],
[data-testid="stTooltipPopover"],
.stTooltipContent,
[data-radix-popper-content-wrapper] > div,
[data-radix-tooltip-content] {
    background: #0D1526 !important;
    color: #F0F4FF !important;
    font-size: 0.85rem !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    padding: 8px 12px !important;
    box-shadow: 0 6px 20px rgba(0,0,0,0.3) !important;
    max-width: 300px !important;
    line-height: 1.6 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
}

/* Force ALL children inside any tooltip to use bright text —
   overrides the global p/span/label rules that bleed in */
div[role="tooltip"] *,
[data-testid="stTooltipContent"] *,
[data-testid="stTooltipPopover"] *,
[data-radix-popper-content-wrapper] > div *,
[data-radix-tooltip-content] * {
    color: #F0F4FF !important;
    background: transparent !important;
}

/* Arrow */
div[role="tooltip"]::before,
[data-testid="stTooltipContent"]::before {
    border-bottom-color: #0D1526 !important;
}

/* ── Layout helpers ───────────────────────────────────── */
[data-testid="column"] { display: flex !important; flex-direction: column !important; justify-content: flex-start !important; }
[data-testid="stHorizontalBlock"] { align-items: stretch !important; gap: 0.75rem !important; }

/* ── Radio Pills ──────────────────────────────────────── */
.stRadio > div { gap: 0.5rem !important; flex-direction: row !important; flex-wrap: wrap !important; }
.stRadio > div > label {
    background: #FFFFFF !important; border: 1.5px solid #D4DCE9 !important;
    border-radius: 9px !important; padding: 0.5rem 1.2rem !important;
    cursor: pointer !important;
    transition: border-color 0.17s, background 0.17s, box-shadow 0.17s !important;
    font-weight: 600 !important; font-size: 0.88rem !important; color: #4A5C78 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
}
.stRadio > div > label:hover { border-color: #93B0E8 !important; color: #2563EB !important; }
.stRadio > div > label:has(input:checked) {
    border-color: #2563EB !important; background: #EFF6FF !important;
    color: #1D4ED8 !important; font-weight: 700 !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.15) !important;
}

/* ── Alerts ───────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px !important; border-left-width: 4px !important;
    font-size: 0.9rem !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05) !important;
}

/* ── Metrics ──────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #FFFFFF !important; border: 1px solid #E0E8F4 !important;
    border-radius: 12px !important; padding: 1.1rem 1.4rem !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.75rem !important; font-weight: 700 !important;
    color: #7A8BA8 !important; text-transform: uppercase !important; letter-spacing: 0.07em !important;
}
[data-testid="stMetricValue"] { font-size: 2.1rem !important; font-weight: 800 !important; color: #0D1526 !important; }

/* ── Expanders ────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #FFFFFF !important; border: 1px solid #E0E8F4 !important;
    border-radius: 12px !important; margin-bottom: 0.75rem !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04) !important; overflow: hidden !important;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important; font-size: 0.93rem !important;
    color: #1E2D4A !important; padding: 0.9rem 1.2rem !important;
}
[data-testid="stExpander"] summary:hover { background: #F5F7FC !important; }

/* ── Dividers ─────────────────────────────────────────── */
hr { border: none !important; border-top: 1px solid #E0E8F4 !important; margin: 1.25rem 0 !important; }

/* ── Checkbox ─────────────────────────────────────────── */
.stCheckbox label { color: #2D3F5C !important; font-weight: 400 !important; font-size: 0.92rem !important; }

/* ── Progress ─────────────────────────────────────────── */
.stProgress > div > div {
    background: linear-gradient(90deg, #2563EB, #60A5FA) !important;
    border-radius: 99px !important;
}
.stProgress > div { border-radius: 99px !important; background: #E0E8F4 !important; }

/* ── Spinner ──────────────────────────────────────────── */
[data-testid="stSpinner"] p { color: #7A8BA8 !important; font-size: 0.88rem !important; }

/* ── Tech badges ──────────────────────────────────────── */
.tech-badge {
    display: inline-block; padding: 3px 10px; border-radius: 6px;
    font-size: 11px; font-weight: 700; margin: 2px 2px; letter-spacing: 0.03em;
}
.score-chip {
    display: inline-block; padding: 4px 14px; border-radius: 6px;
    font-size: 13px; font-weight: 700; margin: 0 4px;
}

/* ── App Header ───────────────────────────────────────── */
.app-header {
    display: flex; align-items: center; gap: 16px;
    margin-bottom: 1.75rem;
    padding: 1.4rem 2rem;
    background: linear-gradient(135deg, #0D1526 0%, #1E3A7A 100%);
    border-radius: 0 0 16px 16px;
    position: relative; overflow: hidden;
}
.app-header::before {
    content: ''; position: absolute; top: -40px; right: -40px;
    width: 200px; height: 200px;
    background: radial-gradient(circle, rgba(37,99,235,0.4) 0%, transparent 70%);
    pointer-events: none;
}
.app-header-icon {
    width: 48px; height: 48px;
    background: rgba(37,99,235,0.9);
    border-radius: 12px; box-shadow: 0 4px 12px rgba(37,99,235,0.4);
    display: flex; align-items: center; justify-content: center;
    font-size: 24px; flex-shrink: 0;
}
.app-header-title {
    font-size: 1.35rem !important; font-weight: 800 !important;
    color: #FFFFFF !important; line-height: 1.2 !important; margin: 0 !important;
    letter-spacing: -0.3px !important;
}
.app-header-sub { font-size: 0.8rem; color: rgba(255,255,255,0.6); margin: 3px 0 0 0; }
.app-header-pill {
    margin-left: auto; background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.2); border-radius: 99px;
    padding: 4px 14px; font-size: 0.75rem; font-weight: 600;
    color: rgba(255,255,255,0.85); letter-spacing: 0.03em; white-space: nowrap;
}

/* ── Section headers ──────────────────────────────────── */
.section-label {
    display: inline-flex; align-items: center; gap: 7px;
    color: #7A8BA8; font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 0.35rem;
}
.section-divider {
    display: flex; align-items: center; gap: 10px;
    margin: 1.5rem 0 1rem 0;
}
.section-divider-line {
    flex: 1; height: 1px; background: #E0E8F4;
}
.section-divider-label {
    font-size: 0.72rem; font-weight: 700; color: #7A8BA8;
    letter-spacing: 0.08em; text-transform: uppercase;
    background: #F0F2F8; padding: 2px 10px; border-radius: 99px;
    border: 1px solid #E0E8F4;
}

/* ── Result cards ─────────────────────────────────────── */
.result-card {
    background: #FFFFFF; border: 1px solid #E0E8F4; border-radius: 12px;
    padding: 1.1rem 1.4rem; margin-bottom: 0.6rem;
    box-shadow: 0 2px 6px rgba(0,0,0,0.04);
    transition: box-shadow 0.2s ease, border-color 0.2s ease, transform 0.15s ease;
}
.result-card:hover {
    box-shadow: 0 8px 24px rgba(13,21,38,0.1); border-color: #B8CDEF;
    transform: translateY(-2px);
}

/* ── Search form card ─────────────────────────────────── */
.search-card {
    background: #FFFFFF; border: 1px solid #E0E8F4; border-radius: 14px;
    padding: 1.6rem 1.75rem; margin-bottom: 1.25rem;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}

/* ── Footer ───────────────────────────────────────────── */
.app-footer {
    margin-top: 3rem; padding-top: 1.25rem; border-top: 1px solid #E0E8F4;
    font-size: 0.78rem; color: #A0B0C8; text-align: center; letter-spacing: 0.01em;
}

/* ── Sidebar ──────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0D1526 0%, #1a2540 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
    min-width: 260px !important;
    max-width: 260px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 0 !important;
}
/* Style the collapse toggle button to be visible on dark bg */
[data-testid="stSidebarCollapseButton"] button {
    background: rgba(255,255,255,0.1) !important;
    color: white !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
    border-radius: 6px !important;
}
/* Expand button (shown when sidebar is collapsed) */
[data-testid="stSidebarCollapsedControl"] button {
    background: #0D1526 !important;
    color: white !important;
    border: 1px solid rgba(255,255,255,0.2) !important;
}
[data-testid="stSidebar"] * { color: rgba(255,255,255,0.88) !important; }
/* But buttons inside sidebar must keep their own explicit colors */
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton > button p,
[data-testid="stSidebar"] .stButton > button span,
[data-testid="stSidebar"] .stButton > button div {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.07) !important;
    color: #FFFFFF !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    box-shadow: none !important;
    border-radius: 8px !important; font-weight: 600 !important;
    font-size: 0.9rem !important; text-align: left !important;
    justify-content: flex-start !important; padding: 0.6rem 0.9rem !important;
    width: 100% !important; transition: all 0.15s ease !important;
}
[data-testid="stSidebar"] .stButton > button p,
[data-testid="stSidebar"] .stButton > button span {
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.16) !important;
    color: #FFFFFF !important;
    border-color: rgba(255,255,255,0.28) !important;
    transform: none !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border: none !important;
    box-shadow: 0 2px 8px rgba(37,99,235,0.5) !important;
    font-weight: 700 !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: #1D4ED8 !important;
    color: #FFFFFF !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.1) !important;
}
.sidebar-logo {
    padding: 1.25rem 0.9rem 0.5rem 0.9rem;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 0.5rem;
}
.sidebar-section-label {
    font-size: 0.68rem !important; font-weight: 700 !important;
    color: rgba(255,255,255,0.35) !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important; padding: 0.8rem 0.9rem 0.3rem 0.9rem !important;
}
.sidebar-user-info {
    padding: 0.75rem 0.9rem;
    background: rgba(255,255,255,0.05);
    border-radius: 10px;
    margin: 0.5rem 0.5rem;
    font-size: 0.82rem;
}
</style>
<script>
(function() {
  function tryOpenSidebar() {
    var btn = document.querySelector('[data-testid="stSidebarCollapsedControl"] button');
    if (btn) { btn.click(); return true; }
    return false;
  }
  // Try immediately and after short delays for initial load
  setTimeout(tryOpenSidebar, 300);
  setTimeout(tryOpenSidebar, 800);
  setTimeout(tryOpenSidebar, 1500);
  // Watch for sidebar being collapsed and reopen it
  var obs = new MutationObserver(function() {
    tryOpenSidebar();
  });
  document.addEventListener('DOMContentLoaded', function() {
    obs.observe(document.body, { childList: true, subtree: false });
    tryOpenSidebar();
  });
})();
</script>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGE SELECTION — shown once at startup, stored in session_state
# ─────────────────────────────────────────────────────────────────────────────
if "lang" not in st.session_state:
    st.markdown("""
<div style="display:flex;align-items:center;justify-content:center;min-height:58vh;flex-direction:column;gap:1.75rem;">
  <div style="text-align:center;">
    <div style="
      width:72px;height:72px;
      background:linear-gradient(135deg,#0D1526 0%,#1E3A7A 100%);
      border-radius:20px;margin:0 auto 1.25rem auto;
      display:flex;align-items:center;justify-content:center;
      font-size:32px;box-shadow:0 8px 24px rgba(37,99,235,0.35);">⚡</div>
    <div style="font-size:2.2rem;font-weight:800;color:#0D1526;margin-bottom:0.3rem;letter-spacing:-0.5px;">
      fast.site <span style="color:#2563EB;font-weight:400;font-size:1.4rem;letter-spacing:0;">Lead Finder</span>
    </div>
    <div style="font-size:0.95rem;color:#7A8BA8;margin-bottom:0.2rem;">
      Find slow websites · Extract contacts · Generate cold emails
    </div>
    <div style="display:inline-block;background:#EFF6FF;color:#2563EB;border:1px solid #BFDBFE;
      border-radius:99px;padding:4px 16px;font-size:0.78rem;font-weight:700;letter-spacing:0.05em;
      text-transform:uppercase;margin-top:0.75rem;">Choose your language · Sprache wählen</div>
  </div>
</div>
""", unsafe_allow_html=True)

    col_l, col_mid, col_r = st.columns([2, 2, 2])
    with col_mid:
        st.markdown("<div style='height:1rem;'></div>", unsafe_allow_html=True)
        if st.button("🇬🇧  English", use_container_width=True, type="primary"):
            st.session_state["lang"] = "en"
            st.rerun()
        st.markdown("<div style='height:0.5rem;'></div>", unsafe_allow_html=True)
        if st.button("🇩🇪  Deutsch", use_container_width=True):
            st.session_state["lang"] = "de"
            st.rerun()
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# TRANSLATION HELPER
# ─────────────────────────────────────────────────────────────────────────────
_LANG: str = st.session_state.get("lang", "en")

def _t(en: str, de: str) -> str:
    return de if _LANG == "de" else en

# ─────────────────────────────────────────────────────────────────────────────
# URL VALIDATION
# ─────────────────────────────────────────────────────────────────────────────
_URL_RE = re.compile(
    r"^(?:https?://)?"           # optional scheme
    r"(?:[A-Za-z0-9-]+\.)+"     # one or more subdomain/domain labels
    r"[A-Za-z]{2,}"             # TLD (at least 2 letters)
    r"(?:[/?#][^\s]*)?"         # optional path/query/fragment
    r"$",
    re.IGNORECASE,
)

def _is_valid_url(raw: str) -> bool:
    """Return True only if raw looks like a real hostname/URL."""
    if not raw:
        return False
    # After stripping a leading scheme, there must be a dot-separated hostname
    stripped = re.sub(r"^https?://", "", raw.strip(), flags=re.I)
    if not _URL_RE.match(raw.strip()):
        return False
    # Must contain at least one dot in the host part
    host = stripped.split("/")[0].split("?")[0].split("#")[0]
    return "." in host

# ─────────────────────────────────────────────────────────────────────────────
# SEARCH — delegate entirely to search.py (no duplication)
# ─────────────────────────────────────────────────────────────────────────────
try:
    from search import search as _search_engine
    SEARCH_AVAILABLE = True
except ImportError:
    SEARCH_AVAILABLE = False

def multi_engine_search(industry: str, area: str, max_results: int = 20) -> tuple[list[dict], list[str]]:
    """Delegate to search.py's search() function."""
    if not SEARCH_AVAILABLE:
        return [], [_t("search.py not found", "search.py nicht gefunden")]
    results, engine = _search_engine(industry, area, max_results)
    return results, [engine] if isinstance(engine, str) else engine

# ─────────────────────────────────────────────────────────────────────────────
# TECH DETECTION  — CMS signatures & plugin detection
# ─────────────────────────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/123.0.0.0",
]

def _headers():
    return {"User-Agent": random.choice(USER_AGENTS)}

CMS_SIGNATURES: dict[str, list[tuple[str, float]]] = {
    "WordPress": [
        (r"/wp-content/themes/", 2.0), (r"/wp-content/plugins/", 2.0),
        (r"/wp-includes/js/", 2.0), (r"/wp-json/", 1.5),
        (r"wp-embed\.min\.js", 1.5), (r'content="WordPress', 1.5),
        (r"xmlrpc\.php", 1.0), (r"/wp-content/uploads/", 1.0),
        (r"wp-block-", 0.8), (r"class=\"wp-", 0.7), (r"WordPress", 0.5),
    ],
    "Shopify": [
        (r"cdn\.shopify\.com", 2.0), (r"myshopify\.com", 2.0),
        (r"Shopify\.theme", 2.0), (r"shopify-section", 1.5),
        (r"shopify\.com/s/files/", 1.5), (r'"shopify"', 1.0),
        (r"Shopify\.shop", 1.0), (r"/collections/", 0.5),
    ],
    "Wix": [
        (r"wixstatic\.com", 2.0), (r"wix\.com/_api/", 2.0),
        (r"X-Wix-Published-Version", 2.0), (r"wix-code", 1.5),
        (r"\"wix\"", 1.0), (r"parastorage\.com", 1.0), (r"wixsite\.com", 1.5),
    ],
    "Squarespace": [
        (r"squarespace\.com", 2.0), (r"sqsp\.net", 2.0),
        (r"static1\.squarespace\.com", 2.0), (r'"squarespace"', 1.5),
        (r"Squarespace-Headers", 1.5), (r"sqs-layout", 1.0), (r"data-sqs-type", 1.0),
    ],
    "Webflow": [
        (r"webflow\.com", 2.0), (r"webflow\.io", 2.0),
        (r"data-wf-page", 2.0), (r"data-wf-site", 2.0),
        (r"webflow\.js", 1.5), (r'"webflow"', 1.0),
    ],
    "Joomla": [
        (r"/components/com_content", 2.0), (r"/components/com_", 1.5),
        (r'content="Joomla', 2.0), (r"joomla", 1.0),
        (r"/media/system/js/", 0.8), (r"Joomla!", 0.8), (r"/administrator/", 0.5),
    ],
    "Drupal": [
        (r"/sites/default/files/", 2.0), (r"Drupal\.settings", 2.0),
        (r'content="Drupal', 2.0), (r"drupal\.js", 1.5),
        (r"drupal", 0.8), (r"/misc/drupal\.js", 1.5), (r"X-Generator.*Drupal", 2.0),
    ],
    "Magento": [
        (r"Mage\.Cookies", 2.0), (r"/skin/frontend/", 2.0),
        (r"magento", 1.0), (r"var BLANK_URL", 1.0),
        (r"Magento_", 1.5), (r"/pub/static/frontend/", 1.5),
    ],
    "Ghost": [
        (r"content\.ghost\.io", 2.0), (r"ghost\.io", 1.5),
        (r'content="Ghost', 2.0), (r"ghost-theme", 1.5), (r"/ghost/api/", 2.0),
    ],
    "Next.js": [(r"_next/static/chunks/", 2.0), (r"__NEXT_DATA__", 2.0), (r"_next/image", 1.5)],
    "Nuxt.js": [(r"__nuxt", 2.0), (r"_nuxt/", 2.0), (r"nuxt-link", 1.5), (r"window\.__nuxt", 2.0)],
    "Gatsby":  [(r"gatsby-", 1.5), (r"/static/gatsby-", 2.0), (r"window\.___gatsby", 2.0)],
    "HubSpot CMS": [(r"hs-scripts\.com", 2.0), (r"hubspot\.com", 1.5), (r"hs-analytics", 1.5)],
    "Framer": [(r"framer\.com", 2.0), (r"framerusercontent\.com", 2.0)],
    "BigCommerce": [(r"bigcommerce\.com", 2.0), (r"cdn\.bigcommerce\.com", 2.0)],
}

HEADER_CMS_MAP: dict[str, str] = {
    "x-shopify-stage": "Shopify", "x-shopid": "Shopify",
    "x-wix-request-id": "Wix", "x-ghost-cache-status": "Ghost",
    "x-drupal-cache": "Drupal", "x-generator": None,
    "x-powered-by-squarespace": "Squarespace",
}

GENERATOR_MAP: dict[str, str] = {
    "wordpress": "WordPress", "joomla": "Joomla", "drupal": "Drupal",
    "ghost": "Ghost", "craft cms": "Craft CMS", "typo3": "TYPO3",
    "squarespace": "Squarespace", "webflow": "Webflow", "framer": "Framer",
    "wix": "Wix", "blogger": "Blogger", "hubspot": "HubSpot CMS",
    "bigcommerce": "BigCommerce", "prestashop": "PrestaShop",
    "opencart": "OpenCart", "magento": "Magento",
}

_INFRASTRUCTURE_LABELS: dict[str, str] = {
    "cloudflare": "Cloudflare CDN", "fastly": "Fastly CDN",
    "akamai": "Akamai CDN", "cloudfront": "AWS CloudFront",
    "bunnycdn": "BunnyCDN", "b-cdn": "BunnyCDN",
}

PLUGIN_SIGNATURES: dict[str, str] = {
    "WooCommerce": r"woocommerce", "Elementor": r"elementor",
    "Yoast SEO": r"yoast|yoast-schema", "Rank Math SEO": r"rank-math|rankmath",
    "Contact Form 7": r"wpcf7|contact-form-7", "Gravity Forms": r"gform_|gravityforms",
    "WPML": r"\bwpml\b", "Akismet": r"akismet", "Jetpack": r"jetpack",
    "WP Rocket": r"wp-rocket|wprocket", "All-in-One SEO": r"aioseo|all-in-one-seo",
    "Divi Builder": r"divi|et_pb_", "WPBakery": r"wpb_|vc_",
    "Beaver Builder": r"fl-builder|beaver-builder",
    "Google Analytics 4": r"G-[A-Z0-9]{6,}|gtag\(.*G-",
    "Google Analytics UA": r"UA-\d{5,}-\d+",
    "Google Tag Manager": r"googletagmanager\.com|GTM-[A-Z0-9]+",
    "Facebook Pixel": r"fbq\(|facebook\.net/en_US/fbevents",
    "Hotjar": r"hotjar\.com|hjid", "Clarity (Microsoft)": r"clarity\.ms|microsoft.*clarity",
    "Mixpanel": r"mixpanel\.com", "Segment": r"segment\.com|analytics\.js",
    "Intercom": r"intercom\.io|intercomcdn", "Tawk.to": r"tawk\.to",
    "Zendesk Chat": r"zendesk\.com|zopim\.com", "Crisp Chat": r"crisp\.chat",
    "Drift": r"drift\.com", "Tidio": r"tidio", "LiveChat": r"livechatinc\.com",
    "Cloudflare": r"cloudflare", "Fastly": r"fastly",
    "AWS CloudFront": r"cloudfront\.net", "Akamai": r"akamai",
    "reCAPTCHA": r"recaptcha", "hCaptcha": r"hcaptcha",
    "Bootstrap": r"bootstrap\.min\.css|bootstrap\.css|bootstrap\.min\.js",
    "Tailwind CSS": r"tailwind|tailwindcss", "jQuery": r"jquery\.min\.js|jquery-\d",
    "React": r"react\.production\.min|react-dom|__react",
    "Vue.js": r"vue\.global|vue\.esm|vue@\d|createApp\(",
    "Angular": r"angular\.min\.js|ng-version|zone\.js",
    "Alpine.js": r"alpine\.min\.js|x-data=",
    "Next.js": r"__NEXT_DATA__|_next/static",
    "Nuxt.js": r"__nuxt|_nuxt/", "Svelte": r"svelte-",
    "Stripe": r"stripe\.com/v3|js\.stripe\.com", "PayPal": r"paypal\.com/sdk",
    "HubSpot Forms": r"hsforms\.net|hbspt\.forms", "Mailchimp": r"mailchimp\.com|mc\.js",
    "Klaviyo": r"klaviyo\.com|kl-private", "ActiveCampaign": r"activecampaign\.com",
    "Cookiebot": r"cookiebot\.com", "OneTrust": r"onetrust\.com|onetrust-banner",
    "CookieYes": r"cookieyes\.com",
}

def _extract_generator_meta(soup) -> str | None:
    tag = soup.find("meta", attrs={"name": re.compile(r"^generator$", re.I)})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None

def _resolve_unknown_cms(t: dict) -> tuple[str, str | None]:
    plugins_lc = " ".join(t.get("plugins", [])).lower()
    svr_raw    = t.get("server") or ""
    svr_lc     = svr_raw.lower()
    if "next.js" in plugins_lc:   return "Next.js", "medium"
    if "nuxt.js" in plugins_lc:   return "Nuxt.js", "medium"
    if "react"   in plugins_lc:   return "Custom (React)", "low"
    if "angular" in plugins_lc:   return "Custom (Angular)", "low"
    if "vue.js"  in plugins_lc:   return "Custom (Vue)", "low"
    if "wordpress" in plugins_lc or "woocommerce" in plugins_lc: return "WordPress", "medium"
    if "shopify"    in plugins_lc: return "Shopify", "medium"
    if "wix"        in plugins_lc: return "Wix", "medium"
    if "squarespace"in plugins_lc: return "Squarespace", "medium"
    if "webflow"    in plugins_lc: return "Webflow", "medium"
    if "drupal"     in plugins_lc: return "Drupal", "medium"
    if "joomla"     in plugins_lc: return "Joomla", "medium"
    if "svelte"     in plugins_lc: return "Custom (Svelte)", "low"
    if "gatsby"     in plugins_lc: return "Gatsby", "low"
    if svr_lc:
        for infra_key, infra_label in _INFRASTRUCTURE_LABELS.items():
            if infra_key in svr_lc:
                return f"Hidden behind {infra_label}", "low"
        if "php" in svr_lc:
            return "Custom PHP site", "low"
        svr_label = svr_raw.split("/")[0].strip()[:20] or "Unknown server"
        return f"Custom site ({svr_label})", "low"
    return "Unknown", None

def detect_tech(url: str, timeout: int = 12) -> dict:
    result: dict = {
        "cms": "Unknown", "cms_confidence": None,
        "plugins": [], "frameworks": [],
        "server": None, "https": url.startswith("https"), "ip": None, "error": None,
    }
    try:
        resp     = requests.get(url, headers=_headers(), timeout=timeout, allow_redirects=True, stream=False)
        raw_html = resp.text
        html_lc  = raw_html.lower()
        hdrs     = resp.headers
        hdrs_lc  = {k.lower(): v.lower() for k, v in hdrs.items()}
        soup     = BeautifulSoup(raw_html, "lxml")

        result["server"] = (hdrs.get("Server") or hdrs.get("X-Powered-By") or hdrs.get("x-powered-by") or None)
        try:
            result["ip"] = socket.gethostbyname(urlparse(url).netloc)
        except Exception:
            pass

        cms_detected = "Unknown"
        confidence   = None

        gen = _extract_generator_meta(soup)
        if gen:
            gen_lc = gen.lower()
            for keyword, cms_name in GENERATOR_MAP.items():
                if keyword in gen_lc:
                    cms_detected = cms_name; confidence = "high"; break

        if cms_detected == "Unknown":
            for hdr_key, cms_name in HEADER_CMS_MAP.items():
                if hdr_key in hdrs_lc:
                    if cms_name:
                        cms_detected = cms_name; confidence = "high"; break
                    elif hdr_key == "x-generator":
                        val = hdrs_lc[hdr_key]
                        for keyword, cname in GENERATOR_MAP.items():
                            if keyword in val:
                                cms_detected = cname; confidence = "high"; break
                    if cms_detected != "Unknown":
                        break
            if cms_detected == "Unknown":
                xpb = hdrs_lc.get("x-powered-by", "")
                for keyword, cname in GENERATOR_MAP.items():
                    if keyword in xpb:
                        cms_detected = cname; confidence = "high"; break

        if cms_detected == "Unknown":
            best_cms = "Unknown"; best_score = 0.0
            combined = html_lc + " " + str(hdrs_lc)
            for cms_name, patterns in CMS_SIGNATURES.items():
                total = sum(w for pat, w in patterns if re.search(pat, combined, re.I))
                if total > best_score:
                    best_score = total; best_cms = cms_name
            if best_score >= 2.0:
                cms_detected = best_cms
                confidence   = "high" if best_score >= 3.0 else "medium"
            elif best_score >= 1.0:
                cms_detected = best_cms; confidence = "low"

        result["cms"]            = cms_detected
        result["cms_confidence"] = confidence
        found = [name for name, pat in PLUGIN_SIGNATURES.items() if re.search(pat, html_lc, re.I)]
        result["plugins"] = found
    except Exception as e:
        result["error"] = str(e)
    return result

# ─────────────────────────────────────────────────────────────────────────────
# AUDIT
# ─────────────────────────────────────────────────────────────────────────────
try:
    from audit import audit_website
    from audit_pdf import generate_audit_pdf
    AUDIT_AVAILABLE = True
except ImportError:
    AUDIT_AVAILABLE = False
    def audit_website(url, progress_callback=None):
        try:
            start = time.time()
            r     = requests.get(url, headers=_headers(), timeout=15)
            ttfb  = round((time.time() - start) * 1000)
            soup  = BeautifulSoup(r.text, "lxml")
        except Exception:
            return {"url": url, "overall_score": 0, "breakdown": {}, "lighthouse_details": {}, "fastsite_projection": {}}
        score = 0; issues = []; strengths = []
        if url.startswith("https"):
            score += 15; strengths.append("HTTPS enabled")
        else:
            issues.append("No HTTPS")
        title = soup.find("title")
        if title and title.get_text(strip=True):
            score += 10; strengths.append("Title tag present")
        else:
            issues.append("Missing title tag")
        h1s = soup.find_all("h1")
        if len(h1s) == 1:   score += 10; strengths.append("Single H1 tag")
        elif not h1s:        issues.append("No H1 tag")
        meta = soup.find("meta", attrs={"name": re.compile("description", re.I)})
        if meta and meta.get("content", "").strip():
            score += 10; strengths.append("Meta description present")
        else:
            issues.append("No meta description")
        ttfb_score = 30 if ttfb < 500 else (20 if ttfb < 1000 else 5)
        score += ttfb_score
        if ttfb < 500: strengths.append(f"Fast TTFB: {ttfb}ms")
        else:          issues.append(f"Slow TTFB: {ttfb}ms")
        return {
            "url": url, "overall_score": min(score + 25, 100),
            "breakdown": {"seo": {"score": score, "issues": issues, "strengths": strengths, "details": {}}},
            "lighthouse_details": {}, "fastsite_projection": {},
        }

    def generate_audit_pdf(audit, lang="en"):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
            buf    = io.BytesIO()
            doc    = SimpleDocTemplate(buf, pagesize=A4)
            styles = getSampleStyleSheet()
            story  = [Paragraph(f"Audit: {audit.get('url')}", styles["Title"]),
                      Paragraph(f"Score: {audit.get('overall_score')}/100", styles["Normal"])]
            for cat, data in audit.get("breakdown", {}).items():
                story.append(Paragraph(f"{cat}: {data.get('score')}/100", styles["Heading2"]))
                for iss in data.get("issues", []):
                    story.append(Paragraph(f"[!] {iss}", styles["Normal"]))
            doc.build(story)
            return buf.getvalue()
        except Exception:
            return b"%PDF-placeholder"

# ─── Lead generation tools ────────────────────────────────────────────────────
try:
    from lead_tools import (
        varnish_opportunity_score,
        opportunity_label,
        generate_cold_email,
        build_leads_csv,
    )
    LEAD_TOOLS_AVAILABLE = True
except ImportError:
    LEAD_TOOLS_AVAILABLE = False
    def varnish_opportunity_score(audit): return 0
    def opportunity_label(score): return ("—", "#888")
    def generate_cold_email(**kw): return "lead_tools.py not found"
    def build_leads_csv(*a, **kw): return b""

def _add_contacted_column(csv_bytes: bytes, contacted_map: dict) -> bytes:
    """Append 'Contacted' / 'Contacted At' columns to an exported leads CSV,
    matched against whichever column holds the site URL."""
    if not csv_bytes or not contacted_map:
        return csv_bytes
    try:
        df = pd.read_csv(io.BytesIO(csv_bytes))
        url_col = next((c for c in df.columns if "url" in c.lower()), None)
        if not url_col:
            return csv_bytes
        df["Contacted"]    = df[url_col].apply(lambda u: "Yes" if u in contacted_map else "No")
        df["Contacted At"] = df[url_col].apply(lambda u: contacted_map.get(u, {}).get("at", ""))
        return df.to_csv(index=False).encode("utf-8")
    except Exception:
        return csv_bytes

try:
    from contact_extractor import extract_contact_info, detect_cdn
    CONTACT_AVAILABLE = True
except ImportError:
    CONTACT_AVAILABLE = False
    def extract_contact_info(url): return {"emails": [], "phones": [], "contact_page": None, "primary_email": None}
    def detect_cdn(url): return {"has_cdn": False, "cdn_name": None, "is_hot_lead": True}

# ─── Preview Measurement API ──────────────────────────────────────────────────
try:
    from preview_api import run_preview_measurement, render_preview_results, get_preview_api_key
    PREVIEW_API_AVAILABLE = True
except ImportError:
    PREVIEW_API_AVAILABLE = False
    def get_preview_api_key(): return None

# ─────────────────────────────────────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────────────────────────────────────
_CMS_COLORS: dict[str, tuple[str, str]] = {
    "WordPress": ("#21759B", "#21759B18"), "Shopify": ("#5E8E3E", "#96BF4818"),
    "Wix": ("#B07D00", "#FAAD1418"), "Squarespace": ("#333333", "#33333318"),
    "Webflow": ("#2D3AC0", "#4353FF18"), "Joomla": ("#C03D1E", "#F44E2718"),
    "Drupal": ("#0678BE", "#0678BE18"), "Magento": ("#C24E12", "#EE672218"),
    "Ghost": ("#738A94", "#738A9418"), "PrestaShop": ("#DF0067", "#DF006718"),
    "Next.js": ("#000000", "#00000015"), "Nuxt.js": ("#00C58E", "#00C58E18"),
    "Gatsby": ("#663399", "#66339918"), "HubSpot CMS": ("#FF7A59", "#FF7A5918"),
    "Framer": ("#0099FF", "#0099FF18"), "BigCommerce": ("#34313F", "#34313F18"),
    "Unknown": ("#888888", "#88888815"),
}

def _cms_badge(cms: str, confidence: str | None = None) -> str:
    fg, bg = _CMS_COLORS.get(cms, ("#888888", "#88888815"))
    conf_icon = {"high": " ✓", "medium": " ~", "low": " "}.get(confidence or "", "")
    return (
        f'<span class="tech-badge" style="background:{bg};color:{fg};'
        f'border:1px solid {fg}55;font-weight:700;">{cms}{conf_icon}</span>'
    )

def _score_color(s):
    return "#2E7D32" if s >= 75 else ("#F57F17" if s >= 50 else "#C62828")

def _render_tech_badges(t: dict) -> str:
    cms  = t.get("cms", "Unknown")
    conf = t.get("cms_confidence")
    if cms == "Unknown":
        cms, conf = _resolve_unknown_cms(t)
    if cms == "Unknown":
        cms_html = '<span class="tech-badge" style="background:#88888815;color:#888;border:1px solid #88888844;">CMS not detected</span>'
    else:
        cms_html = _cms_badge(cms, conf)
    plug_html = " ".join(
        f'<span class="tech-badge" style="background:#6C63FF18;color:#4B44CC;border:1px solid #6C63FF44;">{p}</span>'
        for p in t.get("plugins", [])[:8]
    )
    svr_txt = t.get("server", "")
    svr = (
        f'<span class="tech-badge" style="background:#88888815;color:#555;border:1px solid #88888844;">🖥 {svr_txt[:30]}</span>'
        if svr_txt else ""
    )
    err_txt = t.get("error", "")
    err = (
        f'<span class="tech-badge" style="background:#ff000015;color:#c00;border:1px solid #ff000044;">⚠ {err_txt[:40]}</span>'
        if err_txt else ""
    )
    return cms_html + " " + plug_html + " " + svr + " " + err

# ─────────────────────────────────────────────────────────────────────────────
# REP LOGIN / IDENTITY GATE
# ─────────────────────────────────────────────────────────────────────────────
# Minimal access control: an optional shared team password (set TEAM_PASSWORD
# in secrets.toml to require it) plus a mandatory rep name, so anyone using
# the tool is identified and every email/PDF/CSV is branded with their name.
_TEAM_PASSWORD = _get_secret("TEAM_PASSWORD")

if "_authenticated" not in st.session_state:
    st.session_state["_authenticated"] = not bool(_TEAM_PASSWORD)
if "rep_name" not in st.session_state:
    st.session_state["rep_name"] = ""

if not st.session_state["_authenticated"] or not st.session_state["rep_name"]:
    st.markdown(f"""
<div style="max-width:420px;margin:6rem auto 1rem auto;text-align:center;">
  <div style="font-size:2.2rem;">⚡</div>
  <h1 style="margin-bottom:0;">fast.site — Lead Finder</h1>
  <p style="color:#7A8BA8;font-size:0.9rem;">{_t('Sign in to continue', 'Anmelden, um fortzufahren')}</p>
</div>
""", unsafe_allow_html=True)
    _form_col1, _form_col2, _form_col3 = st.columns([1, 1.4, 1])
    with _form_col2:
        with st.form("rep_login_form"):
            _rep_name_input = st.text_input(
                _t("Your name", "Ihr Name"),
                value=st.session_state.get("rep_name", ""),
                placeholder=_t("e.g. Alex Carter", "z. B. Alex Carter"),
            )
            _pwd_input = ""
            if _TEAM_PASSWORD:
                _pwd_input = st.text_input(_t("Team password", "Team-Passwort"), type="password")
            _submitted = st.form_submit_button(_t("Continue", "Weiter"), use_container_width=True, type="primary")
        if _submitted:
            if not _rep_name_input.strip():
                st.error(_t("Please enter your name.", "Bitte geben Sie Ihren Namen ein."))
            elif _TEAM_PASSWORD and _pwd_input != _TEAM_PASSWORD:
                st.error(_t("Incorrect team password.", "Falsches Team-Passwort."))
            else:
                st.session_state["rep_name"]       = _rep_name_input.strip()
                st.session_state["_authenticated"] = True
                st.rerun()

    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────
if "nav_mode" not in st.session_state:
    st.session_state["nav_mode"] = "search"   # "search" | "direct"

with st.sidebar:
    # Logo / Brand
    st.markdown("""
<div class="sidebar-logo">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:36px;height:36px;background:linear-gradient(135deg,#2563EB,#1D4ED8);
      border-radius:9px;display:flex;align-items:center;justify-content:center;
      font-size:18px;flex-shrink:0;box-shadow:0 3px 10px rgba(37,99,235,0.4);">⚡</div>
    <div>
      <div style="font-size:1.05rem;font-weight:800;color:#fff;line-height:1.1;">fast.site</div>
      <div style="font-size:0.72rem;color:rgba(255,255,255,0.45);font-weight:500;">Lead Finder</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # Navigation
    st.markdown('<div class="sidebar-section-label">Find Leads</div>', unsafe_allow_html=True)

    _nm = st.session_state.get("nav_mode", "search")
    if st.button("🔍  Search Businesses", key="nav_search", use_container_width=True,
                 type="primary" if _nm == "search" else "secondary"):
        if _nm != "search":
            for k in ["audits","results","engines","tech","direct_tech","direct_tech_skipped","direct_url_ready","selected_for_audit","_select_action"]:
                st.session_state.pop(k, None)
        st.session_state["nav_mode"] = "search"
        st.rerun()

    if st.button("🌐  Audit a Website", key="nav_direct", use_container_width=True,
                 type="primary" if _nm == "direct" else "secondary"):
        if _nm != "direct":
            for k in ["audits","results","engines","tech","direct_tech","direct_tech_skipped","direct_url_ready","selected_for_audit","_select_action"]:
                st.session_state.pop(k, None)
        st.session_state["nav_mode"] = "direct"
        st.rerun()

    st.markdown("---")
    st.markdown('<div class="sidebar-section-label">Account</div>', unsafe_allow_html=True)

    # Signed-in user
    rep = st.session_state.get("rep_name", "")
    st.markdown(f"""
<div class="sidebar-user-info">
  <div style="font-size:0.7rem;color:rgba(255,255,255,0.4);font-weight:600;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:3px;">Signed in as</div>
  <div style="font-size:0.88rem;font-weight:700;color:#fff;">👤 {rep}</div>
</div>
""", unsafe_allow_html=True)

    # Language switch
    _other_lang = "🇩🇪  Deutsch" if _LANG == "en" else "🇬🇧  English"
    if st.button(_other_lang, key="lang_switch_sb", use_container_width=True):
        st.session_state["lang"] = "de" if _LANG == "en" else "en"
        for k in ["audits","results","engines","tech","direct_tech","direct_tech_skipped","direct_url_ready","selected_for_audit","_select_action"]:
            st.session_state.pop(k, None)
        st.rerun()

    if st.button(f"🚪  {_t('Log out','Abmelden')}", key="logout_sb", use_container_width=True):
        for k in list(st.session_state.keys()):
            st.session_state.pop(k, None)
        st.rerun()

    st.markdown("---")
    st.markdown(f"""
<div style="padding:0.5rem 0.9rem;font-size:0.72rem;color:rgba(255,255,255,0.28);line-height:1.7;">
  ⚡ fast.site &nbsp;·&nbsp; Lead Finder<br>
  {_t("Find, audit & contact slow websites","Langsame Websites finden & kontaktieren")}
</div>
""", unsafe_allow_html=True)

# Pull the selected mode from session state
is_direct_mode = st.session_state.get("nav_mode", "search") == "direct"

# ── Page header ──────────────────────────────────────────────────────────────
if is_direct_mode:
    _page_title = _t("🌐 Audit a Website", "🌐 Website prüfen")
    _page_sub   = _t("Enter any website address to instantly check its speed, technology, and contact details.",
                     "Webadresse eingeben, um Geschwindigkeit, Technologie und Kontaktdaten sofort zu prüfen.")
else:
    _page_title = _t("🔍 Find Businesses", "🔍 Unternehmen finden")
    _page_sub   = _t("Search for businesses by type and location, then audit their websites to find the best opportunities.",
                     "Unternehmen nach Typ und Standort suchen, dann deren Websites prüfen.")

st.markdown(f"""
<div style="background:linear-gradient(135deg,#2563EB 0%,#1E40AF 100%);
  color:white;padding:22px 28px;border-radius:14px;margin-bottom:1.5rem;
  box-shadow:0 6px 24px rgba(37,99,235,0.22);">
  <div style="font-size:1.45rem;font-weight:800;color:#fff;margin-bottom:4px;">{_page_title}</div>
  <div style="font-size:0.875rem;color:rgba(255,255,255,0.8);">{_page_sub}</div>
</div>
""", unsafe_allow_html=True)

# ── MODE A: Direct URL Audit ─────────────────────────────────────────────────
if is_direct_mode:
    st.markdown(f"""
<div class="search-card">
  <p style="margin-bottom:0.75rem;font-weight:600;">{_t('Enter any website address to check its speed, technology and contact details.','Webadresse eingeben, um Geschwindigkeit, Technologie und Kontaktdaten zu prüfen.')}</p>

""", unsafe_allow_html=True)
    url_col, btn_col = st.columns([4, 1])
    with url_col:
        direct_url = st.text_input(
            _t("Website address", "Webadresse"),
            placeholder="https://example.com",
            label_visibility="collapsed",
            key="direct_url_input",
        )
    with btn_col:
        direct_go_btn = st.button(
            f"🚀 {_t('Audit this website', 'Website prüfen')}",
            type="primary",
            use_container_width=True,
        )

    if direct_go_btn:
        raw = direct_url.strip()
        if not raw:
            st.warning(_t("Please paste a website address first.", "Bitte geben Sie zuerst eine Webadresse ein."))
        elif not _is_valid_url(raw):
            st.error(_t(
                "That doesn't look like a valid website address. "
                "Please enter a real URL, e.g. **example.com** or **https://example.com**.",
                "Das sieht nicht wie eine gültige Webadresse aus. "
                "Bitte geben Sie eine echte URL ein, z.B. **beispiel.de** oder **https://beispiel.de**.",
            ))
        else:
            if not raw.startswith(("http://", "https://")):
                raw = "https://" + raw
            st.session_state["direct_url_ready"] = raw
            st.session_state.pop("direct_tech", None)
            st.session_state.pop("direct_tech_skipped", None)
            st.session_state.pop("audits", None)
            st.session_state.pop("results", None)
            st.session_state.get("contacts", {}).pop(raw, None)

            # One click does it all: tech detect -> audit + CDN -> contacts.
            # The live tracker updates after each step so users see progress.
            def _live_tracker(s1=False, s2=False, s3=False, s4=False, active_step=0):
                step_defs_live = [
                    (_t("Website submitted",   "Website eingereicht"),    s1),
                    (_t("Technology scanned",  "Technologie erkannt"),     s2),
                    (_t("Speed checked",       "Geschwindigkeit geprueft"), s3),
                    (_t("Contact info found",  "Kontaktdaten gefunden"),   s4),
                ]
                html = ""
                for i, (label, done) in enumerate(step_defs_live, start=1):
                    is_active = (active_step == i)
                    if done:
                        cc = "#16A34A"; tc = "#1E2D4A"; ic = "&#10003;"
                    elif is_active:
                        cc = "#2563EB"; tc = "#2563EB"; ic = "&#8943;"
                    else:
                        cc = "#CBD5E1"; tc = "#9AA5BC"; ic = str(i)
                    pulse = "animation:tracker-pulse 1s ease-in-out infinite;" if is_active else ""
                    html += (
                        f'<div style="display:flex;align-items:center;gap:6px;">'
                        f'<div style="width:22px;height:22px;border-radius:50%;background:{cc};'
                        f'color:#fff;font-size:{"13" if done else "11"}px;font-weight:700;'
                        f'display:flex;align-items:center;justify-content:center;flex-shrink:0;{pulse}">'
                        f'{ic}</div>'
                        f'<span style="font-size:11.5px;font-weight:{"700" if done or is_active else "600"};'
                        f'color:{tc};">{_t("Step","Schritt")} {i}: {label}</span></div>'
                    )
                    if i < len(step_defs_live):
                        lc = "#16A34A" if done else "#E2E8F0"
                        html += f'<div style="flex:1;height:2px;background:{lc};min-width:14px;"></div>'
                return (
                    '<style>@keyframes tracker-pulse{0%,100%{opacity:1}50%{opacity:0.4}}</style>'
                    '<div style="display:flex;align-items:center;gap:8px;background:#FFFFFF;'
                    'border:1px solid #E0E8F4;border-radius:10px;padding:12px 16px;margin-bottom:12px;">'
                    + html + '</div>'
                )

            _live_ph  = st.empty()
            _live_msg = st.empty()

            # Step 1 done, step 2 active
            _live_ph.markdown(_live_tracker(s1=True, active_step=2), unsafe_allow_html=True)
            _live_msg.info(f"\U0001f9ea {_t('Detecting tech stack...', 'Tech-Stack wird ermittelt...')}")
            st.session_state["direct_tech"] = {raw: detect_tech(raw)}

            # Step 2 done, step 3 active
            _live_ph.markdown(_live_tracker(s1=True, s2=True, active_step=3), unsafe_allow_html=True)
            _live_msg.info(f"\U0001f680 {_t('Auditing site speed & performance...', 'Geschwindigkeit & Performance werden geprueft...')}")
            result = audit_website(raw)
            cdn_map = st.session_state.get("cdn_map", {})
            cdn_map[raw] = detect_cdn(raw)
            st.session_state["cdn_map"] = cdn_map
            st.session_state["audits"] = {raw: result}

            if CONTACT_AVAILABLE:
                # Step 3 done, step 4 active
                _live_ph.markdown(_live_tracker(s1=True, s2=True, s3=True, active_step=4), unsafe_allow_html=True)
                _live_msg.info(f"\U0001f4e7 {_t('Extracting contact info...', 'Kontaktdaten werden extrahiert...')}")
                st.session_state.setdefault("contacts", {})[raw] = extract_contact_info(raw)
                st.session_state["_contact_auto_extracted"] = raw

            # All 4 steps complete
            _live_ph.markdown(_live_tracker(s1=True, s2=True, s3=True, s4=True), unsafe_allow_html=True)
            _live_msg.success(f"\u2705 {_t('All done! Scroll down to see results.', 'Fertig! Scrollen Sie nach unten.')}")
            time.sleep(0.8)
            _live_ph.empty()
            _live_msg.empty()
            st.rerun()

    ready_url = st.session_state.get("direct_url_ready", "")
    if ready_url:
        st.markdown("")

        direct_tech      = st.session_state.get("direct_tech", {})
        already_detected = ready_url in direct_tech
        _step3_done = ready_url in st.session_state.get("audits", {})
        _step4_done = ready_url in st.session_state.get("contacts", {})

        # ── Step progress tracker — live, updates after each step ────────────
        def _render_tracker(s1=False, s2=False, s3=False, s4=False, active_step=0):
            step_defs = [
                (_t("Website submitted",   "Website eingereicht"),    s1),
                (_t("Technology scanned",  "Technologie erkannt"),     s2),
                (_t("Speed checked",       "Geschwindigkeit geprüft"), s3),
                (_t("Contact info found",  "Kontaktdaten gefunden"),   s4),
            ]
            html = ""
            for i, (label, done) in enumerate(step_defs, start=1):
                is_active = (active_step == i)
                if done:
                    circle_col = "#16A34A"; text_col = "#1E2D4A"; icon = "✓"
                elif is_active:
                    circle_col = "#2563EB"; text_col = "#2563EB"; icon = "⋯"
                else:
                    circle_col = "#CBD5E1"; text_col = "#9AA5BC"; icon = str(i)
                pulse = "animation:tracker-pulse 1s ease-in-out infinite;" if is_active else ""
                html += (
                    f'<div style="display:flex;align-items:center;gap:6px;">'
                    f'<div style="width:22px;height:22px;border-radius:50%;background:{circle_col};'
                    f'color:#fff;font-size:{"13" if done else "11"}px;font-weight:700;'
                    f'display:flex;align-items:center;justify-content:center;flex-shrink:0;{pulse}">'
                    f'{icon}</div>'
                    f'<span style="font-size:11.5px;font-weight:{"700" if done or is_active else "600"};'
                    f'color:{text_col};">{_t("Step","Schritt")} {i}: {label}</span></div>'
                )
                if i < len(step_defs):
                    line_col = "#16A34A" if done else "#E2E8F0"
                    html += f'<div style="flex:1;height:2px;background:{line_col};min-width:14px;"></div>'
            return (
                '<style>@keyframes tracker-pulse{0%,100%{opacity:1}50%{opacity:0.4}}</style>'
                '<div style="display:flex;align-items:center;gap:8px;background:#FFFFFF;'
                'border:1px solid #E0E8F4;border-radius:10px;padding:12px 16px;margin-bottom:12px;">'
                + html + '</div>'
            )

        _tracker_ph = st.empty()
        _tracker_ph.markdown(
            _render_tracker(s1=True, s2=already_detected, s3=_step3_done, s4=_step4_done),
            unsafe_allow_html=True,
        )

        # Show tech badges if detected
        if already_detected:
            t = direct_tech[ready_url]
            st.markdown(
                f"**{_t('Website platform', 'Website-Plattform')}:** " + _render_tech_badges(t),
                unsafe_allow_html=True,
            )

        if _step3_done:
            st.markdown("")
            if st.button(f"🔄 {_t('Check again', 'Erneut prüfen')}", use_container_width=True):
                st.session_state.setdefault("audits", {}).pop(ready_url, None)
                st.session_state.get("contacts", {}).pop(ready_url, None)
                st.rerun()

# ── MODE B: Search Businesses ─────────────────────────────────────────────────
else:
    st.markdown(f"""
<div class="search-card">
  <div style="font-size:1.05rem;font-weight:700;color:#0D1526;margin-bottom:0.4rem;">
    🔍 {_t('Step 1 — Find Businesses', 'Schritt 1 — Unternehmen finden')}
  </div>
  <p style="margin-bottom:0;color:#4A5C78;font-size:0.92rem;">
    {_t(
      'Enter a type of business and a city below, then click <b>Find Businesses</b>. We will search the web and list their websites for you.',
      'Geben Sie unten eine Unternehmensart und eine Stadt ein, und klicken Sie auf <b>Unternehmen finden</b>. Wir durchsuchen das Web und listen deren Websites auf.'
    )}
  </p>
</div>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        industry = st.text_input(
            _t("Type of business", "Art des Unternehmens"),
            placeholder=_t("e.g. restaurants, dentists, gyms", "z.B. Restaurants, Zahnärzte, Fitnessstudios"),
        )
    with col2:
        area_query = st.text_input(
            _t("City or country", "Stadt oder Land"),
            value=st.session_state.get("area_picked", ""),
            placeholder=_t("e.g. Berlin, Germany, Dubai", "z.B. Berlin, Deutschland, Dubai"),
            key="area_query_input",
        )
        area = area_query
    with col3:
        max_results = st.number_input(_t("How many?", "Wie viele?"), 1, 50, 15)

    search_btn = st.button(
        f"🔍 {_t('Find Businesses', 'Unternehmen finden')}",
        type="primary",
        use_container_width=True,
    )

    if search_btn:
        if not industry or not area:
            st.warning(_t("Please fill in both fields — type of business and city/country.",
                          "Bitte füllen Sie beide Felder aus — Unternehmensart und Stadt/Land."))
        else:
            status = st.empty()
            with st.spinner(_t("Searching the web for matching businesses…",
                               "Suche im Web nach passenden Unternehmen…")):
                results, engines = multi_engine_search(industry, area, int(max_results))
            st.session_state["results"]            = results
            st.session_state["engines"]            = engines
            st.session_state["tech"]               = {}
            st.session_state["audits"]             = {}
            st.session_state["selected_for_audit"] = []
            st.session_state.pop("direct_url_ready", None)
            status.empty()

# ── STEP 2 (Search mode): Show Results + Tech Detection ──────────────────────
if "results" in st.session_state and not st.session_state["results"]:
    # Search ran but returned zero businesses
    engines = st.session_state.get("engines", [])
    engine_note = f" ({', '.join(engines)})" if engines and engines != ["None"] else ""
    st.markdown(
        f"""
<div style="
    background:#FFFFFF;border:1px solid #E0E8F4;border-radius:14px;
    padding:3rem 2.5rem;text-align:center;margin:1.5rem 0;
    box-shadow:0 2px 10px rgba(0,0,0,0.05);">
  <div style="width:56px;height:56px;background:#F0F2F8;border-radius:14px;
    display:flex;align-items:center;justify-content:center;font-size:26px;
    margin:0 auto 1.1rem auto;">🔍</div>
  <div style="font-size:1.1rem;font-weight:700;color:#0D1526;margin-bottom:0.5rem;">
    {_t("No businesses found", "Keine Unternehmen gefunden")}
  </div>
  <div style="font-size:0.88rem;color:#7A8BA8;max-width:400px;margin:0 auto 1.5rem auto;line-height:1.7;">
    {_t(
        f"We searched{engine_note} but couldn't find any matching business websites. "
        "Try a broader category, a larger city, or a different spelling.",
        f"Wir haben{engine_note} gesucht, aber keine passenden Unternehmenswebsites gefunden. "
        "Versuchen Sie eine allgemeinere Kategorie, eine größere Stadt oder eine andere Schreibweise."
    )}
  </div>
  <div style="display:flex;gap:0.6rem;justify-content:center;flex-wrap:wrap;font-size:0.82rem;">
    <span style="background:#EFF6FF;color:#2563EB;border:1px solid #BFDBFE;border-radius:6px;padding:3px 10px;font-weight:600;">💡 {_t("Try:", "Tipps:")}</span>
    <span style="background:#F8FAFC;color:#4A5C78;border:1px solid #E0E8F4;border-radius:6px;padding:3px 10px;">{_t('"restaurants"', '"Restaurants"')}</span>
    <span style="background:#F8FAFC;color:#4A5C78;border:1px solid #E0E8F4;border-radius:6px;padding:3px 10px;">{_t('"London"', '"London"')}</span>
    <span style="background:#F8FAFC;color:#4A5C78;border:1px solid #E0E8F4;border-radius:6px;padding:3px 10px;">{_t('"dentists"', '"Zahnärzte"')}</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

if "results" in st.session_state and st.session_state["results"]:
    results = st.session_state["results"]
    engines = st.session_state["engines"]

    st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
  background:#FFFFFF;border:1px solid #E0E8F4;border-radius:12px;
  padding:1rem 1.4rem;margin:1rem 0;box-shadow:0 2px 8px rgba(0,0,0,0.04);">
  <div style="display:flex;align-items:center;gap:12px;">
    <div style="width:40px;height:40px;background:linear-gradient(135deg,#EFF6FF,#DBEAFE);
      border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;">🏢</div>
    <div>
      <div style="font-size:1.25rem;font-weight:800;color:#0D1526;">{len(results)}</div>
      <div style="font-size:0.78rem;color:#7A8BA8;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;">{_t('Businesses found', 'Unternehmen gefunden')}</div>
    </div>
  </div>
      <div style="font-size:0.84rem;color:#4A5C78;font-weight:500;">
    {_t('✅ Step 2 — Tick the boxes next to the websites you want to check, then scroll down and click the blue button.', '✅ Schritt 2 — Setzen Sie Häkchen neben den Websites und klicken Sie unten auf die blaue Schaltfläche.')}
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Auto-detect tech stack for all results (no manual button) ──────────
    all_result_urls = [item.get("source_url", "") for item in results if item.get("source_url")]
    _tech_cache_key = "_tech_cache_urls"
    if st.session_state.get(_tech_cache_key) != all_result_urls:
        prog   = st.progress(0)
        status = st.empty()
        status.text(_t("Scanning websites…", "Websites werden gescannt…"))
        tech   = {}
        cdn_map = {}
        total = len(all_result_urls) or 1
        for i, url in enumerate(all_result_urls):
            status.text(f"{_t('Scanning', 'Scanne')} {url}…")
            tech[url]    = detect_tech(url)
            cdn_map[url] = detect_cdn(url)
            prog.progress((i + 1) / total)
        st.session_state["tech"]    = tech
        st.session_state["cdn_map"] = cdn_map
        st.session_state[_tech_cache_key] = all_result_urls
        status.empty(); prog.empty()

    tech    = st.session_state.get("tech", {})
    cdn_map = st.session_state.get("cdn_map", {})

    if "selected_for_audit" not in st.session_state:
        st.session_state["selected_for_audit"] = []

    all_urls = [item.get("source_url", "") for item in results if item.get("source_url")]
    if "_select_action" not in st.session_state:
        st.session_state["_select_action"] = None

    sel_col1, sel_col2, _ = st.columns([1, 1, 4])
    with sel_col1:
        if st.button(f"☑ {_t('Select All', 'Alle auswählen')}", use_container_width=True):
            st.session_state["selected_for_audit"] = list(all_urls)
            st.session_state["_select_action"] = "all"
            st.rerun()
    with sel_col2:
        if st.button(f"☐ {_t('Clear Selection', 'Auswahl aufheben')}", use_container_width=True):
            st.session_state["selected_for_audit"] = []
            st.session_state["_select_action"] = "none"
            st.rerun()

    selected = st.session_state["selected_for_audit"]

    for idx, item in enumerate(results):
        url  = item.get("source_url", "")
        name = item.get("business_name", url)
        snip = item.get("snippet", "")
        src  = item.get("source", "")
        t    = tech.get(url, {})
        cdn  = cdn_map.get(url, {})
        already_audited = url in st.session_state.get("audits", {})

        # ── Build card data ──────────────────────────────────────────────────
        _cdn_has   = cdn.get("has_cdn", False) if cdn else None
        _cdn_name  = cdn.get("cdn_name", "CDN") if cdn else ""
        _cms       = t.get("cms", "Unknown") if t else "Unknown"
        _plugins   = t.get("plugins", []) if t else []
        if _cms == "Unknown" and t:
            _cms, _ = _resolve_unknown_cms(t)

        # Status badges HTML
        _badge_parts = []
        if already_audited:
            _badge_parts.append(
                '<span style="background:#EFF6FF;color:#1D4ED8;padding:2px 9px;'
                'border-radius:5px;font-size:11px;font-weight:700;">✓ Audited</span>'
            )
        if cdn is not None:
            if _cdn_has:
                _badge_parts.append(
                    f'<span style="background:#ECFDF5;color:#065F46;padding:2px 9px;'
                    f'border-radius:5px;font-size:11px;font-weight:700;">✓ {_cdn_name}</span>'
                )
            else:
                _badge_parts.append(
                    '<span style="background:#FFF7ED;color:#C2410C;padding:2px 9px;'
                    'border-radius:5px;font-size:11px;font-weight:700;">🔥 Hot Lead</span>'
                )
        _contacted_info = st.session_state.get("contacted", {}).get(url)
        if _contacted_info:
            _badge_parts.append(
                f'<span style="background:#ECFDF5;color:#047857;padding:2px 9px;'
                f'border-radius:5px;font-size:11px;font-weight:700;">✅ Contacted</span>'
            )

        # Tech pills (CMS + top plugins, max 5)
        _tech_pills = ""
        if _cms and _cms not in ("Unknown", ""):
            _fg, _bg = _CMS_COLORS.get(_cms, ("#555", "#88888815"))
            _tech_pills += (
                f'<span style="background:{_bg};color:{_fg};border:1px solid {_fg}44;'
                f'padding:2px 9px;border-radius:5px;font-size:11px;font-weight:700;margin-right:4px;">'
                f'{_cms}</span>'
            )
        for _p in _plugins[:4]:
            _tech_pills += (
                f'<span style="background:#F5F3FF;color:#5B21B6;border:1px solid #DDD6FE;'
                f'padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;margin-right:4px;">'
                f'{_p}</span>'
            )

        # Opportunity badge if audited
        _opp_badge = ""
        if already_audited:
            _a = st.session_state.get("audits", {}).get(url, {})
            _cdn_i = st.session_state.get("cdn_map", {}).get(url, {})
            _opp = varnish_opportunity_score(_a, cdn_info=_cdn_i)
            _lbl, _ocol = opportunity_label(_opp)
            _spd = (_a.get("breakdown") or {}).get("speed", {}).get("score", "—")
            _opp_badge = (
                f'<span style="background:{_ocol}18;color:{_ocol};border:1px solid {_ocol}44;'
                f'padding:2px 10px;border-radius:5px;font-size:11px;font-weight:700;margin-right:4px;">'
                f'{_lbl} · {_opp}/100</span>'
                f'<span style="background:#F0F2F8;color:#4A5C78;'
                f'padding:2px 9px;border-radius:5px;font-size:11px;font-weight:600;">'
                f'Speed {_spd}/100</span>'
            )

        # Render the whole lead — title/badges/url/tech pills + checkbox +
        # Check button — inside ONE real st.container so it's a single
        # bordered box, with no seam between an HTML card and a separate
        # widget row.
        _domain_display = url.replace("https://", "").replace("http://", "").rstrip("/")
        _badges_html = " ".join(_badge_parts)
        _tech_row    = f'<div style="margin:6px 0 4px 0;line-height:2;">{_tech_pills}</div>' if _tech_pills else ""
        _opp_row     = f'<div style="margin-top:6px;line-height:2;">{_opp_badge}</div>'      if _opp_badge  else ""

        # ── Card layout: checkbox + title + badges (left) | Check btn (right top)
        # URL and detected stack below, indented to align under the name.
        action_suffix = st.session_state.get("_select_action", "")
        _card_key = f"leadcard_{idx}_{action_suffix}"

        st.markdown(f"""
<style>
div[class*="st-key-{_card_key}"] {{
    background:#FFFFFF !important;
    border:1px solid #E0E8F4 !important;
    border-radius:12px !important;
    box-shadow:0 2px 6px rgba(0,0,0,0.04) !important;
    padding:14px 18px 14px 18px !important;
    margin-bottom:10px !important;
}}
div[class*="st-key-{_card_key}"] [data-testid="stCheckbox"] {{
    margin-top:1px !important;
}}
</style>
""", unsafe_allow_html=True)

        with st.container(key=_card_key):
            # ── Top row: checkbox | name+badges (flex) | Check button ──────────
            hdr_chk, hdr_info, hdr_btn = st.columns([0.55, 6.5, 1.8])

            with hdr_chk:
                checked = st.checkbox(
                    f"Select {name}", value=(url in selected),
                    key=f"chk_{idx}_{action_suffix}", label_visibility="collapsed",
                )
                if checked and url not in selected:
                    selected.append(url)
                    st.session_state["selected_for_audit"] = selected
                    st.session_state["_select_action"] = None
                elif not checked and url in selected:
                    selected.remove(url)
                    st.session_state["selected_for_audit"] = selected
                    st.session_state["_select_action"] = None

            with hdr_info:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:7px;flex-wrap:wrap;min-height:28px;">'
                    f'<span style="font-size:0.95rem;font-weight:700;color:#0D1526;">{name}</span>'
                    f'{_badges_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            with hdr_btn:
                if AUDIT_AVAILABLE:
                    if already_audited:
                        st.button(
                            f"✓ {_t('Checked', 'Geprüft')}",
                            key=f"audit_{idx}",
                            use_container_width=True,
                            disabled=True,
                        )
                        if st.button(
                            f"↺ {_t('Re-check', 'Erneut')}",
                            key=f"reaudit_{idx}",
                            use_container_width=True,
                        ):
                            st.session_state["audits"].pop(url, None)
                            with st.spinner(f"{_t('Re-checking', 'Erneut prüfe')} {url}…"):
                                result = audit_website(url)
                            st.session_state["audits"][url] = result
                            st.rerun()
                    else:
                        if st.button(
                            f"🚀 {_t('Check', 'Prüfen')}",
                            key=f"audit_{idx}",
                            use_container_width=True,
                        ):
                            if url not in st.session_state.get("audits", {}):
                                with st.spinner(f"{_t('Checking', 'Prüfe')} {url}…"):
                                    result = audit_website(url)
                                st.session_state["audits"][url] = result
                                if CONTACT_AVAILABLE and url not in st.session_state.get("contacts", {}):
                                    with st.spinner(_t("Auto-extracting contact info…", "Kontaktdaten werden automatisch extrahiert…")):
                                        st.session_state.setdefault("contacts", {})[url] = extract_contact_info(url)
                            st.rerun()

            # ── URL row (indented ~26px to clear checkbox column) ────────────
            st.markdown(
                f'<div style="margin:3px 0 7px 0;font-size:0.8rem;">'
                f'<a href="{url}" target="_blank" style="color:#2563EB;text-decoration:none;">'
                f'{_domain_display}</a></div>',
                unsafe_allow_html=True,
            )

            # ── Tech stack pills ─────────────────────────────────────────────
            if _tech_pills:
                st.markdown(
                    f'<div style="margin-bottom:6px;line-height:2;">{_tech_pills}</div>',
                    unsafe_allow_html=True,
                )

            # ── Opportunity badge row (if audited) ───────────────────────────
            if _opp_badge:
                st.markdown(
                    f'<div style="margin-top:4px;line-height:2;">{_opp_badge}</div>',
                    unsafe_allow_html=True,
                )

    # ── Bulk Audit ────────────────────────────────────────────────────────────
    st.markdown(f"""
<div class="section-divider">
  <div class="section-divider-line"></div>
  <div class="section-divider-label">🚀 {_t('Step 3 — Run Speed Checks', 'Schritt 3 — Geschwindigkeit prüfen')}</div>
  <div class="section-divider-line"></div>
</div>
""", unsafe_allow_html=True)
    n_selected = len(selected)

    if n_selected == 0:
        st.info(_t(
            "☝ Tick the boxes next to the businesses above, then click the button below to check them all at once.",
            "☝ Setzen Sie oben Häkchen bei den Unternehmen und klicken Sie dann unten auf die Schaltfläche.",
        ))
    else:
        site_word = _t("website", "Website") if n_selected == 1 else _t("websites", "Websites")
        st.success(f"**{n_selected}** {site_word} {_t('selected — ready to check!', 'ausgewählt — bereit zur Prüfung!')}")

    audit_selected_btn = st.button(
        f"🚀 {_t('Check', 'Prüfe')} {n_selected} {_t('website', 'Website') if n_selected == 1 else _t('websites', 'Websites')}",
        type="primary",
        use_container_width=True,
        disabled=(n_selected == 0),
    )

    if audit_selected_btn and n_selected > 0:
        prog   = st.progress(0, text=_t("Starting…", "Wird gestartet…"))
        status = st.empty()
        batch  = [url for url in selected if url]
        _auto_contact_count = 0
        for i, url in enumerate(batch):
            status.info(f"🔍 {_t('Checking', 'Prüfe')} **{i+1}/{len(batch)}**: {url}")
            # Skip URLs already cached in this session to avoid score variance
            if url not in st.session_state.get("audits", {}):
                with st.spinner(f"{_t('Working on', 'Bearbeite')} {url}…"):
                    result = audit_website(url)
                st.session_state["audits"][url] = result
            else:
                result = st.session_state["audits"][url]
            # Always auto-extract contacts for every audited site in the bulk run
            if CONTACT_AVAILABLE and url not in st.session_state.get("contacts", {}):
                status.info(f"📧 {_t('Extracting contacts for', 'Kontakte werden abgerufen für')} {url}…")
                st.session_state.setdefault("contacts", {})[url] = extract_contact_info(url)
                _auto_contact_count += 1
            prog.progress(
                (i + 1) / len(batch),
                text=f"{_t('Done', 'Fertig')}: {i+1} / {len(batch)}",
            )
        status.empty(); prog.empty()
        sites_done = len(batch)
        site_word  = _t("website", "Website") if sites_done == 1 else _t("websites", "Websites")
        st.success(f"✅ {_t('All done!', 'Alles fertig!')} {sites_done} {site_word} {_t('checked.', 'geprüft.')}")
        if _auto_contact_count:
            st.info(f"📧 {_t('Auto-extracted contact info for', 'Kontakte automatisch extrahiert für')} {_auto_contact_count} {_t('sites.', 'Seiten.')}")
        st.rerun()

# ── STEP 4: Audit Results ────────────────────────────────────────────────────
audits = st.session_state.get("audits", {})
_direct_mode_results = audits and "results" not in st.session_state

if audits:
    st.markdown(f"""
<div class="section-divider" style="margin-top:2rem;">
  <div class="section-divider-line"></div>
  <div class="section-divider-label">📊 {_t('Audit Results', 'Prüfergebnisse')}</div>
  <div class="section-divider-line"></div>
</div>
""", unsafe_allow_html=True)
    audit_list = list(audits.values())

    # Fix 6: Show a notice when contacts were auto-extracted after a high-opp audit
    _auto_extracted_url = st.session_state.pop("_contact_auto_extracted", None)
    if _auto_extracted_url:
        _ae_contact = st.session_state.get("contacts", {}).get(_auto_extracted_url, {})
        _ae_email   = _ae_contact.get("primary_email")
        if _ae_email:
            st.success(
                f"📧 {_t('Contact info auto-extracted for this high-opportunity site', 'Kontaktdaten automatisch extrahiert für diese hochopprtune Website')} "
                f"— **{_ae_email}**"
            )
        else:
            st.info(
                f"📧 {_t('Contact extraction ran automatically (high opportunity score) — no email found on this site.', 'Kontaktextraktion automatisch ausgeführt — keine E-Mail gefunden.')}"
            )

    # ── Session Persistence ───────────────────────────────────────────────────
    st.markdown(
        f'<div style="background:#EFF6FF;border:1.5px solid #BFD7FF;border-radius:10px;'
        f'padding:10px 16px;margin:4px 0 8px 0;font-size:0.85rem;color:#1E3A8A;">'
        f'💾 <b>{_t("Don\'t lose your list", "Verlieren Sie Ihre Liste nicht")}</b> — '
        f'{_t("Doing high-volume prospecting? Save your session below so you can pick up exactly where you left off — audits, contacts, and CDN data included.", "Hochvolumiges Prospecting? Speichern Sie unten Ihre Sitzung, um genau dort weiterzumachen — inklusive Prüfungen, Kontakten und CDN-Daten.")}'
        f'</div>',
        unsafe_allow_html=True,
    )
    with st.expander(f"💾 {_t('Save / Restore session', 'Sitzung speichern / wiederherstellen')}",
                      expanded=len(audits) >= 1):
        persist_col1, persist_col2 = st.columns(2)

        with persist_col1:
            st.markdown(f"**{_t('Save current session', 'Aktuelle Sitzung speichern')}**")
            st.caption(_t(
                "Downloads all audit results, contacts, contacted status, and CDN data as a JSON file you can reload later.",
                "Lädt alle Prüfergebnisse, Kontakte, Kontaktstatus und CDN-Daten als JSON-Datei herunter.",
            ))
            session_snapshot = {
                "audits":    {k: v for k, v in audits.items()},
                "contacts":  st.session_state.get("contacts", {}),
                "cdn_map":   st.session_state.get("cdn_map", {}),
                "results":   st.session_state.get("results", []),
                "engines":   st.session_state.get("engines", []),
                "contacted": st.session_state.get("contacted", {}),
            }
            st.download_button(
                label=f"⬇ {_t('Download session (.json)', 'Sitzung herunterladen (.json)')}",
                data=json.dumps(session_snapshot, indent=2, default=str).encode("utf-8"),
                file_name="fastsite_session.json",
                mime="application/json",
                use_container_width=True,
                key="session_save",
            )

        with persist_col2:
            st.markdown(f"**{_t('Restore a saved session', 'Gespeicherte Sitzung wiederherstellen')}**")
            st.caption(_t(
                "Upload a previously saved JSON file to continue where you left off.",
                "Laden Sie eine früher gespeicherte JSON-Datei hoch, um dort weiterzumachen.",
            ))
            uploaded_session = st.file_uploader(
                _t("Upload session file", "Sitzungsdatei hochladen"),
                type=["json"],
                label_visibility="collapsed",
                key="session_upload",
            )
            if uploaded_session is not None:
                try:
                    loaded = json.loads(uploaded_session.read())
                    if st.button(
                        f"✅ {_t('Restore this session', 'Diese Sitzung wiederherstellen')}",
                        type="primary",
                        use_container_width=True,
                        key="session_restore_btn",
                    ):
                        st.session_state["audits"]    = loaded.get("audits", {})
                        st.session_state["contacts"]  = loaded.get("contacts", {})
                        st.session_state["cdn_map"]   = loaded.get("cdn_map", {})
                        st.session_state["contacted"] = loaded.get("contacted", {})
                        if loaded.get("results"):
                            st.session_state["results"] = loaded["results"]
                        if loaded.get("engines"):
                            st.session_state["engines"] = loaded["engines"]
                        st.success(_t(
                            f"✅ Session restored — {len(loaded.get('audits', {}))} audits loaded.",
                            f"✅ Sitzung wiederhergestellt — {len(loaded.get('audits', {}))} Prüfungen geladen.",
                        ))
                        st.rerun()
                except Exception as exc:
                    st.error(_t(f"Could not load session file: {exc}", f"Sitzungsdatei konnte nicht geladen werden: {exc}"))
    # ─────────────────────────────────────────────────────────────────────────

    if not _direct_mode_results:
        successful = [a for a in audit_list if not a.get("error")]
        scores     = [a.get("overall_score", 0) for a in successful]
        _cdn_map_bulk = st.session_state.get("cdn_map", {})
        opps       = [varnish_opportunity_score(a, cdn_info=_cdn_map_bulk.get(a.get("url",""), {})) for a in successful]

        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1: st.metric(_t("Sites Checked", "Geprüfte Seiten"), len(successful))
        with mc2: st.metric(_t("Avg Score", "Ø Score"), f"{int(sum(scores)/len(scores)) if scores else 0}/100")
        with mc3: st.metric(_t("Hot Leads", "Heiße Leads"), sum(1 for o in opps if o >= 65))
        with mc4: st.metric(_t("Avg Opportunity", "Ø Chance"), f"{int(sum(opps)/len(opps)) if opps else 0}/100")

        # ── Quick CSV export shortcut (Fix 5) ────────────────────────────────
        _cdn_map_quick = st.session_state.get("cdn_map", {})
        _contacts_quick = st.session_state.get("contacts", {})
        _csv_quick = build_leads_csv(
            audit_results=[a for a in audit_list if not a.get("error")],
            contact_data=_contacts_quick,
            cdn_data=_cdn_map_quick,
        )
        _csv_quick = _add_contacted_column(_csv_quick, st.session_state.get("contacted", {}))
        _n_exportable = len([a for a in audit_list if not a.get("error")])
        st.markdown(
            f'<div style="background:#EFF6FF;border:1.5px solid #BFDBFE;border-radius:10px;'
            f'padding:12px 16px;display:flex;align-items:center;gap:12px;margin-bottom:12px;">'
            f'<span style="font-size:1.3rem;">📥</span>'
            f'<div style="flex:1;">'
            f'<span style="font-weight:700;color:#1D4ED8;font-size:0.93rem;">'
            f'{_t("Export your leads", "Leads exportieren")}</span>'
            f'<span style="color:#6B7A99;font-size:0.82rem;margin-left:8px;">'
            f'— {_n_exportable} {_t("sites ready to download", "Seiten bereit zum Download")}'
            f'</span></div></div>',
            unsafe_allow_html=True,
        )
        st.download_button(
            label=f"⬇ {_t('Download leads CSV', 'Leads-CSV herunterladen')} ({_n_exportable} {_t('sites', 'Seiten')})",
            data=_csv_quick,
            file_name="fastsite_leads.csv",
            mime="text/csv",
            use_container_width=True,
            key="csv_export_top",
            type="primary",
        )
        st.markdown("")

        col_filter1, col_filter2, col_filter3 = st.columns([2, 1, 1])
        with col_filter1:
            hot_lead_only = st.checkbox(_t("Show only high-opportunity sites", "Nur hochopportune Seiten anzeigen"))
        with col_filter2:
            opp_threshold = st.slider(
                _t("Min opportunity score", "Min. Opportunity Score"),
                min_value=10, max_value=90, value=40, step=5,
                disabled=not hot_lead_only,
                help=_t(
                    "Good performance and speed = cold lead (low score). "
                    "Poor performance and speed = hot lead (high score) — the best Varnish prospects. "
                    "Lower threshold = more sites shown; raise it to focus on the weakest performers.",
                    "Gute Performance und Geschwindigkeit = kalter Lead (niedriger Score). "
                    "Schlechte Performance und Geschwindigkeit = heißer Lead (hoher Score) — die besten Varnish-Interessenten.",
                ),
            )
        with col_filter3:
            cdn_map_for_filter = st.session_state.get("cdn_map", {})
            cdn_filter_available = bool(cdn_map_for_filter)
            no_cdn_only = st.checkbox(
                _t("🔥 No CDN only", "🔥 Nur ohne CDN"),
                help=_t(
                    "Show only sites with no CDN/cache detected — the hottest leads for Varnish.",
                    "Nur Seiten ohne erkanntes CDN/Cache anzeigen — die heißesten Leads für Varnish.",
                ),
                disabled=not cdn_filter_available,
            )
            if not cdn_filter_available:
                st.caption(_t("Run platform detection first", "Erst Plattformerkennung ausführen"))

        filtered = audit_list
        if hot_lead_only:
            filtered = [
                a for a in filtered
                if (not a.get("error") and varnish_opportunity_score(a, cdn_info=cdn_map_for_filter.get(a.get("url",""), {})) >= opp_threshold)
            ]
        if no_cdn_only:
            filtered = [
                a for a in filtered
                if not a.get("error") and not cdn_map_for_filter.get(a.get("url", ""), {}).get("has_cdn")
            ]
    else:
        filtered = audit_list

    # ── Contact extraction state ──────────────────────────────────────────────
    if "contacts" not in st.session_state:
        st.session_state["contacts"] = {}
    contacts = st.session_state["contacts"]

    # ── Bulk contact extraction button ────────────────────────────────────────
    if CONTACT_AVAILABLE:
        # Count from all audited sites (audit_list), not just the filtered view,
        # so the number matches what is shown in the Audit Results header.
        pending_contact = [
            a.get("url", "") for a in audit_list
            if not a.get("error") and a.get("url", "") not in contacts
        ]
        if pending_contact:
            # Contacts are normally auto-extracted right after each audit, but
            # this catches any leftovers (e.g. audits cached from an earlier
            # session) so the email step is never blocked on a manual click.
            with st.spinner(_t("Auto-extracting contact info…", "Kontaktdaten werden automatisch extrahiert…")):
                for url_c in pending_contact:
                    contacts[url_c] = extract_contact_info(url_c)
                st.session_state["contacts"] = contacts

    # ── Individual audit cards ────────────────────────────────────────────────
    for a in filtered:
        url   = a.get("url", "")
        score = a.get("overall_score", 0)
        bd    = a.get("breakdown", {})
        fetch_err = a.get("error", "")
        opp   = varnish_opportunity_score(a, cdn_info=st.session_state.get("cdn_map", {}).get(url, {})) if not fetch_err else 0
        opp_lbl, opp_col = opportunity_label(opp)

        expander_title = (
            f"⚠️ {url}  — Could not reach site"
            if fetch_err else
            f"{'🟢' if score >= 70 else '🟡' if score >= 50 else '🔴'} "
            f"{url}  —  {score}/100  ·  {opp_lbl} ({opp}/100)"
        )

        with st.expander(expander_title, expanded=_direct_mode_results):
            if fetch_err:
                st.error(
                    f"❌ **Could not audit this site.**\n\n"
                    f"{fetch_err}\n\n"
                    f"Please verify the URL is correct and the site is publicly accessible, then try again."
                )
                continue

            # ── Feature 6: Varnish Opportunity Score banner ───────────────────
            _spd_raw  = (bd.get("speed") or {}).get("score", "—")
            _perf_raw = (bd.get("performance") or {}).get("score", "—")
            _rank_raw = (bd.get("page_ranking") or {}).get("score", "—")
            _safe_score = lambda v: v if not isinstance(v, dict) else "—"
            _spd_val  = _safe_score(_spd_raw)
            _perf_val = _safe_score(_perf_raw)
            _rank_val = _safe_score(_rank_raw)
            _cdn_detected = st.session_state.get("cdn_map", {}).get(url, {}).get("has_cdn")

            # Build a readable formula string showing the actual weighted inputs
            _formula_parts = []
            if _spd_val != "—":
                _formula_parts.append(f"Speed {_spd_val} × 55%")
            if _perf_val != "—":
                _formula_parts.append(f"Performance {_perf_val} × 35%")
            if _rank_val != "—":
                _formula_parts.append(f"Ranking {_rank_val} × 10%")
            _cdn_bonus_str = " + 15 no-CDN bonus" if not _cdn_detected else ""
            _formula_str = " + ".join(_formula_parts) + _cdn_bonus_str if _formula_parts else ""
            _legend_tooltip = _t(
                "Good performance and speed = cold lead (site is already fast, lower priority). "
                "Poor performance and speed = hot lead (site is slow, great opportunity for Varnish cache). "
                "A bonus is added if no CDN is detected.",
                "Gute Performance und Geschwindigkeit = kalter Lead (Seite ist bereits schnell, geringere Priorität). "
                "Schlechte Performance und Geschwindigkeit = heißer Lead (Seite ist langsam, gute Chance für Varnish Cache). "
                "Bonus, wenn kein CDN erkannt wird.",
            )
            _formula_note = (
                f'<div title="{_legend_tooltip}" style="font-size:10.5px;color:#9AA5BC;margin-top:5px;'
                f'background:#00000008;border-radius:4px;padding:3px 7px;display:inline-block;cursor:help;">'
                f'{_t("Good performance &amp; speed = cold lead &nbsp;·&nbsp; Poor performance &amp; speed = hot lead", "Gute Performance &amp; Speed = kalter Lead &nbsp;·&nbsp; Schlechte Performance &amp; Speed = heißer Lead")} &nbsp;ⓘ</div>'
            )

            st.markdown(
                f'<div style="background:{opp_col}15;border:1.5px solid {opp_col}44;'
                f'border-radius:10px;padding:14px 18px;margin-bottom:14px;">'
                f'<div style="display:flex;align-items:center;gap:16px;">'
                f'<div style="text-align:center;min-width:70px;">'
                f'<div style="font-size:2rem;font-weight:800;color:{opp_col};">{opp}</div>'
                f'<div style="font-size:10px;font-weight:700;color:{opp_col};text-transform:uppercase;'
                f'letter-spacing:.05em;">OPPORTUNITY</div></div>'
                f'<div style="flex:1;">'
                f'<div style="font-size:13px;font-weight:700;color:{opp_col};">{opp_lbl}</div>'
                f'<div style="font-size:11px;color:#6B7A99;margin-top:2px;">'
                f'Speed score: <b>{_spd_val}/100</b> &nbsp;·&nbsp; '
                f'Performance: <b>{_perf_val}/100</b>'
                f'{"&nbsp;·&nbsp;<b>🔥 No delivery network — great opportunity</b>" if not _cdn_detected else ""}'
                f'</div>'
                f'<div style="font-size:11px;color:#9AA5BC;margin-top:3px;">'
                f'{"This site loads slowly — a strong candidate for speed improvement." if opp >= 50 else "This site already has decent performance — lower priority."}'
                f'</div>'
                f'</div></div></div>',
                unsafe_allow_html=True,
            )

            # ── Feature 1: Speed / caching context callout ────────────────────
            spd_score = (bd.get("speed") or {}).get("score", 50)
            prf_score = (bd.get("performance") or {}).get("score", 50)
            proj      = a.get("fastsite_projection") or {}
            cur       = proj.get("current", {})
            prj_d     = proj.get("projected", {})
            if spd_score < 60 or prf_score < 60:
                ttfb_now  = cur.get("ttfb_ms")
                ttfb_proj = prj_d.get("ttfb_ms")
                ps_min    = prj_d.get("perf_score_min")
                ps_max    = prj_d.get("perf_score_max")
                ttfb_line = (
                    f"Server response time is **{ttfb_now}ms** — ideal is under 200ms. "
                    f"Varnish Edge Cache would bring this to **~{ttfb_proj}ms**."
                    if ttfb_now and ttfb_proj
                    else ""
                )
                ps_line = (
                    f"PageSpeed score could jump from **{prf_score}** to **{ps_min}–{ps_max}/100**."
                    if ps_min else ""
                )
                st.info(
                    f"⚡ **This site has a speed problem.**  "
                    f"Slow-loading websites lose visitors and rank lower on Google.  "
                    f"{ttfb_line}  {ps_line}  "
                    f"Speed improvements could reduce load times by 3–10× with no code changes required."
                )

            # ── Score breakdown ───────────────────────────────────────────────
            st.markdown(
                f'<div style="height:10px;background:#E5EAF3;border-radius:99px;margin-bottom:6px;overflow:hidden;">'
                f'<div style="height:10px;width:{score}%;background:{_score_color(score)};border-radius:99px;transition:width 0.6s ease;"></div>'
                f'</div>', unsafe_allow_html=True
            )
            st.caption(_t(
                "ℹ️ Website's Scores may vary slightly between different runs.",
                "ℹ️ Scores können je nach Messung leicht schwanken.",
            ))

            if bd:
                cols = st.columns(len(bd))
                for col, (cat, data) in zip(cols, bd.items()):
                    s = data.get("score", 0)
                    # Highlight Speed and Performance specially
                    highlight = cat in ("speed", "performance")
                    border_col = "#2563EB" if highlight else "#E5EAF3"
                    col.markdown(
                        f'<div style="text-align:center;background:#F7F8FA;border:{"2px" if highlight else "1px"} solid {border_col};'
                        f'border-radius:10px;padding:0.85rem 0.5rem;">'
                        f'<div style="font-size:1.6rem;font-weight:700;color:{_score_color(s)};line-height:1;">{s}</div>'
                        f'<div style="font-size:10px;color:{"#2563EB" if highlight else "#6B7A99"};font-weight:{"700" if highlight else "600"};letter-spacing:0.07em;'
                        f'text-transform:uppercase;margin-top:4px;">{cat}</div></div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("")

            # ── Feature 2: Contact info ───────────────────────────────────────
            contact = contacts.get(url, {})
            if contact:
                st.markdown(f"**📧 {_t('Contact Info', 'Kontaktdaten')}**")
                c1, c2, c3 = st.columns(3)
                with c1:
                    em = contact.get("primary_email")
                    st.markdown(f"**Email:** `{em}`" if em else "**Email:** —")
                with c2:
                    ph = contact.get("phones", [])
                    st.markdown(f"**Phone:** `{ph[0]}`" if ph else "**Phone:** —")
                with c3:
                    cp = contact.get("contact_page")
                    if cp:
                        st.markdown(f"**Contact page:** [{cp}]({cp})")
                    else:
                        st.markdown("**Contact page:** —")
            elif CONTACT_AVAILABLE:
                # Fallback: should rarely fire since contacts are auto-extracted
                # right after the audit, but covers any edge cases automatically.
                with st.spinner(_t("Auto-extracting contact info…", "Kontaktdaten werden automatisch extrahiert…")):
                    contacts[url] = extract_contact_info(url)
                    st.session_state["contacts"] = contacts
                contact = contacts[url]

            # ── Feature 5: Cold email generator ───────────────────────────────
            contact = contacts.get(url, {})  # refresh after possible extraction
            with st.expander(f"✉️ {_t('Generate cold email for this site', 'Kalt-E-Mail generieren')}"):
                import re as _re
                m = _re.search(r"https?://(?:www\.)?([^/]+)", url)
                biz_name = m.group(1) if m else url
                cdn_info = st.session_state.get("cdn_map", {}).get(url, {})
                email_text = generate_cold_email(
                    business_name=biz_name,
                    url=url,
                    overall_score=score,
                    speed_score=spd_score,
                    performance_score=prf_score,
                    opportunity_score=opp,
                    primary_email=contact.get("primary_email"),
                    ttfb_ms=cur.get("ttfb_ms"),
                    lcp_ms=cur.get("lcp_ms"),
                    has_cdn=cdn_info.get("has_cdn", False),
                )
                _sender_name = st.session_state.get("rep_name", "").strip()
                if _sender_name:
                    for _ph in ("[Your name]", "[your name]", "[YOUR NAME]", "[Your Name]"):
                        email_text = email_text.replace(_ph, _sender_name)
                edited_email = st.text_area(
                    _t("Edit before sending (optional)", "Vor dem Senden bearbeiten (optional)"),
                    value=email_text,
                    height=300,
                    key=f"email_{url}",
                )
                # JS copy button — works inside expanders where st.code's
                # native copy icon is hidden by Streamlit's CSS.
                import streamlit.components.v1 as _components
                _safe_email = edited_email.replace("`", "\\`").replace("\\", "\\\\").replace("$", "\\$")
                _components.html(f"""
<button onclick="navigator.clipboard.writeText(`{_safe_email}`).then(()=>{{
    this.textContent='✅ Copied!';
    setTimeout(()=>{{this.textContent='📋 Copy email'}},2000);
}})" style="
    background:#2563EB;color:#fff;border:none;border-radius:8px;
    padding:8px 18px;font-size:14px;font-weight:600;cursor:pointer;
    font-family:Inter,sans-serif;letter-spacing:0.01em;">
  📋 Copy email
</button>
""", height=50)

                # ── Follow-up tracking ────────────────────────────────────────
                st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
                _contacted_map = st.session_state.setdefault("contacted", {})
                _is_contacted  = url in _contacted_map
                mark_col, status_col = st.columns([2, 3])
                with mark_col:
                    _new_contacted = st.checkbox(
                        f"✅ {_t('Mark as contacted', 'Als kontaktiert markieren')}",
                        value=_is_contacted,
                        key=f"contacted_{url}",
                    )
                with status_col:
                    if _is_contacted:
                        st.caption(
                            f"{_t('Marked contacted on', 'Kontaktiert markiert am')} "
                            f"{_contacted_map[url].get('at','')} "
                            f"{_t('by', 'von')} {_contacted_map[url].get('by','—')}"
                        )
                    else:
                        st.caption(_t(
                            "Tick this once you've sent the email (copy/paste or your own mail client) "
                            "to avoid duplicate outreach later.",
                            "Markieren Sie dies, sobald die E-Mail gesendet wurde, um doppelte Kontaktaufnahmen zu vermeiden.",
                        ))
                if _new_contacted and not _is_contacted:
                    _contacted_map[url] = {
                        "at": time.strftime("%Y-%m-%d %H:%M"),
                        "by": st.session_state.get("rep_name", ""),
                    }
                    st.session_state["contacted"] = _contacted_map
                    st.rerun()
                elif not _new_contacted and _is_contacted:
                    _contacted_map.pop(url, None)
                    st.session_state["contacted"] = _contacted_map
                    st.rerun()

                # ── Send via SMTP ────────────────────────────────────────────
                st.markdown("<div style='margin-top:14px;'></div>", unsafe_allow_html=True)

                smtp_configured = bool(
                    _get_secret("SMTP_USER") and _get_secret("SMTP_PASSWORD")
                )

                if not smtp_configured:
                    st.info("📬 To enable one-click sending, add `SMTP_USER` and `SMTP_PASSWORD` to `.streamlit/secrets.toml` and restart the app.")

                else:
                    recipient = contact.get("primary_email", "")
                    if recipient:
                        col_send, col_status = st.columns([2, 3])
                        with col_send:
                            if st.button(f"📨 Send to {recipient}", key=f"send_{url}", type="primary"):
                                lines = email_text.strip().splitlines()
                                subject_line = lines[0].replace("Subject: ", "").strip() if lines else "Site audit"
                                body = "\n".join(lines[2:]).strip()
                                ok, msg = send_email_smtp(recipient, subject_line, body)
                                if ok:
                                    st.success(f"✅ Email sent to {recipient}")
                                    st.session_state.setdefault("contacted", {})[url] = {
                                        "at": time.strftime("%Y-%m-%d %H:%M"),
                                        "by": st.session_state.get("rep_name", ""),
                                    }
                                    st.rerun()
                                else:
                                    st.error(f"❌ {msg}")
                    else:
                        st.caption(_t("No email address found for this site — extract contact info first to enable sending.", "Keine E-Mail-Adresse gefunden — zuerst Kontaktdaten extrahieren."))

            # ── Preview Measurement API ───────────────────────────────────────
            _preview_key = get_preview_api_key() if PREVIEW_API_AVAILABLE else None
            if PREVIEW_API_AVAILABLE and _preview_key:
                _safe_url_key = url.replace("https://", "").replace("http://", "").replace("/", "_").strip("_")
                _preview_session_key = f"preview_result_{_safe_url_key}"
                _cached_preview = st.session_state.get(_preview_session_key)

                st.markdown(
                    f'<div class="section-divider" style="margin-top:1.2rem;">'
                    f'<div class="section-divider-line"></div>'
                    f'<div class="section-divider-label">⚡ {_t("Live fast.site Preview & Speed Measurement", "Live fast.site Vorschau & Geschwindigkeitsmessung")}</div>'
                    f'<div class="section-divider-line"></div></div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"""<div style="font-size:0.88rem;color:#6B7A99;margin-bottom:12px;">
{_t('One more click', 'Noch ein Klick')} — {_t('provision a branded fast.site edge preview of', 'erstellen Sie eine fast.site-Vorschau für')} <b>{url}</b> {_t('and compare', 'und vergleichen Sie')}
<b>{_t('real measured', 'echte gemessene')}</b> TTFB/TTLB {_t('timings and PageSpeed scores — before vs after Varnish Edge Cache.', 'Zeiten und PageSpeed-Scores — vorher/nachher mit Varnish Edge Cache.')}
</div>""",
                    unsafe_allow_html=True,
                )

                _run_preview_btn = st.button(
                    f"🚀 {_t('Run live preview measurement', 'Live-Vorschaumessung starten')}",
                    key=f"preview_run_{_safe_url_key}",
                    type="primary",
                    use_container_width=True,
                    help=_t(
                        "Provisions a real fast.site edge preview and measures origin vs preview "
                        "TTFB/LCP/PageSpeed improvements. Takes ~30–90 seconds.",
                        "Erstellt eine echte fast.site-Vorschau und misst Verbesserungen. Dauert ~30–90 Sekunden.",
                    ),
                )

                if _run_preview_btn:
                    _status_placeholder = st.empty()
                    def _progress(msg: str):
                        _status_placeholder.info(msg)

                    with st.spinner(_t(
                        "Provisioning edge preview and measuring performance…",
                        "Edge-Vorschau wird bereitgestellt und gemessen…"
                    )):
                        _result = run_preview_measurement(
                            url=url,
                            api_key=_preview_key,
                            progress_callback=_progress,
                        )
                    _status_placeholder.empty()
                    st.session_state[_preview_session_key] = _result
                    st.rerun()

                if _cached_preview is not None:
                    render_preview_results(_cached_preview)

                    # ── Enrich fastsite_projection with real API data ──────
                    # When real measured data is available, surface it clearly
                    # alongside (or instead of) the static Varnish estimates.
                    if _cached_preview.ok and not _cached_preview.inconclusive:
                        _real_ttfb_imp = _cached_preview.ttfb_improvement_pct
                        _real_score_gain = _cached_preview.score_improvement
                        _prev_url = _cached_preview.preview_url
                        _ps_origin = _cached_preview.perf_score_origin
                        _ps_preview = _cached_preview.perf_score_preview
                        st.success(
                            f"✅ **{_t('Real measurement complete', 'Echte Messung abgeschlossen')}** — "
                            f"TTFB {_t('improved by', 'verbessert um')} **{_real_ttfb_imp}%**, "
                            f"PageSpeed **{_ps_origin} → {_ps_preview}** "
                            f"(+{_real_score_gain} {_t('pts', 'Punkte')}). "
                            f"[{_t('View live preview', 'Live-Vorschau ansehen')}]({_prev_url})"
                        )
                else:
                    st.caption(_t(
                        "Click the button above to provision a live edge preview and run the measurement.",
                        "Klicken Sie oben, um eine Live-Vorschau bereitzustellen und die Messung zu starten.",
                    ))

            elif PREVIEW_API_AVAILABLE and not _preview_key:
                pass  # Preview feature not configured — silently skip

            st.markdown("---")
            try:
                pdf_bytes = generate_audit_pdf(a, lang=_LANG)
                safe      = url.replace("https://", "").replace("http://", "").replace("/", "_").strip("_")
                st.download_button(
                    f"⬇ {_t('Download Audit Report (PDF)', 'Prüfbericht herunterladen (PDF)')}",
                    data=pdf_bytes,
                    file_name=f"audit_{safe}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"dl_{url}",
                )
            except Exception as e:
                st.warning(f"{_t('PDF generation failed', 'PDF-Erstellung fehlgeschlagen')}: {e}")

    # ── Export section ────────────────────────────────────────────────────────
    st.markdown(f"""
<div class="section-divider" style="margin-top:1.5rem;">
  <div class="section-divider-line"></div>
  <div class="section-divider-label">⬇ {_t('Export Lead Data', 'Lead-Daten exportieren')}</div>
  <div class="section-divider-line"></div>
</div>
""", unsafe_allow_html=True)
    exp_col1, exp_col2 = st.columns(2)

    # Feature 4: CSV export
    with exp_col1:
        cdn_map_data = st.session_state.get("cdn_map", {})
        csv_bytes = build_leads_csv(
            audit_results=[a for a in filtered if not a.get("error")],
            contact_data=contacts,
            cdn_data=cdn_map_data,
        )
        csv_bytes = _add_contacted_column(csv_bytes, st.session_state.get("contacted", {}))
        st.download_button(
            f"⬇ {_t('Export Leads as CSV', 'Leads als CSV exportieren')} ({len([a for a in filtered if not a.get('error')])} {_t('sites', 'Seiten')})",
            data=csv_bytes,
            file_name="fastsite_leads.csv",
            mime="text/csv",
            use_container_width=True,
            key="csv_export",
        )
        st.caption(_t(
            "Includes all audited sites with scores, contact details, and CDN status.",
            "Enthält alle geprüften Seiten mit Scores, Kontaktdaten und CDN-Status."
        ))

    # Bulk PDF
    with exp_col2:
        writer = PdfWriter()
        for a in filtered:
            if a.get("error"):
                continue
            try:
                pdf_bytes = generate_audit_pdf(a, lang=_LANG)
                writer.append(io.BytesIO(pdf_bytes))
            except Exception:
                pass
        if writer.pages:
            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            st.download_button(
                f"⬇ {_t('Download All Reports (PDF)', 'Alle Berichte herunterladen (PDF)')}",
                data=buf.read(),
                file_name=_t("fastsite_leads_reports.pdf", "fastsite_leads_berichte.pdf"),
                mime="application/pdf",
                use_container_width=True,
                key="pdf_bulk",
            )
        else:
            st.info(_t("Run audits first to generate PDF reports.",
                       "Führen Sie zuerst Prüfungen durch, um PDF-Berichte zu erstellen."))

# ─────────────────────────────────────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="app-footer">
  <span style="font-weight:700;color:#4A5C78;">⚡ fast.site</span>
  &nbsp;·&nbsp; Lead Finder &nbsp;·&nbsp;
  {_t(
      "Find websites · Check performance · Extract contacts · Send cold emails · Export leads",
      "Websites finden · Performance prüfen · Kontakte extrahieren · Kalt-E-Mails · Leads exportieren"
  )}
</div>
""", unsafe_allow_html=True)
