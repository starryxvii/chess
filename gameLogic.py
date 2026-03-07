# gameLogic.py
import logging
from typing import Tuple, Optional

logging.basicConfig(level=logging.DEBUG)

def newBoard(botWhite: bool):
    if botWhite:
        return (
            'r1','n1','b1','q','k','b2','n2','r2',
            'p1','p2','p3','p4','p5','p6','p7','p8',
            None,None,None,None,None,None,None,None,
            None,None,None,None,None,None,None,None,
            None,None,None,None,None,None,None,None,
            None,None,None,None,None,None,None,None,
            'P1','P2','P3','P4','P5','P6','P7','P8',
            'R1','N1','B1','Q','K','B2','N2','R2',
        )
    else:
        return (
            'r1','n1','b1','k','q','b2','n2','r2',
            'p1','p2','p3','p4','p5','p6','p7','p8',
            None,None,None,None,None,None,None,None,
            None,None,None,None,None,None,None,None,
            None,None,None,None,None,None,None,None,
            None,None,None,None,None,None,None,None,
            'P1','P2','P3','P4','P5','P6','P7','P8',
            'R1','N1','B1','K','Q','B2','N2','R2',
        )

def isOnBoard(i: int) -> bool:
    return 0 <= i < 64

def findPiece(piece: str, board: Tuple[Optional[str], ...]) -> int:
    try:
        return board.index(piece)
    except ValueError:
        return -1

def same_side(a: str, b: str) -> bool:
    return (a.isupper() and b.isupper()) or (a.islower() and b.islower())

_KNIGHT_OFFS = (15, 17, -15, -17, 10, 6, -10, -6)

