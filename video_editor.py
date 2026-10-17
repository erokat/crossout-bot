# -*- coding: utf-8 -*-
"""
VIDEO EDITOR ENGINE for Crossout Userbot
Поддерживает операции с видео и анимациями:
- Конвертация видео в GIF (высокое качество, оптимизированная палитра)
- Изменение скорости видео (ускорение 2x, 3x / замедление 0.5x)
- Реверс видео (проигрывание задом наперед)
- Удаление звука / вырезание звуковой дорожки в MP3
- Наложение музыки на видео
- Наложение текста / надписи на видео
- Обрезка видео (тримминг)
- Строгое соблюдение Правила 4: удаление исходных видеофайлов после обработки
"""
import os
import re
import sys
import time
import shutil
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
GIF_DIR = os.path.join(MEDIA_DIR, "gifs")
VIDEO_DIR = os.path.join(MEDIA_DIR, "videos")
SAVED_MEMES_DIR = os.path.join(BASE_DIR, "saved_memes")

os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(GIF_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(SAVED_MEMES_DIR, exist_ok=True)

def cleanup_file(path):
    """Безопасное удаление временного файла для защиты диска (Правило 4)."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
            print(f"[VIDEO CLEANUP] Removed file: {path}")
    except Exception as e:
        print(f"[VIDEO CLEANUP WARNING] Could not remove {path}: {e}")
_LAST_FFMPEG_ERROR = None

def get_last_ffmpeg_error():
    global _LAST_FFMPEG_ERROR
    return _LAST_FFMPEG_ERROR

def set_last_ffmpeg_error(err):
    global _LAST_FFMPEG_ERROR
    _LAST_FFMPEG_ERROR = err

def log_ffmpeg_error(action_name, res):
    err_tail = ""
    if res and res.stderr:
        lines = [line.strip() for line in res.stderr.splitlines() if line.strip()]
        err_tail = lines[-1] if lines else ""
    msg = f"ffmpeg {action_name} failed (code {res.returncode if res else 'unknown'}): {err_tail}"
    sys.stderr.write(f"[VIDEO ERROR] {msg}\n")
    set_last_ffmpeg_error(err_tail or f"Ошибка ffmpeg ({action_name})")


def is_video_editor_request(text, has_video=False):
    if not text:
        return has_video
    t = text.lower().strip()

    triggers = [
        "в гиф", "в гифку", "сделай гифку", "сделай гиф", "переделай в гиф", "переведи в гиф",
        "конвертируй в гиф", "сохрани как гиф", "сохрани в гиф", "gif",
        "ускорь", "ускорить", "замедли", "замедлить", "быстрее", "медленнее",
        "реверс", "реверсни", "задом наперед", "задом наперёд", "наоборот",
        "без звука", "убери звук", "вырежи звук", "удали звук", "заглуши", "мут",
        "извлеки звук", "достань звук", "сохрани звук", "музыку из видео", "в mp3", "в мп3",
        "наложи музыку", "добавь музыку", "наложи трек", "добавь звук", "подставь музыку",
        "обрежь видео", "вырежи видео", "отрежь видео", "обрежь",
        "текст на видео", "надпись на видео", "подпиши видео", "напиши на видео"
    ]
    if any(tr in t for tr in triggers):
        return True

    if has_video and any(w in t for w in ["сделай", "обработай", "отредактируй", "запили", "переделай"]):
        return True

    return False

def video_to_gif(video_path, fps=12, scale_w=480):
    """Конвертирует видео в четкий оптимизированный GIF с генерацией палитры."""
    out_name = f"gif_{int(time.time())}_{os.getpid()}.gif"
    out_path = os.path.join(GIF_DIR, out_name)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", f"fps={fps},scale={scale_w}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer",
        "-y", out_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return out_path
    log_ffmpeg_error("конвертации в GIF", res)
    return None

def build_atempo_filter(speed):
    """
    Constructs ffmpeg atempo filter cascade for any speed > 0.
    In ffmpeg, a single atempo filter only supports values between 0.5 and 2.0.
    For speed > 2.0 (e.g. 3.0), chains atempo=2.0,atempo=1.5.
    For speed < 0.5 (e.g. 0.25), chains atempo=0.5,atempo=0.5.
    """
    speed = float(speed)
    if speed <= 0:
        return "atempo=1.0"
    filters = []
    curr = speed
    if curr > 2.0:
        while curr > 2.0:
            filters.append("atempo=2.0")
            curr /= 2.0
        if curr > 1.0001 or not filters:
            filters.append(f"atempo={curr:.4f}")
    elif curr < 0.5:
        while curr < 0.5:
            filters.append("atempo=0.5")
            curr /= 0.5
        if curr < 0.9999 or not filters:
            filters.append(f"atempo={curr:.4f}")
    else:
        filters.append(f"atempo={curr:.4f}")
    return ",".join(filters)

def has_audio_stream(video_path):
    """Checks via ffprobe whether video contains at least one audio stream."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return bool(res.stdout.strip())
    except Exception:
        return True

def change_video_speed(video_path, speed=2.0):
    """Изменяет скорость видео (ускорение или замедление)."""
    out_name = f"speed_{int(time.time())}_{os.getpid()}.mp4"
    out_path = os.path.join(VIDEO_DIR, out_name)
    pts = 1.0 / speed
    has_audio = has_audio_stream(video_path)

    if has_audio:
        atempo_chain = build_atempo_filter(speed)
        cmd = [
            "ffmpeg", "-i", video_path,
            "-filter_complex", f"[0:v]setpts={pts:.4f}*PTS[v];[0:a]{atempo_chain}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-y", out_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
            return out_path

    # Fallback or direct execution for videos without audio stream
    cmd_no_audio = [
        "ffmpeg", "-i", video_path,
        "-filter_complex", f"[0:v]setpts={pts:.4f}*PTS[v]",
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-an", "-y", out_path
    ]
    res = subprocess.run(cmd_no_audio, capture_output=True, text=True, timeout=60)
    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return out_path
    log_ffmpeg_error("изменения скорости", res)
    return None


def reverse_video(video_path):
    """Проигрывает видео задом наперед."""
    out_name = f"rev_{int(time.time())}_{os.getpid()}.mp4"
    out_path = os.path.join(VIDEO_DIR, out_name)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", "reverse", "-af", "areverse",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-y", out_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if res.returncode != 0:
        # Fallback без звука
        cmd_no_audio = [
            "ffmpeg", "-i", video_path,
            "-vf", "reverse",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-an", "-y", out_path
        ]
        res = subprocess.run(cmd_no_audio, capture_output=True, text=True, timeout=60)

    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return out_path
    log_ffmpeg_error("реверса видео", res)
    return None

def mute_video(video_path):
    """Удаляет звук из видео."""
    out_name = f"mute_{int(time.time())}_{os.getpid()}.mp4"
    out_path = os.path.join(VIDEO_DIR, out_name)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-c:v", "copy", "-an",
        "-y", out_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return out_path
    log_ffmpeg_error("отключения звука", res)
    return None

def extract_audio_from_video(video_path):
    """Извлекает аудиодорожку из видео в MP3."""
    out_name = f"audio_{int(time.time())}_{os.getpid()}.mp3"
    out_path = os.path.join(MEDIA_DIR, out_name)
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn", "-c:a", "libmp3lame", "-q:a", "2",
        "-y", out_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return out_path
    log_ffmpeg_error("извлечения звука", res)
    return None

def add_music_to_video(video_path, music_query_or_file):
    """Накладывает музыку на видео."""
    audio_path = music_query_or_file
    temp_audio_dl = False
    if not os.path.exists(music_query_or_file):
        from media_finder import find_and_download_audio
        dl_path, _ = find_and_download_audio(music_query_or_file)
        if dl_path and os.path.exists(dl_path):
            audio_path = dl_path
            temp_audio_dl = True
        else:
            return None

    out_name = f"musicvid_{int(time.time())}_{os.getpid()}.mp4"
    out_path = os.path.join(VIDEO_DIR, out_name)
    cmd = [
        "ffmpeg", "-i", video_path, "-i", audio_path,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-y", out_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if temp_audio_dl:
        cleanup_file(audio_path)

    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return out_path
    log_ffmpeg_error("наложения музыки", res)
    return None

def add_text_to_video(video_path, text):
    """
    Накладывает читаемую надпись на видео.
    Создает прозрачный PNG оверлей с текстом через Pillow и накладывает его через ffmpeg.
    """
    from PIL import Image, ImageDraw
    from meme_engine import get_font, wrap_text, draw_outlined_text

    # Получаем размеры видео
    probe_cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0",
        video_path
    ]
    res = subprocess.run(probe_cmd, capture_output=True, text=True)
    w, h = 640, 360
    if res.returncode == 0 and "x" in res.stdout:
        try:
            parts = res.stdout.strip().split("x")
            w, h = int(parts[0]), int(parts[1])
        except Exception:
            pass

    # Создаем прозрачный PNG нужного разрешения
    overlay_img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_img)
    font_size = max(20, int(w * 0.05))
    font = get_font("russo", font_size)
    stroke_w = max(3, int(font_size * 0.1))
    line_h = int(font_size * 1.3)

    lines = wrap_text(draw, text.strip(), font, w - 60)
    total_h = len(lines) * line_h
    y_start = h - total_h - max(15, int(h * 0.06))

    for i, line in enumerate(lines):
        bb = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_w)
        lw = bb[2] - bb[0]
        lx = (w - lw) // 2 - bb[0]
        ly = y_start + i * line_h
        draw_outlined_text(draw, (lx, ly), line, font=font, fill="#FFFFFF", stroke_fill="#000000", stroke_width=stroke_w)

    overlay_png = os.path.join(MEDIA_DIR, f"vid_txt_ovl_{os.getpid()}_{int(time.time())}.png")
    overlay_img.save(overlay_png, "PNG")

    out_name = f"captioned_{int(time.time())}_{os.getpid()}.mp4"
    out_path = os.path.join(VIDEO_DIR, out_name)
    cmd = [
        "ffmpeg", "-i", video_path, "-i", overlay_png,
        "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
        "-map", "[v]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-c:a", "copy",
        "-pix_fmt", "yuv420p", "-y", out_path
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    cleanup_file(overlay_png)

    if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return out_path
    log_ffmpeg_error("наложения надписи", res)
    return None

def process_video_command(video_path, command_text):
    """
    Главный диспетчер обработки видео.
    Распознает команду, применяет трансформацию и удаляет входное видео по Правилу 4.
    Возвращает (output_file_path, reply_caption, is_gif, is_audio).
    """
    if not video_path or not os.path.exists(video_path):
        return None, "Видеофайл не найден!", False, False

    t = command_text.lower().strip()
    out_file = None
    reply_cap = "Держи обработанное видео! 🎬🔥"
    is_gif = False
    is_audio = False
    set_last_ffmpeg_error(None)

    try:
        # 1. В гифку
        if any(w in t for w in ["гиф", "gif"]):
            out_file = video_to_gif(video_path)
            reply_cap = "Держи сочную гифку из этого видео! ✨🎞️"
            is_gif = True

        # 2. Ускорить / замедлить
        elif any(w in t for w in ["ускорь", "быстрее"]):
            # Проверим множитель (например 2x, 2х, в 2 раза, 3x, на 1.5x, вдвое, втрое)
            # Не парсить годы (2024), таймкоды или длительности (на 5 минут) без явного указания множителя
            speed = 2.0
            if "втрое" in t:
                speed = 3.0
            elif "вчетверо" in t:
                speed = 4.0
            elif "вдвое" in t:
                speed = 2.0
            else:
                m = re.search(r"(?:(?:в|на)\s+)?(\d+(?:[.,]\d+)?)\s*(?:[xх]|раз[а-я]*)\b", t)
                if not m:
                    # Match "в N" or "на N" only if NOT followed by time or calendar units (минут, секунд, часов, года, лет, дня)
                    m = re.search(r"\b(?:в|на)\s+(\d+(?:[.,]\d+)?)(?!\s*(?:год[а-я]*|мин[а-я]*|сек[а-я]*|час[а-я]*|дн[а-я]*|лет|мес[а-я]*))\b", t)
                if m:
                    try:
                        val = float(m.group(1).replace(",", "."))
                        if 1.0 <= val <= 10.0:
                            speed = min(4.0, max(1.2, val))
                    except ValueError:
                        speed = 2.0
            out_file = change_video_speed(video_path, speed=speed)
            reply_cap = f"Ускорил видео в {speed}x! 🏎️💨"

        elif any(w in t for w in ["замедли", "медленнее"]):
            slow_factor = 2.0
            if "вчетверо" in t:
                slow_factor = 4.0
            elif "втрое" in t:
                slow_factor = 3.0
            elif "вдвое" in t:
                slow_factor = 2.0
            else:
                m = re.search(r"(?:(?:в|на)\s+)?(\d+(?:[.,]\d+)?)\s*(?:[xх]|раз[а-я]*)\b", t)
                if not m:
                    m = re.search(r"\b(?:в|на)\s+(\d+(?:[.,]\d+)?)(?!\s*(?:год[а-я]*|мин[а-я]*|сек[а-я]*|час[а-я]*|дн[а-я]*|лет|мес[а-я]*))\b", t)
                if m:
                    try:
                        val = float(m.group(1).replace(",", "."))
                        if 1.0 < val <= 10.0:
                            slow_factor = val
                        elif 0.0 < val < 1.0:
                            slow_factor = 1.0 / val
                    except ValueError:
                        slow_factor = 2.0
            speed = max(0.1, min(0.9, 1.0 / slow_factor))
            out_file = change_video_speed(video_path, speed=speed)
            reply_cap = f"Замедлил видео в {slow_factor:g} раз(а) (slow-mo)! 🐢🎬"

        # 3. Реверс
        elif any(w in t for w in ["реверс", "задом наперед", "задом наперёд", "наоборот"]):
            out_file = reverse_video(video_path)
            reply_cap = "Запустил видос задом наперёд! 🔄😂"

        # 4. Без звука
        elif any(w in t for w in ["без звука", "убери звук", "вырежи звук", "удали звук", "заглуши", "мут"]):
            out_file = mute_video(video_path)
            reply_cap = "Удалил звук из видео, полная тишина! 🔇🤫"

        # 5. Извлечь аудио
        elif any(w in t for w in ["извлеки звук", "достань звук", "сохрани звук", "музыку из видео", "в mp3", "в мп3"]):
            out_file = extract_audio_from_video(video_path)
            reply_cap = "Вытащил чистую аудиодорожку в MP3! 🎵🎧"
            is_audio = True

        # 6. Наложить музыку
        elif any(w in t for w in ["наложи музыку", "добавь музыку", "наложи трек", "добавь звук", "подставь музыку"]):
            music_q = re.sub(r"(?i)^(?:!бот|!bot|бот[,\s]*|ботик[,\s]*|пожалуйста[,\s]*|плиз[,\s]*|наложи музыку|добавь музыку|наложи трек|добавь звук|подставь музыку)\s*[:,\s-]*", "", command_text).strip()
            out_file = add_music_to_video(video_path, music_q or "epic gaming phonk")
            reply_cap = f"Наложил саундтрек на видео! 🎵🔊"

        # 7. Наложить текст на видео
        elif any(w in t for w in ["текст на видео", "надпись на видео", "подпиши видео", "напиши на видео", "надпись", "текст"]):
            txt = re.sub(r"(?i)^(?:!бот|!bot|бот[,\s]*|ботик[,\s]*|пожалуйста[,\s]*|плиз[,\s]*|добавь надпись на видео|напиши на видео|подпиши видео|текст на видео|надпись|текст)\s*[:,\s-]*", "", command_text).strip()
            if not txt:
                txt = command_text.strip()
            out_file = add_text_to_video(video_path, txt)
            reply_cap = f"Лови видео с твоей надписью! 🎬✍️"

        else:
            # По умолчанию: конвертируем в GIF
            out_file = video_to_gif(video_path)
            reply_cap = "Сконвертировал видео в качественную гифку! ✨🎞️"
            is_gif = True

        if not out_file or not os.path.exists(out_file):
            err_detail = get_last_ffmpeg_error() or "сбой при конвертации ffmpeg (поврежден файл или неподдерживаемый кодек)"
            reply_cap = f"Ошибка обработки видео: {err_detail}"
            out_file = None
    except subprocess.TimeoutExpired:
        sys.stderr.write("[VIDEO ERROR] ffmpeg operation timed out\n")
        reply_cap = "Превышен лимит времени обработки видео (таймаут)!"
        out_file = None
    except Exception as e:
        sys.stderr.write(f"[VIDEO ERROR] Exception in process_video_command: {e}\n")
        reply_cap = f"Ошибка обработки видео: {e}"
        out_file = None
    finally:
        # ПРАВИЛО 4: обязательно удалять исходный видеофайл с диска
        cleanup_file(video_path)

    return out_file, reply_cap, is_gif, is_audio
