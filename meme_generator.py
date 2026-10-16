import os
import sys
import random
import time
import hashlib
import shutil
import json
import re
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

from config import MEDIA_DIR, SAVED_MEMES_DIR
from db import is_meme_already_sent, record_sent_meme, get_last_sent_meme

ANDROID_PHOTOS_DIR = "/storage/emulated/0/Pictures/PhotosEditor"

def get_font(size):
    font_paths = [
        os.path.join(MEDIA_DIR, "RussoOne-Regular.ttf"),
        os.path.join(MEDIA_DIR, "Montserrat.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, size)
                bb_cyr = font.getbbox("А")
                bb_tofu = font.getbbox("\ufffe")
                if bb_cyr != bb_tofu:
                    return font
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

def get_asset(name):
    p = os.path.join(MEDIA_DIR, name)
    return p if os.path.exists(p) else None

# --- GENERATOR FUNCTIONS (each returns img, template_name, headline) ---

def gen_rw_crossover_1():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 20, 28))
    draw = ImageDraw.Draw(img)
    headline = "RAIN WORLD × CROSSOUT: ВЗРЫВНОЕ КОПЬЕ VS ГАЗГЕН"
    
    draw_text_with_outline(draw, (45, 35), "RAIN WORLD  ×  CROSSOUT", get_font(38), fill="#00FFCC")
    draw.line([(40, 85), (860, 85)], fill="#555555", width=3)
    draw_text_with_outline(draw, (50, 105), "Когда Слизнекот и Скэвы случайно заехали в Пустоши...", get_font(24), fill="#E2E8F0")

    scav = get_asset("scav_large.png")
    if scav:
        im = Image.open(scav).convert("RGBA").resize((280, 280))
        img.paste(im, (60, 160), im)
    draw_text_with_outline(draw, (60, 460), "1. Скэв кинул взрывное копье", get_font(28), fill="#FFCC00")

    draw_text_with_outline(draw, (410, 270), "⚡ VS ⚡", get_font(36), fill="#FF3333")

    gas = get_asset("gasgen.png")
    if gas:
        im = Image.open(gas).convert("RGBA").resize((260, 260))
        img.paste(im, (540, 170), im)
    draw_text_with_outline(draw, (500, 460), "2. Попал в открытый Газген", get_font(28), fill="#FF4444")

    draw.rectangle([(40, 520), (860, 780)], fill=(28, 32, 46), outline="#FF3333", width=2)
    draw_text_with_outline(draw, (65, 545), "💥 ДЕТОНАЦИЯ СИЛОЙ В 100 МЕГАТОНН 💥", get_font(36), fill="#FF2222")
    draw_text_with_outline(draw, (70, 610), "• Цикл в Rain World мгновенно завершен", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (70, 660), "• В Crossout: крафт улетел в ангар до конца боя", get_font(26), fill="#FFCC00")
    draw_text_with_outline(draw, (70, 715), "• Дождь испарился вместе с локацией 💀", get_font(26), fill="#AAAAAA")

    draw_text_with_outline(draw, (120, 820), "«Ярик, оцени этот кроссовер от 1 до 10!»", get_font(34), fill="#38BDF8")
    return img, "rw_crossover_1", headline

def gen_rw_crossover_2():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(14, 18, 30))
    draw = ImageDraw.Draw(img)
    headline = "СЛИЗНЕКОТ ЗА РУЛЕМ ХОВЕРА В ПУСТОШАХ"

    draw_text_with_outline(draw, (60, 40), "СЛИЗНЕКОТ В ПУСТОШАХ CROSSOUT", get_font(36), fill="#38BDF8")
    draw.line([(40, 90), (860, 90)], fill="#444444", width=3)
    draw_text_with_outline(draw, (50, 110), "«Думал, что ящеры и дождь опасны...»", get_font(24), fill="#94A3B8")

    art = get_asset("artificer.png") or get_asset("scav_large.png")
    if art:
        im = Image.open(art).convert("RGBA").resize((260, 260))
        img.paste(im, (80, 170), im)

    hov = get_asset("hover.png") or get_asset("kapkan.png")
    if hov:
        im = Image.open(hov).convert("RGBA").resize((280, 240))
        img.paste(im, (520, 180), im)

    draw_text_with_outline(draw, (60, 450), "Собрал крафт на 4 ховерах", get_font(28), fill="#4ADE80")
    draw_text_with_outline(draw, (500, 450), "Поставил Капкан и ПТУР", get_font(28), fill="#F87171")

    draw.rectangle([(40, 520), (860, 770)], fill=(24, 28, 44), outline="#38BDF8", width=2)
    draw_text_with_outline(draw, (70, 550), "РЕАЛЬНОСТЬ ПЕРВОГО БОЯ:", get_font(32), fill="#FBBF24")
    draw_text_with_outline(draw, (70, 610), "1. Зацепился ховером за мусорный бак", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (70, 660), "2. Сзади на полной скорости въехал дробовод", get_font(26), fill="#FF6B6B")
    draw_text_with_outline(draw, (70, 715), "3. Вернулся в убежище Rain World быстрее дождя", get_font(26), fill="#93C5FD")

    draw_text_with_outline(draw, (140, 810), "«Пустоши похуже любого Затененного Цитаделя»", get_font(28), fill="#E2E8F0")
    return img, "rw_crossover_2", headline

# --- PURE RAIN WORLD GENERATORS ---

def gen_rw_scav_toll():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(14, 16, 22))
    draw = ImageDraw.Draw(img)
    headline = "ТАМОЖНЯ МУСОРЩИКОВ В RAIN WORLD: ОЖИДАНИЕ VS РЕАЛЬНОСТЬ"

    draw_text_with_outline(draw, (50, 40), "ТАМОЖНЯ МУСОРЩИКОВ (SCAV TOLL)", get_font(36), fill="#FBBF24")
    draw.line([(40, 90), (860, 90)], fill="#444444", width=3)
    draw_text_with_outline(draw, (50, 110), "«Я просто хотел мирно пройти в следующую зону...»", get_font(24), fill="#94A3B8")

    scav = get_asset("scav_large.png") or get_asset("scavenger.png")
    if scav:
        im = Image.open(scav).convert("RGBA").resize((270, 270))
        img.paste(im, (60, 160), im)

    sp = get_asset("spear.png") or get_asset("spear_clean.png")
    if sp:
        im_sp = Image.open(sp).convert("RGBA").resize((220, 220))
        img.paste(im_sp, (580, 180), im_sp)

    draw.rectangle([(40, 480), (860, 770)], fill=(22, 26, 38), outline="#FBBF24", width=2)
    draw_text_with_outline(draw, (60, 505), "1. Аккуратно положил редкую жемчужину на землю", get_font(26), fill="#4ADE80")
    draw_text_with_outline(draw, (60, 560), "2. Случайно подпрыгнул / моргнул / посмотрел не так", get_font(26), fill="#F87171")
    draw_text_with_outline(draw, (60, 620), "3. ВСЯ ЗАСТАВА ОДНОВРЕМЕННО КИНУЛА 8 ВЗРЫВНЫХ КОПИЙ 💥", get_font(26), fill="#EF4444")
    draw_text_with_outline(draw, (60, 685), "• Репутация у мусорщиков: -100 (Враг народа)", get_font(24), fill="#FFAA00")
    draw_text_with_outline(draw, (60, 725), "• Слизнекот: распылен на атомы до конца цикла", get_font(24), fill="#AAAAAA")

    draw_text_with_outline(draw, (110, 820), "«Самое вежливое общение в Rain World»", get_font(30), fill="#38BDF8")
    return img, "rw_scav_toll", headline

