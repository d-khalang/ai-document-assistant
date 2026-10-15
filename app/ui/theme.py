"""Presentation-only design system for inambiente's Sustainability workspace."""
from __future__ import annotations

import base64
import html
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Tuple

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
.block-container { max-width:1500px; padding-top:1.8rem; padding-bottom:4rem; }
.stMarkdown p,.stMarkdown li { font-size:1rem; line-height:1.7; color:var(--text); }
h1,h2,h3,h4 { color:#1F3424; letter-spacing:-.025em; }
h1 { font-size:2.15rem !important; font-weight:800 !important; }
h2 { font-size:1.55rem !important; font-weight:750 !important; }
h3 { font-size:1.2rem !important; font-weight:700 !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:var(--muted)!important; font-size:.9rem!important; line-height:1.55; }
[data-testid="stSidebar"] { background:#FFFFFF; border-right:1px solid var(--border); }
[data-testid="stSidebar"] > div:first-child { padding-top:1.2rem; }
/* Modern Pill Navigation for Sidebar Radio */
[data-testid="stSidebar"] [data-testid="stRadio"] { width:100%; }
[data-testid="stSidebar"] [data-testid="stRadio"] > div { gap:.4rem; }
[data-testid="stSidebar"] [data-testid="stRadio"] label {
 position:relative;
 display:flex;
 align-items:center;
 width:100%;
 padding:.85rem 1.15rem;
 margin-bottom:.45rem;
 border-radius:14px;
 border:1.5px solid transparent;
 background:transparent;
 cursor:pointer;
 overflow:hidden;
 transition:all .25s cubic-bezier(0.4, 0, 0.2, 1);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label p,
[data-testid="stSidebar"] [data-testid="stRadio"] label div[data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label span {
 font-size:1.15rem !important;
 font-weight:600;
 color:#2D3D30;
 line-height:1.35;
 letter-spacing:-.01em;
 transition:color .2s ease, font-weight .2s ease;
}
/* Hide the small default circular radio indicator for a clean pill-tab look */
[data-testid="stSidebar"] [data-testid="stRadio"] label > div > div:first-child:not(:only-child),
[data-testid="stSidebar"] [data-testid="stRadio"] label div[class*="e1mpz0hj4"] {
 display:none !important;
}
/* Hover State with soft organic green and smooth horizontal slide */
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
 background:#EEF7E3;
 border-color:#D3E5C5;
 transform:translateX(6px);
 box-shadow:0 4px 16px rgba(140,198,63,.16);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover p {
 color:#1A381E !important;
}
/* Active / Checked State */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-selected="true"],
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked),
[data-testid="stSidebar"] [data-testid="stRadio"] label[aria-checked="true"] {
 background:#E2F1D2 !important;
 border-color:#8CC63F !important;
 box-shadow:0 4px 18px rgba(140,198,63,.22), 0 1px 3px rgba(0,0,0,.03) !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-selected="true"] p,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p,
[data-testid="stSidebar"] [data-testid="stRadio"] label[aria-checked="true"] p {
 color:#1E3B1C !important;
 font-weight:750 !important;
}
/* Distinct brand accent line on the left edge of the active navigation pill */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-selected="true"]::before,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked)::before,
[data-testid="stSidebar"] [data-testid="stRadio"] label[aria-checked="true"]::before {
 content:"";
 position:absolute;
 left:0;
 top:15%;
 bottom:15%;
 width:5px;
 border-radius:0 4px 4px 0;
 background:linear-gradient(180deg, #8CC63F 0%, #4F7F1E 100%);
}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-selected="true"]:hover,
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked):hover {
 transform:translateX(4px);
}
[data-testid="stVerticalBlockBorderWrapper"] { border:1px solid var(--border)!important; border-radius:var(--radius)!important; background:var(--surface); box-shadow:0 2px 12px rgba(20,50,20,.025); }
[data-testid="stMetric"] { padding:1rem 1.1rem; border:1px solid var(--border); border-radius:14px; background:white; box-shadow:0 3px 14px rgba(20,50,20,.035); }
[data-testid="stMetricLabel"] { color:var(--muted)!important; font-size:.9rem!important; }
[data-testid="stMetricValue"] { color:#29452A!important; font-weight:800!important; }
.stButton > button, .stDownloadButton > button { min-height:2.85rem; border-radius:11px; font-size:.98rem; font-weight:700; padding:.55rem 1rem; border:1px solid #D4E0D0; transition:all .16s ease; box-shadow:0 3px 10px rgba(34,62,37,.05); }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] { background:var(--brand); color:#1E3018; border-color:var(--brand); }
.stButton > button:hover, .stDownloadButton > button:hover { border-color:var(--brand-dark); transform:translateY(-1px); box-shadow:0 7px 18px rgba(61,100,35,.12); }
[data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea, [data-baseweb="select"] > div { border-radius:10px!important; border-color:#D5DED3!important; background:#fff!important; min-height:2.7rem; }
[data-testid="stFileUploader"] { border:1.5px dashed #B7CBAE; border-radius:16px; padding:1rem; background:#FBFDF9; }
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
.tenant-dot { display:block; width:10px; height:10px; flex:0 0 10px; border-radius:50%; background:#8CC63F; box-shadow:0 0 0 4px #E2F1D2; }

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
.brand-card .brand-zoom-pill {
 font-size:.82rem;
 padding:4px 7px;
 border-radius:8px;
 background:rgba(140,198,63,.15);
 color:#4F7F1E;
 font-weight:700;
 transition:background .15s ease;
}
.brand-card:hover .brand-zoom-pill { background:var(--brand); color:#1A331E; }

/* Whole-card click target: invisible button stretched over the card via Streamlit's .st-key-* classes */
.st-key-brand_card_box { position:relative !important; gap:0 !important; margin-bottom:.85rem; cursor:pointer; }
.st-key-brand_card_box:hover .brand-card { border-color:var(--brand); transform:translateY(-2px); box-shadow:0 8px 24px rgba(140,198,63,.25); }
.st-key-brand_card_box:hover .brand-zoom-pill { background:var(--brand); color:#1A331E; }
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

/* Full-width modern executive header banner */
.page-hero {
 position:relative;
 overflow:hidden;
 width:100%;
 border:1.5px solid #D6E8CD;
 border-radius:22px;
 padding:1.85rem 2.4rem;
 background:
  radial-gradient(circle at 94% 25%, rgba(140,198,63,.22), transparent 42%),
  radial-gradient(circle at 8% 110%, rgba(79,127,30,.08), transparent 36%),
  linear-gradient(130deg,#FFFFFF 0%,#F8FAF6 45%,#EEF6E8 100%);
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
 border-radius:6px 0 0 6px;
}
.page-hero-content { flex:1; min-width:0; }
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
 gap:12px;
 color:#556658;
 margin-top:.6rem;
 font-size:.98rem;
}
.page-hero .tenant-pill {
 font-weight:700;
 color:#213C24;
}
.page-hero .version-badge {
 background:#FFFFFF;
 border:1px solid #CFDFCA;
 border-radius:8px;
 padding:2px 10px;
 font-size:.82rem;
 font-weight:700;
 color:#4F7F1E;
 box-shadow:0 1px 4px rgba(0,0,0,.03);
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
 .block-container{padding:1rem .8rem 2rem}
 .page-hero{flex-direction:column; align-items:flex-start; padding:1.35rem 1.5rem}
 .page-hero .headline{font-size:1.7rem}
 .page-hero-brand{display:none}
}
"""


def inject_custom_css() -> None:
    st.markdown(f"<style>{_CSS}</style>", unsafe_allow_html=True)


def _logo_data_uri() -> str:
    try:
        if _LOGO.is_file():
            encoded = base64.b64encode(_LOGO.read_bytes()).decode("ascii")
            suffix = _LOGO.suffix.lower()
            mime = "image/png" if suffix == ".png" else "image/jpeg"
            return f"data:{mime};base64,{encoded}"
    except OSError:
        pass
    return ""


@st.dialog("inambiente S.r.l. · Identità Aziendale", width="large")
def show_company_identity_modal() -> None:
    """High-resolution company identity and branding modal."""
    if _LOGO.is_file():
        st.image(str(_LOGO), use_container_width=True)
    st.markdown(
        """
        <div style="text-align:center; padding:0.8rem 0 0.5rem 0;">
            <h2 style="margin:0; color:#1F3424; font-weight:800; letter-spacing:-0.02em;">inambiente S.r.l.</h2>
            <div style="color:#4F7F1E; font-weight:700; letter-spacing:0.08em; font-size:0.86rem; text-transform:uppercase; margin:6px 0 14px 0;">
                Document Intelligence · Sustainability · Compliance
            </div>
            <p style="color:#556658; font-size:0.95rem; line-height:1.6; max-width:640px; margin:0 auto;">
                Piattaforma avanzata per l'analisi documentale multimodale, audit di conformità ISO 14001,
                gestione dei consumi energetici, monitoraggio scadenze e generazione di report e fascicoli gestionali.
            </p>
        </div>
        """,
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
                <div class='brand-zoom-pill'>🔍</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Invisible full-card overlay button (styled via .st-key-brand_card_trigger in _CSS).
        if st.button("Apri identità aziendale", key="brand_card_trigger", use_container_width=True):
            show_company_identity_modal()


def render_page_header(title: str, version: str = "", tenant: str = "") -> None:
    safe_title = html.escape(str(title or "Workspace"))
    safe_tenant = html.escape(str(tenant or "Tenant non configurato"))
    safe_version = html.escape(str(version or ""))
    version_badge_html = f"<span class='version-badge'>{safe_version}</span>" if safe_version else ""
    st.markdown(
        f"""
        <div class='page-hero'>
            <div class='page-hero-content'>
                <div class='eyebrow'>🌱 Sustainability · Compliance Platform</div>
                <div class='headline'>{safe_title}</div>
                <div class='subline'>
                    <span class='tenant-pill'>🏢 {safe_tenant}</span>
                    {version_badge_html}
                </div>
            </div>
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
    st.markdown(f"<div class='tenant-mini'><span class='tenant-dot'></span><div><b>{int(n_docs)} documenti attivi</b><small>Archivio documentale</small></div></div>", unsafe_allow_html=True)


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
