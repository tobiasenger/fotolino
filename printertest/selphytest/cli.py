"""Command line interface for selphytest."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from . import (
    GOOD_BACKEND_PREFIX,
    JOB_STATES,
    PRINTER_STATES,
    __version__,
    connect,
    cups_module,
)
from . import cupsinfo, matrix, ppdopts
from .logutil import LOG_DIR, REPORT_DIR, setup_logging
from .printing import cancel_job, submit_and_wait
from .testpage import generate, have_pillow

log = logging.getLogger("selphytest.cli")


# --------------------------------------------------------------------------- helpers

def parse_kv_options(pairs: list[str]) -> dict[str, str]:
    options = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise SystemExit(f"ERROR: option '{pair}' is not in Key=Value form")
        key, _, value = pair.partition("=")
        options[key.strip()] = value.strip()
    return options


def fmt_time(epoch) -> str:
    if not epoch:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(int(epoch)))


def print_job_table(jobs: dict, completed: bool) -> None:
    if not jobs:
        log.info("  (none)")
        return
    header = f"  {'ID':>5}  {'state':<10} {'created':<19} "
    header += f"{'completed':<19} " if completed else ""
    header += f"{'user':<10} name"
    log.info(header)
    for job_id in sorted(jobs):
        attrs = jobs[job_id]
        state = JOB_STATES.get(attrs.get("job-state"), str(attrs.get("job-state")))
        line = (f"  {job_id:>5}  {state:<10} "
                f"{fmt_time(attrs.get('time-at-creation')):<19} ")
        if completed:
            line += f"{fmt_time(attrs.get('time-at-completed')):<19} "
        line += (f"{attrs.get('job-originating-user-name', '-'):<10} "
                 f"{attrs.get('job-name', '-')}")
        log.info(line)


def validate_user_options(conn, printer: str, options: dict[str, str]) -> None:
    if not options:
        return
    with ppdopts.open_ppd(conn, printer) as ppd:
        problems = ppdopts.validate_options(ppd, options)
        if problems:
            for problem in problems:
                log.error("ERROR: %s", problem)
            raise SystemExit(2)
        conflicts = ppdopts.conflict_count(ppd, options)
        if conflicts:
            log.warning("WARNING: PPD reports %d constraint conflict(s) for these "
                        "options — the driver may ignore or fail them.", conflicts)


# --------------------------------------------------------------------------- commands

def cmd_info(args) -> int:
    conn = connect()
    cups = cups_module()
    log.info("=== System ===")
    log.info("selphytest      : %s", __version__)
    log.info("Python          : %s", sys.version.split()[0])
    log.info("pycups          : %s", getattr(cups, "__version__", "unknown"))
    log.info("CUPS server     : %s", cupsinfo.cups_server_version())

    printers = conn.getPrinters()
    nickname = None
    target = None
    try:
        target = cupsinfo.pick_printer(conn, args.printer)
    except SystemExit as exc:
        log.warning("%s", exc)
    if target:
        with ppdopts.open_ppd(conn, target) as ppd:
            nickname = ppdopts.identity(ppd).get("NickName")
    log.info("Gutenprint      : %s", cupsinfo.gutenprint_version(nickname))
    backends = cupsinfo.gutenprint_backends()
    log.info("GP backends     : %s", ", ".join(backends) if backends else
             "NONE FOUND — gutenprint53+usb backend missing!")
    log.info("Pillow          : %s", "available" if have_pillow() else
             "missing (apt install python3-pil for labeled test pages)")

    log.info("")
    log.info("=== Printers (%d) ===", len(printers))
    default = conn.getDefault()
    for name, info in sorted(printers.items()):
        state = PRINTER_STATES.get(info.get("printer-state"), "?")
        mark = " [default]" if name == default else ""
        log.info("%s%s", name, mark)
        log.info("  state      : %s  accepting=%s", state,
                 info.get("printer-is-accepting-jobs"))
        if info.get("printer-state-message"):
            log.info("  message    : %s", info["printer-state-message"])
        reasons = cupsinfo.state_reasons(info)
        if reasons:
            log.info("  reasons    : %s", ", ".join(reasons))
        log.info("  device-uri : %s", info.get("device-uri", "-"))
        log.info("  make/model : %s", info.get("printer-make-and-model", "-"))

    if target:
        log.info("")
        log.info("=== Queue configuration: %s ===", target)
        attrs = cupsinfo.queue_attributes(conn, target)
        for key in sorted(attrs):
            value = attrs[key]
            if isinstance(value, list) and len(value) > 12:
                value = f"{value[:12]} ... ({len(value)} entries)"
            log.info("  %-32s: %s", key, value)
        with ppdopts.open_ppd(conn, target) as ppd:
            log.info("")
            log.info("=== PPD identity: %s ===", target)
            for key, value in ppdopts.identity(ppd).items():
                log.info("  %-16s: %s", key, value)
    return 0


def cmd_printers(args) -> int:
    conn = connect()
    printers = conn.getPrinters()
    default = conn.getDefault()
    if not printers:
        log.info("No printer queues configured in CUPS.")
        return 2
    for name, info in sorted(printers.items()):
        state = PRINTER_STATES.get(info.get("printer-state"), "?")
        mark = " [default]" if name == default else ""
        log.info("%-24s %-11s accepting=%-5s %s%s", name, state,
                 info.get("printer-is-accepting-jobs"),
                 info.get("device-uri", "-"), mark)
    return 0


def cmd_check(args) -> int:
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    log.info("Checking readiness of queue '%s' ...", printer)
    problems, warnings = cupsinfo.readiness_problems(conn, printer)
    info = conn.getPrinters()[printer]
    log.info("  state      : %s", PRINTER_STATES.get(info.get("printer-state"), "?"))
    log.info("  device-uri : %s", info.get("device-uri", "-"))
    if info.get("device-uri", "").startswith(GOOD_BACKEND_PREFIX):
        log.info("  backend    : gutenprint53+usb — correct for the SELPHY")
    for warning in warnings:
        log.warning("  WARNING: %s", warning)
    if problems:
        for problem in problems:
            log.error("  PROBLEM: %s", problem)
        log.error("Result: NOT READY (%d problem(s))", len(problems))
        return 2
    log.info("Result: READY")
    return 0


def cmd_options(args) -> int:
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    with ppdopts.open_ppd(conn, printer) as ppd:
        ident = ppdopts.identity(ppd)
        log.info("PPD options for queue '%s'", printer)
        log.info("Driver: %s", ident.get("NickName", "?"))
        log.info("")
        entries = ppdopts.all_options(ppd)
        if args.keyword:
            needle = args.keyword.lower()
            entries = [e for e in entries
                       if needle in e["keyword"].lower() or needle in e["text"].lower()]
            if not entries:
                log.error("No PPD option matches '%s'", args.keyword)
                return 2
        group = None
        for entry in entries:
            if entry["group"] != group:
                group = entry["group"]
                log.info("--- %s ---", group)
            log.info("%s (%s)  [default: %s]",
                     entry["keyword"], entry["text"], entry["default"])
            for choice, text in entry["choices"]:
                marker = "*" if choice == entry["default"] else " "
                suffix = f"  ({text})" if text and text != choice else ""
                log.info("   %s %s%s", marker, choice, suffix)
            log.info("")

    if not args.keyword:
        log.info("--- IPP view (CUPS) ---")
        attrs = cupsinfo.queue_attributes(conn, printer)
        for key in ("media-default", "media-ready", "media-supported",
                    "printer-resolution-default", "printer-resolution-supported",
                    "print-scaling-default", "print-scaling-supported"):
            if key in attrs:
                log.info("%-30s: %s", key, attrs[key])
        log.info("")
        log.info("Note: CUPS filter options that never appear in the PPD but are "
                 "valid with -o: fit-to-page, print-scaling=fill|fit|none, "
                 "landscape, position, ppi")
    return 0


def cmd_test_page(args) -> int:
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    options = parse_kv_options(args.option)

    if not options and not args.bare:
        # Sensible discovered defaults: borderless photo set when available
        with ppdopts.open_ppd(conn, printer) as ppd:
            for keyword, wanted in (("StpBorderless", "True"),
                                    ("StpiShrinkOutput", "Expand"),
                                    ("StpImageType", "Photo")):
                choices = ppdopts.option_choices(ppd, keyword)
                if choices:
                    match = next((c for c in choices if c.lower() == wanted.lower()),
                                 None)
                    if match:
                        options[keyword] = match
            default_size = ppdopts.option_default(ppd, "PageSize")
            if default_size:
                options["PageSize"] = default_size
        options["fit-to-page"] = "true"
        log.info("Using discovered options (override with -o, or --bare for none): %s",
                 options)
    validate_user_options(conn, printer, options)

    labels = [f"{k} = {v}" for k, v in options.items()] or ["PPD defaults"]
    labels.insert(0, time.strftime("%Y-%m-%d %H:%M:%S"))
    path = generate(LOG_DIR / "testpages", labels)

    outcome = submit_and_wait(conn, printer, str(path), "selphytest test page",
                              options, timeout=args.timeout, wait=not args.no_wait)
    log.info("%s", outcome.summary())
    if outcome.stuck:
        _stuck_advice(printer, outcome)
    return 0 if (outcome.success or args.no_wait and outcome.job_id) else 1


def cmd_print(args) -> int:
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    filepath = Path(args.file)
    if not filepath.is_file():
        log.error("ERROR: file not found: %s", filepath)
        return 2
    options = parse_kv_options(args.option)
    validate_user_options(conn, printer, options)
    outcome = submit_and_wait(conn, printer, str(filepath), filepath.name,
                              options, timeout=args.timeout, wait=not args.no_wait)
    log.info("%s", outcome.summary())
    if outcome.stuck:
        _stuck_advice(printer, outcome)
    return 0 if (outcome.success or args.no_wait and outcome.job_id) else 1


def _stuck_advice(printer: str, outcome) -> None:
    log.warning("")
    log.warning("The job did not finish. Typical causes, in order of likelihood:")
    log.warning(" 1. Wrong backend: device URI must start with gutenprint53+usb:// "
                "(run: %s check)", Path(sys.argv[0]).name)
    log.warning(" 2. PageSize does not match the loaded paper/ink cassette")
    log.warning(" 3. Printer hung on 'receiving data' — power-cycle it")
    log.warning("Cancel the job with: python3 selphy_test.py cancel %s",
                outcome.job_id or "<id>")


def cmd_matrix(args) -> int:
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    options_image = args.image
    if options_image and not Path(options_image).is_file():
        log.error("ERROR: image not found: %s", options_image)
        return 2

    with ppdopts.open_ppd(conn, printer) as ppd:
        dims = matrix.Dimensions.discover(ppd)
        if not dims.available:
            log.error("ERROR: PPD exposes none of %s — cannot build a matrix.",
                      ", ".join(matrix.DIMENSION_KEYWORDS))
            return 2
        log.info("Discovered dimensions from PPD:")
        for keyword, entry in dims.available.items():
            log.info("  %-18s default=%-12s choices=%s",
                     keyword, entry["default"], entry["choices"])

        if args.pagesize:
            valid = dims.choices("PageSize")
            for size in args.pagesize:
                if size not in valid:
                    log.error("ERROR: PageSize '%s' not in PPD. Valid: %s",
                              size, ", ".join(valid))
                    return 2

        if args.mode == "full":
            combos = matrix.build_full_plan(dims, args.pagesize)
        else:
            combos = matrix.build_quick_plan(dims, args.pagesize,
                                             args.include_other_sizes)
        if args.limit and len(combos) > args.limit:
            log.warning("Limiting plan from %d to %d combinations (--limit)",
                        len(combos), args.limit)
            combos = combos[: args.limit]

        log.info("")
        log.info("Test plan (%d combinations):", len(combos))
        for combo in combos:
            opts = " ".join(f"{k}={v}" for k, v in combo.options.items()) or "(defaults)"
            log.info("  #%-3d %-45s %s", combo.index, combo.label, opts)

        if args.dry_run:
            log.info("")
            log.info("Dry run — nothing was printed.")
            return 0

        log.info("")
        log.info("NOTE: load paper and ink cassette; every successful print uses "
                 "one sheet + one ink frame.")
        if not args.yes:
            answer = input(f"Start matrix with {len(combos)} combination(s)? "
                           "[Enter=yes / q=quit] ").strip().lower()
            if answer == "q":
                return 0

        ident = ppdopts.identity(ppd)
        context = {
            "driver": ident.get("NickName", "?"),
            "device-uri": conn.getPrinters().get(printer, {}).get("device-uri", "?"),
            "cups": cupsinfo.cups_server_version(),
            "gutenprint": cupsinfo.gutenprint_version(ident.get("NickName")),
            "mode": args.mode,
            "image": options_image or "generated test pages",
            "timeout_s": args.timeout,
        }
        matrix.run_matrix(conn, printer, combos, ppd, context,
                          options_image, args.timeout, args.yes)
    return 0


def cmd_jobs(args) -> int:
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    if not args.completed or args.all:
        log.info("Active jobs on '%s':", printer)
        print_job_table(cupsinfo.active_jobs(conn, printer), completed=False)
    if args.completed or args.all:
        log.info("")
        log.info("Completed jobs on '%s' (newest %d):", printer, args.limit)
        print_job_table(cupsinfo.completed_jobs(conn, printer, args.limit),
                        completed=True)
    return 0


def cmd_cancel(args) -> int:
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    if args.all:
        jobs = sorted(cupsinfo.active_jobs(conn, printer))
        if not jobs:
            log.info("No active jobs on '%s'.", printer)
            return 0
        count = sum(1 for job_id in jobs if cancel_job(conn, job_id, args.purge))
        log.info("Canceled %d of %d job(s).", count, len(jobs))
        return 0 if count == len(jobs) else 1
    if not args.job_ids:
        log.error("ERROR: pass job IDs or --all")
        return 2
    failed = [j for j in args.job_ids if not cancel_job(conn, j, args.purge)]
    return 1 if failed else 0


def cmd_unstick(args) -> int:
    """Cancel stale jobs and re-enable a paused/rejecting queue."""
    cups = cups_module()
    conn = connect()
    printer = cupsinfo.pick_printer(conn, args.printer)
    jobs = sorted(cupsinfo.active_jobs(conn, printer))
    for job_id in jobs:
        cancel_job(conn, job_id)
    log.info("Canceled %d job(s).", len(jobs))
    for action, func in (("cupsenable", conn.enablePrinter),
                         ("cupsaccept", conn.acceptJobs)):
        try:
            func(printer)
            log.info("%s %s: OK", action, printer)
        except cups.IPPError as exc:
            log.error("%s %s failed: %s", action, printer, exc)
            log.error("You probably lack admin rights — run: sudo %s %s "
                      "(and add your user to the lpadmin group)", action, printer)
    log.info("")
    log.info("If the printer display still shows 'receiving data', power-cycle it — "
             "no software can clear that state.")
    return cmd_check(args)


# --------------------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="selphy_test.py",
        description="Diagnostic & test utility for the Canon SELPHY CP1500 on "
                    "CUPS/Gutenprint (standalone, photo-booth independent).",
        epilog=f"Logs: {LOG_DIR}  Reports: {REPORT_DIR}",
    )
    parser.add_argument("--version", action="version",
                        version=f"selphytest {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("-p", "--printer",
                       help="CUPS queue name (default: auto-detect SELPHY)")
        p.add_argument("-v", "--verbose", action="store_true",
                       help="show debug output on the console")

    p = sub.add_parser("info", help="show CUPS/Gutenprint versions, printers, "
                                    "queue configuration")
    common(p)
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("printers", help="list configured printer queues")
    common(p)
    p.set_defaults(func=cmd_printers)

    p = sub.add_parser("check", help="check printer readiness (exit 0 = ready)")
    common(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("options", help="show all supported PPD/IPP print options")
    common(p)
    p.add_argument("-k", "--keyword", help="filter options by keyword, e.g. PageSize")
    p.set_defaults(func=cmd_options)

    p = sub.add_parser("test-page", help="print a generated diagnostic test page")
    common(p)
    p.add_argument("-o", "--option", action="append", metavar="KEY=VALUE",
                   help="print option (repeatable), e.g. -o PageSize=Postcard")
    p.add_argument("--bare", action="store_true",
                   help="send with NO options at all (pure PPD defaults)")
    p.add_argument("--timeout", type=float, default=180,
                   help="seconds to wait for completion (default 180)")
    p.add_argument("--no-wait", action="store_true",
                   help="submit only, do not watch the job")
    p.set_defaults(func=cmd_test_page)

    p = sub.add_parser("print", help="print a supplied JPEG/PNG file")
    common(p)
    p.add_argument("file", help="image file to print")
    p.add_argument("-o", "--option", action="append", metavar="KEY=VALUE",
                   help="print option (repeatable)")
    p.add_argument("--timeout", type=float, default=180)
    p.add_argument("--no-wait", action="store_true")
    p.set_defaults(func=cmd_print)

    p = sub.add_parser("matrix",
                       help="automatically test combinations of page size / "
                            "borderless / scaling and record what works")
    common(p)
    p.add_argument("--mode", choices=["quick", "full"], default="quick",
                   help="quick: curated set (default); full: cartesian product")
    p.add_argument("--image", help="use this JPEG instead of generated test pages")
    p.add_argument("--pagesize", action="append", metavar="SIZE",
                   help="restrict to these PageSize values (repeatable)")
    p.add_argument("--include-other-sizes", action="store_true",
                   help="quick mode: also test non-default page sizes")
    p.add_argument("--limit", type=int, help="cap the number of combinations")
    p.add_argument("--timeout", type=float, default=180,
                   help="seconds per job before it counts as stuck (default 180)")
    p.add_argument("--dry-run", action="store_true",
                   help="show the plan, do not print")
    p.add_argument("-y", "--yes", action="store_true",
                   help="no interactive confirmation between prints "
                        "(aborts on first stuck job)")
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("jobs", help="view active and completed jobs")
    common(p)
    p.add_argument("--completed", action="store_true", help="show completed jobs")
    p.add_argument("--all", action="store_true", help="show active AND completed")
    p.add_argument("--limit", type=int, default=20,
                   help="max completed jobs to list (default 20)")
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser("cancel", help="cancel queued jobs")
    common(p)
    p.add_argument("job_ids", nargs="*", type=int, help="job IDs to cancel")
    p.add_argument("--all", action="store_true", help="cancel all active jobs")
    p.add_argument("--purge", action="store_true",
                   help="also delete job files/history")
    p.set_defaults(func=cmd_cancel)

    p = sub.add_parser("unstick",
                       help="cancel stale jobs, re-enable the queue, re-check")
    common(p)
    p.set_defaults(func=cmd_unstick)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logfile = setup_logging(args.command, getattr(args, "verbose", False))
    try:
        rc = args.func(args)
    except KeyboardInterrupt:
        log.warning("Interrupted.")
        rc = 130
    log.debug("exit code %s", rc)
    logging.getLogger("selphytest").info("")
    logging.getLogger("selphytest").info("Full log: %s", logfile)
    return rc
