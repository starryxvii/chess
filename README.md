# Chess
A Python chess game where you can play against a bot that matches your skill level adaptively.

Game, bot, and website all developed by [ishsharm0](https://github.com/ishsharm0/) and [rosharma719](https://github.com/rosharma719/).

## Overview

- `gameLogic.py` — Generates legal moves, including castling, en passant, and promotion, and removes moves that leave the king in check.
- `bot.py` — Evaluates positions using material plus piece-square tables to account for piece placement.

The engine searches using **negamax with alpha–beta pruning**, exploring several plies while cutting off branches that cannot improve the result. A **quiescence search** extends evaluation in tactical positions (mainly captures) to avoid unstable leaf evaluations.

Terminal states are handled explicitly: if a side has no legal moves, the engine distinguishes **checkmate** from **stalemate**.

### Adaptive Difficulty
The web app adjusts difficulty dynamically:

- After each player move, the system compares it with the engine’s stronger candidate line using `evaluate_move_quality`.
- A running error estimate is tracked during the session.
- The bot’s search depth is increased or decreased accordingly, producing stronger replies for stronger play and faster replies for weaker play.

## Setup + Running Locally

Prerequisites:
- [Python 3.8+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/download/)

Run these commands in a directory of your choice (Windows/MacOS/Linux):

```bash
git clone https://github.com/starryxvii/chess.git
cd chess
pip install -r requirements.txt
echo SECRET_KEY=MySecretKey > .env
python app.py
```

To play the game in your console, simply run `python consoleMode.py` instead of `python app.py`.

## Optional Engine Testing

This repo includes a minimal UCI wrapper (`uci.py`) so you can play games against other engines like Stockfish.

- Run a direct OurBot vs Stockfish match (prints moves live):
  - `python match_runner.py --black stockfish --movetime-ms 30000 --pgnout matches.pgn`
- Run move-generation correctness checks (perft):
  - `python perft.py startpos 4`
