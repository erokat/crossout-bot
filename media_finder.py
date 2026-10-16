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
IMAGES_DIR = os.path.join(MEDIA_DIR, "images")

os.makedirs(MUSIC_DIR, exist_ok=True)
os.makedirs(GIF_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)

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
        t = re.sub(r"(?i)\s*(?:,\s*)?(?:\bи\s+)?(?:сделай|поставь|назови|дай|с)\s+(?:у\s+самого\s+)?(?:файл[а-я]*\s+)?(?:музыкального\s+)?(?:но[о]*рмальн[а-я]*\s+)?(?:названи[а-я]*|именем|имя|название).*$", "", t).strip()
        return t or "DNCE Cake by the ocean"
    elif media_type == "image":
        t = re.sub(r"(?i)^(?:фото|фотку|фотографию|картинку|пикчу|арт|изображение|в\s+интернете|в\s+сети|в\s+яндексе|в\s+гугле)\s*", "", t).strip()
        t = re.sub(r"(?i)^(?:локации|локацию|персонажа)\s*", "", t).strip()
        return t or "gaming landscape"
    else:
        t = re.sub(r"(?i)^(?:видео|видос|клип|гиф|гифку|гифка)\s*", "", t).strip()
        return t or "funny cat"

CLASSICAL_ARCHIVE = [
    {
        "keywords": ["бетховен", "beethoven", "5", "пятая", "симфони", "симфония"],
        "title": "Людвиг ван Бетховен — Симфония №5 (Op. 67, Allegro con brio)",
        "url": "https://archive.org/download/78_symphony-no-5-in-c-minor-c-moll-op-67-1st-movement-part-1-allegro-con-brio_beethove_gbia7040491a/SYMPHONY%20NO.%205%20IN%20C%20MINOR%20%28C%20MOLL%29%2C%20OP.%2067%20-%201.mp3"
    },
    {
        "keywords": ["ода", "радост", "ode", "joy", "9", "девят"],
        "title": "Людвиг ван Бетховен — Ода к радости (Симфония №9)",
        "url": "https://archive.org/download/78_ode-to-joy_boston-symphony-orchestra-beethoven-dr-serge-koussevitzky_gbia7003450a/01%20ODE%20TO%20JOY%20-%20Boston%20Symphony%20Orchestra%20-%20Beethoven%20-%20Dr.%20Serge%20Koussevitzky.mp3"
    },
    {
        "keywords": ["моцарт", "mozart", "40", "сороков"],
        "title": "Вольфганг Амадей Моцарт — Симфония №40 (K. 550, 1st Movement)",
        "url": "https://archive.org/download/78_symphony-no-40-in-g-minor-k-550-1st-movement_chicago-symphony-orchestra-frederick-_gbia0118833a/01%20Symphony%20No.%2040%20in%20G%20Minor%2C%20K.%20550%20%281st%20Movement%29%20-%20Chicago%20Symphony%20Orchestra.mp3"
    },
    {
        "keywords": ["чайковск", "tchaikovsky", "итальянск", "каприччио", "1812"],
        "title": "Петр Ильич Чайковский — Итальянское каприччио (Op. 45)",
        "url": "https://archive.org/download/78_capriccio-italien-op-45-part-3_the-danish-state-broadcasting-symphony-orchestra_gbia7013296a/01%20CAPRICCIO%20ITALIEN%2C%20OP.%2045%2C%20Part%203%20-%20The%20Danish%20State%20Broadcasting%20Symphony%20Orchestra.mp3"
    },
    {
        "keywords": ["вивальди", "vivaldi", "весна", "spring", "времена"],
        "title": "Антонио Вивальди — Времена года: Весна (Allegro)",
        "url": "https://archive.org/download/78_the-four-seasons-spring-1st-movement-allegro_louis-kaufman-antonio-vivaldi_gbia0187841a/01%20THE%20FOUR%20SEASONS%20-%20SPRING%20-%201st%20Movement%20%28Allegro%29%20-%20Louis%20Kaufman.mp3"
    },
    {
        "keywords": ["григ", "grieg", "утро", "пер", "гюнт", "peer"],
        "title": "Эдвард Григ — Пер Гюнт: Утро (Morning Mood)",
        "url": "https://archive.org/download/78_peer-gynt-suite-no-1-morning_athenaeum-symphony-orchestra-grieg_gbia0443514a/01%20Peer%20Gynt%20Suite%20No.%201%20%22Morning%22%20-%20Athenaeum%20Symphony%20Orchestra.mp3"
    }
]

