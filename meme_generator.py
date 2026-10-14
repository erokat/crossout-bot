import os
import random
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")

def get_font(size):
    font_paths = [
        os.path.join(MEDIA_DIR, "Comfortaa.ttf"),
        os.path.join(MEDIA_DIR, "RobotoCondensed-Bold.ttf"),
        os.path.join(MEDIA_DIR, "Anton.ttf"),
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
    font_title = get_font(42)
    font_body = get_font(32)

    # Check available assets
    gasgen_path = os.path.join(MEDIA_DIR, "gasgen.png")
    ptur_path = os.path.join(MEDIA_DIR, "ptur.png")
    kapkan_path = os.path.join(MEDIA_DIR, "kapkan.png")
    heather_path = os.path.join(MEDIA_DIR, "heather.png")
    doge_path = os.path.join(MEDIA_DIR, "tpl_doge.png")

    if "автосборк" in theme_lower:
        # Автосборка мем
        draw_text_with_outline(draw, (50, 40), "АВТОСБОРКА В CROSSOUT:", font_title, fill="#FFCC00")
        draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
        draw_text_with_outline(draw, (50, 130), "Ожидание: идеальный сбалансированный крафт", font_body, fill="#00FFCC")
        draw_text_with_outline(draw, (50, 180), "Реальность:", font_body, fill="#FF4444")
        
        # Paste assets
        if os.path.exists(gasgen_path):
            g = Image.open(gasgen_path).convert("RGBA").resize((280, 280))
            img.paste(g, (100, 300), g)
            draw_text_with_outline(draw, (80, 590), "Газген на бампере", font_body)
        if os.path.exists(ptur_path):
            p = Image.open(ptur_path).convert("RGBA").resize((320, 260))
            img.paste(p, (480, 310), p)
            draw_text_with_outline(draw, (490, 590), "ПТУР в лоб кабине", font_body)
            
        draw_text_with_outline(draw, (80, 720), "⚠️ ПЕРЕГРУЗ: +6500 КГ | СКОРОСТЬ: 3 КМ/Ч", font_title, fill="#FF2222")
        draw_text_with_outline(draw, (180, 800), "«Шедевр инженерной мысли»", font_body, fill="#CCCCCC")
    else:
        # Рандом / ПТУР / Мета
        draw_text_with_outline(draw, (80, 50), "ТИПИЧНЫЙ БОЙ В CROSSOUT", font_title, fill="#FFCC00")
        draw.line([(50, 110), (850, 110)], fill="#555555", width=3)
        
        draw_text_with_outline(draw, (60, 150), "Когда накопил 40к монет на топ-крафт...", font_body, fill="#FFFFFF")
        
        if os.path.exists(kapkan_path):
            k = Image.open(kapkan_path).convert("RGBA").resize((260, 260))
            img.paste(k, (100, 280), k)
            draw_text_with_outline(draw, (70, 550), "1. Поймал Капкан", font_body, fill="#FF6666")
        if os.path.exists(heather_path):
            h = Image.open(heather_path).convert("RGBA").resize((300, 260))
            img.paste(h, (500, 280), h)
            draw_text_with_outline(draw, (480, 550), "2. Прилетел Вереск", font_body, fill="#FF6666")
            
        draw_text_with_outline(draw, (120, 680), "Итог: Гараж через 15 секунд боя 💀", font_title, fill="#FF3333")
        draw_text_with_outline(draw, (220, 780), "«Рандом ошибок не прощает»", font_body, fill="#AAAAAA")

    output_path = os.path.join(MEDIA_DIR, "generated_meme.png")
    img.save(output_path, "PNG")
    return output_path
