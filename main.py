# play_pygame_pro.py
# PyBot Chess — Coach (H/O/T), right sidebar with word-wrapping, Stockfish auto-detect,
# alias-aware PNG sprites, natural-language rationale, reselect piece UX.

import argparse
import os
import shutil
from typing import Optional, Tuple, List, Dict

import pygame
import chess

from chess_ai import ChessAI

# ---------------- Layout / colors ----------------
BOARD_SIZE = 640              # 8x8 board in px
MARGIN_X = 24
MARGIN_TOP = 24
GAP = 16                      # board → sidebar gap
SIDEBAR_W = 320               # right panel width (narrower; we wrap text)
SQ = BOARD_SIZE // 8

LIGHT = (240, 217, 181)
DARK = (181, 136, 99)
HIGHLIGHT = (246, 246, 105)
LASTMOVE = (186, 202, 68)
BG = (24, 26, 31)
PANEL_BG = (34, 36, 43)
TEXT = (230, 230, 235)
SUBTEXT = (200, 210, 220)
ILLEGAL = (220, 80, 80)
GREEN = (60, 200, 120)
RED = (220, 80, 80)
ACCENT = (120, 170, 255)

# ---------------- NL helpers ----------------
PIECE_WORD = {
    chess.KING: "King", chess.QUEEN: "Queen", chess.ROOK: "Rook",
    chess.BISHOP: "Bishop", chess.KNIGHT: "Knight", chess.PAWN: "Pawn"
}
CENTER_SQS = {chess.D4, chess.E4, chess.D5, chess.E5}
DEV_START = {
    chess.WHITE: [chess.B1, chess.G1, chess.C1, chess.F1],  # knights, bishops
    chess.BLACK: [chess.B8, chess.G8, chess.C8, chess.F8],
}

def side_word(color: bool) -> str:
    return "White" if color == chess.WHITE else "Black"

def cp_to_words(cp: Optional[int]) -> str:
    if cp is None: return "Position unclear."
    if cp >= 200: return "White has a strong advantage."
    if cp >= 70:  return "White is better."
    if cp >= 20:  return "White is slightly better."
    if cp > -20:  return "Roughly equal."
    if cp > -70:  return "Black is slightly better."
    if cp > -200: return "Black is better."
    return "Black has a strong advantage."

def human_square(sq: int) -> str:
    return chess.square_name(sq)

def move_tags(b: chess.Board, m: chess.Move) -> List[str]:
    tags: List[str] = []
    if b.is_castling(m): tags.append("castling")
    if b.is_capture(m):  tags.append("capture")
    if b.gives_check(m): tags.append("check")
    if m.to_square in CENTER_SQS: tags.append("controls center")
    # simple development heuristic
    pc = b.piece_at(m.from_square)
    if pc and pc.piece_type in (chess.KNIGHT, chess.BISHOP):
        start_rank = 1 if pc.color == chess.WHITE else 6
        if chess.square_rank(m.from_square) == start_rank:
            tags.append("develops")
    return tags

def describe_move(b: chess.Board, m: chess.Move) -> str:
    pc = b.piece_at(m.from_square)
    if not pc:  # fallback
        return b.san(m)
    piece = PIECE_WORD[pc.piece_type]
    frm, to = human_square(m.from_square), human_square(m.to_square)
    tags = move_tags(b, m)
    # victim before push
    if b.is_capture(m):
        victim = b.piece_at(m.to_square)
        if victim:
            tags.insert(0, f"takes {side_word(victim.color)} {PIECE_WORD[victim.piece_type]}")
    extra = " — " + "; ".join(tags) if tags else ""
    return f"{piece} {frm}→{to}{extra}"

# ---------------- Geometry helpers ----------------
def board_rect():
    return pygame.Rect(MARGIN_X, MARGIN_TOP, BOARD_SIZE, BOARD_SIZE)

def sidebar_rect():
    x = MARGIN_X + BOARD_SIZE + GAP
    return pygame.Rect(x, MARGIN_TOP, SIDEBAR_W, BOARD_SIZE)

