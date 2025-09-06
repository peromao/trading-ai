import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, time as dtime


# Ensure package import works when executed as a script
if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import orchestrador


@dataclass
class ScheduleConfig:
    weekday_at: dtime
    sunday_at: dtime


def _parse_hhmm(value: str, default: dtime) -> dtime:
    value = (value or "").strip()
    if not value:
        return default
    try:
        hh, mm = value.split(":", 1)
        return dtime(hour=int(hh), minute=int(mm))
    except Exception:
        print(f"[schedule_runner] Invalid time '{value}', using default {default}")
        return default


def _next_weekday_run(now: datetime, at_time: dtime) -> datetime:
    # Monday=0 ... Sunday=6
    today_wd = now.weekday()
    candidate = datetime.combine(now.date(), at_time)
    if today_wd <= 4 and candidate > now:
        return candidate
    for i in range(1, 8):
        d = now + timedelta(days=i)
        if d.weekday() <= 4:
            return datetime.combine(d.date(), at_time)
    # Should never reach here
    return candidate


def _next_sunday_run(now: datetime, at_time: dtime) -> datetime:
    today_wd = now.weekday()
    candidate = datetime.combine(now.date(), at_time)
    if today_wd == 6 and candidate > now:
        return candidate
    # days until next Sunday (6)
    days = (6 - today_wd) % 7
    if days == 0:
        days = 7
    target_date = (now + timedelta(days=days)).date()
    return datetime.combine(target_date, at_time)


def _sleep_until(target: datetime):
    while True:
        now = datetime.now()
        seconds = (target - now).total_seconds()
        if seconds <= 0:
            return
        # Sleep in chunks to allow Ctrl+C responsiveness
        time.sleep(min(seconds, 60))


def _run_job(name: str, func):
    print(
        f"[schedule_runner] Running job: {name} at {datetime.now().isoformat(timespec='seconds')}"
    )
    try:
        func()
        print(f"[schedule_runner] Job '{name}' completed")
    except Exception as exc:
        print(f"[schedule_runner] Job '{name}' failed: {exc}")


def _load_config() -> ScheduleConfig:
    # Defaults: 18:00 for weekdays, 09:00 for Sunday (local time)
    weekday_default = dtime(hour=18, minute=0)
    sunday_default = dtime(hour=9, minute=0)
    weekday_at = _parse_hhmm(os.getenv("WEEKDAY_AT", ""), weekday_default)
    sunday_at = _parse_hhmm(os.getenv("SUNDAY_AT", ""), sunday_default)
    return ScheduleConfig(weekday_at=weekday_at, sunday_at=sunday_at)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run recurring jobs for trading-ai")
    parser.add_argument(
        "--run-now",
        choices=["weekday", "sunday"],
        help="Run a job immediately and continue scheduling",
    )
    args = parser.parse_args(argv)

    cfg = _load_config()
    print(
        f"[schedule_runner] Starting with WEEKDAY_AT={cfg.weekday_at.strftime('%H:%M')} "
        f"SUNDAY_AT={cfg.sunday_at.strftime('%H:%M')}"
    )

    if args.run_now == "weekday":
        _run_job("weekday_processing", orchestrador.weekday_processing)
    elif args.run_now == "sunday":
        _run_job("sunday_processing", orchestrador.sunday_processing)

    # Main scheduler loop
    while True:
        now = datetime.now()
        next_wd = _next_weekday_run(now, cfg.weekday_at)
        next_sun = _next_sunday_run(now, cfg.sunday_at)
        next_run = min(next_wd, next_sun)
        job_name = "weekday_processing" if next_run == next_wd else "sunday_processing"

        print(
            f"[schedule_runner] Next run: {job_name} at {next_run.isoformat(timespec='seconds')}"
        )
        _sleep_until(next_run)
        _run_job(
            job_name,
            (
                orchestrador.weekday_processing
                if job_name == "weekday_processing"
                else orchestrador.sunday_processing
            ),
        )


if __name__ == "__main__":
    main()
