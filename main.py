# main.py
import os
import asyncio
import pygame
import chess
from chess_ai import ChessAI

# ---------------- Layout / colors ----------------
BOARD_SIZE = 640
MARGIN_X = 24
MARGIN_TOP = 24
GAP = 16
SIDEBAR_W = 320
SQ = BOARD_SIZE // 8

LIGHT, DARK = (240, 217, 181), (181, 136, 99)
HIGHLIGHT, LASTMOVE = (246, 246, 105), (186, 202, 68)
BG, PANEL_BG = (24, 26, 31), (34, 36, 43)
TEXT, SUBTEXT = (230, 230, 235), (200, 210, 220)
ILLEGAL, GREEN, RED, ACCENT = (220, 80, 80), (60, 200, 120), (220, 80, 80), (120, 170, 255)

CENTER_SQS = {chess.D4, chess.E4, chess.D5, chess.E5}

# ---------------- Helper Functions ----------------
def square_to_xy(sq):
    f, r = chess.square_file(sq), 7 - chess.square_rank(sq)
    return (MARGIN_X + f * SQ, MARGIN_TOP + r * SQ)

def xy_to_square(px, py):
    if not pygame.Rect(MARGIN_X, MARGIN_TOP, BOARD_SIZE, BOARD_SIZE).collidepoint(px, py): return None
    return chess.square((px - MARGIN_X) // SQ, 7 - (py - MARGIN_TOP) // SQ)

def load_pieces(folder="pieces-png", size=SQ - 8):
    pieces = {}
    # Basic mapping for web compatibility
    for ptype in [1,2,3,4,5,6]:
        for color in [True, False]:
            c_name = "white" if color else "black"
            p_name = chess.piece_name(ptype)
            path = os.path.join(folder, f"{c_name}-{p_name}.png")
            if os.path.exists(path):
                img = pygame.image.load(path).convert_alpha()
                pieces[(ptype, color)] = pygame.transform.smoothscale(img, (size, size))
    return pieces

# ---------------- Draw Routines ----------------
def draw_board(surface, board, last_move, selected, pieces):
    surface.fill(BG)
    for r in range(8):
        for f in range(8):
            pygame.draw.rect(surface, LIGHT if (r+f)%2==0 else DARK, (MARGIN_X + f * SQ, MARGIN_TOP + r * SQ, SQ, SQ))
    
    for sq, piece in board.piece_map().items():
        x, y = square_to_xy(sq)
        if (piece.piece_type, piece.color) in pieces:
            surface.blit(pieces[(piece.piece_type, piece.color)], (x+4, y+4))

# ---------------- Main Game Loop ----------------
async def main():
    pygame.init()
    screen = pygame.display.set_mode((MARGIN_X*2 + BOARD_SIZE + GAP + SIDEBAR_W, MARGIN_TOP*2 + BOARD_SIZE))
    pygame.display.set_caption("CheckMate Web")
    
    pieces = load_pieces()
    board = chess.Board()
    bot = ChessAI(engine_path=None) # Heuristic mode for web safety
    
    selected = None
    running = True
    clock = pygame.time.Clock()

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                sq = xy_to_square(*event.pos)
                if sq is not None:
                    pc = board.piece_at(sq)
                    if selected is None and pc and pc.color == board.turn:
                        selected = sq
                    elif selected is not None:
                        move = chess.Move(selected, sq)
                        if move in board.legal_moves:
                            board.push(move)
                        selected = None

        # Bot Move
        if not board.is_game_over() and board.turn == chess.BLACK:
            await asyncio.sleep(0.5) # Give the user a moment to see their move
            move = bot.choose_move(board)
            board.push(move)

        draw_board(screen, board, None, selected, pieces)
        pygame.display.flip()
        
        # This line is CRITICAL for web support
        await asyncio.sleep(0) 
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    asyncio.run(main())