def gen_rw_rain_cycle():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(12, 14, 26))
    draw = ImageDraw.Draw(img)
    headline = "СУРОВАЯ ЖИЗНЬ В RAIN WORLD: 10 МЕТРОВ ДО УБЕЖИЩА"

    draw_text_with_outline(draw, (70, 40), "КОНЕЦ ЦИКЛА В RAIN WORLD", get_font(38), fill="#38BDF8")
    draw.line([(40, 90), (860, 90)], fill="#3B82F6", width=3)
    draw_text_with_outline(draw, (50, 110), "Таймер цикла подошел к концу. Начинается потоп.", get_font(24), fill="#94A3B8")

    draw.rectangle([(50, 160), (850, 420)], fill=(20, 24, 40), outline="#60A5FA", width=2)
    draw_text_with_outline(draw, (70, 185), "ТВОИ ДОСТИЖЕНИЯ ЗА ЦИКЛ:", get_font(28), fill="#FBBF24")
    draw_text_with_outline(draw, (70, 235), "✓ Накормил Слизнекота 4 ягодами", get_font(24), fill="#FFFFFF")
    draw_text_with_outline(draw, (70, 280), "✓ Увернулся от двух стервятников на открытом мосту", get_font(24), fill="#FFFFFF")
    draw_text_with_outline(draw, (70, 325), "✓ Завалил зеленого ящера с одного копья", get_font(24), fill="#4ADE80")
    draw_text_with_outline(draw, (70, 370), "✓ До заветного люка убежища осталось ровно 3 метра", get_font(24), fill="#38BDF8")

    draw.rectangle([(50, 460), (850, 740)], fill=(34, 18, 24), outline="#EF4444", width=2)
    draw_text_with_outline(draw, (70, 485), "РЕАЛЬНОСТЬ У САМОГО ВХОДА:", get_font(28), fill="#F87171")
    draw_text_with_outline(draw, (70, 540), "• В трубе застряла летучая мышь и жирная пиявка 💀", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (70, 595), "• Экран темнеет, вода поднимается на 2 метра в секунду", get_font(26), fill="#FCA5A5")
    draw_text_with_outline(draw, (70, 650), "• Люк закрывается перед твоим носом", get_font(26), fill="#EF4444")
    draw_text_with_outline(draw, (70, 695), "💥 КАРМА ПАДАЕТ НА ДНО. УДАЧИ В СЛЕДУЮЩЕМ ЦИКЛЕ 💥", get_font(24), fill="#F87171")

    draw_text_with_outline(draw, (180, 810), "«Дождь Пустошей никого не щадит»", get_font(30), fill="#93C5FD")
    return img, "rw_rain_cycle", headline

def gen_rw_artificer_chaos():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(26, 14, 14))
    draw = ImageDraw.Draw(img)
    headline = "КАМПАНИЯ АРТИФИСЕРА: 50% СКИЛЛ, 50% САМОПОДРЫВ"

    draw_text_with_outline(draw, (50, 40), "БУДНИ АРТИФИСЕРА (ВЗРЫВОТЕХНИКА)", get_font(34), fill="#EF4444")
    draw.line([(40, 90), (860, 90)], fill="#B91C1C", width=3)
    draw_text_with_outline(draw, (50, 110), "Геймплей за красного слизнекота в одном кадре:", get_font(24), fill="#FCA5A5")

    art = get_asset("artificer.png")
    if art:
        im = Image.open(art).convert("RGBA").resize((280, 280))
        img.paste(im, (80, 160), im)

    sp = get_asset("spear.png")
    if sp:
        im_sp = Image.open(sp).convert("RGBA").resize((220, 220))
        img.paste(im_sp, (560, 180), im_sp)

    draw.rectangle([(40, 470), (860, 760)], fill=(34, 18, 20), outline="#EF4444", width=2)
    draw_text_with_outline(draw, (60, 495), "План на раунд:", get_font(28), fill="#FBBF24")
    draw_text_with_outline(draw, (60, 545), "1. Скрафтил взрывное копье из слюны и камня", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (60, 595), "2. Сделал двойной взрывной прыжок через пропасть", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (60, 645), "3. Бросил копье в элитного скэва в упор...", get_font(26), fill="#F87171")
    draw_text_with_outline(draw, (60, 700), "💥 ВЗРЫВНАЯ ВОЛНА ОТБРОСИЛА В ПАСТЬ КРАСНОМУ ЯЩЕРУ 💀", get_font(24), fill="#EF4444")

    draw_text_with_outline(draw, (120, 810), "«Насилие — это не ответ, это единственный выход»", get_font(28), fill="#FCA5A5")
    return img, "rw_artificer_chaos", headline

def gen_rw_vulture_mask():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 18, 26))
    draw = ImageDraw.Draw(img)
    headline = "МАСКА СТЕРВЯТНИКА В RAIN WORLD: ОЖИДАНИЕ VS РЕАЛЬНОСТЬ"

    draw_text_with_outline(draw, (60, 40), "МАСКА СТЕРВЯТНИКА (VULTURE MASK)", get_font(34), fill="#A78BFA")
    draw.line([(40, 90), (860, 90)], fill="#6D28D9", width=3)

    vult = get_asset("King_Vulture_Mask_icon.png") or get_asset("Vulture_Mask_icon.png")
    if vult:
        im = Image.open(vult).convert("RGBA").resize((240, 240))
        img.paste(im, (330, 130), im)

    draw.rectangle([(40, 400), (860, 570)], fill=(22, 28, 42), outline="#38BDF8", width=2)
    draw_text_with_outline(draw, (60, 420), "ОЖИДАНИЕ:", get_font(28), fill="#38BDF8")
    draw_text_with_outline(draw, (60, 470), "• Ты опаснейший альфа-хищник Дренажной Системы", get_font(24), fill="#FFFFFF")
    draw_text_with_outline(draw, (60, 515), "• Все ящеры в ужасе вжимаются в стены и бегут", get_font(24), fill="#4ADE80")

    draw.rectangle([(40, 600), (860, 770)], fill=(36, 20, 24), outline="#EF4444", width=2)
    draw_text_with_outline(draw, (60, 620), "РЕАЛЬНОСТЬ:", get_font(28), fill="#EF4444")
    draw_text_with_outline(draw, (60, 670), "• Красный ящер не умеет читать и откусил пол-лица", get_font(24), fill="#FFFFFF")
    draw_text_with_outline(draw, (60, 715), "• Обезличенный стервятник летит за тобой через 3 региона 💀", get_font(24), fill="#F87171")

    draw_text_with_outline(draw, (140, 820), "«Стиль 10 из 10, выживаемость — отрицательная»", get_font(28), fill="#DDD6FE")
    return img, "rw_vulture_mask", headline

