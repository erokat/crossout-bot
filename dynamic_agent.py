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
REGISTRY_FILE = os.path.join(EXTENSIONS_DIR, "registry.json")

os.makedirs(EXTENSIONS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

def load_registry():
    if os.path.exists(REGISTRY_FILE):
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_registry(data):
    try:
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[DYNAMIC AGENT] Failed to save registry: {e}")

def register_extension(slug, filename, description, triggers):
    reg = load_registry()
    reg[slug] = {
        "filename": filename,
        "description": description,
        "triggers": triggers,
        "updated_at": time.time()
    }
    save_registry(reg)

def find_existing_extension(task_text):
    reg = load_registry()
    t = task_text.lower()
    for slug, info in reg.items():
        triggers = info.get("triggers", [])
        if any(tr in t for tr in triggers):
            fn = info.get("filename")
            fp = os.path.join(EXTENSIONS_DIR, fn)
            if os.path.exists(fp):
                return fp, info
    return None, None

def is_autonomous_task(text, has_media=False):
    """
    Определяет, требует ли запрос динамического создания нового дополнения,
    обработки медиафайла, генерации файла или расширения способностей бота.
    """
    if not text:
        return has_media
    t = text.lower().strip()

    # Если уже есть зарегистрированное дополнение под эти триггеры
    ext_path, _ = find_existing_extension(t)
    if ext_path:
        return True

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
        "сделай так чтобы", "установи модуль", "поставь библиотеку", "скачай файл",
        "сделай таблицу", "сохрани в excel", "сохрани в csv", "сделай отчет",
        "сделай pdf", "сгенерируй pdf", "добавь дополнение", "напиши дополнение",
        "создай дополнение", "сгенерируй дополнение", "сделай дополнение",
        "дополни дополнение", "дополнение", "добавь модуль", "создай модуль"
    ]

    if any(verb in t for verb in action_verbs):
        return True

    if has_media and any(w in t for w in ["сделай", "переделай", "измени", "убери", "добавь", "поправь", "обрежь"]):
        return True

    return False

def check_or_classify_autonomous_task(text, has_media=False, ask_ai_fn=None):
    """
    Интеллектуальный классификатор: проверяет быстрые правила и при необходимости
    спрашивает AI, является ли сообщение прямым поручением сделать/сгенерировать что-то.
    """
    if is_autonomous_task(text, has_media):
        return True

    t_clean = text.lower().strip()
    if len(t_clean) < 6:
        return False

    # Исключаем обычные разговорные фразы
    chit_chat = ["привет", "здарова", "как дела", "что делаешь", "ты тут", "спасибо", "пока", "ярик", "бот ты тут", "ясно", "понял"]
    if t_clean in chit_chat:
        return False

    # Поручения создать что-то
    action_intent_patterns = [
        r"\b(сделай|создай|сгенерируй|напиши|запили|собери|выгрузи|сохрани|добавь|установи|прикрути|научись)\b",
        r"\b(файл|скрипт|программ|дополнени|плагин|модул|функци|таблиц|отчет|график|диаграмм|баз|код)\b"
    ]
    matches = sum(1 for p in action_intent_patterns if re.search(p, t_clean))
    if matches >= 2:
        return True

    # Если есть подозрение на поручение — опрашиваем AI
    if ask_ai_fn and len(t_clean) > 8 and any(w in t_clean for w in ["сделай", "создай", "сгенерируй", "напиши", "добавь", "научись", "файл", "можешь", "умеешь"]):
        check_prompt = (
            f"Пользователь написал боту: «{text}».\n"
            "Это конкретное поручение СДЕЛАТЬ/СГЕНЕРИРОВАТЬ ЧТО-ТО (файл, скрипт, вычисление, дополнение, обработку)?\n"
            "Ответь строго 'TASK' если это поручение что-то сделать/создать/написать, или 'CHAT' если это просто беседа."
        )
        res = ask_ai_fn(check_prompt)
        if res and "TASK" in res.upper():
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
        "ffmpeg": "ffmpeg-python",
        "openpyxl": "openpyxl",
        "xlsxwriter": "xlsxwriter",
        "matplotlib": "matplotlib",
        "reportlab": "reportlab"
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

