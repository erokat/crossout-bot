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
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
EXTENSIONS_DIR = os.path.join(BASE_DIR, "extensions")
MEDIA_DIR = os.path.join(BASE_DIR, "media")
SAVED_MEMES_DIR = os.path.join(BASE_DIR, "saved_memes")
REGISTRY_FILE = os.path.join(EXTENSIONS_DIR, "registry.json")

os.makedirs(SKILLS_DIR, exist_ok=True)
os.makedirs(EXTENSIONS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(SAVED_MEMES_DIR, exist_ok=True)

PROTECTED_CORE_FILES = {
    "keep_alive.py",
    "wait_for_yarik.py",
    "db.py",
    "send.py",
    "session.session",
    "crossout_session.session",
    "config.py",
    "config.json",
    "Dockerfile",
    "main.py",
    "requirements.txt",
    "github_sync.py",
    "dynamic_agent.py",
    "add_to_sticker_pack.py",
    "ask_owner.py",
    "media_finder.py",
    "meme_engine.py",
    "meme_generator.py",
    "photo_editor.py",
    "video_editor.py",
    "gdrive.py"
}

def is_safe_skill_path(filepath):
    """
    Ensures that the dynamic generator does not overwrite core system files.
    Allowed locations: skills/, media/, saved_memes/, or new subdirectories.
    Forbidden: core files in root directory.
    """
    if not filepath:
        return False
    abs_path = os.path.abspath(filepath)
    base_name = os.path.basename(abs_path).lower()
    if base_name in {f.lower() for f in PROTECTED_CORE_FILES}:
        return False
    dir_name = os.path.dirname(abs_path)
    if dir_name == BASE_DIR and base_name in {f.lower() for f in PROTECTED_CORE_FILES}:
        return False
    return True

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

def register_extension(slug, filename, description, triggers, produces_media=False):
    reg = load_registry()
    reg[slug] = {
        "filename": filename,
        "description": description,
        "triggers": triggers,
        "produces_media": bool(produces_media),
        "updated_at": time.time()
    }
    save_registry(reg)

COMMON_SKILL_STOPWORDS = {
    "бот", "ботяра", "ботик", "робот", "пожалуйста", "пж", "скинь", "кинь", "дай",
    "сделай", "напиши", "создай", "сгенерируй", "запусти", "покажи", "что", "как",
    "где", "когда", "какая", "какой", "какое", "какие", "сколько", "будет", "мне",
    "нам", "ему", "для", "или", "если", "хочу", "можешь", "умеешь", "давай", "это"
}

def calculate_skill_match_score(query_text, skill_name, triggers):
    if not query_text:
        return 0
    t = query_text.lower().strip()
    t = re.sub(r"^(?:[!/]?бот[,\s]*|ботик[,\s]*|ботяра[,\s]*|bot[,\s]*)", "", t).strip()
    words = [w.strip(".,!?:;\"'()[]{}«»") for w in re.split(r"[\s,;]+", t) if w.strip(".,!?:;\"'()[]{}«»")]

    score = 0
    s_name_clean = (skill_name or "").lower().replace("_", " ")

    if len(skill_name or "") >= 4:
        if skill_name.lower() in t or s_name_clean in t:
            score += 15

    for tr in triggers:
        if not tr or not isinstance(tr, str):
            continue
        tr_clean = tr.lower().strip()
        if tr_clean in COMMON_SKILL_STOPWORDS:
            continue

        # Многословные триггеры («прогноз погоды») имеют наивысший приоритет
        if " " in tr_clean:
            if tr_clean in t:
                score += 12
                continue

        # Одиночные слова дают высокий балл ТОЛЬКО если запрос короткий (команда)
        # В длинных предложениях одно случайное слово не должно вызывать чужой навык
        if tr_clean in words or re.search(r"\b" + re.escape(tr_clean) + r"\b", t):
            if len(words) <= 3:
                score += 8
            else:
                score += 2
            continue

        if len(tr_clean) >= 4:
            stem = tr_clean[:5] if len(tr_clean) >= 6 else tr_clean[:4]
            if any(w.startswith(stem) for w in words if w not in COMMON_SKILL_STOPWORDS):
                score += 3
                continue

    return score

def is_one_off_creative_task(task_text):
    if not task_text:
        return False
    t = task_text.lower().strip()
    if any(k in t for k in ["добавь команду", "добавь функцию", "добавь навык", "добавь модуль", "научись", "создай команду", "создай плагин", "создай модуль"]):
        return False
    creative_markers = [
        "мем", "мэм", "мемасик", "мемчик", "картинк", "пикч", "нарисуй",
        "сгенерируй фото", "сгенерируй изображение", "сгенерируй картинку",
        "доск", "шахмат", "арт", "открытк", "демотиватор", "прикол", "иллюстраци"
    ]
    return any(m in t for m in creative_markers)

def find_existing_skill(task_text):
    """
    Checks the registry of dynamic skills in SQLite (dynamic_skills table)
    using intelligent keyword scoring.
    If found, ensures the file is present in skills/ and returns (script_path, skill_info).
    """
    if not task_text:
        return None, None
    t = task_text.lower().strip()
    if is_one_off_creative_task(t):
        return None, None
    if any(w in t for w in ["новый", "нового", "новеньк", "друг", "переделай", "заново", "по-другому", "реалистичн"]):
        return None, None

    best_match = None
    best_score = 0

    try:
        from db import list_dynamic_skills
        skills = list_dynamic_skills()
        for s in skills:
            s_name = s.get("skill_name", "")
            triggers = s.get("triggers", [])
            score = calculate_skill_match_score(t, s_name, triggers)
            if score >= 6 and score > best_score:
                best_score = score
                best_match = s

        if best_match:
            s_name = best_match.get("skill_name", "")
            fn = os.path.basename(best_match.get("file_path") or f"{s_name}.py")
            if not fn.endswith(".py"):
                fn += ".py"
            fp = os.path.join(SKILLS_DIR, fn)
            if not os.path.exists(fp) and best_match.get("code"):
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(best_match["code"])
            if os.path.exists(fp):
                return fp, best_match
    except Exception as e:
        print(f"[DYNAMIC SKILL ENGINE] Error querying dynamic_skills: {e}")

    # Fallback check in legacy registry
    reg = load_registry()
    best_legacy = None
    best_leg_score = 0
    for slug, info in reg.items():
        triggers = info.get("triggers", [])
        score = calculate_skill_match_score(t, slug, triggers)
        if score >= 6 and score > best_leg_score:
            best_leg_score = score
            best_legacy = (slug, info)

    if best_legacy:
        slug, info = best_legacy
        fn = info.get("filename")
        fp = os.path.join(SKILLS_DIR, fn) if os.path.exists(os.path.join(SKILLS_DIR, fn)) else os.path.join(EXTENSIONS_DIR, fn)
        if os.path.exists(fp):
            if isinstance(info, dict) and "skill_name" not in info:
                info["skill_name"] = slug
            return fp, info

    return None, None

find_existing_extension = find_existing_skill

def is_explicit_meme_request(text):
    if not text:
        return False
    t = text.lower().strip()
    # Explicit coding/module creation requests must not be treated as simple memes
    code_words = [
        "напиши код", "напиши скрипт", "создай скрипт", "создай модуль",
        "создай дополнение", "напиши дополнение", "добавь модуль", "добавь дополнение",
        "сделай модуль", "сделай скрипт", "сделай дополнение"
    ]
    if any(cw in t for cw in code_words):
        return False
    meme_words = ["мем", "мэм", "мемасик", "мемчик", "мемы", "мэмы", "демотиватор"]
    return any(mw in t for mw in meme_words)

def is_meme_or_media_request(text):
    if not text:
        return False
    t = text.lower().strip()
    media_words = [
        "мем", "мэм", "мемасик", "мемчик", "пикч", "картинк", "демотиватор",
        "кросаут", "кроссаут", "crossout", "шахмат", "доск", "нарисуй", "сгенерируй",
        "арт", "рисунок", "сцен", "фото", "изображен", "график", "открытк", "прикол"
    ]
    return any(w in t for w in media_words)

def is_autonomous_task(text, has_media=False):
    """
    Определяет, требует ли запрос динамического создания нового программного модуля в skills/,
    только когда пользователь прямо просит запрограммировать/расширить бота новым кодом.
    Любые запросы на мемы, картинки, генерацию изображений, музыку, решение задач, сочинения
    и обычные вопросы НИКОГДА не должны идти в Dynamic Skill Engine!
    """
    if not text:
        return False
    t = text.lower().strip()

    from photo_editor import is_photo_editor_request
    if is_photo_editor_request(t, has_media):
        return False

    if is_explicit_meme_request(t) or is_one_off_creative_task(t) or is_meme_or_media_request(t):
        return False

    # Если уже есть зарегистрированное дополнение под эти триггеры
    ext_path, _ = find_existing_extension(t)
    if ext_path:
        return True

    # СТРОГИЙ ФИЛЬТР: ТОЛЬКО прямые поручения запрограммировать новый функционал для бота
    explicit_coding_phrases = [
        "добавь себе команду", "добавь команду", "создай модуль для бота", "напиши плагин",
        "добавь функцию бота", "запрограммируй новую функцию", "напиши скрипт парсера",
        "добавь дополнение к боту", "напиши python код", "создай python модуль",
        "научи бота новой команде", "добавь новый навык", "зарегистрируй команду"
    ]
    return any(p in t for p in explicit_coding_phrases)

def check_or_classify_autonomous_task(text, has_media=False, ask_ai_fn=None):
    """
    Проверяет, является ли запрос прямым требованием написать новый модуль/код для бота.
    Никогда не отправляет творческие, визуальные или разговорные запросы в генератор кода.
    """
    return is_autonomous_task(text, has_media)

def extract_python_code(response_text):
    if not response_text:
        return None
    pattern = r"```(?:python|py)?\s*([\s\S]*?)\s*```"
    matches = re.findall(pattern, response_text, re.IGNORECASE)
    if matches:
        return max(matches, key=len).strip()
    # If model returned raw Python without markdown fences
    candidate = response_text.strip()
    if "import " in candidate or "def " in candidate or candidate.startswith("#"):
        lines = [l for l in candidate.splitlines() if not l.strip().startswith("```")]
        return "\n".join(lines).strip()
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

    local_modules = {
        "config", "db", "meme_generator", "meme_engine", "dynamic_agent",
        "photo_editor", "media_finder", "gdrive", "send", "wait_for_yarik", "ask_owner"
    }

    for mod in set(missing_mods):
        base_mod = mod.split(".")[0]
        if base_mod in local_modules:
            continue
        pkg_name = module_pkg_map.get(base_mod, base_mod)
        print(f"[DYNAMIC AGENT] Auto-installing missing dependency: {pkg_name} ...")
        try:
            cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", pkg_name]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if res.returncode != 0 and "no such option" in res.stderr.lower():
                cmd = [sys.executable, "-m", "pip", "install", pkg_name]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
            if res.returncode == 0:
                print(f"[DYNAMIC SKILL ENGINE] Successfully auto-installed {pkg_name}!")
                installed_any = True
            else:
                print(f"[DYNAMIC SKILL ENGINE] Failed to install {pkg_name}: {res.stderr[:200]}")
        except Exception as e:
            print(f"[DYNAMIC SKILL ENGINE] Pip install error: {e}")

    return installed_any

def run_script(script_path, input_file=None, task_text=None, timeout=60):
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    ffmpeg_exe = get_ffmpeg_binary()
    env["FFMPEG_EXE"] = ffmpeg_exe

    # Ensure parent project root and skills/ are in PYTHONPATH so modules can import project files
    existing_pp = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = BASE_DIR + os.pathsep + SKILLS_DIR + (os.pathsep + existing_pp if existing_pp else "")

    if task_text:
        env["TASK_TEXT"] = str(task_text)

    args = [sys.executable, script_path]
    if input_file:
        env["INPUT_FILE"] = os.path.abspath(input_file)
        args.append(os.path.abspath(input_file))
    elif task_text:
        args.append(str(task_text))

    try:
        p = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=BASE_DIR,
            env=env,
            start_new_session=True
        )
        try:
            stdout, stderr = p.communicate(timeout=timeout)
            return p.returncode, (stdout or "").strip(), (stderr or "").strip()
        except subprocess.TimeoutExpired:
            import signal
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            try:
                p.communicate(timeout=2)
            except Exception:
                pass
            return -1, "", f"Превышено максимальное время выполнения скрипта (таймаут {timeout}с)."
    except Exception as e:
        return -1, "", str(e)

