# -*- coding: utf-8 -*-
"""
kling_client.py - Official Kling AI MCP & Video Generation Integration.

Capabilities:
1. Connects to Kling Remote MCP server (https://kling.ai/mcp) via JSON-RPC 2.0.
2. Supports text-to-video (kling_generate_video) and image-to-video (kling_generate_video_from_image).
3. Asynchronous execution in background thread:
   submit task -> poll task status -> download temporary MP4 -> send via send.py -> cleanup.
4. Checks credits balance before generation.
5. Strict Owner permission: if requested by anyone other than owner (e.g. Yarik),
   triggers ask_owner.py and proceeds only upon owner approval.
"""

import os
import sys
import json
import time
import base64
import urllib.request
import urllib.error
import urllib.parse
import threading
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
VIDEO_DIR = os.path.join(MEDIA_DIR, "videos")
DEFAULT_MCP_URL = "https://kling.mcp.acedata.cloud/mcp"
GENAPI_BASE_URL = "https://api.gen-api.ru/api/v1"
DEFAULT_TIMEOUT = 30


def get_kling_config():
    """Reads KLING_API_KEY / KLING_TOKEN and MCP URL from environment variables."""
    token = os.environ.get("KLING_API_KEY", "").strip() or os.environ.get("KLING_TOKEN", "").strip()
    mcp_url = os.environ.get("KLING_MCP_URL", "").strip() or DEFAULT_MCP_URL
    return token, mcp_url


def is_gen_api_token(token):
    """Detects Gen-API token format (starts with sk-)."""
    return bool(token and (token.startswith("sk-") or "gen-api" in os.environ.get("KLING_MCP_URL", "")))


