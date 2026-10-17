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

INVIDIOUS_INSTANCES = [
    "https://invidious.f5.si",
    "https://inv.tux.pizza",
    "https://invidious.nerdvpn.de",
    "https://yewtu.be",
    "https://inv.nadeko.net",
    "https://invidious.flokinet.to"
]

def parse_music_query(clean_q):
    """
    Разделяет 'DELTARUNE - It's TV Time! от InstrumentManiac'
    на title: 'DELTARUNE - It's TV Time!' и artist: 'InstrumentManiac'.
    """
    if not clean_q:
        return "", None
    m = re.search(r"(?i)\s+(?:от|by|автора?|исполнителя?|канал(?:а)?)\s+([^,;!?]+)$", clean_q)
    if m:
        author = m.group(1).strip()
        title = clean_q[:m.start()].strip()
        return title, author
    return clean_q.strip(), None

# Модификаторы для жесткой защиты от ремиксов, мэшапов и каверов
# Если пользователь явно не искал "ремикс" / "кавер", такие треки немедленно дисквалифицируются (-500)
UNWANTED_MODIFIERS = [
    # Категория 1: Жесткие ремиксы, мэшапы, эдиты, спид-апы (дисквалификация -500)
    ("remix", -500),
    ("ремикс", -500),
    ("rmx", -500),
    ("mashup", -500),
    ("мэшап", -500),
    ("bootleg", -500),
    ("vip mix", -500),
    ("nightcore", -500),
    ("slowed", -500),
    ("sped up", -500),
    ("speed up", -500),
    ("bass boosted", -500),
    ("reverb", -500),
    ("parody", -500),
    ("пародия", -500),
    ("ai cover", -500),
    ("chipmunk", -500),
    ("daycore", -500),
    ("earrape", -500),
    ("not mine", -400),
    ("fan made", -400),
    ("fan-made", -400),
    ("juno songs", -400),
    ("hard difficulty", -350),
    ("gameplay", -350),
    ("playthrough", -350),
    ("reaction", -400),

    # Категория 2: Каверы (если пользователь не просил кавер)
    ("metal cover", -500),
    ("guitar cover", -500),
    ("piano cover", -500),
    ("vocal cover", -500),
    ("cover", -500),
    ("кавер", -500),

    # Категория 3: Караоке и текст (lyrics)
    ("with lyrics", -400),
    ("lyrics", -300),
    ("с текстом", -300),
    ("karaoke", -400),
    ("караоке", -400),
    ("backing track", -400),

    # Мягкие инструментальные переложения (если автор не найден)
    ("arrangement", -50),
    ("аранжировка", -50),
    ("recreation", -40),
]

def score_music_candidate(cand, user_title, target_artist=None):
    """
    Оценка соответствия кандидата:
    - Жесткий штраф (-500) за ремиксы/мэшапы/каверы (если их нет в запросе)
    - Огромный бонус (+200) за точное совпадение автора
    - Бонус за Official / OST / Topic-каналы (+120..+150)
    - Бонус за верифицированный канал YouTube (+100)
    """
    title = (cand.get("title") or "").lower()
    uploader = (cand.get("uploader") or cand.get("channel") or "").lower()
    duration = cand.get("duration") or 0
    score = 100.0

    u_title_low = (user_title or "").lower()

    for mod, pen in UNWANTED_MODIFIERS:
        if mod in title and mod not in u_title_low:
            score += pen

    if any(w in title for w in ["official audio", "official track", "original mix", "original soundtrack", "ost", "full ost", "official music video"]):
        score += 120.0
    if "- topic" in uploader:
        score += 150.0
    if cand.get("channel_is_verified") or cand.get("verified"):
        score += 100.0

    if target_artist:
        a_low = target_artist.lower().strip()
        if a_low in uploader:
            score += 200.0
        elif a_low in title:
            score += 100.0
        else:
            score -= 100.0

    user_tokens = set(re.findall(r"\w+", u_title_low))
    title_tokens = set(re.findall(r"\w+", title))
    if user_tokens:
        overlap = len(user_tokens.intersection(title_tokens)) / len(user_tokens)
        score += overlap * 50.0

    if duration:
        if 60 <= duration <= 420:
            score += 20.0
        elif duration < 40 or duration > 900:
            score -= 60.0

    return score

