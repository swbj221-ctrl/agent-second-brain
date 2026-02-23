"""Run news briefing jobs via the sidecar scheduler."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if src.exists() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def main() -> int:
    _ensure_src_on_path()
    from d_brain.sidecar.scheduler import Scheduler, build_default_registry

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    logger = logging.getLogger("news_briefing_job")

    parser = argparse.ArgumentParser(description="Run news briefing jobs")
    parser.add_argument(
        "--job",
        choices=[
            "news_briefing_generate_daily",
            "news_briefing_deliver_telegram",
        ],
        help="Job name to run",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run generate then deliver",
    )
    args = parser.parse_args()

    scheduler = Scheduler(build_default_registry())

    if args.all:
        logger.info("Running job: news_briefing_generate_daily")
        scheduler.run_once("news_briefing_generate_daily")
        logger.info("Running job: news_briefing_deliver_telegram")
        scheduler.run_once("news_briefing_deliver_telegram")
        logger.info("All jobs completed.")
        return 0

    if not args.job:
        parser.error("Provide --job or --all")

    logger.info("Running job: %s", args.job)
    scheduler.run_once(args.job)
    logger.info("Job completed: %s", args.job)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
