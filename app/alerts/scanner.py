import json
from dataclasses import dataclass
from datetime import date
from typing import Dict, Iterable, List, Optional, Any
from app.config import ALERT_MAX_OVERDUE_DAYS

OVERDUE = -1


@dataclass(frozen=True)
class Alert:
    deadline_id: str
    description: str
    due_date: str
    days_left: int
    threshold: int          # -1 = منقضی شده
    module_id: str
    source: str


def classify(days_left: int, thresholds: Iterable[int]) -> Optional[int]:
    """تعیین دقیق‌ترین آستانه قطع‌شده."""
    if days_left < 0:
        return OVERDUE
    crossed = [t for t in thresholds if days_left <= t]
    return min(crossed) if crossed else None


def scan_deadlines(
    deadlines: List[Dict[str, Any]],
    today: Optional[date] = None,
    max_overdue_days: int = ALERT_MAX_OVERDUE_DAYS
) -> List[Alert]:
    """اسکن سررسیدها و تولید لیست هشدارهای فعال به ترتیب اولویت زمانی."""
    today = today or date.today()
    alerts = []

    for d in deadlines:
        try:
            due = date.fromisoformat(d["due_date"])
        except (TypeError, ValueError):
            continue
        days_left = (due - today).days

        if days_left < -max_overdue_days:
            continue

        thresholds = json.loads(d["thresholds"]) if isinstance(d["thresholds"], str) else d["thresholds"]
        t = classify(days_left, thresholds)
        if t is None:
            continue

        src = f"{d.get('source_document') or '-'} p.{d.get('source_page') or '-'}"
        alerts.append(Alert(
            deadline_id=d["id"],
            description=d["description"],
            due_date=d["due_date"],
            days_left=days_left,
            threshold=t,
            module_id=d["module_id"],
            source=src
        ))

    return sorted(alerts, key=lambda a: a.days_left)