import re
from datetime import datetime
from typing import Optional, Tuple, List


DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d %b %Y",
    "%d %B %Y",
]


def parse_date(value: str) -> Optional[datetime]:
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def find_first_match(patterns: List[str], text: str, flags=0) -> Optional[re.Match]:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match
    return None


def parse_float_safe(raw: str) -> Optional[float]:
    if raw is None:
        return None
    raw = raw.replace(",", "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def clean_text(text: str) -> str:
    """Normalize whitespace a bit."""
    # unify line endings and multiple spaces
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
