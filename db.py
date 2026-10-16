import sqlite3
import os
import sys
import re
import time
import json
import fcntl
import contextlib
from config import DB_PATH

@contextlib.contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.create_function("lower", 1, lambda s: str(s).lower() if s is not None else "")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS dynamic_skills (
            skill_name TEXT PRIMARY KEY,
            file_path TEXT,
            triggers TEXT,
            description TEXT,
            requirements TEXT,
            code TEXT,
            updated_at REAL
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dynamic_skills_updated ON dynamic_skills(updated_at)")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            username TEXT,
            type TEXT,
            last_synced TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            chat_id INTEGER,
            message_id INTEGER,
            chat_title TEXT,
            sender_id INTEGER,
            sender_name TEXT,
            date TEXT,
            text TEXT,
            has_media INTEGER DEFAULT 0,
            media_type TEXT,
            media_path TEXT,
            PRIMARY KEY (chat_id, message_id)
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_date ON messages(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_chat ON messages(chat_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_msg_text ON messages(text)")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS confirmations (
            req_id TEXT PRIMARY KEY,
            question TEXT,
            status TEXT DEFAULT 'pending',
            comment TEXT,
            message_id INTEGER,
            initiator TEXT,
            created_at REAL,
            resolved_at REAL
        )
        """)
        for col, col_type in [("message_id", "INTEGER"), ("initiator", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE confirmations ADD COLUMN {col} {col_type}")
            except Exception:
                pass

        conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meme_hash TEXT UNIQUE,
            template_name TEXT,
            headline TEXT,
            file_path TEXT,
            sent_to TEXT,
            created_at REAL
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_memes_hash ON sent_memes(meme_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sent_memes_headline ON sent_memes(headline)")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT,
            fact TEXT,
            full_text TEXT,
            author TEXT,
            created_at REAL
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_memory_topic ON bot_memory(topic)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_memory_created ON bot_memory(created_at)")

        # Migration and schema for handled_messages with composite PRIMARY KEY (chat_id, message_id)
        cur = conn.execute("PRAGMA table_info(handled_messages)")
        cols_info = cur.fetchall()
        if cols_info:
            col_names = [c[1] for c in cols_info]
            pk_cols = [c[1] for c in cols_info if c[5] > 0]
            if "chat_id" not in col_names or set(pk_cols) != {"chat_id", "message_id"}:
                conn.execute("DROP TABLE IF EXISTS handled_messages_new")
                conn.execute("""
                CREATE TABLE handled_messages_new (
                    chat_id INTEGER DEFAULT 0,
                    message_id INTEGER,
                    handled_at REAL,
                    PRIMARY KEY (chat_id, message_id)
                )
                """)
                if "chat_id" in col_names:
                    conn.execute("""
                    INSERT OR IGNORE INTO handled_messages_new (chat_id, message_id, handled_at)
                    SELECT COALESCE(chat_id, 0), message_id, handled_at FROM handled_messages
                    """)
                else:
                    conn.execute("""
                    INSERT OR IGNORE INTO handled_messages_new (chat_id, message_id, handled_at)
                    SELECT 0, message_id, handled_at FROM handled_messages
                    """)
                conn.execute("DROP TABLE handled_messages")
                conn.execute("ALTER TABLE handled_messages_new RENAME TO handled_messages")
        else:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS handled_messages (
                chat_id INTEGER DEFAULT 0,
                message_id INTEGER,
                handled_at REAL,
                PRIMARY KEY (chat_id, message_id)
            )
            """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_handled_msgs ON handled_messages(chat_id, message_id)")

def save_chat(chat_id, title, username, chat_type, last_synced=None):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO chats (chat_id, title, username, type, last_synced)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            title = excluded.title,
            username = excluded.username,
            type = excluded.type,
            last_synced = COALESCE(excluded.last_synced, chats.last_synced)
        """, (chat_id, title, username, chat_type, last_synced))

def save_message(chat_id, message_id, chat_title, sender_id, sender_name, date, text, has_media=0, media_type=None, media_path=None):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO messages (chat_id, message_id, chat_title, sender_id, sender_name, date, text, has_media, media_type, media_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, message_id) DO UPDATE SET
            chat_title = excluded.chat_title,
            sender_name = excluded.sender_name,
            text = excluded.text,
            has_media = excluded.has_media,
            media_type = excluded.media_type,
            media_path = COALESCE(excluded.media_path, messages.media_path)
        """, (chat_id, message_id, chat_title, sender_id, sender_name, str(date), text, 1 if has_media else 0, media_type, media_path))

def create_confirmation(req_id, question, message_id=None, initiator=None):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO confirmations (req_id, question, status, comment, message_id, initiator, created_at, resolved_at)
        VALUES (?, ?, 'pending', NULL, ?, ?, ?, NULL)
        ON CONFLICT(req_id) DO UPDATE SET
            question = excluded.question,
            status = 'pending',
            comment = NULL,
            resolved_at = NULL,
            message_id = COALESCE(excluded.message_id, confirmations.message_id),
            initiator = COALESCE(excluded.initiator, confirmations.initiator),
            created_at = excluded.created_at
        """, (req_id, question, message_id, initiator, time.time()))

def update_confirmation_message_id(req_id, message_id):
    with get_db() as conn:
        conn.execute("UPDATE confirmations SET message_id = ? WHERE req_id = ?", (message_id, req_id))

def resolve_confirmation(req_id, status, comment=None):
    with get_db() as conn:
        conn.execute("""
        UPDATE confirmations
        SET status = ?, comment = COALESCE(?, comment), resolved_at = ?
        WHERE req_id = ?
        """, (status.lower(), comment, time.time(), req_id))

def get_confirmation(req_id):
    with get_db() as conn:
        cursor = conn.execute("SELECT req_id, question, status, comment, message_id, initiator, created_at, resolved_at FROM confirmations WHERE req_id = ?", (req_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "req_id": row[0],
            "question": row[1],
            "status": row[2],
            "comment": row[3],
            "message_id": row[4],
            "initiator": row[5],
            "created_at": row[6],
            "resolved_at": row[7]
        }

def get_latest_pending_confirmation():
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT req_id, question, status, comment, message_id, initiator, created_at, resolved_at FROM confirmations WHERE status = 'pending' ORDER BY created_at DESC LIMIT 1"
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "req_id": row[0],
            "question": row[1],
            "status": row[2],
            "comment": row[3],
            "message_id": row[4],
            "initiator": row[5],
            "created_at": row[6],
            "resolved_at": row[7]
        }

def save_dynamic_skill(skill_name, file_path, triggers, description, requirements, code):
    """
    Saves or updates dynamic skill in SQLite database.
    triggers and requirements can be passed as list/set/tuple or JSON/string.
    """
    if isinstance(triggers, (list, tuple, set)):
        triggers_str = json.dumps(list(triggers), ensure_ascii=False)
    else:
        triggers_str = str(triggers or "[]")

    if isinstance(requirements, (list, tuple, set)):
        reqs_str = json.dumps(list(requirements), ensure_ascii=False)
    else:
        reqs_str = str(requirements or "[]")

    with get_db() as conn:
        conn.execute("""
        INSERT INTO dynamic_skills (skill_name, file_path, triggers, description, requirements, code, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(skill_name) DO UPDATE SET
            file_path = excluded.file_path,
            triggers = excluded.triggers,
            description = excluded.description,
            requirements = excluded.requirements,
            code = excluded.code,
            updated_at = excluded.updated_at
        """, (skill_name, file_path, triggers_str, description, reqs_str, code, time.time()))

def get_dynamic_skill(skill_name):
    with get_db() as conn:
        cur = conn.execute(
            "SELECT skill_name, file_path, triggers, description, requirements, code, updated_at FROM dynamic_skills WHERE skill_name = ?",
            (skill_name,)
        )
        row = cur.fetchone()
        if not row:
            return None
        try:
            triggers = json.loads(row[2]) if row[2] else []
        except Exception:
            triggers = [t.strip() for t in (row[2] or "").split(",") if t.strip()]
        try:
            requirements = json.loads(row[4]) if row[4] else []
        except Exception:
            requirements = [r.strip() for r in (row[4] or "").split(",") if r.strip()]
        return {
            "skill_name": row[0],
            "file_path": row[1],
            "triggers": triggers,
            "description": row[3],
            "requirements": requirements,
            "code": row[5],
            "updated_at": row[6]
        }

def list_dynamic_skills():
    with get_db() as conn:
        cur = conn.execute("SELECT skill_name, file_path, triggers, description, requirements, code, updated_at FROM dynamic_skills ORDER BY updated_at DESC")
        skills = []
        for row in cur.fetchall():
            try:
                triggers = json.loads(row[2]) if row[2] else []
            except Exception:
                triggers = [t.strip() for t in (row[2] or "").split(",") if t.strip()]
            try:
                requirements = json.loads(row[4]) if row[4] else []
            except Exception:
                requirements = [r.strip() for r in (row[4] or "").split(",") if r.strip()]
            skills.append({
                "skill_name": row[0],
                "file_path": row[1],
                "triggers": triggers,
                "description": row[3],
                "requirements": requirements,
                "code": row[5],
                "updated_at": row[6]
            })
        return skills

def delete_dynamic_skill(skill_name):
    with get_db() as conn:
        conn.execute("DELETE FROM dynamic_skills WHERE skill_name = ?", (skill_name,))

STD_LIB_MODULES = {
    "os", "sys", "re", "time", "json", "math", "random", "datetime", "asyncio",
    "shutil", "urllib", "pathlib", "tempfile", "hashlib", "subprocess", "io",
    "typing", "collections", "itertools", "functools", "sqlite3", "threading",
    "multiprocessing", "traceback", "copy", "glob", "socket", "http", "logging",
    "string", "struct", "base64", "uuid", "inspect", "unittest", "fcntl",
    "errno", "gc", "signal", "ctypes", "select", "csv", "xml", "email",
    "contextlib", "queue", "operator", "decimal", "fractions", "pickle", "pprint",
    "enum", "dataclasses", "abc", "typing_extensions", "warnings", "platform",
    "builtins", "__future__", "calendar", "zipfile", "tarfile", "gzip", "bz2", "zlib"
}

def clean_requirement_name(req):
    if not req or not isinstance(req, str):
        return None
    r = req.strip()
    # Strip any leading 'import ' or 'from '
    r = re.sub(r"^(?:import|from)\s+", "", r).strip()
    # Strip comments if any
    r = r.split("#")[0].strip()
    if not r:
        return None
    # Extract base package name before version specifiers or extras
    base = re.split(r"[=<>[\]~!\s]", r)[0].strip().replace("-", "_").lower()
    if not base:
        return None
    # Never install python built-in or stdlib modules
    if base in STD_LIB_MODULES or base in getattr(sys, "stdlib_module_names", set()) or base in sys.builtin_module_names:
        return None
    # Check if any part matches internal project modules
    words = re.findall(r"\b[a-zA-Z0-9_]+\b", r.lower())
    internal_mods = {"config", "db", "meme_generator", "meme_engine", "dynamic_agent", "photo_editor", "media_finder", "gdrive", "send", "wait_for_yarik", "ask_owner", "chess_engine", "internal_module"}
    if any(w in internal_mods for w in words):
        return None
    # Validate against valid PEP 508 requirement syntax (name[extras] op version)
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*(?:\[[a-zA-Z0-9_.,-]+\])?(?:\s*(?:==|>=|<=|~=|!=|<|>|===)\s*[a-zA-Z0-9_.*+-]+)?$", r):
        return None
    return r

def parse_skill_metadata_from_code(code, fallback_name="skill", fallback_desc="Dynamic Skill"):
    import re
    if not code:
        return fallback_name, fallback_desc, [], []

    slug_match = re.search(r'(?:#|"""|\'\'\'|\b)(?:SKILL_NAME|EXTENSION):\s*([a-zA-Z0-9_-]+)', code)
    skill_name = slug_match.group(1).strip() if slug_match else fallback_name

    desc_match = re.search(r'(?:#|"""|\'\'\'|\b)DESCRIPTION:\s*(.+)', code)
    if desc_match:
        skill_desc = desc_match.group(1).strip().splitlines()[0]
    else:
        slug_pipe = re.search(r'(?:#|"""|\'\'\'|\b)(?:SKILL_NAME|EXTENSION):\s*[a-zA-Z0-9_-]+\s*\|\s*(.+)', code)
        skill_desc = slug_pipe.group(1).strip().splitlines()[0] if slug_pipe else fallback_desc

    trig_match = re.search(r'(?:#|"""|\'\'\'|\b)TRIGGERS:\s*(.+)', code)
    if trig_match:
        triggers = [t.strip().lower() for t in trig_match.group(1).splitlines()[0].split(",") if t.strip()]
    else:
        stop_words = {
            "бот", "ботяра", "ботик", "робот", "любую", "дату", "дата", "дате", "даты",
            "день", "дня", "днях", "время", "регионе", "просто", "сделай", "напиши", "создай", "данные"
        }
        triggers = [w for w in re.findall(r"\b[а-яa-z]{4,}\b", skill_desc.lower()) if len(w) >= 4 and w not in stop_words]

    req_match = re.search(r'(?:#|"""|\'\'\'|\b)REQUIREMENTS:\s*(.+)', code)
    if req_match:
        raw_reqs = [r.strip() for r in req_match.group(1).splitlines()[0].split(",") if r.strip()]
        requirements = []
        for rr in raw_reqs:
            cleaned = clean_requirement_name(rr)
            if cleaned and cleaned not in requirements:
                requirements.append(cleaned)
    else:
        requirements = []

    return skill_name, skill_desc, triggers, requirements

def restore_dynamic_skills(skills_dir=None, install_requirements=True):
    """
    Two-way synchronization of dynamic skills:
    1. Scans skills/ folder on disk and seeds any pre-existing or git-tracked .py files into SQLite.
    2. Restores all dynamic skill .py files from SQLite into the skills/ folder.
    3. Checks missing pip requirements and installs them with strict timeout <= 45s.
    """
    import subprocess
    import sys
    import importlib.util
    base_dir = os.path.dirname(os.path.abspath(__file__))
    s_dir = skills_dir or os.path.join(base_dir, "skills")
    os.makedirs(s_dir, exist_ok=True)
    init_file = os.path.join(s_dir, "__init__.py")
    if not os.path.exists(init_file):
        with open(init_file, "w", encoding="utf-8") as f:
            f.write("# -*- coding: utf-8 -*-\n")

    # 0. Sync missing skills from GitHub repository
    try:
        from github_sync import sync_skills_from_github
        gh_synced = sync_skills_from_github(skills_dir=s_dir, install_requirements=install_requirements, timeout=10)
        if gh_synced > 0:
            print(f"[DYNAMIC SKILLS] Synced {gh_synced} skill(s) from GitHub repository.")
    except Exception as ghe:
        print(f"[DYNAMIC SKILLS] GitHub sync notice: {ghe}")

    # 1. Seed any local .py skill files from disk into SQLite dynamic_skills table
    if os.path.exists(s_dir):
        for fname in os.listdir(s_dir):
            if fname.endswith(".py") and fname != "__init__.py":
                fp = os.path.join(s_dir, fname)
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        file_code = f.read()
                    default_slug = os.path.splitext(fname)[0]
                    s_name, s_desc, s_trig, s_req = parse_skill_metadata_from_code(file_code, fallback_name=default_slug)
                    existing_entry = get_dynamic_skill(s_name)
                    if not existing_entry or existing_entry.get("code") != file_code:
                        rel_path = os.path.relpath(fp, base_dir) if fp.startswith(base_dir) else f"skills/{fname}"
                        save_dynamic_skill(
                            skill_name=s_name,
                            file_path=rel_path,
                            triggers=s_trig,
                            description=s_desc,
                            requirements=s_req,
                            code=file_code
                        )
                        print(f"[DYNAMIC SKILLS] Seeded '{s_name}' from disk into SQLite registry.")
                except Exception as se:
                    print(f"[DYNAMIC SKILLS] Warning seeding {fname}: {se}")

    # 2. Restore all dynamic skills from SQLite into skills/ directory
    skills = list_dynamic_skills()
    restored_count = 0
    all_requirements = set()

    for skill in skills:
        fn = os.path.basename(skill["file_path"] or f"{skill['skill_name']}.py")
        if not fn.endswith(".py"):
            fn += ".py"
        target_path = os.path.join(s_dir, fn)
        code = skill.get("code") or ""
        should_write = True
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    if f.read() == code:
                        should_write = False
            except Exception:
                should_write = True
        if should_write and code:
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(code)
            restored_count += 1

        for req in skill.get("requirements", []):
            cleaned = clean_requirement_name(req)
            if cleaned:
                all_requirements.add(cleaned)

    # 3. Fast dependency installation for missing requirements
    if install_requirements and all_requirements:
        for pkg in all_requirements:
            pkg = clean_requirement_name(pkg)
            if not pkg:
                continue
            base_mod = pkg.split("[")[0].split("=")[0].split("<")[0].split(">")[0].strip().replace("-", "_")
            # Skip if already importable/installed
            try:
                if importlib.util.find_spec(base_mod) is not None:
                    continue
            except Exception:
                pass

            try:
                print(f"[DYNAMIC SKILLS] Installing missing requirement: {pkg}...")
                cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--break-system-packages", pkg]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if res.returncode != 0 and "no such option" in (res.stderr or "").lower():
                    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", pkg]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if res.returncode == 0:
                    print(f"[DYNAMIC SKILLS] Successfully installed requirement: {pkg}")
                else:
                    print(f"[DYNAMIC SKILLS] Pip warning for {pkg}: {res.stderr[:150]}")
            except Exception as e:
                print(f"[DYNAMIC SKILLS] Warning: failed to install {pkg}: {e}")

    print(f"[DYNAMIC SKILLS] restore_dynamic_skills complete: {restored_count} files written, {len(skills)} skills active.")
    return restored_count


def get_kv(key, default=None):
    with get_db() as conn:
        cursor = conn.execute("SELECT value FROM kv_store WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_kv(key, value):
    with get_db() as conn:
        conn.execute("INSERT INTO kv_store (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))

def is_message_handled(msg_id, chat_id=0):
    if not msg_id:
        return False
    try:
        cid = int(chat_id) if chat_id is not None else 0
        with get_db() as conn:
            cur = conn.execute(
                "SELECT 1 FROM handled_messages WHERE chat_id = ? AND message_id = ?",
                (cid, int(msg_id))
            )
            return cur.fetchone() is not None
    except Exception:
        return False

is_handled = is_message_handled

def mark_message_handled(msg_id, chat_id=0):
    if not msg_id:
        return
    try:
        cid = int(chat_id) if chat_id is not None else 0
        with get_db() as conn:
            conn.execute("""
            INSERT INTO handled_messages (chat_id, message_id, handled_at)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, message_id) DO NOTHING
            """, (cid, int(msg_id), time.time()))
    except Exception:
        pass

add_handled_id = mark_message_handled

def unmark_message_handled(msg_id, chat_id=0):
    if not msg_id:
        return
    try:
        cid = int(chat_id) if chat_id is not None else 0
        with get_db() as conn:
            conn.execute("DELETE FROM handled_messages WHERE chat_id = ? AND message_id = ?", (cid, int(msg_id)))
    except Exception:
        pass


def configure_session_sqlite(session_path=None):
    """Ensure WAL journal mode, autocommit, and busy_timeout=10000 for Telethon SQLite session."""
    try:
        from config import SESSION_PATH
        path = session_path or SESSION_PATH
        session_file = path if path.endswith(".session") else (path + ".session")
        if os.path.exists(session_file):
            try:
                conn = sqlite3.connect(session_file, timeout=10.0)
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=10000;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.commit()
                conn.close()
            except Exception:
                pass
        try:
            from telethon.sessions import SQLiteSession
            if not getattr(SQLiteSession, "_wal_patched", False):
                def safe_cursor(self):
                    if self._conn is None:
                        self._conn = sqlite3.connect(self.filename, timeout=10.0, check_same_thread=False)
                        self._conn.isolation_level = None  # Autocommit: immediately releases write locks
                        try:
                            self._conn.execute("PRAGMA journal_mode=WAL;")
                            self._conn.execute("PRAGMA busy_timeout=10000;")
                            self._conn.execute("PRAGMA synchronous=NORMAL;")
                        except Exception:
                            pass
                    return self._conn.cursor()

                def safe_create_table(c, *definitions):
                    for definition in definitions:
                        c.execute('create table if not exists {}'.format(definition))

                SQLiteSession._cursor = safe_cursor
                SQLiteSession._create_table = staticmethod(safe_create_table)
                SQLiteSession._wal_patched = True
        except Exception:
            pass
    except Exception:
        pass

@contextlib.contextmanager
def session_flock(lock_path=None, timeout=10.0):
    """File lock context manager with timeout retry to coordinate Telethon session access."""
    try:
        from config import LOCK_PATH
        lp = lock_path or LOCK_PATH
    except Exception:
        lp = "send.lock"
    lock_file = None
    try:
        lock_file = open(lp, "w")
        start = time.time()
        locked = False
        while time.time() - start < timeout:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except (BlockingIOError, OSError):
                time.sleep(0.02)
        if not locked:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                locked = True
            except Exception:
                pass
        yield
    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_file.close()
            except Exception:
                pass


def is_meme_already_sent(meme_hash=None, headline=None, max_age_seconds=7200):
    if not meme_hash and not headline:
        return False
    with get_db() as conn:
        now = time.time()
        cutoff = now - max_age_seconds if max_age_seconds else 0
        if meme_hash:
            cur = conn.execute("SELECT 1 FROM sent_memes WHERE meme_hash = ? AND created_at > ?", (meme_hash, cutoff))
            if cur.fetchone():
                return True
        if headline:
            cur = conn.execute("SELECT 1 FROM sent_memes WHERE LOWER(TRIM(headline)) = LOWER(TRIM(?)) AND created_at > ?", (headline, cutoff))
            if cur.fetchone():
                return True
    return False

def record_sent_meme(meme_hash, template_name, headline, file_path, sent_to=""):
    with get_db() as conn:
        conn.execute("""
        INSERT INTO sent_memes (meme_hash, template_name, headline, file_path, sent_to, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(meme_hash) DO NOTHING
        """, (meme_hash, template_name, headline, file_path, sent_to, time.time()))

def get_last_sent_meme(sent_to=None):
    with get_db() as conn:
        if sent_to:
            cur = conn.execute("SELECT file_path, headline FROM sent_memes WHERE sent_to = ? ORDER BY id DESC LIMIT 1", (sent_to,))
        else:
            cur = conn.execute("SELECT file_path, headline FROM sent_memes ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return {"file_path": row[0], "headline": row[1]} if row else None


# ----------------- BOT LONG-TERM MEMORY ENGINE -----------------

MEMORIES_FILE = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "bot_memories.json")

def save_bot_memory(fact, topic="", full_text="", author=""):
    if not fact:
        return False
    fact = str(fact).strip()
    topic = str(topic).strip() if topic else ""
    full_text = str(full_text).strip() if full_text else fact
    author = str(author).strip() if author else ""

    if not topic:
        about_match = re.search(r"(?:про|о|об|насчет|по поводу)\s+([а-яa-z0-9\s]+?)(?:\s+(?:связан|это|что|было|много|мало)|[,\.!?:\n\"]|$)", full_text, re.IGNORECASE)
        if about_match:
            topic = about_match.group(1).strip()[:50]
        else:
            quotes = re.findall(r'["«]([^"»]+)["»]', full_text)
            if quotes:
                topic = quotes[0][:50]
            else:
                words = [w for w in re.findall(r'\b[а-яa-z0-9]{4,}\b', full_text.lower()) if w not in {"запомни", "сделай", "пожалуйста", "короче", "смотри"}]
                topic = " ".join(words[:3])

    with get_db() as conn:
        conn.execute("""
        INSERT INTO bot_memory (topic, fact, full_text, author, created_at)
        VALUES (?, ?, ?, ?, ?)
        """, (topic, fact, full_text, author, time.time()))

    try:
        sync_memories_to_disk()
    except Exception:
        pass
    return True

def sync_memories_to_disk():
    with get_db() as conn:
        cur = conn.execute("SELECT id, topic, fact, full_text, author, created_at FROM bot_memory ORDER BY id ASC")
        rows = [
            {"id": r[0], "topic": r[1], "fact": r[2], "full_text": r[3], "author": r[4], "created_at": r[5]}
            for r in cur.fetchall()
        ]
    with open(MEMORIES_FILE, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

def restore_bot_memories():
    if not os.path.exists(MEMORIES_FILE):
        return 0
    try:
        with open(MEMORIES_FILE, "r", encoding="utf-8") as f:
            rows = json.load(f)
        if not rows or not isinstance(rows, list):
            return 0
        with get_db() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM bot_memory")
            count = cur.fetchone()[0]
            if count == 0:
                for r in rows:
                    conn.execute("""
                    INSERT INTO bot_memory (topic, fact, full_text, author, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """, (r.get("topic", ""), r.get("fact", ""), r.get("full_text", ""), r.get("author", ""), r.get("created_at", time.time())))
                print(f"[MEMORY] Restored {len(rows)} memories from {MEMORIES_FILE}")
                return len(rows)
    except Exception as e:
        print(f"[MEMORY WARNING] Error restoring memories: {e}")
    return 0

def get_all_memories(limit=25):
    with get_db() as conn:
        cur = conn.execute(
            "SELECT id, topic, fact, full_text, author, created_at FROM bot_memory ORDER BY id DESC LIMIT ?",
            (limit,)
        )
        return [
            {"id": r[0], "topic": r[1], "fact": r[2], "full_text": r[3], "author": r[4], "created_at": r[5]}
            for r in cur.fetchall()
        ]

def get_relevant_memories(query="", limit=5):
    if not query:
        return get_all_memories(limit=limit)

    q_words = [w.lower() for w in re.findall(r'\b[а-яa-z0-9]{3,}\b', query.lower()) if w not in {"бот", "сделай", "мем", "картинку", "скинь", "про", "как", "что", "это", "нарисуй", "покажи"}]
    if not q_words:
        return get_all_memories(limit=limit)

    with get_db() as conn:
        conditions = []
        params = []
        for w in q_words:
            stem = w[:-1] if len(w) >= 5 else w
            conditions.append("(lower(topic) LIKE ? OR lower(fact) LIKE ? OR lower(full_text) LIKE ?)")
            p = f"%{stem}%"
            params.extend([p, p, p])

        sql = f"SELECT id, topic, fact, full_text, author, created_at FROM bot_memory WHERE {' OR '.join(conditions)} ORDER BY id DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(sql, params)
        rows = cur.fetchall()
        if rows:
            return [
                {"id": r[0], "topic": r[1], "fact": r[2], "full_text": r[3], "author": r[4], "created_at": r[5]}
                for r in rows
            ]
    return get_all_memories(limit=limit)

def format_memory_context(query="", limit=4):
    mems = get_relevant_memories(query=query, limit=limit)
    if not mems:
        return ""
    lines = ["[ДОЛГОВРЕМЕННАЯ ПАМЯТЬ БОТА (ФАКТЫ И ПРАВИЛА, КОТОРЫЕ ПРОСИЛИ ЗАПОМНИТЬ ПОЛЬЗОВАТЕЛИ)]:"]
    for m in mems:
        author_str = f" (от {m['author']})" if m.get("author") else ""
        topic_str = f"Тема '{m['topic']}': " if m.get("topic") else ""
        lines.append(f"- {topic_str}{m['fact']}{author_str}")
    return "\n".join(lines)

def delete_bot_memory(query):
    if not query:
        return 0
    q = str(query).strip().lower()
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM bot_memory WHERE lower(topic) LIKE ? OR lower(fact) LIKE ? OR lower(full_text) LIKE ?",
            (f"%{q}%", f"%{q}%", f"%{q}%")
        )
        deleted = cur.rowcount
        if deleted == 0:
            q_words = [w for w in re.findall(r'\b[а-яa-z0-9]{4,}\b', q) if w not in {"забудь", "удали", "памяти", "информацию", "про"}]
            if q_words:
                conds = []
                params = []
                for w in q_words:
                    stem = w[:-1] if len(w) >= 5 else w
                    conds.append("(lower(topic) LIKE ? OR lower(fact) LIKE ? OR lower(full_text) LIKE ?)")
                    p = f"%{stem}%"
                    params.extend([p, p, p])
                cur = conn.execute(f"DELETE FROM bot_memory WHERE {' AND '.join(conds)}", params)
                deleted = cur.rowcount
                if deleted == 0:
                    cur = conn.execute(f"DELETE FROM bot_memory WHERE {' OR '.join(conds)}", params)
                    deleted = cur.rowcount

    if deleted:
        try:
            sync_memories_to_disk()
        except Exception:
            pass
    return deleted

def clear_all_bot_memories():
    with get_db() as conn:
        conn.execute("DELETE FROM bot_memory")
    try:
        if os.path.exists(MEMORIES_FILE):
            os.remove(MEMORIES_FILE)
    except Exception:
        pass
    return True

# Initialize tables on import
try:
    init_db()
    restore_bot_memories()
except Exception:
    pass

if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