def gen_rw_five_pebbles():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(16, 20, 32))
    draw = ImageDraw.Draw(img)
    headline = "ВИЗИТ К ПЯТИ ГАЛЬКАМ (FIVE PEBBLES) В RAIN WORLD"

    draw_text_with_outline(draw, (80, 40), "АУДИЕНЦИЯ У ПЯТИ ГАЛЕК (5P)", get_font(36), fill="#38BDF8")
    draw.line([(40, 90), (860, 90)], fill="#0284C7", width=3)
    draw_text_with_outline(draw, (50, 110), "Преодолел Гниль, невесомость и 40 смертей, чтобы дойти...", get_font(24), fill="#94A3B8")

    draw.rectangle([(40, 160), (860, 450)], fill=(20, 26, 44), outline="#38BDF8", width=2)
    draw_text_with_outline(draw, (60, 185), "ТЫ: маленькое невинное существо, принесшее жемчужину", get_font(26), fill="#FBBF24")
    draw_text_with_outline(draw, (60, 240), "Итератор Пять Галек через 3 секунды:", get_font(26), fill="#FFFFFF")
    draw_text_with_outline(draw, (60, 295), "«ТЫ ПОЧЕМУ ВСЁ ЕЩЁ В МОЕЙ КАМЕРЕ, МОКРЫЙ КРЫСЕНЫШ?!»", get_font(26), fill="#EF4444")
    draw_text_with_outline(draw, (60, 355), "Врубает гравитационный удар силой 500G и вышвыривает в трубу 💥", get_font(24), fill="#60A5FA")

    draw.rectangle([(40, 490), (860, 750)], fill=(28, 20, 36), outline="#A855F7", width=2)
    draw_text_with_outline(draw, (60, 515), "ИТОГ ПЕРЕГОВОРОВ ВЫСШИХ СУЩЕСТВ:", get_font(28), fill="#C084FC")
    draw_text_with_outline(draw, (60, 570), "• Получил знак Созидания (Mark of Communication)", get_font(24), fill="#FFFFFF")
    draw_text_with_outline(draw, (60, 620), "• Получил сотрясение мозга 4-й степени", get_font(24), fill="#F87171")
    draw_text_with_outline(draw, (60, 675), "• Смотрящая на Луну вздыхает где-то на другом конце карты", get_font(24), fill="#94A3B8")

    draw_text_with_outline(draw, (150, 810), "«Священный путь вознесения полон боли»", get_font(30), fill="#E0E7FF")
    return img, "rw_five_pebbles", headline

# --- DYNAMIC THEME GENERATOR ---

def gen_dynamic_meme(theme=""):
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 20, 28))
    draw = ImageDraw.Draw(img)

    clean_theme = (theme or "Мем").strip()
    clean_theme = re.sub(r"(?:сделай|склепай|запили|отправь|скинь|мем|мэм|по|про)\s*", "", clean_theme, flags=re.I).strip() or clean_theme
    headline = f"МЕМ: {clean_theme.upper()[:40]}"

    prompt_meme = (
        f"Придумай очень смешной, жизненный, угарный геймерский/интернет мем по теме: «{clean_theme}».\n"
        "Ответь строго в формате JSON со следующими ключами:\n"
        "{\n"
        '  "title": "КОРОТКИЙ ЗАГОЛОВОК КАПСОМ",\n'
        '  "subtitle": "Подзаголовок или контекст ситуации (1 строка)",\n'
        '  "section1_title": "ОЖИДАНИЕ:",\n'
        '  "section1_items": ["пункт 1", "пункт 2"],\n'
        '  "section2_title": "РЕАЛЬНОСТЬ:",\n'
        '  "section2_items": ["пункт 1 с юмором/фейлом", "пункт 2 с эмодзи"],\n'
        '  "footer": "Финальная смешная цитата в кавычках"\n'
        "}\n"
        "Выдай ТОЛЬКО чистый JSON без markdown блоков ```json."
    )
    res_ai = None
    try:
        from keep_alive import run_antigravity_cli
        res_ai = run_antigravity_cli(prompt_meme)
    except Exception:
        pass

    meme_data = None
    if res_ai:
        try:
            m_json = re.search(r"\{.*\}", res_ai, re.DOTALL)
            if m_json:
                meme_data = json.loads(m_json.group(0))
        except Exception:
            pass

    if not meme_data:
        meme_data = {
            "title": f"МЕМ: {clean_theme.upper()[:30]}",
            "subtitle": "Когда решил проверить это на личном опыте...",
            "section1_title": "ОЖИДАНИЕ:",
            "section1_items": ["Идеальный скилл и лёгкая победа", "Всё под полным контролем"],
            "section2_title": "РЕАЛЬНОСТЬ:",
            "section2_items": ["Всё пошло наперекосяк на 1-й секунде 💀", "Полнейший хаос, поражение и уход на спавн"],
            "footer": "«Классика жанра, которой нет объяснения»"
        }

    # Draw meme canvas
    draw_text_with_outline(draw, (50, 40), meme_data.get("title", "МЕМ")[:35], get_font(34), fill="#38BDF8")
    draw.line([(40, 90), (860, 90)], fill="#3B82F6", width=3)
    draw_text_with_outline(draw, (50, 110), meme_data.get("subtitle", "")[:60], get_font(24), fill="#94A3B8")

    # Section 1
    draw.rectangle([(40, 170), (860, 440)], fill=(22, 28, 42), outline="#38BDF8", width=2)
    draw_text_with_outline(draw, (60, 195), meme_data.get("section1_title", "ОЖИДАНИЕ:"), get_font(28), fill="#4ADE80")
    y_sec1 = 250
    for itm in meme_data.get("section1_items", []):
        draw_text_with_outline(draw, (70, y_sec1), f"• {itm}"[:55], get_font(25), fill="#FFFFFF")
        y_sec1 += 55

    # Section 2
    draw.rectangle([(40, 480), (860, 750)], fill=(36, 20, 26), outline="#EF4444", width=2)
    draw_text_with_outline(draw, (60, 505), meme_data.get("section2_title", "РЕАЛЬНОСТЬ:"), get_font(28), fill="#F87171")
    y_sec2 = 560
    for itm in meme_data.get("section2_items", []):
        draw_text_with_outline(draw, (70, y_sec2), f"• {itm}"[:55], get_font(25), fill="#FFFFFF")
        y_sec2 += 55

    # Footer
    footer = meme_data.get("footer", "")
    if footer:
        draw_text_with_outline(draw, (80, 810), footer[:60], get_font(28), fill="#FBBF24")

    headline = f"МЕМ: {meme_data.get('title', clean_theme)}"
    return img, "dynamic_theme", headline

