"""Column-type detection and cell formatting for data tables (shared by
markdown tables and CSV/XLSX rendering)."""
from __future__ import annotations

import re


_RE_SCI  = re.compile(r'^[+-]?\d+\.?\d*[eE][+-]?\d+$')
_RE_BARE_NUM = re.compile(r'^[+-]?[\d,]+(\.\d+)?$')
_RE_CURRENCY = re.compile(r'^[$€£¥][+-]?[\d,]+(\.\d+)?([eE][+-]?\d+)?$')
_RE_PCT  = re.compile(r'^[+-]?\d+\.?\d*%$')
_RE_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _detect_col_types(rows: list[list[str]], ncols: int) -> list[str]:
    """Infer column types from a majority of non-empty values."""
    types: list[str] = []
    for j in range(ncols):
        vals = [row[j].strip() for row in rows if j < len(row) and row[j].strip()]
        if not vals:
            types.append("text")
            continue
        hits: dict[str, int] = {"sci": 0, "num": 0, "currency": 0, "pct": 0, "date": 0}
        for v in vals:
            if _RE_SCI.match(v):         hits["sci"] += 1
            elif _RE_CURRENCY.match(v):  hits["currency"] += 1
            elif _RE_PCT.match(v):       hits["pct"] += 1
            elif _RE_DATE.match(v):      hits["date"] += 1
            elif _RE_BARE_NUM.match(v.replace(",", "")): hits["num"] += 1
        majority = len(vals) * 0.6
        if hits["sci"] >= majority:       types.append("sci")
        elif hits["currency"] >= majority: types.append("currency")
        elif hits["pct"] >= majority:     types.append("pct")
        elif hits["date"] >= majority:    types.append("date")
        elif (hits["num"] + hits["sci"]) >= majority: types.append("num")
        else:                             types.append("text")
    return types


def _fmt_cell(v: str, col_type: str) -> str:
    """Format a table cell value by detected column type."""
    v = v.strip()
    if not v or v in ("-", "—", "N/A", "n/a"):
        return v
    if col_type == "text":
        return v
    if col_type in ("sci", "num"):
        clean = v.replace(",", "")
        try:
            f = float(clean)
            if "e" in clean.lower() or "E" in clean:
                # scientific notation → comma-formatted
                return f"{int(f):,}" if f == int(f) else f"{f:,.4g}"
            if "." in clean:
                dec_places = len(clean.split(".")[-1])
                return f"{f:,.{min(dec_places, 6)}f}"
            return f"{int(f):,}"
        except ValueError:
            return v
    if col_type == "currency":
        sym = v[0]
        rest = v[1:].replace(",", "")
        try:
            f = float(rest)
            return f"{sym}{f:,.2f}"
        except ValueError:
            return v
    # pct, date — already human-readable
    return v