def is_pure_text_task(task_text, script_path=None):
    t_lower = (task_text or "").lower()
    text_keywords = [
        "погода", "погоду", "погоде", "погодой", "температур", "градус", "прогноз",
        "тираспол", "курс", "валют", "доллар", "евро", "калькулятор", "посчитай",
        "сколько будет", "переведи", "перевод", "расписание", "вики", "инфо", "новости"
    ]
    if any(k in t_lower for k in text_keywords):
        return True
    if script_path:
        base = os.path.basename(script_path).lower()
        if any(marker in base for marker in ["weather", "calc", "currency", "translate", "text", "info"]):
            return True
def is_media_task(task_text):
    t = (task_text or "").lower()
    media_words = [
        "график", "диаграмм", "плот", "plot", "chart", "рисун", "нарисуй", "начерти",
        "картинк", "пикч", "мем", "мэм", "фото", "qr", "куар", "видео", "клип",
        "аудио", "песн", "трек", "mp3", "mp4", "gif", "гиф", "файл", "pdf", "пдф",
        "excel", "эксель", "таблиц", "сгенерируй изображение", "сгенерируй картинку"
    ]
    return any(w in t for w in media_words)

MEDIA_BLACKLIST_NAMES = {"harvester.png", "tpl_clown.png", "tpl_skeleton.png", "tpl_dr_livesey.png", "test_yandex.jpg", "sine_wave.png"}
MEDIA_BLACKLIST_DIRS = {"meme_templates", "mahoraga_temp", "__pycache__", "fonts"}