def gen_autobuild():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(20, 22, 28))
    draw = ImageDraw.Draw(img)
    headline = "АВТОСБОРКА В CROSSOUT: ШЕДЕВР ИНЖЕНЕРИИ"

    draw_text_with_outline(draw, (50, 40), "АВТОСБОРКА В CROSSOUT:", get_font(38), fill="#FFCC00")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (50, 130), "Ожидание: идеальный сбалансированный крафт", get_font(28), fill="#00FFCC")
    draw_text_with_outline(draw, (50, 180), "Реальность:", get_font(28), fill="#FF4444")

    gas = get_asset("gasgen.png")
    if gas:
        g = Image.open(gas).convert("RGBA").resize((280, 280))
        img.paste(g, (100, 250), g)
        draw_text_with_outline(draw, (80, 550), "Газген на бампере", get_font(26))

    pt = get_asset("ptur.png")
    if pt:
        p = Image.open(pt).convert("RGBA").resize((320, 260))
        img.paste(p, (480, 260), p)
        draw_text_with_outline(draw, (490, 550), "ПТУР в лоб кабине", get_font(26))

    draw_text_with_outline(draw, (60, 680), "⚠️ ПЕРЕГРУЗ: +6500 КГ | СКОРОСТЬ: 3 КМ/Ч", get_font(34), fill="#FF2222")
    draw_text_with_outline(draw, (180, 760), "«Шедевр инженерной мысли»", get_font(28), fill="#CCCCCC")
    return img, "autobuild", headline

def gen_gasgen_blast():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(28, 18, 18))
    draw = ImageDraw.Draw(img)
    headline = "ПОСТАВИЛ ГАЗГЕН В ПУСТОШАХ НА ПЕРВОЙ СЕКУНДЕ"

    draw_text_with_outline(draw, (80, 40), "ПОСТАВИЛ ГАЗГЕН В ПУСТОШАХ", get_font(38), fill="#FF3333")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "1. Заспавнился в бою с хорошим настроением", get_font(28))

    gas = get_asset("gasgen.png")
    if gas:
        g = Image.open(gas).convert("RGBA").resize((320, 320))
        img.paste(g, (290, 220), g)

    draw_text_with_outline(draw, (60, 580), "2. Шальная пуля коснулась заднего брызговика", get_font(28), fill="#FFCC00")
    draw_text_with_outline(draw, (100, 670), "💥 ВЗРЫВ СИЛОЙ 10 МЕГАТОНН 💥", get_font(36), fill="#FF2222")
    draw_text_with_outline(draw, (210, 760), "«Ушел в ангар на 5-й секунде боя»", get_font(28), fill="#AAAAAA")
    return img, "gasgen_blast", headline

def gen_heather_vs_ptur():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 22, 30))
    draw = ImageDraw.Draw(img)
    headline = "СРАВНЕНИЕ ГЕЙМПЛЕЯ: ВЕРЕСК VS ПТУР В CROSSOUT"

    draw_text_with_outline(draw, (70, 35), "ГЕЙМПЛЕЙ: ВЕРЕСК VS ПТУР", get_font(36), fill="#38BDF8")
    draw.line([(40, 85), (860, 85)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 105), "Два пути дальней баллистики в Пустошах Crossout", get_font(24), fill="#E2E8F0")

    # Вереск слева
    draw.rectangle([(40, 150), (435, 780)], fill=(22, 28, 40), outline="#0ea5e9", width=2)
    draw_text_with_outline(draw, (60, 170), "МИНОМЕТ «ВЕРЕСК»", get_font(24), fill="#38bdf8")
    h_asset = get_asset("heather.png")
    if h_asset:
        im = Image.open(h_asset).convert("RGBA").resize((280, 220))
        img.paste(im, (90, 220), im)
    draw_text_with_outline(draw, (55, 470), "• Запустил залп навесом на удачу", get_font(20), fill="#ffffff")
    draw_text_with_outline(draw, (55, 520), "• Ушел пить чай на базу", get_font(20), fill="#4ade80")
    draw_text_with_outline(draw, (55, 570), "• 90% ракет упали в забор", get_font(20), fill="#fca5a5")
    draw_text_with_outline(draw, (55, 620), "• 10% ваншотнули вражеский утюг", get_font(20), fill="#fef08a")
    draw_text_with_outline(draw, (55, 700), "Статус: Бог баллистики 🎯", get_font(22), fill="#38bdf8")

    # ПТУР справа
    draw.rectangle([(465, 150), (860, 780)], fill=(36, 22, 26), outline="#ef4444", width=2)
    draw_text_with_outline(draw, (490, 170), "РАКЕТА «ПТУР КЛАРНЕТ»", get_font(24), fill="#f87171")
    p_asset = get_asset("ptur.png")
    if p_asset:
        im = Image.open(p_asset).convert("RGBA").resize((280, 220))
        img.paste(im, (520, 220), im)
    draw_text_with_outline(draw, (480, 470), "• 15 секунд летишь в ракете", get_font(20), fill="#ffffff")
    draw_text_with_outline(draw, (480, 520), "• Смотришь кино от первого лица", get_font(20), fill="#cbd5e1")
    draw_text_with_outline(draw, (480, 570), "• Врезался в дрон союзника 💀", get_font(20), fill="#ef4444")
    draw_text_with_outline(draw, (480, 620), "• Твой крафт уже доели ховеры", get_font(20), fill="#f87171")
    draw_text_with_outline(draw, (480, 700), "Статус: Кинооператор в гараже 🎥", get_font(22), fill="#f87171")

    draw_text_with_outline(draw, (90, 830), "«На Вереске решает рандом, на ПТУРе — терпение союзников»", get_font(22), fill="#cbd5e1")
    return img, "heather_vs_ptur", headline

