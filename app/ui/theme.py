"""Presentation-only design system for inambiente's Sustainability workspace."""
from __future__ import annotations

import base64
import html
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator, List, Optional, Tuple
from urllib.parse import quote

import streamlit as st

_ASSETS = Path(__file__).resolve().parent / "assets"
_LOGO = _ASSETS / "logo.jpg"

TOKENS = {
    "brand": "#8CC63F", "brand_dark": "#4F7F1E", "brand_soft": "#EEF7E3",
    "canvas": "#F6F8F5", "surface": "#FFFFFF", "surface_alt": "#F0F4EF",
    "text": "#1F2A22", "muted": "#66736A", "border": "#DDE5DC",
    "success": "#2E7D32", "warning": "#A65D00", "danger": "#B42318",
}

_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root {
 --brand:#8CC63F; --brand-dark:#4F7F1E; --brand-soft:#EEF7E3;
 --canvas:#F6F8F5; --surface:#FFFFFF; --surface-alt:#F0F4EF;
 --text:#1F2A22; --muted:#66736A; --border:#DDE5DC;
 --success:#2E7D32; --warning:#A65D00; --danger:#B42318;
 --radius:16px; --shadow:0 8px 28px rgba(34,62,37,.07);
}
html, body, [class*="css"], .stApp, .stMarkdown, label, input, textarea, button, select {
 font-family:Inter,system-ui,-apple-system,'Segoe UI',sans-serif;
}
.stApp { background:var(--canvas); color:var(--text); font-size:16px; }
[data-testid="stHeader"] { background:rgba(246,248,245,.88); }
.block-container { max-width:1500px; padding-top:4.6rem; padding-bottom:4rem; }
.stMarkdown p,.stMarkdown li { font-size:1rem; line-height:1.7; color:var(--text); }
h1,h2,h3,h4 { color:#1F3424; letter-spacing:-.025em; }
h1 { font-size:2.15rem !important; font-weight:800 !important; }
h2 { font-size:1.55rem !important; font-weight:750 !important; }
h3 { font-size:1.2rem !important; font-weight:700 !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:var(--muted)!important; font-size:.9rem!important; line-height:1.55; }
[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid var(--border); }
[data-testid="stSidebar"] > div:first-child { padding-top:1.2rem; }
/* Streamlit 1.5x opens the sidebar at ~255px, too narrow for icon + label + chevron cards: keep a usable minimum (expanded only) */
[data-testid="stSidebar"][aria-expanded="true"] { min-width:19rem; }
/* Sidebar navigation cards: white card, soft border, chevron at the end of the row */
[data-testid="stSidebar"] [data-testid="stRadio"] { width:100%; }
[data-testid="stSidebar"] [data-testid="stRadio"] > div { gap:.55rem; }
[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] { display:flex; flex-direction:column; align-items:stretch; gap:.55rem; }
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) {
 position:relative;
 display:flex;
 align-items:center;
 gap:.4rem;
 width:100%;
 padding:.85rem 1rem .85rem 3.35rem;
 margin-bottom:0;
 border-radius:14px;
 border:1.5px solid var(--border);
 background-color:#FFFFFF;
 background-repeat:no-repeat;
 background-position:1.1rem center;
 background-size:22px 22px;
 box-shadow:0 2px 8px rgba(34,62,37,.04);
 cursor:pointer;
 overflow:hidden;
 transition:background .2s ease, border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) div[data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) span {
 font-size:1.02rem !important;
 font-weight:600;
 color:#2D3D30;
 line-height:1.35;
 letter-spacing:-.01em;
 overflow-wrap:normal;
 word-break:normal;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) div[data-testid="stMarkdownContainer"] p {
 display:flex;
 align-items:center;
 gap:.6rem;
 margin:0 !important;
}
/* The ":material/...:" shortcodes in the option labels stay in the Python source, but the icon font is not
   relied upon (it renders as clipped ligature text when the font is late): the icon is a 22px SVG drawn as the
   card background, matched by child position (see _NAV_ICON_PATHS). */
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) span[data-testid="stIconMaterial"],
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) span[role="img"][translate="no"],
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) span.material-symbols-rounded,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) span.material-symbols-sharp {
 display:none !important;
}
__NAV_ICON_RULES__
/* Hide the default circular radio indicator (BaseWeb <= 1.5x: label > div; react-aria 1.6x: stRadioOption > div > div) */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child:not(:has([data-testid="stMarkdownContainer"])),
[data-testid="stSidebar"] [data-testid="stRadio"] [data-testid="stRadioOption"] > div > div:first-child:not(:has([data-testid="stMarkdownContainer"])) {
 display:none !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]) input[type="radio"] {
 position:absolute;
 opacity:0;
 width:0;
 height:0;
 pointer-events:none;
}
/* Chevron ">" pinned to the end of every row */
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])::after {
 content:"";
 flex:0 0 18px;
 width:18px;
 height:18px;
 margin-left:auto;
 background:url("__CHEVRON__") center / contain no-repeat;
 transition:transform .2s ease;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]):hover {
 background-color:#F7FBF2;
 border-color:#C9DEB8;
 box-shadow:0 4px 14px rgba(140,198,63,.14);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]):hover::after { transform:translateX(3px); }