def is_blacklisted_media(fp):
    base = os.path.basename(fp).lower()
    if base in MEDIA_BLACKLIST_NAMES:
        return True
    if base.startswith(("tpl_", "harvester", "cached_", "test_", "placeholder_", "default_")):
        return True
    if base.endswith((".ttf", ".otf", ".py", ".pyc", ".json", ".db", ".session", ".txt", ".csv")):
        return True
    for part in fp.replace("\\", "/").split("/"):
        if part.lower() in MEDIA_BLACKLIST_DIRS:
            return True
    return False

def get_all_media_snapshot():
    snapshot = set()
    search_dirs = [MEDIA_DIR, os.path.join(MEDIA_DIR, "videos"), os.path.join(MEDIA_DIR, "music"), os.path.join(EXTENSIONS_DIR, "media"), EXTENSIONS_DIR]
    for d in search_dirs:
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    snapshot.add(os.path.join(root, f))
    return snapshot

def find_newest_media(before_files, stdout="", min_mtime=0, task_text="", script_path=None):
    # 0. Если задача чисто текстовая (погода, расчеты, курсы и т.д.) — медиафайл исключен!
    if is_pure_text_task(task_text, script_path):
        return None

    # 1. Проверяем явный путь в stdout
    if stdout:
        m = re.findall(r"([/\w.-]+\.(?:png|jpg|jpeg|gif|webp|mp4|webm|mov|mp3|ogg|wav|xlsx|pdf))", stdout, re.IGNORECASE)
        for raw_cand in reversed(m):
            test_paths = [raw_cand]
            if not os.path.isabs(raw_cand):
                test_paths.append(os.path.join(BASE_DIR, raw_cand))
            else:
                if raw_cand.startswith("/app/"):
                    test_paths.append(os.path.join(BASE_DIR, raw_cand[len("/app/"):].lstrip("/")))
                test_paths.append(os.path.join(BASE_DIR, raw_cand.lstrip("/")))

            for cand in test_paths:
                if is_blacklisted_media(cand):
                    continue
                if os.path.exists(cand) and os.path.isfile(cand) and os.path.getsize(cand) > 0:
                    # Если путь явно выведен скриптом в stdout — это и есть готовый результат!
                    return os.path.abspath(cand)

    # 2. Если в stdout путь не был напечатан, ищем в папках ТОЛЬКО если задача явно просила файл/медиа
    if not is_media_task(task_text):
        return None

    # 3. Проверяем папки media/ и extensions/
    search_dirs = [MEDIA_DIR, os.path.join(MEDIA_DIR, "videos"), os.path.join(MEDIA_DIR, "music"), os.path.join(EXTENSIONS_DIR, "media")]
    all_candidates = []
    for d in search_dirs:
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".wav", ".xlsx", ".pdf")):
                        fp = os.path.join(root, f)
                        if is_blacklisted_media(fp):
                            continue
                        if os.path.isfile(fp) and os.path.getsize(fp) > 0:
                            mtime = os.path.getmtime(fp)
                            # Либо файл новый, либо был перезаписан скриптом во время работы
                            if fp not in before_files or (min_mtime > 0 and mtime >= min_mtime - 5):
                                all_candidates.append(fp)

    if all_candidates:
        all_candidates.sort(key=os.path.getmtime, reverse=True)
        return all_candidates[0]
    return None

