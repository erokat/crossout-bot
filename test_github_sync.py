# -*- coding: utf-8 -*-
"""
test_github_sync.py - Unit tests for GitHub REST API skill persistence and two-way sync.

Covers:
1. Safe path validation (is_valid_github_skill_path) & core protection.
2. Skill creation on GitHub (PUT without sha when file does not exist).
3. Skill update on GitHub (GET existing sha -> PUT with sha).
4. Strict enforcement of '[skip render]' in commit messages.
5. Startup two-way sync (restore_dynamic_skills downloading new skills from GitHub).
6. Resilience against timeouts, missing tokens, and network errors.
7. Conflict resolution (HTTP 409 retry with updated sha).
"""

import os
import sys
import json
import base64
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import shutil
import urllib.error
import socket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import github_sync
import db
import dynamic_agent


class TestGitHubSyncSecurityAndConfig(unittest.TestCase):
    def test_get_github_config_reads_env(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "test_tok_123", "GITHUB_REPO": "testowner/testrepo"}):
            token, repo = github_sync.get_github_config()
            self.assertEqual(token, "test_tok_123")
            self.assertEqual(repo, "testowner/testrepo")

    def test_get_github_config_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            token, repo = github_sync.get_github_config()
            self.assertIsNone(token)
            self.assertEqual(repo, github_sync.DEFAULT_REPO)

    def test_is_valid_github_skill_path_allowed(self):
        temp_dir = tempfile.mkdtemp()
        try:
            self.assertTrue(github_sync.is_valid_github_skill_path("my_skill.py", skills_dir=temp_dir))
            self.assertTrue(github_sync.is_valid_github_skill_path(os.path.join(temp_dir, "custom_calc.py"), skills_dir=temp_dir))
            self.assertTrue(github_sync.is_valid_github_skill_path("skills/weather_tiraspol.py"))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_is_valid_github_skill_path_rejected(self):
        temp_dir = tempfile.mkdtemp()
        try:
            # Core protected files
            for core in ["keep_alive.py", "db.py", "config.py", "Dockerfile", "main.py"]:
                self.assertFalse(github_sync.is_valid_github_skill_path(core, skills_dir=temp_dir))
                self.assertFalse(github_sync.is_valid_github_skill_path(os.path.join(temp_dir, core), skills_dir=temp_dir))

            # Package init file
            self.assertFalse(github_sync.is_valid_github_skill_path("__init__.py", skills_dir=temp_dir))
            self.assertFalse(github_sync.is_valid_github_skill_path(os.path.join(temp_dir, "__init__.py"), skills_dir=temp_dir))

            # Directory traversal
            self.assertFalse(github_sync.is_valid_github_skill_path("../config.py", skills_dir=temp_dir))
            self.assertFalse(github_sync.is_valid_github_skill_path("../../etc/passwd", skills_dir=temp_dir))

            # Non-python files
            self.assertFalse(github_sync.is_valid_github_skill_path("exploit.sh", skills_dir=temp_dir))
            self.assertFalse(github_sync.is_valid_github_skill_path("data.json", skills_dir=temp_dir))

            # Path outside skills_dir
            outside_file = os.path.join(os.path.dirname(temp_dir), "outside.py")
            self.assertFalse(github_sync.is_valid_github_skill_path(outside_file, skills_dir=temp_dir))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestGitHubSyncPush(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.env_patcher = patch.dict(os.environ, {
            "GITHUB_TOKEN": "mock_token_xyz",
            "GITHUB_REPO": "testowner/testbot"
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("urllib.request.urlopen")
    def test_push_new_skill_creates_without_sha(self, mock_urlopen):
        # 1. GET returns 404 (file does not exist on GitHub yet)
        # 2. PUT returns 201 Created
        skill_name = "test_new_skill"
        skill_code = "# -*- coding: utf-8 -*-\n# SKILL_NAME: test_new_skill\nprint('new')\n"
        skill_file = os.path.join(self.temp_dir, f"{skill_name}.py")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(skill_code)

        def mock_side_effect(req, *args, **kwargs):
            if req.get_method() == "GET":
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
            elif req.get_method() == "PUT":
                resp = MagicMock()
                resp.__enter__.return_value = resp
                resp.status = 201
                resp.read.return_value = json.dumps({
                    "content": {"name": f"{skill_name}.py", "path": f"skills/{skill_name}.py"},
                    "commit": {"sha": "c0ffee123456789"}
                }).encode("utf-8")
                return resp
            raise ValueError(f"Unexpected method: {req.get_method()}")

        mock_urlopen.side_effect = mock_side_effect

        success, result = github_sync.push_skill_to_github(
            skill_name=skill_name,
            file_path=skill_file,
            code=skill_code,
            skills_dir=self.temp_dir
        )

        self.assertTrue(success)
        self.assertEqual(result.get("commit", {}).get("sha"), "c0ffee123456789")

        # Verify PUT call arguments
        put_calls = [c for c in mock_urlopen.call_args_list if c[0][0].get_method() == "PUT"]
        self.assertEqual(len(put_calls), 1)
        put_req = put_calls[0][0][0]

        self.assertEqual(put_req.full_url, "https://api.github.com/repos/testowner/testbot/contents/skills/test_new_skill.py")
        self.assertIn("Bearer mock_token_xyz", put_req.headers.get("Authorization", ""))

        payload = json.loads(put_req.data.decode("utf-8"))
        self.assertNotIn("sha", payload, "New file PUT must NOT contain 'sha'")
        self.assertIn("[skip render]", payload["message"])
        self.assertEqual(base64.b64decode(payload["content"]).decode("utf-8"), skill_code)

    @patch("urllib.request.urlopen")
    def test_push_existing_skill_updates_with_sha(self, mock_urlopen):
        # 1. GET returns 200 with existing sha
        # 2. PUT returns 200 OK
        skill_name = "test_existing_skill"
        skill_code = "# -*- coding: utf-8 -*-\n# SKILL_NAME: test_existing_skill\nprint('updated')\n"
        skill_file = os.path.join(self.temp_dir, f"{skill_name}.py")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(skill_code)

        existing_sha = "blob_sha_existing_99999"

        def mock_side_effect(req, *args, **kwargs):
            if req.get_method() == "GET":
                resp = MagicMock()
                resp.__enter__.return_value = resp
                resp.status = 200
                resp.read.return_value = json.dumps({
                    "name": f"{skill_name}.py",
                    "sha": existing_sha,
                    "content": base64.b64encode(b"old_code").decode("ascii")
                }).encode("utf-8")
                return resp
            elif req.get_method() == "PUT":
                resp = MagicMock()
                resp.__enter__.return_value = resp
                resp.status = 200
                resp.read.return_value = json.dumps({
                    "commit": {"sha": "new_commit_sha_888"}
                }).encode("utf-8")
                return resp
            raise ValueError(f"Unexpected method: {req.get_method()}")

        mock_urlopen.side_effect = mock_side_effect

        success, result = github_sync.push_skill_to_github(
            skill_name=skill_name,
            file_path=skill_file,
            code=skill_code,
            skills_dir=self.temp_dir
        )

        self.assertTrue(success)

        # Verify PUT call arguments
        put_calls = [c for c in mock_urlopen.call_args_list if c[0][0].get_method() == "PUT"]
        self.assertEqual(len(put_calls), 1)
        put_req = put_calls[0][0][0]

        payload = json.loads(put_req.data.decode("utf-8"))
        self.assertEqual(payload.get("sha"), existing_sha, "Updated file PUT MUST contain existing 'sha'")
        self.assertIn("[skip render]", payload["message"])
        self.assertEqual(base64.b64decode(payload["content"]).decode("utf-8"), skill_code)

    @patch("urllib.request.urlopen")
    def test_skip_render_enforcement_in_commit_messages(self, mock_urlopen):
        skill_name = "calc_skill"
        skill_code = "print('calc')"
        skill_file = os.path.join(self.temp_dir, f"{skill_name}.py")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(skill_code)

        captured_messages = []

        def capture_put(req, *args, **kwargs):
            if req.get_method() == "GET":
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
            if req.get_method() == "PUT":
                payload = json.loads(req.data.decode("utf-8"))
                captured_messages.append(payload["message"])
                resp = MagicMock()
                resp.__enter__.return_value = resp
                resp.status = 201
                resp.read.return_value = json.dumps({"commit": {"sha": "123"}}).encode("utf-8")
                return resp
            return MagicMock()

        mock_urlopen.side_effect = capture_put

        # Case A: Default message (commit_message=None)
        github_sync.push_skill_to_github(skill_name=skill_name, file_path=skill_file, code=skill_code, skills_dir=self.temp_dir)
        self.assertIn("[skip render]", captured_messages[-1])
        self.assertEqual(captured_messages[-1], "feat(skills): auto-save skill calc_skill [skip render]")

        # Case B: Custom message without tag
        github_sync.push_skill_to_github(skill_name=skill_name, file_path=skill_file, code=skill_code, commit_message="fix(calc): bugfix", skills_dir=self.temp_dir)
        self.assertIn("[skip render]", captured_messages[-1])
        self.assertEqual(captured_messages[-1], "fix(calc): bugfix [skip render]")

        # Case C: Custom message already having tag
        github_sync.push_skill_to_github(skill_name=skill_name, file_path=skill_file, code=skill_code, commit_message="feat: new module [skip render]", skills_dir=self.temp_dir)
        self.assertEqual(captured_messages[-1].count("[skip render]"), 1)
        self.assertEqual(captured_messages[-1], "feat: new module [skip render]")

    def test_push_rejects_unsafe_paths(self):
        unsafe_cases = [
            ("../keep_alive.py", "keep_alive"),
            ("config.py", "config"),
            ("/etc/passwd", "passwd"),
            ("__init__.py", "__init__")
        ]
        for path, sname in unsafe_cases:
            success, err = github_sync.push_skill_to_github(
                skill_name=sname,
                file_path=path,
                code="print('evil')",
                skills_dir=self.temp_dir
            )
            self.assertFalse(success)
            self.assertIn("Unsafe", str(err))

    @patch("urllib.request.urlopen")
    def test_push_resilient_to_network_errors(self, mock_urlopen):
        skill_name = "timeout_skill"
        skill_code = "print('timeout')"
        skill_file = os.path.join(self.temp_dir, f"{skill_name}.py")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(skill_code)

        # Simulate timeout on GET
        mock_urlopen.side_effect = socket.timeout("timed out")
        success, err = github_sync.push_skill_to_github(skill_name=skill_name, file_path=skill_file, code=skill_code, skills_dir=self.temp_dir)
        self.assertFalse(success)

        # Simulate HTTP 500 error on PUT
        def err_side_effect(req, *args, **kwargs):
            if req.get_method() == "GET":
                raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
            raise urllib.error.HTTPError(req.full_url, 500, "Internal Server Error", {}, MagicMock(read=lambda: b"server error"))

        mock_urlopen.side_effect = err_side_effect
        success, err = github_sync.push_skill_to_github(skill_name=skill_name, file_path=skill_file, code=skill_code, skills_dir=self.temp_dir)
        self.assertFalse(success)
        self.assertIn("500", str(err))

    @patch("urllib.request.urlopen")
    def test_push_conflict_409_resolves_and_retries(self, mock_urlopen):
        skill_name = "conflict_skill"
        skill_code = "print('conflict')"
        skill_file = os.path.join(self.temp_dir, f"{skill_name}.py")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(skill_code)

        call_sequence = []

        def side_effect(req, *args, **kwargs):
            m = req.get_method()
            call_sequence.append(m)
            if m == "GET" and len(call_sequence) == 1:
                # First GET returns stale sha
                resp = MagicMock()
                resp.__enter__.return_value = resp
                resp.status = 200
                resp.read.return_value = json.dumps({"sha": "stale_sha_1"}).encode("utf-8")
                return resp
            elif m == "PUT" and len(call_sequence) == 2:
                # First PUT fails with 409 Conflict
                raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {}, MagicMock(read=lambda: b"conflict"))
            elif m == "GET" and len(call_sequence) == 3:
                # Second GET during retry returns fresh sha
                resp = MagicMock()
                resp.__enter__.return_value = resp
                resp.status = 200
                resp.read.return_value = json.dumps({"sha": "fresh_sha_2"}).encode("utf-8")
                return resp
            elif m == "PUT" and len(call_sequence) == 4:
                # Second PUT succeeds with fresh sha
                payload = json.loads(req.data.decode("utf-8"))
                self.assertEqual(payload.get("sha"), "fresh_sha_2")
                resp = MagicMock()
                resp.__enter__.return_value = resp
                resp.status = 200
                resp.read.return_value = json.dumps({"commit": {"sha": "resolved_commit"}}).encode("utf-8")
                return resp
            raise ValueError(f"Unexpected request {m} #{len(call_sequence)}")

        mock_urlopen.side_effect = side_effect
        success, res = github_sync.push_skill_to_github(skill_name=skill_name, file_path=skill_file, code=skill_code, skills_dir=self.temp_dir)
        self.assertTrue(success)
        self.assertEqual(call_sequence, ["GET", "PUT", "GET", "PUT"])


class TestGitHubSyncStartupRestore(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.temp_dir = tempfile.mkdtemp()
        self.env_patcher = patch.dict(os.environ, {
            "GITHUB_TOKEN": "mock_token_sync",
            "GITHUB_REPO": "testowner/crossout-bot"
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("urllib.request.urlopen")
    def test_two_way_sync_downloads_and_registers_skill(self, mock_urlopen):
        skill_slug = "github_remote_calc"
        skill_code = (
            "# -*- coding: utf-8 -*-\n"
            "# SKILL_NAME: github_remote_calc\n"
            "# DESCRIPTION: Remote GitHub Calculator\n"
            "# TRIGGERS: гиткальк, облаковычислитель\n"
            "# REQUIREMENTS: sympy\n"
            "print('Remote Calc Activated!')\n"
        )
        b64_code = base64.b64encode(skill_code.encode("utf-8")).decode("ascii")

        # Mock GET contents/skills (list) and GET contents/skills/github_remote_calc.py (single)
        def mock_side_effect(req, *args, **kwargs):
            url = req.full_url
            resp = MagicMock()
            resp.__enter__.return_value = resp
            resp.status = 200
            if url.endswith("/contents/skills"):
                # Directory listing
                data = [
                    {"name": "__init__.py", "type": "file"},
                    {"name": "other_file.txt", "type": "file"},
                    {"name": f"{skill_slug}.py", "path": f"skills/{skill_slug}.py", "type": "file", "sha": "remote_sha_111"}
                ]
                resp.read.return_value = json.dumps(data).encode("utf-8")
                return resp
            elif url.endswith(f"/contents/skills/{skill_slug}.py"):
                # File content download
                data = {
                    "name": f"{skill_slug}.py",
                    "sha": "remote_sha_111",
                    "content": b64_code,
                    "encoding": "base64"
                }
                resp.read.return_value = json.dumps(data).encode("utf-8")
                return resp
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        mock_urlopen.side_effect = mock_side_effect

        # Ensure skill is not in DB or on disk prior to test
        db.delete_dynamic_skill(skill_slug)
        local_file = os.path.join(self.temp_dir, f"{skill_slug}.py")
        if os.path.exists(local_file):
            os.remove(local_file)

        # Run restore_dynamic_skills
        restored = db.restore_dynamic_skills(skills_dir=self.temp_dir, install_requirements=False)

        # 1. File must have been downloaded to disk
        self.assertTrue(os.path.exists(local_file), "File was not written to disk")
        with open(local_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), skill_code)

        # 2. Skill must be registered in SQLite dynamic_skills
        entry = db.get_dynamic_skill(skill_slug)
        self.assertIsNotNone(entry, "Skill was not registered in SQLite dynamic_skills")
        self.assertEqual(entry["skill_name"], skill_slug)
        self.assertEqual(entry["description"], "Remote GitHub Calculator")
        self.assertIn("гиткальк", entry["triggers"])
        self.assertIn("облаковычислитель", entry["triggers"])
        self.assertIn("sympy", entry["requirements"])
        self.assertEqual(entry["code"], skill_code)

        # Clean up
        db.delete_dynamic_skill(skill_slug)

    @patch("urllib.request.urlopen")
    def test_startup_restore_resilient_to_github_failure(self, mock_urlopen):
        # Even if GitHub API returns 500 or network fails, restore_dynamic_skills must complete locally
        mock_urlopen.side_effect = urllib.error.HTTPError("https://api.github.com/...", 500, "Error", {}, MagicMock(read=lambda: b""))

        # Pre-seed a local skill on disk
        local_slug = "test_local_only"
        local_code = (
            "# -*- coding: utf-8 -*-\n"
            "# SKILL_NAME: test_local_only\n"
            "# DESCRIPTION: Local fallback\n"
            "# TRIGGERS: локалтест\n"
            "print('Local only!')\n"
        )
        local_file = os.path.join(self.temp_dir, f"{local_slug}.py")
        with open(local_file, "w", encoding="utf-8") as f:
            f.write(local_code)

        # Run restore_dynamic_skills without crashing
        db.restore_dynamic_skills(skills_dir=self.temp_dir, install_requirements=False)

        # Verify local skill was still seeded
        entry = db.get_dynamic_skill(local_slug)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["description"], "Local fallback")

        # Clean up
        db.delete_dynamic_skill(local_slug)


class TestDynamicAgentGitHubIntegration(unittest.TestCase):
    def setUp(self):
        db.init_db()

    @patch("dynamic_agent.register_extension")
    @patch("github_sync.push_skill_to_github")
    def test_dynamic_agent_pushes_healed_skill_to_github(self, mock_push, mock_register):
        mock_push.return_value = (True, {"commit": {"sha": "healed_123"}})

        temp_dir = tempfile.mkdtemp()
        try:
            # We will test the execution of execute_autonomous_task with a task that triggers self-healing
            # or direct execution
            broken_first = """# -*- coding: utf-8 -*-
# SKILL_NAME: test_gh_autoheal
# DESCRIPTION: Healed skill
# TRIGGERS: гитхил
# REQUIREMENTS:
import sys
if not os.environ.get('HEALED'):
    raise RuntimeError("Needs repair")
print("Healed and working!")
"""
            healed_code = """# -*- coding: utf-8 -*-
# SKILL_NAME: test_gh_autoheal
# DESCRIPTION: Healed skill
# TRIGGERS: гитхил
# REQUIREMENTS:
print("Healed and working!")
"""
            attempts = [0]
            def fake_ai(prompt, **kwargs):
                attempts[0] += 1
                if "исправлению" in prompt or "упал" in prompt:
                    return f"```python\n{healed_code}\n```"
                return f"```python\n{broken_first}\n```"

            res_text, res_media = dynamic_agent.execute_autonomous_task(
                task_text="сделай скрипт гитхил",
                sender_name="Тестер",
                ask_ai_fn=fake_ai
            )

            # push_skill_to_github must have been called
            self.assertTrue(mock_push.called, "push_skill_to_github was not called after self-healing success")
            call_kwargs = mock_push.call_args[1] if mock_push.call_args[1] else {}
            call_args = mock_push.call_args[0] if mock_push.call_args[0] else ()

            passed_name = call_kwargs.get("skill_name") or (call_args[0] if len(call_args) > 0 else None)
            self.assertEqual(passed_name, "test_gh_autoheal")

            # Clean up
            db.delete_dynamic_skill("test_gh_autoheal")
            sk_file = os.path.join(dynamic_agent.SKILLS_DIR, "test_gh_autoheal.py")
            if os.path.exists(sk_file):
                os.remove(sk_file)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
