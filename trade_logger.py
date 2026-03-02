"""
CSV trade logger — records every trade event for P&L tracking.
"""
import csv
import logging
import os
from datetime import datetime, timezone

from config import LOG_FILE

logger = logging.getLogger(__name__)

HEADERS = [
    "timestamp", "coin", "event", "side",
    "size", "price", "pnl_usd", "account_equity", "notes",
]


def _ensure_file():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()


def log_event(
    coin: str,
    event: str,                    # OPEN | TP1 | SL | TRAIL_CLOSE | MANUAL_CLOSE
    side: str,
    size: float,
    price: float,
    pnl_usd: float = 0.0,
    account_equity: float = 0.0,
    notes: str = "",
):
    _ensure_file()
    row = {
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "coin":           coin,
        "event":          event,
        "side":           side,
        "size":           size,
        "price":          price,
        "pnl_usd":        round(pnl_usd, 4),
        "account_equity": round(account_equity, 2),
        "notes":          notes,
    }
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writerow(row)
    logger.info(f"TRADE LOG: {row}")
