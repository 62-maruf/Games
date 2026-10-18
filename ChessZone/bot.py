import random, time
import chess
import config as C

VALUE = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
MATE, INFINITY = 100000, 10 ** 7


class OutOfTime(Exception):
    pass


def position_bonus(piece_type, square, color, endgame):
    file, rank = chess.square_file(square), chess.square_rank(square)
    if color == chess.BLACK:
        rank = 7 - rank
    centre = 7 - (abs(file - 3.5) + abs(rank - 3.5))  # 6 in the middle, 0 in the corners
    if piece_type == chess.PAWN:
        return rank * 8 + centre * 2
    if piece_type == chess.KNIGHT:
        return centre * 8
    if piece_type == chess.BISHOP:
        return centre * 4
    if piece_type == chess.ROOK:
        return 15 if rank == 6 else 0
    if piece_type == chess.QUEEN:
        return centre
    if endgame:
        return centre * 6
    return 25 if rank == 0 and file in (1, 2, 6) else -centre * 4 + (-20 if rank > 1 else 0)


def evaluate(board):
    """Score in centipawns from White's point of view."""
    endgame, score = not board.queens, 0
    for square, piece in board.piece_map().items():
        value = VALUE[piece.piece_type] + position_bonus(piece.piece_type, square, piece.color, endgame)
        score += value if piece.color == chess.WHITE else -value
    return score


def score_for_side_to_move(board):
    score = evaluate(board)
    return score if board.turn == chess.WHITE else -score


def ordered_moves(board, captures_only=False):
    def importance(move):
        points = VALUE.get(move.promotion, 0)
        if board.is_capture(move):
            victim = board.piece_type_at(move.to_square) or chess.PAWN
            points += 10 * VALUE[victim] - VALUE[board.piece_type_at(move.from_square)]
        return -points
    moves = [m for m in board.legal_moves if not captures_only or board.is_capture(m) or m.promotion]
    return sorted(moves, key=importance)


class Search:
    def __init__(self, deadline):
        self.deadline, self.nodes = deadline, 0

    def count_node(self):
        self.nodes += 1
        if self.nodes % 256 == 0 and time.time() > self.deadline:
            raise OutOfTime

    def quiet_search(self, board, alpha, beta, depth_left=4):
        self.count_node()
        stand_pat = score_for_side_to_move(board)
        if stand_pat >= beta or depth_left == 0:
            return stand_pat
        alpha = max(alpha, stand_pat)
        for move in ordered_moves(board, captures_only=True):
            board.push(move)
            score = -self.quiet_search(board, -beta, -alpha, depth_left - 1)
            board.pop()
            if score >= beta:
                return score
            alpha = max(alpha, score)
        return alpha

    def negamax(self, board, depth, alpha, beta, ply):
        self.count_node()
        moves = ordered_moves(board)
        if not moves:
            return -MATE + ply if board.is_check() else 0
        if depth == 0:
            return self.quiet_search(board, alpha, beta)
        best = -INFINITY
        for move in moves:
            board.push(move)
            score = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1)
            board.pop()
            best = max(best, score)
            alpha = max(alpha, score)
            if alpha >= beta:
                break
        return best


def score_root_moves(board, moves, depth, deadline, exact):
    search, scores, alpha = Search(deadline), {}, -INFINITY
    for move in moves:
        board.push(move)
        if exact:   # full window: every move gets a true score (needed for easy/medium variety)
            score = -search.negamax(board, depth - 1, -INFINITY, INFINITY, 1)
        else:       # narrowing window: faster, only the best move is exact
            score = -search.negamax(board, depth - 1, -INFINITY, -alpha, 1)
        board.pop()
        scores[move] = score
        alpha = max(alpha, score)
    return scores


def choose_move(board, level_name):
    level = C.BOT_LEVELS.get(level_name) or C.BOT_LEVELS["medium"]
    moves = list(board.legal_moves)
    if not moves:
        return None
    if random.random() < level["random_move"]:
        return random.choice(moves)
    deadline, best_scores = time.time() + level["seconds"], None
    board = board.copy(stack=False)
    for depth in range(1, level["depth"] + 1):          # think 1 move deep, then 2, then 3...
        try:
            scores = score_root_moves(board, moves, depth, deadline, exact=level["margin"] > 0)
        except OutOfTime:
            break
        best_scores = scores
        moves = sorted(scores, key=scores.get, reverse=True)  # best first = faster next round
    if not best_scores:
        return random.choice(moves)
    top = max(best_scores.values())
    return random.choice([m for m, s in best_scores.items() if s >= top - level["margin"]])


def wants_draw(board, bot_color):
    score = evaluate(board) * (1 if bot_color == chess.WHITE else -1)
    return score <= C.BOT_DRAW_ACCEPT_BELOW
