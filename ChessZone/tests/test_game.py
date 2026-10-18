"""Run from the project folder:  pip install pytest && python -m pytest"""
import chess

from game import Game


def local_game():
    return Game("local", {"w": "s", "b": "s"}, {"w": "White", "b": "Black"})


def play(game, *moves):
    for from_sq, to_sq in moves:
        assert game.make_move(from_sq, to_sq), f"{from_sq}{to_sq} should be legal"


def test_start_position():
    game = local_game()
    assert game.turn == "w" and not game.over
    assert len(game.legal_table()) == 10          # 8 pawns + 2 knights can move


def test_illegal_and_invalid_moves_are_rejected():
    game = local_game()
    assert not game.make_move("e2", "e5")
    assert not game.make_move("zz", "e4")
    assert not game.make_move(None, None)
    assert game.moves == []


def test_fools_mate_ends_the_game():
    game = local_game()
    play(game, ("f2", "f3"), ("e7", "e5"), ("g2", "g4"), ("d8", "h4"))
    assert game.over and game.winner == "b" and game.reason == "checkmate"
    assert game.moves[-1] == "Qh4#"
    assert game.payload("s")["legal"] == {}


def test_captures_are_tracked():
    game = local_game()
    play(game, ("e2", "e4"), ("d7", "d5"), ("e4", "d5"))
    assert game.taken == {"w": ["p"], "b": []}


def test_promotion_defaults_to_queen_and_can_be_chosen():
    game = local_game()
    game.board = chess.Board("8/P6k/8/8/8/8/7K/8 w - - 0 1")
    assert game.make_move("a7", "a8", "n")
    assert game.board.piece_at(chess.A8).piece_type == chess.KNIGHT

    game.board = chess.Board("8/P6k/8/8/8/8/7K/8 w - - 0 1")
    assert game.make_move("a7", "a8")
    assert game.board.piece_at(chess.A8).piece_type == chess.QUEEN


def test_payload_tells_each_player_their_colour():
    game = Game("online", {"w": "alice", "b": "bob"}, {"w": "Alice", "b": "Bob"})
    assert game.payload("alice")["you"] == "w"
    assert game.payload("bob")["you"] == "b"
    assert local_game().payload("s")["you"] is None


def test_reset_starts_a_fresh_game():
    game = local_game()
    play(game, ("e2", "e4"))
    game.reset()
    assert game.moves == [] and game.board.fen() == chess.STARTING_FEN
