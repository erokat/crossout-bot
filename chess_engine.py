# -*- coding: utf-8 -*-
"""
CHESS ENGINE for Telegram Bot
High-resolution chessboard generator & visual puzzle renderer.
Supports:
- Clean/empty chessboards
- Custom piece placements by coordinate (Russian and English letters)
- Standard initial positions
- Tactical setups (sniper bishop, checkmate patterns)
- Highlights and move arrows
- Zero external heavy dependencies (uses PIL with pre-bundled Staunton sprites)
"""
import os
import re
import time
import math
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
PIECES_DIR = os.path.join(MEDIA_DIR, "chess_pieces")
SAVED_MEMES_DIR = os.path.join(BASE_DIR, "saved_memes")

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(PIECES_DIR, exist_ok=True)
os.makedirs(SAVED_MEMES_DIR, exist_ok=True)

CYRILLIC_TO_FILE = {
    'а': 'a', 'a': 'a',
    'б': 'b', 'в': 'b', 'b': 'b',
    'с': 'c', 'ц': 'c', 'c': 'c',
    'д': 'd', 'd': 'd',
    'е': 'e', 'e': 'e',
    'ф': 'f', 'f': 'f',
    'г': 'g', 'g': 'g',
    'х': 'h', 'н': 'h', 'h': 'h'
}

FILE_TO_CYRILLIC = {
    'a': 'A', 'b': 'B', 'c': 'C', 'd': 'D',
    'e': 'E', 'f': 'F', 'g': 'G', 'h': 'H'
}

PIECE_PATTERNS = [
    (r'(?:корол|king|\bкр\b)', 'K', 'король'),
    (r'(?:ферз|королев|queen|\bф\b)', 'Q', 'ферзь'),
    (r'(?:ладь|тур|rook|\bл\b)', 'R', 'ладья'),
    (r'(?:слон|офицер|bishop|\bсл\b)', 'B', 'слон'),
    (r'(?:кон|лошад|knight|\bкн\b)', 'N', 'конь'),
    (r'(?:пешк|pawn|\bп\b)', 'P', 'пешка')
]

COLOR_PATTERNS = [
    (r'(?:бел|white|\bw\b)', 'w', 'белый'),
    (r'(?:черн|чёрн|black|\bb\b)', 'b', 'чёрный')
]

INITIAL_CHESS_SETUP = {
    'a1': 'wR', 'b1': 'wN', 'c1': 'wB', 'd1': 'wQ', 'e1': 'wK', 'f1': 'wB', 'g1': 'wN', 'h1': 'wR',
    'a2': 'wP', 'b2': 'wP', 'c2': 'wP', 'd2': 'wP', 'e2': 'wP', 'f2': 'wP', 'g2': 'wP', 'h2': 'wP',
    'a7': 'bP', 'b7': 'bP', 'c7': 'bP', 'd7': 'bP', 'e7': 'bP', 'f7': 'bP', 'g7': 'bP', 'h7': 'bP',
    'a8': 'bR', 'b8': 'bN', 'c8': 'bB', 'd8': 'bQ', 'e8': 'bK', 'f8': 'bB', 'g8': 'bN', 'h8': 'bR',
}

