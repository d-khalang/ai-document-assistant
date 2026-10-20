import re
import unicodedata
from datetime import datetime
from typing import Optional

SUPPORTED_MONTHS = {
    # ایتالیایی
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
    "gen": 1, "feb": 2, "mar": 3, "apr": 4, "mag": 5, "giu": 6,
    "lug": 7, "ago": 8, "set": 9, "ott": 10, "nov": 11, "dic": 12,
    # انگلیسی
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
}


def normalize_date(raw_date_str: Optional[str]) -> Optional[str]:
    """
    نرمال‌سازی تاریخ‌های گوناگون (ایتالیایی، انگلیسی، اسلش، نقطه و خط فاصله) به فرمت YYYY-MM-DD.
    """
    if not raw_date_str or not isinstance(raw_date_str, str):
        return None

    cleaned = raw_date_str.strip().lower()
    cleaned = re.sub(r"[,\.]", " ", cleaned)
    cleaned = " ".join(cleaned.split())

    # تاریخ‌های حروفی مانند '31 luglio 2026' یا '15 October 2026'
    for m_name, m_num in SUPPORTED_MONTHS.items():
        if m_name in cleaned:
            pattern = rf"(\d{{1,2}})\s+{m_name}\s+(\d{{4}})"
            match = re.search(pattern, cleaned)
            if match:
                day, year = int(match.group(1)), int(match.group(2))
                return f"{year:04d}-{m_num:02d}-{day:02d}"

    raw_norm = raw_date_str.strip().replace(".", "/").replace("-", "/")

    # DD/MM/YYYY
    match_dmy = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw_norm)
    if match_dmy:
        d, m, y = int(match_dmy.group(1)), int(match_dmy.group(2)), int(match_dmy.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}"

    # YYYY/MM/DD
    match_ymd = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", raw_norm)
    if match_ymd:
        y, m, d = int(match_ymd.group(1)), int(match_ymd.group(2)), int(match_ymd.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}"

    return raw_date_str.strip()


def normalize_number(raw_num_str: Optional[str]) -> Optional[float]:
    """
    نرمال‌سازی دقیق اعداد با فرمت ایتالیایی و بین‌المللی به عدد float استاندارد.
    """
    if raw_num_str is None:
        return None

    if isinstance(raw_num_str, (int, float)):
        return float(raw_num_str)

    val = str(raw_num_str).strip()
    num_match = re.search(r"[-+]?[0-9]+(?:[\.\,][0-9]+)*", val)
    if not num_match:
        return None

    clean_str = num_match.group(0)

    # حالت ۱: هر دو کاراکتر نقطه و ویرگول وجود دارند (مثل 1.250,50 یا 1,250.50)
    if "." in clean_str and "," in clean_str:
        if clean_str.rfind(",") > clean_str.rfind("."):
            clean_str = clean_str.replace(".", "").replace(",", ".")
        else:
            clean_str = clean_str.replace(",", "")
    # حالت ۲: فقط ویرگول وجود دارد (اعشار ایتالیایی مثل 250,00 -> 250.00)
    elif "," in clean_str:
        clean_str = clean_str.replace(",", ".")
    # حالت ۳: فقط نقطه وجود دارد (تشخیص هوشمند هزارگان ایتالیایی مثل 2.000 در برابر اعشار 12.5)
    elif "." in clean_str:
        if re.match(r"^\d{1,3}(\.\d{3})+$", clean_str):
            clean_str = clean_str.replace(".", "")

    try:
        return float(clean_str)
    except ValueError:
        return None


def normalize_plate(plate_str: Optional[str]) -> Optional[str]:
    """یکسان‌سازی پلاک خودرو (حذف فاصله‌ها و بزرگ‌نویسی حروف)."""
    if not plate_str:
        return None
    return re.sub(r"[\s\-_]", "", str(plate_str)).upper()


def normalize_key(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[\s_\-\./]+", " ", s).strip()


def keyword_matches(term: str, text: str) -> bool:
    t = normalize_key(term)
    prefix = t.endswith("*")
    body = re.escape(t.rstrip("*").strip())
    return re.search(r"(?<![a-z0-9])" + body + ("" if prefix else r"(?![a-z0-9])"),
                     normalize_key(text)) is not None