def gen_enemy_ptur_vs_ally_ptur():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 22, 30))
    draw = ImageDraw.Draw(img)
    headline = "ВРАЖЕСКИЙ ПТУР VS СОЮЗНЫЙ ПТУР В CROSSOUT"

    draw_text_with_outline(draw, (70, 35), "ПТУР: ВРАЖЕСКИЙ VS СОЮЗНЫЙ", get_font(36), fill="#F87171")
    draw.line([(40, 85), (860, 85)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 105), "Суровая субординация управляемых ракет в Пустошах", get_font(24), fill="#E2E8F0")

    # Вражеский ПТУР слева
    draw.rectangle([(40, 150), (435, 780)], fill=(36, 20, 24), outline="#ef4444", width=2)
    draw_text_with_outline(draw, (60, 170), "ВРАЖЕСКИЙ ПТУР 🔴", get_font(24), fill="#f87171")
    p_asset = get_asset("ptur.png")
    if p_asset:
        im = Image.open(p_asset).convert("RGBA").resize((280, 220))
        img.paste(im, (90, 220), im)
    draw_text_with_outline(draw, (55, 470), "• Огибает 3 горы и 5 укрытий", get_font(20), fill="#ffffff")
    draw_text_with_outline(draw, (55, 520), "• Залетает в щель в 1 пиксель", get_font(20), fill="#fca5a5")
    draw_text_with_outline(draw, (55, 570), "• Ваншотает твой Газген и склад", get_font(20), fill="#f87171")
    draw_text_with_outline(draw, (55, 620), "• Управляется киберкотлетой", get_font(20), fill="#fef08a")
    draw_text_with_outline(draw, (55, 700), "Статус: Билет в ангар за 3 сек 💥", get_font(22), fill="#ef4444")

    # Союзный ПТУР справа
    draw.rectangle([(465, 150), (860, 780)], fill=(20, 28, 40), outline="#38bdf8", width=2)
    draw_text_with_outline(draw, (490, 170), "СОЮЗНЫЙ ПТУР 🔵", get_font(24), fill="#38bdf8")
    if p_asset:
        im_ally = Image.open(p_asset).convert("RGBA").resize((280, 220))
        im_ally = im_ally.transpose(Image.FLIP_LEFT_RIGHT)
        img.paste(im_ally, (520, 220), im_ally)
    draw_text_with_outline(draw, (480, 470), "• 15 сек летит строго в небо", get_font(20), fill="#ffffff")
    draw_text_with_outline(draw, (480, 520), "• Крутит сальто над базой", get_font(20), fill="#cbd5e1")
    draw_text_with_outline(draw, (480, 570), "• Врезается в спину союзнику 💀", get_font(20), fill="#fca5a5")
    draw_text_with_outline(draw, (480, 620), "• Тиммейт в войсе в шоке", get_font(20), fill="#38bdf8")
    draw_text_with_outline(draw, (480, 700), "Статус: Помог врагам победить 🤡", get_font(22), fill="#38bdf8")

    quotes = [
        "«Вражеский ПТУР целится в тебя, а союзный — в твою нервную систему»",
        "«Враг на ПТУРе выигрывает катку, союзник на ПТУРе ищет кнопку выстрела»",
        "«Вражеский ПТУР летит как хищник, союзный — как слепой голубь»",
        "«Закон Пустошей: союзная ракета всегда найдет твой собственный затылок»"
    ]
    chosen_quote = random.choice(quotes)
    draw_text_with_outline(draw, (60, 830), chosen_quote, get_font(21), fill="#cbd5e1")
    return img, "enemy_ptur_vs_ally_ptur", headline

def gen_ptur_sniper():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 24, 30))
    draw = ImageDraw.Draw(img)
    headline = "ТИПИЧНЫЙ ПТУРОВОД ЗА ХОЛМОМ В ИНВИЗЕ"

    draw_text_with_outline(draw, (120, 40), "ТИПИЧНЫЙ ПТУРОВОД В БОЮ", get_font(38), fill="#00CCFF")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Стоит за холмом в инвизе 3 минуты и выцеливает...", get_font(26))

    pt = get_asset("ptur.png")
    if pt:
        p = Image.open(pt).convert("RGBA").resize((380, 300))
        img.paste(p, (260, 220), p)

    draw_text_with_outline(draw, (60, 580), "Запускает управляемую ракету через всю карту 🚀", get_font(28), fill="#FFFF44")
    draw_text_with_outline(draw, (70, 670), "Итог: ракета врезалась в свой же дрон 😂", get_font(34), fill="#FF4444")
    draw_text_with_outline(draw, (260, 760), "«Снайпер года в Пустошах»", get_font(28), fill="#888888")
    return img, "ptur_sniper", headline

def gen_scorpion_relic():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(20, 24, 32))
    draw = ImageDraw.Draw(img)
    headline = "РЕЛИКТОВЫЙ НАГИБ: СКОРПИОН ЗА 80K МОНЕТ"

    draw_text_with_outline(draw, (80, 40), "РЕЛИКТОВЫЙ НАГИБ: СКОРПИОН", get_font(38), fill="#38BDF8")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Продал почку, почку друга и гараж ради двух Скорпов...", get_font(24))

    sc = get_asset("scorpion.png")
    if sc:
        s = Image.open(sc).convert("RGBA").resize((380, 280))
        img.paste(s, (260, 210), s)

    draw_text_with_outline(draw, (60, 560), "Первый залп в бою:", get_font(28), fill="#FFCC00")
    draw_text_with_outline(draw, (50, 630), "Снаряд пробил 15 деталей и выбил фару боту на 15 урона 😂", get_font(30), fill="#FF4444")
    draw_text_with_outline(draw, (160, 740), "«Зато статус в Пустошах легендарный»", get_font(28), fill="#AAAAAA")
    return img, "scorpion_relic", headline

def gen_mammoth_tank():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(26, 22, 18))
    draw = ImageDraw.Draw(img)
    headline = "МАМОНТОВЫЙ ТЯЖ НА 25 ТОНН В РАНДОМЕ"

    draw_text_with_outline(draw, (80, 40), "МАМОНТОВЫЙ ТЯЖ В РАНДОМЕ", get_font(38), fill="#FF9900")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Собрал крафт на 25 тонн чистого чугуна...", get_font(28))

    mam = get_asset("mammoth.png")
    if mam:
        m = Image.open(mam).convert("RGBA").resize((380, 280))
        img.paste(m, (260, 210), m)

    draw_text_with_outline(draw, (60, 560), "Пока доехал до центра карты со скоростью 30 км/ч:", get_font(26), fill="#FFCC00")
    draw_text_with_outline(draw, (70, 640), "Вся союзная команда уже дружно в ангаре 💀", get_font(34), fill="#FF3333")
    draw_text_with_outline(draw, (140, 740), "«Один против шести ховеров с деструкторами. F»", get_font(26), fill="#888888")
    return img, "mammoth_tank", headline

