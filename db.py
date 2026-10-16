import sqlite3
import os
import time
import json
import fcntl
import contextlib
from config import DB_PATH

@contextlib.contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
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
    requirements = [r.strip() for r in req_match.group(1).splitlines()[0].split(",") if r.strip()] if req_match else []

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
            if req and isinstance(req, str):
                all_requirements.add(req.strip())

    # 3. Fast dependency installation for missing requirements
    if install_requirements and all_requirements:
        for pkg in all_requirements:
            base_mod = pkg.split("[")[0].split("=")[0].split("<")[0].split(">")[0].strip().replace("-", "_")
            # Skip if already importable/installed
            try:
                if importlib.util.find_spec(base_mod) is not None:
                    continue
            except Exception:
                pass

            try:
                print(f"[DYNAMIC SKILLS] Installing missing requirement: {pkg}...")
                cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", pkg]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if res.returncode != 0 and "no such option" in (res.stderr or "").lower():
                    cmd = [sys.executable, "-m", "pip", "install", pkg]
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

# Initialize tables on import
try:
    init_db()
except Exception:
    pass

if __name__ == "__main__":
    init_db()
    print("Database initialized at", DB_PATH)
