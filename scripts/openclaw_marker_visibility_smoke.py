"""Smoke test for marker visibility in openclaw logs --json --plain style captures."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from d_brain.integrations.marker_visibility import emit_observable_marker


PATTERNS = [
    "openclaw_voice_dispatch_path_select",
    "openclaw_voice_dispatch_wrapper_trace",
    "openclaw_voice_dispatch_path_result",
    "telegram_voice_pipeline",
    "stt_multipass_selected",
    "openclaw_adapter_outgoing_boundary",
    "outgoing_text_source",
    "chat_response_source",
]


def _wrap_openclaw_log_line(marker_line: str) -> str:
    return json.dumps(
        {
            "type": "log",
            "time": "2026-02-26T00:00:00.000Z",
            "level": "info",
            "message": marker_line,
            "raw": json.dumps({"0": marker_line}, ensure_ascii=True),
        },
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _emit_line(marker: dict[str, object]) -> str:
    line = emit_observable_marker(marker, logger_obj=None, stream_fallback=False)
    if not line:
        raise RuntimeError("marker_emit_failed")
    return line


def main() -> int:
    rid = "smoke-marker-001"
    marker_lines = [
        _emit_line(
            {
                "event": "openclaw_voice_dispatch_path_select",
                "traceStage": "adapter.pre_bridge",
                "requestId": rid,
                "request_id": rid,
                "selectedPath": "d_brain_openclaw_bridge",
            }
        ),
        _emit_line(
            {
                "event": "openclaw_voice_dispatch_wrapper_trace",
                "traceStage": "wrapper.adapter_dispatch",
                "requestId": rid,
                "request_id": rid,
                "embeddedTranscriptDecision": "suppress_embedded_transcript",
            }
        ),
        _emit_line(
            {
                "event": "openclaw_voice_dispatch_path_result",
                "traceStage": "adapter.post_bridge",
                "requestId": rid,
                "request_id": rid,
                "outgoing_text_source": "bridge_stt",
            }
        ),
        _emit_line(
            {
                "event": "telegram_voice_pipeline",
                "stage": "stt_multipass_selected",
                "requestId": rid,
                "request_id": rid,
                "selectedLang": "ru",
            }
        ),
        _emit_line(
            {
                "event": "openclaw_adapter_outgoing_boundary",
                "traceStage": "adapter.respond.final",
                "requestId": rid,
                "request_id": rid,
                "chat_response_source": "bridge_stt",
                "outgoing_text_source": "bridge_stt",
            }
        ),
    ]

    with tempfile.TemporaryDirectory(prefix="marker-visibility-smoke-") as tmp:
        out = Path(tmp) / "capture.log"
        rendered = []
        for marker_line in marker_lines:
            rendered.append(marker_line)
            rendered.append(_wrap_openclaw_log_line(marker_line))
        out.write_text("\n".join(rendered) + "\n", encoding="utf-8")

        content = out.read_text(encoding="utf-8", errors="replace").splitlines()
        failures = 0
        for pat in PATTERNS:
            count = sum(1 for line in content if pat in line)
            ok = count > 0
            print(f"pattern={pat} count={count} ok={ok}")
            if not ok:
                failures += 1

        print(f"capture={out}")
        print(f"ok={failures == 0}")
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