def download_file_direct(url, dest_path, timeout=30):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
            if len(content) > 20000:
                with open(dest_path, "wb") as f:
                    f.write(content)
                return True
    except Exception as e:
        print(f"[MEDIA FINDER] Direct download error ({url}): {e}")
    return False

def search_internet_archive_audio(clean_q, dest_path):
    try:
        search_term = urllib.parse.quote(f"({clean_q}) AND mediatype:(audio)")
        api_url = f"https://archive.org/advancedsearch.php?q={search_term}&fl[]=identifier,title&rows=3&output=json"
        req = urllib.request.Request(api_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            docs = data.get("response", {}).get("docs", [])
            for doc in docs:
                ident = doc.get("identifier")
                title = doc.get("title", clean_q)
                if not ident:
                    continue
                meta_url = f"https://archive.org/metadata/{ident}/files"
                m_req = urllib.request.Request(meta_url, headers=HEADERS)
                with urllib.request.urlopen(m_req, timeout=8) as m_resp:
                    m_data = json.loads(m_resp.read().decode("utf-8"))
                    files = m_data.get("result", [])
                    mp3_cand = next((f["name"] for f in files if f.get("name", "").lower().endswith(".mp3") and f.get("size", 0) and int(f["size"]) < 35000000), None)
                    if mp3_cand:
                        dl_url = f"https://archive.org/download/{ident}/{urllib.parse.quote(mp3_cand)}"
                        if download_file_direct(dl_url, dest_path):
                            return dest_path, title
    except Exception as e:
        print(f"[MEDIA FINDER] Internet Archive search error: {e}")
    return None, None

def synthesize_classical_symphony(clean_q, dest_path, duration=22.0):
    """
    Автономный процедурный синтезатор симфоний (на случай блокировок YouTube / оффлайна).
    Генерирует полифоническую оркестровую гармонию в Ре миноре с духовыми, смычковыми,
    ведущей мелодией и перкуссией, конвертирует в MP3.
    """
    import math
    import struct
    import wave
    import tempfile
    import shutil

    sample_rate = 44100
    num_samples = int(sample_rate * duration)

    chords = [
        [146.83, 174.61, 220.00, 293.66, 349.23], # Dm
        [116.54, 146.83, 174.61, 233.08, 293.66], # Bb
        [87.31, 130.81, 174.61, 220.00, 261.63],  # F
        [130.81, 196.00, 261.63, 329.63, 392.00], # C
        [98.00, 146.83, 196.00, 233.08, 293.66],  # Gm
        [110.00, 164.81, 220.00, 277.18, 329.63], # A7
        [146.83, 174.61, 220.00, 293.66, 349.23], # Dm
        [146.83, 220.00, 293.66, 349.23, 440.00]  # Dm (final chord)
    ]

    melody_notes = [
        (293.66, 0.6), (349.23, 0.6), (440.00, 1.3),
        (392.00, 0.6), (349.23, 0.6), (329.63, 1.3),
        (233.08, 0.6), (293.66, 0.6), (349.23, 1.3),
        (440.00, 0.6), (392.00, 0.6), (349.23, 1.3),
        (349.23, 0.6), (392.00, 0.6), (440.00, 1.3),
        (523.25, 0.6), (440.00, 0.6), (392.00, 1.3),
        (329.63, 0.6), (277.18, 0.6), (293.66, 1.3),
        (220.00, 0.6), (293.66, 2.2)
    ]

    tmpdir = tempfile.gettempdir()
    wav_path = os.path.join(tmpdir, f"synth_{os.getpid()}_{int(time.time())}.wav")

    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)

            samples = []
            chord_dur = duration / len(chords)

            for i in range(num_samples):
                t = i / sample_rate
                ch_idx = min(int(t / chord_dur), len(chords) - 1)
                cur_chord = chords[ch_idx]

                pad = 0.0
                for f in cur_chord:
                    pad += 0.12 * math.sin(2 * math.pi * f * t)
                    pad += 0.06 * math.sin(2 * math.pi * f * 2 * t)
                    pad += 0.03 * math.sin(2 * math.pi * f * 3 * t)

                mel_t = t % duration
                accum = 0.0
                cur_mel = 293.66
                note_phase = 0.0
                for freq, dur in melody_notes:
                    if accum <= mel_t < accum + dur:
                        cur_mel = freq
                        note_phase = mel_t - accum
                        break
                    accum += dur

                env = min(1.0, note_phase * 12.0) * max(0.0, 1.0 - (note_phase / dur) * 0.4)
                mel = 0.35 * env * (math.sin(2 * math.pi * cur_mel * t) + 0.4 * math.sin(2 * math.pi * cur_mel * 2 * t))

                beat = (t * 2.0) % 1.0
                timpani_env = math.exp(-beat * 6.0)
                timpani = 0.28 * timpani_env * math.sin(2 * math.pi * (cur_chord[0] / 2.0) * t)

                total = pad + mel + timpani
                sample_val = int(max(-32767, min(32767, total * 22000)))
                samples.append(struct.pack("<h", sample_val))

            wf.writeframes(b"".join(samples))

        res = subprocess.run(["ffmpeg", "-y", "-i", wav_path, "-b:a", "192k", dest_path], capture_output=True)
        if res.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 10000:
            return dest_path, f"Симфония «{clean_q.capitalize()}» (Op. 1)"
        shutil.copy2(wav_path, dest_path)
        return dest_path, f"Симфония «{clean_q.capitalize()}» (Op. 1)"
    except Exception as e:
        print(f"[MEDIA FINDER] Audio synth error: {e}")
        return None, None
    finally:
        if os.path.exists(wav_path):
            try: os.remove(wav_path)
            except Exception: pass