def gen_harvester_ambush():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(22, 18, 24))
    draw = ImageDraw.Draw(img)
    headline = "НЕВИДИМЫЙ УТЮГ СО ЖНЕЦОМ В КУСТАХ"

    draw_text_with_outline(draw, (80, 40), "ТИХАЯ ОХОТА В ПУСТОШАХ", get_font(38), fill="#EC4899")
    draw.line([(50, 100), (850, 100)], fill="#555555", width=3)
    draw_text_with_outline(draw, (60, 140), "Спокойно стоишь на холме и выцеливаешь противника...", get_font(26))

    hv = get_asset("harvester.png")
    if hv:
        h = Image.open(hv).convert("RGBA").resize((380, 280))
        img.paste(h, (260, 210), h)

    draw_text_with_outline(draw, (60, 560), "Звук из кустов за твоей спиной через 2 секунды:", get_font(26), fill="#FBBF24")
    draw_text_with_outline(draw, (80, 630), "«ВЖЖЖЖЖ-ХРУСЬ-ХРУСЬ» (Рама отвалилась) 💀", get_font(32), fill="#EF4444")
    draw_text_with_outline(draw, (180, 730), "«Доброго вечора, вы приняты в ангар»", get_font(28), fill="#94A3B8")
    return img, "harvester_ambush", headline

def gen_clown_progression():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(20, 20, 26))
    draw = ImageDraw.Draw(img)
    headline = "ЭВОЛЮЦИЯ ИГРОКА В CROSSOUT: 4 СТАДИИ КЛОУНАДЫ"

    draw_text_with_outline(draw, (70, 35), "СТАДИИ СБОРКИ КРАФТА В CROSSOUT", get_font(36), fill="#F59E0B")
    draw.line([(40, 85), (860, 85)], fill="#555555", width=3)

    steps = [
        ("1. «Сейчас соберу непобедимую имбу сам»", "#38BDF8"),
        ("2. «Ладно, поставлю Газген, энергии не хватает»", "#FBBF24"),
        ("3. «Перегруз +8000 кг? Колеса и так поедут»", "#FB7185"),
        ("4. «Сдетонировал на спавне, команда виновата»", "#EF4444")
    ]

    y = 130
    for text, color in steps:
        draw.rectangle([(50, y), (850, y + 100)], fill=(28, 30, 42), outline=color, width=2)
        draw_text_with_outline(draw, (80, y + 30), text, get_font(28), fill=color)
        y += 135

    draw_text_with_outline(draw, (160, 720), "«И так каждый божий день в рандоме»", get_font(30), fill="#94A3B8")
    return img, "clown_progression", headline

def gen_doge_comparison():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(18, 22, 28))
    draw = ImageDraw.Draw(img)
    headline = "КРАФТ В ТЕСТ-ДРАЙВЕ VS КРАФТ В РЕАЛЬНОМ БОЮ"

    draw_text_with_outline(draw, (60, 40), "КРАФТ В ГАРАЖЕ  VS  КРАФТ В БОЮ", get_font(36), fill="#FBBF24")
    draw.line([(40, 90), (860, 90)], fill="#555555", width=3)

    draw.rectangle([(40, 130), (430, 680)], fill=(24, 30, 40), outline="#38BDF8", width=2)
    draw_text_with_outline(draw, (60, 150), "В ТЕСТ-ДРАЙВЕ:", get_font(30), fill="#38BDF8")
    draw_text_with_outline(draw, (60, 220), "• Скорость 120 км/ч", get_font(24))
    draw_text_with_outline(draw, (60, 270), "• Дроны разваливают ботов", get_font(24))
    draw_text_with_outline(draw, (60, 320), "• Броня держит всё", get_font(24))
    draw_text_with_outline(draw, (60, 370), "• Чувствуешь себя богом", get_font(24), fill="#4ADE80")

    draw.rectangle([(470, 130), (860, 680)], fill=(32, 24, 28), outline="#EF4444", width=2)
    draw_text_with_outline(draw, (490, 150), "В ПЕРВОМ БОЮ:", get_font(30), fill="#EF4444")
    draw_text_with_outline(draw, (490, 220), "• Застрял в союзнике", get_font(24))
    draw_text_with_outline(draw, (490, 270), "• Вереск прилетел в крышу", get_font(24))
    draw_text_with_outline(draw, (490, 320), "• Оторвало оба колеса", get_font(24))
    draw_text_with_outline(draw, (490, 370), "• Ангар через 8 секунд", get_font(24), fill="#F87171")

    draw_text_with_outline(draw, (140, 740), "«Классика жанра, которой нет конца»", get_font(32), fill="#E2E8F0")
    return img, "doge_comparison", headline

def gen_hover_physics():
    width, height = 900, 950
    img = Image.new("RGB", (width, height), color=(16, 22, 30))
    draw = ImageDraw.Draw(img)
    headline = "ФИЗИКА ХОВЕРОВ В CROSSOUT: ПОЛЕТ В КОСМОС"

    draw_text_with_outline(draw, (90, 40), "ФИЗИКА ХОВЕРОВ В 2026 ГОДУ", get_font(38), fill="#00E5FF")
    draw.line([(50, 100), (850, 100)], fill="#444444", width=3)
    draw_text_with_outline(draw, (60, 140), "Паришь над землей, чувствуешь превосходство...", get_font(26))

    hov = get_asset("hover.png")
    if hov:
        h = Image.open(hov).convert("RGBA").resize((380, 280))
        img.paste(h, (260, 210), h)

    draw_text_with_outline(draw, (60, 560), "Наехал левым ховером на маленький камешек:", get_font(26), fill="#FFD600")
    draw_text_with_outline(draw, (80, 640), "Сальто назад 720° и приземление на Газген 💀", get_font(32), fill="#FF1744")
    draw_text_with_outline(draw, (180, 740), "«Гравитация Пустошей беспощадна»", get_font(28), fill="#80D8FF")
    return img, "hover_physics", headline

RW_GENERATORS = [
    ("rw_toll", gen_rw_scav_toll),
    ("rw_cycle", gen_rw_rain_cycle),
    ("rw_artificer", gen_rw_artificer_chaos),
    ("rw_vulture", gen_rw_vulture_mask),
    ("rw_pebbles", gen_rw_five_pebbles),
]

CROSSOVER_GENERATORS = [
    ("rw_1", gen_rw_crossover_1),
    ("rw_2", gen_rw_crossover_2),
]

CROSSOUT_GENERATORS = [
    ("enemy_ptur_vs_ally_ptur", gen_enemy_ptur_vs_ally_ptur),
    ("heather_ptur", gen_heather_vs_ptur),
    ("autobuild", gen_autobuild),
    ("gasgen", gen_gasgen_blast),
    ("ptur", gen_ptur_sniper),
    ("scorpion", gen_scorpion_relic),
    ("mammoth", gen_mammoth_tank),
    ("harvester", gen_harvester_ambush),
    ("clown", gen_clown_progression),
    ("doge", gen_doge_comparison),
    ("hover", gen_hover_physics),
]

ALL_GENERATORS = RW_GENERATORS + CROSSOVER_GENERATORS + CROSSOUT_GENERATORS

def wrap_text_lines(draw, text, font, max_width):
    words = text.split()
    lines = []
    curr = []
    for w in words:
        test_line = " ".join(curr + [w])
        bb = draw.textbbox((0, 0), test_line, font=font)
        if bb[2] - bb[0] <= max_width:
            curr.append(w)
        else:
            if curr:
                lines.append(" ".join(curr))
                curr = [w]
            else:
                lines.append(w)
                curr = []
    if curr:
        lines.append(" ".join(curr))
    return lines

