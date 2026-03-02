"""
Hyperliquid API client wrapper.
Handles candle fetching, order placement, position queries,
and leverage management.
"""
import time
import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from config import HL_API_URL, HL_PRIVATE_KEY, HL_WALLET_ADDRESS, LEVERAGE

logger = logging.getLogger(__name__)


def _get_clients():
    """Lazy-init HL clients (avoids import errors if SDK not yet installed)."""
    from hyperliquid.info import Info
    from hyperliquid.exchange import Exchange
    import eth_account

    info = Info(HL_API_URL, skip_ws=True)

    if not HL_PRIVATE_KEY:
        raise ValueError("HL_PRIVATE_KEY environment variable not set")
    wallet = eth_account.Account.from_key(HL_PRIVATE_KEY)
    exchange = Exchange(wallet, HL_API_URL)

    return info, exchange


# ── Market data ───────────────────────────────────────────────────────────────

def fetch_candles(coin: str, lookback: int = 60) -> pd.DataFrame:
    """
    Fetch the last `lookback` daily candles for `coin`.
    Returns DataFrame with columns: open, high, low, close, volume, timestamp
    """
    info, _ = _get_clients()

    end_ms   = int(time.time() * 1000)
    start_ms = end_ms - lookback * 24 * 3600 * 1000  # lookback days back

    candles = info.candles_snapshot(coin, "1d", start_ms, end_ms)

    if not candles:
        raise ValueError(f"No candle data returned for {coin}")

    rows = []
    for c in candles:
        rows.append({
            "timestamp": datetime.fromtimestamp(c["T"] / 1000, tz=timezone.utc),
            "open":      float(c["o"]),
            "high":      float(c["h"]),
            "low":       float(c["l"]),
            "close":     float(c["c"]),
            "volume":    float(c["v"]),
        })

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    logger.info(f"{coin}: fetched {len(df)} candles, last close {df['close'].iloc[-1]:.4f}")
    return df


# ── Account state ─────────────────────────────────────────────────────────────

def get_account_equity() -> float:
    """Return total account equity in USD."""
    info, _ = _get_clients()
    state = info.user_state(HL_WALLET_ADDRESS)
    return float(state["marginSummary"]["accountValue"])


def get_open_positions() -> dict:
    """
    Return dict of currently open perp positions keyed by coin.
    Each value: {"side": "long"|"short", "size": float, "entry": float,
                 "unrealized_pnl": float, "liquidation_px": float}
    """
    info, _ = _get_clients()
    state = info.user_state(HL_WALLET_ADDRESS)

    positions = {}
    for p in state.get("assetPositions", []):
        pos = p.get("position", {})
        sz  = float(pos.get("szi", 0))
        if sz == 0:
            continue
        coin = pos["coin"]
        positions[coin] = {
            "side":           "long" if sz > 0 else "short",
            "size":           abs(sz),
            "entry":          float(pos.get("entryPx", 0)),
            "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
            "liquidation_px": float(pos.get("liquidationPx") or 0),
        }
    return positions


def get_open_orders(coin: str) -> list:
    """Return list of open orders for a coin."""
    info, _ = _get_clients()
    orders = info.open_orders(HL_WALLET_ADDRESS)
    return [o for o in orders if o.get("coin") == coin]


# ── Leverage ──────────────────────────────────────────────────────────────────

def set_leverage(coin: str, lev: int = LEVERAGE):
    """Set isolated leverage for a coin."""
    _, exchange = _get_clients()
    result = exchange.update_leverage(lev, coin, is_cross=False)
    logger.info(f"{coin}: leverage set to {lev}× — {result}")
    return result


# ── Orders ────────────────────────────────────────────────────────────────────

def market_open(coin: str, is_buy: bool, size: float, slippage: float = 0.002) -> dict:
    """Open a position with a market order."""
    _, exchange = _get_clients()
    result = exchange.market_open(coin, is_buy, size, slippage=slippage)
    logger.info(f"{coin}: market_open is_buy={is_buy} size={size} → {result}")
    return result


def place_limit_order(
    coin: str,
    is_buy: bool,
    size: float,
    price: float,
    reduce_only: bool = False,
) -> dict:
    """Place a GTC limit order (used for TP1)."""
    _, exchange = _get_clients()
    order_type = {"limit": {"tif": "Gtc"}}
    result = exchange.order(coin, is_buy, size, price, order_type, reduce_only=reduce_only)
    logger.info(f"{coin}: limit is_buy={is_buy} size={size} px={price} ro={reduce_only} → {result}")
    return result


def place_stop_market(
    coin: str,
    is_buy: bool,
    size: float,
    trigger_price: float,
    reduce_only: bool = True,
) -> dict:
    """
    Place a stop-market order (used for SL).
    Hyperliquid uses trigger orders for stops.
    """
    _, exchange = _get_clients()
    # HL stop-market: orderType = {"trigger": {"triggerPx": px, "isMarket": True, "tpsl": "sl"}}
    order_type = {
        "trigger": {
            "triggerPx": trigger_price,
            "isMarket":  True,
            "tpsl":      "sl",
        }
    }
    result = exchange.order(coin, is_buy, size, trigger_price, order_type, reduce_only=reduce_only)
    logger.info(f"{coin}: stop_market trigger={trigger_price} size={size} → {result}")
    return result


def cancel_order(coin: str, order_id: int) -> dict:
    """Cancel a specific order by ID."""
    _, exchange = _get_clients()
    result = exchange.cancel(coin, order_id)
    logger.info(f"{coin}: cancelled order {order_id} → {result}")
    return result


def cancel_all_orders(coin: str):
    """Cancel all open orders for a coin."""
    info, exchange = _get_clients()
    orders = info.open_orders(HL_WALLET_ADDRESS)
    for o in orders:
        if o.get("coin") == coin:
            try:
                exchange.cancel(coin, o["oid"])
                logger.info(f"{coin}: cancelled order {o['oid']}")
            except Exception as e:
                logger.warning(f"{coin}: failed to cancel {o['oid']}: {e}")


def market_close(coin: str, size: float, is_long: bool, slippage: float = 0.002) -> dict:
    """Market-close a position (reduce_only)."""
    _, exchange = _get_clients()
    # To close a long we sell; to close a short we buy
    result = exchange.market_open(coin, not is_long, size, slippage=slippage)
    logger.info(f"{coin}: market_close size={size} → {result}")
    return result
