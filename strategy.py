"""
BB Squeeze Breakout Signal Generator

Entry logic:
  1. BB width (upper - lower) / mid must be at a BB_PERIOD-day low  → squeeze detected
  2. Previous close was inside the bands
  3. Current close breaks ABOVE upper band → LONG  (only if close > EMA200)
     Current close breaks BELOW lower band → SHORT (only if close < EMA200)
  4. Volume > VOL_PERIOD-day average (confirms genuine breakout)

Exit logic (managed in bot.py / monitor loop):
  - Trailing stop: 5% below running candle high (long) / above running candle low (short)
  - Hard SL: 5% from entry price
"""
import pandas as pd
from config import BB_PERIOD, BB_STD, SQUEEZE_PERIOD, VOL_PERIOD, EMA_TREND, SL_PCT, TRAIL_PCT


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Bollinger Bands
    df["bb_mid"]   = df["close"].rolling(BB_PERIOD).mean()
    df["bb_std"]   = df["close"].rolling(BB_PERIOD).std()
    df["bb_upper"] = df["bb_mid"] + BB_STD * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - BB_STD * df["bb_std"]
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    # Squeeze: BB width at N-day low (bands at tightest recently)
    df["squeeze"] = df["bb_width"] == df["bb_width"].rolling(SQUEEZE_PERIOD).min()

    # EMA trend filter
    df["ema200"] = df["close"].ewm(span=EMA_TREND, adjust=False).mean()

    # Volume moving average
    df["vol_ma"] = df["volume"].rolling(VOL_PERIOD).mean()

    return df.dropna()


def get_signal(df: pd.DataFrame) -> dict:
    df = compute_indicators(df)

    # Need at least 2 rows to check prev close vs bands
    if len(df) < 2:
        return _flat("Not enough data")

    last = df.iloc[-1]
    prev = df.iloc[-2]

    close    = float(last["close"])
    bb_upper = float(last["bb_upper"])
    bb_lower = float(last["bb_lower"])
    ema200   = float(last["ema200"])
    vol      = float(last["volume"])
    vol_ma   = float(last["vol_ma"])

    prev_close    = float(prev["close"])
    prev_bb_upper = float(prev["bb_upper"])
    prev_bb_lower = float(prev["bb_lower"])

    # Was there a recent squeeze? Check last SQUEEZE_PERIOD candles
    squeeze_recently = bool(df["squeeze"].iloc[-SQUEEZE_PERIOD:].any())

    # Volume confirmation
    vol_ok = vol > vol_ma

    # Breakout conditions
    broke_up   = prev_close <= prev_bb_upper and close > bb_upper
    broke_down = prev_close >= prev_bb_lower and close < bb_lower

    # Trend filter
    above_ema = close > ema200
    below_ema = close < ema200

    if squeeze_recently and broke_up and above_ema and vol_ok:
        sl_price    = round(close * (1 - SL_PCT), 6)
        trail_start = close  # trail from entry candle close initially
        return {
            "signal":      "LONG",
            "entry":       close,
            "sl_price":    sl_price,
            "trail_high":  close,   # will be updated each candle
            "direction":   "long",
            "reason": (
                f"BB squeeze breakout LONG: close {close:.2f} > BB upper {bb_upper:.2f}, "
                f"above EMA200 {ema200:.2f}, vol {vol/vol_ma:.1f}× avg"
            ),
        }

    if squeeze_recently and broke_down and below_ema and vol_ok:
        sl_price   = round(close * (1 + SL_PCT), 6)
        return {
            "signal":     "SHORT",
            "entry":      close,
            "sl_price":   sl_price,
            "trail_low":  close,    # will be updated each candle
            "direction":  "short",
            "reason": (
                f"BB squeeze breakout SHORT: close {close:.2f} < BB lower {bb_lower:.2f}, "
                f"below EMA200 {ema200:.2f}, vol {vol/vol_ma:.1f}× avg"
            ),
        }

    # Build reason for no signal
    reasons = []
    if not squeeze_recently:
        reasons.append(f"no squeeze (BB width {last['bb_width']:.3f})")
    elif not broke_up and not broke_down:
        reasons.append(f"no breakout (close {close:.2f} inside bands {bb_lower:.2f}–{bb_upper:.2f})")
    elif broke_up and not above_ema:
        reasons.append(f"long blocked by EMA200 (close {close:.2f} < EMA200 {ema200:.2f})")
    elif broke_down and not below_ema:
        reasons.append(f"short blocked by EMA200 (close {close:.2f} > EMA200 {ema200:.2f})")
    elif not vol_ok:
        reasons.append(f"volume too low ({vol/vol_ma:.1f}× avg)")

    return _flat("; ".join(reasons) if reasons else "No signal")


def get_trail_stops(pos: dict, current_high: float, current_low: float) -> dict:
    """
    Update trailing stop based on new candle high/low.
    Returns updated trail_high / trail_low and the active stop price.
    """
    side = pos["side"]

    if side == "long":
        new_trail_high = max(pos.get("trail_high", pos["entry_price"]), current_high)
        stop_price     = round(new_trail_high * (1 - TRAIL_PCT), 6)
        hard_sl        = pos["sl_price"]
        active_stop    = max(stop_price, hard_sl)   # never lower than hard SL
        return {"trail_high": new_trail_high, "active_stop": active_stop}
    else:
        new_trail_low = min(pos.get("trail_low", pos["entry_price"]), current_low)
        stop_price    = round(new_trail_low * (1 + TRAIL_PCT), 6)
        hard_sl       = pos["sl_price"]
        active_stop   = min(stop_price, hard_sl)    # never higher than hard SL
        return {"trail_low": new_trail_low, "active_stop": active_stop}


def _flat(reason: str) -> dict:
    return {"signal": "FLAT", "entry": None, "sl_price": None, "direction": None, "reason": reason}
