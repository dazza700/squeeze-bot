"""BB Squeeze Breakout Bot — Entry Point"""
import logging, sys, threading, time
import schedule, uvicorn
from config import SIGNAL_CHECK_UTC, POSITION_CHECK_M, HL_PRIVATE_KEY, HL_WALLET_ADDRESS
from bot import daily_signal_scan, monitor_positions
from dashboard import app

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("squeeze_main")


def _check_config():
    if not HL_PRIVATE_KEY:
        logger.error("HL_PRIVATE_KEY not set"); sys.exit(1)
    if not HL_WALLET_ADDRESS:
        logger.error("HL_WALLET_ADDRESS not set"); sys.exit(1)
    logger.info(f"Wallet: {HL_WALLET_ADDRESS[:6]}…{HL_WALLET_ADDRESS[-4:]}")


def _run_scheduler():
    schedule.every().day.at(SIGNAL_CHECK_UTC).do(lambda: _safe(daily_signal_scan))
    schedule.every(POSITION_CHECK_M).minutes.do(lambda: _safe(monitor_positions))
    logger.info(f"Scheduled: signal scan {SIGNAL_CHECK_UTC} UTC | monitor every {POSITION_CHECK_M}m")
    _safe(monitor_positions)   # run immediately on startup to resume any open positions
    while True:
        schedule.run_pending()
        time.sleep(30)


def _safe(fn):
    try: fn()
    except Exception as e: logger.error(f"{fn.__name__} error: {e}", exc_info=True)


def main():
    logger.info("╔══════════════════════════════════════════╗")
    logger.info("║   BB Squeeze Breakout Bot  — Starting    ║")
    logger.info("╚══════════════════════════════════════════╝")
    _check_config()
    threading.Thread(target=_run_scheduler, daemon=True).start()
    logger.info("Starting dashboard on port 8080…")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")


if __name__ == "__main__":
    main()
