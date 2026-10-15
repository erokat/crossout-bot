# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import re
import unittest
import tempfile
import shutil
import subprocess

# Add codebase to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import db
import video_editor
import dynamic_agent

class TestVideoSpeedParser(unittest.TestCase):
    def test_speed_parser_does_not_parse_years_or_durations(self):
        # Texts containing years, random numbers, or duration units should not parse as speed multipliers
        test_cases = [
            ("ускорь видео 2024", 2.0),
            ("ускорь видос 2024 года", 2.0),
            ("ускорь видео за 2023 год", 2.0),
            ("сделай быстрее видос 1999", 2.0),
            ("ускорь видео в 2024 году", 2.0),
            ("ускорь на 5 минут", 2.0),
            ("ускорь видео в 2 часа", 2.0),
            ("сделай быстрее на 10 секунд", 2.0),
        ]
        for text, expected in test_cases:
            t = text.lower().strip()
            speed = 2.0
            if "втрое" in t:
                speed = 3.0
            elif "вчетверо" in t:
                speed = 4.0
            elif "вдвое" in t:
                speed = 2.0
            else:
                m = re.search(r"(?:(?:в|на)\s+)?(\d+(?:[.,]\d+)?)\s*(?:[xх]|раз[а-я]*)\b", t)
                if not m:
                    m = re.search(r"\b(?:в|на)\s+(\d+(?:[.,]\d+)?)(?!\s*(?:год[а-я]*|мин[а-я]*|сек[а-я]*|час[а-я]*|дн[а-я]*|лет|мес[а-я]*))\b", t)
                if m:
                    try:
                        val = float(m.group(1).replace(",", "."))
                        if 1.0 <= val <= 10.0:
                            speed = min(4.0, max(1.2, val))
                    except ValueError:
                        speed = 2.0
            self.assertEqual(speed, expected, f"Failed for text: {text}")

    def test_speed_parser_explicit_multipliers(self):
        test_cases = [
            ("ускорь в 2 раза", 2.0),
            ("ускорь в 3 раза", 3.0),
            ("ускорь 1.5x", 1.5),
            ("ускорь на 2х", 2.0),
            ("сделай быстрее в 4 раза", 4.0),
            ("ускорь 5x", 4.0),  # Clamped to max 4.0
            ("ускорь 0.5x", 2.0), # Outside 1.0-10.0
            ("ускорь втрое", 3.0),
            ("ускорь вдвое", 2.0),
        ]
        for text, expected in test_cases:
            t = text.lower().strip()
            speed = 2.0
            if "втрое" in t:
                speed = 3.0
            elif "вчетверо" in t:
                speed = 4.0
            elif "вдвое" in t:
                speed = 2.0
            else:
                m = re.search(r"(?:(?:в|на)\s+)?(\d+(?:[.,]\d+)?)\s*(?:[xх]|раз[а-я]*)\b", t)
                if not m:
                    m = re.search(r"\b(?:в|на)\s+(\d+(?:[.,]\d+)?)(?!\s*(?:год[а-я]*|мин[а-я]*|сек[а-я]*|час[а-я]*|дн[а-я]*|лет|мес[а-я]*))\b", t)
                if m:
                    try:
                        val = float(m.group(1).replace(",", "."))
                        if 1.0 <= val <= 10.0:
                            speed = min(4.0, max(1.2, val))
                    except ValueError:
                        speed = 2.0
            self.assertAlmostEqual(speed, expected, delta=0.01, msg=f"Failed for text: {text}")


class TestCoreProtection(unittest.TestCase):
    def test_protected_files(self):
        core_files = [
            "keep_alive.py",
            "wait_for_yarik.py",
            "db.py",
            "send.py",
            "session.session",
            "crossout_session.session",
            "config.py",
            "config.json",
            "Dockerfile"
        ]
        for cf in core_files:
            target_path = os.path.join(BASE_DIR, cf)
            self.assertFalse(dynamic_agent.is_safe_skill_path(target_path), f"Should NOT be safe: {target_path}")
            self.assertFalse(dynamic_agent.is_safe_skill_path(cf), f"Should NOT be safe: {cf}")

    def test_allowed_paths(self):
        allowed = [
            os.path.join(BASE_DIR, "skills", "test_skill.py"),
            os.path.join(BASE_DIR, "media", "output.png"),
            os.path.join(BASE_DIR, "skills", "crypto_tool.py"),
        ]
        for p in allowed:
            self.assertTrue(dynamic_agent.is_safe_skill_path(p), f"Should be safe: {p}")


