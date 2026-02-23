"""Stage 9 Health MVP smoke test."""

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
            "request_id": f"stage9-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage9-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_stage9_smoke() -> None:
    ingest_response = assert_ok(
        make_request(
            "ingest",
            {
                "source_type": "manual",
                "content_type": "text",
                "summary_format": "plain",
                "content": "Lab report: basic panel results attached.",
            },
        ),
        "ingest",
    )
    artifact_id = ingest_response["data"]["artifact_id"]

    record_response = assert_ok(
        make_request(
            "health_record_add",
            {
                "title": "General check-in",
                "record_type": "general",
                "notes": "Short note only.",
                "occurred_at": "2026-02-23T09:00:00+00:00",
            },
        ),
        "health_record_add",
    )

    medication_response = assert_ok(
        make_request(
            "health_medication_add",
            {
                "name": "Vitamin D",
                "dosage": "1000 IU",
                "schedule": "daily",
                "started_at": "2026-02-01",
            },
        ),
        "health_medication_add",
    )

    treatment_response = assert_ok(
        make_request(
            "health_treatment_add",
            {
                "name": "Physical therapy",
                "description": "Weekly session",
                "started_at": "2026-02-10",
            },
        ),
        "health_treatment_add",
    )

    observation_response = assert_ok(
        make_request(
            "health_observation_add",
            {
                "observation_type": "blood_pressure",
                "value": "120/80",
                "unit": "mmHg",
                "observed_at": "2026-02-23T08:30:00+00:00",
            },
        ),
        "health_observation_add",
    )

    lab_report_response = assert_ok(
        make_request(
            "health_lab_report_add",
            {
                "artifact_id": artifact_id,
                "title": "Basic panel report",
                "report_date": "2026-02-22",
                "notes": "Linked to existing artifact.",
            },
        ),
        "health_lab_report_add",
    )

    records_list = assert_ok(
        make_request("health_record_list", {"limit": 5}),
        "health_record_list",
    )["data"]["records"]
    medications_list = assert_ok(
        make_request("health_medication_list", {"limit": 5}),
        "health_medication_list",
    )["data"]["medications"]
    treatments_list = assert_ok(
        make_request("health_treatment_list", {"limit": 5}),
        "health_treatment_list",
    )["data"]["treatments"]
    observations_list = assert_ok(
        make_request("health_observation_list", {"limit": 5}),
        "health_observation_list",
    )["data"]["observations"]
    lab_reports_list = assert_ok(
        make_request("health_lab_report_list", {"limit": 5}),
        "health_lab_report_list",
    )["data"]["lab_reports"]

    if not records_list:
        raise AssertionError("health_record_list returned zero records")
    if not medications_list:
        raise AssertionError("health_medication_list returned zero medications")
    if not treatments_list:
        raise AssertionError("health_treatment_list returned zero treatments")
    if not observations_list:
        raise AssertionError("health_observation_list returned zero observations")
    if not lab_reports_list:
        raise AssertionError("health_lab_report_list returned zero lab reports")

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        record_count = conn.execute("SELECT COUNT(*) FROM health_records;").fetchone()[0]
        medication_count = conn.execute(
            "SELECT COUNT(*) FROM health_medications;"
        ).fetchone()[0]
        treatment_count = conn.execute(
            "SELECT COUNT(*) FROM health_treatments;"
        ).fetchone()[0]
        observation_count = conn.execute(
            "SELECT COUNT(*) FROM health_observations;"
        ).fetchone()[0]
        lab_report_row = conn.execute(
            "SELECT artifact_id FROM health_lab_reports WHERE id = ?;",
            (lab_report_response["data"]["lab_report_id"],),
        ).fetchone()

    if record_count < 1:
        raise AssertionError("health_records table is empty")
    if medication_count < 1:
        raise AssertionError("health_medications table is empty")
    if treatment_count < 1:
        raise AssertionError("health_treatments table is empty")
    if observation_count < 1:
        raise AssertionError("health_observations table is empty")
    if not lab_report_row or int(lab_report_row[0]) != artifact_id:
        raise AssertionError("health_lab_reports artifact link missing")

    print("stage9_health_smoke_ok")
    print(f"artifact_id={artifact_id}")
    print(f"record_id={record_response['data']['record_id']}")
    print(f"medication_id={medication_response['data']['medication_id']}")
    print(f"treatment_id={treatment_response['data']['treatment_id']}")
    print(f"observation_id={observation_response['data']['observation_id']}")
    print(f"lab_report_id={lab_report_response['data']['lab_report_id']}")
    print(f"records_listed={len(records_list)}")
    print(f"medications_listed={len(medications_list)}")
    print(f"treatments_listed={len(treatments_list)}")
    print(f"observations_listed={len(observations_list)}")
    print(f"lab_reports_listed={len(lab_reports_list)}")


if __name__ == "__main__":
    run_stage9_smoke()
