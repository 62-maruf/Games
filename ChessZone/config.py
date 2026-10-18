"""Settings. Everything can be overridden with environment variables (see README)."""
import os

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 5000))

# Origins allowed to open a WebSocket. Empty = same origin only (safest default).
# Use ALLOWED_ORIGINS="https://chess.example.com" or "*" if you really need it.
_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
ALLOWED_ORIGINS = "*" if _origins == "*" else ([o.strip() for o in _origins.split(",") if o.strip()] or None)

STATIC_CACHE_SECONDS = int(os.environ.get("STATIC_CACHE_SECONDS", 86400))  # file URLs change when files change

MAX_NAME_LEN = 14
MAX_GAMES = int(os.environ.get("MAX_GAMES", 200))
MAX_BOT_THREADS = int(os.environ.get("MAX_BOT_THREADS", 4))   # computer moves calculated at the same time

# How long a player waits for another human before being asked "play the computer instead?"
WAIT_SECONDS = 20

# Computer opponent: depth = moves looked ahead, seconds = max thinking time,
# random_move = chance of a deliberately random move, margin = picks randomly among near-best moves
BOT_LEVELS = {
    "easy":   {"depth": 1, "seconds": 1.0, "random_move": 0.25, "margin": 120},
    "medium": {"depth": 2, "seconds": 2.0, "random_move": 0.0,  "margin": 15},
    "hard":   {"depth": 4, "seconds": 3.0, "random_move": 0.0,  "margin": 8},
}
BOT_THINK_DELAY = 0.6          # small pause so the computer does not answer instantly
BOT_DRAW_ACCEPT_BELOW = -150   # computer accepts a draw offer when it is this far behind (centipawns)