def square_to_xy(sq: int) -> Tuple[int, int]:
    f = chess.square_file(sq)
    r = 7 - chess.square_rank(sq)
    return (MARGIN_X + f * SQ, MARGIN_TOP + r * SQ)

def xy_to_square(px: int, py: int) -> Optional[int]:
    if not board_rect().collidepoint(px, py):
        return None
    file_ = (px - MARGIN_X) // SQ
    r_disp = (py - MARGIN_TOP) // SQ
    rank = 7 - r_disp
    return chess.square(file_, rank)

# ---------------- Text wrapping helper (pixel width) ----------------
def wrap_lines_by_width(lines: List[str], font: pygame.font.Font, max_px: int) -> List[str]:
    """Word-wrap lines so each rendered line fits within max_px pixels."""
    wrapped: List[str] = []
    for line in lines:
        words = line.split()
        if not words:
            wrapped.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            test = cur + " " + w
            if font.size(test)[0] <= max_px:
                cur = test
            else:
                wrapped.append(cur)
                cur = w
        wrapped.append(cur)
    return wrapped

# ---------------- PNG loader (alias-aware) ----------------
def load_pieces(folder="pieces-png", size=SQ - 8):
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Piece folder not found: {folder}")
    aliases: Dict[int, List[str]] = {
        chess.KING:   ["king", "nrking"],
        chess.QUEEN:  ["queen", "rqueen"],
        chess.ROOK:   ["rook", "rook4"],
        chess.BISHOP: ["bishop", "archbis", "chancel"],
        chess.KNIGHT: ["knight", "rknight", "nightrd"],
        chess.PAWN:   ["pawn", "bpawn", "bpawn2"],
    }
    pieces: Dict[Tuple[int, bool], pygame.Surface] = {}
    for ptype, names in aliases.items():
        for color_bool, color_name in ((True, "white"), (False, "black")):
            chosen = None
            for alias in names:
                candidate = os.path.join(folder, f"{color_name}-{alias}.png")
                if os.path.exists(candidate):
                    chosen = candidate; break
            if not chosen:
                tried = ", ".join([f"{color_name}-{n}.png" for n in names])
                raise FileNotFoundError(f"Missing sprite for {color_name} {chess.piece_symbol(ptype).upper()} — tried: {tried}")
            img = pygame.image.load(chosen).convert_alpha()
            img = pygame.transform.smoothscale(img, (size, size))
            pieces[(ptype, color_bool)] = img
    return pieces

# ---------------- Heuristic eval (fallback) ----------------
PIECE_VALUES = {
    chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
    chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0,
}
def simple_material_eval(board: chess.Board) -> int:
    score = 0
    for pt, val in PIECE_VALUES.items():
        score += len(board.pieces(pt, chess.WHITE)) * val
        score -= len(board.pieces(pt, chess.BLACK)) * val
    return score if board.turn == chess.WHITE else -score

# ---------------- Engine helpers ----------------
def autodetect_engine(explicit: str) -> str:
    if explicit: return explicit
    env = os.getenv("PYBOT_ENGINE", "").strip()
    if env: return env
    on_path = shutil.which("stockfish")
    if on_path: return on_path
    for c in ["/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish", "/usr/bin/stockfish", "/usr/games/stockfish"]:
        if os.path.exists(c): return c
    return ""

def engine_eval_and_pv(bot: ChessAI, board: chess.Board, time_limit=0.2) -> Tuple[Optional[int], List[chess.Move]]:
    cp = None; pv: List[chess.Move] = []
    if bot.engine is None: return cp, pv
    try:
        info = bot.engine.analyse(board, chess.engine.Limit(time=time_limit))  # type: ignore[attr-defined]
        cp = info["score"].white().score(mate_score=10000)
        if "pv" in info and info["pv"]:
            pv = list(info["pv"])
    except Exception:
        pass
    return cp, pv

