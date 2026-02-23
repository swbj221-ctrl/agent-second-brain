"""Stage 18 Projects & Tasks smoke test."""

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
            "request_id": f"stage18-{action}",
            "user_id": "smoke-user",
            "action": action,
            "payload": payload or {},
            "metadata": {"source": "stage18-smoke"},
        }
    )


def assert_ok(response: dict, label: str) -> dict:
    if response.get("status") != "ok":
        raise AssertionError(f"{label} failed: {json.dumps(response, indent=2)}")
    return response


def run_stage18_smoke() -> None:
    project_a = assert_ok(
        make_request("project_create", {"name": "Stage 18 Smoke Project A"}),
        "project_create",
    )
    project_a_id = project_a["data"]["project_id"]

    project_b = assert_ok(
        make_request("project_create", {"name": "Stage 18 Smoke Project B"}),
        "project_create",
    )
    project_b_id = project_b["data"]["project_id"]

    task_one = assert_ok(
        make_request(
            "task_create",
            {
                "project_id": project_a_id,
                "title": "First smoke task",
                "status": "open",
                "source_type": "smoke",
                "source_ref": "stage18",
            },
        ),
        "task_create_one",
    )
    task_one_id = task_one["data"]["task_id"]

    task_two = assert_ok(
        make_request(
            "task_create",
            {
                "project_id": project_a_id,
                "title": "Second smoke task",
                "status": "open",
                "due_at": "2026-03-01",
                "source_type": "smoke",
                "source_ref": "stage18",
            },
        ),
        "task_create_two",
    )
    task_two_id = task_two["data"]["task_id"]

    list_response = assert_ok(
        make_request(
            "task_list",
            {"project_id": project_a_id, "limit": 10, "offset": 0},
        ),
        "task_list",
    )
    tasks = list_response["data"]["tasks"]
    if len(tasks) < 2:
        raise AssertionError("task_list returned too few tasks")

    assert_ok(
        make_request(
            "task_update_status",
            {"task_id": task_one_id, "status": "done"},
        ),
        "task_update_status",
    )

    assert_ok(
        make_request(
            "task_update_project",
            {"task_id": task_two_id, "project_id": project_b_id},
        ),
        "task_update_project",
    )

    note_response = assert_ok(
        make_request(
            "task_note_add",
            {"task_id": task_one_id, "text": "Smoke note for task one."},
        ),
        "task_note_add",
    )
    note_id = note_response["data"]["note_id"]

    settings = get_settings()
    with sqlite3.connect(settings.db_path) as conn:
        project_count = conn.execute("SELECT COUNT(*) FROM projects;").fetchone()[0]
        task_count = conn.execute("SELECT COUNT(*) FROM tasks;").fetchone()[0]
        note_count = conn.execute(
            "SELECT COUNT(*) FROM notes WHERE source_type = 'task';"
        ).fetchone()[0]
        task_two_row = conn.execute(
            "SELECT project_id, due_at FROM tasks WHERE id = ?;",
            (task_two_id,),
        ).fetchone()
        task_one_status = conn.execute(
            "SELECT status FROM tasks WHERE id = ?;",
            (task_one_id,),
        ).fetchone()

    if project_count < 2:
        raise AssertionError("projects table has too few rows")
    if task_count < 2:
        raise AssertionError("tasks table has too few rows")
    if note_count < 1:
        raise AssertionError("task notes were not stored")
    if not task_two_row or int(task_two_row[0]) != project_b_id:
        raise AssertionError("task_update_project did not move task")
    if task_two_row[1] != "2026-03-01":
        raise AssertionError("task due_at was not stored correctly")
    if not task_one_status or task_one_status[0] != "done":
        raise AssertionError("task_update_status did not set done")

    print("stage18_projects_tasks_smoke_ok")
    print(f"project_a_id={project_a_id}")
    print(f"project_b_id={project_b_id}")
    print(f"task_one_id={task_one_id}")
    print(f"task_two_id={task_two_id}")
    print(f"note_id={note_id}")


if __name__ == "__main__":
    run_stage18_smoke()
