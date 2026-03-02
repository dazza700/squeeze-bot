"""Position sizing for Channel Breakout — fixed fractional, no TP."""
import math
from config import LEVERAGE, RISK_PCT, SL_PCT, MIN_NOTIONAL_USD, get_precision


def calc_position(account_equity: float, entry_price: float, coin: str) -> dict:
    risk_usd     = account_equity * RISK_PCT
    notional_usd = risk_usd / SL_PCT
    collateral   = notional_usd / LEVERAGE

    if notional_usd < MIN_NOTIONAL_USD:
        return None

    precision = get_precision(coin)
    size_coin = math.floor((notional_usd / entry_price) * 10**precision) / 10**precision

    if size_coin <= 0:
        return None

    sl_price = round(entry_price * (1 - SL_PCT), precision + 2)

    return {
        "notional_usd": round(notional_usd, 2),
        "collateral":   round(collateral, 2),
        "size_coin":    size_coin,
        "sl_price":     sl_price,
    }
