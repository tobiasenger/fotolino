"""Automated print-setting matrix test.

Builds combinations of PageSize / borderless / scaling options from what the
installed PPD actually offers (runtime discovery, no hardcoded values), prints
each one and records the result.

quick mode: a handful of high-value combinations around the PPD defaults.
full mode:  cartesian product of PageSize x StpBorderless x StpiShrinkOutput
            x fit-to-page (can use a LOT of paper — every successful print
            consumes one sheet AND one ink-cassette frame).
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field

from . import ppdopts
from .cupsinfo import active_jobs, readiness_problems
from .printing import cancel_job, submit_and_wait
from .report import MatrixReport
from .testpage import generate, have_pillow
from .logutil import LOG_DIR

log = logging.getLogger("selphytest.matrix")

# Option keywords the matrix varies, in priority order. Only the ones that
# actually exist in the queue's PPD are used.
DIMENSION_KEYWORDS = ("PageSize", "StpBorderless", "StpiShrinkOutput")
# Extra non-PPD option dimension handled by the CUPS image filters
FIT_DIMENSION = ("fit-to-page", ["true", ""])  # "" = option omitted


@dataclass
class Combo:
    index: int
    label: str
    options: dict[str, str]
    skipped: bool = False
    skip_reason: str = ""
    outcome: dict | None = None

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "label": self.label,
            "options": self.options,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "outcome": self.outcome,
        }


@dataclass
class Dimensions:
    """PPD-discovered values for the option keywords the matrix varies."""
    available: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def discover(cls, ppd) -> "Dimensions":
        dims = cls()
        for keyword in DIMENSION_KEYWORDS:
            option = ppdopts.find_option(ppd, keyword)
            if option is not None:
                dims.available[option.keyword] = {
                    "default": option.defchoice,
                    "choices": [c["choice"] for c in option.choices],
                }
        log.debug("discovered matrix dimensions: %s", dims.available)
        return dims

    def has(self, keyword: str) -> bool:
        return keyword in self.available

    def default(self, keyword: str) -> str | None:
        entry = self.available.get(keyword)
        return entry["default"] if entry else None

    def choices(self, keyword: str) -> list[str]:
        entry = self.available.get(keyword)
        return list(entry["choices"]) if entry else []


def build_quick_plan(dims: Dimensions, page_sizes: list[str] | None,
                     include_other_sizes: bool) -> list[Combo]:
    """A small set of high-value combinations."""
    plans: list[tuple[str, dict]] = []
    default_size = dims.default("PageSize")

    plans.append(("PPD defaults only", {}))

    recommended = {}
    if default_size:
        recommended["PageSize"] = default_size
    if dims.has("StpBorderless"):
        recommended["StpBorderless"] = _pick(dims.choices("StpBorderless"), "true")
    if dims.has("StpiShrinkOutput"):
        recommended["StpiShrinkOutput"] = _pick(dims.choices("StpiShrinkOutput"), "expand")
    recommended["fit-to-page"] = "true"
    plans.append(("borderless + expand + fit-to-page (photobooth set)", recommended))

    no_fit = {k: v for k, v in recommended.items() if k != "fit-to-page"}
    if no_fit != dict(plans[0][1]):
        plans.append(("borderless + expand, no fit-to-page", no_fit))

    bordered = {}
    if default_size:
        bordered["PageSize"] = default_size
    if dims.has("StpBorderless"):
        bordered["StpBorderless"] = _pick(dims.choices("StpBorderless"), "false")
    bordered["fit-to-page"] = "true"
    plans.append(("bordered + fit-to-page", bordered))

    # Fullbleed page-size variants, if this PPD defines any
    for size in dims.choices("PageSize"):
        if "fullbleed" in size.lower():
            plans.append((f"PageSize {size} + fit-to-page",
                          {"PageSize": size, "fit-to-page": "true"}))

    sizes = page_sizes or ([] if not include_other_sizes else
                           [s for s in dims.choices("PageSize")
                            if s != default_size and "fullbleed" not in s.lower()])
    for size in sizes:
        combo = {"PageSize": size, "fit-to-page": "true"}
        if dims.has("StpBorderless"):
            combo["StpBorderless"] = _pick(dims.choices("StpBorderless"), "true")
        plans.append((f"PageSize {size}", combo))

    return _dedupe(plans)


def build_full_plan(dims: Dimensions, page_sizes: list[str] | None) -> list[Combo]:
    """Cartesian product over all discovered dimensions."""
    axes: list[list[tuple[str, str]]] = []
    sizes = page_sizes or dims.choices("PageSize") or [None]
    axes.append([("PageSize", s) for s in sizes])
    for keyword in ("StpBorderless", "StpiShrinkOutput"):
        if dims.has(keyword):
            axes.append([(keyword, c) for c in dims.choices(keyword)])
    fit_key, fit_values = FIT_DIMENSION
    axes.append([(fit_key, v) for v in fit_values])

    plans = []
    for cells in itertools.product(*axes):
        options = {k: v for k, v in cells if k is not None and v not in (None, "")}
        label = " ".join(f"{k}={v}" for k, v in options.items()) or "(defaults)"
        plans.append((label, options))
    return _dedupe(plans)


def _pick(choices: list[str], wanted_lower: str) -> str:
    for choice in choices:
        if choice.lower() == wanted_lower:
            return choice
    return choices[0] if choices else wanted_lower


def _dedupe(plans: list[tuple[str, dict]]) -> list[Combo]:
    seen = set()
    combos = []
    for label, options in plans:
        key = tuple(sorted(options.items()))
        if key in seen:
            continue
        seen.add(key)
        combos.append(Combo(index=len(combos) + 1, label=label, options=dict(options)))
    return combos


def run_matrix(conn, printer: str, combos: list[Combo], ppd, context: dict,
               image: str | None, timeout: float, assume_yes: bool) -> MatrixReport:
    report = MatrixReport(printer, context)
    log.info("")
    log.info("=== Matrix run: %d combination(s) on queue '%s' ===", len(combos), printer)
    log.info("Each successful print uses one sheet + one ink frame.")

    aborted = False
    try:
        for combo in combos:
            if aborted:
                combo.skipped = True
                combo.skip_reason = "run aborted earlier"
                report.add(combo.as_dict())
                continue

            conflicts = ppdopts.conflict_count(ppd, combo.options)
            if conflicts:
                combo.skipped = True
                combo.skip_reason = f"{conflicts} PPD constraint conflict(s)"
                log.warning("[%d/%d] %s — SKIPPED (%s)", combo.index, len(combos),
                            combo.label, combo.skip_reason)
                report.add(combo.as_dict())
                continue

            opts_str = " ".join(f"{k}={v}" for k, v in combo.options.items()) or "(defaults)"
            log.info("")
            log.info("[%d/%d] %s", combo.index, len(combos), combo.label)
            log.info("        options: %s", opts_str)

            if not assume_yes:
                answer = input("        print this? [Enter=yes / s=skip / q=quit] ").strip().lower()
                if answer == "q":
                    aborted = True
                    combo.skipped = True
                    combo.skip_reason = "user aborted"
                    report.add(combo.as_dict())
                    continue
                if answer == "s":
                    combo.skipped = True
                    combo.skip_reason = "user skipped"
                    report.add(combo.as_dict())
                    continue

            if not _ensure_idle(conn, printer, assume_yes):
                aborted = True
                combo.skipped = True
                combo.skip_reason = "queue not idle / not ready"
                report.add(combo.as_dict())
                continue

            filepath = image
            if filepath is None:
                labels = [f"{k} = {v}" for k, v in combo.options.items()] or ["PPD defaults"]
                filepath = str(generate(LOG_DIR / "testpages", labels, index=combo.index))
            title = f"selphytest #{combo.index} {opts_str}"

            outcome = submit_and_wait(conn, printer, filepath, title,
                                      combo.options, timeout=timeout)
            combo.outcome = outcome.as_dict()
            report.add(combo.as_dict())
            log.info("        => %s", outcome.summary())

            if outcome.stuck:
                if outcome.job_id is not None:
                    cancel_job(conn, outcome.job_id)
                log.warning("")
                log.warning("Job got stuck — the SELPHY very likely needs a power-cycle")
                log.warning("before further jobs can print (backend holds the device).")
                if assume_yes:
                    log.warning("Unattended mode (--yes): aborting the remaining combinations.")
                    aborted = True
                else:
                    answer = input(
                        "Power-cycle the printer, wait for its home screen, then press "
                        "Enter to continue (or q to abort): "
                    ).strip().lower()
                    if answer == "q":
                        aborted = True
    finally:
        report.finalize()

    done = [c for c in combos if not c.skipped and c.outcome]
    ok = [c for c in done if c.outcome.get("success")]
    log.info("")
    log.info("=== Matrix finished: %d printed, %d succeeded, %d skipped ===",
             len(done), len(ok), len(combos) - len(done))
    for combo in ok:
        opts_str = " ".join(f"{k}={v}" for k, v in combo.options.items()) or "(defaults)"
        log.info("  WORKS: #%d  %s", combo.index, opts_str)
    return report


def _ensure_idle(conn, printer: str, assume_yes: bool) -> bool:
    """Make sure no unfinished jobs are queued before submitting the next combo."""
    pending = active_jobs(conn, printer)
    if pending:
        ids = sorted(pending)
        log.warning("Queue still has unfinished job(s): %s", ids)
        if assume_yes:
            return False
        answer = input(f"Cancel job(s) {ids} and continue? [Enter=yes / q=quit] ").strip().lower()
        if answer == "q":
            return False
        for job_id in ids:
            cancel_job(conn, job_id)
    problems, _warnings = readiness_problems(conn, printer)
    if problems:
        for problem in problems:
            log.warning("NOT READY: %s", problem)
        return False
    return True
