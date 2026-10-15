# -*- coding: utf-8 -*-
# SKILL_NAME: skill_mod
# DESCRIPTION: Бот, сгенерируй шахматную доску,на которой будет п
# TRIGGERS: шахматную доску, шахматы, слон со снайперкой, выцеливает ферзя, шахматная доска
# REQUIREMENTS: pillow

import os
import sys
import math
from PIL import Image, ImageDraw, ImageFont

def get_font(font_path, size):
    try:
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    except Exception:
        pass
    fallbacks = [
        "/app/media/RussoOne-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/app/media/Montserrat.ttf",
    ]
    for fb in fallbacks:
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, size)
            except Exception:
                pass
    return ImageFont.load_default()

def generate_sniper_chess_board(output_path=None):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    media_dir = os.path.join(base_dir, "media")
    os.makedirs(media_dir, exist_ok=True)
    
    if not output_path:
        output_path = os.path.join(media_dir, "chess_sniper_bishop.png")

    width = 1000
    height = 1180

    russo_path = os.path.join(media_dir, "RussoOne-Regular.ttf")
    dejavu_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    mont_path = os.path.join(media_dir, "Montserrat.ttf")

    font_title = get_font(russo_path, 34)
    font_sub = get_font(russo_path, 20)
    font_board_coord = get_font(russo_path, 18)
    font_piece = get_font(dejavu_path, 60)
    font_bubble = get_font(russo_path, 15)
    font_footer_bold = get_font(russo_path, 22)
    font_footer_sub = get_font(mont_path, 17)
    font_badge = get_font(russo_path, 14)

    # Base background (Crossout wasteland dark metal theme)
    base = Image.new("RGBA", (width, height), (18, 20, 24, 255))
    draw = ImageDraw.Draw(base)

    # Metal grid lines
    for y in range(0, height, 40):
        draw.line([(0, y), (width, y)], fill=(28, 30, 36, 120), width=1)
    for x in range(0, width, 40):
        draw.line([(x, 0), (x, height)], fill=(28, 30, 36, 120), width=1)

    # Header Panel
    draw.rectangle([(20, 15), (width - 20, 125)], fill=(26, 28, 35, 240), outline=(230, 90, 20), width=3)
    for x1, y1 in [(20, 15), (width - 60, 15), (20, 105), (width - 60, 105)]:
        draw.rectangle([(x1, y1), (x1 + 40, y1 + 20)], fill=(230, 90, 20))

    draw.text((width // 2, 45), "ШАХМАТЫ В ПУСТОШАХ CROSSOUT", font=font_title, fill=(255, 215, 0), anchor="mm")
    draw.text((width // 2, 85), "Когда белые уже орут «ШАХ И МАТ!», но забыли про открытую диагональ...", font=font_sub, fill=(220, 220, 230), anchor="mm")

    # Chessboard coordinates and dimensions
    board_size = 640
    sq_size = board_size // 8  # 80 px
    board_x = (width - board_size) // 2  # 180
    board_y = 170

    # Board outer wooden/metal frame
    pad = 28
    draw.rectangle([
        (board_x - pad, board_y - pad),
        (board_x + board_size + pad, board_y + board_size + pad)
    ], fill=(42, 28, 18, 255), outline=(210, 140, 50), width=4)

    # Board colors
    light_sq = (238, 216, 182, 255)
    dark_sq = (138, 86, 50, 255)

    # Coordinates
    cols = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    ranks = ['8', '7', '6', '5', '4', '3', '2', '1']

    for i, c in enumerate(cols):
        cx = board_x + i * sq_size + sq_size // 2
        draw.text((cx, board_y - 14), c.upper(), font=font_board_coord, fill=(255, 200, 100), anchor="mm")
        draw.text((cx, board_y + board_size + 14), c.upper(), font=font_board_coord, fill=(255, 200, 100), anchor="mm")

    for j, r in enumerate(ranks):
        cy = board_y + j * sq_size + sq_size // 2
        draw.text((board_x - 14, cy), r, font=font_board_coord, fill=(255, 200, 100), anchor="mm")
        draw.text((board_x + board_size + 14, cy), r, font=font_board_coord, fill=(255, 200, 100), anchor="mm")

    # Draw Squares
    for row in range(8):
        for col in range(8):
            x1 = board_x + col * sq_size
            y1 = board_y + row * sq_size
            is_dark = (row + col) % 2 == 1
            col_fill = dark_sq if is_dark else light_sq

            # Highlight sniper diagonal a1 -> h8 (row + col == 7)
            if row + col == 7:
                col_fill = (150, 60, 45, 255) if is_dark else (245, 195, 180, 255)

            draw.rectangle([(x1, y1), (x1 + sq_size, y1 + sq_size)], fill=col_fill, outline=(30, 20, 15, 60))

    # Board state dictionary: (row, col) -> (glyph, color_type, name)
    pieces = {
        # Black Pieces (Defending)
        (0, 7): ('♚', 'B', 'Black King'),    # h8 - Black King trapped!
        (0, 2): ('♜', 'B', 'Black Rook'),    # c8
        (1, 7): ('♟', 'B', 'Black Pawn'),    # h7
        (1, 5): ('♟', 'B', 'Black Pawn'),    # f7
        (1, 0): ('♟', 'B', 'Black Pawn'),    # a7
        (2, 2): ('♟', 'B', 'Black Pawn'),    # c6
        (7, 0): ('♝', 'B', 'SNIPER BISHOP'), # a1 - THE LEGENDARY SNIPER!

        # White Pieces (Attacking)
        (1, 6): ('♛', 'W', 'White Queen'),   # g7 - DELIVERING "MATE"!
        (3, 5): ('♞', 'W', 'White Knight'),  # f5 - Protecting g7!
        (2, 7): ('♟', 'W', 'White Pawn'),    # h6 - Supporting pawn
        (4, 3): ('♟', 'W', 'White Pawn'),    # d4
        (5, 4): ('♟', 'W', 'White Pawn'),    # e3
        (6, 6): ('♟', 'W', 'White Pawn'),    # g2
        (7, 6): ('♚', 'W', 'White King'),    # g1
        (7, 5): ('♜', 'W', 'White Rook'),    # f1
    }

    # Render pieces
    for (row, col), (glyph, ctype, name) in pieces.items():
        cx = board_x + col * sq_size + sq_size // 2
        cy = board_y + row * sq_size + sq_size // 2

        if ctype == 'W':
            fill_c = (255, 252, 245)
            stroke_c = (20, 20, 20)
        else:
            fill_c = (28, 28, 34)
            stroke_c = (235, 200, 150)

        # Bishop on a1 has special sniper highlight
        if (row, col) == (7, 0):
            draw.ellipse([(cx - 36, cy - 36), (cx + 36, cy + 36)], fill=(20, 80, 20, 180), outline=(50, 255, 50), width=2)
            fill_c = (35, 55, 35)
            stroke_c = (80, 255, 80)

        # Queen on g7 has special target highlight
        if (row, col) == (1, 6):
            draw.ellipse([(cx - 36, cy - 36), (cx + 36, cy + 36)], fill=(120, 15, 15, 180), outline=(255, 50, 50), width=3)

        draw.text((cx, cy), glyph, font=font_piece, fill=fill_c, stroke_width=2, stroke_fill=stroke_c, anchor="mm")

    # Coordinates for sniper laser: a1 -> g7
    a1_x = board_x + 0 * sq_size + sq_size // 2
    a1_y = board_y + 7 * sq_size + sq_size // 2
    g7_x = board_x + 6 * sq_size + sq_size // 2
    g7_y = board_y + 1 * sq_size + sq_size // 2

    # Laser sight overlay
    laser_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    laser_draw = ImageDraw.Draw(laser_layer)
    laser_draw.line([(a1_x, a1_y), (g7_x, g7_y)], fill=(255, 0, 0, 90), width=9)
    laser_draw.line([(a1_x, a1_y), (g7_x, g7_y)], fill=(255, 50, 50, 180), width=4)
    laser_draw.line([(a1_x, a1_y), (g7_x, g7_y)], fill=(255, 255, 255, 240), width=1)

    for step in range(1, 15):
        t = step / 15.0
        px = a1_x + (g7_x - a1_x) * t
        py = a1_y + (g7_y - a1_y) * t
        laser_draw.ellipse([(px - 3, py - 3), (px + 3, py + 3)], fill=(255, 220, 220, 200))

    base = Image.alpha_composite(base, laser_layer)
    draw = ImageDraw.Draw(base)

    # Sniper Crosshair on Queen (g7)
    cr_rad = 34
    draw.ellipse([(g7_x - cr_rad, g7_y - cr_rad), (g7_x + cr_rad, g7_y + cr_rad)], outline=(255, 20, 20, 255), width=3)
    draw.ellipse([(g7_x - 14, g7_y - 14), (g7_x + 14, g7_y + 14)], outline=(255, 20, 20, 200), width=1)
    draw.line([(g7_x - cr_rad - 12, g7_y), (g7_x + cr_rad + 12, g7_y)], fill=(255, 20, 20, 240), width=2)
    draw.line([(g7_x, g7_y - cr_rad - 12), (g7_x, g7_y + cr_rad + 12)], fill=(255, 20, 20, 240), width=2)
    draw.ellipse([(g7_x - 4, g7_y - 4), (g7_x + 4, g7_y + 4)], fill=(255, 50, 50, 255))

    # Target locked tag
    draw.rectangle([(g7_x + 38, g7_y - 28), (g7_x + 130, g7_y - 8)], fill=(180, 20, 20, 230), outline=(255, 255, 255), width=1)
    draw.text((g7_x + 84, g7_y - 18), "TARGET LOCKED", font=font_badge, fill=(255, 255, 255), anchor="mm")

    # Queen Speech Bubble
    qb_x1, qb_y1, qb_x2, qb_y2 = g7_x - 140, g7_y - 75, g7_x - 10, g7_y - 45
    draw.rounded_rectangle([(qb_x1, qb_y1), (qb_x2, qb_y2)], radius=6, fill=(255, 255, 255), outline=(20, 20, 20), width=2)
    draw.polygon([(qb_x2 - 10, qb_y2), (qb_x2, qb_y2 + 8), (qb_x2 - 2, qb_y2)], fill=(255, 255, 255))
    draw.text(((qb_x1 + qb_x2) // 2, (qb_y1 + qb_y2) // 2), "«ЭТО МАТ, ПСЫ!»", font=font_bubble, fill=(200, 20, 20), anchor="mm")

    # Black King sweating on h8
    hk_x = board_x + 7 * sq_size + sq_size // 2
    hk_y = board_y + 0 * sq_size + sq_size // 2
    draw.polygon([(hk_x + 18, hk_y - 20), (hk_x + 24, hk_y - 12), (hk_x + 12, hk_y - 12)], fill=(100, 200, 255))
    draw.ellipse([(hk_x + 12, hk_y - 14), (hk_x + 24, hk_y - 4)], fill=(100, 200, 255))

    # Sniper rifle barrel on a1 Bishop
    angle = math.atan2(g7_y - a1_y, g7_x - a1_x)
    barrel_len = 42
    bx_end = a1_x + math.cos(angle) * barrel_len
    by_end = a1_y + math.sin(angle) * barrel_len

    draw.line([(a1_x + 5, a1_y - 5), (bx_end, by_end)], fill=(30, 30, 30), width=5)
    draw.line([(a1_x + 5, a1_y - 5), (bx_end, by_end)], fill=(80, 80, 80), width=3)

    sc_cx = a1_x + math.cos(angle) * 20
    sc_cy = a1_y + math.sin(angle) * 20
    draw.line([(sc_cx - 4, sc_cy - 4), (sc_cx + 4, sc_cy + 4)], fill=(40, 220, 40), width=4)
    draw.ellipse([(bx_end - 4, by_end - 4), (bx_end + 4, by_end + 4)], fill=(255, 50, 50), outline=(255, 255, 255))

    # Bishop speech bubble
    bb_x1, bb_y1, bb_x2, bb_y2 = a1_x + 40, a1_y + 10, a1_x + 240, a1_y + 40
    draw.rounded_rectangle([(bb_x1, bb_y1), (bb_x2, bb_y2)], radius=6, fill=(20, 30, 20), outline=(50, 255, 50), width=2)
    draw.polygon([(bb_x1, bb_y1 + 10), (bb_x1 - 10, bb_y1 + 5), (bb_x1, bb_y1 + 18)], fill=(20, 30, 20))
    draw.text(((bb_x1 + bb_x2) // 2, (bb_y1 + bb_y2) // 2), "«В прицеле. Минус кабина.»", font=font_bubble, fill=(80, 255, 80), anchor="mm")

    # Badge on a1
    draw.rectangle([(a1_x - 38, a1_y + 26), (a1_x + 38, a1_y + 42)], fill=(0, 0, 0, 200), outline=(50, 255, 50), width=1)
    draw.text((a1_x, a1_y + 34), "СНАЙПЕР a1", font=font_badge, fill=(50, 255, 50), anchor="mm")

    # Crossout Scorpion emblem if available
    sc_path = os.path.join(media_dir, "scorpion.png")
    if os.path.exists(sc_path):
        try:
            sc_img = Image.open(sc_path).convert("RGBA")
            sc_img = sc_img.resize((90, 90), Image.Resampling.LANCZOS)
            base.paste(sc_img, (board_x - 130, board_y + board_size - 90), sc_img)
            draw.text((board_x - 85, board_y + board_size + 10), "«СКОРПИОН»", font=font_badge, fill=(255, 180, 50), anchor="mm")
        except Exception:
            pass

    # Footer Panel
    fy1 = height - 190
    fy2 = height - 20
    draw.rectangle([(20, fy1), (width - 20, fy2)], fill=(24, 26, 32, 250), outline=(230, 90, 20), width=3)

    for sx in range(20, width - 20, 30):
        draw.polygon([(sx, fy2 - 12), (sx + 15, fy2 - 12), (sx + 25, fy2), (sx + 10, fy2)], fill=(230, 90, 20))

    footer_title = "СЛОН НА a1 СО «СКОРПИОНОМ»: «ПОДЕРЖИ МОЙ ГАЗГЕН...»"
    draw.text((width // 2, fy1 + 35), footer_title, font=font_footer_bold, fill=(255, 215, 0), anchor="mm")

    footer_quote = "«Белые думали, что поставили мат на g7, но забыли закон Пустошей:\nНикогда не выезжай на открытую диагональ, пока жив реликтовый снайпер!»"
    draw.text((width // 2, fy1 + 90), footer_quote, font=font_footer_sub, fill=(230, 230, 230), anchor="mm", align="center")

    footer_stats = "Crossout Chess • Дистанция: 7 клеток • Урон: 100% пробитие • Bxg7#"
    draw.text((width // 2, fy1 + 138), footer_stats, font=font_badge, fill=(255, 120, 30), anchor="mm")

    # Convert and save
    base = base.convert("RGB")
    base.save(output_path, quality=95)
    return output_path

if __name__ == "__main__":
    result_path = generate_sniper_chess_board()
    print(result_path)