def generate_search_variations(clean_q):
    """
    Генерирует ранжированный список поисковых гипотез:
    1. Запрос без предлогов и стоп-слов ('от', 'by', 'автор', 'исполнитель')
    2. Только название трека (если был указан автор)
    3. Автор + Название трека
    4. Запрос без дефисов
    5. Исходный очищенный запрос
    """
    variations = []
    q_norm = re.sub(r"(?i)\b(?:от|by|автора?|исполнителя?|группы)\b", " ", clean_q).strip()
    q_norm = re.sub(r"\s+", " ", q_norm)
    if q_norm:
        variations.append(q_norm)

    m_author = re.split(r"(?i)\s+(?:от|by)\s+", clean_q, maxsplit=1)
    if len(m_author) == 2:
        title_only = m_author[0].strip()
        author_only = m_author[1].strip()
        if title_only and title_only not in variations:
            variations.append(title_only)
        rev = f"{author_only} {title_only}".strip()
        if rev not in variations:
            variations.append(rev)

    if " - " in clean_q:
        parts = clean_q.split(" - ", 1)
        no_dash = f"{parts[0].strip()} {parts[1].strip()}".strip()
        if no_dash not in variations:
            variations.append(no_dash)

    if clean_q not in variations:
        variations.append(clean_q)

    seen = set()
    unique_vars = []
    for v in variations:
        v_low = v.lower()
        if v_low not in seen:
            seen.add(v_low)
            unique_vars.append(v)
    return unique_vars or [clean_q]

def fetch_candidates(source_prefix, query_str, limit=5, timeout=12):
    """
    Быстрый опрос метаданных топ-N кандидатов с YouTube без скачивания аудио.
    SoundCloud полностью исключен.
    """
    cmd = [
        "yt-dlp",
        "--dump-single-json",
        "--flat-playlist",
        "--socket-timeout", "6",
        "--retries", "0",
        "--no-warnings",
        "--extractor-args", "youtube:player_client=android,web",
        "--geo-bypass"
    ]
    prefix = source_prefix if source_prefix and source_prefix.startswith("ytsearch") else "ytsearch"
    cmd.append(f"{prefix}{limit}:{query_str}")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if res.returncode == 0 and res.stdout:
            data = json.loads(res.stdout)
            entries = data.get("entries", [])
            items = []
            for e in entries:
                if not e:
                    continue
                vid_id = e.get("id")
                direct_url = e.get("url") or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None)
                items.append({
                    "source": "youtube",
                    "id": vid_id,
                    "url": direct_url,
                    "title": e.get("title") or "",
                    "uploader": e.get("uploader") or e.get("channel") or "",
                    "duration": e.get("duration") or 0,
                    "channel_is_verified": e.get("channel_is_verified", False)
                })
            return items
    except Exception as ex:
        sys.stderr.write(f"[MEDIA FINDER] fetch_candidates error ({query_str}): {ex}\n")
    return []

