# -*- coding: utf-8 -*-
"""
EXTENSION: weather_tiraspol | Прогноз погоды в Тирасполе и регионе на любую дату
"""
import os
import sys
import re
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

def get_weather(query_text=""):
    q = (query_text or "").lower()

    # City detection (default: Tiraspol)
    city_name = "Тирасполь"
    lat, lon = 46.8403, 29.6433

    # Date detection
    today = datetime.now()
    target_date = today

    if "завтра" in q:
        target_date = today + timedelta(days=1)
    elif "послезавтра" in q:
        target_date = today + timedelta(days=2)
    elif "вчера" in q:
        target_date = today - timedelta(days=1)
    else:
        # Check for numeric date like 15.10 or 2026-10-15 or 15 октября
        dm = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", q)
        if dm:
            day, month = int(dm.group(1)), int(dm.group(2))
            year = int(dm.group(3)) if dm.group(3) else today.year
            if year < 100: year += 2000
            try:
                target_date = datetime(year, month, day)
            except Exception:
                target_date = today

    date_str = target_date.strftime("%Y-%m-%d")
    is_today = (target_date.date() == today.date())

    wmo_codes = {
        0: ("Ясно", "☀️"),
        1: ("Преимущественно ясно", "🌤️"),
        2: ("Переменная облачность", "⛅"),
        3: ("Пасмурно", "☁️"),
        45: ("Туман", "🌫️"),
        48: ("Иней / туман", "🌫️"),
        51: ("Легкая морось", "🌦️"),
        53: ("Морось", "🌦️"),
        55: ("Плотная морось", "🌧️"),
        61: ("Небольшой дождь", "🌧️"),
        63: ("Умеренный дождь", "🌧️"),
        65: ("Сильный ливень", "⛈️"),
        71: ("Небольшой снегопад", "🌨️"),
        73: ("Снегопад", "❄️"),
        75: ("Сильный снегопад", "❄️"),
        77: ("Снежные зерна", "❄️"),
        80: ("Кратковременный дождь", "🌦️"),
        81: ("Ливень", "🌧️"),
        82: ("Шквальный ливень", "⛈️"),
        85: ("Снегопад", "🌨️"),
        95: ("Гроза", "⛈️"),
        96: ("Гроза с градом", "⛈️")
    }

    headers = {"User-Agent": "Mozilla/5.0"}
    
    # 1. Open-Meteo Forecast & Archive API
    try:
        if (today - target_date).days > 5:
            api_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={lat}&longitude={lon}&start_date={date_str}&end_date={date_str}&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max&timezone=auto"
        else:
            api_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max,sunrise,sunset&timezone=auto&start_date={date_str}&end_date={date_str}"
        
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
            
        daily = data.get("daily", {})
        code = daily.get("weather_code", [0])[0]
        desc, emoji = wmo_codes.get(code, ("Без существенных осадков", "🌤️"))
        t_max = daily.get("temperature_2m_max", [None])[0]
        t_min = daily.get("temperature_2m_min", [None])[0]
        precip = daily.get("precipitation_sum", [0.0])[0]
        wind_max = daily.get("wind_speed_10m_max", [None])[0]

        curr = data.get("current")
        curr_block = ""
        if is_today and curr:
            c_temp = curr.get("temperature_2m", 0)
            c_app = curr.get("apparent_temperature", 0)
            c_hum = curr.get("relative_humidity_2m", 0)
            c_wind = curr.get("wind_speed_10m", 0)
            c_code = curr.get("weather_code", code)
            c_desc, c_emoji = wmo_codes.get(c_code, (desc, emoji))
            curr_block = (
                f"🌡️ **Сейчас на улице:** `{c_temp:+.1f}°C` (ощущается как `{c_app:+.1f}°C`)\n"
                f"{c_emoji} **Состояние:** {c_desc}\n"
                f"💧 **Влажность:** `{c_hum}%` | 💨 **Ветер:** `{c_wind} км/ч`\n\n"
            )

        date_human = target_date.strftime("%d.%m.%Y")
        t_max_str = f"+{t_max:.1f}°C" if t_max and t_max > 0 else f"{t_max:.1f}°C"
        t_min_str = f"+{t_min:.1f}°C" if t_min and t_min > 0 else f"{t_min:.1f}°C"

        report = (
            f"📍 **Погода в г. {city_name} (Приднестровье)**\n"
            f"📅 **Дата:** `{date_human}`\n\n"
            f"{curr_block}"
            f"📊 **Прогноз на день:**\n"
            f"{emoji} {desc}\n"
            f"📈 **Днем:** `{t_max_str}` | 📉 **Ночью:** `{t_min_str}`\n"
            f"💨 **Ветер до:** `{wind_max} км/ч`\n"
            f"🌧️ **Осадки:** `{precip} мм`\n\n"
            f"✨ _Метеостанция Тирасполя • ПМР_"
        )
        return report

    except Exception as e:
        try:
            w_url = f"https://wttr.in/Tiraspol?format=%C:+%t+(ощущается+%f),+ветер+%w,+влажность+%h"
            req2 = urllib.request.Request(w_url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req2, timeout=5) as r2:
                wttr_text = r2.read().decode("utf-8").strip()
            return f"📍 **Погода в г. {city_name} (Приднестровье):**\n\n🌤️ {wttr_text}\n📅 Дата: {target_date.strftime('%d.%m.%Y')}"
        except Exception:
            return f"Не удалось получить погоду для Тирасполя: {e}"

if __name__ == "__main__":
    task_input = " ".join(sys.argv[1:]) or os.environ.get("TASK_TEXT", "") or os.environ.get("INPUT_FILE", "")
    print(get_weather(task_input))
