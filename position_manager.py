"""
Position state manager for BB Squeeze bot.
Supports both long and short positions, trail_high/trail_low tracking.
"""
import json, logging, os
from datetime import datetime, timezone
from typing import Optional
from config import STATE_FILE

logger = logging.getLogger(__name__)


class PositionManager:
    def __init__(self):
        self._state: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    self._state = json.load(f)
                logger.info(f"Loaded positions: {list(self._state.keys())}")
            except Exception as e:
                logger.warning(f"Could not load state: {e}")
                self._state = {}

    def _save(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self._state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def has_position(self, coin: str) -> bool:
        return coin in self._state and self._state[coin].get("side") is not None

    def get(self, coin: str) -> Optional[dict]:
        return self._state.get(coin)

    def all_positions(self) -> dict:
        return {k: v for k, v in self._state.items() if v.get("side") is not None}

    def position_count(self) -> int:
        return len(self.all_positions())

    def open_position(self, coin, size, entry_price, sl_price, trail_stop,
                      notional_usd, side="long", trail_high=None, trail_low=None):
        self._state[coin] = {
            "coin":         coin,
            "side":         side,
            "size":         size,
            "entry_price":  entry_price,
            "sl_price":     sl_price,
            "trail_stop":   trail_stop,
            "trail_high":   trail_high or entry_price,
            "trail_low":    trail_low  or entry_price,
            "notional_usd": notional_usd,
            "opened_at":    datetime.now(timezone.utc).isoformat(),
        }
        self._save()
        logger.info(f"{coin}: position opened — {side} {size} @ {entry_price}, sl={sl_price}")

    def update_field(self, coin: str, field: str, value):
        """Update any field in a position (used for trail_high, trail_low, trail_stop)."""
        if coin in self._state:
            self._state[coin][field] = value
            self._save()

    def close_position(self, coin: str):
        if coin in self._state:
            pos = self._state.pop(coin)
            self._save()
            logger.info(f"{coin}: position removed from state")
            return pos
        return None