def synthesize_meme_extension_code(task_text, ext_slug, ext_desc):
    clean_theme = task_text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')
    is_crossout = any(w in clean_theme.lower() for w in ["кросаут", "кроссаут", "crossout", "газген", "птур", "ховер", "утюг", "капкан", "мамонт", "скорпион"])
    is_chess = any(w in clean_theme.lower() for w in ["шахмат", "доск", "слон", "ферз", "ладь"])
    if is_chess:
        return f'''# -*- coding: utf-8 -*-
# EXTENSION: {ext_slug} | {ext_desc}
import os, sys
from PIL import Image, ImageDraw, ImageFont

_cur_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_cur_dir)
media_dir = os.path.join(_parent_dir, "media")
os.makedirs(media_dir, exist_ok=True)

width, height = 1080, 1080
img = Image.new("RGB", (width, height), (22, 24, 29))
draw = ImageDraw.Draw(img)

board_size = 720
bx0 = (width - board_size) // 2
by0 = 160
cell_size = board_size // 8

light_color = (240, 217, 181)
dark_color = (181, 136, 99)

for r in range(8):
    for c in range(8):
        col = light_color if (r + c) % 2 == 0 else dark_color
        draw.rectangle([bx0 + c * cell_size, by0 + r * cell_size, bx0 + (c + 1) * cell_size, by0 + (r + 1) * cell_size], fill=col)

font_coords = None
for f_path in [os.path.join(media_dir, "RussoOne-Regular.ttf"), "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
    if os.path.exists(f_path):
        try: font_coords = ImageFont.truetype(f_path, 20); break
        except Exception: pass
if not font_coords: font_coords = ImageFont.load_default()

letters = "ABCDEFGH"
for i in range(8):
    draw.text((bx0 + i * cell_size + cell_size // 2, by0 + board_size + 15), letters[i], font=font_coords, fill="#CCCCCC", anchor="mm")
    draw.text((bx0 - 20, by0 + i * cell_size + cell_size // 2), str(8 - i), font=font_coords, fill="#CCCCCC", anchor="mm")

bishop_cx = bx0 + 0 * cell_size + cell_size // 2
bishop_cy = by0 + 7 * cell_size + cell_size // 2
queen_cx = bx0 + 6 * cell_size + cell_size // 2
queen_cy = by0 + 1 * cell_size + cell_size // 2

# Draw pieces
draw.ellipse([bishop_cx - 24, bishop_cy - 24, bishop_cx + 24, bishop_cy + 24], fill=(30, 30, 30), outline=(0, 255, 120), width=3)
draw.ellipse([queen_cx - 26, queen_cy - 26, queen_cx + 26, queen_cy + 26], fill=(245, 245, 245), outline=(255, 30, 30), width=3)

# Laser line & sniper crosshair
draw.line([(bishop_cx, bishop_cy), (queen_cx, queen_cy)], fill=(255, 40, 40), width=4)
draw.ellipse([queen_cx - 32, queen_cy - 32, queen_cx + 32, queen_cy + 32], outline=(255, 0, 0), width=3)
draw.ellipse([queen_cx - 16, queen_cy - 16, queen_cx + 16, queen_cy + 16], outline=(255, 0, 0), width=2)
draw.line([(queen_cx - 42, queen_cy), (queen_cx + 42, queen_cy)], fill=(255, 0, 0), width=2)
draw.line([(queen_cx, queen_cy - 42), (queen_cx, queen_cy + 42)], fill=(255, 0, 0), width=2)

draw.text((queen_cx, queen_cy - 50), "TARGET LOCKED: ФЕРЗЬ", font=font_coords, fill="#FF4444", anchor="mm")
draw.text((bishop_cx + 35, bishop_cy + 5), "СЛОН СО СНАЙПЕРКОЙ", font=font_coords, fill="#00FF88", anchor="lm")

font_title = None
for f_path in [os.path.join(media_dir, "RussoOne-Regular.ttf"), "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
    if os.path.exists(f_path):
        try: font_title = ImageFont.truetype(f_path, 32); break
        except Exception: pass
if not font_title: font_title = ImageFont.load_default()

draw.rectangle([(40, 30), (width - 40, 125)], fill=(30, 35, 45), outline=(240, 160, 20), width=2)
draw.text((width // 2, 65), "ШАХ И МАТ? НЕ ТАК БЫСТРО...", font=font_title, fill="#FFCC00", anchor="mm")
draw.text((width // 2, 100), "Когда белые орут «Шах и мат!», но не заметили слона на диагонали", font=font_coords, fill="#E0E0E0", anchor="mm")

draw.rectangle([(40, height - 120), (width - 40, height - 35)], fill=(30, 35, 45), outline=(70, 80, 100), width=2)
draw.text((width // 2, height - 78), "Слон на A1 со снайперкой держит диагональ: «Минус ферзь!» ♟️🎯", font=font_title, fill="#FFFFFF", anchor="mm")

out_path = os.path.join(media_dir, "chess_sniper_bishop.png")
img.save(out_path, "PNG")
print(out_path)
print("Шахматная доска готова! Слон в засаде держит вражеского ферзя на прицеле со снайперкой ♟️🎯")
'''
    elif is_crossout:
        return f'''# -*- coding: utf-8 -*-
# EXTENSION: {ext_slug} | {ext_desc}
import os
import sys

_cur_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_cur_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

from meme_generator import generate_crossout_meme

theme = "{clean_theme}"
meme_file = generate_crossout_meme(theme=theme, allow_repeat=False)
if meme_file and os.path.exists(meme_file):
    print(meme_file)
    print("Мем успешно сгенерирован по теме:", theme)
else:
    sys.exit(1)
'''
    else:
        return f'''# -*- coding: utf-8 -*-
# EXTENSION: {ext_slug} | {ext_desc}
import os
import sys
from PIL import Image, ImageDraw, ImageFont

_cur_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_cur_dir)
media_dir = os.path.join(_parent_dir, "media")
os.makedirs(media_dir, exist_ok=True)

theme = "{clean_theme}"

def get_font(size):
    candidates = [
        os.path.join(media_dir, "RussoOne-Regular.ttf"),
        os.path.join(media_dir, "Montserrat.ttf"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()

width, height = 1000, 1000
img = Image.new("RGB", (width, height), (18, 20, 26))
draw = ImageDraw.Draw(img)
draw.rectangle([(40, 40), (width - 40, height - 40)], fill=(28, 32, 42), outline=(70, 80, 100), width=3)

font_title = get_font(40)
font_body = get_font(28)

draw.text((width // 2, 100), "МЕМ // ЮМОР", font=font_title, fill="#FFCC00", anchor="mm")

words = theme.split()
lines = []
curr = []
for w in words:
    curr.append(w)
    if len(" ".join(curr)) > 35:
        lines.append(" ".join(curr[:-1]))
        curr = [w]
if curr:
    lines.append(" ".join(curr))

y = 350
for l in lines:
    draw.text((width // 2, y), l, font=font_body, fill="#FFFFFF", anchor="mm")
    y += 45

out_path = os.path.join(media_dir, f"meme_{abs(hash(theme)) % 100000}.png")
img.save(out_path, "PNG")
print(out_path)
print("Держи мем по твоему запросу! 🔥")
'''