# ---------------- Teaching builders ----------------
def engine_rationale(bot: ChessAI, board: chess.Board) -> List[str]:
    """Natural-language explanation using engine if available, else heuristics."""
    lines: List[str] = []
    cp, pv = engine_eval_and_pv(bot, board, time_limit=0.25)
    if cp is not None:
        lines.append(cp_to_words(cp))
        lines.append(f"Eval (cp): {cp}")
        if pv:
            b2 = board.copy()
            lines.append("Plan:")
            for mv in pv[:4]:
                lines.append(f"  • {describe_move(b2, mv)}")
                b2.push(mv)
            # SAN PV for quick reference
            b3 = board.copy()
            san = []
            for mv in pv[:8]:
                san.append(b3.san(mv)); b3.push(mv)
            lines.append("PV (SAN): " + " ".join(san))
        return lines

    # Heuristic fallback
    mat = simple_material_eval(board)
    lines.append(cp_to_words(mat))
    lines.append(f"Material (side to move): {mat} cp")
    caps = [m for m in board.legal_moves if board.is_capture(m)]
    checks = [m for m in board.legal_moves if board.gives_check(m)]
    center = [m for m in board.legal_moves if m.to_square in CENTER_SQS]
    if caps:
        lines.append(f"{len(caps)} capture{'s' if len(caps)!=1 else ''} available. Examples:")
        b2 = board.copy()
        for m in caps[:2]:
            lines.append(f"  • {describe_move(b2, m)}")
    if checks: lines.append(f"{len(checks)} checking move{'s' if len(checks)!=1 else ''} available.")
    if center: lines.append(f"{len(center)} move{'s' if len(center)!=1 else ''} increase center control.")
    return lines

def coaching_feedback(bot: ChessAI, before: chess.Board, move: chess.Move, after: chess.Board) -> Tuple[List[str], bool]:
    """Explain player's move vs engine best; return (lines, is_blunder) for red outline."""
    lines: List[str] = []
    is_blunder = False
    if bot.engine is None:
        lines.append("Coach: (no engine) Try to control the center, develop pieces, castle early.")
        return lines, is_blunder

    best_cp, best_pv = engine_eval_and_pv(bot, before, time_limit=0.25)
    after_cp, _ = engine_eval_and_pv(bot, after, time_limit=0.2)

    lines.append(f"You played: {describe_move(before, move)}")

    if best_cp is None or after_cp is None:
        lines.append("Coach: Position unclear.")
        return lines, is_blunder

    diff = (best_cp - after_cp)  # positive → worse than best for White
    if abs(diff) < 40:
        lines.append("✅ Good! Keeps the position about equal.")
    elif diff < 120:
        lines.append("⚠️ Not the best. There was a stronger idea:")
    else:
        lines.append("⛔ Blunder: this loses too much compared with the best move.")
        is_blunder = True

    if best_pv:
        btmp = before.copy()
        suggestion = describe_move(btmp, best_pv[0])
        btmp.push(best_pv[0])
        lines.append(f"Coach suggests: {suggestion}")
        tags = move_tags(before, best_pv[0])
        if "develops" in tags:
            lines.append("Because it develops a piece toward the center.")
        elif "controls center" in tags:
            lines.append("Because it fights for the center (d4/e4/d5/e5).")
        elif "capture" in tags:
            lines.append("Because it wins material or removes a key defender.")
        elif "castling" in tags:
            lines.append("Because it makes your king safer (castling).")
    lines.append("Tips: open with center pawns, develop knights/bishops, castle early, avoid hanging pieces.")
    return lines, is_blunder

def find_hanging_pieces(board: chess.Board, color: bool) -> List[int]:
    """Squares of color's pieces that are attacked by the opponent and not defended by own side."""
    hangs: List[int] = []
    opp = not color
    for sq, pc in board.piece_map().items():
        if pc.color != color: continue
        if board.is_attacked_by(opp, sq) and not board.is_attacked_by(color, sq):
            hangs.append(sq)
    return hangs

