# -*- coding: utf-8 -*-
# SKILL_NAME: not_an_expert
# DESCRIPTION: Экспертный вердикт и мем «Я не эксперт, но...» от диванного инженера Crossout
# TRIGGERS: я не эксперт, не эксперт, эксперт, экспертное мнение, диванный эксперт, совет эксперта, вердикт эксперта
# REQUIREMENTS: pillow

import os
import sys
import random
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
SAVED_MEMES_DIR = os.path.join(BASE_DIR, "saved_memes")
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(SAVED_MEMES_DIR, exist_ok=True)

try:
    from db import get_kv, set_kv
except Exception:
    def get_kv(key, default=None):
        return default
    def set_kv(key, value):
        pass

def get_font(font_name_or_path, size):
    candidates = [
        font_name_or_path,
        os.path.join(MEDIA_DIR, font_name_or_path),
        os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
        os.path.join(MEDIA_DIR, "Montserrat.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    for c in candidates:
        if c and os.path.exists(c):
            try:
                f = ImageFont.truetype(c, size)
                # Verify Cyrillic support
                if f.getbbox("А") != f.getbbox("\ufffe"):
                    return f
            except Exception:
                continue
    return ImageFont.load_default()

def draw_text_with_outline(draw, pos, text, font, fill="white", outline="black", outline_width=2, anchor=None):
    x, y = pos
    if anchor:
        bbox = draw.textbbox((x, y), text, font=font, anchor=anchor)
    else:
        bbox = draw.textbbox((x, y), text, font=font)
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline, anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    return lines

VERDICTS = [
    {
        "asset": "gasgen.png",
        "intro": "Я не эксперт, но ставить Газген прямо под днище крафта на белых колёсах — это тактический гений.",
        "punchline": "До первой кочки или шальной дробинки из инвиза.",
        "stat_title": "Шанс детонации:",
        "stat_val": "99.9% (при спавне)",
        "grade": "Оценка: 10 Газгенов из 10"
    },
    {
        "asset": "ptur.png",
        "intro": "Я не эксперт, но если твой ПТУР развернулся на 180° и влетел в союзника — виновата геометрия карты.",
        "punchline": "Главное сразу написать в чат «Это была тактическая подсветка».",
        "stat_title": "Точность наведения:",
        "stat_val": "-40% в спину союзника",
        "grade": "Оценка: Стратег Пустошей"
    },
    {
        "asset": "kapkan.png",
        "intro": "Я не эксперт, но вражеский Капкан всегда ловит тебя за раму, а твой собственный ловит тиммейта на утюге.",
        "punchline": "Закон подлости пустошей работает стабильнее серверов.",
        "stat_title": "Сила удержания:",
        "stat_val": "Сильнее гравитации",
        "grade": "Оценка: Поймал своих"
    },
    {
        "asset": "mammoth.png",
        "intro": "Я не эксперт, но с двумя Мамонтами на синей раме главное не стрелять обоими стволами одновременно.",
        "punchline": "Иначе крафт сделает сальто назад и улетит в стратосферу.",
        "stat_title": "Отдача:",
        "stat_val": "Выбивает из катки",
        "grade": "Оценка: Баллистический цирк"
    },
    {
        "asset": "hover.png",
        "intro": "Я не эксперт, но срезать всю броню с ховера ради максимальной скорости — верный путь к успеху.",
        "punchline": "Правда, первый же выстрел дробовика превратит тебя в летающую кабину.",
        "stat_title": "Живучесть:",
        "stat_val": "1 микросекунда",
        "grade": "Оценка: Сквозняк в гараже"
    },
    {
        "asset": "scorpion.png",
        "intro": "Я не эксперт, но два Скорпиона на 4000 ОМ — это не педофильство, это деликатная проверка брони новичков.",
        "punchline": "Сквозной прострел кабины формирует характер с первого уровня.",
        "stat_title": "Баланс:",
        "stat_val": "Идеально честно (нет)",
        "grade": "Оценка: Заслуженный токсик"
    },
    {
        "asset": "yeti.png",
        "intro": "Я не эксперт, но включить Йети, заехать в куст на базе и простоять там весь раунд — это позиционный мастер-класс.",
        "punchline": "Команда проиграла, зато крафт остался не поцарапанным.",
        "stat_title": "Польза команде:",
        "stat_val": "0.0001%",
        "grade": "Оценка: Мастер кустов"
    },
    {
        "asset": "harvester.png",
        "intro": "Я не эксперт, но лобовой таран комбайном в борт вражеского левиафана решает любые тактические споры.",
        "punchline": "Особенно если у врага под капотом три бочки с бензином.",
        "stat_title": "Агрессия:",
        "stat_val": "Максимальная",
        "grade": "Оценка: Мясник металлолома"
    }
]

def generate_expert_meme(task_text="", input_photo=None):
    width, height = 1080, 1080
    bg_img = Image.new("RGBA", (width, height), (16, 18, 22, 255))
    draw = ImageDraw.Draw(bg_img)

    # Grid background
    for y in range(0, height, 30):
        draw.line([(0, y), (width, y)], fill=(24, 27, 34, 150), width=1)
    for x in range(0, width, 30):
        draw.line([(x, 0), (x, height)], fill=(24, 27, 34, 150), width=1)

    # Hazard stripes on top and bottom borders
    stripe_w = 28
    for i in range(-50, width + 50, stripe_w * 2):
        # Top hazard stripe
        draw.polygon([(i, 0), (i + stripe_w, 0), (i + stripe_w - 20, 24), (i - 20, 24)], fill=(235, 140, 20))
        # Bottom hazard stripe
        draw.polygon([(i, height - 24), (i + stripe_w, height - 24), (i + stripe_w - 20, height), (i - 20, height)], fill=(235, 140, 20))

    # Fonts
    font_badge = get_font("RussoOne-Regular.ttf", 20)
    font_header = get_font("RussoOne-Regular.ttf", 42)
    font_sub = get_font("Montserrat.ttf", 22)
    font_quote_head = get_font("RussoOne-Regular.ttf", 36)
    font_quote_body = get_font("Montserrat.ttf", 27)
    font_punchline = get_font("RussoOne-Regular.ttf", 28)
    font_stat_lbl = get_font("RussoOne-Regular.ttf", 20)
    font_stat_val = get_font("Montserrat.ttf", 22)
    font_footer = get_font("RussoOne-Regular.ttf", 18)

    # Header Panel (Dark steel card with neon orange border)
    draw.rectangle([(40, 45), (width - 40, 165)], fill=(25, 29, 36, 245), outline=(240, 100, 25), width=3)
    
    # Corner tactical accents
    for cx, cy in [(40, 45), (width - 60, 45), (40, 145), (width - 60, 145)]:
        draw.rectangle([(cx, cy), (cx + 20, cy + 20)], fill=(240, 100, 25))

    draw_text_with_outline(draw, (width // 2, 75), "CROSSOUT // ДИВАННАЯ ЭКСПЕРТИЗА", font_header, fill="#FFAA00", outline="#000000", outline_width=2, anchor="mm")
    draw_text_with_outline(draw, (width // 2, 125), "Официальное заключение Высшей Палаты Гаражных Инженеров", font_sub, fill="#E2E8F0", outline="#000000", outline_width=1, anchor="mm")

    # Select verdict
    t_low = (task_text or "").lower()
    matched = None
    for item in VERDICTS:
        kw = item["asset"].replace(".png", "")
        if kw in t_low:
            matched = item
            break
    if not matched:
        matched = random.choice(VERDICTS)

    # Center card area (600 px high)
    card_x0, card_y0 = 40, 190
    card_x1, card_y1 = width - 40, 890
    draw.rectangle([(card_x0, card_y0), (card_x1, card_y1)], fill=(20, 23, 29, 230), outline=(50, 56, 68), width=2)

    # If input photo is provided, embed it with an industrial viewfinder HUD
    asset_img_loaded = False
    if input_photo and os.path.exists(input_photo):
        try:
            user_pic = Image.open(input_photo).convert("RGBA")
            user_pic.thumbnail((440, 360), Image.Resampling.LANCZOS)
            uw, uh = user_pic.size
            ux = (width - uw) // 2
            uy = card_y0 + 35
            # Glow / border behind photo
            draw.rectangle([(ux - 6, uy - 6), (ux + uw + 6, uy + uh + 6)], fill=(10, 12, 15), outline=(235, 120, 20), width=2)
            bg_img.paste(user_pic, (ux, uy), user_pic)
            asset_img_loaded = True
            content_y_start = uy + uh + 30
        except Exception:
            asset_img_loaded = False

    if not asset_img_loaded:
        # Load Crossout icon asset
        asset_file = os.path.join(MEDIA_DIR, matched["asset"])
        if os.path.exists(asset_file):
            try:
                icon = Image.open(asset_file).convert("RGBA")
                icon.thumbnail((260, 260), Image.Resampling.LANCZOS)
                iw, ih = icon.size
                ix = (width - iw) // 2
                iy = card_y0 + 25
                # Glowing circle behind icon
                glow_box = [(ix - 25, iy - 10), (ix + iw + 25, iy + ih + 10)]
                draw.ellipse(glow_box, fill=(40, 35, 25, 180), outline=(245, 140, 20, 120), width=2)
                bg_img.paste(icon, (ix, iy), icon)
                content_y_start = iy + ih + 35
            except Exception:
                content_y_start = card_y0 + 50
        else:
            content_y_start = card_y0 + 50

    # Badge: «Я НЕ ЭКСПЕРТ, НО...»
    draw.rectangle([(width // 2 - 270, content_y_start), (width // 2 + 270, content_y_start + 48)], fill=(225, 45, 35), outline=(255, 215, 0), width=2)
    draw_text_with_outline(draw, (width // 2, content_y_start + 24), "« Я НЕ ЭКСПЕРТ, НО... »", font_quote_head, fill="#FFFFFF", outline="#400000", outline_width=2, anchor="mm")

    # Main text lines wrapped
    intro_lines = wrap_text(matched["intro"], font_quote_body, max_width=900, draw=draw)
    text_y = content_y_start + 70
    for l in intro_lines:
        draw_text_with_outline(draw, (width // 2, text_y), l, font_quote_body, fill="#F0F4F8", outline="#000000", outline_width=2, anchor="mm")
        text_y += 38

    # Punchline in neon yellow
    text_y += 15
    punch_lines = wrap_text(f"👉 {matched['punchline']}", font_punchline, max_width=920, draw=draw)
    for pl in punch_lines:
        draw_text_with_outline(draw, (width // 2, text_y), pl, font_punchline, fill="#FFDD00", outline="#101010", outline_width=2, anchor="mm")
        text_y += 42

    # Bottom stat badge inside the card
    stat_box_y = card_y1 - 85
    draw.rectangle([(60, stat_box_y), (width - 60, card_y1 - 20)], fill=(12, 14, 18, 220), outline=(80, 90, 105), width=1)
    
    # Stat 1
    draw.text((80, stat_box_y + 12), f"{matched['stat_title']} ", font=font_stat_lbl, fill="#FFA500")
    draw.text((80 + draw.textbbox((0, 0), f"{matched['stat_title']} ", font=font_stat_lbl)[2], stat_box_y + 11), matched['stat_val'], font=font_stat_val, fill="#FFFFFF")

    # Stat 2 (right aligned)
    r_text = matched['grade']
    r_bbox = draw.textbbox((0, 0), r_text, font=font_stat_lbl)
    r_w = r_bbox[2] - r_bbox[0]
    draw.text((width - 90 - r_w, stat_box_y + 12), r_text, font=font_stat_lbl, fill="#00FFCC")

    # Counter persistence in SQLite
    count = 1
    try:
        curr = get_kv("not_an_expert_count", "0")
        count = int(curr) + 1
        set_kv("not_an_expert_count", str(count))
    except Exception:
        count = random.randint(100, 999)

    # Stamp: «ОДОБРЕНО СВАРОЧНЫМ АППАРАТОМ»
    stamp_txt = f"ЗАКЛЮЧЕНИЕ ЭКСПЕРТА #{count} // ПРИНЯТО ЕДИНОГЛАСНО"
    draw_text_with_outline(draw, (width // 2, height - 55), stamp_txt, font_footer, fill="#94A3B8", outline="#000000", outline_width=1, anchor="mm")

    # Save image
    timestamp = int(time.time() * 1000)
    out_filename = f"not_an_expert_{timestamp}.png"
    out_path = os.path.join(MEDIA_DIR, out_filename)
    bg_img.convert("RGB").save(out_path, "PNG", quality=95)

    # Also save a copy to saved_memes/
    saved_copy = os.path.join(SAVED_MEMES_DIR, out_filename)
    try:
        bg_img.convert("RGB").save(saved_copy, "PNG")
    except Exception:
        pass

    return out_path, matched

def main():
    task_text = os.environ.get("TASK_TEXT") or (sys.argv[1] if len(sys.argv) > 1 else "Я не эксперт")
    input_file = os.environ.get("INPUT_FILE")
    if not input_file and len(sys.argv) > 2:
        input_file = sys.argv[2]
    if input_file and not os.path.exists(input_file):
        input_file = None

    image_path, verdict_data = generate_expert_meme(task_text=task_text, input_photo=input_file)

    # 1. Print media path for autonomous dispatcher
    print(image_path)

    # 2. Print natural Crossout gamer response for Yarik
    responses = [
        f"Держи экспертное заключение, Ярик! Диванный инженер Пустошей врать не станет 🛠️💥\n{verdict_data['intro']}",
        f"Консилиум гаражных экспертов вынес вердикт, Ярик! 🔥\n«Я не эксперт, но... {verdict_data['punchline']}»",
        f"Лови авторитетное мнение диванного эксперта Crossout! 🚗💨\n{verdict_data['grade']}"
    ]
    chosen_msg = random.choice(responses)
    print(chosen_msg)

if __name__ == "__main__":
    main()
