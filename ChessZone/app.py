"""ChessZone server: Flask + Socket.IO. Matchmaking and socket events live here, the rules live in game.py.

All games are kept in memory, so run exactly ONE worker process (see gunicorn.conf.py)."""
import os
import random
import re
import threading
import time
import traceback

import chess
from flask import Flask, render_template, request, send_from_directory, url_for
from flask_socketio import SocketIO

import bot
import config as C
from game import Game, opposite

app = Flask(__name__)
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = C.STATIC_CACHE_SECONDS
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins=C.ALLOWED_ORIGINS)

state_lock = threading.RLock()
bot_slots = threading.BoundedSemaphore(C.MAX_BOT_THREADS)
games = {}       # game id -> Game
game_of = {}     # socket id -> game id
waiting = []     # humans waiting for an opponent: {"sid", "name", "since", "prompted"}

CSP = ("default-src 'self'; script-src 'self' https://cdnjs.cloudflare.com; style-src 'self'; "
       "img-src 'self' data:; connect-src 'self' ws: wss:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


# ---------- web pages ----------

@app.context_processor
def asset_helper():
    """{{ asset('app.js') }} -> /static/app.js?v=<file time>, so browsers fetch new files after every update."""
    def asset(name):
        return url_for("static", filename=name, v=int(os.path.getmtime(os.path.join(app.static_folder, name))))
    return {"asset": asset}


@app.after_request
def add_security_headers(response):
    response.headers.update({"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff",
                             "X-Frame-Options": "DENY", "Referrer-Policy": "same-origin"})
    return response


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.ico")


@app.route("/health")
def health():
    return {"status": "ok", "games": len(games), "waiting": len(waiting)}


# ---------- helpers ----------

def clean_name(raw, fallback):
    name = re.sub(r"[^\w \-]", "", str(raw or "")).strip()[:C.MAX_NAME_LEN]
    return name or fallback


def read_dict(data):
    return data if isinstance(data, dict) else {}


def notify(sid, text):
    socketio.emit("notice", {"text": text}, to=sid)


def lobby_info():
    online = sum(1 for g in games.values() if g.mode == "online" and not g.over)
    return {"waiting": len(waiting), "playing": online, "wait": C.WAIT_SECONDS}


def broadcast_lobby():
    socketio.emit("lobby", lobby_info())


def send_game(game):
    for sid in game.humans:
        socketio.emit("game", game.payload(sid), to=sid)


def create_game(mode, seats, names, level="medium"):
    game = Game(mode, seats, names, level)
    games[game.id] = game
    for sid in game.humans:
        game_of[sid] = game.id
    return game


def delete_game(game):
    game.over = True    # stops any computer move that is still being calculated
    games.pop(game.id, None)
    for sid in [s for s, gid in game_of.items() if gid == game.id]:
        del game_of[sid]


def acting_side(game, sid, data):
    """Which side presses a button. On a shared screen the page tells us which player it was."""
    if game.mode == "local":
        side = read_dict(data).get("side")
        return side if side in ("w", "b") else game.turn
    return game.side_of(sid)


def leave_everything(sid):
    waiting[:] = [w for w in waiting if w["sid"] != sid]
    game = games.get(game_of.pop(sid, None))
    if game:
        if game.mode == "online":
            side = game.side_of(sid)
            game.seats[side] = "gone"
            if not game.over:
                game.finish(opposite(side), "opponent left")
            if game.humans:
                send_game(game)
            else:
                delete_game(game)
        else:
            delete_game(game)
    broadcast_lobby()


# ---------- computer opponent ----------

def start_bot_turn_if_needed(game):
    if game.mode == "bot" and not game.over and not game.thinking and game.seats[game.turn] == "bot":
        game.thinking = True
        socketio.start_background_task(run_bot_turn, game.id, len(game.board.move_stack))


def run_bot_turn(game_id, ply):
    """Think in the background; drop the result if the game moved on (rematch, left, resigned) meanwhile."""
    socketio.sleep(C.BOT_THINK_DELAY)
    try:
        with state_lock:
            game = games.get(game_id)
            if not game or game.over or len(game.board.move_stack) != ply:
                return
            position, level = game.board.copy(stack=False), game.level
        with bot_slots:
            try:
                move = bot.choose_move(position, level)
            except Exception:
                traceback.print_exc()
                move = random.choice(list(position.legal_moves))
        with state_lock:
            game = games.get(game_id)
            if not game or game.over or len(game.board.move_stack) != ply:
                return
            game.thinking = False
            game.play(move)
            send_game(game)
    finally:
        with state_lock:
            game = games.get(game_id)
            if game and len(game.board.move_stack) == ply:
                game.thinking = False


# ---------- matchmaking timer ----------

def run_background_loop():
    while True:
        socketio.sleep(1)
        try:
            now = time.time()
            with state_lock:
                for entry in waiting:
                    if not entry["prompted"] and now - entry["since"] >= C.WAIT_SECONDS:
                        entry["prompted"] = True
                        socketio.emit("no_opponent", {}, to=entry["sid"])
        except Exception:
            traceback.print_exc()


# ---------- socket events ----------

@socketio.on("connect")
def on_connect():
    socketio.emit("lobby", lobby_info(), to=request.sid)


@socketio.on("disconnect")
@socketio.on("leave")
@socketio.on("cancel")
def on_leave(*_):
    with state_lock:
        leave_everything(request.sid)


@socketio.on("play_online")
def on_play_online(data):
    sid, data = request.sid, read_dict(data)
    with state_lock:
        leave_everything(sid)
        me = {"sid": sid, "name": clean_name(data.get("name"), "Player"), "since": time.time(), "prompted": False}
        if not waiting:
            waiting.append(me)
            socketio.emit("queued", {"wait": C.WAIT_SECONDS}, to=sid)
            return broadcast_lobby()
        if len(games) >= C.MAX_GAMES:
            return notify(sid, "Server is busy, try again soon.")
        pair = [waiting.pop(0), me]
        random.shuffle(pair)
        if pair[0]["name"].lower() == pair[1]["name"].lower():
            pair[1]["name"] = pair[1]["name"][:C.MAX_NAME_LEN - 2] + " 2"
        game = create_game("online", {"w": pair[0]["sid"], "b": pair[1]["sid"]},
                           {"w": pair[0]["name"], "b": pair[1]["name"]})
        send_game(game)
        broadcast_lobby()


@socketio.on("wait_more")
def on_wait_more():
    with state_lock:
        for entry in waiting:
            if entry["sid"] == request.sid:
                entry["since"], entry["prompted"] = time.time(), False
                socketio.emit("queued", {"wait": C.WAIT_SECONDS}, to=request.sid)


@socketio.on("play_bot")
def on_play_bot(data):
    sid, data = request.sid, read_dict(data)
    level = data.get("level") if data.get("level") in C.BOT_LEVELS else "medium"
    color = data.get("color") if data.get("color") in ("w", "b") else random.choice("wb")
    with state_lock:
        leave_everything(sid)
        if len(games) >= C.MAX_GAMES:
            return notify(sid, "Server is busy, try again soon.")
        names = {color: clean_name(data.get("name"), "Player"), opposite(color): f"Computer ({level.title()})"}
        game = create_game("bot", {color: sid, opposite(color): "bot"}, names, level)
        start_bot_turn_if_needed(game)
        send_game(game)


@socketio.on("play_local")
def on_play_local():
    sid = request.sid
    with state_lock:
        leave_everything(sid)
        if len(games) >= C.MAX_GAMES:
            return notify(sid, "Server is busy, try again soon.")
        send_game(create_game("local", {"w": sid, "b": sid}, {"w": "White", "b": "Black"}))


@socketio.on("move")
def on_move(data):
    sid, data = request.sid, read_dict(data)
    with state_lock:
        game = games.get(game_of.get(sid))
        if not game or game.over or game.seats[game.turn] != sid:
            return
        if not game.make_move(data.get("from"), data.get("to"), data.get("promotion")):
            notify(sid, "That move is not allowed.")
            return send_game(game)
        start_bot_turn_if_needed(game)
        send_game(game)


@socketio.on("resign")
def on_resign(data=None):
    with state_lock:
        game = games.get(game_of.get(request.sid))
        side = acting_side(game, request.sid, data) if game else None
        if side and not game.over:
            game.finish(opposite(side), "resignation")
            send_game(game)


@socketio.on("offer_draw")
def on_offer_draw(data=None):
    with state_lock:
        game = games.get(game_of.get(request.sid))
        side = acting_side(game, request.sid, data) if game else None
        if not side or game.over or game.draw_offer:
            return
        if game.mode == "bot":
            if bot.wants_draw(game.board, chess.BLACK if side == "w" else chess.WHITE):
                game.finish(None, "agreement")
                return send_game(game)
            return notify(request.sid, "The computer declined your draw offer.")
        game.draw_offer = side
        send_game(game)


@socketio.on("draw_response")
def on_draw_response(data):
    with state_lock:
        game = games.get(game_of.get(request.sid))
        if not game or game.over or not game.draw_offer:
            return
        offerer = game.draw_offer
        if game.seats[opposite(offerer)] != request.sid:
            return
        if read_dict(data).get("accept"):
            game.finish(None, "agreement")
        else:
            game.draw_offer = None
            if game.seats[offerer] != request.sid:
                notify(game.seats[offerer], "Your draw offer was declined.")
        send_game(game)


@socketio.on("rematch")
def on_rematch():
    with state_lock:
        game = games.get(game_of.get(request.sid))
        if not game or not game.over or "gone" in game.seats.values():
            return
        game.rematch.add(request.sid)
        if game.humans <= game.rematch:
            if game.mode != "local":    # swap colours for the next game
                game.seats["w"], game.seats["b"] = game.seats["b"], game.seats["w"]
                game.names["w"], game.names["b"] = game.names["b"], game.names["w"]
            game.reset()
            start_bot_turn_if_needed(game)
        send_game(game)


socketio.start_background_task(run_background_loop)

if __name__ == "__main__":
    socketio.run(app, host=C.HOST, port=C.PORT, allow_unsafe_werkzeug=True)   # development server only
