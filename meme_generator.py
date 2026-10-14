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
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 20, 28))
    draw = ImageDraw.Draw(img)
    font_title = get_font(38)
    font_body = get_font(28)
    font_sub = get_font(24)

    gasgen_path = os.path.join(MEDIA_DIR, "gasgen.png")
    ptur_path = os.path.join(MEDIA_DIR, "ptur.png")
    kapkan_path = os.path.join(MEDIA_DIR, "kapkan.png")
    heather_path = os.path.join(MEDIA_DIR, "heather.png")
    mammoth_path = os.path.join(MEDIA_DIR, "mammoth.png")
    doge_path = os.path.join(MEDIA_DIR, "tpl_doge.png")
    clown_path = os.path.join(MEDIA_DIR, "tpl_clown.png")
    scorp_path = os.path.join(MEDIA_DIR, "scorpion.png")
    harv_path = os.path.join(MEDIA_DIR, "harvester.png")
    artificer_path = os.path.join(MEDIA_DIR, "artificer.png")
    scav_path = os.path.join(MEDIA_DIR, "scav_large.png")
    spear_path = os.path.join(MEDIA_DIR, "spear.png")

    # 1. Rain World × Crossout Crossover
    if any(w in theme_lower for w in ["рэин", "рейн", "rain", "слизн", "скэв", "scav", "искусник", "копье", "ворлд"]):
        draw_text_with_outline(draw, (50, 35), "RAIN WORLD  ×  CROSSOUT", font_title, fill="#00FFCC")
        draw.line([(40, 85), (860, 85)], fill="#555555", width=3)
        draw_text_with_outline(draw, (50, 105), "Когда Слизнекот и Скэвы случайно заехали в Пустоши...", font_sub, fill="#E2E8F0")

        if os.path.exists(scav_path):
            scav = Image.open(scav_path).convert("RGBA").resize((280, 280))
            img.paste(scav, (60, 160), scav)
        draw_text_with_outline(draw, (60, 460), "1. Скэв кинул взрывное копье", font_body, fill="#FFCC00")

        draw_text_with_outline(draw, (410, 270), "⚡ VS ⚡", font_title, fill="#FF3333")

        if os.path.exists(gasgen_path):
            gas = Image.open(gasgen_path).convert("RGBA").resize((260, 260))
            img.paste(gas, (540, 170), gas)
        draw_text_with_outline(draw, (500, 460), "2. Попал в незащищенный Газген", font_body, fill="#FF4444")

        draw.rectangle([(40, 520), (860, 780)], fill=(28, 32, 46), outline="#FF3333", width=2)
        draw_text_with_outline(draw, (65, 545), "💥 ДЕТОНАЦИЯ СИЛОЙ В 100 МЕГАТОНН 💥", font_title, fill="#FF2222")
        draw_text_with_outline(draw, (70, 610), "• Цикл в Rain World мгновенно завершен", font_body, fill="#FFFFFF")
        draw_text_with_outline(draw, (70, 660), "• В Crossout: крафт улетел в ангар до конца боя", font_body, fill="#FFCC00")
        draw_text_with_outline(draw, (70, 715), "• Дождь испарился вместе с локацией 💀", font_body, fill="#AAAAAA")

        draw_text_with_outline(draw, (120, 820), "«Ярик, оцени этот кроссовер от 1 до 10!»", font_title, fill="#38BDF8")

    # 2. Автосборка
    elif "автосборк" in theme_lower:
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

    # 3. Газген / Взрыв
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

    # 4. Скорпион / Реликты
    elif any(w in theme_lower for w in ["скорп", "реликт", "донат"]):
        draw_text_with_outline(draw, (80, 40), "РЕЛИКТОВЫЙ НАГИБ: СКОРПИОН", font_title, fill="#38BDF8")
        draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
        draw_text_with_outline(draw, (60, 140), "Продал почку, почку друга и гараж ради двух Скорпов...", font_sub)

        if os.path.exists(scorp_path):
            s = Image.open(scorp_path).convert("RGBA").resize((380, 280))
            img.paste(s, (260, 220), s)

        draw_text_with_outline(draw, (60, 580), "Первый выстрел в бою:", font_body, fill="#FFCC00")
        draw_text_with_outline(draw, (60, 640), "Снаряд пробил 15 деталей и выбил фару дрону 😂", font_title, fill="#FF4444")
        draw_text_with_outline(draw, (160, 740), "«Зато статус в Пустошах легендарный»", font_body, fill="#AAAAAA")

    # 5. Мамонт / Тяжелые пушки
    elif any(w in theme_lower for w in ["мамонт", "пушк", "утюг"]):
        draw_text_with_outline(draw, (80, 40), "МАМОНТОВЫЙ ТЯЖ В РАНДОМЕ", font_title, fill="#FF9900")
        draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
        draw_text_with_outline(draw, (60, 140), "Собрал крафт на 25 тонн чистого чугуна...", font_body)

        if os.path.exists(mammoth_path):
            m = Image.open(mammoth_path).convert("RGBA").resize((380, 280))
            img.paste(m, (260, 220), m)

        draw_text_with_outline(draw, (60, 580), "Пока доехал до центра карты:", font_body, fill="#FFCC00")
        draw_text_with_outline(draw, (80, 660), "Вся союзная команда уже в ангаре 💀", font_title, fill="#FF3333")
        draw_text_with_outline(draw, (140, 750), "«Один против шести ховеров. F»", font_body, fill="#888888")

    # 6. Случайный мем из пула (чтобы не повторялся)
    else:
        variant = random.choice([1, 2, 3])
        if variant == 1:
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
        elif variant == 2:
            draw_text_with_outline(draw, (120, 50), "ПТУРОВОД ЗА ХОЛМОМ", font_title, fill="#00CCFF")
            draw.line([(50, 110), (850, 110)], fill="#555555", width=3)
            draw_text_with_outline(draw, (60, 150), "Стоит в инвизе 3 минуты и целится...", font_body, fill="#FFFFFF")
            if os.path.exists(ptur_path):
                p = Image.open(ptur_path).convert("RGBA").resize((380, 300))
                img.paste(p, (260, 230), p)
            draw_text_with_outline(draw, (60, 600), "Запускает ракету через всю карту 🚀", font_body, fill="#FFFF44")
            draw_text_with_outline(draw, (80, 700), "Итог: ракета врезалась в свой же дрон 😂", font_title, fill="#FF4444")
            draw_text_with_outline(draw, (250, 780), "«Снайпер от Бога»", font_body, fill="#888888")
        else:
            draw_text_with_outline(draw, (100, 50), "КАК СОБИРАЕТСЯ КРАФТ В 3 ЧАСА НОЧИ", font_title, fill="#FF4444")
            draw.line([(50, 110), (850, 110)], fill="#555555", width=3)
            draw_text_with_outline(draw, (60, 150), "«Сейчас по-быстрому сбалансирую броню...»", font_body, fill="#FFFFFF")
            if os.path.exists(gasgen_path):
                g = Image.open(gasgen_path).convert("RGBA").resize((280, 280))
                img.paste(g, (120, 260), g)
            if os.path.exists(harv_path):
                h = Image.open(harv_path).convert("RGBA").resize((280, 280))
                img.paste(h, (500, 260), h)
            draw_text_with_outline(draw, (70, 620), "Итог: Жнец торчит из кабины, Газген на крыше", font_body, fill="#FFCC00")
            draw_text_with_outline(draw, (110, 710), "Зато в бой едет с душой! 🚜💀", font_title, fill="#00FFCC")

    out_name = f"meme_{int(time.time())}_{random.randint(100, 999)}.png"
    out_path = os.path.join(MEDIA_DIR, out_name)
    img.save(out_path, "PNG")
    return out_path
