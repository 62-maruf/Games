"""Production server settings. Start with:  gunicorn app:app"""
import os

bind = f"{os.environ.get('HOST', '0.0.0.0')}:{os.environ.get('PORT', '5000')}"
workers = 1        # Games live in memory. A second worker would be a separate world where players cannot meet.
threads = int(os.environ.get("THREADS", 100))    # every open WebSocket uses one thread = max players at once
timeout = 120
accesslog = "-"
