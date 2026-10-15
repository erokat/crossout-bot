import os
import sys
import json
import time
import mimetypes
import urllib.request
import urllib.parse
from db import get_kv, set_kv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "gdrive_token.json")
CONFIG_FILE = os.path.join(BASE_DIR, "gdrive_config.json")

def _load_local_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

_CONFIG = _load_local_config()
RENDER_SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", _CONFIG.get("RENDER_SERVICE_ID", ""))
RENDER_API_KEY = os.environ.get("RENDER_API_KEY", _CONFIG.get("RENDER_API_KEY", ""))

def get_credentials():
    client_id = os.environ.get("GDRIVE_CLIENT_ID", _CONFIG.get("GDRIVE_CLIENT_ID", "")).strip()
    client_secret = os.environ.get("GDRIVE_CLIENT_SECRET", _CONFIG.get("GDRIVE_CLIENT_SECRET", "")).strip()
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "https://yarik-crossout-userbot.onrender.com").rstrip("/")
    redirect_uri = f"{render_url}/oauth/google/callback"
    return client_id, client_secret, redirect_uri


def get_auth_url():
    client_id, _, redirect_uri = get_credentials()
    if not client_id:
        return None
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/drive.file",
        "access_type": "offline",
        "prompt": "consent"
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

def save_refresh_token_to_render(refresh_token):
    """Персистентно сохраняет GDRIVE_REFRESH_TOKEN в переменные окружения Render через API."""
    try:
        # 1. Получаем текущие переменные
        get_url = f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars"
        headers = {
            "Authorization": f"Bearer {RENDER_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(get_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        current_vars = {}
        for item in data:
            ev = item.get("envVar", {})
            if "key" in ev and "value" in ev:
                current_vars[ev["key"]] = ev["value"]

        current_vars["GDRIVE_REFRESH_TOKEN"] = refresh_token

        # 2. Обновляем переменные через PUT
        put_payload = [{"key": k, "value": v} for k, v in current_vars.items()]
        put_data = json.dumps(put_payload).encode("utf-8")
        put_req = urllib.request.Request(get_url, data=put_data, headers=headers, method="PUT")
        with urllib.request.urlopen(put_req, timeout=15) as put_resp:
            print("[GDRIVE] GDRIVE_REFRESH_TOKEN successfully saved to Render environment variables!")
            return True
    except Exception as e:
        sys.stderr.write(f"[GDRIVE WARNING] Could not persist token to Render env-vars: {e}\n")
        return False

def exchange_code(code):
    client_id, client_secret, redirect_uri = get_credentials()
    if not client_id or not client_secret:
        return False, "GDRIVE_CLIENT_ID or GDRIVE_CLIENT_SECRET not set"

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(token_url, data=encoded_data, headers={"Content-Type": "application/x-www-form-urlencoded"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        
        refresh_token = res.get("refresh_token")
        access_token = res.get("access_token")
        expires_in = res.get("expires_in", 3600)

        if refresh_token:
            set_kv("gdrive_refresh_token", refresh_token)
            # Сохраняем в локальный JSON
            try:
                with open(TOKEN_FILE, "w", encoding="utf-8") as tf:
                    json.dump({"refresh_token": refresh_token}, tf)
            except Exception:
                pass
            # Сохраняем на Render через API
            save_refresh_token_to_render(refresh_token)

        if access_token:
            set_kv("gdrive_access_token", access_token)
            set_kv("gdrive_token_expires_at", str(time.time() + expires_in - 60))

        # Check and ensure memes folder is initialized
        folder_id = ensure_folder(access_token, "memes")
        return True, f"Google Drive connected! Folder 'memes' ID: {folder_id}"
    except Exception as e:
        sys.stderr.write(f"[GDRIVE ERROR] Failed to exchange code: {e}\n")
        return False, str(e)

def get_valid_access_token():
    # 1. Check cached access token
    access_token = get_kv("gdrive_access_token")
    expires_at = float(get_kv("gdrive_token_expires_at", "0"))
    if access_token and time.time() < expires_at:
        return access_token

    # 2. Check refresh token in KV, file, or ENV
    refresh_token = get_kv("gdrive_refresh_token") or os.environ.get("GDRIVE_REFRESH_TOKEN", "").strip()

    if not refresh_token and os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as tf:
                td = json.load(tf)
                refresh_token = td.get("refresh_token", "").strip()
        except Exception:
            pass

    if not refresh_token and RENDER_API_KEY and RENDER_SERVICE_ID:
        try:
            req = urllib.request.Request(

                f"https://api.render.com/v1/services/{RENDER_SERVICE_ID}/env-vars",
                headers={"Authorization": f"Bearer {RENDER_API_KEY}", "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                for item in data:
                    ev = item.get("envVar", {})
                    if ev.get("key") == "GDRIVE_REFRESH_TOKEN":
                        refresh_token = ev.get("value", "").strip()
                        if refresh_token:
                            set_kv("gdrive_refresh_token", refresh_token)
                            try:
                                with open(TOKEN_FILE, "w", encoding="utf-8") as tf:
                                    json.dump({"refresh_token": refresh_token}, tf)
                            except Exception:
                                pass
                            break
        except Exception:
            pass

    if not refresh_token:

        return None

    client_id, client_secret, _ = get_credentials()
    if not client_id or not client_secret:
        return None

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token"
    }
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(token_url, data=encoded_data, headers={"Content-Type": "application/x-www-form-urlencoded"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        new_token = res.get("access_token")
        expires_in = res.get("expires_in", 3600)
        if new_token:
            set_kv("gdrive_access_token", new_token)
            set_kv("gdrive_token_expires_at", str(time.time() + expires_in - 60))
            return new_token
    except Exception as e:
        sys.stderr.write(f"[GDRIVE ERROR] Token refresh failed: {e}\n")
    return None

def ensure_folder(access_token=None, folder_name="memes"):
    if not access_token:
        access_token = get_valid_access_token()
    if not access_token:
        return None

    cached_folder = get_kv(f"gdrive_{folder_name}_folder_id")
    if cached_folder:
        return cached_folder

    # Query for existing folder
    query = urllib.parse.quote(f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    search_url = f"https://www.googleapis.com/drive/v3/files?q={query}&fields=files(id,name)"
    req = urllib.request.Request(search_url, headers={"Authorization": f"Bearer {access_token}"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        files = data.get("files", [])
        if files:
            folder_id = files[0]["id"]
            set_kv(f"gdrive_{folder_name}_folder_id", folder_id)
            return folder_id
    except Exception as e:
        sys.stderr.write(f"[GDRIVE ERROR] Search folder {folder_name} failed: {e}\n")

    # Create folder
    create_url = "https://www.googleapis.com/drive/v3/files"
    meta = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder"
    }
    body = json.dumps(meta).encode("utf-8")
    req = urllib.request.Request(create_url, data=body, headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        folder_id = data.get("id")
        if folder_id:
            set_kv(f"gdrive_{folder_name}_folder_id", folder_id)
            print(f"[GDRIVE] Created new folder '{folder_name}' with ID: {folder_id}")
            return folder_id
    except Exception as e:
        sys.stderr.write(f"[GDRIVE ERROR] Create folder {folder_name} failed: {e}\n")

    return None

def ensure_memes_folder(access_token=None):
    return ensure_folder(access_token, "memes")

def upload_file_to_drive(file_path, folder_type="memes"):
    """
    Выгружает файл на Google Диск в соответствующую папку (memes, music, videos, photos).
    """
    if not os.path.exists(file_path):
        return None

    access_token = get_valid_access_token()
    if not access_token:
        print("[GDRIVE] Not connected. Connect via https://yarik-crossout-userbot.onrender.com/gdrive/connect")
        return None

    folder_id = ensure_folder(access_token, folder_type)
    if not folder_id:
        folder_id = ensure_memes_folder(access_token)
    if not folder_id:
        return None

    filename = os.path.basename(file_path)
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "image/png"

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    boundary = "-------314159265358979323846"
    metadata = {
        "name": filename,
        "parents": [folder_id]
    }

    body = bytearray()
    body.extend(f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode("utf-8"))
    body.extend(json.dumps(metadata).encode("utf-8"))
    body.extend(f"\r\n--{boundary}\r\nContent-Type: {mime_type}\r\n\r\n".encode("utf-8"))
    body.extend(file_bytes)
    body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

    upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink"
    req = urllib.request.Request(upload_url, data=bytes(body), headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": f"multipart/related; boundary={boundary}"
    })

    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        print(f"[GDRIVE] Successfully uploaded {filename} to folder '{folder_type}' (ID: {res.get('id')})")
        return res
    except Exception as e:
        sys.stderr.write(f"[GDRIVE ERROR] Upload file failed for {filename}: {e}\n")
        return None

def upload_and_cleanup(file_path, folder_type="memes"):
    """
    Выгружает файл на Google Диск, а затем удаляет локальную копию, освобождая память.
    """
    res = upload_file_to_drive(file_path, folder_type)
    if res and os.path.exists(file_path):
        if "saved_memes" in os.path.abspath(file_path):
            print(f"[STORAGE PRESERVED] Kept local file {file_path} in saved_memes after Google Drive upload.")
            return res
        try:
            os.remove(file_path)
            print(f"[STORAGE CLEANUP] Removed local file {file_path} after successful Google Drive upload.")
        except Exception as e:
            print(f"[STORAGE CLEANUP WARNING] Could not remove {file_path}: {e}")
    return res
