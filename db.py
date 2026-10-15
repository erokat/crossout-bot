import sqlite3
import os
import time
from config import DB_PATH

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    with get_db() as conn:
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
            message_id = COALESCE(excluded.message_id, confirmations.message_id),
            initiator = COALESCE(excluded.initiator, confirmations.initiator)
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
            if cid == 0:
                cur = conn.execute("SELECT 1 FROM handled_messages WHERE message_id = ?", (int(msg_id),))
            else:
                cur = conn.execute(
                    "SELECT 1 FROM handled_messages WHERE message_id = ? AND (chat_id = ? OR chat_id = 0)",
                    (int(msg_id), cid)
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

def configure_session_sqlite(session_path=None):
    """Ensure WAL journal mode and busy_timeout=10000 for Telethon SQLite session."""
    try:
        from config import SESSION_PATH
        path = session_path or SESSION_PATH
        session_file = path if path.endswith(".session") else (path + ".session")
        if os.path.exists(session_file):
            try:
                conn = sqlite3.connect(session_file, timeout=10.0)
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA busy_timeout=10000;")
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
                        try:
                            self._conn.execute("PRAGMA journal_mode=WAL;")
                            self._conn.execute("PRAGMA busy_timeout=10000;")
                        except Exception:
                            pass
                    return self._conn.cursor()
                SQLiteSession._cursor = safe_cursor
                SQLiteSession._wal_patched = True
        except Exception:
            pass
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
