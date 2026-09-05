"""APScheduler wrapper: run paper-trading on a cron schedule."""
from __future__ import annotations

import logging
from typing import Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from qrp_platform.config import settings
from qrp_platform.live.paper import PaperBroker
from qrp_platform.strategies.base import Strategy

log = logging.getLogger(__name__)


def start_scheduler(
    strategy: Strategy,
    tickers: list[str],
    capital: float | None = None,
    cron: str | None = None,
    job_func: Callable | None = None,
) -> BlockingScheduler:
    """Start a blocking cron scheduler that rebalances the paper broker.

    Args:
        strategy: a Strategy instance to call each tick.
        tickers: list of symbols.
        capital: starting capital (defaults to PAPER_CAPITAL env).
        cron: cron expression (defaults to PAPER_CRON env).
        job_func: optional callable to run instead of the paper loop.
    """
    cron = cron or settings.paper_cron
    sched = BlockingScheduler()
    broker = PaperBroker(capital=capital)

    def _job() -> None:
        log.info("scheduler tick: strategy=%s tickers=%s", strategy.name, tickers)
        snap = broker.run_one_tick(strategy, tickers)
        log.info("scheduler tick done: equity=%.2f cash=%.2f", snap["equity"], snap["cash"])

    target = job_func or _job
    sched.add_job(target, CronTrigger.from_crontab(cron), id="paper-rebalance")
    log.info("scheduler started: cron='%s' strategy=%s", cron, strategy.name)
    sched.start()
    return sched