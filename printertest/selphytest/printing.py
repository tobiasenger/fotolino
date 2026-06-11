"""Job submission and monitoring.

A job is only counted as a success when CUPS reports IPP state 9 (completed).
Jobs that sit in pending/processing past the timeout are classified as STUCK —
that is exactly the "Waiting for printer to become available" failure mode.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from . import JOB_STATES, PRINTER_STATES, cups_module

log = logging.getLogger("selphytest.printing")

FINAL_STATES = {7, 8, 9}  # canceled, aborted, completed


@dataclass
class JobOutcome:
    job_id: int | None
    options: dict[str, str]
    title: str
    file: str
    submitted_at: str = ""
    duration_s: float = 0.0
    final_state: int | None = None
    final_state_name: str = "not-submitted"
    success: bool = False
    stuck: bool = False
    error: str = ""
    history: list[dict] = field(default_factory=list)
    printer_messages: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.error and self.job_id is None:
            return f"SUBMIT FAILED: {self.error}"
        verdict = "SUCCESS" if self.success else ("STUCK" if self.stuck else "FAILED")
        msg = f"job {self.job_id}: {verdict} (state={self.final_state_name}, {self.duration_s:.0f}s)"
        if self.printer_messages:
            msg += f" — printer said: {self.printer_messages[-1]!r}"
        return msg

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "title": self.title,
            "file": self.file,
            "options": self.options,
            "submitted_at": self.submitted_at,
            "duration_s": round(self.duration_s, 1),
            "final_state": self.final_state,
            "final_state_name": self.final_state_name,
            "success": self.success,
            "stuck": self.stuck,
            "error": self.error,
            "printer_messages": self.printer_messages,
            "history": self.history,
        }


def _job_attrs(conn, job_id: int) -> dict:
    cups = cups_module()
    try:
        return conn.getJobAttributes(job_id)
    except cups.IPPError as exc:
        log.debug("getJobAttributes(%s) failed: %s", job_id, exc)
        return {}


def _printer_message(conn, printer: str) -> tuple[str, int | None]:
    try:
        attrs = conn.getPrinterAttributes(
            printer,
            requested_attributes=[
                "printer-state",
                "printer-state-message",
                "printer-state-reasons",
            ],
        )
        return attrs.get("printer-state-message", ""), attrs.get("printer-state")
    except Exception as exc:
        log.debug("printer attrs poll failed: %s", exc)
        return "", None


def submit_and_wait(
    conn,
    printer: str,
    filepath: str,
    title: str,
    options: dict[str, str],
    timeout: float = 180.0,
    poll: float = 2.0,
    wait: bool = True,
) -> JobOutcome:
    """Submit a file and watch the job until it finishes, fails or times out."""
    cups = cups_module()
    str_options = {str(k): str(v) for k, v in options.items()}
    outcome = JobOutcome(
        job_id=None, options=str_options, title=title, file=str(filepath)
    )
    log.info("Submitting %s to '%s' with options %s", filepath, printer, str_options)
    outcome.submitted_at = datetime.now().isoformat(timespec="seconds")
    start = time.monotonic()
    try:
        outcome.job_id = conn.printFile(printer, str(filepath), title, str_options)
    except cups.IPPError as exc:
        outcome.error = f"IPP error on submit: {exc}"
        outcome.final_state_name = "submit-failed"
        log.error(outcome.error)
        return outcome
    except OSError as exc:
        outcome.error = f"submit failed: {exc}"
        outcome.final_state_name = "submit-failed"
        log.error(outcome.error)
        return outcome

    log.info("CUPS accepted job id %s", outcome.job_id)
    if not wait:
        outcome.final_state_name = "submitted (not watched)"
        return outcome

    last_logged = None
    while True:
        elapsed = time.monotonic() - start
        attrs = _job_attrs(conn, outcome.job_id)
        state = attrs.get("job-state")
        state_name = JOB_STATES.get(state, str(state))
        reasons = attrs.get("job-state-reasons", "")
        if isinstance(reasons, list):
            reasons = ",".join(reasons)
        job_msg = attrs.get("job-printer-state-message", "")
        prn_msg, prn_state = _printer_message(conn, printer)

        snapshot = (state, reasons, job_msg, prn_msg)
        if snapshot != last_logged:
            last_logged = snapshot
            outcome.history.append(
                {
                    "t": round(elapsed, 1),
                    "job_state": state_name,
                    "job_state_reasons": reasons,
                    "printer_state": PRINTER_STATES.get(prn_state, str(prn_state)),
                    "printer_message": prn_msg or job_msg,
                }
            )
            log.info(
                "  [%5.1fs] job=%s reasons=%s printer=%s msg=%s",
                elapsed,
                state_name,
                reasons or "-",
                PRINTER_STATES.get(prn_state, "?"),
                (prn_msg or job_msg or "-"),
            )
        for message in (job_msg, prn_msg):
            if message and message not in outcome.printer_messages:
                outcome.printer_messages.append(message)

        if state in FINAL_STATES:
            outcome.final_state = state
            outcome.final_state_name = state_name
            outcome.success = state == 9
            outcome.duration_s = elapsed
            log.info("Job %s finished: %s", outcome.job_id, outcome.summary())
            return outcome

        if elapsed >= timeout:
            outcome.final_state = state
            outcome.final_state_name = f"{state_name} (timeout after {timeout:.0f}s)"
            outcome.stuck = True
            outcome.duration_s = elapsed
            log.warning("Job %s STUCK: %s", outcome.job_id, outcome.summary())
            return outcome

        time.sleep(poll)


def cancel_job(conn, job_id: int, purge: bool = False) -> bool:
    cups = cups_module()
    try:
        conn.cancelJob(job_id, purge_job=purge)
        log.info("Canceled job %s%s", job_id, " (purged)" if purge else "")
        return True
    except cups.IPPError as exc:
        log.error("Cannot cancel job %s: %s", job_id, exc)
        return False


def cancel_all(conn, printer: str, job_ids: list[int], purge: bool = False) -> int:
    """Cancel the given jobs one by one; returns number canceled."""
    count = 0
    for job_id in job_ids:
        if cancel_job(conn, job_id, purge=purge):
            count += 1
    return count
