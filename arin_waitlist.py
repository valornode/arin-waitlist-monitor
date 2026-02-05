#!/usr/bin/env python3
"""
ARIN IPv4 Waiting List Monitor (Playwright)

- Scrapes ARIN waiting list table (JS-rendered) via Playwright
- Finds your entry by the exact timestamp string
- ALWAYS emails your current position each run (or prints if email fails)
- Supports:
    - STARTTLS SMTP (typically port 587)
    - SMTPS implicit TLS (typically port 465)
- Verbose progress output
- Multiple recipients supported via MAIL_TO

Exit codes:
  0 = found
  2 = not found
  3 = error
"""

import os
import re
import json
import time
import argparse
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

try:
    from zoneinfo import ZoneInfo  # py3.9+
except Exception:
    ZoneInfo = None  # type: ignore


WAITLIST_URL = "https://www.arin.net/resources/guide/ipv4/waiting_list/"

DEFAULT_TARGET_DATE = os.getenv("ARIN_TARGET_DATE", "Tue, 03 Feb 2026, 12:17:25 EST")
DEFAULT_INTERVAL_SECONDS = int(os.getenv("ARIN_CHECK_INTERVAL_SECONDS", str(12 * 60 * 60)))
DEFAULT_STATE_FILE = os.getenv("ARIN_STATE_FILE", "arin_waitlist_state.json")

# SMTP settings (env)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
MAIL_FROM = os.getenv("MAIL_FROM", SMTP_USER)
MAIL_TO_RAW = os.getenv("MAIL_TO", "")
MAIL_SUBJECT_PREFIX = os.getenv("MAIL_SUBJECT_PREFIX", "[ARIN Waitlist]")

SMTP_CONNECT_TIMEOUT = int(os.getenv("SMTP_CONNECT_TIMEOUT", "15"))

# Time checked format requested: "MM/DD/YYYY 00:00PM CST"
# We'll render in America/Chicago if available, otherwise fixed CST offset.
CST_TZ = None
if ZoneInfo is not None:
    try:
        CST_TZ = ZoneInfo("America/Chicago")
    except Exception:
        CST_TZ = None

# Match lines like:
# "473 Tue, 03 Feb 2026, 12:17:25 EST /22 /22"
ROW_RE = re.compile(
    r"^\s*(?P<pos>\d+)\s+(?P<dt>(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),.+?)\s+(?P<max>/\d+)\s+(?P<min>/\d+)\s*$"
)