def download_via_ytdlp(source_prefix, query_or_url, out_file, safe_name, max_filesize="30M", timeout=30):
    """
    Унифицированный скачиватель через yt-dlp с жестким тайм-аутом, сокет-таймаутом,
    фильтрацией длительности, форматом bestaudio/18/best и гарантированной конвертацией в MP3.
    Поддерживает как поисковый префикс, так и прямой URL.
    """
    out_tmpl = os.path.join(MUSIC_DIR, f"{safe_name}.%(ext)s")
    target_arg = query_or_url
    if source_prefix and not query_or_url.startswith("http"):
        target_arg = f"{source_prefix}:{query_or_url}"

    cookie_file = None
    b64_cookies = os.environ.get("YOUTUBE_COOKIES_BASE64")
    if not b64_cookies:
        try:
            from db import get_kv
            b64_cookies = get_kv("yt_cookies_base64", "")
        except Exception:
            pass
    if b64_cookies:
        try:
            import base64
            import tempfile
            cookie_file = os.path.join(tempfile.gettempdir(), f"yt_cookies_{os.getpid()}_{time.time_ns()}.txt")
            with open(cookie_file, "wb") as cf:
                cf.write(base64.b64decode(b64_cookies))
        except Exception as ce:
            sys.stderr.write(f"[MEDIA FINDER] Cookies setup error: {ce}\n")

    clients_to_try = ["android,web", "ios,web", "tv,android"] if ("youtube" in target_arg.lower() or "youtu.be" in target_arg.lower() or not target_arg.startswith("http")) else ["default"]

    try:
        for client_arg in clients_to_try:
            cmd = [
                "yt-dlp",
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "0",
                "-f", "bestaudio/18/best",
                "--max-filesize", max_filesize,
                "--no-playlist",
                "--no-simulate",
                "--socket-timeout", "10",
                "--retries", "1",
                "--match-filter", "duration >=? 15 & duration <=? 1200",
                "--embed-metadata",
                "--print", "%(title)s - %(uploader,artist)s",
                "-o", out_tmpl
            ]
            if client_arg != "default":
                cmd.extend([
                    "--extractor-args", f"youtube:player_client={client_arg}",
                    "--geo-bypass"
                ])
            if cookie_file and os.path.exists(cookie_file):
                cmd.extend(["--cookies", cookie_file])

            cmd.append(target_arg)

            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                extracted_title = ""
                if res.stdout:
                    for line in res.stdout.splitlines():
                        line = line.strip()
                        if line and not line.startswith("[") and not line.startswith("ERROR") and not line.startswith("WARNING"):
                            extracted_title = line
                            break

                if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
                    return out_file, extracted_title

                if res.stderr and ("error" in res.stderr.lower() or "warning" in res.stderr.lower()):
                    sys.stderr.write(f"[MEDIA FINDER] yt-dlp notice ({client_arg}) for {target_arg}: {res.stderr.strip()[:200]}\n")

                # Поиск по шаблону и доконвертация в mp3, если yt-dlp оставил m4a/opus/webm/mp4
                for f in os.listdir(MUSIC_DIR):
                    if f.startswith(safe_name):
                        fpath = os.path.join(MUSIC_DIR, f)
                        if not f.endswith(".mp3") and os.path.getsize(fpath) > 50000:
                            conv_cmd = ["ffmpeg", "-y", "-i", fpath, "-vn", "-c:a", "libmp3lame", "-q:a", "2", out_file]
                            subprocess.run(conv_cmd, capture_output=True, timeout=25)
                            try: os.remove(fpath)
                            except Exception: pass
                            if os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
                                return out_file, extracted_title
                        elif f.endswith(".mp3") and os.path.getsize(fpath) > 50000:
                            return fpath, extracted_title
            except subprocess.TimeoutExpired:
                sys.stderr.write(f"[MEDIA FINDER] yt-dlp timeout ({timeout}s) for {target_arg} ({client_arg})\n")
            except Exception as e:
                sys.stderr.write(f"[MEDIA FINDER] yt-dlp error for {target_arg}: {e}\n")
            finally:
                for f in os.listdir(MUSIC_DIR):
                    if f.startswith(safe_name) and f.endswith((".part", ".ytdl", ".temp")):
                        try: os.remove(os.path.join(MUSIC_DIR, f))
                        except Exception: pass
    finally:
        if cookie_file and os.path.exists(cookie_file):
            try: os.remove(cookie_file)
            except Exception: pass

    return None, ""

def stream_invidious_video_id(video_id, title, author, out_file, timeout=20):
    """
    Прямой стриминг аудиопотока YouTube видео по ID через Invidious API (обход 403 блокировки).
    """
    req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    for base_url in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{base_url}/api/v1/videos/{video_id}?fields=title,author,adaptiveFormats,formatStreams"
            req = urllib.request.Request(api_url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            formats = data.get("adaptiveFormats", [])
            audio_formats = [f for f in formats if f.get("type", "").startswith("audio/")]
            if not audio_formats:
                audio_formats = [f for f in data.get("formatStreams", []) if f.get("url")]
            if not audio_formats:
                continue

            best = max(audio_formats, key=lambda x: int(x.get("bitrate", 0) or 0))
            stream_url = best.get("url")
            if not stream_url:
                continue

            if stream_url.startswith("/"):
                stream_url = f"{base_url}{stream_url}"

            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-reconnect", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "-i", stream_url,
                "-vn", "-c:a", "libmp3lame", "-q:a", "2",
                "-id3v2_version", "3",
                "-metadata", f"title={title}",
                "-metadata", f"artist={author}",
                out_file
            ]
            f_res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=timeout)
            if f_res.returncode == 0 and os.path.exists(out_file) and os.path.getsize(out_file) > 50000:
                full_title = f"{title} - {author}" if author else title
                return out_file, full_title
        except Exception as ex:
            sys.stderr.write(f"[MEDIA FINDER] Invidious instance {base_url} error: {ex}\n")
            continue
    return None, ""

def search_invidious_audio(query_str, out_file, timeout=15):
    """
    Резервный поиск YouTube аудио через публичные Invidious API инстансы (обход IP блокировок дата-центра).
    """
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CrossoutBot/1.0"}
    for base_url in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{base_url}/api/v1/search?q={urllib.parse.quote(query_str)}&type=video"
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=7) as resp:
                results = json.loads(resp.read().decode("utf-8"))
            if not results or not isinstance(results, list):
                continue

            video = results[0]
            video_id = video.get("videoId")
            title = video.get("title", query_str)
            author = video.get("author", "")
            if not video_id:
                continue

            res_file, full_title = stream_invidious_video_id(video_id, title, author, out_file, timeout=timeout)
            if res_file:
                return res_file, full_title
        except Exception:
            continue
    return None, ""

