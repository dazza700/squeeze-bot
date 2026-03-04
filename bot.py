"""
BB Squeeze Breakout Bot — Core Logic

Daily scan  : detect BB squeeze + breakout + EMA200 + volume → enter LONG or SHORT
15-min monitor: update trailing stop each candle, exit if breached
"""
import logging
from typing import Optional

import hl_client as hl
import trade_logger as tlog
from config import TOKENS, LEVERAGE, MAX_CONCURRENT, CANDLE_LOOKBACK, SL_PCT, TRAIL_PCT
from position_manager import PositionManager
from risk import calc_position
from strategy import get_signal, get_trail_stops

logger = logging.getLogger(__name__)
pm = PositionManager()


def daily_signal_scan():
    logger.info("=" * 60)
    logger.info("BB SQUEEZE — DAILY SIGNAL SCAN")
    logger.info("=" * 60)

    try:
        equity = hl.get_account_equity()
        logger.info(f"Account equity: ${equity:.2f}")
    except Exception as e:
        logger.error(f"Could not fetch equity: {e}")
        return

    open_count = pm.position_count()

    for coin in TOKENS:
        logger.info(f"── Scanning {coin} ──")

        if pm.has_position(coin):
            logger.info(f"{coin}: already in position — trail stop managed in monitor")
            continue

        if open_count >= MAX_CONCURRENT:
            logger.info(f"Max positions reached ({MAX_CONCURRENT})")
            break

        try:
            df     = hl.fetch_candles(coin, CANDLE_LOOKBACK)
            signal = get_signal(df)
        except Exception as e:
            logger.error(f"{coin}: signal error — {e}")
            continue

        logger.info(f"{coin}: {signal['signal']} — {signal['reason']}")

        if signal["signal"] not in ("LONG", "SHORT"):
            continue

        is_long  = signal["signal"] == "LONG"
        sizing   = calc_position(equity, signal["entry"], coin)
        if sizing is None:
            logger.warning(f"{coin}: position too small, skipping")
            continue

        # Set leverage
        try:
            hl.set_leverage(coin, LEVERAGE)
        except Exception as e:
            logger.error(f"{coin}: set leverage failed — {e}")
            continue

        # Enter market order
        try:
            result      = hl.market_open(coin, is_long, sizing["size_coin"])
            fill_price  = float(
                result["response"]["data"]["statuses"][0]
                .get("filled", {}).get("avgPx", signal["entry"])
            )
        except Exception as e:
            logger.error(f"{coin}: entry failed — {e}")
            continue

        # Recalculate sl_price based on actual fill and correct direction
        actual_sl = round(
            fill_price * (1 - SL_PCT) if is_long else fill_price * (1 + SL_PCT), 6
        )

        # Place hard SL stop order (use actual_sl so direction is always correct)
        try:
            sl_res = hl.place_stop_market(
                coin,
                is_buy        = not is_long,   # sell to close long / buy to close short
                size          = sizing["size_coin"],
                trigger_price = actual_sl,     # correct for both long and short
            )
        except Exception as e:
            logger.warning(f"{coin}: SL order failed — {e}")

        pm.open_position(
            coin         = coin,
            size         = sizing["size_coin"],
            entry_price  = fill_price,
            sl_price     = actual_sl,
            trail_stop   = None,            # trail managed via trail_high/trail_low
            notional_usd = sizing["notional_usd"],
            side         = "long" if is_long else "short",
            trail_high   = fill_price,      # start trailing from entry
            trail_low    = fill_price,
        )

        tlog.log_event(
            coin, "OPEN", "long" if is_long else "short",
            sizing["size_coin"], fill_price,
            account_equity=equity, notes=signal["reason"]
        )

        open_count += 1
        logger.info(f"{coin}: ✓ squeeze entry {'LONG' if is_long else 'SHORT'} @ {fill_price:.4f}")


def monitor_positions():
    """
    Runs every 15 minutes.
    Fetches latest candle, updates trailing stop, exits if breached.
    """
    positions = pm.all_positions()
    if not positions:
        return

    logger.info(f"Monitoring {len(positions)} squeeze position(s)")

    try:
        equity = hl.get_account_equity()
    except Exception:
        equity = 0.0

    try:
        live_positions = hl.get_open_positions()
    except Exception as e:
        logger.error(f"Could not fetch live positions: {e}")
        return

    for coin, pos in list(positions.items()):
        live = live_positions.get(coin)

        # Position closed externally
        if live is None:
            logger.info(f"{coin}: no longer open on HL — recording external close")
            # FIX: Use real price + compute PnL instead of logging price=0.0
            is_long = pos.get("side", "long") == "long"
            close_price, pnl = 0.0, 0.0
            try:
                close_price = hl.get_mid_price(coin)
                pnl = (close_price - pos["entry_price"]) / pos["entry_price"] * pos["notional_usd"]
                if not is_long:
                    pnl = -pnl
            except Exception:
                pass
            tlog.log_event(coin, "EXTERNAL_CLOSE", pos.get("side","long"),
                           pos["size"], close_price, pnl, account_equity=equity,
                           notes="Closed externally")
            pm.close_position(coin)
            continue

        # Get latest candle high/low for trailing stop update (daily H/L is correct here)
        # FIX: Also get real-time mid price separately for hard SL breach check
        try:
            df            = hl.fetch_candles(coin, lookback=5)
            current_high  = float(df["high"].iloc[-1])
            current_low   = float(df["low"].iloc[-1])
            current_price = float(df["close"].iloc[-1])
        except Exception:
            current_price = float(live.get("entry", pos["entry_price"]))
            current_high  = current_price
            current_low   = current_price

        # Use real-time mid price for the actual SL breach check
        try:
            current_price = hl.get_mid_price(coin)
        except Exception:
            pass  # fall back to daily candle close

        side = pos.get("side", "long")
        sl   = pos["sl_price"]

        # Update trailing stop
        trail_update = get_trail_stops(pos, current_high, current_low)
        active_stop  = trail_update["active_stop"]

        # Update stored trail high/low
        if "trail_high" in trail_update:
            pm.update_field(coin, "trail_high", trail_update["trail_high"])
        if "trail_low" in trail_update:
            pm.update_field(coin, "trail_low", trail_update["trail_low"])
        pm.update_field(coin, "trail_stop", active_stop)

        # Check exit condition
        if side == "long":
            if current_price <= active_stop:
                event = "SL" if current_price <= sl else "TRAIL_STOP"
                logger.info(f"{coin}: {event} hit (price={current_price:.4f} stop={active_stop:.4f})")
                _close_position(coin, pos, current_price, equity, event, is_long=True)
        else:  # short
            if current_price >= active_stop:
                event = "SL" if current_price >= sl else "TRAIL_STOP"
                logger.info(f"{coin}: {event} hit (price={current_price:.4f} stop={active_stop:.4f})")
                _close_position(coin, pos, current_price, equity, event, is_long=False)


def _close_position(coin, pos, price, equity, event, is_long: bool):
    try:
        hl.cancel_all_orders(coin)
        hl.market_close(coin, pos["size"], is_long)
    except Exception as e:
        logger.error(f"{coin}: close failed — {e}")
        return

    entry = pos["entry_price"]
    if is_long:
        pnl = (price - entry) / entry * pos["notional_usd"]
    else:
        pnl = (entry - price) / entry * pos["notional_usd"]

    tlog.log_event(coin, event, "long" if is_long else "short",
                   pos["size"], price, pnl, equity)
    pm.close_position(coin)
