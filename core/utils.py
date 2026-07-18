"""Tiện ích dùng chung: chuẩn hoá ngày tháng, format tiền Việt."""
from __future__ import annotations
import datetime as dt


def to_date_str(d) -> str:
    """Chuẩn hoá 1 giá trị ngày (str | date | datetime | pandas.Timestamp) về 'YYYY-MM-DD'."""
    if isinstance(d, str):
        return d[:10]
    if isinstance(d, dt.datetime):
        return d.date().isoformat()
    if isinstance(d, dt.date):
        return d.isoformat()
    return str(d)[:10]


def fmt_vnd(amount: float) -> str:
    """1234567 -> '1.234.567đ'"""
    sign = "-" if amount < 0 else ""
    n = int(round(abs(amount)))
    s = f"{n:,}".replace(",", ".")
    return f"{sign}{s}đ"


def fmt_pct(x: float, digits: int = 0) -> str:
    return f"{x * 100:.{digits}f}%"
