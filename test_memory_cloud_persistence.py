# -*- coding: utf-8 -*-
"""
test_memory_cloud_persistence.py - Unit tests for bot memory synchronization
to GitHub and Google Drive, and cold-start restoration.
"""

import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import db
import github_sync
import gdrive


class TestMemoryCloudPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_memories_file = db.MEMORIES_FILE
        self.test_memories_file = os.path.join(self.temp_dir, "bot_memories.json")
        db.MEMORIES_FILE = self.test_memories_file

    def tearDown(self):
        db.MEMORIES_FILE = self.orig_memories_file
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch("github_sync.push_memories_to_github")
    @patch("gdrive.get_valid_access_token")
    @patch("gdrive.upload_memory_to_drive")
    def test_sync_memories_to_cloud_invokes_both(self, mock_gdrive_upload, mock_token, mock_gh_push):
        mock_token.return_value = "fake_access_token"
        
        # Write dummy memory file
        with open(self.test_memories_file, "w", encoding="utf-8") as f:
            json.dump([{"topic": "тест", "fact": "факт"}], f)

        db.sync_memories_to_cloud(async_mode=False)

        mock_gh_push.assert_called_once_with(self.test_memories_file)
        mock_gdrive_upload.assert_called_once_with(self.test_memories_file)

    @patch("db.sync_memories_to_cloud")
    def test_save_and_delete_triggers_cloud_sync(self, mock_cloud_sync):
        # Save memory
        res = db.save_bot_memory(fact="ПТУР летит медленно", topic="птур", author="Миша")
        self.assertTrue(res)
        self.assertTrue(mock_cloud_sync.called)

        mock_cloud_sync.reset_mock()

        # Delete memory
        del_count = db.delete_bot_memory("птур")
        self.assertGreaterEqual(del_count, 1)
        self.assertTrue(mock_cloud_sync.called)

        mock_cloud_sync.reset_mock()

        # Clear all
        db.clear_all_bot_memories()
        self.assertTrue(mock_cloud_sync.called)

    @patch("github_sync.fetch_memories_from_github")
    def test_restore_bot_memories_from_github(self, mock_fetch_gh):
        # Ensure file does not exist initially
        if os.path.exists(self.test_memories_file):
            os.remove(self.test_memories_file)

        mock_fetch_gh.return_value = json.dumps([
            {"topic": "сервер", "fact": "работает на Koyeb/Render", "author": "Миша"}
        ])

        with patch("db.get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_get_db.return_value.__enter__.return_value = mock_conn
            mock_cur = MagicMock()
            mock_cur.fetchone.return_value = [0]  # count = 0
            mock_conn.execute.return_value = mock_cur

            restored_count = db.restore_bot_memories()
            self.assertEqual(restored_count, 1)
            self.assertTrue(os.path.exists(self.test_memories_file))
            with open(self.test_memories_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data[0]["topic"], "сервер")

    @patch("github_sync.get_github_config")
    @patch("github_sync.get_file_sha")
    @patch("urllib.request.urlopen")
    def test_push_memories_to_github_has_skip_render_tag(self, mock_urlopen, mock_sha, mock_config):
        mock_config.return_value = ("fake_token", "erokat/crossout-bot")
        mock_sha.return_value = "old_sha_123"

        with open(self.test_memories_file, "w", encoding="utf-8") as f:
            f.write("[]")

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"commit": {"sha": "abcdef1234"}}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = False
        mock_urlopen.return_value = mock_resp

        ok, res = github_sync.push_memories_to_github(self.test_memories_file, commit_message="Update memories")
        self.assertTrue(ok)

        self.assertTrue(mock_urlopen.called)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data.decode("utf-8"))
        self.assertIn("[skip render]", payload["message"])
        self.assertEqual(payload["sha"], "old_sha_123")


    @patch("github_sync.fetch_memories_from_github")
    def test_restore_bot_memories_when_local_is_empty_brackets(self, mock_fetch_gh):
        # Local file exists with "[]" (as checked into git repository)
        with open(self.test_memories_file, "w", encoding="utf-8") as f:
            f.write("[]")

        mock_fetch_gh.return_value = json.dumps([
            {"topic": "день рождения", "fact": "1 мая", "author": "Миша"}
        ])

        with patch("db.get_db") as mock_get_db:
            mock_conn = MagicMock()
            mock_get_db.return_value.__enter__.return_value = mock_conn
            mock_cur = MagicMock()
            mock_cur.fetchall.return_value = []
            mock_conn.execute.return_value = mock_cur

            restored_count = db.restore_bot_memories()
            self.assertEqual(restored_count, 1)
            with open(self.test_memories_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data[0]["topic"], "день рождения")


if __name__ == "__main__":
    unittest.main()
