"""
BB Squeeze Breakout Strategy Configuration
Hyperliquid Perpetuals — Live Trading Bot
"""
import os

# ── Tokens ──────────────────────────────────────────────────────────────────
TOKENS = ["SOL", "AVAX", "ADA"]

# ── Account & Risk ───────────────────────────────────────────────────────────
LEVERAGE         = 3           # 3× isolated leverage (conservative)
RISK_PCT         = 0.33        # Up to 1/3 of account per trade (1 position max)
SL_PCT           = 0.05        # Hard stop-loss: 5% from entry price
TRAIL_PCT        = 0.05        # Trailing stop: 5% from candle high/low
MIN_NOTIONAL_USD = 15.0
MAX_CONCURRENT   = 1           # One position at a time (squeeze = high conviction)

# ── Strategy Parameters ──────────────────────────────────────────────────────
BB_PERIOD        = 20          # Bollinger Band period
BB_STD           = 2.0         # Bollinger Band std dev multiplier
SQUEEZE_PERIOD   = 20          # BB width must be at N-day low to count as squeeze
VOL_PERIOD       = 20          # Volume must exceed N-day avg
EMA_TREND        = 200         # Only trade in direction of EMA200
CANDLE_LOOKBACK  = 250         # Daily candles to fetch (need 200 for EMA200)

# ── Scheduling ───────────────────────────────────────────────────────────────
SIGNAL_CHECK_UTC = "00:15"     # 5 mins after Breakout bot (00:10) to avoid conflicts
POSITION_CHECK_M = 15          # Monitor every 15 mins

# ── Hyperliquid ──────────────────────────────────────────────────────────────
HL_MAINNET_URL    = "https://api.hyperliquid.xyz"
HL_TESTNET_URL    = "https://api.hyperliquid-testnet.xyz"
USE_MAINNET       = os.getenv("HL_MAINNET", "true").lower() == "true"
HL_API_URL        = HL_MAINNET_URL if USE_MAINNET else HL_TESTNET_URL
HL_PRIVATE_KEY    = os.getenv("HL_PRIVATE_KEY", "")
HL_WALLET_ADDRESS = os.getenv("HL_WALLET_ADDRESS", "")

# ── State ────────────────────────────────────────────────────────────────────
STATE_FILE = "positions.json"
LOG_FILE   = "trades.csv"

COIN_PRECISION = {"SOL": 3, "AVAX": 3, "ADA": 1, "BTC": 5, "ETH": 4}

def get_precision(coin: str) -> int:
    return COIN_PRECISION.get(coin, 3)
