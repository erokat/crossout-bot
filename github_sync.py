# -*- coding: utf-8 -*-
"""
github_sync.py - Immortal persistence of dynamic skills via GitHub REST API.

Provides:
1. push_skill_to_github: Auto-pushes newly created or self-healed skills from skills/
   to GitHub repository via PUT /repos/{owner}/{repo}/contents/skills/{skill_name}.py.
   Fetches current blob sha via GET if the file already exists to avoid 409/422 conflicts.
   Automatically resolves conflicts and retries once on HTTP 409/422 with freshly fetched sha.
   Always includes '[skip render]' in the commit message to prevent container restarts.
2. fetch_skills_from_github: Lists all files in skills/ directory from GitHub repo.
3. download_skill_code_from_github: Retrieves decoded source code of a skill from GitHub.
4. sync_skills_from_github: Two-way synchronization at bot startup:
   - Downloads missing or remotely updated skill files from GitHub, avoiding redundant
     downloads when local git blob SHA already matches.
   - Registers skills in SQLite dynamic_skills and installs dependencies if requested.
   - Pushes any locally created skills missing on GitHub to ensure complete bidirectional persistence.
5. Strict security checks (is_valid_github_skill_path, is_safe_skill_path) and 10s timeout.
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.error
import urllib.parse
import socket
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SKILLS_DIR = os.path.join(BASE_DIR, "skills")
DEFAULT_REPO = "erokat/crossout-bot"
DEFAULT_TIMEOUT = 10  # Strict 10-second timeout for resilience

# Protected core files that can never be overwritten or pushed as skills
PROTECTED_CORE_FILES = {
    "keep_alive.py",
    "wait_for_yarik.py",
    "db.py",
    "send.py",
    "session.session",
    "crossout_session.session",
    "config.py",
    "config.json",
    "Dockerfile",
    "main.py",
    "requirements.txt",
    "github_sync.py",
    "dynamic_agent.py",
    "add_to_sticker_pack.py",
    "ask_owner.py",
    "media_finder.py",
    "meme_engine.py",
    "meme_generator.py",
    "photo_editor.py",
    "video_editor.py",
    "gdrive.py"
}


def get_github_config():
    """
    Reads GITHUB_TOKEN and GITHUB_REPO from environment variables.
    Never hardcodes secrets. Returns (token, repo).
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip() or DEFAULT_REPO
    repo = repo.strip("/")
    return (token if token else None, repo)


def is_valid_github_skill_path(filepath_or_name, skills_dir=None):
    """
    Strict security validation:
    1. Rejects path traversal (..), absolute paths outside skills/, or suspicious characters.
    2. Ensures the filename is a valid Python file ending with .py and not __init__.py.
    3. Confirms the file name is not in PROTECTED_CORE_FILES.
    4. Ensures the target file resides directly inside skills_dir (no subdirectories).
    5. Delegates to dynamic_agent.is_safe_skill_path if available.
    """
    if not filepath_or_name or not isinstance(filepath_or_name, str):
        return False

    cleaned = filepath_or_name.replace("\\", "/").strip()
    if ".." in cleaned or cleaned.startswith("~"):
        return False

    filename = os.path.basename(cleaned)
    if not filename.endswith(".py") or filename == "__init__.py":
        return False

    if filename.lower() in {f.lower() for f in PROTECTED_CORE_FILES}:
        return False

    s_dir = os.path.abspath(skills_dir) if skills_dir else os.path.abspath(SKILLS_DIR)

    if os.path.isabs(cleaned):
        target_abs = os.path.abspath(cleaned)
    elif cleaned.startswith("skills/") and not skills_dir:
        target_abs = os.path.abspath(os.path.join(BASE_DIR, cleaned))
    elif "/" in cleaned:
        target_abs = os.path.abspath(os.path.join(s_dir, cleaned))
    else:
        target_abs = os.path.abspath(os.path.join(s_dir, filename))

    if os.path.dirname(target_abs) != s_dir:
        return False

    try:
        from dynamic_agent import is_safe_skill_path as _safe_check
        if not _safe_check(target_abs):
            return False
    except Exception:
        pass

    return True


def get_file_sha(repo, github_path, token=None, timeout=DEFAULT_TIMEOUT):
    """
    Performs GET /repos/{owner}/{repo}/contents/{github_path} to retrieve existing file SHA.
    Returns sha string if file exists, None if 404 Not Found or on error.
    """
    token = token or get_github_config()[0]
    if not repo:
        return None

    encoded_path = urllib.parse.quote(github_path, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Crossout-Bot-SkillsSync/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"[GITHUB SYNC] Warning getting SHA for {github_path}: HTTP {e.code}")
        return None
    except Exception as e:
        print(f"[GITHUB SYNC] Warning getting SHA for {github_path}: {e}")
        return None
    return None


