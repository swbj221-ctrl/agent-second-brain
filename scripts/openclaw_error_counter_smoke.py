"""Smoke checks for in-memory bridge error counters (runtime tracker)."""

from __future__ import annotations

import json

from d_brain.integrations.openclaw_bridge import (
    _record_runtime_error_for_test,
    get_runtime_observability_snapshot,
)


def main() -> int:
    before = get_runtime_observability_snapshot()
    before_total = sum((before.get("error_counts_by_type") or {}).values())

    _record_runtime_error_for_test("smoke_handler", "fake_error")
    _record_runtime_error_for_test("smoke_handler", "fake_error")
    _record_runtime_error_for_test("another_handler", "another_error")

    after = get_runtime_observability_snapshot()
    after_counts = after.get("error_counts_by_type") or {}
    after_total = sum(after_counts.values())
    recent = after.get("recent_errors") or []

    ok = (
        after_total >= before_total + 3
        and int(after_counts.get("fake_error", 0)) >= 2
        and int(after_counts.get("another_error", 0)) >= 1
        and len(recent) >= 1
        and bool(after.get("last_error_at"))
    )
    print(json.dumps({"case": "error_counter_tracker", "ok": ok, "before_total": before_total, "after_total": after_total, "counts": after_counts, "last_error_at": after.get("last_error_at")}, ensure_ascii=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