def log(msg: str) -> None:
    print(f"[INFO] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"[WARN] {msg}", flush=True)


def err(msg: str) -> None:
    print(f"[ERROR] {msg}", flush=True)


def parse_recipients(mail_to_raw: str) -> list[str]:
    """
    Accepts comma/semicolon/whitespace-separated recipients.
    Returns a de-duplicated list preserving order.
    """
    if not mail_to_raw:
        return []
    # split on comma, semicolon, or whitespace
    parts = re.split(r"[,\s;]+", mail_to_raw.strip())
    out = []
    seen = set()
    for p in parts:
        if not p:
            continue
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def load_state(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path: str, state: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def format_time_checked_cst(now_utc: datetime) -> str:
    """
    Format as: MM/DD/YYYY 00:00PM CST
    Uses America/Chicago if available; otherwise uses fixed CST (UTC-6).
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    if CST_TZ is not None:
        local = now_utc.astimezone(CST_TZ)
        # Could be CDT in summer; user asked for "CST" literal, so we will print CST regardless.
        # If you want accurate abbreviation (CST/CDT), tell me and I’ll switch.
        return local.strftime("%m/%d/%Y %I:%M%p") + " CST"
    # fixed CST fallback
    fixed = now_utc.astimezone(timezone.utc).timestamp() - (6 * 3600)
    local = datetime.fromtimestamp(fixed, tz=timezone.utc)
    return local.strftime("%m/%d/%Y %I:%M%p") + " CST"


def send_email(subject: str, body: str) -> None:
    """
    Supports both STARTTLS SMTP and SMTPS:
      - If SMTP_PORT == 465: SMTPS (implicit TLS) via SMTP_SSL
      - Else: SMTP + STARTTLS
    Multiple recipients supported via MAIL_TO (comma/semicolon/space separated).
    If sending fails, prints message instead (non-fatal).
    """
    recipients = parse_recipients(MAIL_TO_RAW)

    log(f"Email config: host={SMTP_HOST!r} port={SMTP_PORT} user={SMTP_USER!r} from={MAIL_FROM!r} to={recipients!r}")

    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and recipients and MAIL_FROM):
        warn("SMTP not fully configured; printing message instead of emailing.")
        print("Subject:", subject, flush=True)
        print(body, flush=True)
        return

    msg = EmailMessage()
    msg["From"] = MAIL_FROM
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)

    context = ssl.create_default_context()

    try:
        if SMTP_PORT == 465:
            log("Sending via SMTPS (SMTP_SSL)")
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_CONNECT_TIMEOUT, context=context) as s:
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)
        else:
            log("Sending via SMTP STARTTLS")
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_CONNECT_TIMEOUT) as s:
                s.ehlo()
                s.starttls(context=context)
                s.ehlo()
                s.login(SMTP_USER, SMTP_PASS)
                s.send_message(msg)

        log("Email sent successfully.")

    except Exception as e:
        err(f"Email send failed ({SMTP_HOST}:{SMTP_PORT}): {e}")
        print("Subject:", subject, flush=True)
        print(body, flush=True)


def scrape_waitlist_rows() -> list[dict]:
    """
    Returns list of dicts:
      { position:int, dt_str:str, max_prefix:str, min_prefix:str }
    """
    rows_out: list[dict] = []

    log("Launching Chromium (headless)")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        log("Loading ARIN waiting list page")
        try:
            page.goto(WAITLIST_URL, wait_until="networkidle", timeout=60000)
        except PWTimeoutError:
            warn("networkidle timed out; retrying with wait_until=load")
            page.goto(WAITLIST_URL, wait_until="load", timeout=60000)

        log("Locating table rows")
        rows = page.locator("table tbody tr")
        count = rows.count()
        log(f"Found {count} rows (including any non-data rows)")

        for i in range(count):
            txt = rows.nth(i).inner_text().replace("\n", " ").strip()
            m = ROW_RE.match(txt)
            if not m:
                continue

            rows_out.append(
                {
                    "position": int(m.group("pos")),
                    "dt_str": m.group("dt").strip(),
                    "max_prefix": m.group("max").strip(),
                    "min_prefix": m.group("min").strip(),
                    "raw": txt,
                }
            )

        browser.close()

    log(f"Parsed {len(rows_out)} data rows")
    return rows_out


def find_entry(rows: list[dict], target_dt_str: str) -> dict | None:    """
    Match by exact timestamp string (normalized whitespace).
    """
    target_norm = " ".join(target_dt_str.split())
    for r in rows:
        if " ".join(r["dt_str"].split()) == target_norm:
            return r
    return None


def build_body(current_pos: int, total: int, last_pos: int | None, joined: str, maxp: str, minp: str, time_checked: str) -> str:
    last_pos_str = str(last_pos) if last_pos is not None else "None"    return (
        "Your current ARIN IPv4 waiting list position is:\n"
        f"{current_pos}/{total}.\n\n"
        "Your last position was:\n"
        f"{last_pos_str}/{total}.\n\n"
        "You joined the waitlist on:\n"
        f"{joined}\n\n"
        f"Max Prefix: {maxp} | Min Prefix: {minp}\n\n"
        "Time Checked:\n"
        f"{time_checked}\n"
    )


def run_once(target_dt_str: str, state_file: str) -> int:
    log("Starting ARIN waitlist check")
    now_utc = datetime.now(timezone.utc)
    state = load_state(state_file)

    try:
        rows = scrape_waitlist_rows()
        total = len(rows)
        log(f"Searching for target timestamp: {target_dt_str}")

        match = find_entry(rows, target_dt_str)
        if not match:
            warn("Entry not found in table")
            subject = f"{MAIL_SUBJECT_PREFIX} NOT FOUND"
            body = (
                "Could not find your entry in the ARIN waiting list table.\n\n"
                f"Target timestamp:\n{target_dt_str}\n\n"
                f"Rows parsed:\n{total}\n\n"
                "Time Checked:\n"
                f"{format_time_checked_cst(now_utc)}\n"
            )
            send_email(subject, body)
            return 2

        current_pos = match["position"]
        last_pos = state.get("last_position")
        log(f"Match found! Current position = {current_pos}/{total}")

        time_checked = format_time_checked_cst(now_utc)
        body = build_body(
            current_pos=current_pos,
            total=total,
            last_pos=int(last_pos) if last_pos is not None else None,
            joined=target_dt_str,
            maxp=match["max_prefix"],
            minp=match["min_prefix"],
            time_checked=time_checked,
        )

        subject = f"{MAIL_SUBJECT_PREFIX} Position: {current_pos}/{total}"
        send_email(subject, body)

        state["last_position"] = current_pos
        state["last_checked_utc"] = now_utc.isoformat()
        save_state(state_file, state)
        log(f"State saved to {state_file}")
        log("Done")
        return 0

    except Exception as e:
        err(f"Run failed: {e}")
        subject = f"{MAIL_SUBJECT_PREFIX} ERROR"
        body = (
            "Error while checking ARIN waiting list:\n"
            f"{e}\n\n"
            "Time Checked:\n"
            f"{format_time_checked_cst(now_utc)}\n"
        )
        send_email(subject, body)
        return 3


def main() -> None:
    ap = argparse.ArgumentParser(description="Monitor ARIN IPv4 waiting list position (Playwright).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Run once and exit.")
    mode.add_argument("--watch", action="store_true", help="Run continuously (default).")

    ap.add_argument("--target", default=DEFAULT_TARGET_DATE, help="Target timestamp as shown on ARIN page.")
    ap.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Watch interval in seconds (default 12h).")
    ap.add_argument("--state-file", default=DEFAULT_STATE_FILE, help="Path to state file.")

    args = ap.parse_args()

    if args.once:
        raise SystemExit(run_once(args.target, args.state_file))

    log(f"Watch mode enabled. Interval={args.interval}s (default 12h)")
    log(f"Target={args.target}")
    log(f"State file={args.state_file}")

    while True:
        run_once(args.target, args.state_file)
        log(f"Sleeping for {args.interval} seconds")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