/* Active / checked card */
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[data-selected="true"],
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]):has(input:checked),
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[aria-checked="true"] {
 background-color:#EEF7E3 !important;
 border-color:#8CC63F !important;
 box-shadow:0 4px 16px rgba(140,198,63,.20) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[data-selected="true"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]):has(input:checked) p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[aria-checked="true"] p {
 color:#1E3B1C !important;
 font-weight:800 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[data-selected="true"]::after,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]):has(input:checked)::after,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[aria-checked="true"]::after {
 background-image:url("__CHEVRON_ACTIVE__");
}
/* Brand-green indicator bar on the left edge of the active card */
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[data-selected="true"]::before,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"]):has(input:checked)::before,
[data-testid="stSidebar"] [data-testid="stRadio"] label:not([data-testid="stWidgetLabel"])[aria-checked="true"]::before {
 content:"";
 position:absolute;
 left:0;
 top:14%;
 bottom:14%;
 width:5px;
 border-radius:0 4px 4px 0;
 background:#8CC63F;
}
/* Operating-module selector uses the same card look (BaseWeb select and the newer role=group select) */
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"] {
 min-height:3.1rem;
 padding:.15rem .5rem .15rem .35rem;
 border:1.5px solid #CFDDC6 !important;
 border-radius:14px !important;
 background:#FFFFFF !important;
 box-shadow:0 2px 8px rgba(34,62,37,.04);
 transition:border-color .2s ease, background .2s ease, box-shadow .2s ease;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover,
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within,
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"]:hover,
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"]:focus-within {
 border-color:#8CC63F !important;
 background:#F7FBF2 !important;
 box-shadow:0 4px 14px rgba(140,198,63,.16);
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] div[value],
[data-testid="stSidebar"] [data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"] { font-weight:650; color:#2D3D30; }
[data-testid="stSidebar"] [data-testid="stSelectbox"] svg { color:#4F7F1E; }
[data-testid="stVerticalBlockBorderWrapper"] { border:1px solid var(--border)!important; border-radius:var(--radius)!important; background:var(--surface); box-shadow:0 2px 12px rgba(20,50,20,.025); }
[data-testid="stMetric"] { padding:1rem 1.1rem; border:1px solid var(--border); border-radius:14px; background:white; box-shadow:0 3px 14px rgba(20,50,20,.035); }
[data-testid="stMetricLabel"] { color:var(--muted)!important; font-size:.9rem!important; }
[data-testid="stMetricValue"] { color:#29452A!important; font-weight:800!important; }
.stButton > button, .stDownloadButton > button { min-height:2.85rem; border-radius:11px; font-size:.98rem; font-weight:700; padding:.55rem 1rem; border:1px solid #D4E0D0; transition:all .16s ease; box-shadow:0 3px 10px rgba(34,62,37,.05); }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] { background:var(--brand); color:#1E3018; border-color:var(--brand); }
.stButton > button:hover, .stDownloadButton > button:hover { border-color:var(--brand-dark); transform:translateY(-1px); box-shadow:0 7px 18px rgba(61,100,35,.12); }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-baseweb="select"] > div { border-radius:10px!important; border-color:#D5DED3!important; background:#fff!important; min-height:2.7rem; }
[data-testid="stDataFrame"], [data-testid="stTable"] { border:1px solid var(--border); border-radius:12px; overflow:hidden; }
[data-testid="stExpander"] { border:1px solid var(--border); border-radius:12px; background:#fff; }
[data-testid="stChatMessage"] { border:1px solid var(--border); border-radius:16px; padding:.8rem 1rem; background:#fff; margin-bottom:.7rem; }
[data-testid="stChatInput"] { border-radius:16px; border-color:#CBD9C5; box-shadow:var(--shadow); }
[data-baseweb="tab-list"] { gap:.45rem; }
[data-baseweb="tab"] { border-radius:10px 10px 0 0; padding:.7rem 1rem; }
hr { border-color:var(--border)!important; }
.nav-eyebrow { color:#78906F; font-size:.72rem; font-weight:800; letter-spacing:.12em; padding:.6rem .2rem .2rem; }
.tenant-mini { display:flex; gap:.65rem; align-items:center; padding:.8rem .7rem; margin:.65rem 0; background:#F4F8F0; border:1px solid #E0EAD8; border-radius:12px; overflow-wrap:anywhere; }
.tenant-mini b { display:block; color:#29452A; font-size:.88rem; }
.tenant-mini small { display:block; color:#6B7B69; margin-top:.15rem; font-size:.78rem; }
.tenant-badge {
 display:block;
 flex:0 0 36px;
 width:36px;
 height:36px;
 border-radius:11px;
 background:#FFFFFF url("__TENANT_ICON__") center / 20px 20px no-repeat;
 border:1px solid #D5E5C6;
 box-shadow:0 2px 6px rgba(79,127,30,.10);
}
.tenant-badge.is-empty { background-image:url("__TENANT_ICON_EMPTY__"); border-style:dashed; border-color:#C9D3C6; box-shadow:none; }

/* Company identity modal: dialog sized to the logo, logo centred and symmetric */
[role="dialog"]:has(.identity-modal) { width:min(700px,94vw) !important; max-width:94vw !important; margin-inline:auto !important; }
.identity-modal { display:flex; flex-direction:column; align-items:center; gap:1.1rem; }
.identity-modal .identity-logo {
 display:block;
 width:100% !important;
 max-width:560px !important;
 height:auto;
 margin:0 auto;
 object-fit:contain;
 background:#fff;
 border:1px solid var(--border);
 border-radius:16px;
 box-shadow:0 4px 18px rgba(34,62,37,.07);
}
.identity-copy { width:100%; max-width:560px; text-align:center; }
.identity-copy h2 { margin:0; padding:0; color:#1F3424; font-weight:800; letter-spacing:-.02em; }
.identity-tag { color:#4F7F1E; font-weight:700; letter-spacing:.08em; font-size:.82rem; text-transform:uppercase; margin:.4rem 0 .8rem; }
.identity-copy p { color:#556658; font-size:.95rem; line-height:1.6; margin:0; }

/* Interactive brand card at the top of the sidebar */
.brand-card-container {
 position:relative;
 cursor:pointer;
 margin-bottom:0.25rem;
}
.brand-card {
 display:flex;
 align-items:center;
 gap:.8rem;
 padding:.85rem .9rem;
 border:1.5px solid var(--border);
 border-radius:16px;
 background:linear-gradient(135deg,#FFFFFF 0%,#F3F8EE 100%);
 box-shadow:0 3px 12px rgba(34,62,37,.05);
 transition:all .2s ease;
}
.brand-card:hover {
 border-color:var(--brand);
 transform:translateY(-2px);
 box-shadow:0 8px 24px rgba(140,198,63,.25);
}
.brand-card img {
 width:52px;
 height:52px;
 object-fit:contain;
 border-radius:10px;
 background:#fff;
 box-shadow:0 2px 6px rgba(0,0,0,.06);
 flex-shrink:0;
}
.brand-card .brand-info { flex:1; min-width:0; }
.brand-card .brand-name { font-size:1.12rem; font-weight:850; color:#244026; letter-spacing:-.02em; line-height:1.15; }
.brand-card .brand-sub { font-size:.72rem; font-weight:700; color:#5D745B; letter-spacing:.06em; margin-top:.2rem; text-transform:uppercase; }

/* Whole-card click target: invisible button stretched over the card via Streamlit's .st-key-* classes */
.st-key-brand_card_box { position:relative !important; gap:0 !important; margin-bottom:.85rem; cursor:pointer; }
.st-key-brand_card_box:hover .brand-card { border-color:var(--brand); transform:translateY(-2px); box-shadow:0 8px 24px rgba(140,198,63,.25); }
/* Card visuals never intercept the mouse: clicks fall through to the overlay button */
.st-key-brand_card_box .brand-card,
.st-key-brand_card_box .brand-card * { pointer-events:none !important; }
/* Neutralise every intermediate Streamlit wrapper so the button's containing block is the card box itself */
.st-key-brand_card_trigger,
.st-key-brand_card_trigger * { position:static !important; transform:none !important; }
.st-key-brand_card_trigger { margin:0 !important; height:0 !important; min-height:0 !important; overflow:visible !important; }
.st-key-brand_card_trigger button {
 position:absolute !important;
 inset:0 !important;
 width:100% !important;
 height:100% !important;
 z-index:5 !important;
 opacity:0 !important;
 cursor:pointer !important;
 pointer-events:auto !important;
 border:none !important;
 background:transparent !important;
 box-shadow:none !important;
 min-height:0 !important;
 margin:0 !important;
 padding:0 !important;
}

/* Full-width executive header banner with vector sustainability artwork */
.page-hero {
 position:relative;
 overflow:hidden;
 width:100%;
 border:1.5px solid #D6E8CD;
 border-radius:22px;
 padding:1.85rem 2.4rem;
 background:
  linear-gradient(90deg,#FFFFFF 0%,rgba(255,255,255,.92) 34%,rgba(255,255,255,0) 66%),
  url("__HERO_ART__") right bottom / auto 100% no-repeat,
  linear-gradient(130deg,#FFFFFF 0%,#F4F9EF 55%,#E6F2DB 100%);
 box-shadow:0 10px 32px rgba(45,80,40,.06), 0 2px 6px rgba(0,0,0,.02);
 margin-bottom:1.85rem;
 display:flex;
 justify-content:space-between;
 align-items:center;
 gap:1.8rem;
}
.page-hero::before {
 content:"";
 position:absolute;
 left:0;
 top:0;
 bottom:0;
 width:7px;
 background:linear-gradient(180deg,#8CC63F 0%,#4F7F1E 100%);
}
.page-hero-content { position:relative; flex:1; min-width:0; }
.page-hero .eyebrow {
 display:inline-flex;
 align-items:center;
 gap:6px;
 text-transform:uppercase;
 letter-spacing:.12em;
 font-size:.74rem;
 color:#46701B;
 font-weight:800;
 background:rgba(140,198,63,.15);
 border:1px solid rgba(140,198,63,.35);
 padding:3px 12px;
 border-radius:999px;
 margin-bottom:.65rem;
}
.page-hero .headline {
 color:#1A341E;
 font-size:2.25rem;
 font-weight:850;
 letter-spacing:-.035em;
 line-height:1.18;
 margin:0;
}
.page-hero .subline {
 display:flex;
 align-items:center;
 flex-wrap:wrap;
 gap:10px;
 margin-top:.8rem;
 font-size:.95rem;
}
/* Frosted-glass status pills (tenant + version) */
.page-hero .hero-subline-text {
 color:#38543B;
 font-size:1.02rem;
 font-weight:550;
 margin-top:.45rem;
 line-height:1.45;
}
.page-hero .tenant-pill,
.page-hero .module-pill,
.page-hero .version-badge {
 display:inline-flex;
 align-items:center;
 gap:6px;
 padding:5px 14px;
 border-radius:999px;
 border:1px solid rgba(79,127,30,.28);
 background:rgba(255,255,255,.62);
 -webkit-backdrop-filter:blur(8px);
 backdrop-filter:blur(8px);
 box-shadow:0 2px 8px rgba(45,80,40,.06), inset 0 1px 0 rgba(255,255,255,.8);
 font-weight:700;
 color:#213C24;
}
.page-hero .module-pill {
 background:rgba(238,247,227,.75);
 color:#274B16;
 border-color:rgba(140,198,63,.45);
}
.page-hero .version-badge { font-size:.84rem; color:#4F7F1E; }
.page-hero-slogan {
 position:relative;
 align-self:flex-end;
 flex:0 1 300px;
 max-width:320px;
 display:flex;
 gap:.7rem;
 align-items:flex-start;
 padding:1rem 1.15rem;
 border-radius:16px;
 border:1px solid rgba(79,127,30,.22);
 background:rgba(255,255,255,.52);
 -webkit-backdrop-filter:blur(3px);
 backdrop-filter:blur(3px);
 box-shadow:0 6px 20px rgba(45,80,40,.08);
 color:#1F4A1E;
 font-size:1.12rem;
 font-weight:750;
 line-height:1.35;
 letter-spacing:-.01em;
 text-align:right;
}
.page-hero-slogan svg { flex:0 0 26px; width:26px; height:26px; color:#4F7F1E; }

/* Dashboard metric cards */
.metric-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:1rem; margin:.4rem 0 1.5rem; }
.metric-card {
 display:flex;
 gap:1.2rem;
 align-items:center;
 padding:1.3rem 1.4rem;
 background:#fff;
 border:1.5px solid var(--border);
 border-radius:18px;
 box-shadow:0 4px 18px rgba(34,62,37,.05);
}
.metric-icon { display:grid; place-items:center; flex:0 0 64px; width:64px; height:64px; border-radius:18px; }
.metric-icon svg { width:34px; height:34px; }
.metric-body { min-width:0; }
.metric-label { display:flex; align-items:center; gap:7px; color:var(--muted); font-size:.92rem; font-weight:650; }
.metric-info {
 display:inline-grid; place-items:center; width:16px; height:16px; border-radius:50%;
 border:1.5px solid #9AA89C; color:#7C897E; font-size:.64rem; font-weight:800; font-style:normal; cursor:help;
}
.metric-value { color:#1F3424; font-size:2.4rem; font-weight:850; line-height:1.1; letter-spacing:-.03em; margin-top:.25rem; }
.metric-note { margin-top:.4rem; font-size:.85rem; font-weight:650; color:var(--muted); }
.metric-card.tone-green .metric-icon { background:#E6F4D4; color:#4F7F1E; }
.metric-card.tone-blue  .metric-icon { background:#DDEBFC; color:#1D5FB8; }
.metric-card.tone-red   .metric-icon { background:#FCE3DE; color:#C4412F; }
.metric-card.tone-green .metric-note.delta { color:#2E7D32; }
.metric-card.tone-blue  .metric-note.delta { color:#1D5FB8; }
.metric-card.tone-red   .metric-note.delta { color:#B42318; }

/* File dropzone: Italian copy, upload illustration on the left, single green "Sfoglia file" button on the right.
   Streamlit's own texts (1.50: "Drag and drop files here" / "Limit ..." / "Browse files"; 1.6x: "Upload") are hidden
   and replaced through pseudo-elements, so the result does not depend on the Streamlit version's inner markup. */
[data-testid="stFileUploader"] { border:none; padding:0; background:transparent; }
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
 position:relative;
 display:flex;
 align-items:center;
 gap:1rem;
 min-height:7.6rem;
 padding:1.2rem 1.6rem 1.2rem 8.6rem;
 border:1.5px dashed #A9C795;
 border-radius:18px;
 background:#FAFDF7 url("__UPLOAD_ART__") no-repeat 1.5rem center / 80px 80px;
 transition:border-color .2s ease, background-color .2s ease;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"]:hover { border-color:#8CC63F; background-color:#F3FAEA; }
/* Text column: native children hidden, Italian copy drawn by ::before / ::after */
[data-testid="stFileUploaderDropzoneInstructions"] {
 order:1;
 flex:1 1 auto;
 display:flex;
 flex-direction:column;
 gap:.2rem;
 min-width:0;
 align-items:flex-start !important;
 justify-content:center;
 text-align:left !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > * { display:none !important; }
[data-testid="stFileUploaderDropzoneInstructions"]::before {
 content:"Trascina qui i file";
 color:#1F3424;
 font-size:1.08rem;
 font-weight:750;
 letter-spacing:-.01em;
}
[data-testid="stFileUploaderDropzoneInstructions"]::after {
 content:"PDF, Word, Excel e immagini \2014  oppure selezionali dal computer";
 color:var(--muted);
 font-size:.9rem;
 font-weight:500;
 line-height:1.4;
}
/* Action button (and the wrapper Streamlit puts around it) pushed to the right edge */
[data-testid="stFileUploaderDropzone"] > button,
[data-testid="stFileUploaderDropzone"] > div:has(button),
[data-testid="stFileUploaderDropzone"] > span:has(button) { order:2; margin-left:auto; flex:0 0 auto; }
[data-testid="stFileUploaderDropzone"] button {
 display:inline-flex !important;
 align-items:center;
 justify-content:center;
 min-height:2.75rem;
 min-width:9rem;
 padding:0 1.5rem !important;
 background:#8CC63F !important;
 border:1px solid #8CC63F !important;
 border-radius:11px !important;
 box-shadow:0 4px 12px rgba(140,198,63,.30);
 font-size:0 !important;
 line-height:0 !important;
 color:transparent !important;
 transition:background .16s ease, transform .16s ease;
}
[data-testid="stFileUploaderDropzone"] button:hover { background:#7DB531 !important; transform:translateY(-1px); }
/* Whatever the button contains (text node, markdown wrapper, icon) is hidden: only the Italian label shows */
[data-testid="stFileUploaderDropzone"] button > * { display:none !important; }
[data-testid="stFileUploaderDropzone"] button::after {
 content:"Sfoglia file";
 color:#1E3018;
 font-size:.98rem;
 font-weight:750;
 line-height:1.2;
}
@media (max-width:640px) {
 [data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
  flex-direction:column;
  align-items:flex-start;
  padding:6.2rem 1.2rem 1.2rem;
  background-position:1.2rem 1.1rem;
 }
 [data-testid="stFileUploaderDropzone"] > button,
 [data-testid="stFileUploaderDropzone"] > div:has(button),
 [data-testid="stFileUploaderDropzone"] > span:has(button) { margin-left:0; }
}

/* Operational Action Buttons: Esegui analisi, Rigenera fascicolo, Elimina, Svuota */
.st-key-btn_run_pipeline button,
.st-key-btn_rebuild_report button,
.st-key-btn_delete_doc button,
.st-key-btn_delete_all button {
 min-height:3.2rem !important;
 height:3.2rem !important;
 border-radius:11px !important;
 padding:0 1.4rem !important;
 font-size:.98rem !important;
 font-weight:750 !important;
 letter-spacing:-.01em !important;
 transition:all .16s ease !important;
 display:inline-flex !important;
 align-items:center !important;
 justify-content:center !important;
 gap:.5rem !important;
}
.st-key-btn_run_pipeline button p,
.st-key-btn_rebuild_report button p,
.st-key-btn_delete_doc button p,
.st-key-btn_delete_all button p {
 font-size:.98rem !important;
 font-weight:750 !important;
 letter-spacing:-.01em !important;
 margin:0 !important;
}
.st-key-btn_run_pipeline button span[data-testid="stIconMaterial"],
.st-key-btn_rebuild_report button span[data-testid="stIconMaterial"],
.st-key-btn_delete_doc button span[data-testid="stIconMaterial"],
.st-key-btn_delete_all button span[data-testid="stIconMaterial"] {
 font-size:1.25rem !important;
 display:inline-flex !important;
 align-items:center !important;
}
.st-key-btn_run_pipeline button {
 background:#8CC63F !important;
 color:#1E3018 !important;
 border:1px solid #8CC63F !important;
 box-shadow:0 4px 14px rgba(140,198,63,.32) !important;
}
.st-key-btn_run_pipeline button:hover {
 background:#7DB531 !important;
 border-color:#7DB531 !important;
 color:#1E3018 !important;
 transform:translateY(-1px);
 box-shadow:0 6px 18px rgba(125,181,49,.42) !important;
}
.st-key-btn_run_pipeline button:active {
 transform:translateY(0);
 box-shadow:0 2px 8px rgba(125,181,49,.25) !important;
}
.st-key-btn_rebuild_report button {
 background:#FFFFFF !important;
 color:#244026 !important;
 border:1.5px solid #A9C795 !important;
 box-shadow:0 3px 12px rgba(34,62,37,.05) !important;
}
.st-key-btn_rebuild_report button:hover {
 background:#F4F8F0 !important;
 border-color:#8CC63F !important;
 color:#1E3018 !important;
 transform:translateY(-1px);
 box-shadow:0 6px 16px rgba(140,198,63,.18) !important;
}
.st-key-btn_rebuild_report button:active {
 transform:translateY(0);
 box-shadow:0 2px 6px rgba(34,62,37,.05) !important;
}
.st-key-btn_delete_doc button {
 background:#FFF8F7 !important;
 color:#B42318 !important;
 border:1.5px solid #FECDCA !important;
 box-shadow:0 3px 10px rgba(180,35,24,.05) !important;
}
.st-key-btn_delete_doc button:hover {
 background:#FEE4E2 !important;
 border-color:#FDA29B !important;
 color:#912018 !important;
 transform:translateY(-1px);
 box-shadow:0 6px 16px rgba(180,35,24,.16) !important;
}
.st-key-btn_delete_doc button:active {
 transform:translateY(0);
 box-shadow:0 2px 6px rgba(180,35,24,.10) !important;
}
.st-key-btn_delete_all button {
 background:#FEF3F2 !important;
 color:#B42318 !important;
 border:1.5px solid #FECDCA !important;
 box-shadow:0 3px 10px rgba(180,35,24,.06) !important;
}
.st-key-btn_delete_all button:hover {
 background:#FECDCA !important;
 border-color:#F04438 !important;
 color:#7A1913 !important;
 transform:translateY(-1px);
 box-shadow:0 6px 18px rgba(180,35,24,.22) !important;
}
.st-key-btn_delete_all button:active {
 transform:translateY(0);
 box-shadow:0 2px 6px rgba(180,35,24,.12) !important;
}
.st-key-sel_remove_doc [data-baseweb="select"] > div {
 min-height:3.2rem !important;
 height:3.2rem !important;
 border-radius:11px !important;
}
.kpi-grid { display:flex; gap:.8rem; flex-wrap:wrap; }
.kpi-card { flex:1; min-width:130px; padding:1rem; background:#fff; border:1px solid var(--border); border-radius:14px; box-shadow:0 3px 12px rgba(25,55,25,.04); }
.kpi-label { color:var(--muted); font-size:.8rem; font-weight:600; }
.kpi-value { color:#29452A; font-size:1.6rem; font-weight:800; margin-top:.2rem; }
.kpi-hint { color:#788579; font-size:.76rem; margin-top:.2rem; }
.stat-chips { display:flex; flex-wrap:wrap; gap:.5rem; margin:.5rem 0 1rem; }
.stat-chip { border:1px solid var(--border); background:#fff; border-radius:999px; padding:.45rem .75rem; font-size:.83rem; color:#344538; }
.stat-chip b { margin-left:.25rem; }
.stat-chip.ok { background:#EEF8EB; border-color:#D5EACB; }
.stat-chip.warn { background:#FFF7E8; border-color:#F2D9A8; }
.stat-chip.crit { background:#FFF0EF; border-color:#F0C7C4; }
.loader-shell { padding:1rem; border:1px solid var(--border); border-radius:14px; background:white; }
.loader-track { height:7px; border-radius:99px; overflow:hidden; background:#E7EDE4; margin-top:.7rem; }
.loader-fill { width:40%; height:100%; border-radius:99px; background:linear-gradient(90deg,#8CC63F,#C8E86D,#8CC63F); animation:shimmer 1.5s infinite ease-in-out; }
@keyframes shimmer { 0%{transform:translateX(-110%)} 100%{transform:translateX(280%)} }
@media(max-width:900px){
 .block-container{padding:4.2rem .8rem 2rem}
 .page-hero{flex-direction:column; align-items:flex-start; padding:1.35rem 1.5rem}
 .page-hero .headline{font-size:1.7rem}
 .page-hero-slogan{flex:1 1 auto; max-width:none; text-align:left}
}
"""


HERO_SLOGAN = "Documenti oggi per un domani più sostenibile."

# Clean vector artwork for the hero banner: rolling green hills, a low-rise green city and wind turbines.
_HERO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 260" preserveAspectRatio="xMaxYMax slice">
<defs>
<linearGradient id="far" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#BFE08F"/><stop offset="1" stop-color="#9CCB63"/></linearGradient>
<linearGradient id="near" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#8CC63F"/><stop offset="1" stop-color="#5E9A2B"/></linearGradient>
<g id="blades"><path d="M0 0 L-2.4 -5 L0 -50 L2.4 -5Z"/><path d="M0 0 L-2.4 -5 L0 -50 L2.4 -5Z" transform="rotate(120)"/><path d="M0 0 L-2.4 -5 L0 -50 L2.4 -5Z" transform="rotate(240)"/></g>
</defs>
<path d="M300 190 C400 150 480 175 580 150 C700 120 820 160 960 130 L960 260 L300 260Z" fill="url(#far)" opacity=".75"/>
<g fill="#4F7F1E" fill-opacity=".30">
<rect x="430" y="148" width="22" height="46"/><rect x="456" y="130" width="26" height="64"/><rect x="486" y="156" width="20" height="38"/>
<rect x="510" y="140" width="24" height="54"/><rect x="538" y="160" width="18" height="34"/>
</g>
<g fill="#FFFFFF" fill-opacity=".55">
<rect x="460" y="138" width="4" height="4"/><rect x="468" y="138" width="4" height="4"/><rect x="460" y="150" width="4" height="4"/><rect x="468" y="150" width="4" height="4"/>
<rect x="515" y="150" width="4" height="4"/><rect x="523" y="150" width="4" height="4"/><rect x="434" y="158" width="4" height="4"/><rect x="442" y="158" width="4" height="4"/>
</g>
<g fill="#6FA83A" fill-opacity=".85"><rect x="456" y="126" width="26" height="4" rx="2"/><rect x="510" y="136" width="24" height="4" rx="2"/></g>
<g fill="#FFFFFF" stroke="#5E9A2B" stroke-width="1.1">
<path d="M638 168 L640 64 L642 168Z"/><use href="#blades" transform="translate(640 64) rotate(15)"/>
<path d="M758 172 L760 80 L762 172Z"/><use href="#blades" transform="translate(760 80) scale(.8) rotate(70)"/>
<path d="M858 168 L860 92 L862 168Z"/><use href="#blades" transform="translate(860 92) scale(.62) rotate(40)"/>
<path d="M908 164 L910 108 L912 164Z"/><use href="#blades" transform="translate(910 108) scale(.46) rotate(95)"/>
</g>
<path d="M0 214 C140 180 260 215 400 196 C560 174 700 214 860 190 C910 183 940 186 960 184 L960 260 L0 260Z" fill="url(#near)"/>
<g fill="#FFFFFF" fill-opacity=".30"><circle cx="600" cy="232" r="18"/><circle cx="880" cy="226" r="24"/></g>
</svg>"""


def _svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;utf8," + quote(" ".join(svg.split()))


def _chevron_uri(color: str) -> str:
    return _svg_data_uri(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='none' stroke='" + color +
        "' stroke-width='2.2' stroke-linecap='round' stroke-linejoin='round'><path d='M7 4l6 6-6 6'/></svg>"
    )


# Sidebar navigation icons, in the order of the st.radio options (matched by child position).
_NAV_ICON_PATHS = (
    # Area Documentale & Pipeline — folder
    "<path d='M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z'/>",
    # Profilo Anagrafico & Utente — office building
    "<rect x='5' y='3' width='14' height='18' rx='1.5'/><path d='M9 7h2M13 7h2M9 11h2M13 11h2M9 15h2M13 15h2'/>",
    # Chat Documentale — speech bubble
    "<path d='M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.3A8 8 0 1 1 21 12z'/><path d='M8.5 12h.01M12 12h.01M15.5 12h.01'/>",
    # Estrazione & Revisione — bar chart
    "<path d='M4 20h16M7 20v-7M12 20V5M17 20v-10'/>",
    # Scadenze & Allerte — calendar with clock hand
    "<rect x='3.5' y='5' width='17' height='15.5' rx='2'/><path d='M3.5 10h17M8 3v4M16 3v4M12 13v3l2 1.2'/>",
)

_NAV_GROUP = '[data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"]'


def _line_icon_uri(paths: str, color: str, stroke: str = "1.8") -> str:
    return _svg_data_uri(
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='" + color +
        "' stroke-width='" + stroke + "' stroke-linecap='round' stroke-linejoin='round'>" + paths + "</svg>"
    )


def _nav_icon_rules() -> str:
    """One rule per option for the idle icon and one (higher specificity) for the checked card.

    The card <label> is a direct child of the radiogroup in Streamlit 1.5x (BaseWeb) but sits inside a per-option
    wrapper <div> in 1.6x (react-aria), so both shapes are targeted by child position."""
    rules = []
    for i, paths in enumerate(_NAV_ICON_PATHS, start=1):
        idle, active = _line_icon_uri(paths, "#4F7F1E"), _line_icon_uri(paths, "#2E6212", "2")

        def sel(state: str = "") -> str:
            return f"{_NAV_GROUP} > label:nth-child({i}){state}, {_NAV_GROUP} > :nth-child({i}) > label{state}"

        rules.append(f'{sel()} {{ background-image:url("{idle}"); }}')
        for state in ('[data-selected="true"]', ":has(input:checked)"):
            rules.append(f'{sel(state)} {{ background-image:url("{active}"); }}')
    return "\n".join(rules)


# Dropzone illustration: soft disc, green cloud with white upward arrow, leaves around it.
_UPLOAD_ART_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96'>
<circle cx='48' cy='48' r='46' fill='#EEF7E3'/>
<path d='M16 34c0-9 7-15 16-15 0 9-7 15-16 15z' fill='#6FA83A'/>
<path d='M16 34c4-6 8-10 14-13' stroke='#EEF7E3' stroke-width='1.4' fill='none' stroke-linecap='round'/>
<path d='M80 38c0-8-6-13-13-13 0 8 6 13 13 13z' fill='#A8D56A'/>
<path d='M74 74c-7 0-12-5-12-11 7 0 12 5 12 11z' fill='#6FA83A'/>
<g fill='#8CC63F'><circle cx='37' cy='55' r='11'/><circle cx='51' cy='46' r='15'/><circle cx='65' cy='55' r='10'/><rect x='37' y='55' width='28' height='11'/></g>
<path d='M51 59V40M43 47l8-8 8 8' stroke='#FFFFFF' stroke-width='4.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/>
</svg>"""

# Company tag shown in the sidebar: office building (configured) / dashed variant (not configured yet).
_TENANT_PATHS = (
    "<rect x='5' y='3' width='14' height='18' rx='1.5'/><path d='M9 7h2M13 7h2M9 11h2M13 11h2'/><path d='M10 21v-4h4v4'/>"
)


_LEAF_ICON = (
    "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' "
    "stroke-linejoin='round' aria-hidden='true'><path d='M5 19c0-8 5-13 14-14 0 9-5 14-13 14'/><path d='M5 19c3-5 6-8 10-10'/></svg>"
)


def inject_custom_css() -> None:
    css = (
        _CSS.replace("__NAV_ICON_RULES__", _nav_icon_rules())
        .replace("__HERO_ART__", _svg_data_uri(_HERO_SVG))
        .replace("__UPLOAD_ART__", _svg_data_uri(_UPLOAD_ART_SVG))
        .replace("__TENANT_ICON_EMPTY__", _line_icon_uri(_TENANT_PATHS, "#8A968C"))
        .replace("__TENANT_ICON__", _line_icon_uri(_TENANT_PATHS, "#4F7F1E"))
        .replace("__CHEVRON_ACTIVE__", _chevron_uri("#4F7F1E"))
        .replace("__CHEVRON__", _chevron_uri("#7C897E"))
    )
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


@lru_cache(maxsize=1)
def _logo_data_uri() -> str:
    """Logo as a data URI (no media-file round trip, so it is there on the very first render); "" if missing."""
    for candidate in (_LOGO, _LOGO.with_suffix(".png")):
        try:
            if candidate.is_file():
                encoded = base64.b64encode(candidate.read_bytes()).decode("ascii")
                mime = "image/png" if candidate.suffix.lower() == ".png" else "image/jpeg"
                return f"data:{mime};base64,{encoded}"
        except OSError:
            continue
    return ""


@st.dialog("inambiente S.r.l. · Identità Aziendale", width="large")
def show_company_identity_modal() -> None:
    """Company identity modal: logo centred at a controlled width, then the product blurb."""
    uri = _logo_data_uri()
    logo_html = f"<img class='identity-logo' src='{uri}' alt='inambiente S.r.l. - logo e dati aziendali'>" if uri else ""
    st.markdown(
        "<div class='identity-modal'>"
        f"{logo_html}"
        "<div class='identity-copy'>"
        "<h2>inambiente S.r.l.</h2>"
        "<div class='identity-tag'>Document Intelligence · Sustainability · Compliance</div>"
        "<p>Piattaforma avanzata per l'analisi documentale multimodale, audit di conformità ISO 14001, "
        "gestione dei consumi energetici, monitoraggio scadenze e generazione di report e fascicoli gestionali.</p>"
        "</div></div>",
        unsafe_allow_html=True,
    )


def render_brand_header() -> None:
    """Renders the brand card in the sidebar; the whole card is clickable and opens the identity modal."""
    uri = _logo_data_uri()
    img_html = f"<img src='{uri}' alt='inambiente logo'>" if uri else ""
    with st.container(key="brand_card_box"):
        st.markdown(
            f"""
            <div class='brand-card'>
                {img_html}
                <div class='brand-info'>
                    <div class='brand-name'>inambiente</div>
                    <div class='brand-sub'>DOCUMENT INTELLIGENCE</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Invisible full-card overlay button (styled via .st-key-brand_card_trigger in _CSS).
        if st.button("Apri identità aziendale", key="brand_card_trigger", use_container_width=True):
            show_company_identity_modal()


def render_page_header(
    title: str,
    version: str = "",
    tenant: str = "",
    subtitle: str = "",
    module_label: str = "",
) -> None:
    safe_title = html.escape(str(title or "Workspace"))
    safe_tenant = html.escape(str(tenant or "Azienda non configurata"))
    safe_version = html.escape(str(version or ""))
    safe_subtitle = html.escape(str(subtitle or ""))
    safe_module = html.escape(str(module_label or ""))

    subtitle_html = f"<div class='hero-subline-text'>{safe_subtitle}</div>" if safe_subtitle else ""
    version_badge_html = f"<span class='version-badge'>{safe_version}</span>" if safe_version else ""
    module_pill_html = f"<span class='module-pill'>🧩 {safe_module}</span>" if safe_module else ""

    st.markdown(
        f"""
        <div class='page-hero'>
            <div class='page-hero-content'>
                <div class='eyebrow'>🌱 Sustainability · Compliance Platform</div>
                <div class='headline'>{safe_title}</div>
                {subtitle_html}
                <div class='subline'>
                    <span class='tenant-pill'>🏢 {safe_tenant}</span>
                    {module_pill_html}
                    {version_badge_html}
                </div>
            </div>
            <div class='page-hero-slogan'>{_LEAF_ICON}<span>{html.escape(HERO_SLOGAN)}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(text: str, subtitle: str = "", compact: bool = False) -> None:
    st.markdown(f"### {html.escape(str(text))}", unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def sidebar_label(text: str) -> None:
    st.markdown(f"<div class='nav-eyebrow'>{html.escape(str(text))}</div>", unsafe_allow_html=True)


def render_sidebar_stats(n_docs: int, n_chunks: int) -> None:
    st.markdown(f"<div class='tenant-mini'><span class='tenant-badge'></span><div><b>{int(n_docs)} documenti attivi</b><small>Archivio documentale</small></div></div>", unsafe_allow_html=True)


def danger_zone_marker() -> None:
    st.markdown("<div style='color:#B42318;font-weight:800;font-size:.82rem;padding:.4rem 0'>AREA RISERVATA · AZIONI IRREVERSIBILI</div>", unsafe_allow_html=True)


def layout_split_marker() -> None:
    return None


def render_kpi_row(items: List[Tuple[str, object, str, str]]) -> None:
    cols = st.columns(max(1, len(items)))
    for col, item in zip(cols, items):
        label, value, hint, level = item
        with col:
            st.markdown(f"<div class='kpi-card'><div class='kpi-label'>{html.escape(str(label))}</div><div class='kpi-value'>{html.escape(str(value))}</div><div class='kpi-hint'>{html.escape(str(hint))}</div></div>", unsafe_allow_html=True)


_METRIC_ICONS = {
    "docs": "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'/><path d='M14 3v5h5'/><path d='M9 13h6M9 17h4'/></svg>",
    "indexed": "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><ellipse cx='12' cy='6' rx='7' ry='3'/><path d='M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6'/><path d='M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6'/></svg>",
    "alert": "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'><path d='M10.3 4.2 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z'/><path d='M12 9v4M12 16.5v.01'/></svg>",
}


@dataclass(frozen=True)
class MetricCard:
    """Presentation-only dashboard card. `delta` (e.g. '+12% rispetto al mese scorso') is rendered only when
    the caller supplies a real, computed figure; otherwise `note` is shown."""
    label: str
    value: object
    tone: str = "green"            # green | blue | red
    icon: str = "docs"             # docs | indexed | alert
    info: str = ""                 # tooltip behind the (i) badge
    note: str = ""
    delta: Optional[str] = None
    delta_trend: str = "up"        # up | down


def render_metric_cards(cards: List[MetricCard]) -> None:
    parts = []
    for c in cards:
        tone = c.tone if c.tone in {"green", "blue", "red"} else "green"
        info = f"<i class='metric-info' title='{html.escape(c.info, quote=True)}'>i</i>" if c.info else ""
        if c.delta:
            arrow = "▼" if c.delta_trend == "down" else "▲"
            foot = f"<div class='metric-note delta'>{arrow} {html.escape(c.delta)}</div>"
        else:
            foot = f"<div class='metric-note'>{html.escape(c.note)}</div>" if c.note else ""
        parts.append(
            f"<div class='metric-card tone-{tone}'>"
            f"<div class='metric-icon'>{_METRIC_ICONS.get(c.icon, _METRIC_ICONS['docs'])}</div>"
            f"<div class='metric-body'><div class='metric-label'>{html.escape(c.label)}{info}</div>"
            f"<div class='metric-value'>{html.escape(str(c.value))}</div>{foot}</div></div>"
        )
    st.markdown("<div class='metric-grid'>" + "".join(parts) + "</div>", unsafe_allow_html=True)


def render_stat_chips(items: List[Tuple[str, object, str]]) -> None:
    chunks = []
    for label, value, level in items:
        cls = level if level in {"ok", "warn", "crit"} else ""
        chunks.append(f"<span class='stat-chip {cls}'>{html.escape(str(label))}<b>{html.escape(str(value))}</b></span>")
    st.markdown("<div class='stat-chips'>" + "".join(chunks) + "</div>", unsafe_allow_html=True)


@contextmanager
def loader(title: str, subtitle: str = "", variant: str = "orbit") -> Iterator[object]:
    with st.container(border=True):
        st.markdown(f"**{html.escape(title)}**")
        if subtitle:
            st.caption(subtitle)
        st.markdown("<div class='loader-track'><div class='loader-fill'></div></div>", unsafe_allow_html=True)
        slot = st.empty()
        try:
            yield slot
        finally:
            pass


def progress_bar(slot, done: int, total: int, label: str = "") -> None:
    total = max(1, int(total))
    slot.progress(min(1.0, max(0.0, done / total)), text=label or f"{done}/{total}")