def refine_music_query_via_ai(clean_q):
    """
    Резервный ИИ-поиск и нормализация музыкального запроса через Gemini 3.8 Flash Medium.
    Если поиск по исходной строке не дал результатов (опечатки, транслит, слова из песни),
    модель определяет каноническое название трека и исполнителя и возвращает очищенный запрос.
    """
    if not clean_q or len(clean_q.strip()) < 2:
        return None

    prompt = (
        "Ты — профессиональный музыкальный эксперт и ассистент по поиску музыки.\n"
        f"Пользователь искал трек: «{clean_q}»\n"
        "По этой точной строке в базах аудио ничего не нашлось (возможно: опечатка, фраза на слух, "
        "русский транслит англоязычного трека, обрывок слов из песни, неточное имя исполнителя или описание сцены).\n\n"
        "Твоя задача:\n"
        "1. Понять, какую именно песню, композицию или саундтрек имел в виду пользователь.\n"
        "2. Восстановить правильное официальное название трека и исполнителя/композитора.\n"
        "3. Выдать один точный, канонический поисковый запрос (например: 'Artist - Track Title' или 'Official Track Title').\n\n"
        "СТРОЖАЙШЕЕ ПРАВИЛО: Верни ТОЛЬКО одну строку с очищенным запросом для поиска. "
        "Без кавычек, без кавычек-ёлочек, без вводных слов, без пояснений, без markdown."
    )

    refined = None

    # 1. Приоритет: Antigravity CLI (модель gemini-3.8-flash-medium)
    try:
        from keep_alive import run_antigravity_cli
        refined = run_antigravity_cli(prompt, timeout=25)
    except Exception:
        pass

    if not refined:
        try:
            import shutil
            agy_bin = shutil.which("agy") or shutil.which("antigravity")
            if not agy_bin:
                for candidate in ["/usr/local/bin/agy", "/root/.local/bin/agy", "/data/data/com.termux/files/usr/bin/agy"]:
                    if os.path.exists(candidate):
                        agy_bin = candidate
                        break
            if agy_bin:
                cmd = [agy_bin, "--model", "gemini-3.8-flash-medium", "--dangerously-skip-permissions", "--disable-slash-commands", "-p", prompt]
                r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=25)
                if r.returncode == 0 and r.stdout.strip():
                    refined = r.stdout.strip()
        except Exception:
            pass

    if not refined:
        # 2. Резерв: Gemini API напрямую
        try:
            from keep_alive import ask_gemini_api
            refined = ask_gemini_api(prompt, system_instruction="Return only the clean canonical music title and artist.")
        except Exception:
            pass

    if refined:
        refined = re.sub(r"^```[a-zA-Z]*\n?", "", refined.strip())
        refined = re.sub(r"\n?```$", "", refined.strip())
        refined = re.sub(r"^(?:поисковый запрос|запрос|query|результат|трек|песня)[:\s\-]+", "", refined, flags=re.IGNORECASE)
        refined = refined.strip("\"'«»`").strip()
        if "\n" in refined:
            refined = refined.splitlines()[0].strip().strip("\"'«»`")
        if refined and refined.lower() != clean_q.lower():
            return refined

    return None

