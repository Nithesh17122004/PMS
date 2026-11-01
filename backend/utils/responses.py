from __future__ import annotations

import math
from datetime import date, datetime, time
from decimal import Decimal

from flask import jsonify


def _json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def ok(data=None, meta=None, status=200):
    payload = {"ok": True, "data": _json_safe(data)}
    if meta is not None:
        payload["meta"] = _json_safe(meta)
    return jsonify(payload), status


def fail(code: str, message: str, status=400, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = _json_safe(details)
    return jsonify({"ok": False, "error": error}), status


def pagination_meta(total: int, page: int, per_page: int) -> dict:
    pages = max(1, math.ceil(total / per_page)) if per_page else 1
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


def parse_pagination(args, default_per_page=25, max_per_page=100):
    try:
        page = max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(args.get("per_page", default_per_page))
    except (TypeError, ValueError):
        per_page = default_per_page
    per_page = min(max(per_page, 1), max_per_page)
    return page, per_page