def find_and_download_music(query, max_filesize="30M"):
    clean_q = clean_query(query, "music")
    safe_name = re.sub(r'[\\/*?:"<>|]', "", clean_q).strip()[:80]
    if not safe_name:
        safe_name = f"track_{hashlib.md5(clean_q.lower().encode()).hexdigest()[:10]}"
    out_file = os.path.join(MUSIC_DIR, f"{safe_name}.mp3")

    if os.path.exists(out_file) and os.path.getsize(out_file) > 100000:
        return out_file, clean_q

    q_lower = (query or "").lower()
    is_classical_query = any(w in q_lower for w in ["симфони", "symphony", "оркестр", "бетховен", "моцарт", "баха", "чайковск", "классик", "сочини", "сыграй"])

    # 1. Если это классика или симфония — проверяем кураторский архив шедевров без 403 блокировок
    if is_classical_query:
        for item in CLASSICAL_ARCHIVE:
            if any(kw in q_lower for kw in item["keywords"]):
                print(f"[MEDIA FINDER] Match in curated classical archive: {item['title']}")
                if download_file_direct(item["url"], out_file):
                    return out_file, item["title"]

    # 2. Формируем варианты поисковых запросов для yt-dlp
    search_queries = [clean_q]
    q_no_preps = re.sub(r"(?i)\b(?:от|by|автора?|исполнителя?|группы)\b", " ", clean_q).strip()
    q_no_preps = re.sub(r"\s+", " ", q_no_preps)
    if q_no_preps and q_no_preps.lower() != clean_q.lower():
        search_queries.insert(0, q_no_preps)

    # Добавляем сокращенные запросы на случай опечаток в длинной фразе
    words = [w for w in q_no_preps.split() if len(w) > 1]
    if len(words) >= 4:
        search_queries.append(f"{words[0]} {words[1]} {' '.join(words[3:])}")
        search_queries.append(f"{words[0]} {words[1]}")
    elif len(words) == 3:
        search_queries.append(f"{words[0]} {words[1]}")

    out_tmpl = os.path.join(MUSIC_DIR, f"{safe_name}.%(ext)s")
    for sq in search_queries:
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--default-search", "ytsearch",
            "--extractor-args", "youtube:player_client=android,ios",
            "--max-filesize", max_filesize,
            "--no-playlist",
            "--no-simulate",
            "--print", "%(title)s",
            "-o", out_tmpl,
            f"ytsearch1:{sq}"
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
            extracted_title = ""
            if res.stdout:
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if line and not line.startswith("[") and not line.startswith("ERROR") and not line.startswith("WARNING"):
                        extracted_title = line
                        break

            if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
                return out_file, extracted_title or clean_q

            for f in os.listdir(MUSIC_DIR):
                if f.startswith(safe_name) and f.endswith(".mp3"):
                    fpath = os.path.join(MUSIC_DIR, f)
                    if os.path.getsize(fpath) > 50000:
                        return fpath, extracted_title or clean_q
        except Exception as e:
            print(f"[MEDIA FINDER] yt-dlp error for query {sq!r}: {e}")

    # 3. Резервный поиск по Internet Archive (публичный архив)
    ia_file, ia_title = search_internet_archive_audio(clean_q, out_file)
    if ia_file:
        return ia_file, ia_title or clean_q

    # 4. СТРОГО ЕСЛИ ЗАПРОШЕНА КЛАССИКА / СИМФОНИЯ — используем классические фоллбэки
    if is_classical_query:
        synth_file, synth_title = synthesize_classical_symphony(clean_q, out_file)
        if synth_file:
            return synth_file, synth_title
        fallback_classical = CLASSICAL_ARCHIVE[0]
        if download_file_direct(fallback_classical["url"], out_file):
            return out_file, fallback_classical["title"]

    # Для обычных песен (не классика) — НИКОГДА не подсовывать Бетховена!
    return None, clean_q

