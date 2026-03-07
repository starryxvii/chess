# consoleMode.py

from bot import botMove, scoreMoveForEnemy
from gameLogic import (
    newBoard, isKingSafe, detectCheckmate, detectStalemate, moveValidate, movePiece,
    findSquare, castle, promotePawn, checkCheckmateOrStalemate, castleValidate,
    castle_start_positions
)

from colorama import init as colorama_init, Fore, Style
colorama_init(autoreset=True)

import sys
from typing import Optional, Tuple

# -------------------------------
# Helpers
# -------------------------------

FILES = "abcdefgh"

def index_to_square(idx: int) -> str:
    row = 7 - (idx // 8)
    col = idx % 8
    return f"{FILES[col]}{row+1}"

def _piece_color(piece: str) -> str:
    """Return a color code based on piece kind & side (bot=upper / player=lower)."""
    if piece.isupper():  # bot pieces
        kind = piece[0]
        if kind == 'K': return Fore.RED + Style.BRIGHT
        if kind == 'Q': return Fore.RED
        if kind == 'B': return Fore.MAGENTA
        if kind == 'N': return Fore.LIGHTMAGENTA_EX + Style.BRIGHT
        if kind == 'R': return Fore.LIGHTYELLOW_EX + Style.BRIGHT
        if kind == 'P': return Fore.YELLOW
    else:               # player pieces
        kind = piece[0]
        if kind == 'k': return Fore.GREEN + Style.BRIGHT
        if kind == 'q': return Fore.GREEN
        if kind == 'b': return Fore.CYAN
        if kind == 'n': return Fore.LIGHTCYAN_EX + Style.BRIGHT
        if kind == 'r': return Fore.LIGHTBLUE_EX + Style.BRIGHT
        if kind == 'p': return Fore.BLUE
    return ""

def print_board(board) -> None:
    """Pretty print with colors (no external fonts)."""
    hr = "  +---"*8 + "+"
    print()
    for r in range(8):
        row_label = str(8 - r)
        print(hr)
        cells = []
        for c in range(8):
            piece = board[r*8 + c]
            if piece:
                color = _piece_color(piece)
                disp = (color + piece.rjust(3) + Style.RESET_ALL)
            else:
                disp = "  ".rjust(3)
            cells.append(disp)
        print(row_label + " |" + "|".join(cells) + "|")
    print(hr)
    print("    a   b   c   d   e   f   g   h\n")

def parse_move_input(user_text: str, board, turn: str) -> Optional[Tuple[str, int, str]]:
    """
    Parse user input to (piece_name, dest_index, raw_dest_display).
    Supports:
      - 'p2 e4'
      - 'e2 e4' (auto-detect piece at source square)
      - 'castle'
    """
    s = user_text.strip().lower()
    if s == "castle":
        return ("__castle__", -1, "castle")

    parts = s.split()
    if len(parts) != 2:
        return None

    a, b = parts[0], parts[1]

    # Try "piece dest" first (piece name string exists on board)
    if any(p == a for p in board if p):
        piece_name = None
        for p in board:
            if p == a:
                piece_name = p
                break
        dest_idx = findSquare(b) if not b.isdigit() else int(b)
        if dest_idx is False:
            return None
        return (piece_name, dest_idx, b)

    # Try "src_square dest"
    src_idx = findSquare(a) if not a.isdigit() else int(a)
    if src_idx is False or src_idx < 0 or src_idx >= 64:
        return None
    piece = board[src_idx]
    if not piece or not piece[0].islower():  # must be player's piece (lowercase)
        return None

    dest_idx = findSquare(b) if not b.isdigit() else int(b)
    if dest_idx is False:
        return None
    return (piece, dest_idx, b)

def promotion_needed(piece: str, dest_idx: int) -> bool:
    return piece[0].lower() == 'p' and (dest_idx // 8 in (0, 7))

def prompt_promotion() -> str:
    while True:
        choice = input("Promote pawn to (QUEEN/ROOK/BISHOP/KNIGHT) [default QUEEN]: ").strip().upper()
        if choice == "":
            return "QUEEN"
        if choice in ("QUEEN", "ROOK", "BISHOP", "KNIGHT"):
            return choice
        print("Invalid choice. Please type one of: QUEEN, ROOK, BISHOP, KNIGHT.")

def adjust_prune_rate(skill_score: float, base: float = 0.30) -> float:
    return max(0.10, min(1.00, base - (skill_score / 100.0)))


def _new_castling_rights():
    return {"player": True, "bot": True}


def _update_castling_rights(castling_rights, botWhite, board_before, board_after):
    rights = dict(castling_rights)
    for side in ("player", "bot"):
        if not rights.get(side, False):
            continue
        layout = castle_start_positions(botWhite, side)
        king_piece, king_pos = layout["king"]
        rook_piece, rook_pos = layout["rook"]
        if board_before[king_pos] != king_piece or board_after[king_pos] != king_piece:
            rights[side] = False
            continue
        if board_before[rook_pos] != rook_piece or board_after[rook_pos] != rook_piece:
            rights[side] = False
    return rights

# -------------------------------
# Game loop
# -------------------------------

def startGame(botWhite: bool = True):
    board = newBoard(botWhite)
    gameStates = [board]
    castlingRights = _new_castling_rights()
    turn = "bot" if botWhite else "player"
    other = "player" if turn == "bot" else "bot"
    pruneRate = 0.30

    print("\nWelcome to Console Chess!")
    print("Type moves like: 'p2 e4' or 'e2 e4'. Type 'castle' to castle, 'help' for help, 'quit' to exit.")

    # If bot starts, make its opening move
    if turn == "bot":
        mv = botMove(board, turn, gameStates, botWhite, pruneRate=pruneRate)
        if mv is not None and isKingSafe(mv, turn):
            castlingRights = _update_castling_rights(castlingRights, botWhite, board, mv)
            board = mv
            gameStates.append(board)
            turn, other = other, turn

    while True:
        print_board(board)
        print(f"Turn: {turn.upper()}")

        if not isKingSafe(board, turn):
            if detectCheckmate(board, turn, botWhite, gameStates):
                winner = "bot" if turn == 'player' else "player"
                print(f"Checkmate! {winner.upper()} wins.")
                break
            print("Check!")

        if detectStalemate(board, turn, botWhite, gameStates):
            print("Stalemate! Game over.")
            break

        if turn == "bot":
            mv = botMove(board, turn, gameStates, botWhite, pruneRate=pruneRate)
            if mv is not None and isKingSafe(mv, turn):
                castlingRights = _update_castling_rights(castlingRights, botWhite, board, mv)
                board = mv
                gameStates.append(board)
                outcome = checkCheckmateOrStalemate(board, 'bot', botWhite, gameStates)
                if outcome == 'checkmate':
                    print_board(board)
                    print("Checkmate! BOT wins.")
                    break
                if outcome == 'stalemate':
                    print_board(board)
                    print("Stalemate! Game over.")
                    break
                turn, other = other, turn
                continue
            else:
                print("Bot has no legal moves.")
                break

        # Player move
        user = input("Your move: ").strip()
        if user.lower() in ("q", "quit", "exit"):
            print("Goodbye!")
            break
        if user.lower() in ("h", "help"):
            print("Examples:\n  p2 e4  -> move piece named p2 to e4\n  e2 e4  -> move piece on e2 to e4\n  castle -> attempt to castle (if legal)")
            continue

        parsed = parse_move_input(user, board, turn)
        if not parsed:
            print("Couldn't parse that. Try 'p2 e4' or 'e2 e4' or 'castle'.")
            continue

        piece, dest_idx, _ = parsed

        if piece == "__castle__":
            if not castleValidate(botWhite, turn, board, castlingRights):
                print("Castling not allowed in current position.")
                continue
            newb = castle(turn, board, botWhite)
            if newb != board:
                castlingRights = _update_castling_rights(castlingRights, botWhite, board, newb)
                board = newb
                gameStates.append(board)
                turn, other = other, turn
            else:
                print("Castling not allowed in current position.")
            continue

        if not moveValidate(piece, dest_idx, turn, board, botWhite, gameStates):
            print("That move isn't legal. Try again.")
            continue

        testBoard = movePiece(piece, dest_idx, board, gameStates, turn)
        if not isKingSafe(testBoard, turn):
            print("Illegal: your king would be in check after that move.")
            continue

        # Apply move
        castlingRights = _update_castling_rights(castlingRights, botWhite, board, testBoard)
        board = testBoard

        # Promotion
        if promotion_needed(piece, dest_idx):
            choice = prompt_promotion()
            board = promotePawn(piece, dest_idx, choice, board, turn)

        gameStates.append(board)

        # Adapt bot search to player strength
        skill_score = scoreMoveForEnemy(board, botWhite, gameStates)
        pruneRate = adjust_prune_rate(skill_score)

        outcome = checkCheckmateOrStalemate(board, 'player', botWhite, gameStates)
        if outcome == 'checkmate':
            print_board(board)
            print("Checkmate! PLAYER wins. Nice!")
            break
        if outcome == 'stalemate':
            print_board(board)
            print("Stalemate! Game over.")
            break

        turn, other = other, turn

if __name__ == "__main__":
    try:
        pick = input("Should the bot be White and move first? (Y/n): ").strip().lower()
        bot_white = False if pick == "n" else True
    except Exception:
        bot_white = True
    startGame(bot_white)
