"""
memory/habitual_memory.py
==========================
Local, offline habit tracking using SQLite.

Logs every selection with a timestamp. When the user looks at a category,
predict their most likely specific need based on:
  1. Time of day (morning / afternoon / evening / night)
  2. Recent frequency within the current time bucket

No cloud. No LLM. Pure frequency statistics — fast and interpretable.
"""

import sqlite3
import os
import time
from datetime import datetime
from collections import defaultdict


DB_PATH = os.path.join(os.path.dirname(__file__), "habits.db")

# Time-of-day buckets (hour ranges, inclusive start)
TIME_BUCKETS = {
    "morning":   range(5,  12),
    "afternoon": range(12, 17),
    "evening":   range(17, 21),
    "night":     range(21, 24),
}

# Default predictions per category × time bucket
# These are shown before enough data is collected
DEFAULT_PREDICTIONS = {
    "Water / Drink": {
        "morning":   ["Hot coffee", "Green tea", "Water"],
        "afternoon": ["Water", "Iced coffee", "Juice"],
        "evening":   ["Water", "Herbal tea", "Warm milk"],
        "night":     ["Water", "Warm milk", "Chamomile tea"],
    },
    "Food / Eat": {
        "morning":   ["Oatmeal", "Toast", "Eggs"],
        "afternoon": ["Sandwich", "Soup", "Salad"],
        "evening":   ["Dinner", "Rice bowl", "Pasta"],
        "night":     ["Light snack", "Crackers", "Fruit"],
    },
    "Washroom": {
        "morning":   ["Need help now", "Urgently", "Can wait 5 min"],
        "afternoon": ["Need help now", "Can wait 5 min", "Urgently"],
        "evening":   ["Need help now", "Can wait 5 min", "Urgently"],
        "night":     ["Need help now", "Urgently", "Can wait 5 min"],
    },
    "Emergency / Help": {
        "morning":   ["Call caregiver", "I am in pain", "Help me move"],
        "afternoon": ["Call caregiver", "I am in pain", "Help me move"],
        "evening":   ["Call caregiver", "I am in pain", "Help me move"],
        "night":     ["Call caregiver", "I am in pain", "Help me move"],
    },
}


def _time_bucket() -> str:
    hour = datetime.now().hour
    for name, rng in TIME_BUCKETS.items():
        if hour in rng:
            return name
    return "night"  # midnight–5am


class HabitualMemory:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------

    def _init_db(self):
        with self._conn() as cx:
            cx.execute("""
                CREATE TABLE IF NOT EXISTS selections (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    category    TEXT    NOT NULL,
                    specific    TEXT    NOT NULL,
                    time_bucket TEXT    NOT NULL,
                    ts          INTEGER NOT NULL
                )
            """)

    def _conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log_selection(self, category: str, specific: str):
        bucket = _time_bucket()
        with self._conn() as cx:
            cx.execute(
                "INSERT INTO selections (category, specific, time_bucket, ts) VALUES (?,?,?,?)",
                (category, specific, bucket, int(time.time()))
            )

    # ------------------------------------------------------------------
    # Read / predict
    # ------------------------------------------------------------------

    def predict(self, category: str, top_n: int = 3) -> list[str]:
        """
        Returns top_n predicted specific needs for `category` based on
        time-of-day frequency. Falls back to defaults when data is sparse.
        """
        bucket = _time_bucket()

        with self._conn() as cx:
            rows = cx.execute(
                """
                SELECT specific, COUNT(*) as cnt
                FROM   selections
                WHERE  category = ? AND time_bucket = ?
                GROUP  BY specific
                ORDER  BY cnt DESC
                LIMIT  ?
                """,
                (category, bucket, top_n)
            ).fetchall()

        if len(rows) >= top_n:
            return [r[0] for r in rows]

        # Blend learned + defaults
        learned  = [r[0] for r in rows]
        defaults = DEFAULT_PREDICTIONS.get(category, {}).get(bucket, [])
        combined = learned[:]
        for d in defaults:
            if d not in combined:
                combined.append(d)
            if len(combined) >= top_n:
                break
        return combined[:top_n]

    def recent_selections(self, limit: int = 20) -> list[dict]:
        with self._conn() as cx:
            rows = cx.execute(
                "SELECT category, specific, time_bucket, ts FROM selections ORDER BY ts DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [
            {"category": r[0], "specific": r[1], "bucket": r[2],
             "time": datetime.fromtimestamp(r[3]).strftime("%H:%M")}
            for r in rows
        ]

    def clear(self):
        with self._conn() as cx:
            cx.execute("DELETE FROM selections")