def render_dynamic_pillow_meme(theme="", is_crossout=False, recipient="yarik"):
    width, height = 960, 960
    palettes = [
        {"bg": (18, 22, 34), "card1": (26, 32, 48), "card2": (38, 24, 30), "accent": "#38BDF8", "p1": "#4ADE80", "p2": "#F87171", "quote": "#FBBF24"},
        {"bg": (22, 18, 28), "card1": (32, 26, 42), "card2": (42, 26, 26), "accent": "#A78BFA", "p1": "#34D399", "p2": "#FB7185", "quote": "#FDE047"},
        {"bg": (16, 24, 24), "card1": (22, 36, 36), "card2": (36, 24, 28), "accent": "#2DD4BF", "p1": "#A3E635", "p2": "#F43F5E", "quote": "#FACC15"},
        {"bg": (20, 20, 24), "card1": (30, 32, 42), "card2": (40, 28, 30), "accent": "#60A5FA", "p1": "#6EE7B7", "p2": "#FDA4AF", "quote": "#FBBF24"},
    ]
    pal = random.choice(palettes)
    img = Image.new("RGB", (width, height), pal["bg"])
    draw = ImageDraw.Draw(img)

    clean_theme = re.sub(r"^(?:!|/)?(?:бот|ботяра|ботик|робот)[,\s]*", "", theme or "жизненный мем", flags=re.I).strip()
    clean_theme = re.sub(r"^(?:сгенерируй|создай|сделай|запили|склепай|выдай|скинь|нарисуй)\s+(?:мне\s+)?(?:кринжанутый\s+|смешной\s+|угарный\s+)?(?:мем|мемасик|мемчик|пикчу|картинку)?\s*", "", clean_theme, flags=re.I).strip()
    if not clean_theme:
        clean_theme = "жизненный мем"

    title_text = f"МЕМ: {clean_theme.upper()[:36]}"
    draw_text_with_outline(draw, (50, 40), title_text, get_font(34), fill=pal["accent"])
    draw.line([(40, 95), (width - 40, 95)], fill=pal["accent"], width=3)
    draw_text_with_outline(draw, (50, 115), "Когда решил проверить всё лично...", get_font(22), fill="#94A3B8")

    # Card 1: Expectation
    draw.rounded_rectangle([(40, 165), (width - 40, 440)], radius=12, fill=pal["card1"], outline=pal["accent"], width=2)
    draw_text_with_outline(draw, (65, 185), "ОЖИДАНИЕ:", get_font(28), fill=pal["p1"])
    if is_crossout:
        p1_lines = ["• Идеальный крафт с балансом массы и брони", "• Заезжаешь в PvP и разносишь всю команду врага"]
        gas = get_asset("gasgen.png") or get_asset("ptur.png")
        if gas:
            try:
                g_im = Image.open(gas).convert("RGBA").resize((160, 160))
                img.paste(g_im, (width - 220, 200), g_im)
            except Exception:
                pass
    else:
        p1_lines = [f"• Полный контроль ситуации по теме «{clean_theme[:30]}»", "• Всё идет строго по идеальному плану без сбоев"]

    y_pos = 240
    for l in p1_lines:
        wrapped = wrap_text_lines(draw, l, get_font(24), width - 300)
        for wl in wrapped:
            draw_text_with_outline(draw, (75, y_pos), wl, get_font(24), fill="#FFFFFF")
            y_pos += 35

    # Card 2: Reality
    draw.rounded_rectangle([(40, 470), (width - 40, 750)], radius=12, fill=pal["card2"], outline="#EF4444", width=2)
    draw_text_with_outline(draw, (65, 490), "РЕАЛЬНОСТЬ:", get_font(28), fill=pal["p2"])
    if is_crossout:
        p2_lines = ["• Союзник влетел в борт на первой секунде", "• Вражеский ПТУР находит открытый Газген через всю карту 💀"]
        kap = get_asset("kapkan.png") or get_asset("hover.png")
        if kap:
            try:
                k_im = Image.open(kap).convert("RGBA").resize((160, 160))
                img.paste(k_im, (width - 220, 510), k_im)
            except Exception:
                pass
    else:
        p2_lines = ["• Всё пошло наперекосяк на первой же секунде 💀", "• Стоишь в шоке и думаешь, где был просчет"]

    y_pos = 550
    for l in p2_lines:
        wrapped = wrap_text_lines(draw, l, get_font(24), width - 300)
        for wl in wrapped:
            draw_text_with_outline(draw, (75, y_pos), wl, get_font(24), fill="#FFFFFF")
            y_pos += 35

    # Footer quote
    quote_text = "«Классика жанра, которой невозможно противостоять»" if not is_crossout else "«Законы Пустошей беспощадны к смельчакам 🚜💀»"
    draw_text_with_outline(draw, (80, 810), quote_text, get_font(26), fill=pal["quote"])

    out_name = f"meme_{int(time.time())}_{random.randint(1000, 9999)}.png"
    out_path = os.path.join(MEDIA_DIR, out_name)
    img.save(out_path, "PNG")

    saved_copy = os.path.join(SAVED_MEMES_DIR, out_name)
    try:
        shutil.copy2(out_path, saved_copy)
    except Exception:
        pass

    if os.path.exists(ANDROID_PHOTOS_DIR):
        try:
            shutil.copy2(out_path, os.path.join(ANDROID_PHOTOS_DIR, out_name))
        except Exception:
            pass

    h = hashlib.sha256(clean_theme.encode("utf-8") + str(time.time()).encode()).hexdigest()
    record_sent_meme(h, "dynamic_pillow_fallback", f"МЕМ: {clean_theme[:40]}", out_path, sent_to=recipient)
    return out_path