find_and_download_audio = find_and_download_music

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
        "--extractor-args", "youtube:player_client=android,ios",
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

def find_and_download_image(query, dest_dir=None):
    """
    Ищет изображение в сети через Bing Images и Yandex Images, проверяет через PIL и сохраняет в JPEG.
    Возвращает (file_path, clean_query) или (None, clean_query).
    """
    if not dest_dir:
        dest_dir = IMAGES_DIR
    os.makedirs(dest_dir, exist_ok=True)

    import random
    clean_q = clean_query(query, "image")
    out_file = os.path.join(dest_dir, f"img_{int(time.time())}_{random.randint(1000, 9999)}.jpg")

    urls = []

    # 1. Yandex Images Search (Primary: best for Russian, games, wikis, and screenshots)
    try:
        y_url = f"https://yandex.ru/images/search?text={urllib.parse.quote(clean_q)}"
        req = urllib.request.Request(y_url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            found = re.findall(r'img_url=([^\x26\s\"<>]+)', html)
            for u in found:
                unq = urllib.parse.unquote(u)
                if any(ext in unq.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    urls.append(unq)
    except Exception as e:
        print(f"[MEDIA FINDER] Yandex image error: {e}")

    # 2. Bing Images Search (with language & locale parameters to prevent European redirect to trending calendars)
    if len(urls) < 8:
        try:
            bing_url = f"https://www.bing.com/images/search?q={urllib.parse.quote(clean_q)}&setlang=ru&cc=RU"
            req = urllib.request.Request(bing_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                found = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', html)
                for u in found:
                    u_low = u.lower()
                    # Filter out unrelated European trending junk (calendars, weather widgets)
                    if "kalender" in u_low or "kalenderpedia" in u_low or "wetter" in u_low:
                        continue
                    if any(ext in u_low for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                        urls.append(u)
        except Exception as e:
            print(f"[MEDIA FINDER] Bing image error: {e}")

    # 3. Query expansion for games/locations if needed (e.g. Rain World, Crossout)
    q_lower = clean_q.lower()
    alt_q = None
    if "rain world" in q_lower or "рейн ворлд" in q_lower:
        if "фильтраци" in q_lower or "filtration" in q_lower:
            alt_q = "Rain World Filtration System screenshot wiki"
        else:
            alt_q = f"{clean_q} screenshot game"
    elif "crossout" in q_lower or "кроссаут" in q_lower:
        alt_q = f"Crossout {clean_q} screenshot"

    if alt_q and len(urls) < 15:
        try:
            y_url_alt = f"https://yandex.ru/images/search?text={urllib.parse.quote(alt_q)}"
            req = urllib.request.Request(y_url_alt, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
                found = re.findall(r'img_url=([^\x26\s\"<>]+)', html)
                for u in found:
                    unq = urllib.parse.unquote(u)
                    if any(ext in unq.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                        urls.append(unq)
        except Exception as e:
            print(f"[MEDIA FINDER] Alt search error: {e}")

    # Download candidate, handle transparency, and verify visibility with PIL
    from PIL import Image, ImageStat
    for cand_url in urls[:20]:
        try:
            req = urllib.request.Request(cand_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                if len(data) < 5000:
                    continue
                temp_raw = out_file + f".tmp_{os.getpid()}_{int(time.time())}"
                with open(temp_raw, "wb") as f:
                    f.write(data)
                try:
                    with Image.open(temp_raw) as img:
                        # Composite alpha transparency onto a white canvas to prevent pitch black backgrounds
                        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                            rgba = img.convert("RGBA")
                            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                            img_rgb = Image.alpha_composite(bg, rgba).convert("RGB")
                        else:
                            img_rgb = img.convert("RGB")

                        # Verify that the image is not a completely flat, monochromatic or solid blank frame
                        stat = ImageStat.Stat(img_rgb)
                        mean_b = sum(stat.mean) / len(stat.mean)
                        std_b = sum(stat.stddev) / len(stat.stddev)
                        # Only reject if image has zero/near-zero variation (solid flat rectangle)
                        if std_b < 4.0 or (mean_b < 3.0 and std_b < 5.0):
                            if os.path.exists(temp_raw):
                                os.remove(temp_raw)
                            continue

                        img_rgb.save(out_file, "JPEG", quality=95)

                    if os.path.exists(temp_raw):
                        os.remove(temp_raw)
                    return out_file, clean_q
                except Exception:
                    if os.path.exists(temp_raw):
                        os.remove(temp_raw)
                    continue
        except Exception:
            continue

    return None, clean_q

def extract_image_search_and_caption(text):
    """
    Проверяет, содержит ли сообщение запрос на поиск изображения в сети,
    и извлекает поисковый запрос и надпись (если запрошена).
    """
    if not text:
        return False, None, None
    t = text.strip()
    t_clean = re.sub(r"(?i)^(?:!бот|!bot|/бот|/bot|бот[,\s]*|ботик[,\s]*|пожалуйста[,\s]*|плиз[,\s]*)\s*", "", t).strip()
    t_lower = t_clean.lower()

    # Если пользователь явно ищет информацию/факты/статью — это текстовый поиск знаний, а не чистый поиск фото!
    info_keywords = ["информаци", "инфу", "стать", "новост", "факты", "что такое", "кто такой", "справк", "описание"]
    if any(k in t_lower for k in info_keywords):
        return False, None, None

    search_pat = r"(?i)^(?:найди(?:\s+в\s+интернете|\s+в\s+сети|\s+в\s+гугле|\s+в\s+яндексе)?|скинь|поищи|покажи|скачай|отправь|кинь)\s+(?:фото|фотку|картинку|пикчу|арт|изображение|обои)\s*(.+)$"
    m = re.search(search_pat, t_clean)
    if not m:
        return False, None, None
    body = m.group(1).strip()

    caption_pat = r"(?i)\s*(?:,\s*)?(?:\bи\s+)?(?:добавь\s+надпись|сделай\s+надпись|напиши|подпиши|с\s+надписью|с\s+текстом|добавь\s+текст|сделай\s+мем)\s*[:\s-]+\s*(.+)$"
    m_cap = re.search(caption_pat, body)
    if m_cap:
        caption = m_cap.group(1).strip()
        search_query = body[:m_cap.start()].strip()
    else:
        caption = None
        search_query = body

    search_query = re.sub(r"(?i)^(?:локации|локацию|персонажа|арт|фото|картинку|фотку|пикчу)\s*", "", search_query).strip()
    return True, search_query, caption