def push_skill_to_github(skill_name=None, file_path=None, code=None, commit_message=None, timeout=DEFAULT_TIMEOUT, skills_dir=None):
    """
    Uploads or updates a dynamic skill in the GitHub repository via PUT /repos/{owner}/{repo}/contents/skills/{skill_name}.py.
    
    Requirements satisfied:
    - Obtains current SHA via GET if the file already exists on GitHub to prevent 409/422 conflicts.
    - Resolves conflicts and retries automatically if 409 or 422 occurs.
    - Adds '[skip render]' tag to the commit message to prevent unwanted Render container restarts.
    - Validates path safety via is_valid_github_skill_path.
    - 10-second network timeout.
    - Does not raise exceptions on network errors; logs warning and returns (False, err).
    """
    s_dir = os.path.abspath(skills_dir) if skills_dir else os.path.abspath(SKILLS_DIR)

    # 1. Determine skill_name and file_path
    if file_path and not skill_name:
        fname = os.path.basename(file_path)
        skill_name = os.path.splitext(fname)[0]
    elif skill_name and not file_path:
        fname = f"{skill_name}.py" if not skill_name.endswith(".py") else skill_name
        skill_name = os.path.splitext(fname)[0]
        file_path = os.path.join(s_dir, fname)
    elif skill_name and file_path:
        if skill_name.endswith(".py") or "/" in skill_name or "\\" in skill_name:
            fname = os.path.basename(skill_name)
            skill_name = os.path.splitext(fname)[0]
        else:
            fname = os.path.basename(file_path)
    else:
        return False, "Neither skill_name nor file_path provided"

    # Normalize file_path to s_dir if it exists there and not locally
    if not os.path.isabs(file_path):
        if not os.path.exists(file_path) and os.path.exists(os.path.join(s_dir, os.path.basename(file_path))):
            file_path = os.path.join(s_dir, os.path.basename(file_path))

    fname = os.path.basename(file_path)
    if not fname.endswith(".py"):
        fname += ".py"
        file_path += ".py"

    # 2. Security validation
    if not is_valid_github_skill_path(file_path, skills_dir=s_dir):
        print(f"[GITHUB SYNC] Push rejected: unsafe skill path '{file_path}'")
        return False, f"Unsafe skill path: {file_path}"

    # 3. Read code if not provided
    if code is None:
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
            except Exception as e:
                return False, f"Could not read skill file: {e}"
        else:
            return False, f"Skill file does not exist: {file_path}"

    # 4. Read credentials
    token, repo = get_github_config()
    if not token:
        print("[GITHUB SYNC] GITHUB_TOKEN not configured. Skipping GitHub push.")
        return False, "GITHUB_TOKEN not configured"

    # 5. Format commit message with [skip render]
    if not commit_message:
        commit_message = f"feat(skills): auto-save skill {skill_name} [skip render]"
    elif "[skip render]" not in commit_message:
        commit_message = f"{commit_message} [skip render]"

    github_path = f"skills/{fname}"

    # 6. Retrieve existing sha if file already exists on GitHub
    sha = get_file_sha(repo, github_path, token=token, timeout=timeout)

    # 7. Prepare PUT payload
    content_b64 = base64.b64encode(code.encode("utf-8")).decode("ascii")
    payload = {
        "message": commit_message,
        "content": content_b64
    }
    if sha:
        payload["sha"] = sha

    encoded_path = urllib.parse.quote(github_path, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Crossout-Bot-SkillsSync/1.0",
        "Content-Type": "application/json"
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers=headers, method="PUT")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status in (200, 201):
                resp_json = json.loads(resp.read().decode("utf-8"))
                commit_sha = resp_json.get("commit", {}).get("sha", "")[:7]
                print(f"[GITHUB SYNC] Successfully pushed skill '{skill_name}' to GitHub ({github_path}) [{commit_sha}]. Tag: [skip render]")
                return True, resp_json
            else:
                return False, f"Unexpected status {resp.status}"
    except urllib.error.HTTPError as he:
        # If conflict 409 or 422 occurs (sha mismatch or missing sha), retry once with freshly fetched sha
        if he.code in (409, 422):
            try:
                new_sha = get_file_sha(repo, github_path, token=token, timeout=timeout)
                if new_sha:
                    payload["sha"] = new_sha
                    retry_data = json.dumps(payload).encode("utf-8")
                    retry_req = urllib.request.Request(url, data=retry_data, headers=headers, method="PUT")
                    with urllib.request.urlopen(retry_req, timeout=timeout) as retry_resp:
                        if retry_resp.status in (200, 201):
                            resp_json = json.loads(retry_resp.read().decode("utf-8"))
                            print(f"[GITHUB SYNC] Successfully updated skill '{skill_name}' on GitHub after resolving {he.code} conflict.")
                            return True, resp_json
            except Exception as retry_e:
                print(f"[GITHUB SYNC] Conflict retry failed for {skill_name}: {retry_e}")

        err_body = he.read().decode("utf-8", errors="ignore")[:200]
        print(f"[GITHUB SYNC] HTTPError {he.code} pushing skill '{skill_name}': {err_body}")
        return False, f"HTTP {he.code}: {err_body}"
    except (urllib.error.URLError, socket.timeout, TimeoutError) as net_err:
        print(f"[GITHUB SYNC] Network timeout/error pushing skill '{skill_name}': {net_err}")
        return False, str(net_err)
    except Exception as e:
        print(f"[GITHUB SYNC] Unexpected error pushing skill '{skill_name}': {e}")
        return False, str(e)


