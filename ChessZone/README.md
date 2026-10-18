# ChessZone

Real-time chess: play online, against the computer, or face to face on one device.
Flask + Flask-SocketIO on the server, plain HTML/CSS/JS in the browser (no build step).

## Run it (development)
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000. To test online play with one computer, open the page in two browser tabs.
To let phones on your Wi-Fi join: `HOST=0.0.0.0 python app.py`, then open `http://<your-computer-ip>:5000`.

## Run it (production)
    gunicorn app:app          # settings are in gunicorn.conf.py
or with Docker:

    docker build -t chesszone .
    docker run -p 5000:5000 chesszone

**Use exactly one worker.** All games live in memory, so a second worker would split players into separate
worlds. One worker with 100 threads (`THREADS=…`) handles a few hundred players on a small server.

Put it behind HTTPS (nginx, Caddy, or your host's proxy). WebSockets must be allowed through, for nginx:

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

`/health` returns `{"status": "ok"}` for uptime checks.

## Settings (environment variables)
| Variable | Default | Meaning |
|---|---|---|
| `HOST` / `PORT` | `127.0.0.1` / `5000` | where `python app.py` listens (gunicorn defaults to `0.0.0.0`) |
| `ALLOWED_ORIGINS` | same origin only | comma-separated list, or `*`. Set it if the browser console shows a CORS/origin error behind a proxy |
| `THREADS` | `100` | gunicorn threads = max simultaneous players |
| `MAX_GAMES` | `200` | new games are refused above this |
| `MAX_BOT_THREADS` | `4` | computer moves calculated at the same time |
| `STATIC_CACHE_SECONDS` | `86400` | browser cache for CSS/JS/images (URLs change automatically when a file changes) |

Computer levels, the matchmaking wait time and other game settings are in `config.py`.

## Player settings (gear icon)
The gear icon (home page, and next to the game status) opens the settings panel. Choices are saved in the
player's own browser (`localStorage`), so they are remembered next time:
- **Board:** move suggestions (dots), highlight last move, show coordinates
- **Audio:** sound effects and background music, each with its own volume

All sounds and the music are generated in the browser with the Web Audio API (`static/sound.js`),
so there are no audio files to host. Browsers only allow audio after the first tap, so music begins then.
Defaults (suggestions on, sound on, music off) are in `DEFAULTS` at the top of the settings section in `static/app.js`.

## Project structure
    app.py                 server: pages, security headers, matchmaking, socket events
    game.py                one game: rules, history, data sent to browsers (no networking)
    bot.py                 computer opponent (minimax + alpha-beta, time limited)
    config.py              settings
    templates/index.html   the page (home, board, dialogs)
    templates/_pieces.svg  the 6 chess piece drawings + lighting, shared by both colours
    static/style.css       white UI + marble board
    static/app.js          browser logic (board, game, settings)
    static/sound.js        sound effects + music (Web Audio, no files)
    static/                logo.svg, favicon, app icons, manifest
    tests/test_game.py     rule tests (python -m pytest)

## Customising
- **Logo / icons:** edit `static/logo.svg` (copy to `favicon.svg`), then re-export the PNG sizes.
- **Board colours:** `.sq.dark` and the `#board` background in `static/style.css`.
- **Sounds / music:** `EFFECTS` and `CHORDS` in `static/sound.js`.
- **Pieces:** each is one `<symbol>` in `templates/_pieces.svg`. The same drawing is filled white or black by `app.js`.
  On very old phones you can delete the `filter="url(#bevel)"` part in `app.js` for flatter, faster pieces.
- **Socket.IO** is loaded from cdnjs (version pinned). To self-host it, put `socket.io.min.js` in `static/`,
  change the `<script>` in `index.html`, and remove `https://cdnjs.cloudflare.com` from `CSP` in `app.py`.
