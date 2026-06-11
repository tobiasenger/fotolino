"""Matrix report writing (JSON + Markdown) into printertest/reports/."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from .logutil import REPORT_DIR

log = logging.getLogger("selphytest.report")


class MatrixReport:
    """Collects per-combination results and persists them incrementally,
    so data survives an aborted run."""

    def __init__(self, printer: str, context: dict):
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.json_path = REPORT_DIR / f"matrix_{stamp}.json"
        self.md_path = REPORT_DIR / f"matrix_{stamp}.md"
        self.data = {
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "printer": printer,
            "context": context,
            "results": [],
        }

    def add(self, entry: dict) -> None:
        self.data["results"].append(entry)
        self.flush()

    def flush(self) -> None:
        self.json_path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def finalize(self) -> None:
        self.flush()
        self.md_path.write_text(self._markdown(), encoding="utf-8")
        log.info("Report written: %s", self.json_path)
        log.info("Report written: %s", self.md_path)

    def _markdown(self) -> str:
        lines = [
            "# SELPHY CP1500 print matrix report",
            "",
            f"- Created: {self.data['created']}",
            f"- Printer queue: `{self.data['printer']}`",
        ]
        for key, value in self.data["context"].items():
            lines.append(f"- {key}: `{value}`")
        lines += [
            "",
            "| # | Label | Options | Job | Result | State | Time | Printer message |",
            "|---|-------|---------|-----|--------|-------|------|-----------------|",
        ]
        successes = []
        for entry in self.data["results"]:
            outcome = entry.get("outcome", {})
            options = entry.get("options", {})
            opts_str = " ".join(f"{k}={v}" for k, v in options.items()) or "(defaults)"
            if entry.get("skipped"):
                result = "SKIPPED"
                state = entry.get("skip_reason", "")
                job = duration = message = ""
            else:
                success = outcome.get("success")
                stuck = outcome.get("stuck")
                result = "✅ OK" if success else ("⏳ STUCK" if stuck else "❌ FAIL")
                state = outcome.get("final_state_name", "")
                job = str(outcome.get("job_id") or "")
                duration = f"{outcome.get('duration_s', 0):.0f}s"
                messages = outcome.get("printer_messages") or []
                message = messages[-1] if messages else ""
                if success:
                    successes.append((entry["index"], opts_str))
            lines.append(
                f"| {entry['index']} | {entry.get('label','')} | `{opts_str}` "
                f"| {job} | {result} | {state} | {duration} | {message} |"
            )
        lines += ["", "## Working combinations", ""]
        if successes:
            for index, opts_str in successes:
                lines.append(f"- **#{index}**: `{opts_str}`")
        else:
            lines.append("- none — see job histories in the JSON report")
        lines += [
            "",
            f"Raw data incl. full job state history: `{self.json_path.name}`",
            "",
        ]
        return "\n".join(lines)