def execute_autonomous_task(task_text, sender_name, photo_path=None, ask_ai_fn=None, sender_key=None, retry_context=None):
    """
    Универсальный автономный саморасширяющийся исполнитель Antigravity:
    1. Проверяет реестр существующих дополнений.
    2. Если дополнения еще нет — генерирует новый автономный модуль под задачу.
    3. Авто-устанавливает недостающие внешние библиотеки.
    4. Запускает код, при ошибках запускает самоотладку (self-healing).
    5. Регистрирует новое дополнение в extensions/registry.json для постоянного использования.
    6. Возвращает созданный файл и подробный отчет.
    """
    proposal_user = sender_key or ("owner" if sender_name in ["Миша", "erokat", "Ты (Владелец)"] else str(sender_name))

    # 1. Проверяем, есть ли уже готовое дополнение для этой задачи (не требует AI!)
    existing_script, ext_info = find_existing_extension(task_text)
    if existing_script:
        ext_produces_media = ext_info.get("produces_media", True)
        before_files = get_all_media_snapshot() if ext_produces_media else set()
        start_time = time.time()
        print(f"[DYNAMIC AGENT] Reusing existing extension: {existing_script}")
        code_rc, stdout, stderr = run_script(existing_script, input_file=photo_path, task_text=task_text)
        if code_rc == 0:
            if not ext_produces_media or is_pure_text_task(task_text, existing_script):
                new_media = None
            else:
                new_media = find_newest_media(before_files, stdout=stdout, min_mtime=start_time, task_text=task_text, script_path=existing_script)

            if new_media and os.path.exists(new_media):
                clean_lines = []
                if stdout:
                    for line in stdout.splitlines():
                        line_str = line.strip()
                        if not line_str or line_str.startswith("/") or line_str.startswith("media/") or line_str.endswith((".png", ".jpg", ".mp4", ".mp3", ".xlsx", ".pdf", ".gif")):
                            continue
                        if any(tech_w in line_str.lower() for tech_w in ["traceback", "module", "saved to", "successfully", "extension", "/app/"]):
                            continue
                        clean_lines.append(line_str)

                natural_caption = " ".join(clean_lines).strip() if (clean_lines and len(" ".join(clean_lines)) < 160) else ""
                if not natural_caption:
                    natural_caption = f"Готово, {sender_name}! Лови результат 🔥"
                return natural_caption, new_media

            if any(marker in stdout for marker in ["📍", "🌡️", "📊", "☀️", "🌤️", "☁️"]):
                report = stdout
            else:
                report = (
                    f"⚡ **Использовано дополнение к боту:** `{os.path.basename(existing_script)}`\n"
                    f"_{ext_info.get('description', 'Выполнение сохраненной функции')}_\n\n"
                )
                if stdout:
                    report += f"📊 **Результат:**\n```\n{stdout[:2000]}\n```\n"
            return report, None

        elif ask_ai_fn and os.path.exists(existing_script):
            # Attempt self-healing directly on the existing failing skill!
            print(f"[DYNAMIC AGENT] Existing extension {existing_script} failed (rc={code_rc}). Initiating self-healing...")
            script_path = existing_script
            script_filename = os.path.basename(existing_script)
            skill_name = ext_info.get("skill_name") or os.path.splitext(script_filename)[0]
            skill_desc = ext_info.get("description") or f"Навык {skill_name}"
            triggers = ext_info.get("triggers") or []
            requirements = ext_info.get("requirements") or []
            try:
                with open(existing_script, "r", encoding="utf-8") as f:
                    code = f.read()
            except Exception:
                code = None

            if code:
                if "ModuleNotFoundError" in stderr or "No module named" in stderr:
                    installed = auto_install_missing_packages(stderr)
                    if installed:
                        code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text, timeout=60)

                if code_rc != 0:
                    for attempt in range(1, 4):
                        print(f"[DYNAMIC SKILL ENGINE] Self-healing attempt {attempt}/3 for existing skill {skill_name} (rc={code_rc})...")
                        err_details = stderr if stderr else (stdout if stdout else f"Скрипт завершился с кодом ошибки {code_rc}")
                        fix_prompt = (
                            f"Скрипт навыка '{skill_name}' для задачи «{task_text}» упал с кодом {code_rc}.\n"
                            f"Ошибка / Traceback:\n```\n{err_details[:1500]}\n```\n\n"
                            f"Исходный код:\n```python\n{code}\n```\n\n"
                            "Инструкции по исправлению:\n"
                            "1. Проанализируй причину ошибки и устрани её.\n"
                            "2. Сохрани комментарии с метаданными (# SKILL_NAME, # DESCRIPTION, # TRIGGERS, # REQUIREMENTS).\n"
                            "3. Не изменяй файлы системного ядра бота.\n"
                            "4. Верни исправленный, полностью работающий Python-код строго внутри ```python ... ```."
                        )
                        fixed_reply = ask_ai_fn(fix_prompt)
                        fixed_code = extract_python_code(fixed_reply)
                        if fixed_code and is_safe_skill_path(script_path):
                            if not fixed_code.startswith("# -*- coding: utf-8 -*-"):
                                fixed_code = "# -*- coding: utf-8 -*-\n" + fixed_code
                            with open(script_path, "w", encoding="utf-8") as f:
                                f.write(fixed_code)
                            code = fixed_code
                            code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text, timeout=60)
                            if code_rc != 0 and ("ModuleNotFoundError" in stderr or "No module named" in stderr):
                                if auto_install_missing_packages(stderr):
                                    code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text, timeout=60)
                            if code_rc == 0:
                                print(f"[DYNAMIC SKILL ENGINE] Self-healing succeeded on attempt {attempt}/3 for existing skill!")
                                try:
                                    from db import parse_skill_metadata_from_code
                                    s_name_upd, s_desc_upd, s_trig_upd, s_req_upd = parse_skill_metadata_from_code(code, fallback_name=skill_name, fallback_desc=skill_desc)
                                    skill_name = s_name_upd
                                    skill_desc = s_desc_upd
                                    if s_trig_upd:
                                        triggers = s_trig_upd
                                    if s_req_upd:
                                        requirements = s_req_upd
                                except Exception:
                                    pass
                                break

                if code_rc == 0:
                    try:
                        from db import save_dynamic_skill
                        save_dynamic_skill(
                            skill_name=skill_name,
                            file_path=script_path,
                            triggers=triggers,
                            description=skill_desc,
                            requirements=requirements,
                            code=code
                        )
                    except Exception as dbe:
                        print(f"[DYNAMIC SKILL ENGINE] Error saving healed skill to SQLite: {dbe}")

                    try:
                        from gdrive import upload_file_to_drive
                        upload_file_to_drive(script_path, folder_type="skills")
                    except Exception as ge:
                        print(f"[DYNAMIC SKILL ENGINE] GDrive backup notice: {ge}")

                    try:
                        from github_sync import push_skill_to_github
                        push_skill_to_github(skill_name=skill_name, file_path=script_path, code=code)
                    except Exception as ghe:
                        print(f"[DYNAMIC SKILL ENGINE] GitHub push notice: {ghe}")

                    new_media = None
                    if ext_produces_media:
                        new_media = find_newest_media(before_files, stdout=stdout, min_mtime=start_time, task_text=task_text, script_path=existing_script)

                    register_extension(skill_name, script_filename, skill_desc, triggers[:7], produces_media=bool(new_media))

                    if new_media and os.path.exists(new_media):
                        return f"Готово, {sender_name}! Исправил и выполнил 🔥", new_media

                    clean_out = "\n".join([l for l in stdout.splitlines() if not l.startswith("/") and not l.endswith((".png", ".jpg", ".mp4", ".mp3"))])
                    return f"⚡ **Навык `{script_filename}` успешно самоисправлен:**\n\n```\n{clean_out[:2000]}\n```", None

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

    prev_context = ""
    if retry_context and isinstance(retry_context, dict):
        last_e = retry_context.get("last_err", "")
        if last_e:
            prev_context = f"\nВНИМАНИЕ: Предыдущая попытка упала с ошибкой: {last_e}. Обязательно учти и исправь это!\n"

    # 2. Генерируем новое дополнение с нуля
    # 2. Генерируем новый динамический модуль с нуля через Gemini
    prompt = (
        f"Ты — автономный генератор Python 3 скриптов и медиа (Dynamic Skill Engine) для Telegram-бота.\n"
        f"Пользователь {sender_name} просит выполнить задачу: «{task_text}».\n"
        f"{file_context}{prev_context}\n"
        "ВАЖНЕЙШЕЕ ПРАВИЛО ТЕМАТИКИ (СТРОЖАЙШИЙ ЗАПРЕТ НА ЛИШНИЙ КРОССАУТ):\n"
        "1. Создавай изображение/мем/графику/скрипт СТРОГО по теме, которую запросил пользователь!\n"
        "2. Если запрос про шахматы — делай ТОЛЬКО шахматы (никакого Crossout, никаких скорпионов, кабин и пушек, если о них прямо не просили)!\n"
        "3. Если запрос про Rain World, котиков, учёбу, CS, Dota, жизненные ситуации, аниме, сессию, программирование — делай СТРОГО по этой теме!\n"
        "4. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО приплетать элементы Crossout (Газген, ПТУР, Капканы, Пустоши, Скорпион, кабины, ховеры), если в тексте задачи пользователь САМ прямо не упомянул игру Crossout или её детали!\n"
        "5. Игру Crossout используй ТОЛЬКО тогда, когда пользователь САМ прямо попросил Crossout (или явно упомянул крафты, оружие и детали из Crossout).\n\n"
        "СПЕЦИФИКАЦИЯ ВНУТРЕННЕЙ АРХИТЕКТУРЫ И ОКРУЖЕНИЯ:\n"
        "1. Корень проекта находится в PYTHONPATH. Тебе доступны модули:\n"
        "   - `from db import get_db, get_kv, set_kv` — чтение и запись в базу данных SQLite.\n"
        "   - `from media_finder import find_and_download_image` — поиск и скачивание артов/изображений.\n"
        "2. Рабочие директории и генерация медиа:\n"
        "   - `./media/` — сохранение любых сгенерированных медиафайлов (картинки, графики, qr, видео, аудио).\n"
        "   - ДЛЯ ГЕНЕРАЦИИ КАРТИНОК, ГРАФИКИ, МЕМОВ, АРТОВ И СХЕМ: используй библиотеку `PIL` (`Pillow`) или `matplotlib`. Шрифты лежат в `./media/` (`RussoOne-Regular.ttf`, `Montserrat.ttf`, `Comfortaa.ttf`, `Anton.ttf`). Рисуй все запрошенные пользователем сцены, детали, персонажей и надписи качественно! Готовый файл сохраняй в `./media/<filename>.png` и обязательно печатай путь в stdout: `print(out_path)`.\n"
        "   - ЕСЛИ ПРИКРЕПЛЕН ВХОДНОЙ ФАЙЛ (INPUT_FILE) И ЗАПРОШЕН ФОТОМОНТАЖ / РЕДАКТИРОВАНИЕ (замена фона, вставка объектов из интернета, коллаж, добавление деталей): открой `INPUT_FILE` через Image.open(), скачай нужные картинки (urllib / requests) или возьми из `./media/`, вырежи, наложи слои, сохрани результат в `./media/<filename>.jpg` и напечатай путь в stdout: `print(out_path)`.\n"
        "3. Входные аргументы скрипта:\n"
        "   - Текст запроса: `os.environ.get('TASK_TEXT')` или `sys.argv[1]`.\n"
        "   - Входной файл (если прикреплен): `os.environ.get('INPUT_FILE')`.\n"
        "   - Исполняемый ffmpeg: `os.environ.get('FFMPEG_EXE', 'ffmpeg')`.\n"
        "4. Библиотеки и зависимости:\n"
        "   - Если нужны внешние пакеты (requests, beautifulsoup4, pillow, openpyxl, pandas, matplotlib, qrcode, pydub), свободно импортируй их!\n"
        "   - Движок автоматически установит недостающие пакеты через pip.\n"
        "5. ЗАЩИТА СИСТЕМНОГО ЯДРА (СТРОГИЙ ЗАПРЕТ):\n"
        "   Никогда не изменяй и не перезаписывай файлы ядра бота:\n"
        "   keep_alive.py, wait_for_yarik.py, db.py, send.py, session.session, crossout_session.session, config.py.\n"
        "6. Метаданные навыка в начале файла:\n"
        "   # SKILL_NAME: <slug_латиницей>\n"
        "   # DESCRIPTION: <Краткое описание навыка>\n"
        "   # TRIGGERS: <полная_фраза_триггера_1>, <полная_фраза_триггера_2>\n"
        "   (ЗАПРЕЩЕНО указывать в триггерах одиночные общие слова вроде 'шахматы', 'эксперт', 'мем' — только полные фразы!)\n"
        "   # REQUIREMENTS: <пакет1>, <пакет2>\n\n"
        "Напиши надежный, готовый к запуску Python 3 код.\n"
        "Ответ должен содержать код строго внутри блока ```python ... ```."
    )

    ai_reply = ask_ai_fn(prompt, photo_path=photo_path)
    if not ai_reply:
        if is_meme_or_media_request(task_text):
            print("[DYNAMIC SKILL ENGINE] AI generation timed out for media/meme task. Falling back to guaranteed synthesized extension immediately!")
            ai_reply = None
        else:
            # Попытка 2: компактный промпт для не-медиа задач для защиты от таймаута
            print("[DYNAMIC SKILL ENGINE] Prompt 1 timed out or failed. Retrying with compact prompt...")
            compact_prompt = (
                f"Напиши надежный автономный Python 3 скрипт для задачи: «{task_text}».\n"
                f"# SKILL_NAME: task_exec\n# DESCRIPTION: {task_text[:120]}\n"
                "ВАЖНОЕ ПРАВИЛО: Делай СТРОГО по теме задачи пользователя! НЕ приплетай Crossout, если о нем прямо не просили!\n"
                "Если требуется графика/картинка/мем или фотомонтаж входного файла INPUT_FILE — используй Pillow (PIL) и сохрани результат в media/, напечатав путь в stdout.\n"
                "Код верни строго внутри ```python ... ``` без лишних рассуждений."
            )
            ai_reply = ask_ai_fn(compact_prompt, photo_path=photo_path)

    code = extract_python_code(ai_reply) if ai_reply else None

    # Если AI не смог сгенерировать код
    if not code:
        if is_meme_or_media_request(task_text):
            ext_slug = "skill_meme_" + hashlib.md5(task_text.encode()).hexdigest()[:6]
            ext_desc = f"Генератор мема: {task_text[:120]}"
            code = synthesize_meme_extension_code(task_text, ext_slug, ext_desc)
            print(f"[DYNAMIC SKILL ENGINE] Synthesized guaranteed meme extension code for: {task_text}")
        else:
            set_pending_proposal(proposal_user, task_text, last_err="Таймаут AI-генератора кода")
            return (
                f"⚠️ {sender_name}, произошла заминка: AI-движок не успел сформировать код дополнения (таймаут генерации).\n\n"
                f"Я сохранил задачу «{task_text}». Могу исправить и доделать этот модуль генерации!\n"
                f"Напиши «доделай модуль» или уточни требования 👍"
            ), None

    # Извлекаем метаданные навыка
    slug_match = re.search(r"#\s*(?:SKILL_NAME|EXTENSION):\s*([a-zA-Z0-9_-]+)", code)
    if slug_match:
        skill_name = slug_match.group(1).strip()
    else:
        skill_name = "skill_" + hashlib.md5(task_text.encode()).hexdigest()[:6]

    desc_match = re.search(r"#\s*DESCRIPTION:\s*(.+)", code)
    if desc_match:
        skill_desc = desc_match.group(1).strip()
    else:
        slug_pipe = re.search(r"#\s*(?:SKILL_NAME|EXTENSION):\s*[a-zA-Z0-9_-]+\s*\|\s*(.+)", code)
        skill_desc = slug_pipe.group(1).strip() if slug_pipe else f"Навык: {task_text[:60]}"

    trig_match = re.search(r"#\s*TRIGGERS:\s*(.+)", code)
    if trig_match:
        triggers = [t.strip().lower() for t in trig_match.group(1).split(",") if t.strip()]
    else:
        stopwords = {"бот", "пожалуйста", "скинь", "сделай", "напиши", "сгенерируй", "создай", "дополнение", "навык", "чтобы", "можешь", "умеешь", "давай", "хочу"}
        triggers = [w for w in re.findall(r"\b[а-яa-z]{4,}\b", task_text.lower()) if w not in stopwords]
        for part in re.split(r"[_-]", skill_name):
            if len(part) >= 3 and part.lower() not in triggers:
                triggers.append(part.lower())

    req_match = re.search(r"#\s*REQUIREMENTS:\s*(.+)", code)
    requirements = [r.strip() for r in req_match.group(1).split(",") if r.strip()] if req_match else []

    script_filename = f"{skill_name}.py"
    script_path = os.path.join(SKILLS_DIR, script_filename)

    # Защита системного ядра: проверяем допустимость пути
    if not is_safe_skill_path(script_path):
        return f"⚠️ Ошибка безопасности: недопустимый путь для навыка `{script_path}`.", None

    if not code.startswith("# -*- coding: utf-8 -*-"):
        code = "# -*- coding: utf-8 -*-\n" + code

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code)

    before_files = get_all_media_snapshot()
    start_time = time.time()

    # Первый запуск (таймаут 60 секунд)
    code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text, timeout=60)

    # Если не хватило модуля — авто-устанавливаем через pip (таймаут 45с) и перезапускаем
    if code_rc != 0 and ("ModuleNotFoundError" in stderr or "No module named" in stderr):
        installed = auto_install_missing_packages(stderr)
        if installed:
            code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text, timeout=60)

    # Self-healing / самоотладка при ошибках (до 3 итераций!)
    if code_rc != 0:
        for attempt in range(1, 4):
            print(f"[DYNAMIC SKILL ENGINE] Self-healing attempt {attempt}/3 for {skill_name} (rc={code_rc})...")
            err_details = stderr if stderr else (stdout if stdout else f"Скрипт завершился с кодом ошибки {code_rc}")
            fix_prompt = (
                f"Скрипт навыка '{skill_name}' для задачи «{task_text}» упал с кодом {code_rc}.\n"
                f"Ошибка / Traceback:\n```\n{err_details[:1500]}\n```\n\n"
                f"Исходный код:\n```python\n{code}\n```\n\n"
                "Инструкции по исправлению:\n"
                "1. Проанализируй причину ошибки и устрани её.\n"
                "2. Сохрани комментарии с метаданными (# SKILL_NAME, # DESCRIPTION, # TRIGGERS, # REQUIREMENTS).\n"
                "3. Не изменяй файлы системного ядра бота.\n"
                "4. Верни исправленный, полностью работающий Python-код строго внутри ```python ... ```."
            )
            fixed_reply = ask_ai_fn(fix_prompt)
            fixed_code = extract_python_code(fixed_reply)
            if fixed_code and is_safe_skill_path(script_path):
                if not fixed_code.startswith("# -*- coding: utf-8 -*-"):
                    fixed_code = "# -*- coding: utf-8 -*-\n" + fixed_code
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                code = fixed_code
                code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text, timeout=60)
                if code_rc != 0 and ("ModuleNotFoundError" in stderr or "No module named" in stderr):
                    if auto_install_missing_packages(stderr):
                        code_rc, stdout, stderr = run_script(script_path, input_file=photo_path, task_text=task_text, timeout=60)
                if code_rc == 0:
                    print(f"[DYNAMIC SKILL ENGINE] Self-healing succeeded on attempt {attempt}/3!")
                    try:
                        from db import parse_skill_metadata_from_code
                        s_name_upd, s_desc_upd, s_trig_upd, s_req_upd = parse_skill_metadata_from_code(code, fallback_name=skill_name, fallback_desc=skill_desc)
                        skill_name = s_name_upd
                        skill_desc = s_desc_upd
                        if s_trig_upd:
                            triggers = s_trig_upd
                        if s_req_upd:
                            requirements = s_req_upd
                    except Exception:
                        pass
                    break

    # Ищем созданный медиафайл (если задача не чисто текстовая)
    new_media = find_newest_media(before_files, stdout=stdout, min_mtime=start_time, task_text=task_text, script_path=script_path)

    # Если скрипт успешно отработал: персистентно сохраняем в SQLite dynamic_skills и GitHub ТОЛЬКО постоянные навыки!
    is_one_off = is_one_off_creative_task(task_text)
    if code_rc == 0:
        if not is_one_off:
            try:
                from db import save_dynamic_skill
                save_dynamic_skill(
                    skill_name=skill_name,
                    file_path=script_path,
                    triggers=triggers,
                    description=skill_desc,
                    requirements=requirements,
                    code=code
                )
                print(f"[DYNAMIC SKILL ENGINE] Persisted skill '{skill_name}' in SQLite dynamic_skills table.")
            except Exception as dbe:
                print(f"[DYNAMIC SKILL ENGINE] Error saving skill to SQLite: {dbe}")

            try:
                from gdrive import upload_file_to_drive
                upload_file_to_drive(script_path, folder_type="skills")
            except Exception as ge:
                print(f"[DYNAMIC SKILL ENGINE] GDrive backup notice: {ge}")

            try:
                from github_sync import push_skill_to_github
                push_skill_to_github(skill_name=skill_name, file_path=script_path, code=code)
            except Exception as ghe:
                print(f"[DYNAMIC SKILL ENGINE] GitHub push notice: {ghe}")

            register_extension(skill_name, script_filename, skill_desc, triggers[:7], produces_media=bool(new_media))
            print(f"[DYNAMIC SKILL ENGINE] Successfully registered dynamic skill: {skill_name} (triggers: {triggers[:7]}, produces_media={bool(new_media)})")
        else:
            print(f"[DYNAMIC SKILL ENGINE] One-off creative generation completed. Skipping persistent skill registration.")
            if os.path.exists(script_path):
                try:
                    os.remove(script_path)
                except Exception:
                    pass

    # Формируем естественный, живой ответ пользователю без технического спама
    if new_media and os.path.exists(new_media):
        clean_lines = []
        if stdout:
            for line in stdout.splitlines():
                line_str = line.strip()
                if not line_str or line_str.startswith("/") or line_str.startswith("media/") or line_str.endswith((".png", ".jpg", ".mp4", ".mp3", ".xlsx", ".pdf", ".gif")):
                    continue
                if any(tech_w in line_str.lower() for tech_w in ["traceback", "module", "saved to", "successfully", "extension"]):
                    continue
                clean_lines.append(line_str)

        natural_caption = " ".join(clean_lines).strip() if (clean_lines and len(" ".join(clean_lines)) < 160) else ""

        if not natural_caption:
            clean_topic = re.sub(
                r"(?i)^(?:бот[,\s]*)*(?:пожалуйста[,\s]*)*(?:создай|сделай|запили|скинь|сгенерируй)?\s*(?:мем|мемасик|мемчик)?\s*(?:по|про|о)?\s*",
                "", task_text
            ).strip()
            if any(w in task_text.lower() for w in ["мем", "мэм", "мемасик", "прикол"]):
                if clean_topic:
                    natural_caption = f"Держи свежий мем по {clean_topic}, {sender_name}! 🔥"
                else:
                    natural_caption = f"Лови свежий мем, {sender_name}! 🔥"
            else:
                natural_caption = f"Готово, {sender_name}! Лови результат 🔥"

        return natural_caption, new_media

    # Если чисто текстовый результат
    if stdout and code_rc == 0 and not is_meme_or_media_request(task_text):
        clean_out = "\n".join([line for line in stdout.splitlines() if not line.startswith("/") and not line.endswith((".png", ".jpg", ".mp4", ".mp3", ".xlsx", ".pdf"))])
        if clean_out.strip():
            return clean_out.strip(), None

    if code_rc == 0 and not is_meme_or_media_request(task_text):
        return f"Готово, {sender_name}! Всё четко сработало 👍", None

    # Если скрипт успешно завершился, но медиафайл не был найден (для медиа-запроса)
    if code_rc == 0 and is_meme_or_media_request(task_text) and not new_media:
        try:
            from meme_generator import generate_crossout_meme
            fallback_meme = generate_crossout_meme(theme=task_text, recipient="owner" if proposal_user == "owner" else "yarik")
            if fallback_meme and os.path.exists(fallback_meme):
                return f"Сгенерировал свежий мем по теме «{task_text}», {sender_name}! 🔥", fallback_meme
        except Exception as e:
            print(f"[DYNAMIC SKILL ENGINE] Fallback meme generation failed: {e}")

    # Обработка ошибки выполнения скрипта: сообщаем суть ошибки и предлагаем доделать модуль
    err_lines = [l.strip() for l in (stderr or "").strip().splitlines() if l.strip()]
    last_err = err_lines[-1] if err_lines else f"код {code_rc}"
    set_pending_proposal(proposal_user, task_text, last_err=last_err, script_path=script_path)

    if is_meme_or_media_request(task_text):
        try:
            from meme_generator import generate_crossout_meme
            fallback_meme = generate_crossout_meme(theme=task_text, recipient="owner" if proposal_user == "owner" else "yarik")
            if fallback_meme and os.path.exists(fallback_meme):
                report = (
                    f"⚠️ Модуль генерации завершился с ошибкой: `{last_err}`.\n"
                    f"Я попытался исправить код автоматически (3 попытки self-healing), а пока держи готовый мем через штатный генератор! 🔥\n\n"
                    f"💡 Хочешь, чтобы я доделал и отладил этот модуль? Напиши «доделай модуль»!"
                )
                return report, fallback_meme
        except Exception as e:
            print(f"[DYNAMIC SKILL ENGINE] Fallback meme generation failed after script error: {e}")

    return (
        f"⚠️ Ошибка выполнения модуля для «{task_text}»:\n`{last_err}`\n\n"
        f"Я попытался исправить скрипт через самоотладку (3 итерации self-healing), но ошибка осталась.\n"
        f"Предлагаю доделать этот модуль генерации! Напиши «доделай модуль» или «исправь» 👍"
    ), None

