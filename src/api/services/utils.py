"""Utility helpers shared across API services."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional


def normalize_statement_key(value: str) -> str:
    cleaned = value.upper().replace("&", "AND")
    for token in [
        "CONSOLIDATED",
        "CONDENSED",
        "UNAUDITED",
        "INTERIM",
        "COMBINED",
        "SUMMARY",
    ]:
        cleaned = cleaned.replace(token, "")
    if "(" in cleaned:
        cleaned = cleaned.split("(", 1)[0]
    cleaned = cleaned.rstrip("0123456789")
    cleaned = cleaned.replace("STATEMENTS OF", "STATEMENT OF")
    cleaned = cleaned.replace("STATEMENTS", "STATEMENT")
    cleaned = cleaned.replace("  ", " ")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip(" -_")


def normalize_date_bounds(
    start_date: Optional[date],
    end_date: Optional[date],
) -> tuple[Optional[datetime], Optional[datetime]]:
    end = end_date or date.today()
    start_dt = datetime.combine(start_date, time.min) if start_date else None
    end_dt = datetime.combine(end, time.max)
    if start_dt and start_dt > end_dt:
        raise ValueError("startDate must be before endDate")
    return start_dt, end_dt


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