def run_script(script_path, input_file=None, task_text=None, timeout=60):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    ffmpeg_exe = get_ffmpeg_binary()
    env["FFMPEG_EXE"] = ffmpeg_exe

    if task_text:
        env["TASK_TEXT"] = str(task_text)

    args = [sys.executable, script_path]
    if input_file:
        env["INPUT_FILE"] = os.path.abspath(input_file)
        args.append(os.path.abspath(input_file))
    elif task_text:
        args.append(str(task_text))

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
        m = re.findall(r"([/\w.-]+\.(?:png|jpg|jpeg|gif|webp|mp4|webm|mov|mp3|ogg|wav|csv|xlsx|txt|pdf))", stdout, re.IGNORECASE)
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
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".wav", ".csv", ".xlsx", ".txt", ".pdf")):
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
    1. Проверяет реестр существующих дополнений.
    2. Если дополнения еще нет — генерирует новый автономный модуль под задачу.
    3. Авто-устанавливает недостающие внешние библиотеки.
    4. Запускает код, при ошибках запускает самоотладку (self-healing).
    5. Регистрирует новое дополнение в extensions/registry.json для постоянного использования.
    6. Возвращает созданный файл и подробный отчет.
    """
    # 1. Проверяем, есть ли уже готовое дополнение для этой задачи (не требует AI!)
    existing_script, ext_info = find_existing_extension(task_text)
    if existing_script:
        print(f"[DYNAMIC AGENT] Reusing existing extension: {existing_script}")
        code_rc, stdout, stderr = run_script(existing_script, input_file=photo_path, task_text=task_text)
        if code_rc == 0:
            new_media = find_newest_media(set(), stdout=stdout)
            if any(marker in stdout for marker in ["📍", "🌡️", "📊", "☀️", "🌤️", "☁️"]):
                report = stdout
            else:
                report = (
                    f"⚡ **Использовано дополнение к боту:** `{os.path.basename(existing_script)}`\n"
                    f"_{ext_info.get('description', 'Выполнение сохраненной функции')}_\n\n"
                )
                if stdout:
                    report += f"📊 **Результат:**\n```\n{stdout[:2000]}\n```\n"
            if new_media:
                report += f"\n📁 Готовый файл: `{os.path.basename(new_media)}`"
            return report, new_media

    # 2. Если дополнения еще нет — требуется AI для генерации нового модуля
    if not ask_ai_fn:
        return f"{sender_name}, модуль AI временно недоступен для генерации нового кода.", None

    ffmpeg_bin = get_ffmpeg_binary()

    file_context = ""
    if photo_path and os.path.exists(photo_path):
        file_ext = os.path.splitext(photo_path)[1].lower()
        file_context = (
            f"\nПользователь прикрепил входной файл: `{photo_path}` (тип: {file_ext}).\n"
            f"Внутри твоего кода путь к этому файлу доступен через `os.environ.get('INPUT_FILE')` "
            f"или `sys.argv[1] if len(sys.argv) > 1 else None`.\n"
        )

    # 2. Генерируем новое дополнение с нуля
    prompt = (
        f"Ты — автономный саморасширяющийся AI-движок Telegram-бота на базе Google Antigravity.\n"
        f"Пользователь {sender_name} просит выполнить задачу, которой бот еще не умел: «{task_text}».\n"
        f"{file_context}\n"
        "Инструкции для создания нового дополнения (модуля):\n"
        "1. Напиши автономный скрипт на Python 3, который добавляет эту новую функцию и выполняет её прямо сейчас.\n"
        "2. В первой строке комментария укажи краткий slug и описание модуля в формате:\n"
        "   # EXTENSION: <slug_name> | <Краткое описание>\n"
        "3. Если требуется обработка видео или звука (обрезка, монтаж, извлечение аудио, конвертация):\n"
        f"   - Используй ffmpeg через `os.environ.get('FFMPEG_EXE', '{ffmpeg_bin}')` или модуль `subprocess`.\n"
        "   - Или используй moviepy / pydub / opencv / PIL.\n"
        "4. Если требуются сторонние библиотеки (например: openpyxl, pandas, qrcode, pillow, moviepy, pydub, matplotlib, reportlab):\n"
        "   Смело импортируй их — движок автоматически установит их через pip!\n"
        "5. Все создаваемые файлы сохраняй в папку `media/` и обязательно выводи путь к созданному файлу через `print(result_path)`.\n"
        "6. Результаты работы и пояснения выводи через `print(...)`.\n\n"
        "Формат ответа:\n"
        "Краткое пояснение (1 строка).\n"
        "```python\n"
        "# Рабочий, готовый к запуску Python-код\n"
        "```\n"
    )

    ai_reply = ask_ai_fn(prompt, photo_path=photo_path)
    if not ai_reply:
        return f"{sender_name}, не удалось сгенерировать дополнение для этой задачи. Попробуй уточнить требования!", None

    code = extract_python_code(ai_reply)
    if not code:
        return ai_reply, None

    # Извлекаем метаданные дополнения
    slug_match = re.search(r"#\s*EXTENSION:\s*([a-zA-Z0-9_-]+)\s*\|\s*(.+)", code)
    if slug_match:
        ext_slug = slug_match.group(1).strip()
        ext_desc = slug_match.group(2).strip()
    else:
        ext_slug = "ext_" + hashlib.md5(task_text.encode()).hexdigest()[:6]
        ext_desc = f"Дополнение для задачи: {task_text[:60]}"

    script_filename = f"{ext_slug}.py"
    script_path = os.path.join(EXTENSIONS_DIR, script_filename)

    with open(script_path, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write(f"# Auto-generated Antigravity Extension: {ext_desc}\n\n")
        f.write(code)

    before_files = set()
    for root, _, files in os.walk(MEDIA_DIR):
        for f in files:
            before_files.add(os.path.join(root, f))

    # Первый запуск
    code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text)

    # Если не хватило модуля — авто-устанавливаем через pip и перезапускаем
    if code_rc != 0 and ("ModuleNotFoundError" in stderr or "No module named" in stderr):
        installed = auto_install_missing_packages(stderr)
        if installed:
            code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text)

    # Self-healing / самоотладка при ошибках
    if code_rc != 0 and stderr:
        fix_prompt = (
            f"Скрипт дополнения для «{task_text}» упал с ошибкой:\n\n"
            f"```\n{stderr[:900]}\n```\n\n"
            f"Исходный код:\n```python\n{code}\n```\n\n"
            "Устрани ошибку, исправь логику и верни исправленный, полностью работающий Python-код строго внутри ```python ... ```."
        )
        fixed_reply = ask_ai_fn(fix_prompt)
        fixed_code = extract_python_code(fixed_reply)
        if fixed_code:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("# -*- coding: utf-8 -*-\n")
                f.write(f"# Auto-fixed Antigravity Extension: {ext_desc}\n\n")
                f.write(fixed_code)
            code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text)
            if code_rc != 0 and ("ModuleNotFoundError" in stderr or "No module named" in stderr):
                if auto_install_missing_packages(stderr):
                    code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text)

    # Если скрипт успешно отработал — регистрируем его как постоянное дополнение к боту!
    if code_rc == 0:
        stopwords = {"бот", "пожалуйста", "скинь", "сделай", "напиши", "сгенерируй", "создай", "дополнение", "чтобы", "можешь", "умеешь", "давай", "хочу"}
        words = [w for w in re.findall(r"\b[а-яa-z]{4,}\b", task_text.lower()) if w not in stopwords]
        # Добавляем части slug
        for part in re.split(r"[_-]", ext_slug):
            if len(part) >= 3 and part.lower() not in words:
                words.append(part.lower())
        register_extension(ext_slug, script_filename, ext_desc, words[:7])
        print(f"[DYNAMIC AGENT] Successfully registered new extension: {ext_slug} (triggers: {words[:7]})")

    # Ищем созданный медиафайл
    new_media = find_newest_media(before_files, stdout=stdout)

    final_text_parts = []
    final_text_parts.append(f"🧩 **Сгенерировано новое дополнение к боту:** `{script_filename}`")
    final_text_parts.append(f"💡 _{ext_desc}_\n")

    if stdout:
        clean_out = "\n".join([line for line in stdout.splitlines() if not line.startswith("/") and not line.endswith((".png", ".jpg", ".mp4", ".mp3", ".xlsx", ".pdf"))])
        if clean_out.strip():
            if any(marker in clean_out for marker in ["📍", "🌡️", "📊", "☀️", "🌤️", "☁️", "#", "*"]):
                final_text_parts.append(clean_out[:2000])
            else:
                final_text_parts.append(f"📊 **Результат:**\n```\n{clean_out[:1200]}\n```")

    if code_rc == 0 and not new_media and not stdout:
        final_text_parts.append("✅ Дополнение успешно скомпилировано, зарегистрировано в системе и выполнено!")
    elif code_rc != 0 and not new_media:
        final_text_parts.append(f"⚠️ Ошибка при выполнении:\n`{stderr[:300]}`")

    if new_media:
        final_text_parts.append(f"\n📁 Создан готовый файл: `{os.path.basename(new_media)}`")

    return "\n".join(final_text_parts), new_media

def set_pending_proposal(user_id, task_text, bot_msg_id=None):
    from db import set_kv
    data = {
        "task_text": task_text,
        "bot_msg_id": bot_msg_id,
        "created_at": time.time()
    }
    set_kv(f"pending_ext_proposal_{user_id}", json.dumps(data, ensure_ascii=False))

def get_pending_proposal(user_id):
    from db import get_kv
    raw = get_kv(f"pending_ext_proposal_{user_id}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        # 15 minutes TTL
        if time.time() - data.get("created_at", 0) > 900:
            clear_pending_proposal(user_id)
            return None
        return data
    except Exception:
        return None

def clear_pending_proposal(user_id):
    from db import set_kv
    set_kv(f"pending_ext_proposal_{user_id}", "")

def is_pure_chitchat(text):
    if not text:
        return True
    t = text.lower().strip()
    for prefix in ["!бот", "!bot", "бот,", "бот "]:
        if t.startswith(prefix):
            t = t[len(prefix):].strip()

    t_clean = re.sub(r"[^\w\s]", "", t).strip()
    chit_chat_exact = {
        "привет", "здарова", "здорово", "хай", "ку", "салам", "салют", "добрый день",
        "добрый вечер", "доброе утро", "как дела", "как жизнь", "че как", "чё как",
        "что делаешь", "че делаешь", "ты тут", "бот ты тут", "живой", "ты жив",
        "спасибо", "от души", "благодарю", "пока", "до связи", "до завтра", "споки",
        "ясно", "понял", "понятно", "ок", "хорошо", "ладно", "лол", "кек",
        "хаха", "ахах", "красава", "красавчик", "нормас", "норм", "круто", "огонь",
        "ярик лох", "ярик", "миша"
    }
    if t_clean in chit_chat_exact:
        return True
    if len(t_clean) < 4 and not any(w in t_clean for w in ["да", "нет", "го", "не"]):
        return True
    return False