def _normalize_proposal_keys(user_id):
    uid_str = str(user_id).strip().lower()
    if uid_str in ["owner", "миша", "миха", "мишан", "5067025016", "erokat", "ты (владелец)"]:
        return ["owner", "Миша", "5067025016"]
    if uid_str in ["yarik", "ярик", "6271387044"]:
        return ["yarik", "Ярик", "6271387044"]
    return [str(user_id)]

def set_pending_proposal(user_id, task_text, bot_msg_id=None, last_err=None, script_path=None, proposal_msg_id=None):
    from db import set_kv
    data = {
        "task_text": task_text,
        "bot_msg_id": bot_msg_id,
        "proposal_msg_id": proposal_msg_id,
        "last_err": last_err,
        "script_path": script_path,
        "created_at": time.time()
    }
    dumped = json.dumps(data, ensure_ascii=False)
    for k in _normalize_proposal_keys(user_id):
        set_kv(f"pending_ext_proposal_{k}", dumped)
        if proposal_msg_id:
            set_kv(f"proposal_msg_id_{k}", str(proposal_msg_id))

def get_pending_proposal(user_id):
    from db import get_kv
    for k in _normalize_proposal_keys(user_id):
        raw = get_kv(f"pending_ext_proposal_{k}")
        if raw:
            try:
                data = json.loads(raw)
                # 15 minutes TTL
                if time.time() - data.get("created_at", 0) > 900:
                    clear_pending_proposal(user_id)
                    return None
                if not data.get("proposal_msg_id"):
                    prop_id_str = get_kv(f"proposal_msg_id_{k}")
                    if prop_id_str and prop_id_str.isdigit():
                        data["proposal_msg_id"] = int(prop_id_str)
                return data
            except Exception:
                continue
    return None

