"""One chess game: rules, history and the data we send to browsers. No networking in here."""
import uuid

import chess

END_TEXT = {"CHECKMATE": "checkmate", "STALEMATE": "stalemate", "INSUFFICIENT_MATERIAL": "insufficient material",
            "SEVENTYFIVE_MOVES": "75-move rule", "FIFTY_MOVES": "50-move rule",
            "FIVEFOLD_REPETITION": "repetition", "THREEFOLD_REPETITION": "threefold repetition"}


def opposite(side):
    return "b" if side == "w" else "w"


class Game:
    """mode: "online" (two humans), "bot" (human vs computer) or "local" (two humans, one device).
    seats maps "w"/"b" to a socket id, or "bot" / "gone"."""

    def __init__(self, mode, seats, names, level="medium"):
        self.id = uuid.uuid4().hex[:8]
        self.mode, self.seats, self.names, self.level = mode, seats, names, level
        self.rematch = set()
        self.reset()

    def reset(self):
        self.board = chess.Board()
        self.moves, self.taken = [], {"w": [], "b": []}     # taken[side] = piece letters that side captured
        self.last = self.winner = self.draw_offer = None
        self.over = self.thinking = False
        self.reason = ""
        self.rematch = set()

    # ---- who is who ----
    @property
    def turn(self):
        return "w" if self.board.turn == chess.WHITE else "b"

    @property
    def humans(self):
        return {sid for sid in self.seats.values() if sid not in ("bot", "gone")}

    def side_of(self, sid):
        return next((side for side, s in self.seats.items() if s == sid), None)

    # ---- playing ----
    def finish(self, winner, reason):
        self.over, self.winner, self.reason, self.draw_offer, self.thinking = True, winner, reason, None, False

    def play(self, move):
        board, mover = self.board, self.turn
        self.moves.append(board.san(move))
        if board.is_capture(move):
            victim = chess.PAWN if board.is_en_passant(move) else board.piece_type_at(move.to_square)
            self.taken[mover].append(chess.piece_symbol(victim))
        board.push(move)
        self.last, self.draw_offer = [chess.square_name(move.from_square), chess.square_name(move.to_square)], None
        outcome = board.outcome(claim_draw=True)
        if outcome:
            winner = None if outcome.winner is None else "w" if outcome.winner == chess.WHITE else "b"
            self.finish(winner, END_TEXT.get(outcome.termination.name, "draw"))

    def make_move(self, from_sq, to_sq, promotion=None):
        """Play a move sent by a browser. Returns False when it is not legal."""
        try:
            move = chess.Move(chess.parse_square(str(from_sq)), chess.parse_square(str(to_sq)))
        except ValueError:
            return False
        piece = self.board.piece_at(move.from_square)
        if piece and piece.piece_type == chess.PAWN and chess.square_rank(move.to_square) in (0, 7):
            move.promotion = chess.PIECE_SYMBOLS.index(promotion if promotion in ("q", "r", "b", "n") else "q")
        if move not in self.board.legal_moves:
            return False
        self.play(move)
        return True

    # ---- what the browser needs ----
    def legal_table(self):
        table = {}
        for move in self.board.legal_moves:
            table.setdefault(chess.square_name(move.from_square), set()).add(chess.square_name(move.to_square))
        return {square: sorted(targets) for square, targets in table.items()}

    def payload(self, sid):
        board = self.board
        return {"id": self.id, "mode": self.mode, "you": None if self.mode == "local" else self.side_of(sid),
                "names": self.names, "fen": board.fen(), "turn": self.turn,
                "legal": {} if self.over else self.legal_table(), "last": self.last,
                "check": chess.square_name(board.king(board.turn)) if board.is_check() else None,
                "moves": self.moves, "taken": self.taken, "over": self.over, "winner": self.winner,
                "reason": self.reason, "thinking": self.thinking, "draw_offer": self.draw_offer,
                "rematch_me": sid in self.rematch, "rematch_other": bool(self.rematch - {sid}),
                "opponent_gone": self.mode == "online" and "gone" in self.seats.values()}
