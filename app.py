# app.py
from flask import Flask, request, redirect, url_for, session, render_template, jsonify
from gameLogic import (
    newBoard, inputValidate, castle, movePiece, isKingSafe,
    checkCheckmateOrStalemate, getAllTeamMoves, promotePawn, castleValidate,
    castle_start_positions
)
from bot import botMove, scoreMoveForEnemy, evaluate_move_quality
import logging, random, os, json
import dotenv
import time
from typing import Optional

# --- Config / init ---
dotenv.load_dotenv()
app = Flask(__name__, static_folder='static', template_folder='templates')
# Use a stable key in production via env var; in local/dev default to a random key so restarts reset sessions.
app.secret_key = os.getenv('SECRET_KEY') or os.urandom(32)
logging.basicConfig(level=logging.DEBUG)

DEFAULT_CONFIG = {
    "debugMode": False,
    "adaptiveDifficulty": True,
    "botTimeLimitSeconds": None,
}


def load_config():
    try:
        with open("config.json", "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
            if not isinstance(loaded, dict):
                raise ValueError("config.json must contain a JSON object")
            return {**DEFAULT_CONFIG, **loaded}
    except FileNotFoundError:
        logging.warning("config.json not found. Falling back to defaults.")
    except Exception:
        logging.exception("Failed to load config.json. Falling back to defaults.")
    return DEFAULT_CONFIG.copy()


config = load_config()


def get_config_value(key, default=None):
    global config
    config = load_config()
    return config.get(key, default)

DEFAULT_PRUNE = 0.20  # default beam/prune
BASE_BOT_DEPTH = 3
MIN_BOT_DEPTH = 2
MAX_BOT_DEPTH = 5
SKILL_EVAL_DEPTH = 2
SKILL_EMA_ALPHA = 0.20
SKILL_ERR_CLAMP = 5.0  # pawns-ish

def adaptive_enabled() -> bool:
    return bool(get_config_value("adaptiveDifficulty", DEFAULT_CONFIG["adaptiveDifficulty"]))

def bot_time_limit_s() -> Optional[float]:
    """
    Optional hard time limit for bot search (seconds). Set to 0/None to disable.
    """
    v = get_config_value("botTimeLimitSeconds", DEFAULT_CONFIG["botTimeLimitSeconds"])
    try:
        if v is None:
            return None
        v = float(v)
        return None if v <= 0 else v
    except Exception:
        return None

def asset_version() -> str:
    """
    Cache-busting for Safari/others: version static assets by mtime.
    """
    try:
        js_m = int(os.path.getmtime(os.path.join(app.static_folder, "scripts.js")))
        css_m = int(os.path.getmtime(os.path.join(app.static_folder, "styles.css")))
        return f"{js_m}-{css_m}"
    except Exception:
        return "0"

def adjust_prune_rate(rank, total):
    if total <= 1:
        return DEFAULT_PRUNE
    pct = rank / total
    return max(0.05, DEFAULT_PRUNE * (1 - pct))

def adjust_prune_rate_based_on_move(board, gameStates, botWhite, current_prune_rate):
    player_moves = getAllTeamMoves('player', board, botWhite, gameStates)
    move_scores = [scoreMoveForEnemy(m, botWhite, gameStates) for moves in player_moves for m in moves]
    if not move_scores:
        return current_prune_rate
    move_scores.sort(reverse=True)
    current_score = scoreMoveForEnemy(board, botWhite, gameStates)
    EPS = 1e-6
    higher = sum(1 for s in move_scores if s > current_score + EPS)
    rank = higher + 1
    new_rate = adjust_prune_rate(rank, len(move_scores))
    logging.debug(f"Player move rank {rank}/{len(move_scores)} -> prune {new_rate:.3f}")
    return new_rate

def _depth_from_skill_ema(skill_ema: float) -> int:
    # skill_ema ~= avg "pawns lost vs best" per move (lower is stronger player).
    if skill_ema <= 0.25:
        return MAX_BOT_DEPTH
    if skill_ema <= 0.60:
        return max(MIN_BOT_DEPTH, min(MAX_BOT_DEPTH, BASE_BOT_DEPTH + 1))
    if skill_ema <= 1.25:
        return BASE_BOT_DEPTH
    return MIN_BOT_DEPTH

def _update_skill_and_depth(board_before, board_after):
    """
    Update `session['skill_ema']` and `session['bot_depth']` based on the quality of the player's move.
    """
    try:
        res = evaluate_move_quality(
            board_before,
            board_after,
            "player",
            session["botWhite"],
            session["gameStates"],
            depth=SKILL_EVAL_DEPTH,
        )
        if res is None:
            return
        best_score, played_score = res  # player-perspective ("good for player")
        err = max(0.0, best_score - played_score)
        err = min(err, SKILL_ERR_CLAMP)

        prev = float(session.get("skill_ema", 0.0))
        ema = (1.0 - SKILL_EMA_ALPHA) * prev + SKILL_EMA_ALPHA * err
        session["skill_ema"] = ema
        session["last_move_error"] = err
        session["bot_depth"] = _depth_from_skill_ema(ema)
    except Exception:
        logging.exception("Skill estimation failed")

def side_in_check(board, side, botWhite, gameStates):
    return not isKingSafe(board, side)

def _check_terminal_for(turn_side):
    """Return 'checkmate'/'stalemate'/'none' for the side-to-move."""
    return checkCheckmateOrStalemate(session['board'], turn_side, session['botWhite'], session['gameStates'])

def _end_game(status, winner=None):
    session['game_over'] = True
    session['winner'] = winner
    return {'status': status, 'winner': winner, 'board': session['board'], 'turn': session['turn']}


def _new_castling_rights():
    return {'player': True, 'bot': True}


def _update_castling_rights_from_transition(board_before, board_after):
    rights = dict(session.get('castling_rights', _new_castling_rights()))
    for side in ('player', 'bot'):
        if not rights.get(side, False):
            continue
        layout = castle_start_positions(session['botWhite'], side)
        king_piece, king_pos = layout['king']
        rook_piece, rook_pos = layout['rook']
        if board_before[king_pos] != king_piece or board_after[king_pos] != king_piece:
            rights[side] = False
            continue
        if board_before[rook_pos] != rook_piece or board_after[rook_pos] != rook_piece:
            rights[side] = False
    session['castling_rights'] = rights

# --- Routes ---
@app.get('/')
def index():
    logging.debug("Index called")
    session.clear()
    session['botWhite'] = random.choice([True, False])
    session['board'] = newBoard(session['botWhite'])
    session['gameStates'] = [session['board']]
    session['turn'] = 'bot' if session['botWhite'] else 'player'
    session['promote'] = False
    session['promotion_piece'] = None
    session['promotion_dest'] = None
    session['castling_rights'] = _new_castling_rights()
    session['prune_rate'] = DEFAULT_PRUNE
    session['bot_depth'] = BASE_BOT_DEPTH
    session['skill_ema'] = 0.0
    session['last_move_error'] = 0.0
    session['adaptive'] = adaptive_enabled()
    session['game_over'] = False
    session['winner'] = None

    logging.debug(f"New game botWhite={session['botWhite']}, turn={session['turn']}")

    # If bot opens, make its move and check terminal on player's side.
    if session['turn'] == 'bot':
        depth = session['bot_depth'] if adaptive_enabled() else BASE_BOT_DEPTH
        new_board = botMove(
            session['board'],
            session['turn'],
            session['gameStates'],
            session['botWhite'],
            depth=depth,
            pruneRate=session['prune_rate'],
            time_limit_s=bot_time_limit_s(),
            debug=bool(get_config_value("debugMode", DEFAULT_CONFIG["debugMode"])),
        )
        if new_board and isKingSafe(new_board, 'bot'):
            _update_castling_rights_from_transition(session['board'], new_board)
            session['board'] = new_board
            session['gameStates'].append(new_board)
            session['gameStates'] = session['gameStates'][-2:]
            # Check if player is already mated/stalemated before handing turn
            status = _check_terminal_for('player')
            if status == 'checkmate':
                _end = _end_game('checkmate', winner='bot')
                return redirect(url_for('active'))
            if status == 'stalemate':
                _end = _end_game('stalemate', winner=None)
                return redirect(url_for('active'))
            session['turn'] = 'player'
            logging.debug("Bot made the first move.")
    return redirect(url_for('active'))

@app.get('/active')
def active():
    # If session state is missing (e.g., direct navigation or server restart), start a new game.
    if 'board' not in session or 'turn' not in session or 'gameStates' not in session:
        return redirect(url_for('index'))
    v = asset_version()
    return render_template(
        'index.html',
        board=session.get('board'),
        turn=session.get('turn'),
        promote=session.get('promote'),
        botWhite=session.get('botWhite'),
        game_over=session.get('game_over'),
        winner=session.get('winner'),
        asset_v=v,
    )

@app.post('/make_move')
def make_move():
    # Make config changes take effect immediately even with an existing session cookie.
    session['adaptive'] = adaptive_enabled()
    if 'board' not in session or 'turn' not in session or 'gameStates' not in session:
        return jsonify({'status': 'no-session'}), 400
    # If game is already over, refuse further moves.
    if session.get('game_over'):
        return jsonify({
            'status': 'game-over',
            'winner': session.get('winner'),
            'board': session['board'],
            'turn': session['turn'],
            'promote': session['promote'],
            'botWhite': session['botWhite']
        })

    # Before processing, if the side-to-move is already checkmated/stalemated, end immediately.
    pre_status = _check_terminal_for(session['turn'])
    if pre_status == 'checkmate':
        winner = 'bot' if session['turn'] == 'player' else 'player'
        payload = _end_game('checkmate', winner=winner)
        payload.update({'promote': session['promote'], 'botWhite': session['botWhite']})
        return jsonify(payload)
    if pre_status == 'stalemate':
        payload = _end_game('stalemate', winner=None)
        payload.update({'promote': session['promote'], 'botWhite': session['botWhite']})
        return jsonify(payload)

    response = {}
    move_input = request.json.get('move')

    if move_input:
        board_before = session['board']
        validity, piece, dest = inputValidate(move_input, session['board'], session['botWhite'], session['turn'], session['gameStates'])
        if validity == "castle":
            if not castleValidate(session['botWhite'], session['turn'], session['board'], session.get('castling_rights')):
                response['status'] = 'invalid-castle'
            else:
                board_after = castle(session['turn'], session['board'], session['botWhite'])
                # Reject any move that leaves the mover's king in check.
                if not isKingSafe(board_after, session['turn']):
                    response['status'] = 'self-check'
                    response.update({
                        'board': session['board'],
                        'turn': session['turn'],
                        'promote': session['promote'],
                        'botWhite': session['botWhite'],
                        'game_over': session['game_over'],
                        'winner': session['winner']
                    })
                    return jsonify(response)
                if adaptive_enabled() and session['turn'] == 'player':
                    _update_skill_and_depth(board_before, board_after)
                _update_castling_rights_from_transition(board_before, board_after)
                session['board'] = board_after
                session['gameStates'].append(session['board'])
                session['gameStates'] = session['gameStates'][-2:]

                # After player's move, check terminal on bot side immediately
                outcome = _check_terminal_for('bot')
                if outcome == 'checkmate':
                    endp = _end_game('checkmate', winner='player')
                    return jsonify(endp)
                if outcome == 'stalemate':
                    endp = _end_game('stalemate', winner=None)
                    return jsonify(endp)

                response['status'] = 'castle'
                response['in_check'] = side_in_check(session['board'], 'bot', session['botWhite'], session['gameStates'])
                session['turn'] = 'bot'

        elif validity:
            # Normal move
            board_after = movePiece(piece, dest, session['board'], session['gameStates'], session['turn'])
            # Reject any move that leaves the mover's king in check.
            if not isKingSafe(board_after, session['turn']):
                response['status'] = 'self-check'
                response.update({
                    'board': session['board'],
                    'turn': session['turn'],
                    'promote': session['promote'],
                    'botWhite': session['botWhite'],
                    'game_over': session['game_over'],
                    'winner': session['winner']
                })
                return jsonify(response)
            if adaptive_enabled() and session['turn'] == 'player':
                _update_skill_and_depth(board_before, board_after)
            _update_castling_rights_from_transition(board_before, board_after)
            session['board'] = board_after
            session['gameStates'].append(session['board'])
            session['gameStates'] = session['gameStates'][-2:]

            # Promotion trigger
            if piece[0].lower() == 'p' and (dest // 8 in (0, 7)):
                session['promote'] = True
                session['promotion_piece'] = piece
                session['promotion_dest'] = dest
                response['status'] = 'promote'
            else:
                # After player's move, check terminal on bot side immediately
                status = _check_terminal_for('bot')
                if status == 'checkmate':
                    endp = _end_game('checkmate', winner='player')
                    return jsonify(endp)
                if status == 'stalemate':
                    endp = _end_game('stalemate', winner=None)
                    return jsonify(endp)

                session['turn'] = 'bot'
                response['status'] = 'success'
                response['in_check'] = side_in_check(session['board'], 'bot', session['botWhite'], session['gameStates'])
        else:
            response['status'] = 'invalid'

    response.update({
        'board': session['board'],
        'turn': session['turn'],
        'promote': session['promote'],
        'botWhite': session['botWhite'],
        'game_over': session['game_over'],
        'winner': session['winner']
    })
    return jsonify(response)

@app.post('/promote')
def promote():
    session['adaptive'] = adaptive_enabled()
    if 'board' not in session or 'turn' not in session or 'gameStates' not in session:
        return jsonify({'status': 'no-session'}), 400
    if session.get('game_over'):
        return jsonify({
            'status': 'game-over',
            'winner': session.get('winner'),
            'board': session['board'],
            'turn': session['turn']
        })

    if not session.get('promote'):
        return jsonify({'status': 'no-promotion', 'board': session['board'], 'turn': session['turn']})

    payload = request.get_json(silent=True) or request.form
    choice = payload.get('piece') or payload.get('promotion_piece') or 'QUEEN'
    choice = choice.upper()
    piece = session['promotion_piece']
    dest = session['promotion_dest']
    session['board'] = promotePawn(piece, dest, choice, session['board'], 'player')
    session['gameStates'].append(session['board'])
    session['gameStates'] = session['gameStates'][-2:]
    session['promote'] = False
    session['promotion_piece'] = None
    session['promotion_dest'] = None

    # After promotion completes, check terminal on bot side immediately
    status = _check_terminal_for('bot')
    if status == 'checkmate':
        return jsonify(_end_game('checkmate', winner='player'))
    if status == 'stalemate':
        return jsonify(_end_game('stalemate', winner=None))

    session['turn'] = 'bot'
    return jsonify({
        'status': 'promoted',
        'board': session['board'],
        'turn': session['turn'],
        'in_check': side_in_check(session['board'], 'bot', session['botWhite'], session['gameStates']),
        'game_over': session['game_over'],
        'winner': session['winner']
    })

@app.post('/bot_move')
def bot_move():
    # Make config changes take effect immediately even with an existing session cookie.
    session['adaptive'] = adaptive_enabled()
    if 'board' not in session or 'turn' not in session or 'gameStates' not in session:
        return jsonify({'status': 'no-session'}), 400
    # If game is already over, refuse further moves.
    if session.get('game_over'):
        return jsonify({
            'status': 'game-over',
            'winner': session.get('winner'),
            'board': session['board'],
            'turn': session['turn'],
            'botWhite': session['botWhite']
        })

    response = {}
    if session['turn'] == 'bot':
        # If bot's turn but bot is already mated/stalemated, end immediately.
        pre_status = _check_terminal_for('bot')
        if pre_status == 'checkmate':
            return jsonify(_end_game('checkmate', winner='player'))
        if pre_status == 'stalemate':
            return jsonify(_end_game('stalemate', winner=None))

        depth = session.get('bot_depth', BASE_BOT_DEPTH) if adaptive_enabled() else BASE_BOT_DEPTH
        t0 = time.perf_counter()
        new_board = botMove(
            session['board'],
            session['turn'],
            session['gameStates'],
            session['botWhite'],
            depth=depth,
            pruneRate=session['prune_rate'],
            time_limit_s=bot_time_limit_s(),
            debug=bool(get_config_value("debugMode", DEFAULT_CONFIG["debugMode"])),
        )
        dt = time.perf_counter() - t0
        logging.info(f"bot_move depth={depth} adaptive={adaptive_enabled()} took {dt:.3f}s")

        if new_board and isKingSafe(new_board, session['turn']):
            _update_castling_rights_from_transition(session['board'], new_board)
            session['board'] = new_board
            session['gameStates'].append(new_board)
            session['gameStates'] = session['gameStates'][-2:]

            # After bot's move, check terminal on player's side immediately
            status = _check_terminal_for('player')
            if status == 'checkmate':
                return jsonify(_end_game('checkmate', winner='bot'))
            if status == 'stalemate':
                return jsonify(_end_game('stalemate', winner=None))

            session['turn'] = 'player'
            response['status'] = 'success'
            response['in_check'] = side_in_check(session['board'], 'player', session['botWhite'], session['gameStates'])
        else:
            logging.error("Bot couldn't find a valid board.")
            response['status'] = 'error'

    response.update({
        'board': session['board'],
        'turn': session['turn'],
        'botWhite': session['botWhite'],
        'game_over': session['game_over'],
        'winner': session['winner']
    })
    return jsonify(response)

if __name__ == '__main__':
    app.run(debug=bool(get_config_value("debugMode", DEFAULT_CONFIG["debugMode"])))
