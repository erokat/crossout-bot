import os
import random
import time
from PIL import Image, ImageDraw, ImageFont

from config import MEDIA_DIR, SAVED_MEMES_DIR

def get_font(size):
    font_paths = [
        os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
        os.path.join(MEDIA_DIR, "RobotoCondensed-Bold.ttf"),
        os.path.join(MEDIA_DIR, "Anton.ttf"),
        os.path.join(MEDIA_DIR, "Comfortaa.ttf"),
        os.path.join(MEDIA_DIR, "Oswald.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

def draw_text_with_outline(draw, pos, text, font, fill="white", outline="black", outline_width=3):
    x, y = pos
    for dx in range(-outline_width, outline_width + 1):
        for dy in range(-outline_width, outline_width + 1):
            if dx != 0 or dy != 0:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)

def generate_crossout_meme(theme=""):
    theme_lower = theme.lower()
    width, height = 900, 900
    img = Image.new("RGB", (width, height), color=(20, 22, 28))
    draw = ImageDraw.Draw(img)
    font_title = get_font(40)
    font_body = get_font(30)
    font_sub = get_font(26)

    gasgen_path = os.path.join(MEDIA_DIR, "gasgen.png")
    ptur_path = os.path.join(MEDIA_DIR, "ptur.png")
    kapkan_path = os.path.join(MEDIA_DIR, "kapkan.png")
    heather_path = os.path.join(MEDIA_DIR, "heather.png")
    mammoth_path = os.path.join(MEDIA_DIR, "mammoth.png")
    doge_path = os.path.join(MEDIA_DIR, "tpl_doge.png")
    clown_path = os.path.join(MEDIA_DIR, "tpl_clown.png")
    scorp_path = os.path.join(MEDIA_DIR, "scorpion.png")
    harv_path = os.path.join(MEDIA_DIR, "harvester.png")

    if "автосборк" in theme_lower:
        draw_text_with_outline(draw, (50, 40), "АВТОСБОРКА В CROSSOUT:", font_title, fill="#FFCC00")
        draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
        draw_text_with_outline(draw, (50, 130), "Ожидание: идеальный сбалансированный крафт", font_body, fill="#00FFCC")
        draw_text_with_outline(draw, (50, 180), "Реальность:", font_body, fill="#FF4444")
        
        if os.path.exists(gasgen_path):
            g = Image.open(gasgen_path).convert("RGBA").resize((280, 280))
            img.paste(g, (100, 280), g)
            draw_text_with_outline(draw, (80, 580), "Газген на бампере", font_body)
        if os.path.exists(ptur_path):
            p = Image.open(ptur_path).convert("RGBA").resize((320, 260))
            img.paste(p, (480, 290), p)
            draw_text_with_outline(draw, (490, 580), "ПТУР в лоб кабине", font_body)
            
        draw_text_with_outline(draw, (60, 700), "⚠️ ПЕРЕГРУЗ: +6500 КГ | СКОРОСТЬ: 3 КМ/Ч", font_title, fill="#FF2222")
        draw_text_with_outline(draw, (180, 780), "«Шедевр инженерной мысли»", font_body, fill="#CCCCCC")

    elif "газген" in theme_lower or "взрыв" in theme_lower:
        draw_text_with_outline(draw, (80, 40), "ПОСТАВИЛ ГАЗГЕН В ПУСТОШАХ", font_title, fill="#FF3333")
        draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
        draw_text_with_outline(draw, (60, 140), "1. Заспавнился в бою с хорошим настроением", font_body)
        
        if os.path.exists(gasgen_path):
            g = Image.open(gasgen_path).convert("RGBA").resize((320, 320))
            img.paste(g, (290, 240), g)
            
        draw_text_with_outline(draw, (60, 600), "2. Шальная пуля коснулась заднего брызговика", font_body, fill="#FFCC00")
        draw_text_with_outline(draw, (120, 700), "💥 ВЗРЫВ СИЛОЙ 10 МЕГАТОНН 💥", font_title, fill="#FF2222")
        draw_text_with_outline(draw, (230, 780), "«Ушел в ангар на 5-й секунде»", font_body, fill="#AAAAAA")

    elif "птур" in theme_lower:
        draw_text_with_outline(draw, (120, 40), "ТИПИЧНЫЙ ПТУРОВОД В БОЮ", font_title, fill="#00CCFF")
        draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
        draw_text_with_outline(draw, (60, 140), "Стоит за холмом в инвизе 3 минуты...", font_body)
        
        if os.path.exists(ptur_path):
            p = Image.open(ptur_path).convert("RGBA").resize((380, 300))
            img.paste(p, (260, 230), p)
            
        draw_text_with_outline(draw, (60, 600), "Запускает ракету через всю карту 🚀", font_body, fill="#FFFF44")
        draw_text_with_outline(draw, (80, 700), "Итог: врезался в свой же дрон и сгорел 😂", font_title, fill="#FF4444")
        draw_text_with_outline(draw, (250, 780), "«Снайпер от Бога»", font_body, fill="#888888")

    else:
        # Универсальный мем по Пустошам
        draw_text_with_outline(draw, (80, 50), "ТИПИЧНЫЙ РАНДОМ В CROSSOUT", font_title, fill="#FFCC00")
        draw.line([(50, 110), (850, 110)], fill="#555555", width=3)
        
        draw_text_with_outline(draw, (60, 150), "Когда накопил 40к монет на топ-крафт...", font_body, fill="#FFFFFF")
        
        if os.path.exists(kapkan_path):
            k = Image.open(kapkan_path).convert("RGBA").resize((260, 260))
            img.paste(k, (100, 260), k)
            draw_text_with_outline(draw, (70, 540), "1. Поймал Капкан", font_body, fill="#FF6666")
        if os.path.exists(heather_path):
            h = Image.open(heather_path).convert("RGBA").resize((300, 260))
            img.paste(h, (500, 260), h)
            draw_text_with_outline(draw, (480, 540), "2. Прилетел Вереск", font_body, fill="#FF6666")
            
        draw_text_with_outline(draw, (100, 680), "Итог: Гараж через 15 секунд боя 💀", font_title, fill="#FF3333")
        draw_text_with_outline(draw, (220, 780), "«Рандом ошибок не прощает»", font_body, fill="#AAAAAA")

    out_name = f"meme_{int(time.time())}_{random.randint(100, 999)}.png"
    out_path = os.path.join(MEDIA_DIR, out_name)
    img.save(out_path, "PNG")
    return out_path
