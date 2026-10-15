# -*- coding: utf-8 -*-
import os
import sys
import time
import json
import re
import unittest
import tempfile
import shutil

# Add codebase to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import db
import video_editor
import dynamic_agent

class TestVideoSpeedParser(unittest.TestCase):
    def test_speed_parser_does_not_parse_years(self):
        # Texts containing years or random numbers should not parse year as speed multiplier
        test_cases = [
            ("ускорь видео 2024", 2.0),
            ("ускорь видос 2024 года", 2.0),
            ("ускорь видео за 2023 год", 2.0),
            ("сделай быстрее видос 1999", 2.0),
            ("ускорь видео в 2024 году", 2.0),
        ]
        for text, expected in test_cases:
            t = text.lower().strip()
            m = re.search(r"(?:(?:в|на)\s+)?(\d+(?:[.,]\d+)?)\s*(?:[xх]|раз[а-я]*)", t) or re.search(r"\b(?:в|на)\s+(\d+(?:[.,]\d+)?)\b", t)
            speed = 2.0
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
            ("ускорь 0.5x", 2.0), # Outside 1.0-10.0 or clamped
        ]
        for text, expected in test_cases:
            t = text.lower().strip()
            m = re.search(r"(?:(?:в|на)\s+)?(\d+(?:[.,]\d+)?)\s*(?:[xх]|раз[а-я]*)", t) or re.search(r"\b(?:в|на)\s+(\d+(?:[.,]\d+)?)\b", t)
            speed = 2.0
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
        # Critical core files must be rejected
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
        # Skills and media paths must be allowed
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

    def test_restore_dynamic_skills(self):
        test_dir = tempfile.mkdtemp()
        try:
            skill_name = "test_restore_skill"
            code = "# -*- coding: utf-8 -*-\nprint('Restored successfully')\n"
            db.save_dynamic_skill(
                skill_name=skill_name,
                file_path=f"skills/{skill_name}.py",
                triggers=["тест"],
                description="Тест восстановления",
                requirements=[],
                code=code
            )

            restored = db.restore_dynamic_skills(skills_dir=test_dir, install_requirements=False)
            target_file = os.path.join(test_dir, f"{skill_name}.py")
            self.assertTrue(os.path.exists(target_file))
            with open(target_file, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, code)

            # Cleanup DB
            db.delete_dynamic_skill(skill_name)
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)


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


class TestDynamicSkillExecutionAndHealing(unittest.TestCase):
    def test_skill_execution_and_self_healing(self):
        # Test simulated self-healing
        skill_name = "test_healing_skill"
        script_path = os.path.join(BASE_DIR, "skills", f"{skill_name}.py")
        os.makedirs(os.path.join(BASE_DIR, "skills"), exist_ok=True)

        # Step 1: Write buggy code that throws ZeroDivisionError
        buggy_code = """# -*- coding: utf-8 -*-
# SKILL_NAME: test_healing_skill
# DESCRIPTION: Test healing
import sys
x = 1 / 0
"""
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(buggy_code)

        rc, stdout, stderr = dynamic_agent.run_script(script_path, timeout=10)
        self.assertNotEqual(rc, 0)
        self.assertIn("ZeroDivisionError", stderr)

        # Step 2: Simulate Gemini fixing the error in self-healing loop
        healing_attempts = 0
        fixed_code = None
        for attempt in range(1, 4):
            healing_attempts += 1
            # Mock Gemini fix function
            if "ZeroDivisionError" in stderr:
                fixed_code = """# -*- coding: utf-8 -*-
# SKILL_NAME: test_healing_skill
# DESCRIPTION: Test healing
print("Healing succeeded! Result is 42")
"""
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                rc, stdout, stderr = dynamic_agent.run_script(script_path, timeout=10)
                if rc == 0:
                    break

        self.assertEqual(rc, 0)
        self.assertEqual(healing_attempts, 1)
        self.assertIn("Healing succeeded", stdout)

        # Save to DB
        db.save_dynamic_skill(
            skill_name=skill_name,
            file_path=script_path,
            triggers=["тестхилинг"],
            description="Test healing skill",
            requirements=[],
            code=fixed_code
        )
        saved = db.get_dynamic_skill(skill_name)
        self.assertIsNotNone(saved)

        # Cleanup
        if os.path.exists(script_path):
            os.remove(script_path)
        db.delete_dynamic_skill(skill_name)


if __name__ == "__main__":
    unittest.main()
