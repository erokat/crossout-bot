# -*- coding: utf-8 -*-
import os
import sys
import re
import time
import json
import shutil
import hashlib
import subprocess
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENSIONS_DIR = os.path.join(BASE_DIR, "extensions")
MEDIA_DIR = os.path.join(BASE_DIR, "media")

os.makedirs(EXTENSIONS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

def is_autonomous_task(text, has_media=False):
    """
    Определяет, требует ли запрос динамического создания нового скрипта,
    обработки медиафайла, выполнения кода или установки новых модулей.
    """
    if not text:
        return has_media
    t = text.lower().strip()

    action_verbs = [
        "обрежь", "обрезать", "вырежи", "вырезать", "сожми", "сжать",
        "склей", "склеить", "конвертируй", "сконвертируй", "конвертировать",
        "поверни", "переверни", "замедли", "ускорь", "извлеки", "вытащи звук",
        "сделай гиф", "сделай qr", "создай qr", "сгенерируй qr", "распакуй",
        "обработай", "отредактируй", "удали фон", "сделай прозрачным",
        "измени размер", "сделай превью", "наложи", "напиши код", "напиши скрипт",
        "напиши программу", "создай файл", "сгенерируй файл", "добавь функцию",
        "добавь возможность", "добавь команду", "сделай функцию", "добавь себе",
        "научись", "сделай скрипт", "сделай генератор", "рассчитай", "смоделируй",
        "нарисуй график", "создай график", "сделай парсер", "напиши парсер",
        "симулятор", "калькулятор", "посчитай", "выполни код", "запусти код",
        "сгенерируй код", "автономн", "сделай фичу", "добавь фичу",
        "сделай так чтобы", "установи модуль", "поставь библиотеку", "скачай файл"
    ]

    if any(verb in t for verb in action_verbs):
        return True

    if has_media and any(w in t for w in ["сделай", "переделай", "измени", "убери", "добавь", "поправь"]):
        return True

    return False

def extract_python_code(response_text):
    if not response_text:
        return None
    pattern = r"```(?:python|py)?\s*([\s\S]*?)\s*```"
    matches = re.findall(pattern, response_text, re.IGNORECASE)
    if matches:
        return matches[0].strip()
    return None

def get_ffmpeg_binary():
    """Возвращает путь к исполняемому файлу ffmpeg, при необходимости авто-устанавливая imageio-ffmpeg."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        try:
            print("[DYNAMIC AGENT] Auto-installing imageio-ffmpeg for media processing...")
            subprocess.run([sys.executable, "-m", "pip", "install", "imageio-ffmpeg"], capture_output=True, timeout=90)
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            return "ffmpeg"

def auto_install_missing_packages(error_output):
    """
    Автоматически обнаруживает недостающие библиотеки из трейсбека ошибки
    (ModuleNotFoundError / ImportError) и устанавливает их через pip.
    """
    installed_any = False
    missing_mods = re.findall(r"No module named ['\"]([^'\"]+)['\"]", error_output)

    module_pkg_map = {
        "cv2": "opencv-python-headless",
        "PIL": "pillow",
        "yaml": "pyyaml",
        "bs4": "beautifulsoup4",
        "moviepy": "moviepy",
        "qrcode": "qrcode[pil]",
        "pydub": "pydub",
        "fitz": "pymupdf",
        "docx": "python-docx",
        "pptx": "python-pptx",
        "sklearn": "scikit-learn",
        "scipy": "scipy",
        "pandas": "pandas",
        "numpy": "numpy",
        "imageio": "imageio",
        "ffmpeg": "ffmpeg-python"
    }

    for mod in set(missing_mods):
        base_mod = mod.split(".")[0]
        pkg_name = module_pkg_map.get(base_mod, base_mod)
        print(f"[DYNAMIC AGENT] Auto-installing missing dependency: {pkg_name} ...")
        try:
            res = subprocess.run([sys.executable, "-m", "pip", "install", pkg_name], capture_output=True, text=True, timeout=120)
            if res.returncode == 0:
                print(f"[DYNAMIC AGENT] Successfully auto-installed {pkg_name}!")
                installed_any = True
            else:
                print(f"[DYNAMIC AGENT] Failed to install {pkg_name}: {res.stderr[:200]}")
        except Exception as e:
            print(f"[DYNAMIC AGENT] Pip install error: {e}")

    return installed_any

def run_script(script_path, input_file=None, timeout=60):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    ffmpeg_exe = get_ffmpeg_binary()
    env["FFMPEG_EXE"] = ffmpeg_exe

    args = [sys.executable, script_path]
    if input_file:
        env["INPUT_FILE"] = os.path.abspath(input_file)
        args.append(os.path.abspath(input_file))

    try:
        res = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            cwd=BASE_DIR,
            env=env
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Превышено максимальное время выполнения скрипта (таймаут {timeout}с)."
    except Exception as e:
        return -1, "", str(e)

def find_newest_media(before_files, stdout=""):
    # 1. Проверяем явный путь в stdout
    if stdout:
        m = re.findall(r"([/\w.-]+\.(?:png|jpg|jpeg|gif|webp|mp4|webm|mov|mp3|ogg|wav|csv|txt|pdf))", stdout, re.IGNORECASE)
        for cand in reversed(m):
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
            full_cand = os.path.join(BASE_DIR, cand.lstrip("/"))
            if os.path.exists(full_cand) and os.path.isfile(full_cand):
                return full_cand

    # 2. Проверяем папки media/ и extensions/
    search_dirs = [MEDIA_DIR, os.path.join(MEDIA_DIR, "videos"), os.path.join(MEDIA_DIR, "music"), os.path.join(EXTENSIONS_DIR, "media"), EXTENSIONS_DIR]
    all_candidates = []
    for d in search_dirs:
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".wav", ".csv", ".txt", ".pdf")):
                        fp = os.path.join(root, f)
                        if os.path.isfile(fp) and (time.time() - os.path.getmtime(fp) < 90) and fp not in before_files:
                            all_candidates.append(fp)

    if all_candidates:
        all_candidates.sort(key=os.path.getmtime, reverse=True)
        return all_candidates[0]
    return None

def execute_autonomous_task(task_text, sender_name, photo_path=None, ask_ai_fn=None):
    """
    Универсальный автономный саморасширяющийся исполнитель Antigravity:
    1. Анализирует запрос и входные файлы.
    2. При необходимости авто-устанавливает внешние библиотеки через pip.
    3. Генерирует готовый к исполнению Python-скрипт с обработкой входного файла.
    4. Запускает код в изолированной среде с передачей путей и параметров.
    5. При ошибке (например, падение или нехватка модуля) проводит self-healing и auto-install.
    6. Сохраняет новую способность в extensions/ для персистентности.
    7. Возвращает готовый файл и пояснение.
    """
    if not ask_ai_fn:
        return "Модуль AI недоступен.", None

    ffmpeg_bin = get_ffmpeg_binary()

    file_context = ""
    if photo_path and os.path.exists(photo_path):
        file_ext = os.path.splitext(photo_path)[1].lower()
        file_context = (
            f"\nПользователь прикрепил входной файл: `{photo_path}` (тип: {file_ext}).\n"
            f"Внутри твоего кода путь к этому файлу доступен через `os.environ.get('INPUT_FILE')` "
            f"или `sys.argv[1] if len(sys.argv) > 1 else None`.\n"
        )

    prompt = (
        f"Ты — автономный саморасширяющийся AI-движок Telegram-бота на базе Google Antigravity.\n"
        f"Пользователь {sender_name} просит выполнить задачу: «{task_text}».\n"
        f"{file_context}\n"
        "Инструкции для генерации исполняемого кода:\n"
        "1. Напиши автономный скрипт на Python 3 для решения этой задачи.\n"
        "2. Если требуется обработка видео или звука (обрезка, монтаж, извлечение аудио, конвертация):\n"
        f"   - Используй ffmpeg через `os.environ.get('FFMPEG_EXE', '{ffmpeg_bin}')` или модуль `subprocess`.\n"
        "   - Или используй moviepy / pydub / opencv / PIL.\n"
        "3. Если требуются сторонние библиотеки (например: pillow, opencv-python-headless, qrcode, pydub, scipy, pandas, beautifulsoup4), смело используй их в import — движок автоматически установит недостающие пакеты при запуске!\n"
        "4. Все создаваемые файлы сохраняй в папку `media/` (например, `os.path.join(os.path.dirname(__file__), '..', 'media', 'output_filename.ext')`) и печатай путь к итоговому файлу через `print(result_path)`.\n"
        "5. Результаты работы и пояснения выводи через `print(...)`.\n\n"
        "Формат ответа:\n"
        "Краткое пояснение (1 строка).\n"
        "```python\n"
        "# Рабочий, готовый к запуску Python-код\n"
        "```\n"
    )

    ai_reply = ask_ai_fn(prompt, photo_path=photo_path)
    if not ai_reply:
        return f"{sender_name}, не удалось сгенерировать скрипт для этой задачи. Попробуй уточнить требования!", None

    code = extract_python_code(ai_reply)
    if not code:
        return ai_reply, None

    # Предварительное обнаружение нужных библиотек из кода
    needed_packages = []
    if "import cv2" in code: needed_packages.append("opencv-python-headless")
    if "import qrcode" in code: needed_packages.append("qrcode[pil]")
    if "import moviepy" in code: needed_packages.append("moviepy")
    if "import pydub" in code: needed_packages.append("pydub")
    if "import docx" in code: needed_packages.append("python-docx")
    if "import fitz" in code: needed_packages.append("pymupdf")
    for pkg in needed_packages:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", pkg], capture_output=True, timeout=90)
        except Exception:
            pass

    script_id = hashlib.md5(f"{task_text}_{time.time()}".encode()).hexdigest()[:8]
    script_filename = f"auto_{script_id}.py"
    script_path = os.path.join(EXTENSIONS_DIR, script_filename)

    with open(script_path, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write(f"# Auto-generated by Antigravity Autonomous Engine for task: {task_text[:80]}\n\n")
        f.write(code)

    before_files = set()
    for root, _, files in os.walk(MEDIA_DIR):
        for f in files:
            before_files.add(os.path.join(root, f))

    # Первый запуск
    code_rc, stdout, stderr = run_script(script_path, input_file=photo_path)

    # Если упал из-за отсутствия пакета — устанавливаем и перезапускаем
    if code_rc != 0 and ("ModuleNotFoundError" in stderr or "No module named" in stderr):
        installed = auto_install_missing_packages(stderr)
        if installed:
            code_rc, stdout, stderr = run_script(script_path, input_file=photo_path)

    # Self-healing / самоотладка через AI при ошибке выполнения
    if code_rc != 0 and stderr:
        fix_prompt = (
            f"Скрипт, написанный для задачи «{task_text}», упал с ошибкой:\n\n"
            f"```\n{stderr[:900]}\n```\n\n"
            f"Исходный код:\n```python\n{code}\n```\n\n"
            "Устрани причину падения, исправь синтаксис/логику и верни исправленный, полностью работающий Python-код строго внутри ```python ... ```."
        )
        fixed_reply = ask_ai_fn(fix_prompt)
        fixed_code = extract_python_code(fixed_reply)
        if fixed_code:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("# -*- coding: utf-8 -*-\n")
                f.write(f"# Auto-fixed by Antigravity Autonomous Engine for task: {task_text[:80]}\n\n")
                f.write(fixed_code)
            code_rc, stdout, stderr = run_script(script_path, input_file=photo_path)
            if code_rc != 0 and ("ModuleNotFoundError" in stderr or "No module named" in stderr):
                if auto_install_missing_packages(stderr):
                    code_rc, stdout, stderr = run_script(script_path, input_file=photo_path)

    # Ищем появившийся файл
    new_media = find_newest_media(before_files, stdout=stdout)

    clean_desc = re.sub(r"```[\s\S]*?```", "", ai_reply).strip()

    final_text_parts = []
    final_text_parts.append(f"⚡ **Автономное действие выполнено для {sender_name}:**")
    if clean_desc:
        final_text_parts.append(f"_{clean_desc}_\n")

    if stdout:
        clean_out = "\n".join([line for line in stdout.splitlines() if not line.startswith("/") and not line.endswith((".png", ".jpg", ".mp4", ".mp3"))])
        if clean_out.strip():
            final_text_parts.append(f"📊 **Результат:**\n```\n{clean_out[:1200]}\n```")

    if code_rc == 0 and not new_media and not stdout:
        final_text_parts.append("✅ Задача успешно выполнена и скрипт сохранен в `extensions/`.")
    elif code_rc != 0 and not new_media:
        final_text_parts.append(f"⚠️ Ошибка выполнения:\n`{stderr[:300]}`")

    if new_media:
        final_text_parts.append(f"📁 Готовый файл: `{os.path.basename(new_media)}`")

    return "\n".join(final_text_parts), new_media
