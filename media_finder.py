import os
import re
import sys
import time
import json
import hashlib
import subprocess
import urllib.request
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
MUSIC_DIR = os.path.join(MEDIA_DIR, "music")
GIF_DIR = os.path.join(MEDIA_DIR, "gifs")
VIDEO_DIR = os.path.join(MEDIA_DIR, "videos")

os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(GIF_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
}

def clean_query(text, media_type="music"):
    t = text.strip()
    prefix_pattern = r"(?i)^(?:!бот|!bot|бот[,\s]*|ботик[,\s]*|пожалуйста[,\s]*|плиз[,\s]*|найди|скинь|скачай|загрузи|поставь|включи|отправь|сочини|сыграй|сделай|запили|сгенерируй)\s*"
    while True:
        new_t = re.sub(prefix_pattern, "", t).strip()
        if new_t == t:
            break
        t = new_t

    t_lower = t.lower()
    if media_type == "music":
        if any(w in t_lower for w in ["симфони", "symphony", "оркестр"]):
            if len(t) < 20:
                return "Beethoven symphony 5 orchestra epic"
        t = re.sub(r"(?i)^(?:музыку|музыка|трек|песню|песня|бит|симфонию|симфония)\s*", "", t).strip()
        return t or "DNCE Cake by the ocean"
    else:
        t = re.sub(r"(?i)^(?:видео|видос|клип|гиф|гифку|гифка)\s*", "", t).strip()
        return t or "funny cat"

def find_and_download_music(query, max_filesize="30M"):
    clean_q = clean_query(query, "music")
    q_hash = hashlib.md5(clean_q.lower().encode()).hexdigest()[:10]
    out_file = os.path.join(MUSIC_DIR, f"track_{q_hash}.mp3")

    if os.path.exists(out_file) and os.path.getsize(out_file) > 100000:
        return out_file, clean_q

    out_tmpl = os.path.join(MUSIC_DIR, f"track_{q_hash}.%(ext)s")
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--default-search", "ytsearch",
        "--max-filesize", max_filesize,
        "--no-playlist",
        "-o", out_tmpl,
        f"ytsearch1:{clean_q}"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
            return out_file, clean_q
        
        # Check if downloaded under slightly different name
        for f in os.listdir(MUSIC_DIR):
            if f.startswith(f"track_{q_hash}") and f.endswith(".mp3"):
                return os.path.join(MUSIC_DIR, f), clean_q
    except Exception as e:
        print(f"[MEDIA FINDER] Music download error: {e}")

    return None, clean_q

def find_and_download_gif(query):
    clean_q = clean_query(query, "gif")
    q_hash = hashlib.md5(clean_q.lower().encode()).hexdigest()[:10]
    out_file = os.path.join(GIF_DIR, f"gif_{q_hash}.gif")

    if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
        return out_file, clean_q

    # 1. Tenor search
    try:
        url = f"https://tenor.com/search/{urllib.parse.quote(clean_q)}-gifs"
        req = urllib.request.Request(url, headers=HEADERS)
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        gifs = re.findall(r"(https://media\.tenor\.com/[^\"\s]+\.gif)", html)
        if gifs:
            gif_url = gifs[0]
            req2 = urllib.request.Request(gif_url, headers=HEADERS)
            data = urllib.request.urlopen(req2, timeout=12).read()
            with open(out_file, "wb") as f:
                f.write(data)
            return out_file, clean_q
    except Exception as e:
        print(f"[MEDIA FINDER] Tenor gif error: {e}")

    # 2. Giphy / DuckDuckGo fallback
    try:
        ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(clean_q + ' gif')}"
        req = urllib.request.Request(ddg_url, headers=HEADERS)
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
        gifs = re.findall(r"(https?://[^\s\"<>]+\.gif)", html)
        if gifs:
            req2 = urllib.request.Request(gifs[0], headers=HEADERS)
            data = urllib.request.urlopen(req2, timeout=12).read()
            with open(out_file, "wb") as f:
                f.write(data)
            return out_file, clean_q
    except Exception as e:
        print(f"[MEDIA FINDER] DDG gif error: {e}")

    return None, clean_q

def find_and_download_video(query, max_filesize="40M"):
    clean_q = clean_query(query, "video")
    q_hash = hashlib.md5(clean_q.lower().encode()).hexdigest()[:10]
    out_file = os.path.join(VIDEO_DIR, f"video_{q_hash}.mp4")

    if os.path.exists(out_file) and os.path.getsize(out_file) > 100000:
        return out_file, clean_q

    out_tmpl = os.path.join(VIDEO_DIR, f"video_{q_hash}.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "mp4[filesize<35M]/best[filesize<35M]/best",
        "--default-search", "ytsearch",
        "--max-filesize", max_filesize,
        "--no-playlist",
        "-o", out_tmpl,
        f"ytsearch1:{clean_q}"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
            return out_file, clean_q

        for f in os.listdir(VIDEO_DIR):
            if f.startswith(f"video_{q_hash}") and f.endswith(".mp4"):
                return os.path.join(VIDEO_DIR, f), clean_q
    except Exception as e:
        print(f"[MEDIA FINDER] Video download error: {e}")

    return None, clean_q
