# -*- coding: utf-8 -*-
# SKILL_NAME: kling_video_skill
# DESCRIPTION: Генерация ИИ-видео через удаленный MCP-сервер Kling AI
# TRIGGERS: клинг, kling, сгенерируй видео, сгенерировать видео, создай видео, ии видео, видео по тексту
# REQUIREMENTS: 

import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from kling_client import (
        get_kling_config,
        check_kling_credits,
        submit_text_to_video,
        submit_image_to_video,
        generate_kling_video_async
    )
except ImportError:
    pass

def handle_task(task_text, photo_path=None, **kwargs):
    token, _ = get_kling_config()
    if not token:
        return "Для генерации видео в Kling AI необходимо настроить переменную KLING_API_KEY в окружении бота на Render 🔧", None

    prompt = task_text
    for prefix in ["клинг", "kling", "сгенерируй видео", "создай видео", "сделай видео"]:
        if prefix in prompt.lower():
            idx = prompt.lower().find(prefix) + len(prefix)
            prompt = prompt[idx:].strip()

    prompt = prompt.strip(" :,-") or "Кинематографичный ролик с динамичным освещением"
    return f"Запуск генерации видео Kling AI по запросу: «{prompt}»...", None

if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "тест"
    res, media = handle_task(text)
    print(res)