def opening_advice(board: chess.Board) -> List[str]:
    """Child-friendly opening guidance (not currently injected; kept for future use)."""
    lines: List[str] = []
    turn = board.turn
    lines.append("Opening coach:")
    if turn == chess.WHITE:
        lines.append("• Try to play e4 or d4 to claim the center.")
    else:
        lines.append("• Try to answer the center (…e5/…d5) and develop.")
    dev_squares = [s for s in DEV_START[turn] if board.piece_at(s)]
    if dev_squares:
        pretty = ", ".join(human_square(s) for s in dev_squares)
        lines.append(f"• Develop from: {pretty}. Knights and bishops first.")
    lines.append("• Don’t move the same piece many times in the opening. Castle when safe.")
    return lines

# ---------------- Draw routines ----------------
def draw_board(surface, board: chess.Board, last_move: Optional[chess.Move],
               selected: Optional[int], legal_targets: List[int],
               piece_images: Dict[Tuple[int, bool], pygame.Surface]):
    surface.fill(BG)
    # squares
    for r in range(8):
        for f in range(8):
            x = MARGIN_X + f * SQ
            y = MARGIN_TOP + r * SQ
            pygame.draw.rect(surface, LIGHT if (r+f)%2==0 else DARK, (x, y, SQ, SQ))

    # last move highlight
    if last_move:
        for sq in (last_move.from_square, last_move.to_square):
            x, y = square_to_xy(sq)
            s = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
            s.fill((*LASTMOVE, 90))
            surface.blit(s, (x, y))

    # selected + legal dots
    if selected is not None:
        x, y = square_to_xy(selected)
        s = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        s.fill((*HIGHLIGHT, 110))
        surface.blit(s, (x, y))
        for sq in legal_targets:
            tx, ty = square_to_xy(sq)
            pygame.draw.circle(surface, (20,20,20), (tx + SQ//2, ty + SQ//2), 8)

    # pieces
    for sq, piece in board.piece_map().items():
        x, y = square_to_xy(sq)
        img = piece_images[(piece.piece_type, piece.color)]
        rect = img.get_rect(center=(x + SQ//2, y + SQ//2))
        surface.blit(img, rect)

def draw_arrow(surface, move: chess.Move, color=(0,255,0), thickness=5):
    x1, y1 = square_to_xy(move.from_square); x1 += SQ//2; y1 += SQ//2
    x2, y2 = square_to_xy(move.to_square);   x2 += SQ//2; y2 += SQ//2
    pygame.draw.line(surface, color, (x1, y1), (x2, y2), thickness)

def draw_square_outline(surface, sq: int, color, thickness=4):
    x, y = square_to_xy(sq)
    pygame.draw.rect(surface, color, (x, y, SQ, SQ), thickness)

def draw_center_highlights(surface):
    for sq in CENTER_SQS:
        x, y = square_to_xy(sq)
        s = pygame.Surface((SQ, SQ), pygame.SRCALPHA)
        s.fill((ACCENT[0], ACCENT[1], ACCENT[2], 70))
        surface.blit(s, (x, y))

def draw_sidebar(surface, panel_font, small_font, info_lines: List[str],
                 score: Dict[str,int], ms_per_move: int, mode_label: str,
                 turn_label: str, toggles: Dict[str,bool], engine_active: bool):
    pr = sidebar_rect()
    pygame.draw.rect(surface, PANEL_BG, pr, border_radius=10)
    x = pr.left + 12
    y = pr.top + 12
    max_w = pr.width - 24  # padding

    # Header
    header = f"{mode_label} | {turn_label}"
    surface.blit(panel_font.render(header, True, TEXT), (x, y)); y += 26

    # Meta
    meta = f"W:{score['W']}  D:{score['D']}  L:{score['L']}   |   Speed: {ms_per_move} ms"
    for line in wrap_lines_by_width([meta], small_font, max_w):
        surface.blit(small_font.render(line, True, SUBTEXT), (x, y)); y += 20

    # Toggles
    togg = (f"Hints(H): {'ON' if toggles['H'] else 'OFF'}   "
            f"Openings(O): {'ON' if toggles['O'] else 'OFF'}   "
            f"Tactics(T): {'ON' if toggles['T'] else 'OFF'}   "
            f"Engine: {'Yes' if engine_active else 'No'}")
    for line in wrap_lines_by_width([togg], small_font, max_w):
        surface.blit(small_font.render(line, True, SUBTEXT), (x, y)); y += 20
    y += 4

    # Info lines
    wrapped = []
    for ln in info_lines[:40]:
        wrapped.extend(wrap_lines_by_width([ln], small_font, max_w) or [""])
    for ln in wrapped:
        surface.blit(small_font.render(ln, True, TEXT), (x, y)); y += 20

# ---------------- Main loop ----------------
def collect_legal_targets(board: chess.Board, selected: Optional[int]) -> List[int]:
    if selected is None: return []
    return [m.to_square for m in board.legal_moves if m.from_square == selected]

def play_loop(mode: str, side: str, engine_path: str, ms_per_move: int):
    pygame.init()
    width = MARGIN_X*2 + BOARD_SIZE + GAP + SIDEBAR_W
    height = MARGIN_TOP*2 + BOARD_SIZE
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("PyBot Chess — Coach (H/O/T)")

    panel_font = pygame.font.SysFont("arial", 18, bold=True)
    small_font = pygame.font.SysFont("arial", 16)

    pieces = load_pieces("pieces-png", size=SQ-8)

    botA = ChessAI(engine_path=engine_path or None)
    botB = ChessAI(engine_path=engine_path or None, epsilon=max(0.05, botA.epsilon * 1.2))

    board = chess.Board()
    selected: Optional[int] = None
    last_move: Optional[chess.Move] = None
    info_lines: List[str] = []
    score = {"W":0,"D":0,"L":0}
    illegal_flash_until = 0

    # Toggles
    toggles = {"H": False, "O": False, "T": False}  # H: hints, O: openings, T: tactics
    last_player_move_blunder = False  # for red outline

    playing_human = (mode == "human")
    duel = (mode == "duel")
    human_white = (side == "white")

    clock = pygame.time.Clock()
    running = True

    while running:
        # -------- events --------
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                elif event.key == pygame.K_r:
                    board.reset(); last_move=None; selected=None; info_lines=[]; last_player_move_blunder=False
                elif event.key == pygame.K_LEFTBRACKET: ms_per_move = min(3000, ms_per_move + 100)
                elif event.key == pygame.K_RIGHTBRACKET: ms_per_move = max(0, ms_per_move - 100)
                elif event.key == pygame.K_h: toggles["H"] = not toggles["H"]
                elif event.key == pygame.K_o: toggles["O"] = not toggles["O"]
                elif event.key == pygame.K_t: toggles["T"] = not toggles["T"]

            if playing_human:
                human_turn = (board.turn == chess.WHITE and human_white) or (board.turn == chess.BLACK and not human_white)
                if human_turn and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    px, py = event.pos
                    sq = xy_to_square(px, py)
                    if sq is None: continue
                    pc = board.piece_at(sq)
                    if selected is None:
                        if pc and pc.color == board.turn:
                            selected = sq
                    else:
                        if pc and pc.color == board.turn:
                            selected = sq  # reselect
                        else:
                            # analyze BEFORE move if hints/tactics
                            before = board.copy()
                            mv = chess.Move(selected, sq, promotion=chess.QUEEN)
                            pushed = False
                            if mv in board.legal_moves:
                                board.push(mv); last_move=mv; selected=None; pushed=True
                            else:
                                for m in list(board.legal_moves):
                                    if m.from_square == selected and m.to_square == sq:
                                        board.push(m); last_move=m; selected=None; pushed=True; break

                            if pushed:
                                # base rationale
                                info_lines = engine_rationale(botA, board)
                                # feedback for your move (hints ON)
                                if toggles["H"]:
                                    fb, is_blunder = coaching_feedback(botA, before, last_move, board)
                                    last_player_move_blunder = is_blunder
                                    info_lines = fb + ["—"] + info_lines
                                else:
                                    last_player_move_blunder = False
                                # tactics: highlight hanging pieces for side to move
                                if toggles["T"]:
                                    hangs = find_hanging_pieces(board, board.turn)
                                    if hangs:
                                        info_lines = [f"⚠️ Hanging piece(s): {', '.join(human_square(s) for s in hangs)}"] + info_lines
                            else:
                                illegal_flash_until = pygame.time.get_ticks() + 350

        # -------- engine / self-play moves --------
        if not board.is_game_over():
            if playing_human:
                bot_turn = (board.turn == chess.WHITE and not human_white) or (board.turn == chess.BLACK and human_white)
                if bot_turn:
                    if ms_per_move > 0: pygame.time.delay(ms_per_move)
                    mv = botA.choose_move(board)
                    board.push(mv); last_move=mv
                    info_lines = engine_rationale(botA, board)
            else:
                if ms_per_move > 0: pygame.time.delay(ms_per_move)
                mover = botA if (not duel or board.turn == chess.WHITE) else botB
                mv = mover.choose_move(board)
                board.push(mv); last_move=mv
                info_lines = engine_rationale(botA, board)

        # -------- scoreboard --------
        if board.is_game_over():
            res = board.result()
            if res == '1-0': score["W" if (playing_human and human_white) or not playing_human else "L"] += 1
            elif res == '0-1': score["L" if (playing_human and human_white) or not playing_human else "W"] += 1
            else: score["D"] += 1

        # -------- render --------
        legal_targets = collect_legal_targets(board, selected)
        draw_board(screen, board, last_move, selected, legal_targets, pieces)

        # Openings overlay
        if toggles["O"]:
            draw_center_highlights(screen)
            # encourage development squares for side to move
            for s in DEV_START[board.turn]:
                if board.piece_at(s):  # still at home
                    draw_square_outline(screen, s, ACCENT, thickness=3)

        # Hints: best move arrow
        if toggles["H"] and botA.engine is not None and not board.is_game_over():
            _, pv_now = engine_eval_and_pv(botA, board, time_limit=0.2)
            if pv_now:
                draw_arrow(screen, pv_now[0], color=GREEN, thickness=5)

        # Tactics overlay: highlight hanging pieces for side to move
        if toggles["T"] and not board.is_game_over():
            for sq in find_hanging_pieces(board, board.turn):
                draw_square_outline(screen, sq, RED, thickness=4)

        # If your last move was a blunder, outline the to-square briefly
        if toggles["H"] and last_player_move_blunder and last_move:
            draw_square_outline(screen, last_move.to_square, RED, thickness=5)

        # illegal overlay flash
        if pygame.time.get_ticks() < illegal_flash_until:
            s = pygame.Surface((BOARD_SIZE, BOARD_SIZE), pygame.SRCALPHA)
            s.fill((*ILLEGAL, 60))
            screen.blit(s, (MARGIN_X, MARGIN_TOP))

        mode_label = "Human vs Bot" if playing_human else ("Bot Duel" if duel else "Self-Play")
        turn_label = ("White" if board.turn == chess.WHITE else "Black") + " to move" if not board.is_game_over() else f"Game Over: {board.result()}"
        draw_sidebar(
            screen, panel_font, small_font, info_lines, score, ms_per_move,
            mode_label, turn_label, toggles, engine_active=(botA.engine is not None)
        )

        pygame.display.flip()
        clock.tick(60)

    botA.close(); botB.close()
    pygame.quit()

# ---------------- CLI ----------------
def main():
    ap = argparse.ArgumentParser(description="PyBot Chess — Coach Mode (H/O/T), right sidebar")
    ap.add_argument("--engine", type=str, default="", help="Path to UCI engine (optional; auto-detects if omitted)")
    ap.add_argument("--mode", type=str, default="human", choices=["human","self","duel"])
    ap.add_argument("--side", type=str, default="white", choices=["white","black"])
    ap.add_argument("--ms", type=int, default=300, help="delay per bot move (ms); adjust live with [ and ]")
    args = ap.parse_args()

    engine_path = autodetect_engine(args.engine)
    if engine_path:
        print(f"[PyBot] Using engine: {engine_path}")
    else:
        print("[PyBot] No engine found — coaching uses heuristics.")

    play_loop(args.mode, args.side, engine_path, args.ms)

if __name__ == "__main__":
    main()