def find_and_download_music(query, max_filesize="30M", allow_ai_fallback=True):
    clean_q = clean_query(query, "music")
    safe_name = re.sub(r'[\\/*?:"<>|]', "", clean_q).strip()[:80]
    if not safe_name:
        safe_name = f"track_{hashlib.md5(clean_q.lower().encode()).hexdigest()[:10]}"
    out_file = os.path.join(MUSIC_DIR, f"{safe_name}.mp3")

    # 0. Кэш-проверка: если файл уже есть на диске и валиден (>100 КБ)
    if os.path.exists(out_file) and os.path.getsize(out_file) > 100000:
        return out_file, clean_q

    q_lower = (query or "").lower()
    is_classical_query = any(w in q_lower for w in ["симфони", "symphony", "оркестр", "бетховен", "моцарт", "баха", "чайковск", "классик", "сочини", "сыграй"])

    # Если классика — приоритетно проверяем кураторский архив шедевров
    if is_classical_query:
        for item in CLASSICAL_ARCHIVE:
            if any(kw in q_lower for kw in item["keywords"]):
                if download_file_direct(item["url"], out_file):
                    return out_file, item["title"]

    title_q, target_artist = parse_music_query(clean_q)
    search_q = f"{title_q} {target_artist}".strip() if target_artist else clean_q

    # 1. ПУЛ КАНДИДАТОВ: Только YouTube (SoundCloud категорически запрещен)
    yt_candidates = fetch_candidates("ytsearch", search_q, limit=6, timeout=12)

    # Дополнительный опрос для поиска Official Audio / Topic / OST
    if target_artist:
        extra_q = f"{target_artist} - {title_q}"
    else:
        extra_q = f"{title_q} Official Audio"
    extra_candidates = fetch_candidates("ytsearch", extra_q, limit=4, timeout=10)

    # Дедупликация кандидатов по ID
    seen_ids = set()
    combined_candidates = []
    for cand in yt_candidates + extra_candidates:
        cid = cand.get("id")
        if cid and cid not in seen_ids:
            seen_ids.add(cid)
            combined_candidates.append(cand)

    # 2. Интеллектуальный скоринг кандидатов с жесткой защитой от ремиксов (-300)
    scored_candidates = []
    for cand in combined_candidates:
        cand["score"] = score_music_candidate(cand, title_q, target_artist)
        scored_candidates.append(cand)

    scored_candidates.sort(key=lambda x: x["score"], reverse=True)

    # Логируем результаты топ-3 скоринга для мониторинга
    if scored_candidates:
        top_logs = [f"[{c['score']:.0f}] {c['title'][:30]} ({c['uploader'][:15]})" for c in scored_candidates[:3]]
        sys.stderr.write(f"[MUSIC SCORE] Top candidates for '{clean_q}': {' | '.join(top_logs)}\n")

    # 3. Скачивание лучшего кандидата (порог >= 60, отсекает любые ремиксы со штрафом -300)
    for cand in scored_candidates:
        if cand["score"] < 60:
            break
        cand_url = cand.get("url")
        cand_title = cand.get("title", clean_q)
        cand_author = cand.get("uploader", "")
        cand_id = cand.get("id")

        # 1) Сначала пробуем скачать YouTube через yt-dlp с android клиентом
        track, title = download_via_ytdlp(None, cand_url, out_file, safe_name, max_filesize=max_filesize, timeout=25)
        if track:
            return track, title or f"{cand_title} - {cand_author}"
        # 2) Если на Render прилетел 403 — скачиваем аудиопоток точного videoId через Invidious
        if cand_id:
            track, title = stream_invidious_video_id(cand_id, cand_title, cand_author, out_file, timeout=20)
            if track:
                return track, title or f"{cand_title} - {cand_author}"

    # 4. Резервные уровни (Bandcamp и Invidious Text Search)
    variations = generate_search_variations(clean_q)
    for var in variations[:2]:
        track, title = search_invidious_audio(var, out_file, timeout=18)
        if track:
            return track, title or clean_q

    for var in variations[:2]:
        track, title = download_via_ytdlp("bcsearch1", var, out_file, safe_name, max_filesize=max_filesize, timeout=25)
        if track:
            return track, title or clean_q

    # 5. Классика: синтезатор и архив
    if is_classical_query:
        synth_file, synth_title = synthesize_classical_symphony(clean_q, out_file)
        if synth_file:
            return synth_file, synth_title
        ia_file, ia_title = search_internet_archive_audio(clean_q, out_file)
        if ia_file:
            return ia_file, ia_title or clean_q
        fallback_classical = CLASSICAL_ARCHIVE[0]
        if download_file_direct(fallback_classical["url"], out_file):
            return out_file, fallback_classical["title"]

    # 6. Резервный ИИ-поиск и нормализация запроса через Gemini 3.8 Flash Medium (если ничего не найдено)
    if allow_ai_fallback:
        try:
            refined_q = refine_music_query_via_ai(clean_q)
            if refined_q and refined_q.lower() != clean_q.lower():
                sys.stderr.write(f"[MEDIA FINDER] AI Refinement triggered: '{clean_q}' -> '{refined_q}'. Retrying search...\n")
                ai_track, ai_title = find_and_download_music(refined_q, max_filesize=max_filesize, allow_ai_fallback=False)
                if ai_track:
                    return ai_track, ai_title or refined_q
        except Exception as ai_err:
            sys.stderr.write(f"[MEDIA FINDER] AI Refinement error: {ai_err}\n")

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
        "--extractor-args", "youtube:player_client=android",
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