def fetch_skills_from_github(timeout=DEFAULT_TIMEOUT):
    """
    Performs GET /repos/{owner}/{repo}/contents/skills to list all files in the skills directory.
    Returns list of dicts, or empty list on error/absence.
    """
    token, repo = get_github_config()
    if not repo:
        return []

    url = f"https://api.github.com/repos/{repo}/contents/skills"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Crossout-Bot-SkillsSync/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return []
        print(f"[GITHUB SYNC] HTTPError {e.code} listing skills from GitHub")
        return []
    except Exception as e:
        print(f"[GITHUB SYNC] Error listing skills from GitHub: {e}")
        return []
    return []


def download_skill_code_from_github(item_or_path, timeout=DEFAULT_TIMEOUT):
    """
    Retrieves and decodes Python source code for a skill file from GitHub.
    Can accept either a dictionary item from fetch_skills_from_github or a relative repo path.
    """
    token, repo = get_github_config()
    if not repo:
        return None

    if isinstance(item_or_path, dict) and item_or_path.get("content"):
        try:
            raw_b64 = item_or_path["content"].replace("\n", "").replace("\r", "")
            return base64.b64decode(raw_b64).decode("utf-8")
        except Exception:
            pass

    if isinstance(item_or_path, dict):
        rel_path = item_or_path.get("path") or f"skills/{item_or_path.get('name')}"
    else:
        rel_path = item_or_path

    encoded_path = urllib.parse.quote(rel_path, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Crossout-Bot-SkillsSync/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                raw_b64 = data.get("content", "").replace("\n", "").replace("\r", "")
                if raw_b64:
                    return base64.b64decode(raw_b64).decode("utf-8")
                # Fallback to download_url if available
                download_url = data.get("download_url")
                if download_url:
                    dl_req = urllib.request.Request(download_url, headers={"User-Agent": "Crossout-Bot-SkillsSync/1.0"})
                    if token and "github.com" in download_url:
                        dl_req.add_header("Authorization", f"Bearer {token}")
                    with urllib.request.urlopen(dl_req, timeout=timeout) as dl_resp:
                        if dl_resp.status == 200:
                            return dl_resp.read().decode("utf-8")
    except Exception as e:
        print(f"[GITHUB SYNC] Error downloading {rel_path} from GitHub: {e}")
        return None
    return None


def sync_skills_from_github(skills_dir=None, install_requirements=True, push_missing_local=True, timeout=DEFAULT_TIMEOUT):
    """
    Two-way synchronization of dynamic skills with GitHub repository:
    1. Requests GET /repos/{owner}/{repo}/contents/skills.
    2. Remote -> Local: For any .py file on GitHub:
       - Compares local git blob SHA to avoid unnecessary download if local file is already identical.
       - If missing locally or remote SHA differs, downloads code from GitHub and updates disk.
       - Parses metadata (# SKILL_NAME, # DESCRIPTION, # TRIGGERS, # REQUIREMENTS).
       - Saves dynamic skill to SQLite dynamic_skills table.
       - If install_requirements=True, installs any missing pip packages.
    3. Local -> Remote: For any local .py skill not present on GitHub:
       - If push_missing_local=True and GITHUB_TOKEN configured, auto-pushes to GitHub with '[skip render]'.
    Returns the number of newly downloaded/registered skills.
    """
    token, repo = get_github_config()
    if not repo:
        return 0

    s_dir = os.path.abspath(skills_dir) if skills_dir else os.path.abspath(SKILLS_DIR)
    os.makedirs(s_dir, exist_ok=True)

    items = fetch_skills_from_github(timeout=timeout)
    if not items and not os.path.exists(s_dir):
        return 0

    synced_count = 0
    all_new_reqs = set()
    remote_fnames = set()

    import db

    # 1. Remote -> Local Sync
    if items:
        for item in items:
            fname = item.get("name", "")
            if not fname.endswith(".py") or fname == "__init__.py":
                continue

            remote_fnames.add(fname)
            target_path = os.path.join(s_dir, fname)
            if not is_valid_github_skill_path(fname, skills_dir=s_dir):
                continue

            slug = os.path.splitext(fname)[0]
            exists_on_disk = os.path.exists(target_path)
            existing_entry = db.get_dynamic_skill(slug)

            # Check if local file on disk has matching git blob SHA
            is_sha_matching = False
            local_code = None
            if exists_on_disk:
                try:
                    with open(target_path, "rb") as f:
                        local_bytes = f.read()
                    local_sha = hashlib.sha1(f"blob {len(local_bytes)}\0".encode() + local_bytes).hexdigest()
                    remote_sha = item.get("sha")
                    if remote_sha and local_sha == remote_sha:
                        is_sha_matching = True
                        local_code = local_bytes.decode("utf-8")
                except Exception:
                    is_sha_matching = False

            code = None
            # Download if missing on disk OR if remote SHA changed
            if not exists_on_disk or not is_sha_matching:
                print(f"[GITHUB SYNC] Found remote skill '{fname}' missing or updated locally. Syncing...")
                code = download_skill_code_from_github(item, timeout=timeout)
                if not code:
                    continue

                # Write to disk
                try:
                    with open(target_path, "w", encoding="utf-8") as f:
                        f.write(code)
                except Exception as we:
                    print(f"[GITHUB SYNC] Error writing skill file {target_path}: {we}")
                    continue
            elif not existing_entry and local_code:
                # File is on disk and matches remote SHA, but SQLite record is missing
                code = local_code

            if code:
                # Parse metadata
                s_name, s_desc, s_trig, s_req = db.parse_skill_metadata_from_code(code, fallback_name=slug)

                # Rel path for SQLite
                try:
                    rel_path = os.path.relpath(target_path, BASE_DIR) if target_path.startswith(BASE_DIR) else f"skills/{fname}"
                except Exception:
                    rel_path = f"skills/{fname}"

                # Save to SQLite
                db.save_dynamic_skill(
                    skill_name=s_name,
                    file_path=rel_path,
                    triggers=s_trig,
                    description=s_desc,
                    requirements=s_req,
                    code=code
                )
                print(f"[GITHUB SYNC] Successfully registered '{s_name}' from GitHub into SQLite.")

                for req in s_req:
                    if req and isinstance(req, str):
                        all_new_reqs.add(req.strip())

                synced_count += 1

    # 2. Local -> Remote Sync (push local skills that are missing on GitHub)
    if push_missing_local and token and os.path.exists(s_dir):
        for local_file in os.listdir(s_dir):
            if local_file.endswith(".py") and local_file != "__init__.py" and local_file not in remote_fnames:
                if is_valid_github_skill_path(local_file, skills_dir=s_dir):
                    local_slug = os.path.splitext(local_file)[0]
                    local_path = os.path.join(s_dir, local_file)
                    print(f"[GITHUB SYNC] Found local skill '{local_file}' missing on GitHub. Auto-pushing...")
                    try:
                        pushed, _ = push_skill_to_github(
                            skill_name=local_slug,
                            file_path=local_path,
                            skills_dir=s_dir,
                            timeout=timeout
                        )
                        if pushed:
                            print(f"[GITHUB SYNC] Successfully synced local skill '{local_slug}' to GitHub.")
                    except Exception as pe:
                        print(f"[GITHUB SYNC] Notice auto-pushing local skill '{local_slug}': {pe}")

    # 3. Install requirements if requested
    if install_requirements and all_new_reqs:
        import subprocess
        import importlib.util

        for pkg in all_new_reqs:
            from db import clean_requirement_name
            pkg = clean_requirement_name(pkg)
            if not pkg:
                continue
            base_mod = pkg.split("[")[0].split("=")[0].split("<")[0].split(">")[0].strip().replace("-", "_")
            try:
                if importlib.util.find_spec(base_mod) is not None:
                    continue
            except Exception:
                pass

            try:
                print(f"[GITHUB SYNC] Installing requirement for synced skill: {pkg}...")
                cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", pkg]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if res.returncode != 0 and "no such option" in (res.stderr or "").lower():
                    cmd = [sys.executable, "-m", "pip", "install", pkg]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if res.returncode == 0:
                    print(f"[GITHUB SYNC] Successfully installed requirement: {pkg}")
                else:
                    print(f"[GITHUB SYNC] Pip warning for {pkg}: {res.stderr[:150] if res.stderr else ''}")
            except Exception as e:
                print(f"[GITHUB SYNC] Error installing {pkg}: {e}")

    return synced_count