class TestDynamicSkillsDatabase(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_save_and_get_dynamic_skill(self):
        skill_name = "test_calc_skill"
        file_path = "skills/test_calc_skill.py"
        triggers = ["посчитай", "калькулятор", "вычисли"]
        description = "Тестовый калькулятор для вычислений"
        requirements = ["requests"]
        code = "# -*- coding: utf-8 -*-\nprint('Hello calc!')\n"

        db.save_dynamic_skill(skill_name, file_path, triggers, description, requirements, code)
        retrieved = db.get_dynamic_skill(skill_name)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["skill_name"], skill_name)
        self.assertEqual(retrieved["triggers"], triggers)
        self.assertEqual(retrieved["description"], description)
        self.assertEqual(retrieved["requirements"], requirements)
        self.assertEqual(retrieved["code"], code)

        all_skills = db.list_dynamic_skills()
        names = [s["skill_name"] for s in all_skills]
        self.assertIn(skill_name, names)

        # Cleanup
        db.delete_dynamic_skill(skill_name)
        self.assertIsNone(db.get_dynamic_skill(skill_name))

    def test_restore_dynamic_skills_two_way_sync(self):
        test_dir = tempfile.mkdtemp()
        try:
            # Seed a skill on disk first
            disk_skill = "test_disk_seeded"
            disk_code = """# -*- coding: utf-8 -*-
# SKILL_NAME: test_disk_seeded
# DESCRIPTION: Seeded from disk
# TRIGGERS: сидтест, дисктест
# REQUIREMENTS:
print('Seeded!')
"""
            disk_file = os.path.join(test_dir, f"{disk_skill}.py")
            with open(disk_file, "w", encoding="utf-8") as f:
                f.write(disk_code)

            # Also create a skill in SQLite that is NOT yet on disk
            db_skill = "test_db_to_disk"
            db_code = """# -*- coding: utf-8 -*-
# SKILL_NAME: test_db_to_disk
# DESCRIPTION: From DB to disk
# TRIGGERS: дбтест
# REQUIREMENTS:
print('From DB!')
"""
            db.save_dynamic_skill(
                skill_name=db_skill,
                file_path=f"skills/{db_skill}.py",
                triggers=["дбтест"],
                description="From DB to disk",
                requirements=[],
                code=db_code
            )

            # Run restore_dynamic_skills on test_dir
            db.restore_dynamic_skills(skills_dir=test_dir, install_requirements=False)

            # 1. Verify disk_skill was seeded into DB
            seeded = db.get_dynamic_skill(disk_skill)
            self.assertIsNotNone(seeded)
            self.assertEqual(seeded["description"], "Seeded from disk")
            self.assertIn("сидтест", seeded["triggers"])

            # 2. Verify db_skill was written to disk
            db_file_on_disk = os.path.join(test_dir, f"{db_skill}.py")
            self.assertTrue(os.path.exists(db_file_on_disk))
            with open(db_file_on_disk, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), db_code)

            # Cleanup DB
            db.delete_dynamic_skill(disk_skill)
            db.delete_dynamic_skill(db_skill)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


class TestDynamicSkillLookup(unittest.TestCase):
    def setUp(self):
        db.init_db()
        db.restore_dynamic_skills(install_requirements=False)

    def test_weather_skill_matching(self):
        weather_queries = [
            "какая погода?",
            "погода",
            "скажи погоду",
            "прогноз погоды",
            "температура на улице",
            "погода в тирасполе",
            "какой прогноз?",
            "тирасполь"
        ]
        for q in weather_queries:
            script_path, skill_info = dynamic_agent.find_existing_skill(q)
            self.assertIsNotNone(skill_info, f"Failed to match query: '{q}'")
            self.assertEqual(skill_info["skill_name"], "weather_tiraspol", f"Matched wrong skill for '{q}'")

    def test_non_matching_queries(self):
        non_matching = [
            "привет бот",
            "как дела?",
            "сделай мем про ховеры",
            "посчитай мне 2 + 2",
            "что делаешь?"
        ]
        for q in non_matching:
            script_path, skill_info = dynamic_agent.find_existing_skill(q)
            self.assertIsNone(skill_info, f"Should NOT have matched '{q}', but got {skill_info}")


