"""Idea research helpers for Stage 10 first pass."""

from __future__ import annotations

from typing import Any

from .errors import SidecarError
from .store import SQLiteStore, utc_now

DEFAULT_FINDING_TYPES = ["market", "user", "competitor", "opportunity", "risk"]


def normalize_finding_types(finding_types: list[str] | None) -> list[str]:
    if not finding_types:
        return DEFAULT_FINDING_TYPES[:]
    cleaned: list[str] = []
    for raw in finding_types:
        if raw is None:
            continue
        value = str(raw).strip().lower()
        if not value:
            continue
        if value not in cleaned:
            cleaned.append(value)
    return cleaned or DEFAULT_FINDING_TYPES[:]


def build_report_text(topic: str, summary_text: str, findings: list[dict[str, Any]]) -> str:
    lines = [
        "Idea Research Report",
        f"Topic: {topic}",
        f"Run Summary: {summary_text}",
        "Findings:",
    ]
    for finding in findings:
        ftype = finding.get("finding_type") or "finding"
        title = finding.get("title") or "Untitled"
        summary = finding.get("summary_text") or "Summary pending."
        lines.append(f"- [{ftype}] {title}: {summary}")
    return "\n".join(lines)


def start_manual_research_run(
    store: SQLiteStore,
    job_id: int,
    finding_types: list[str] | None = None,
    summary_text: str | None = None,
) -> dict[str, Any]:
    job = store.get_idea_research_job(job_id)
    if job is None:
        raise SidecarError("not_found", f"Idea research job {job_id} not found.")

    run_summary = (summary_text or "").strip() or "Manual research run started."
    run_id = store.create_idea_research_run(
        job_id=job_id,
        status="started",
        stage="init",
        summary_text=run_summary,
    )

    findings_payload: list[dict[str, Any]] = []
    for ftype in normalize_finding_types(finding_types):
        title = f"{ftype.title()} insight"
        summary = "Placeholder finding summary."
        finding_id = store.create_idea_research_finding(
            run_id=run_id,
            finding_type=ftype,
            title=title,
            summary_text=summary,
            evidence_ref=None,
        )
        findings_payload.append(
            {
                "finding_id": finding_id,
                "run_id": run_id,
                "finding_type": ftype,
                "title": title,
                "summary_text": summary,
                "evidence_ref": None,
            }
        )

    store.update_idea_research_run(
        run_id=run_id,
        status="started",
        stage="placeholder_findings",
        summary_text=run_summary,
        completed_at=None,
    )

    report_text = build_report_text(job["title"], run_summary, findings_payload)
    report_id = store.create_idea_research_report(
        run_id=run_id,
        report_text=report_text,
        report_format="plain",
    )

    store.update_idea_research_run(
        run_id=run_id,
        status="completed",
        stage="report_assembled",
        summary_text="Manual research run completed.",
        completed_at=utc_now(),
    )

    run_payload = store.get_idea_research_run(run_id)
    report_payload = store.get_idea_research_report(report_id)

    return {
        "job": job,
        "run": run_payload,
        "findings": findings_payload,
        "report": report_payload,
    }


def get_research_run(store: SQLiteStore, run_id: int) -> dict[str, Any]:
    run = store.get_idea_research_run(run_id)
    if run is None:
        raise SidecarError("not_found", f"Idea research run {run_id} not found.")
    job = store.get_idea_research_job(run["job_id"])
    findings = store.list_idea_research_findings(run_id)
    report = store.get_idea_research_report_by_run(run_id)
    return {
        "job": job,
        "run": run,
        "findings": findings,
        "report": report,
    }


def get_research_report(
    store: SQLiteStore,
    report_id: int | None = None,
    run_id: int | None = None,
) -> dict[str, Any]:
    if report_id is not None:
        report = store.get_idea_research_report(report_id)
    elif run_id is not None:
        report = store.get_idea_research_report_by_run(run_id)
    else:
        report = None
    if report is None:
        raise SidecarError("not_found", "Idea research report not found.")
    return report