def generate_dynamic_meme_via_ai(theme="", recipient="yarik"):
    """
    Primary Meme Generator:
    AI model (agy --model gemini-3.8-flash-medium via generate_code_via_antigravity)
    generates a Python script with Pillow FROM SCRATCH dynamically tailored to the specific topic/theme requested.
    The script creates the image, outputs the generated image path via print(out_path),
    and the bot executes the script and sends the newly generated image.
    No repeated cached images or static hardcoded templates!
    """
    raw_theme = (theme or "").strip()
    clean_theme = re.sub(r"^(?:!|/)?(?:бот|ботяра|ботик|робот)[,\s]*", "", raw_theme, flags=re.I).strip()
    clean_theme = re.sub(r"^(?:сгенерируй|создай|сделай|запили|склепай|выдай|скинь|нарисуй)\s+(?:мне\s+)?(?:кринжанутый\s+|смешной\s+|угарный\s+)?(?:мем|мемасик|мемчик|пикчу|картинку)?\s*", "", clean_theme, flags=re.I).strip()
    if not clean_theme:
        clean_theme = raw_theme or "жизненный мем"

    theme_lower = raw_theme.lower()
    is_crossout_topic = any(w in theme_lower for w in ["кроссаут", "кросаут", "crossout"])
    media_abs = os.path.abspath(MEDIA_DIR)

    if is_crossout_topic:
        theme_guideline = (
            f"Тема мема: Crossout (Пустоши, крафты, рандом, PvP/PvE, союзники, взрывы, ховеры, тактика). "
            f"В каталоге '{media_abs}' есть ассеты игры: "
            "'gasgen.png', 'ptur.png', 'kapkan.png', 'heather.png', 'mammoth.png', 'scorpion.png', 'yeti.png', 'hover.png', 'harvester.png', 'wheel1.png'. "
            "Скрипт может загружать нужные ассеты через Image.open(path), масштабировать и накладывать с альфа-каналом, либо рисовать стильную авторскую графику."
        )
    else:
        theme_guideline = (
            "СТРОЖАЙШИЙ ЗАПРЕТ: НЕ приплетать Crossout, Газген, крафты и Пустоши! "
            f"Мем должен быть строго про «{clean_theme}» — жизненный, остроумный, смешной, молодежный/пацанский юмор."
        )

    prompt = f"""Напиши автономный скрипт на Python 3 с использованием библиотеки Pillow (PIL), который С НУЛЯ создает уникальный графический мем по запросу:
«{clean_theme}»

ТРЕБОВАНИЯ К СКРИПТУ:
1. Необходимые импорты:
   `import os, sys, time, random`
   `from PIL import Image, ImageDraw, ImageFont`
2. Размер изображения: 900x900 или 1000x1000 пикселей (высокое разрешение).
3. Графический дизайн:
   - Фон: стильный темный цвет или градиент (например (20, 24, 34) или (16, 20, 30)).
   - Структура: контрастные панели, рамки, разделители (например: две секции 'ОЖИДАНИЕ' vs 'РЕАЛЬНОСТЬ', или диалоговые блоки, или карточка с ярким заголовком, пунктами и цитатой).
4. Шрифты:
   - Ищи шрифты в '{media_abs}':
     'RussoOne-Regular.ttf', 'Montserrat.ttf', 'Anton.ttf', 'RobotoCondensed-Bold.ttf', 'Oswald.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'.
   - Сделай функцию get_font(size), которая пробует загрузить truetype шрифт и падает на ImageFont.load_default() при ошибке.
5. Текст:
   - Остроумный, смешной, оригинальный текст строго под тему «{clean_theme}».
   - Обязательно реализуй перенос строк (word wrap), чтобы текст аккуратно помещался в секциях.
   - Отрисуй текст с контрастной обводкой (stroke_width=2..3) или на ярких плашках.
6. {theme_guideline}
7. Сохранение файла и вывод:
   - Скрипт должен сохранить итоговую картинку в '{media_abs}' с уникальным именем:
     `out_path = os.path.join('{media_abs}', f'meme_{{int(time.time())}}_{{random.randint(1000, 9999)}}.png')`
     `img.save(out_path, 'PNG')`
   - В САМОЙ ПОСЛЕДНЕЙ СТРОКЕ скрипт ОБЯЗАТЕЛЬНО должен вывести путь к файлу в stdout:
     `print(out_path)`
8. Скрипт должен быть полностью самодостаточным, без внешних сетевых запросов и без вызова сторонних библиотек кроме Pillow.

Верни ТОЛЬКО готовый Python 3 код строго внутри одного блока ```python ... ``` без лишнего текста вокруг."""

    code = None
    try:
        from dynamic_agent import generate_code_via_antigravity
        res_ai = generate_code_via_antigravity(prompt, timeout=90)
        if res_ai:
            m = re.search(r"```(?:python)?\s*(.*?)\s*```", res_ai, re.DOTALL)
            code = m.group(1).strip() if m else res_ai.strip()
    except Exception as e:
        print(f"[DYNAMIC MEME GEN] Error invoking Antigravity CLI: {e}")

    out_path = None
    if code:
        temp_script = os.path.join(tempfile.gettempdir(), f"dyn_meme_{int(time.time()*1000)}_{random.randint(100, 999)}.py")
        try:
            with open(temp_script, "w", encoding="utf-8") as f:
                f.write(code)
            proc = subprocess.run([sys.executable, temp_script], capture_output=True, text=True, timeout=35)
            if proc.returncode == 0 and proc.stdout.strip():
                for line in reversed(proc.stdout.splitlines()):
                    candidate = line.strip()
                    if os.path.exists(candidate) and os.path.isfile(candidate) and os.path.getsize(candidate) > 500:
                        out_path = candidate
                        break
            else:
                print(f"[DYNAMIC MEME GEN] Generated script failed (rc={proc.returncode}): {proc.stderr[:300]}")
        except Exception as e_run:
            print(f"[DYNAMIC MEME GEN] Error running generated script: {e_run}")
        finally:
            if os.path.exists(temp_script):
                try:
                    os.remove(temp_script)
                except Exception:
                    pass

    if out_path and os.path.exists(out_path):
        saved_copy = os.path.join(SAVED_MEMES_DIR, os.path.basename(out_path))
        try:
            shutil.copy2(out_path, saved_copy)
        except Exception:
            pass
        if os.path.exists(ANDROID_PHOTOS_DIR):
            try:
                shutil.copy2(out_path, os.path.join(ANDROID_PHOTOS_DIR, os.path.basename(out_path)))
            except Exception:
                pass
        h = hashlib.sha256(clean_theme.encode("utf-8") + str(time.time()).encode()).hexdigest()
        record_sent_meme(h, "ai_gemini_3_8_flash", f"МЕМ: {clean_theme[:40]}", out_path, sent_to=recipient)
        print(f"[DYNAMIC MEME GEN] Successfully created custom AI meme: {out_path}")
        return out_path

    # Fallback if AI generation failed or timed out: dynamic Pillow rendering (NEVER static cached templates!)
    print(f"[DYNAMIC MEME GEN] Falling back to dynamic Pillow generation for '{clean_theme}'")
    return render_dynamic_pillow_meme(clean_theme, is_crossout=is_crossout_topic, recipient=recipient)

def generate_crossout_meme(theme="", allow_repeat=False, recipient="yarik"):
    # If repeat is specifically requested, return the last sent meme if available
    if allow_repeat:
        last = get_last_sent_meme(sent_to=recipient) or get_last_sent_meme()
        if last and os.path.exists(last["file_path"]):
            print(f"[MEME] Repeat allowed and requested. Returning last meme: {last['file_path']}")
            return last["file_path"]

    return generate_dynamic_meme_via_ai(theme=theme, recipient=recipient)

# Alias for universal meme generation
generate_meme = generate_crossout_meme

