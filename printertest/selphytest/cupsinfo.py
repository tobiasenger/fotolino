"""Runtime discovery of CUPS / Gutenprint / printer information.

Everything here is read-only and prefers values reported by the live system
(CUPS server, installed PPD, backends on disk) over hardcoded assumptions.
"""

from __future__ import annotations

import glob
import logging
import re
import shutil
import subprocess
import urllib.request

from . import (
    BAD_BACKEND_PREFIX,
    GOOD_BACKEND_PREFIX,
    PRINTER_STATES,
)

log = logging.getLogger("selphytest.cupsinfo")

# Attributes worth showing for the queue configuration
QUEUE_ATTRIBUTES = [
    "printer-state",
    "printer-state-message",
    "printer-state-reasons",
    "printer-is-accepting-jobs",
    "device-uri",
    "printer-make-and-model",
    "printer-info",
    "printer-location",
    "printer-is-shared",
    "media-default",
    "media-supported",
    "media-ready",
    "printer-resolution-supported",
    "printer-resolution-default",
    "print-scaling-supported",
    "print-scaling-default",
    "document-format-supported",
    "printer-error-policy",
    "printer-op-policy",
    "queued-job-count",
]


def _run(cmd: list[str]) -> str | None:
    """Run a command, return stripped stdout or None on any failure."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=False
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
        log.debug("command %s rc=%s stderr=%s", cmd, out.returncode, out.stderr.strip())
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("command %s failed: %s", cmd, exc)
    return None


def cups_server_version() -> str:
    """Determine the CUPS server version via several fallbacks."""
    # 1) cups-config (present when libcups2-dev is installed, as on this Pi)
    if shutil.which("cups-config"):
        version = _run(["cups-config", "--version"])
        if version:
            return f"{version} (cups-config)"
    # 2) HTTP "Server:" header of the local CUPS web interface
    try:
        req = urllib.request.Request("http://localhost:631/", method="HEAD")
        with urllib.request.urlopen(req, timeout=3) as resp:
            server = resp.headers.get("Server", "")
            match = re.search(r"CUPS/([\d.]+)", server)
            if match:
                return f"{match.group(1)} (http Server header)"
    except OSError as exc:
        log.debug("CUPS http probe failed: %s", exc)
    # 3) Debian package version
    pkg = _run(["dpkg-query", "-W", "-f=${Version}", "cups"])
    if pkg:
        return f"{pkg} (dpkg package)"
    return "unknown"


def gutenprint_version(ppd_nickname: str | None = None) -> str:
    """Determine the *active* Gutenprint version.

    The dpkg package version is misleading here (source install overrides it),
    so prefer gutenprint-config and the version embedded in the queue's PPD.
    """
    results = []
    for exe in ("gutenprint-config", "/usr/local/bin/gutenprint-config"):
        if shutil.which(exe) or exe.startswith("/"):
            version = _run([exe, "--version"])
            if version:
                results.append(f"{version} (gutenprint-config)")
                break
    if ppd_nickname:
        match = re.search(r"Gutenprint\s+v?([\d.]+)", ppd_nickname)
        if match:
            results.append(f"{match.group(1)} (queue PPD NickName)")
    pkg = _run(["dpkg-query", "-W", "-f=${Version}", "printer-driver-gutenprint"])
    if pkg:
        results.append(f"{pkg} (dpkg package — may differ from active source install)")
    return " / ".join(results) if results else "unknown"


def gutenprint_backends() -> list[str]:
    """Locate Gutenprint CUPS backends on disk (gutenprint53+usb is the important one)."""
    candidates = set()
    serverbin = _run(["cups-config", "--serverbin"]) if shutil.which("cups-config") else None
    dirs = {
        "/usr/lib/cups/backend",
        "/usr/local/lib/cups/backend",
    }
    if serverbin:
        dirs.add(f"{serverbin}/backend")
    for directory in dirs:
        candidates.update(glob.glob(f"{directory}/*gutenprint*"))
    return sorted(candidates)


def pick_printer(conn, requested: str | None = None) -> str:
    """Choose the printer queue to operate on.

    Order: exact requested name -> case-insensitive match -> name containing
    'selphy' or 'cp1500' -> CUPS default -> the only existing queue.
    """
    printers = conn.getPrinters()
    if not printers:
        raise SystemExit(
            "ERROR: no printer queues configured in CUPS.\n"
            "Create one first, e.g.:\n"
            '  sudo lpadmin -p SELPHY -E -v "gutenprint53+usb://..." '
            '-m "gutenprint.5.3://canon-cp1500/expert"'
        )
    if requested:
        if requested in printers:
            return requested
        for name in printers:
            if name.lower() == requested.lower():
                return name
        raise SystemExit(
            f"ERROR: printer '{requested}' not found. "
            f"Available: {', '.join(sorted(printers))}"
        )
    for name in printers:
        if "selphy" in name.lower() or "cp1500" in name.lower():
            log.debug("auto-selected printer %s (name match)", name)
            return name
    default = conn.getDefault()
    if default and default in printers:
        log.debug("auto-selected printer %s (CUPS default)", default)
        return default
    if len(printers) == 1:
        name = next(iter(printers))
        log.debug("auto-selected printer %s (only queue)", name)
        return name
    raise SystemExit(
        "ERROR: cannot decide which printer to use. "
        f"Pass -p/--printer. Available: {', '.join(sorted(printers))}"
    )


def state_reasons(attrs: dict) -> list[str]:
    """Normalize printer-state-reasons (CUPS returns str or list)."""
    reasons = attrs.get("printer-state-reasons", [])
    if isinstance(reasons, str):
        reasons = [reasons]
    return [r for r in reasons if r and r != "none"]


def queue_attributes(conn, printer: str) -> dict:
    try:
        return conn.getPrinterAttributes(
            printer, requested_attributes=QUEUE_ATTRIBUTES
        )
    except Exception as exc:  # cups.IPPError
        log.debug("requested_attributes query failed (%s), retrying without", exc)
        return conn.getPrinterAttributes(printer)


def readiness_problems(conn, printer: str) -> tuple[list[str], list[str]]:
    """Check whether the queue is ready to print.

    Returns (problems, warnings). Empty problems list == ready.
    """
    problems: list[str] = []
    warnings: list[str] = []
    printers = conn.getPrinters()
    if printer not in printers:
        return [f"queue '{printer}' does not exist in CUPS"], warnings
    info = printers[printer]

    state = info.get("printer-state")
    state_name = PRINTER_STATES.get(state, str(state))
    if state == 5:
        problems.append(
            f"queue is STOPPED (printer-state=5). Re-enable with: sudo cupsenable {printer}"
        )
    elif state == 4:
        warnings.append("queue is currently processing a job")

    if not info.get("printer-is-accepting-jobs", True):
        problems.append(
            f"queue is not accepting jobs. Fix with: sudo cupsaccept {printer}"
        )

    message = info.get("printer-state-message", "")
    if message:
        warnings.append(f"printer-state-message: {message!r}")
        if "waiting for printer to become available" in message.lower():
            problems.append(
                "backend cannot open the printer ('Waiting for printer to become "
                "available'). Power-cycle the SELPHY and re-plug USB; verify the "
                "device URI uses gutenprint53+usb://"
            )

    for reason in state_reasons(info):
        if reason.endswith("-error"):
            problems.append(f"printer-state-reason: {reason}")
        elif reason.endswith(("-warning", "-report")):
            warnings.append(f"printer-state-reason: {reason}")
        else:
            warnings.append(f"printer-state-reason: {reason}")

    uri = info.get("device-uri", "")
    if uri.startswith(BAD_BACKEND_PREFIX):
        problems.append(
            f"device URI uses the generic USB backend ({uri}). SELPHY dye-sub "
            "printers need the Gutenprint backend. Fix:\n"
            "    lpinfo -v | grep gutenprint53+usb\n"
            f"    sudo lpadmin -p {printer} -v \"gutenprint53+usb://...\""
        )
    elif not uri.startswith(GOOD_BACKEND_PREFIX):
        warnings.append(f"device URI uses an unexpected backend: {uri}")

    incomplete = active_jobs(conn, printer)
    if incomplete:
        ids = ", ".join(str(j) for j in sorted(incomplete))
        warnings.append(
            f"{len(incomplete)} unfinished job(s) in the queue (ids: {ids}) — "
            "new jobs wait behind them"
        )

    log.debug("readiness for %s: state=%s problems=%s warnings=%s",
              printer, state_name, problems, warnings)
    return problems, warnings


def active_jobs(conn, printer: str) -> dict:
    """Return incomplete jobs (id -> attrs) belonging to this queue."""
    try:
        jobs = conn.getJobs(
            which_jobs="not-completed",
            my_jobs=False,
            requested_attributes=[
                "job-id",
                "job-name",
                "job-state",
                "job-printer-uri",
                "time-at-creation",
                "job-originating-user-name",
            ],
        )
    except TypeError:
        # older pycups without requested_attributes
        jobs = conn.getJobs(which_jobs="not-completed", my_jobs=False)
    suffix = f"/printers/{printer}"
    return {
        job_id: attrs
        for job_id, attrs in jobs.items()
        if attrs.get("job-printer-uri", "").endswith(suffix)
    }


def completed_jobs(conn, printer: str, limit: int = 20) -> dict:
    try:
        jobs = conn.getJobs(
            which_jobs="completed",
            my_jobs=False,
            requested_attributes=[
                "job-id",
                "job-name",
                "job-state",
                "job-printer-uri",
                "time-at-creation",
                "time-at-completed",
                "job-originating-user-name",
            ],
        )
    except TypeError:
        jobs = conn.getJobs(which_jobs="completed", my_jobs=False)
    suffix = f"/printers/{printer}"
    matching = {
        job_id: attrs
        for job_id, attrs in jobs.items()
        if attrs.get("job-printer-uri", "").endswith(suffix)
    }
    newest = sorted(matching, reverse=True)[:limit]
    return {job_id: matching[job_id] for job_id in newest}