class TestConfirmationSQLite(unittest.TestCase):
    def setUp(self):
        db.init_db()

    def test_confirmation_lifecycle(self):
        import uuid
        req_id = f"test_{uuid.uuid4().hex[:8]}"
        question = "Удалить тестовое сообщение?"
        db.create_confirmation(req_id, question, message_id=999, initiator="Ярик")

        pending = db.get_latest_pending_confirmation()
        self.assertIsNotNone(pending)
        self.assertEqual(pending["req_id"], req_id)
        self.assertEqual(pending["status"], "pending")

        # Resolve confirmation
        db.resolve_confirmation(req_id, "approved", comment="Тестовое разрешение")
        resolved = db.get_confirmation(req_id)
        self.assertEqual(resolved["status"], "approved")
        self.assertEqual(resolved["comment"], "Тестовое разрешение")

    def test_confirmation_text_regex_no_substring_false_positives(self):
        # Words containing 'да', 'нет', 'ок' as substrings should not trigger resolution
        false_positive_words = ["погода", "задача", "интернет", "около", "покой", "карандаш"]
        for text in false_positive_words:
            t_lower = text.strip().lower()
            is_rejection = bool(re.search(r"(?:\b(?:нет|отказ[а-я]*|нельзя|отмен[а-я]*|отбой|reject)\b|(?<!\S)-(?!\S))", t_lower) or re.search(r"\bне\s+(?:удаляй|надо|трогай|делай|разрешай)", t_lower))
            is_approval = bool(not is_rejection and re.search(r"(?:\b(?:да|разреш[а-я]*|ок|удаляй|сноси|подтвержд[а-я]*|yes)\b|(?<!\S)\+(?!\S))", t_lower))
            self.assertFalse(is_approval, f"'{text}' falsely classified as approval!")
            self.assertFalse(is_rejection, f"'{text}' falsely classified as rejection!")

        # Real confirmation keywords
        true_approvals = ["да", "ок", "разрешаю", "удаляй", "сноси", "подтверждаю", "+", "yes"]
        for text in true_approvals:
            t_lower = text.strip().lower()
            is_rejection = bool(re.search(r"(?:\b(?:нет|отказ[а-я]*|нельзя|отмен[а-я]*|отбой|reject)\b|(?<!\S)-(?!\S))", t_lower) or re.search(r"\bне\s+(?:удаляй|надо|трогай|делай|разрешай)", t_lower))
            is_approval = bool(not is_rejection and re.search(r"(?:\b(?:да|разреш[а-я]*|ок|удаляй|сноси|подтвержд[а-я]*|yes)\b|(?<!\S)\+(?!\S))", t_lower))
            self.assertTrue(is_approval, f"'{text}' failed to classify as approval!")

        true_rejections = ["нет", "отмена", "нельзя", "отбой", "отказ", "не удаляй", "-"]
        for text in true_rejections:
            t_lower = text.strip().lower()
            is_rejection = bool(re.search(r"(?:\b(?:нет|отказ[а-я]*|нельзя|отмен[а-я]*|отбой|reject)\b|(?<!\S)-(?!\S))", t_lower) or re.search(r"\bне\s+(?:удаляй|надо|трогай|делай|разрешай)", t_lower))
            self.assertTrue(is_rejection, f"'{text}' failed to classify as rejection!")


class TestDynamicSkillExecutionAndHealing(unittest.TestCase):
    def test_run_script_process_group_timeout(self):
        # Verify run_script does not hang and kills process group on timeout
        fp = os.path.join(BASE_DIR, "skills", "test_timeout_worker.py")
        code = """import subprocess, time
subprocess.Popen(["sleep", "9876"])
time.sleep(100)
"""
        with open(fp, "w", encoding="utf-8") as f:
            f.write(code)

        try:
            t0 = time.monotonic()
            rc, stdout, stderr = dynamic_agent.run_script(fp, timeout=2)
            dt = time.monotonic() - t0
            self.assertEqual(rc, -1)
            self.assertIn("Превышено максимальное время", stderr)
            self.assertLess(dt, 6.0, "run_script took too long to terminate process group!")
        finally:
            if os.path.exists(fp):
                os.remove(fp)
            subprocess.run(["pkill", "-9", "-f", "sleep 9876"], capture_output=True)

    def test_real_execute_autonomous_task_self_healing(self):
        # Verify execute_autonomous_task's real self-healing loop
        skill_name = "test_autoheal_unit"
        calls = []

        def mock_ai(prompt, photo_path=None):
            calls.append(prompt)
            if "упал с кодом" in prompt or "ZeroDivisionError" in prompt:
                return f'''```python
# SKILL_NAME: {skill_name}
# DESCRIPTION: Healed unit skill
# TRIGGERS: юнитхил
# REQUIREMENTS:
print("HEALED OUTPUT 999")
```'''
            else:
                return f'''```python
# SKILL_NAME: {skill_name}
# DESCRIPTION: Broken unit skill
# TRIGGERS: юнитхил
# REQUIREMENTS:
x = 1 / 0
```'''

        try:
            res_text, res_media = dynamic_agent.execute_autonomous_task(
                "сделай юнитхил",
                "Тестер",
                ask_ai_fn=mock_ai
            )
            self.assertIn("HEALED OUTPUT 999", res_text)
            self.assertGreaterEqual(len(calls), 2, "Self-healing loop did not call AI with error prompt!")

            # Verify persisted to SQLite
            saved = db.get_dynamic_skill(skill_name)
            self.assertIsNotNone(saved)
            self.assertEqual(saved["description"], "Healed unit skill")
            self.assertIn("юнитхил", saved["triggers"])

        finally:
            db.delete_dynamic_skill(skill_name)
            target_file = os.path.join(BASE_DIR, "skills", f"{skill_name}.py")
            if os.path.exists(target_file):
                os.remove(target_file)
            reg = dynamic_agent.load_registry()
            if skill_name in reg:
                del reg[skill_name]
                dynamic_agent.save_registry(reg)


if __name__ == "__main__":
    unittest.main()
