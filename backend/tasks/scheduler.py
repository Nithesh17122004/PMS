"""Single-process background scheduler.

ClinicFlow deploys one scheduler-enabled web service (or a dedicated worker)
because reminder jobs are designed to be idempotent but should not be run from
every web instance. Set ``ENABLE_SCHEDULER=true`` on exactly one service.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from flask import Flask, current_app

from .jobs import run_all_jobs

logger = logging.getLogger(__name__)

_thread: threading.Thread | None = None
_stop_event = threading.Event()
_start_lock = threading.Lock()


def _interval_seconds() -> int:
    return max(60, int(current_app.config.get("SCHEDULER_INTERVAL_MINUTES", 15)) * 60)


def _loop(app: Flask) -> None:
    logger.info("ClinicFlow scheduler started (pid=%s)", os.getpid())
    # Small initial delay so application startup and migrations finish first.
    if _stop_event.wait(10):
        return
    while not _stop_event.is_set():
        try:
            with app.app_context():
                run_all_jobs()
        except Exception:
            logger.exception("Scheduler cycle failed")
        if _stop_event.wait(_interval_seconds()):
            break
    logger.info("ClinicFlow scheduler stopped")


def start_scheduler(app: Flask) -> threading.Thread | None:
    global _thread
    with _start_lock:
        if _thread and _thread.is_alive():
            return _thread
        _stop_event.clear()
        _thread = threading.Thread(
            target=_loop,
            args=(app,),
            name="clinicflow-scheduler",
            daemon=True,
        )
        _thread.start()
        return _thread


def stop_scheduler() -> None:
    _stop_event.set()


def run_forever() -> None:
    """Blocking loop used by the ``flask run-scheduler`` CLI command."""
    app = current_app._get_current_object()
    logger.info("Running scheduler in the foreground (Ctrl+C to stop)")
    try:
        while True:
            with app.app_context():
                run_all_jobs()
            time.sleep(_interval_seconds())
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted")
