import os
import sys
import re
import time
import json
import hashlib
import subprocess
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENSIONS_DIR = os.path.join(BASE_DIR, "extensions")
MEDIA_DIR = os.path.join(BASE_DIR, "media")

os.makedirs(EXTENSIONS_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

def is_autonomous_task(text):
    if not text:
        return False
    t = text.lower().strip()
    
    triggers = [
        "напиши код", "напиши скрипт", "напиши программу", "создай файл",
        "сгенерируй файл", "добавь функцию", "добавь возможность", "добавь команду",
        "сделай функцию", "добавь себе", "научись", "сделай скрипт", "сделай генератор",
        "рассчитай", "смоделируй", "нарисуй график", "создай график", "сделай парсер",
        "напиши парсер", "симулятор", "калькулятор", "посчитай сложн", "выполни код",
        "запусти код", "сгенерируй код", "автономн", "сделай фичу", "добавь фичу"
    ]
    return any(trig in t for trig in triggers)

def extract_python_code(response_text):
    if not response_text:
        return None
    pattern = r"```(?:python|py)?\s*([\s\S]*?)\s*```"
    matches = re.findall(pattern, response_text, re.IGNORECASE)
    if matches:
        return matches[0].strip()
    return None

def run_script(script_path, timeout=35):
    try:
        res = subprocess.run(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            cwd=BASE_DIR
        )
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Превышено максимальное время выполнения скрипта (таймаут 35с)."
    except Exception as e:
        return -1, "", str(e)

def find_newest_media(before_files, stdout=""):
    # 1. Check if stdout contains an explicit file path
    if stdout:
        m = re.findall(r"([/\w.-]+\.(?:png|jpg|jpeg|gif|webp|mp4|webm|csv|txt|pdf))", stdout, re.IGNORECASE)
        for cand in reversed(m):
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
            full_cand = os.path.join(BASE_DIR, cand.lstrip("/"))
            if os.path.exists(full_cand) and os.path.isfile(full_cand):
                return full_cand

    # 2. Check MEDIA_DIR and EXTENSIONS_DIR for newly created files
    search_dirs = [MEDIA_DIR, os.path.join(EXTENSIONS_DIR, "media"), EXTENSIONS_DIR]
    all_candidates = []
    for d in search_dirs:
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".csv", ".txt", ".pdf")):
                        fp = os.path.join(root, f)
                        if os.path.isfile(fp) and (time.time() - os.path.getmtime(fp) < 45):
                            all_candidates.append(fp)

    if all_candidates:
        all_candidates.sort(key=os.path.getmtime, reverse=True)
        return all_candidates[0]
    return None

def execute_autonomous_task(task_text, sender_name, photo_path=None, ask_ai_fn=None):
    """
    Автономный исполнитель задач Antigravity:
    1. Просит AI сгенерировать скрипт/файл для решения задачи.
    2. Сохраняет и выполняет сгенерированный код.
    3. При ошибке делает автоматический self-healing (самоотладку).
    4. Возвращает текстовый отчет и путь к созданному файлу/медиа (если создан).
    """
    if not ask_ai_fn:
        return "Модуль AI недоступен.", None

    prompt = (
        f"Ты — автономный саморасширяющийся AI-агент в Telegram (построен на Google Antigravity).\n"
        f"Пользователь {sender_name} просит выполнить задачу: «{task_text}».\n\n"
        "Ты можешь САМ написать Python-код, сохранить его и выполнить прямо сейчас в рабочей среде.\n"
        "У тебя есть доступ к стандартным библиотекам (math, random, json, re, datetime, urllib, requests, PIL/Pillow, opencv).\n"
        "Рабочая папка скрипта: BASE_DIR (переменная BASE_DIR или текущая папка).\n"
        "Если создаешь медиафайл (картинка, график, файл), сохраняй его в папку `media/` (например, `os.path.join(os.path.dirname(__file__), '..', 'media', 'result.png')`).\n"
        "Результаты выводи через `print(...)`.\n\n"
        "Формат твоего ответа:\n"
        "1. Краткое пояснение (1 предложение), что делает этот скрипт.\n"
        "2. Блок исполняемого кода Python строго внутри тройных кавычек:\n"
        "```python\n"
        "# Твой рабочий, полностью готовый код\n"
        "```\n"
        "Пиши надежный код без внешних неизвестных зависимостей."
    )

    ai_reply = ask_ai_fn(prompt, photo_path=photo_path)
    if not ai_reply:
        return f"{sender_name}, не удалось сгенерировать скрипт для этой задачи. Попробуй уточнить требования!", None

    code = extract_python_code(ai_reply)
    if not code:
        # Если AI решил ответить чисто текстом без кода
        return ai_reply, None

    # Сохраняем код в папку extensions
    script_id = hashlib.md5(f"{task_text}_{time.time()}".encode()).hexdigest()[:8]
    script_filename = f"auto_{script_id}.py"
    script_path = os.path.join(EXTENSIONS_DIR, script_filename)

    with open(script_path, "w", encoding="utf-8") as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write(f"# Auto-generated by Antigravity Agent for task: {task_text[:80]}\n\n")
        f.write(code)

    before_files = set(os.listdir(MEDIA_DIR)) if os.path.exists(MEDIA_DIR) else set()

    # Запускаем скрипт
    code_rc, stdout, stderr = run_script(script_path)

    # Self-healing / самоотладка при ошибке
    if code_rc != 0 and stderr:
        fix_prompt = (
            f"Скрипт, написанный для задачи «{task_text}», упал с ошибкой:\n\n"
            f"```\n{stderr[:800]}\n```\n\n"
            f"Исходный код:\n```python\n{code}\n```\n\n"
            "Исправь ошибку, устрани причину падения и верни исправленный работающий Python-код строго в блоке ```python ... ```."
        )
        fixed_reply = ask_ai_fn(fix_prompt)
        fixed_code = extract_python_code(fixed_reply)
        if fixed_code:
            with open(script_path, "w", encoding="utf-8") as f:
                f.write("# -*- coding: utf-8 -*-\n")
                f.write(f"# Auto-fixed by Antigravity Agent for task: {task_text[:80]}\n\n")
                f.write(fixed_code)
            code_rc, stdout, stderr = run_script(script_path)

    # Проверяем, появился ли новый файл в media/
    new_media = find_newest_media(before_files, stdout=stdout)

    # Формируем итоговый понятный ответ пользователю
    clean_desc = re.sub(r"```[\s\S]*?```", "", ai_reply).strip()

    final_text_parts = []
    final_text_parts.append(f"⚡ **Автономное действие выполнено для {sender_name}:**")
    if clean_desc:
        final_text_parts.append(f"_{clean_desc}_\n")

    if stdout:
        final_text_parts.append(f"📊 **Результат выполнения:**\n```\n{stdout[:1500]}\n```")
    elif code_rc == 0 and not new_media:
        final_text_parts.append("✅ Скрипт успешно выполнен (сохранено в `extensions/`).")
    elif code_rc != 0:
        final_text_parts.append(f"⚠️ Ошибка выполнения:\n`{stderr[:300]}`")

    if new_media:
        final_text_parts.append(f"📁 Создан медиафайл: `{os.path.basename(new_media)}`")

    return "\n".join(final_text_parts), new_media