def _same_row(a: int, b: int) -> bool:
    return (a // 8) == (b // 8)

def _valid_step(prev: int, curr: int, step: int) -> bool:
    """Ensure moving from prev->curr by 'step' stays on the intended line without wrapping."""
    if not isOnBoard(prev) or not isOnBoard(curr):
        return False
    dr = (curr // 8) - (prev // 8)
    dc = (curr % 8) - (prev % 8)
    if step == 1:   # right
        return dr == 0 and dc == 1
    if step == -1:  # left
        return dr == 0 and dc == -1
    if step == 8:   # down a row
        return dr == 1 and dc == 0
    if step == -8:  # up a row
        return dr == -1 and dc == 0
    if step == 9:   # down-right
        return dr == 1 and dc == 1
    if step == -9:  # up-left
        return dr == -1 and dc == -1
    if step == 7:   # down-left
        return dr == 1 and dc == -1
    if step == -7:  # up-right
        return dr == -1 and dc == 1
    return False

def _path_clear(board, start, dest, step) -> bool:
    i = start + step
    while i != dest:
        if not isOnBoard(i) or not _valid_step(i - step, i, step):
            return False
        if board[i] is not None:
            return False
        i += step
    # Final continuity check into dest
    return _valid_step(dest - step, dest, step)

def isEnemyPiece(board, position, pieceType, enemy_turn) -> bool:
    p = board[position]
    if p and p[0].lower() == pieceType:
        return (p.islower() if enemy_turn == 'player' else p.isupper())
    return False

def isKingSafe(board, turn: str, position: Optional[int] = None) -> bool:
    casePiece = 'K' if turn == 'bot' else 'k'
    king_pos = position if position is not None else findPiece(casePiece, board)
    if king_pos == -1:
        return False
    enemy = 'player' if turn == 'bot' else 'bot'
    # Pawn attacks
    pawn_attacks = (-9, -7) if turn == 'bot' else (9, 7)
    for off in pawn_attacks:
        pos = king_pos + off
        if isOnBoard(pos) and _valid_step(king_pos, pos, off) and isEnemyPiece(board, pos, 'p', enemy):
            return False
    # Rook/Queen lines
    for d in (1, -1, 8, -8):
        i = king_pos + d
        while isOnBoard(i) and _valid_step(i - d, i, d):
            piece = board[i]
            if piece:
                if piece[0].lower() in ('r', 'q') and (piece.islower() if enemy == 'player' else piece.isupper()):
                    return False
                break
            i += d
    # Bishop/Queen diagonals
    for d in (9, -9, 7, -7):
        i = king_pos + d
        while isOnBoard(i) and _valid_step(i - d, i, d):
            piece = board[i]
            if piece:
                if piece[0].lower() in ('b', 'q') and (piece.islower() if enemy == 'player' else piece.isupper()):
                    return False
                break
            i += d
    # Knights
    for off in _KNIGHT_OFFS:
        i = king_pos + off
        if isOnBoard(i) and isEnemyPiece(board, i, 'n', enemy):
            rdiff = abs((i // 8) - (king_pos // 8))
            cdiff = abs((i % 8) - (king_pos % 8))
            if (rdiff, cdiff) in {(1, 2), (2, 1)}:
                return False
    # Opposing king adjacency
    for off in (-1, 1, -8, 8, -9, -7, 9, 7):
        i = king_pos + off
        if isOnBoard(i) and _valid_step(king_pos, i, off) and isEnemyPiece(board, i, 'k', enemy):
            return False
    return True

def _last_move(gameStates):
    if not gameStates or len(gameStates) < 2:
        return None
    prev = gameStates[-1]
    prev2 = gameStates[-2]
    diffs = [i for i in range(64) if prev[i] != prev2[i]]
    if not diffs:
        return None
    from_idx = next((i for i in diffs if prev2[i] and prev[i] != prev2[i]), None)
    to_idx = next((i for i in diffs if prev[i] and prev[i] != prev2[i]), None)
    if from_idx is None or to_idx is None:
        return None
    return (prev[to_idx], from_idx, to_idx)

def moveValidate(piece: str, dest: int, turn: str, board, botWhite, gameStates) -> bool:
    if not ((piece[0].islower() and turn == 'player') or (piece[0].isupper() and turn == 'bot')): return False
    if not isOnBoard(dest): return False
    src = findPiece(piece, board)
    if src == -1: return False
    if board[dest] is not None and same_side(piece, board[dest]): return False
    # Kings are not capturable; checkmate ends the game instead.
    if turn == 'player' and board[dest] == 'K': return False
    if turn == 'bot' and board[dest] == 'k': return False
    rdiff = (dest // 8) - (src // 8)
    cdiff = (dest % 8) - (src % 8)
    t = piece[0].lower()

    if t == 'r':
        if rdiff != 0 and cdiff != 0: return False
        step = 8 if rdiff > 0 else (-8 if rdiff < 0 else (1 if cdiff > 0 else -1))
        if not _valid_step(src, src + step, step): return False
        return _path_clear(board, src, dest, step)

    if t == 'b':
        if abs(rdiff) != abs(cdiff): return False
        step = 9 if (rdiff > 0 and cdiff > 0) else (-9 if (rdiff < 0 and cdiff < 0) else (7 if (rdiff > 0 and cdiff < 0) else -7))
        if not _valid_step(src, src + step, step): return False
        return _path_clear(board, src, dest, step)

    if t == 'q':
        if rdiff == 0 or cdiff == 0:
            step = 8 if rdiff > 0 else (-8 if rdiff < 0 else (1 if cdiff > 0 else -1))
            if not _valid_step(src, src + step, step): return False
            return _path_clear(board, src, dest, step)
        if abs(rdiff) == abs(cdiff):
            step = 9 if (rdiff > 0 and cdiff > 0) else (-9 if (rdiff < 0 and cdiff < 0) else (7 if (rdiff > 0 and cdiff < 0) else -7))
            if not _valid_step(src, src + step, step): return False
            return _path_clear(board, src, dest, step)
        return False

    if t == 'n':
        return (abs(rdiff), abs(cdiff)) in {(1,2),(2,1)}

    if t == 'k':
        return max(abs(rdiff), abs(cdiff)) == 1  # (castling handled via special "castle" action)

    if t == 'p':
        forward = 1 if turn == 'player' else -1
        start_row = 1 if turn == 'player' else 6
        # one step forward
        if rdiff == forward and cdiff == 0 and board[dest] is None: return True
        # two steps from start
        if rdiff == 2*forward and cdiff == 0 and (src//8)==start_row and board[dest] is None and board[src+8*forward] is None: return True
        # capture
        if rdiff == forward and abs(cdiff) == 1 and board[dest] is not None and not same_side(piece, board[dest]): return True
        # en passant capture
        if rdiff == forward and abs(cdiff) == 1 and board[dest] is None:
            last = _last_move(gameStates)
            if last:
                last_piece, from_idx, to_idx = last
                if last_piece and last_piece[0].lower() == 'p' and abs(to_idx-from_idx) == 16:
                    if (to_idx // 8) == (src // 8) and (to_idx % 8) == (dest % 8):
                        return True
        return False

    return False

def getPieceMoves(piece, originalBoard, botWhite, gameStates):
    if piece is None:
        return tuple()
    src = findPiece(piece, originalBoard)
    if src == -1:
        return tuple()

    turn = 'player' if piece[0].islower() else 'bot'
    t = piece[0].lower()
    moves = []
    last = _last_move(gameStates)

    def add_move(dest: int):
        if dest == src:
            return
        if not moveValidate(piece, dest, turn, originalBoard, botWhite, gameStates):
            return
        b = list(originalBoard)
        # handle en passant capture removal
        if t == 'p' and b[dest] is None and (abs((dest % 8) - (src % 8)) == 1) and last:
            _, _, to_idx = last
            if (to_idx // 8) == (src // 8) and (to_idx % 8) == (dest % 8):
                b[to_idx] = None
        b[dest] = piece
        b[src] = None
        moves.append(tuple(b))

    def ray(step: int):
        i = src + step
        while isOnBoard(i) and _valid_step(i - step, i, step):
            if originalBoard[i] is None:
                add_move(i)
            else:
                if not same_side(piece, originalBoard[i]):
                    add_move(i)
                break
            i += step

    if t == 'r':
        for step in (1, -1, 8, -8):
            ray(step)
        return tuple(moves)

    if t == 'b':
        for step in (7, -7, 9, -9):
            ray(step)
        return tuple(moves)

    if t == 'q':
        for step in (1, -1, 8, -8, 7, -7, 9, -9):
            ray(step)
        return tuple(moves)

    if t == 'n':
        sr, sc = src // 8, src % 8
        for off in _KNIGHT_OFFS:
            dest = src + off
            if not isOnBoard(dest):
                continue
            dr = abs((dest // 8) - sr)
            dc = abs((dest % 8) - sc)
            if (dr, dc) not in {(1, 2), (2, 1)}:
                continue
            if originalBoard[dest] is None or not same_side(piece, originalBoard[dest]):
                add_move(dest)
        return tuple(moves)

    if t == 'k':
        for off in (-1, 1, -8, 8, -9, -7, 9, 7):
            dest = src + off
            if not isOnBoard(dest) or not _valid_step(src, dest, off):
                continue
            if originalBoard[dest] is None or not same_side(piece, originalBoard[dest]):
                add_move(dest)
        return tuple(moves)

    if t == 'p':
        forward = 1 if turn == 'player' else -1
        start_row = 1 if turn == 'player' else 6
        one = src + 8 * forward
        if isOnBoard(one) and _valid_step(src, one, 8 * forward) and originalBoard[one] is None:
            add_move(one)
            two = src + 16 * forward
            if (src // 8) == start_row and isOnBoard(two) and originalBoard[two] is None:
                # if one is empty then two is reachable
                add_move(two)

        # captures and en passant
        for step in (7 * forward, 9 * forward):
            dest = src + step
            if not isOnBoard(dest) or not _valid_step(src, dest, step):
                continue
            target = originalBoard[dest]
            if target is not None:
                if not same_side(piece, target):
                    add_move(dest)
                continue
            # potential en passant: diagonal into empty square
            if last:
                last_piece, from_idx, to_idx = last
                if last_piece and last_piece[0].lower() == 'p' and abs(to_idx - from_idx) == 16:
                    if not same_side(piece, last_piece) and (to_idx // 8) == (src // 8) and (to_idx % 8) == (dest % 8):
                        add_move(dest)
        return tuple(moves)

    # Fallback (shouldn't happen)
    for dest in range(64):
        add_move(dest)
    return tuple(moves)

def getAllTeamMoves(team, board, botWhite, gameStates):
    teamMoves = []
    if team == 'player':
        for p in board:
            if p and p[0].islower():
                teamMoves.append(getPieceMoves(p, board, botWhite, gameStates))
    else:
        for p in board:
            if p and p[0].isupper():
                teamMoves.append(getPieceMoves(p, board, botWhite, gameStates))
    return tuple(teamMoves)

def promotePawn(piece: str, dest: int, new_piece: str, board, turn: str):
    name_map = {"QUEEN": 'q', "ROOK": 'r', "BISHOP": 'b', "KNIGHT": 'n'}
    base = name_map.get(new_piece.upper(), 'q')
    b = list(board)
    count = 1
    for existing in b:
        if existing and existing[0].lower() == base:
            suffix = int(existing[1:]) if len(existing) > 1 and existing[1:].isdigit() else 1
            count = max(count, suffix + 1)
    new_name = base + str(count)
    new_name = new_name.upper() if piece.isupper() else new_name.lower()
    b[dest] = new_name
    return tuple(b)

def movePiece(piece, destIndex, board, gameStates, turn):
    src = findPiece(piece, board)
    if src == -1: return board
    b = list(board)
    # en passant removal if applicable
    if piece[0].lower() == 'p' and b[destIndex] is None and abs((destIndex%8)-(src%8)) == 1:
        last = _last_move(gameStates)
        if last:
            last_piece, _, to_idx = last
            if last_piece and last_piece[0].lower() == 'p' and (to_idx // 8) == (src // 8) and (to_idx % 8) == (destIndex % 8):
                b[to_idx] = None
    b[destIndex] = piece
    b[src] = None
    return tuple(b)

def findSquare(square: str):
    try:
        colIndex = ord(square[0].lower()) - ord('a')
        rowIndex = int(square[1]) - 1
        index = (7 - rowIndex) * 8 + colIndex
        return index
    except Exception:
        return False

def castle_start_positions(botWhite, turn):
    if botWhite:
        if turn == 'bot':
            return {'king': ('K', 60), 'rook': ('R2', 63), 'through': 61, 'dest': 62, 'empty': (61, 62)}
        return {'king': ('k', 4), 'rook': ('r2', 7), 'through': 5, 'dest': 6, 'empty': (5, 6)}
    if turn == 'bot':
        return {'king': ('K', 59), 'rook': ('R1', 56), 'through': 58, 'dest': 57, 'empty': (57, 58)}
    return {'king': ('k', 3), 'rook': ('r1', 0), 'through': 2, 'dest': 1, 'empty': (1, 2)}

def _board_with_king_at(board, turn, dest):
    king_piece = 'K' if turn == 'bot' else 'k'
    src = findPiece(king_piece, board)
    if src == -1:
        return None
    b = list(board)
    b[src] = None
    b[dest] = king_piece
    return tuple(b)

def castle(turn, board, botWhite):
    b = list(board)
    if botWhite:
        if turn == 'bot':
            if b[60] == 'K' and b[63] == 'R2' and b[61] is None and b[62] is None:
                b[60], b[62], b[63], b[61] = None, 'K', None, 'R2'
        else:
            if b[4] == 'k' and b[7] == 'r2' and b[5] is None and b[6] is None:
                b[4], b[6], b[7], b[5] = None, 'k', None, 'r2'
    else:
        if turn == 'bot':
            if b[59] == 'K' and b[56] == 'R1' and b[58] is None and b[57] is None:
                b[59], b[57], b[56], b[58] = None, 'K', None, 'R1'
        else:
            if b[3] == 'k' and b[0] == 'r1' and b[2] is None and b[1] is None:
                b[3], b[1], b[0], b[2] = None, 'k', None, 'r1'
    return tuple(b)

def castleValidate(botWhite, turn, board, castlingRights=None):
    if castlingRights is not None and not castlingRights.get(turn, False):
        return False

    layout = castle_start_positions(botWhite, turn)
    king_piece, kingPos = layout['king']
    rook_piece, rookPos = layout['rook']
    through = layout['through']
    dest = layout['dest']

    if board[kingPos] != king_piece or board[rookPos] != rook_piece:
        return False
    if any(board[i] is not None for i in layout['empty']):
        return False
    if not isKingSafe(board, turn):
        return False

    through_board = _board_with_king_at(board, turn, through)
    if through_board is None or not isKingSafe(through_board, turn):
        return False

    final_board = castle(turn, board, botWhite)
    if final_board == board or not isKingSafe(final_board, turn):
        return False

    # Final sanity check that the king reaches the expected destination.
    return final_board[dest] == king_piece

def detectCheckmate(board, turn, botWhite, gameStates):
    team_moves = getAllTeamMoves(turn, board, botWhite, gameStates)
    legal = [m for moves in team_moves for m in moves if isKingSafe(m, turn)]
    if legal: return False
    return not isKingSafe(board, turn)

def detectStalemate(board, turn, botWhite, gameStates):
    team_moves = getAllTeamMoves(turn, board, botWhite, gameStates)
    legal = [m for moves in team_moves for m in moves if isKingSafe(m, turn)]
    return (not legal) and isKingSafe(board, turn)

def checkCheckmateOrStalemate(board, turn, botWhite, gameStates):
    if detectCheckmate(board, turn, botWhite, gameStates): return 'checkmate'
    if detectStalemate(board, turn, botWhite, gameStates): return 'stalemate'
    return 'none'

def inputValidate(inputString: str, board, botWhite, turn: str, gameStates):
    """
    Parse user input and validate:
      - 'p2 e4'  -> piece name and dest (index or algebraic)
      - 'e2 e4'  -> from-square to-square (auto-detect piece)
      - 'castle' -> special action (validated by castleValidate in route)
    Returns:
      - ("castle", None, None) if castling request
      - (True, piece_name, dest_index) if legal by moveValidate
      - (False, None, None) otherwise
    """
    try:
        s = inputString.strip()
        if s.lower() == "castle":
            return ("castle", None, None)

        parts = s.split()
        if len(parts) != 2:
            return (False, None, None)

        a, b = parts[0], parts[1]

        # Case 1: explicit piece name present on board
        if a in board:
            piece = a
            destIndex = int(b) if b.isdigit() else findSquare(b)
            if destIndex is False:
                return (False, None, None)
            if moveValidate(piece, destIndex, turn, board, botWhite, gameStates):
                return (True, piece, destIndex)
            return (False, None, None)

        # Case 2: square-to-square
        srcIndex = int(a) if a.isdigit() else findSquare(a)
        if srcIndex is False or not isOnBoard(srcIndex):
            return (False, None, None)
        piece = board[srcIndex]
        if not piece or not ((piece[0].islower() and turn == 'player') or (piece[0].isupper() and turn == 'bot')):
            return (False, None, None)

        destIndex = int(b) if b.isdigit() else findSquare(b)
        if destIndex is False or not isOnBoard(destIndex):
            return (False, None, None)

        if moveValidate(piece, destIndex, turn, board, botWhite, gameStates):
            return (True, piece, destIndex)
        return (False, None, None)
    except Exception as e:
        logging.exception(f"inputValidate error: {e}")
        return (False, None, None)