def clear_pending_proposal(user_id):
    from db import set_kv
    for k in _normalize_proposal_keys(user_id):
        set_kv(f"pending_ext_proposal_{k}", "")
        set_kv(f"proposal_msg_id_{k}", "")

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

def run_autonomous_task_async(
    task_text,
    sender_name,
    photo_path=None,
    ask_ai_fn=None,
    sender_key=None,
    retry_context=None,
    recipient="owner",
    reply_to_msg_id=None,
    ack_msg_id=None,
    is_owner_sender=False
):
    """
    Executes an autonomous task or dynamic skill in a non-blocking background thread.
    The caller (keep_alive loop) returns immediately and does not hang.
    When complete, the background worker sends the result via send.py and cleans up ack_msg_id.
    """
    import threading

    def _worker():
        try:
            print(f"[DYNAMIC ASYNC WORKER] Starting task for {sender_name}: {task_text}")
            res_text, res_media = execute_autonomous_task(
                task_text,
                sender_name=sender_name,
                photo_path=photo_path,
                ask_ai_fn=ask_ai_fn,
                sender_key=sender_key,
                retry_context=retry_context
            )
            print(f"[DYNAMIC ASYNC WORKER] Finished task for {sender_name}. Delivering result...")
            send_cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "send.py"),
                "--to", recipient
            ]
            if not is_owner_sender:
                send_cmd.append("--no-copy")
            if reply_to_msg_id:
                send_cmd.extend(["--reply-to", str(reply_to_msg_id)])

            if res_media and os.path.exists(res_media):
                send_cmd.extend(["--photo", res_media, "--text", res_text])
            else:
                send_cmd.extend(["--text", res_text])

            subprocess.run(send_cmd)

            if ack_msg_id:
                try:
                    del_cmd = [sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", recipient, "--delete", str(ack_msg_id)]
                    subprocess.run(del_cmd)
                except Exception:
                    pass

        except Exception as e:
            traceback.print_exc()
            err_msg = f"⚠️ Ошибка выполнения автономного навыка: {e}"
            subprocess.run([sys.executable, os.path.join(BASE_DIR, "send.py"), "--to", recipient, "--text", err_msg])

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