def mcp_rpc_call(method, params=None, timeout=DEFAULT_TIMEOUT):
    """
    Executes a JSON-RPC 2.0 call to the Kling MCP endpoint.
    """
    token, mcp_url = get_kling_config()
    if not token:
        return {"error": {"code": -32000, "message": "KLING_API_KEY / KLING_TOKEN is not configured in environment."}}

    payload = {
        "jsonrpc": "2.0",
        "id": f"kling-{int(time.time() * 1000)}",
        "method": method,
        "params": params or {}
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {token}",
        "User-Agent": "CrossoutBot-KlingMCP/1.0"
    }

    req = urllib.request.Request(mcp_url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as he:
        err_msg = he.read().decode("utf-8", errors="ignore")[:300]
        return {"error": {"code": he.code, "message": f"HTTP {he.code}: {err_msg}"}}
    except Exception as e:
        return {"error": {"code": -32099, "message": str(e)}}


def call_kling_tool(tool_name, arguments=None, timeout=DEFAULT_TIMEOUT):
    """Calls a specific tool on the Kling MCP server via tools/call."""
    params = {
        "name": tool_name,
        "arguments": arguments or {}
    }
    resp = mcp_rpc_call("tools/call", params, timeout=timeout)
    if "error" in resp:
        return False, resp["error"].get("message", "Unknown MCP error")

    result = resp.get("result", {})
    if isinstance(result, dict) and result.get("isError"):
        content_items = result.get("content", [])
        err_texts = [c.get("text", "") for c in content_items if isinstance(c, dict) and c.get("type") == "text"]
        err_msg = " ".join(err_texts) if err_texts else "MCP tool error"
        return False, err_msg
    return True, result


def check_kling_credits():
    """
    Checks the remaining credits or balance for the authenticated Kling / Gen-API account.
    Returns (True, credits_info) or (False, error_msg).
    """
    token, _ = get_kling_config()
    if not token:
        return False, "KLING_API_KEY is not configured in environment."

    if is_gen_api_token(token):
        url = f"{GENAPI_BASE_URL}/user"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "CrossoutBot/1.0"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
                bal = data.get("balance", 0)
                name = data.get("name", "")
                return True, {"balance": bal, "credits": bal, "name": name, "service": "gen-api"}
        except urllib.error.HTTPError as he:
            return False, f"Gen-API HTTP {he.code}"
        except Exception as e:
            return False, f"Gen-API error: {e}"

    # Standard MCP fallback
    success, res = call_kling_tool("kling_get_credits", {})
    if not success:
        success, res = call_kling_tool("kling_account_info", {})
        if not success:
            success, res = call_kling_tool("kling_list_models", {})
            if not success:
                return False, str(res)
    return True, res


def submit_text_to_video(prompt, model="kling-v1", duration="5s", aspect_ratio="16:9"):
    """
    Submits a text-to-video generation task to Kling via Gen-API or MCP.
    Returns (True, task_id) or (False, error_message).
    """
    token, _ = get_kling_config()
    if not token:
        return False, "KLING_API_KEY is not configured."

    dur_val = 5
    if isinstance(duration, int):
        dur_val = duration
    elif isinstance(duration, str):
        digits = "".join([c for c in duration if c.isdigit()])
        dur_val = int(digits) if digits else 5

    clean_aspect = aspect_ratio if aspect_ratio in ["16:9", "9:16", "1:1"] else "16:9"

    if is_gen_api_token(token):
        url = f"{GENAPI_BASE_URL}/networks/kling"
        payload = {
            "prompt": prompt,
            "duration": dur_val,
            "aspect_ratio": clean_aspect
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "CrossoutBot/1.0"
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                req_id = res.get("request_id")
                if req_id:
                    return True, str(req_id)
                return False, f"Could not extract request_id from Gen-API response: {res}"
        except urllib.error.HTTPError as he:
            err_data = he.read().decode("utf-8", errors="ignore")
            if he.code == 402:
                return False, "На счете GenAPI недостаточно средств. Пополни баланс на gen-api.ru для генерации видео через Kling!"
            return False, f"Gen-API HTTP {he.code}: {err_data[:200]}"
        except Exception as e:
            return False, f"Gen-API connection error: {e}"

    # MCP tool fallback
    args = {
        "prompt": prompt,
        "model": model,
        "duration": dur_val,
        "aspect_ratio": clean_aspect
    }
    success, res = call_kling_tool("kling_generate_video", args)
    if not success:
        return False, str(res)

    # Extract task_id from MCP tool result
    task_id = None
    if isinstance(res, dict):
        task_id = res.get("task_id") or res.get("id") or (res.get("data", {}).get("task_id") if isinstance(res.get("data"), dict) else None)
        if not task_id and "content" in res and isinstance(res["content"], list):
            for item in res["content"]:
                if item.get("type") == "text" and "task_id" in item.get("text", ""):
                    try:
                        parsed = json.loads(item["text"])
                        task_id = parsed.get("task_id")
                    except Exception:
                        pass
    if task_id:
        return True, str(task_id)
    return False, f"Could not extract task_id from response: {res}"


def submit_image_to_video(image_path, prompt="", model="kling-v1", duration="5s"):
    """
    Submits an image-to-video generation task to Kling via Gen-API or MCP.
    """
    token, _ = get_kling_config()
    if not token:
        return False, "KLING_API_KEY is not configured."

    if not os.path.exists(image_path):
        return False, f"Image not found: {image_path}"

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("ascii")

    mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    data_uri = f"data:{mime};base64,{img_b64}"

    dur_val = 5
    if isinstance(duration, int):
        dur_val = duration
    elif isinstance(duration, str):
        digits = "".join([c for c in duration if c.isdigit()])
        dur_val = int(digits) if digits else 5

    if is_gen_api_token(token):
        url = f"{GENAPI_BASE_URL}/networks/kling"
        payload = {
            "prompt": prompt or "Dynamic video motion",
            "image": data_uri,
            "duration": dur_val
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "CrossoutBot/1.0"
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                req_id = res.get("request_id")
                if req_id:
                    return True, str(req_id)
                return False, f"Could not extract request_id from Gen-API response: {res}"
        except urllib.error.HTTPError as he:
            err_data = he.read().decode("utf-8", errors="ignore")
            if he.code == 402:
                return False, "На счете GenAPI недостаточно средств. Пополни баланс на gen-api.ru для генерации видео через Kling!"
            return False, f"Gen-API HTTP {he.code}: {err_data[:200]}"
        except Exception as e:
            return False, f"Gen-API error: {e}"

    args = {
        "start_image_url": data_uri,
        "prompt": prompt,
        "model": model,
        "duration": dur_val
    }
    success, res = call_kling_tool("kling_generate_video_from_image", args)
    if not success:
        return False, str(res)

    task_id = None
    if isinstance(res, dict):
        task_id = res.get("task_id") or res.get("id") or (res.get("data", {}).get("task_id") if isinstance(res.get("data"), dict) else None)
    if task_id:
        return True, str(task_id)
    return False, f"Could not extract task_id from response: {res}"


def get_task_status(task_id):
    """
    Queries status of a video generation task.
    Returns (True, dict) or (False, error_msg).
    Dict format: {"status": "processing"|"succeed"|"failed", "video_url": "...", "progress": int}
    """
    token, _ = get_kling_config()
    if is_gen_api_token(token):
        url = f"{GENAPI_BASE_URL}/request/get/{task_id}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "CrossoutBot/1.0"
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                raw_st = (res.get("status") or "processing").lower()
                status = "processing"
                video_url = None
                if raw_st in ["success", "succeed", "completed"]:
                    status = "succeed"
                    output = res.get("output") or []
                    if isinstance(output, list) and output:
                        video_url = output[0]
                    elif isinstance(output, str):
                        video_url = output
                    elif isinstance(output, dict):
                        video_url = output.get("url") or output.get("video_url")
                elif raw_st in ["error", "failed"]:
                    status = "failed"
                progress = res.get("progress") or (100 if status == "succeed" else 50)
                return True, {"status": status, "video_url": video_url, "progress": progress}
        except Exception as e:
            return False, str(e)

    success, res = call_kling_tool("kling_get_task", {"task_id": str(task_id)})
    if not success:
        return False, str(res)

    status_data = {"status": "processing", "video_url": None, "progress": 0}
    if isinstance(res, dict):
        data_block = res.get("data") if isinstance(res.get("data"), dict) else res
        status_data["status"] = (data_block.get("status") or "processing").lower()
        status_data["progress"] = data_block.get("progress", 0)
        videos = data_block.get("videos") or data_block.get("works") or []
        if isinstance(videos, list) and videos:
            first_v = videos[0]
            if isinstance(first_v, dict):
                status_data["video_url"] = first_v.get("url") or first_v.get("video_url")
            elif isinstance(first_v, str):
                status_data["video_url"] = first_v
        if not status_data["video_url"]:
            status_data["video_url"] = data_block.get("video_url") or data_block.get("url")

    return True, status_data


def download_kling_video(video_url, task_id):
    """
    Downloads the completed video file before the temporary CDN URL expires.
    """
    os.makedirs(VIDEO_DIR, exist_ok=True)
    out_file = os.path.join(VIDEO_DIR, f"kling_{task_id}_{int(time.time())}.mp4")
    req = urllib.request.Request(video_url, headers={"User-Agent": "CrossoutBot-VideoFetcher/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(out_file, "wb") as f:
            f.write(resp.read())
    if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
        return out_file
    return None


def request_owner_permission_for_kling(prompt, requester_name="Ярик"):
    """
    Calls ask_owner.py to seek explicit approval for spending Kling credits.
    Returns True if approved, False otherwise.
    """
    ask_script = os.path.join(BASE_DIR, "ask_owner.py")
    question_text = f"Запрос на генерацию видео через Kling AI: «{prompt}»"
    cmd = [
        sys.executable,
        ask_script,
        question_text,
        "--initiator", requester_name
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=190)
        stdout = proc.stdout.strip()
        for line in stdout.splitlines():
            try:
                data = json.loads(line)
                if data.get("verdict") == "APPROVED":
                    return True
            except Exception:
                continue
    except Exception as e:
        print(f"[KLING PERMISSION ERROR] {e}")
    return False


def generate_kling_video_async(
    prompt,
    sender_name="Ярик",
    recipient="yarik",
    is_owner=False,
    image_path=None,
    reply_to_msg_id=None
):
    """
    Spawns background daemon thread to safely execute Kling video generation:
    1. Permission check via ask_owner if not owner.
    2. Credits check.
    3. Task submission.
    4. Async polling until completion.
    5. Download temporary MP4 file.
    6. Delivery via send.py and file cleanup.
    """
    def _worker():
        target_name = "Миша" if is_owner else "Ярик"
        video_file = None
        try:
            # 1. Permission check for non-owner
            if not is_owner:
                print(f"[KLING WORKER] Requesting owner permission for {sender_name}...")
                approved = request_owner_permission_for_kling(prompt, requester_name=sender_name)
                if not approved:
                    refusal_msg = f"{target_name}, Миша пока не разрешил тратить кредиты Kling на это видео 🚜"
                    subprocess.run([
                        sys.executable, os.path.join(BASE_DIR, "send.py"),
                        "--to", recipient, "--text", refusal_msg,
                        "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
                    ])
                    return

            # 2. Credits verification
            token, _ = get_kling_config()
            if not token:
                no_token_msg = f"{target_name}, токен KLING_API_KEY не настроен в конфигурации бота на сервере 🔧"
                subprocess.run([
                    sys.executable, os.path.join(BASE_DIR, "send.py"),
                    "--to", recipient, "--text", no_token_msg,
                    "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
                ])
                return

            cr_ok, cr_data = check_kling_credits()
            if cr_ok and isinstance(cr_data, dict):
                balance = None
                for k in ["credits", "balance"]:
                    if k in cr_data:
                        balance = cr_data[k]
                        break
                    if isinstance(cr_data.get("data"), dict) and k in cr_data["data"]:
                        balance = cr_data["data"][k]
                        break
                if balance is not None and isinstance(balance, (int, float)):
                    is_genapi = is_gen_api_token(token)
                    min_cost = 15 if is_genapi else 1
                    if balance < min_cost:
                        user_name = cr_data.get("name") or "Коробкин Михаил"
                        no_credits_msg = (
                            f"{target_name}, на счете GenAPI ({user_name}) сейчас {balance} ₽ (нужно от 15 ₽). "
                            f"Для генерации видео через Kling AI пополни баланс на gen-api.ru 💸"
                        ) if is_genapi else f"{target_name}, на аккаунте Kling AI закончились кредиты ({balance}) 💸"
                        subprocess.run([
                            sys.executable, os.path.join(BASE_DIR, "send.py"),
                            "--to", recipient, "--text", no_credits_msg,
                            "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
                        ])
                        return

            # 3. Task submission
            ack_msg = f"Принял задачу, {target_name}! Запустил генерацию видео в Kling AI... 🎬⏳ Это займет пару минут."
            subprocess.run([
                sys.executable, os.path.join(BASE_DIR, "send.py"),
                "--to", recipient, "--text", ack_msg,
                "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
            ])

            if image_path and os.path.exists(image_path):
                ok, res = submit_image_to_video(image_path, prompt=prompt)
            else:
                ok, res = submit_text_to_video(prompt)

            if not ok:
                err_msg = f"{target_name}, не удалось запустить генерацию в Kling AI: {res} 💀"
                subprocess.run([
                    sys.executable, os.path.join(BASE_DIR, "send.py"),
                    "--to", recipient, "--text", err_msg,
                    "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
                ])
                return

            task_id = res
            print(f"[KLING WORKER] Task submitted successfully (task_id={task_id}). Polling status...")

            # 4. Polling loop (up to 10 minutes)
            video_url = None
            start_poll = time.time()
            while time.time() - start_poll < 600:
                time.sleep(10)
                st_ok, st_data = get_task_status(task_id)
                if not st_ok:
                    continue

                status = st_data.get("status")
                print(f"[KLING WORKER] Task {task_id} status: {status} ({st_data.get('progress', 0)}%)")
                if status in ["succeed", "completed", "success"]:
                    video_url = st_data.get("video_url")
                    break
                elif status in ["failed", "error"]:
                    err_msg = f"{target_name}, генерация видео в Kling AI завершилась ошибкой 💀"
                    subprocess.run([
                        sys.executable, os.path.join(BASE_DIR, "send.py"),
                        "--to", recipient, "--text", err_msg,
                        "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
                    ])
                    return

            if not video_url:
                timeout_msg = f"{target_name}, время ожидания рендера видео в Kling AI истекло (таймаут 10 мин) ⏳"
                subprocess.run([
                    sys.executable, os.path.join(BASE_DIR, "send.py"),
                    "--to", recipient, "--text", timeout_msg,
                    "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
                ])
                return

            # 5. Download MP4 file
            print(f"[KLING WORKER] Downloading generated video from {video_url}...")
            video_file = download_kling_video(video_url, task_id)
            if not video_file or not os.path.exists(video_file):
                fail_dl_msg = f"{target_name}, видео успешно создано, но не удалось скачать готовый файл 💀"
                subprocess.run([
                    sys.executable, os.path.join(BASE_DIR, "send.py"),
                    "--to", recipient, "--text", fail_dl_msg,
                    "--reply-to", str(reply_to_msg_id) if reply_to_msg_id else "0"
                ])
                return

            # 6. Deliver to chat
            caption = f"Держи видео от Kling AI, {target_name}! 🎬🔥\nЗапрос: {prompt[:80]}"
            send_cmd = [
                sys.executable, os.path.join(BASE_DIR, "send.py"),
                "--to", recipient,
                "--photo", video_file,
                "--text", caption
            ]
            if reply_to_msg_id:
                send_cmd.extend(["--reply-to", str(reply_to_msg_id)])
            subprocess.run(send_cmd)

        except Exception as e:
            print(f"[KLING WORKER EXCEPTION] {e}")
        finally:
            if video_file and os.path.exists(video_file):
                try:
                    os.remove(video_file)
                    print(f"[KLING CLEANUP] Removed temporary video: {video_file}")
                except Exception:
                    pass
            if image_path and os.path.exists(image_path) and any(seg in image_path for seg in ["media/", "media\\", "owner_", "yarik_"]):
                try:
                    os.remove(image_path)
                    print(f"[KLING CLEANUP] Cleaned up processed input image: {image_path}")
                except Exception:
                    pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t
