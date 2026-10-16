import os
import sys
import unittest
import tempfile
import json
import shutil

# Ensure workspace is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import (
    init_db,
    save_bot_memory,
    get_relevant_memories,
    format_memory_context,
    get_all_memories,
    delete_bot_memory,
    clear_all_bot_memories,
    restore_bot_memories,
    MEMORIES_FILE
)
from keep_alive import is_memory_request, process_memory_command

class TestBotMemoryAndPip(unittest.TestCase):
    def setUp(self):
        # Clear all memories before each test
        clear_all_bot_memories()

    def tearDown(self):
        clear_all_bot_memories()

    def test_save_and_retrieve_memory(self):
        saved = save_bot_memory(
            fact="Все шутки про маму Нолана связаны с тем, что она много весит.",
            topic="мама Нолана",
            full_text="Бот, запомни: все шутки про маму Нолана связаны с тем, что она много весит.",
            author="Ярик"
        )
        self.assertTrue(saved)
        mems = get_all_memories()
        self.assertEqual(len(mems), 1)
        self.assertEqual(mems[0]["topic"], "мама Нолана")
        self.assertIn("много весит", mems[0]["fact"])
        self.assertEqual(mems[0]["author"], "Ярик")

    def test_auto_topic_deduction(self):
        text = 'Бот,запомни:"Все шутки про маму Нолана связаны с тем,что она много весит".Пример:"Радиус живота мамы Нолана настолько большой,что когда ученые попытались его измерить, ввели новое понятие - луч"'
        saved = save_bot_memory(
            fact=text,
            full_text=text,
            author="Ярик"
        )
        self.assertTrue(saved)
        mems = get_all_memories()
        self.assertEqual(len(mems), 1)
        self.assertTrue(len(mems[0]["topic"]) > 0)
        self.assertIn("Нолан", mems[0]["topic"] + mems[0]["fact"])

    def test_relevant_memories_search(self):
        save_bot_memory(
            fact="Шутки про маму Нолана связаны с весом",
            topic="мама Нолана",
            full_text="все шутки про маму нолана",
            author="Ярик"
        )
        save_bot_memory(
            fact="В Crossout ховеры летают над землей",
            topic="Crossout ховеры",
            full_text="ховеры летают",
            author="Миша"
        )

        nolan_mems = get_relevant_memories("сделай мем про маму Нолана")
        self.assertTrue(any("Нолан" in m["fact"] or "Нолан" in m["topic"] for m in nolan_mems))

        hover_mems = get_relevant_memories("ховеры в пустошах")
        self.assertTrue(any("ховер" in m["fact"].lower() for m in hover_mems))

    def test_format_memory_context(self):
        save_bot_memory(
            fact="Кошка любит спать на клавиатуре",
            topic="кошка",
            full_text="запомни что кошка спит на клавиатуре",
            author="Миша"
        )
        ctx = format_memory_context("расскажи про кошку")
        self.assertIn("ДОЛГОВРЕМЕННАЯ ПАМЯТЬ БОТА", ctx)
        self.assertIn("кошка", ctx.lower())
        self.assertIn("клавиатуре", ctx.lower())

    def test_delete_and_clear_memory(self):
        save_bot_memory(fact="Факт номер 1", topic="физика", full_text="физика это наука")
        save_bot_memory(fact="Факт номер 2", topic="химия", full_text="химия это опыты")
        self.assertEqual(len(get_all_memories()), 2)

        deleted = delete_bot_memory("физика")
        self.assertEqual(deleted, 1)
        self.assertEqual(len(get_all_memories()), 1)
        self.assertEqual(get_all_memories()[0]["topic"], "химия")

        clear_all_bot_memories()
        self.assertEqual(len(get_all_memories()), 0)

    def test_disk_sync_and_restore(self):
        save_bot_memory(fact="Синхронизированный факт", topic="тест", full_text="тест синхронизации")
        self.assertTrue(os.path.exists(MEMORIES_FILE))
        with open(MEMORIES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data), 1)
        self.assertIn("Синхронизированный факт", data[0]["fact"])

        # Wipe DB table only, leaving json on disk
        from db import get_db
        with get_db() as conn:
            conn.execute("DELETE FROM bot_memory")
        self.assertEqual(len(get_all_memories()), 0)

        restored = restore_bot_memories()
        self.assertEqual(restored, 1)
        self.assertEqual(len(get_all_memories()), 1)

    def test_process_memory_command_yarik(self):
        # 1. Exact prompt from screenshot
        msg = 'Бот,запомни:"Все шутки про маму Нолана связаны с тем,что она много весит".Пример:"Радиус живота мамы Нолана настолько большой,что когда ученые попытались его измерить, ввели новое понятие - луч"'
        self.assertTrue(is_memory_request(msg))

        resp = process_memory_command(msg, sender_name="Ярик", is_owner=False)
        self.assertIsNotNone(resp)
        self.assertIn("Запомнил намертво, Ярик!", resp)
        self.assertIn("долговременную память", resp)

        # 2. Recall request
        recall_msg = "Бот, вспомни про маму Нолана"
        self.assertTrue(is_memory_request(recall_msg))
        recall_resp = process_memory_command(recall_msg, sender_name="Ярик", is_owner=False)
        self.assertIn("Ярик, вот что я помню по теме «маму Нолана»", recall_resp)
        self.assertIn("много весит", recall_resp)

        # 3. List all memories
        list_msg = "Бот, что ты помнишь?"
        self.assertTrue(is_memory_request(list_msg))
        list_resp = process_memory_command(list_msg, sender_name="Ярик", is_owner=False)
        self.assertIn("вот что записано в моей долговременной памяти", list_resp)

        # 4. Forget topic
        forget_msg = "Бот, забудь про маму Нолана"
        self.assertTrue(is_memory_request(forget_msg))
        forget_resp = process_memory_command(forget_msg, sender_name="Ярик", is_owner=False)
        self.assertIn("Удалил из памяти", forget_resp)

        # 5. Verify deleted
        self.assertEqual(len(get_all_memories()), 0)

    def test_process_memory_command_owner(self):
        # 1. Owner save command
        msg = "Бот, сохрани в память: У Миши день рождения 1 мая"
        self.assertTrue(is_memory_request(msg))
        resp = process_memory_command(msg, sender_name="Миша", is_owner=True)
        self.assertIn("Запомнил намертво, Миша!", resp)
        self.assertNotIn("Ярик", resp)

        # 2. Owner memory list
        list_msg = "Бот, покажи память"
        list_resp = process_memory_command(list_msg, sender_name="Миша", is_owner=True)
        self.assertIn("Миша, вот что записано", list_resp)
        self.assertIn("1 мая", list_resp)

        # 3. Owner memory clear
        wipe_msg = "Бот, очисти память"
        wipe_resp = process_memory_command(wipe_msg, sender_name="Миша", is_owner=True)
        self.assertIn("Всю долговременную память зачистил начисто", wipe_resp)
        self.assertEqual(len(get_all_memories()), 0)

    def test_dockerfile_pip_upgrade(self):
        df_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Dockerfile")
        self.assertTrue(os.path.exists(df_path))
        with open(df_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("pip install --no-cache-dir --upgrade pip", content)

if __name__ == "__main__":
    unittest.main()
