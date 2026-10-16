import unittest
from unittest.mock import patch, MagicMock
import time
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from keep_alive import spawn_meme_creator_subagent, handle_yarik_message, handle_owner_message

class TestMemeSubagentRouting(unittest.TestCase):
    @patch("keep_alive.ask_ai", return_value="Ярик, лови мем!")
    @patch("keep_alive.subprocess.run")
    @patch("keep_alive.generate_crossout_meme")
    def test_spawn_meme_creator_subagent_non_blocking(self, mock_gen, mock_subproc, mock_ask_ai):
        mock_gen.return_value = os.path.join(BASE_DIR, "media", "gasgen.png")
        mock_subproc.return_value = MagicMock(returncode=0)

        t_start = time.time()
        thread = spawn_meme_creator_subagent(
            theme="Тест Газгена",
            recipient="yarik",
            reply_to_msg_id=12345,
            meme_index=1,
            total_count=1,
            is_owner_sender=False
        )
        elapsed = time.time() - t_start
        self.assertLess(elapsed, 0.5, "spawn_meme_creator_subagent must return immediately without blocking")
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive(), "Worker thread should complete within timeout")
        mock_gen.assert_called_once()
        self.assertTrue(mock_subproc.called)

    @patch("keep_alive.spawn_meme_creator_subagent")
    def test_handle_yarik_message_meme_routing(self, mock_spawn):
        msg = {
            "id": 99999,
            "sender_id": 6271387044,
            "sender_title": "Yarik",
            "text": "!бот сделай 3 мема про утюг и капкан",
            "reply_to_msg_id": None
        }
        handle_yarik_message(msg)
        self.assertEqual(mock_spawn.call_count, 3, "Should spawn exactly 3 subagents for 3 memes")

    @patch("keep_alive.spawn_meme_creator_subagent")
    def test_handle_yarik_message_non_meme_does_not_spawn_meme_subagents(self, mock_spawn):
        with patch("keep_alive.ask_ai", return_value="Привет Ярик!"):
            msg = {
                "id": 99998,
                "sender_id": 6271387044,
                "sender_title": "Yarik",
                "text": "!бот привет как дела",
                "reply_to_msg_id": None
            }
            with patch("keep_alive.subprocess.run"):
                handle_yarik_message(msg)
            mock_spawn.assert_not_called()

    @patch("keep_alive.spawn_meme_creator_subagent")
    @patch("keep_alive.subprocess.run")
    def test_handle_owner_message_meme_routing(self, mock_subproc, mock_spawn):
        msg = {
            "id": 88888,
            "text": "скинь ярику 2 мема про птур",
            "photo": None
        }
        handle_owner_message(msg)
        self.assertEqual(mock_spawn.call_count, 2, "Should spawn 2 subagents for 2 memes ordered by owner")

if __name__ == "__main__":
    unittest.main()