def get_font(size=26, bold=True):
    candidates = [
        os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
        os.path.join(MEDIA_DIR, "Montserrat.ttf"),
        os.path.join(MEDIA_DIR, "Comfortaa.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()

def normalize_square(sq_raw):
    if not sq_raw or len(sq_raw) != 2:
        return None
    if sq_raw[0].isdigit():
        rank = sq_raw[0]
        f_char = sq_raw[1]
    else:
        f_char = sq_raw[0]
        rank = sq_raw[1]
    f_norm = CYRILLIC_TO_FILE.get(f_char.lower())
    if not f_norm or rank not in '12345678':
        return None
    return f"{f_norm}{rank}"

def parse_piece_name(raw_text):
    if not raw_text:
        return None
    for pat, p_code, _ in PIECE_PATTERNS:
        if re.search(pat, raw_text, re.IGNORECASE):
            return p_code
    return None

def parse_color_name(raw_text):
    if not raw_text:
        return 'w'
    for pat, c_code, _ in COLOR_PATTERNS:
        if re.search(pat, raw_text, re.IGNORECASE):
            return c_code
    return 'w'

WEAPON_MAP = {
    'птур': 'ptur',
    'ptur': 'ptur',
    'кларнет': 'ptur',
    'ракета': 'ptur',
    'газген': 'gasgen',
    'gasgen': 'gasgen',
    'генератор': 'gasgen',
    'вереск': 'heather',
    'heather': 'heather',
    'капкан': 'kapkan',
    'kapkan': 'kapkan',
    'мамонт': 'mammoth',
    'mammoth': 'mammoth',
    'пушка': 'mammoth',
    'скорпион': 'scorpion',
    'скорп': 'scorpion',
    'scorpion': 'scorpion',
    'ховер': 'hover',
    'hover': 'hover',
    'комбайн': 'harvester',
    'жнец': 'harvester',
    'harvester': 'harvester',
    'йети': 'yeti',
    'yeti': 'yeti',
    'колесо': 'wheel1',
    'снайперка': 'sniper_rifle',
    'снайперку': 'sniper_rifle',
    'снайперке': 'sniper_rifle',
    'снайпер': 'sniper_rifle',
    'снайперская': 'sniper_rifle',
    'снайперскую': 'sniper_rifle',
    'снайперское': 'sniper_rifle',
    'винтовка': 'sniper_rifle',
    'винтовку': 'sniper_rifle',
    'винтовке': 'sniper_rifle',
    'awp': 'sniper_rifle',
    'rifle': 'sniper_rifle',
    'прицел': 'sniper_rifle'
}

def is_chess_request(text, has_photo=False):
    if not text:
        return False
    t = text.lower()
    
    # Если прикреплено фото и запрос на фоторедактор (прифотошопь/прилепи/наложи), НЕ перехватывать
    if has_photo:
        clear_triggers = ["убери фигуры", "убери все фигуры", "очисти доску", "чистая доска", "стереть фигуры", "без фигур"]
        if not any(k in t for k in clear_triggers):
            if any(w in t for w in ["прифотошоп", "отфотошоп", "прилепи", "наложи", "вставь", "напиши", "добавь"]):
                return False

    chess_keywords = [
        "шахмат", "доск", "клетк", "ход кон", "fide",
        "мат на доске", "фигуры на доске", "чистая доска", "пустая доска", "убери фигуры",
        "убери все фигуры", "убери все фигуры и надписи", "очисти доску", "стереть фигуры",
        "расставь фигуры", "начальная позиция", "шахматн"
    ]
    if any(k in t for k in chess_keywords):
        return True

    # Проверка шахматной фигуры в контексте (например: «черной фигуре слон», «черный слон», «белый ферзь»)
    has_piece_context = bool(re.search(r'(?:фигур[а-я]*|бел[а-я]*|черн[а-я]*|чёрн[а-я]*)\s+(?:слон[а-я]*|ферз[а-я]*|корол[а-я]*|ладь[а-я]*|кон[а-я]*|пешк[а-я]*)', t))
    if has_piece_context:
        return True

    # If explicit coordinates are mentioned with chess piece words
    has_coord = bool(re.search(r'\b[a-hA-Hа-яА-Я][1-8]\b|\b[1-8][a-hA-Hа-яА-Я]\b', text))
    has_piece = any(re.search(pat, t) for pat, _, _ in PIECE_PATTERNS)
    return has_coord and has_piece

def parse_chess_request(text):
    t = text.lower()
    
    # 1. Empty board request
    empty_triggers = [
        "пуст", "убери все фигуры", "убери фигуры", "чист", "без фигур",
        "очисти доску", "стереть фигуры", "удали фигуры", "удали все фигуры",
        "без фигур и надписей", "убери все надписи"
    ]
    if any(p in t for p in empty_triggers) and not any(w in t for w in ["расставь", "начальн", "поставь", "сгенерируй", "прифотошопь", "оружие", "птур", "слон"]):
        return {}, "empty", None, None, None

    # 2. Initial / start position
    start_triggers = ["начальн", "стандартн", "расставь фигуры", "начальная позиция", "все фигуры на доске"]
    if any(p in t for p in start_triggers):
        return dict(INITIAL_CHESS_SETUP), "start", None, None, None

    # 2.5. Проверка наличия запроса на оружие / модуль (ПТУР, Газген, Вереск и т.д.)
    detected_weapon = None
    for kw, w_name in WEAPON_MAP.items():
        if re.search(r'\b' + re.escape(kw), t):
            detected_weapon = w_name
            break
    if not detected_weapon and any(w in t for w in ["птур", "ракета", "кларнет"]):
        detected_weapon = "ptur"

    # Определение цвета и фигуры
    col = 'b' if any(w in t for w in ["черн", "чёрн", "black"]) else ('w' if any(w in t for w in ["бел", "white"]) else ('b' if detected_weapon else 'w'))
    piece = 'B'
    if any(w in t for w in ["слон", "офицер", "bishop"]):
        piece = 'B'
    elif any(w in t for w in ["ферз", "королев", "queen"]):
        piece = 'Q'
    elif any(w in t for w in ["корол", "king"]):
        piece = 'K'
    elif any(w in t for w in ["ладь", "rook"]) or re.search(r'\bтур[а-я]*\b', t):
        piece = 'R'
    elif any(w in t for w in ["кон", "лошад", "knight"]):
        piece = 'N'
    elif any(w in t for w in ["пешк", "pawn"]):
        piece = 'P'

    # Проверка явных координат
    coord_match = re.search(r'\b([a-hA-Hа-яА-Я][1-8]|[1-8][a-hA-Hа-яА-Я])\b', t)
    target_sq = normalize_square(coord_match.group(1)) if coord_match else None
    all_coords = re.findall(r'\b([a-hA-Hа-яА-Я][1-8]|[1-8][a-hA-Hа-яА-Я])\b', t)

    # Если запрошено оружие для фигуры (например: «черной фигуре слон оружие птур») ТОЛЬКО если 1 координата
    if detected_weapon and len(all_coords) <= 1:
        if target_sq:
            pieces = {target_sq: f"{col}{piece}"}
            attachments = {target_sq: detected_weapon}
            highlights = {target_sq: (80, 220, 120, 140)}
            return pieces, "weapon_custom", highlights, None, attachments
        else:
            # Если слон с оружием
            if piece == 'B':
                pieces = {'b1': 'bK', 'b3': 'wK', 'c2': 'wQ', 'h7': f"{col}B"}
                arrow = ('h7', 'c2')
                highlights = {'c2': (255, 90, 90, 140), 'h7': (80, 220, 120, 140)}
                attachments = {'h7': detected_weapon}
                return pieces, "weapon_sniper", highlights, arrow, attachments
            else:
                default_sq = 'c2' if piece == 'Q' else ('e8' if piece == 'K' else ('a1' if piece == 'R' else 'd4'))
                pieces = {default_sq: f"{col}{piece}"}
                attachments = {default_sq: detected_weapon}
                highlights = {default_sq: (80, 220, 120, 140)}
                return pieces, "weapon_custom", highlights, None, attachments

    # 3. Explicit coordinate-based placement
    pieces = {}
    
    # Regex 1: "на клетке B1 черного короля", "B1 черного короля", "на B1 черный король"
    regex1 = re.finditer(
        r'(?:на\s+(?:клетке\s+|клетку\s+)?)?([a-hA-Hа-яА-Я][1-8]|[1-8][a-hA-Hа-яА-Я])\s+(?:(?:(бел[а-я]*|черн[а-я]*|чёрн[а-я]*|white|black)\s+)?([а-яa-z]+)|([а-яa-z]+)\s+(бел[а-я]*|черн[а-я]*|чёрн[а-я]*|white|black))',
        t
    )
    for m in regex1:
        sq_raw = m.group(1)
        col_raw = m.group(2) or m.group(5) or ''
        piece_raw = m.group(3) or m.group(4) or ''
        sq = normalize_square(sq_raw)
        if not sq:
            continue
        col_parsed = parse_color_name(col_raw)
        piece_parsed = parse_piece_name(piece_raw)
        if piece_parsed:
            pieces[sq] = f"{col_parsed}{piece_parsed}"

    # Regex 2: "черного короля на B1", "белого ферзя на клетку C2"
    regex2 = re.finditer(
        r'(?:(бел[а-я]*|черн[а-я]*|чёрн[а-я]*|white|black)\s+)?([а-яa-z]+)\s+(?:(бел[а-я]*|черн[а-я]*|чёрн[а-я]*|white|black)\s+)?(?:на\s+(?:клетку\s+|клетке\s+)?)?([a-hA-Hа-яА-Я][1-8]|[1-8][a-hA-Hа-яА-Я])',
        t
    )
    for m in regex2:
        col_raw = m.group(1) or m.group(3) or ''
        piece_raw = m.group(2) or ''
        sq_raw = m.group(4)
        sq = normalize_square(sq_raw)
        if not sq:
            continue
        col_parsed = parse_color_name(col_raw)
        piece_parsed = parse_piece_name(piece_raw)
        if piece_parsed and sq not in pieces:
            pieces[sq] = f"{col_parsed}{piece_parsed}"

    # Check for laser / sniper diagonal arrow
    arrow = None
    highlights = None
    if 'h7' in pieces and pieces['h7'] in ['bB', 'wB'] and 'c2' in pieces and pieces['c2'] in ['wQ', 'bQ']:
        arrow = ('h7', 'c2')
        highlights = {'c2': (255, 90, 90, 140), 'h7': (80, 220, 120, 140)}
    elif 'a1' in pieces and 'g7' in pieces:
        arrow = ('a1', 'g7')
        highlights = {'g7': (255, 90, 90, 140), 'a1': (80, 220, 120, 140)}

    # Attachments for coordinate-based placement if weapon requested
    attachments = None
    if detected_weapon and pieces:
        target_weapon_sq = None
        # Check if specific piece type was named for weapon
        if any(w in t for w in ["слон", "офицер", "bishop"]):
            for sq, p_code in pieces.items():
                if p_code[1] == 'B':
                    target_weapon_sq = sq
                    break
        elif any(w in t for w in ["ферз", "queen"]):
            for sq, p_code in pieces.items():
                if p_code[1] == 'Q':
                    target_weapon_sq = sq
                    break
        elif any(w in t for w in ["ладь", "rook"]):
            for sq, p_code in pieces.items():
                if p_code[1] == 'R':
                    target_weapon_sq = sq
                    break
        elif any(w in t for w in ["кон", "knight"]):
            for sq, p_code in pieces.items():
                if p_code[1] == 'N':
                    target_weapon_sq = sq
                    break

        if not target_weapon_sq and arrow:
            target_weapon_sq = arrow[0]

        if not target_weapon_sq:
            non_kings = [sq for sq, p_code in pieces.items() if p_code[1] != 'K']
            target_weapon_sq = non_kings[0] if non_kings else list(pieces.keys())[0]

        if target_weapon_sq:
            attachments = {target_weapon_sq: detected_weapon}
            if not highlights:
                highlights = {}
            if target_weapon_sq not in highlights:
                highlights[target_weapon_sq] = (80, 220, 120, 140)

    if pieces:
        mode = "custom_weapon" if attachments else "custom"
        return pieces, mode, highlights, arrow, attachments

    # 4. Semantic checkmate / 2 kings + 1 queen pattern
    if any(w in t for w in ["2 короля", "двух королей", "2 королей"]) or ("корол" in t and "ферз" in t and any(w in t for w in ["мат", "ставит мат", "почти мат", "ловушк"])):
        # Check if bishop / sniper is mentioned
        if any(w in t for w in ["слон", "выцеливает", "засад", "снайпер"]):
            pieces = {'b1': 'bK', 'b3': 'wK', 'c2': 'wQ', 'h7': 'bB'}
            arrow = ('h7', 'c2')
            highlights = {'c2': (255, 90, 90, 140), 'h7': (80, 220, 120, 140)}
            weapon_att = detected_weapon or ("sniper_rifle" if any(w in t for w in ["снайпер", "винтовк"]) else None)
            attachments = {'h7': weapon_att} if weapon_att else None
            return pieces, "sniper", highlights, arrow, attachments
        else:
            pieces = {'e8': 'bK', 'e6': 'wK', 'e7': 'wQ'}
            highlights = {'e8': (255, 90, 90, 140), 'e7': (255, 215, 0, 140)}
            return pieces, "mate", highlights, None, None

    # 4.5. Если просто упомянут слон или другая фигура без координат
    if any(w in t for w in ["слон", "офицер", "bishop"]):
        pieces = {'b1': 'bK', 'b3': 'wK', 'c2': 'wQ', 'h7': f"{col}B"}
        arrow = ('h7', 'c2')
        highlights = {'c2': (255, 90, 90, 140), 'h7': (80, 220, 120, 140)}
        weapon_att = detected_weapon or ("sniper_rifle" if any(w in t for w in ["снайпер", "винтовк"]) else None)
        attachments = {'h7': weapon_att} if weapon_att else None
        return pieces, "sniper", highlights, arrow, attachments

    # 5. Fallback: clean empty board ТОЛЬКО если прямо просили пустую доску
    return {}, "empty", None, None, None

def render_chess_board(pieces_dict=None, highlight_squares=None, arrow=None, attachments=None, out_path=None):
    """
    Renders an elegant high-resolution chessboard (1000x1000 px).
    - Pieces: classic transparent Staunton sprites.
    - Coordinates: bold, high-contrast labels on border.
    - Highlights & arrows for moves and tactics.
    - Attachments: weapons/modules (PTUR, Gasgen, Heather) mounted on pieces.
    """
    pieces = pieces_dict or {}
    sq_size = 112
    margin = 52
    board_px = sq_size * 8
    img_size = board_px + margin * 2

    # Create dark mahogany wood border
    img = Image.new("RGBA", (img_size, img_size), (40, 32, 28, 255))
    draw = ImageDraw.Draw(img)

    light_sq = (240, 217, 181, 255) # Classic light tournament cream
    dark_sq = (181, 136, 99, 255)   # Classic dark warm walnut

    files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    ranks = ['8', '7', '6', '5', '4', '3', '2', '1']

    # Draw squares
    for r in range(8):
        for c in range(8):
            x = margin + c * sq_size
            y = margin + r * sq_size
            col = light_sq if (r + c) % 2 == 0 else dark_sq
            draw.rectangle([x, y, x + sq_size, y + sq_size], fill=col)

    # Highlight squares if requested
    if highlight_squares:
        overlay = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
        o_draw = ImageDraw.Draw(overlay)
        for sq_code, col_val in highlight_squares.items():
            f_char, r_char = sq_code[0].lower(), sq_code[1]
            if f_char in files and r_char in ranks:
                c_idx = files.index(f_char)
                r_idx = ranks.index(r_char)
                hx = margin + c_idx * sq_size
                hy = margin + r_idx * sq_size
                hl_color = col_val if isinstance(col_val, tuple) else (255, 215, 0, 130)
                o_draw.rectangle([hx, hy, hx + sq_size, hy + sq_size], fill=hl_color)
                o_draw.rectangle([hx + 2, hy + 2, hx + sq_size - 2, hy + sq_size - 2], outline=(255, 255, 255, 180), width=3)
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

    # Inner crisp border line around the board
    draw.rectangle([margin - 1, margin - 1, margin + board_px, margin + board_px], outline=(25, 20, 17, 255), width=3)

    # Draw coordinates
    font_coords = get_font(26, bold=True)
    coord_color = (244, 226, 199, 255)

    for i, f_char in enumerate(files):
        x = margin + i * sq_size + sq_size // 2
        f_upper = f_char.upper()
        draw.text((x, margin // 2), f_upper, font=font_coords, fill=coord_color, anchor="mm")
        draw.text((x, margin + board_px + margin // 2), f_upper, font=font_coords, fill=coord_color, anchor="mm")

    for i, r_char in enumerate(ranks):
        y = margin + i * sq_size + sq_size // 2
        draw.text((margin // 2, y), r_char, font=font_coords, fill=coord_color, anchor="mm")
        draw.text((margin + board_px + margin // 2, y), r_char, font=font_coords, fill=coord_color, anchor="mm")

    # Draw arrow if specified
    if arrow:
        from_sq, to_sq = arrow
        if from_sq[0] in files and from_sq[1] in ranks and to_sq[0] in files and to_sq[1] in ranks:
            c1 = files.index(from_sq[0])
            r1 = ranks.index(from_sq[1])
            c2 = files.index(to_sq[0])
            r2 = ranks.index(to_sq[1])
            x1 = margin + c1 * sq_size + sq_size // 2
            y1 = margin + r1 * sq_size + sq_size // 2
            x2 = margin + c2 * sq_size + sq_size // 2
            y2 = margin + r2 * sq_size + sq_size // 2

            arrow_layer = Image.new("RGBA", (img_size, img_size), (0, 0, 0, 0))
            a_draw = ImageDraw.Draw(arrow_layer)

            # Draw laser / tactic line
            a_draw.line([(x1, y1), (x2, y2)], fill=(255, 45, 45, 200), width=6)
            
            # Draw targeting crosshair at destination
            a_draw.ellipse([x2 - 32, y2 - 32, x2 + 32, y2 + 32], outline=(255, 40, 40, 220), width=3)
            a_draw.line([(x2 - 42, y2), (x2 + 42, y2)], fill=(255, 40, 40, 220), width=3)
            a_draw.line([(x2, y2 - 42), (x2, y2 + 42)], fill=(255, 40, 40, 220), width=3)

            img = Image.alpha_composite(img, arrow_layer)
            draw = ImageDraw.Draw(img)

    # Draw chess pieces
    piece_size = sq_size - 14
    for sq, p_code in pieces.items():
        f_char, r_char = sq[0].lower(), sq[1]
        if f_char not in files or r_char not in ranks:
            continue
        c_idx = files.index(f_char)
        r_idx = ranks.index(r_char)
        p_path = os.path.join(PIECES_DIR, f"{p_code}.png")
        if os.path.exists(p_path):
            try:
                p_img = Image.open(p_path).convert("RGBA")
                p_img = p_img.resize((piece_size, piece_size), Image.Resampling.LANCZOS)
                px = margin + c_idx * sq_size + (sq_size - piece_size) // 2
                py = margin + r_idx * sq_size + (sq_size - piece_size) // 2
                img.paste(p_img, (px, py), p_img)
            except Exception as e:
                print(f"[CHESS PIECE ERROR] Failed to draw {p_code}: {e}")

    # Draw attachments / weapons on pieces
    if attachments:
        for sq, weapon in attachments.items():
            f_char, r_char = sq[0].lower(), sq[1]
            if f_char not in files or r_char not in ranks:
                continue
            c_idx = files.index(f_char)
            r_idx = ranks.index(r_char)
            piece_cx = margin + c_idx * sq_size + sq_size // 2
            piece_cy = margin + r_idx * sq_size + sq_size // 2
            px = margin + c_idx * sq_size + (sq_size - piece_size) // 2
            py = margin + r_idx * sq_size + (sq_size - piece_size) // 2

            weapon_file = os.path.join(MEDIA_DIR, f"{weapon}.png")
            if os.path.exists(weapon_file):
                try:
                    w_raw = Image.open(weapon_file).convert("RGBA")
                    if weapon == "sniper_rifle":
                        target_center = None
                        if arrow and arrow[0].lower() == sq.lower():
                            to_sq = arrow[1].lower()
                            if to_sq[0] in files and to_sq[1] in ranks:
                                tc = files.index(to_sq[0])
                                tr = ranks.index(to_sq[1])
                                target_center = (
                                    margin + tc * sq_size + sq_size // 2,
                                    margin + tr * sq_size + sq_size // 2
                                )

                        w_scale = 105.0 / max(w_raw.width, w_raw.height)
                        new_w = max(24, int(w_raw.width * w_scale))
                        new_h = max(24, int(w_raw.height * w_scale))
                        w_resized = w_raw.resize((new_w, new_h), Image.Resampling.LANCZOS)

                        if target_center:
                            dx = target_center[0] - piece_cx
                            dy = target_center[1] - piece_cy
                            target_angle = math.degrees(math.atan2(dy, dx))
                            rot_deg = -(target_angle + 45)
                            w_resized = w_resized.rotate(rot_deg, resample=Image.Resampling.BICUBIC, expand=True)

                        wx = piece_cx - w_resized.width // 2
                        wy = piece_cy - w_resized.height // 2
                        img.paste(w_resized, (wx, wy), w_resized)
                    else:
                        w_scale = 68.0 / max(w_raw.width, w_raw.height)
                        new_w = max(24, int(w_raw.width * w_scale))
                        new_h = max(24, int(w_raw.height * w_scale))
                        w_resized = w_raw.resize((new_w, new_h), Image.Resampling.LANCZOS)
                        wx = px + piece_size - new_w + 6
                        wy = py - 6
                        img.paste(w_resized, (wx, wy), w_resized)
                except Exception as e:
                    print(f"[CHESS WEAPON ERROR] Failed to draw {weapon}: {e}")

    # Convert to RGB and save
    final_img = img.convert("RGB")
    if not out_path:
        out_path = os.path.join(MEDIA_DIR, f"chess_{int(time.time() * 1000)}.png")
    final_img.save(out_path, "PNG", quality=95)

    # Copy to saved_memes for persistence
    try:
        copy_path = os.path.join(SAVED_MEMES_DIR, os.path.basename(out_path))
        if copy_path != out_path:
            final_img.save(copy_path, "PNG", quality=95)
    except Exception:
        pass

    return out_path

def process_chess_command(text, sender_name="Ярик", reply_to_photo=None):
    """
    Main entry point for handling chess requests from chat.
    Returns (image_path, caption_text).
    """
    parsed = parse_chess_request(text)
    if len(parsed) == 5:
        pieces, mode, highlights, arrow, attachments = parsed
    else:
        pieces, mode, highlights, arrow = parsed
        attachments = None

    # If replying to a photo asking to remove figures
    if reply_to_photo and any(w in text.lower() for w in ["убери", "очисти", "без фигур", "стереть", "чист"]):
        pieces = {}
        mode = "empty"
        highlights = None
        arrow = None
        attachments = None

    out_file = os.path.join(MEDIA_DIR, f"chess_{int(time.time() * 1000)}.png")
    image_path = render_chess_board(pieces_dict=pieces, highlight_squares=highlights, arrow=arrow, attachments=attachments, out_path=out_file)

    if mode == "empty":
        caption = f"Держи чистую шахматную доску без фигур! ♟️"
    elif mode == "start":
        caption = f"Расставил все 32 фигуры в начальную позицию. Партия начинается! ♟️👑"
    elif mode in ["weapon_sniper", "weapon_custom", "custom_weapon"]:
        w_name = attachments.get(list(attachments.keys())[0], "оружие") if attachments else "оружие"
        if w_name == "sniper_rifle":
            w_text = "снайперской винтовкой с оптическим прицелом"
        elif w_name == "ptur":
            w_text = "ракетным комплексом ПТУР"
        else:
            w_text = f"модулем {w_name.upper()}"

        desc_parts = []
        for sq, p_code in pieces.items():
            color_ru = "белый" if p_code[0] == 'w' else "чёрный"
            p_map = {'K': 'король', 'Q': 'ферзь', 'R': 'ладья', 'B': 'слон', 'N': 'конь', 'P': 'пешка'}
            piece_ru = p_map.get(p_code[1], 'фигура')
            desc_parts.append(f"{color_ru} {piece_ru} на {sq.upper()}")
        pieces_summary = ", ".join(desc_parts)

        if arrow:
            from_sq, to_sq = arrow
            caption = f"Готово, {sender_name}! Расставил фигуры по координатам ({pieces_summary}), вооружил фигуру на {from_sq.upper()} {w_text} и взял на прицел {to_sq.upper()}! ♟️🎯"
        else:
            caption = f"Готово, {sender_name}! Расставил фигуры по координатам ({pieces_summary}) и вооружил {w_text}! ♟️🔥"
    elif mode == "sniper":
        caption = f"Шахматная доска готова! Черный слон с H7 выцеливает белого ферзя на C2 через всю диагональ ♟️🎯"
    elif mode == "mate":
        caption = f"Позиция готова: белый ферзь ставит мат черному королю! ♟️👑"
    else:
        # Describe custom placed pieces nicely
        desc_parts = []
        for sq, p_code in pieces.items():
            color_ru = "белый" if p_code[0] == 'w' else "чёрный"
            p_map = {'K': 'король', 'Q': 'ферзь', 'R': 'ладья', 'B': 'слон', 'N': 'конь', 'P': 'пешка'}
            piece_ru = p_map.get(p_code[1], 'фигура')
            desc_parts.append(f"{color_ru} {piece_ru} на {sq.upper()}")
        pieces_summary = ", ".join(desc_parts)
        caption = f"Готово, {sender_name}! Расставил фигуры по координатам ({pieces_summary}) ♟️🔥"

    return image_path, caption
