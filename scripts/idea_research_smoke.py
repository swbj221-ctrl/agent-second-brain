"""Stage 10 Idea Research smoke test."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


ensure_src_on_path()

import sqlite3  # noqa: E402

from d_brain.config import get_settings  # noqa: E402
from d_brain.sidecar.dispatcher import handle_request  # noqa: E402


def make_request(action: str, payload: dict | None) -> dict:
    return handle_request(
        {
            "request_id": f"stage10-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage10-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_stage10_smoke() -> None:
    job_response = assert_ok(
        make_request(
            "idea_research_job_create",
            {
                "title": "Remote team productivity toolkit",
                "status": "active",
                "notes": "First-pass research topic.",
            },
        ),
        "idea_research_job_create",
    )
    job_id = job_response["data"]["job_id"]

    list_response = assert_ok(
        make_request("idea_research_job_list", {"limit": 5}),
        "idea_research_job_list",
    )
    jobs = list_response["data"]["jobs"]
    if not jobs:
        raise AssertionError("idea_research_job_list returned zero jobs")

    run_response = assert_ok(
        make_request(
            "idea_research_run_start",
            {
                "job_id": job_id,
                "finding_types": ["market", "user", "competitor"],
                "summary_text": "Manual run for smoke test.",
            },
        ),
        "idea_research_run_start",
    )
    run_id = run_response["data"]["run"]["id"]
    report_id = run_response["data"]["report"]["id"]
    findings = run_response["data"]["findings"]
    if len(findings) < 3:
        raise AssertionError("idea_research_run_start returned too few findings")

    run_get = assert_ok(
        make_request("idea_research_run_get", {"run_id": run_id}),
        "idea_research_run_get",
    )["data"]
    report_get = assert_ok(
        make_request("idea_research_report_get", {"report_id": report_id}),
        "idea_research_report_get",
    )["data"]

    if run_get["run"]["id"] != run_id:
        raise AssertionError("idea_research_run_get returned wrong run")
    if report_get["id"] != report_id:
        raise AssertionError("idea_research_report_get returned wrong report")

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        job_count = conn.execute(
            "SELECT COUNT(*) FROM idea_research_jobs;"
        ).fetchone()[0]
        run_count = conn.execute(
            "SELECT COUNT(*) FROM idea_research_runs;"
        ).fetchone()[0]
        finding_count = conn.execute(
            "SELECT COUNT(*) FROM idea_research_findings;"
        ).fetchone()[0]
        report_count = conn.execute(
            "SELECT COUNT(*) FROM idea_research_reports;"
        ).fetchone()[0]
        row = conn.execute(
            "SELECT run_id FROM idea_research_reports WHERE id = ?;",
            (report_id,),
        ).fetchone()

    if job_count < 1:
        raise AssertionError("idea_research_jobs table is empty")
    if run_count < 1:
        raise AssertionError("idea_research_runs table is empty")
    if finding_count < 1:
        raise AssertionError("idea_research_findings table is empty")
    if report_count < 1:
        raise AssertionError("idea_research_reports table is empty")
    if not row or int(row[0]) != run_id:
        raise AssertionError("idea_research_reports run link missing")

    print("stage10_idea_research_smoke_ok")
    print(f"job_id={job_id}")
    print(f"run_id={run_id}")
    print(f"report_id={report_id}")
    print(f"findings_count={len(findings)}")


if __name__ == "__main__":
    run_stage10_smoke()
