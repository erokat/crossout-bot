# -*- coding: utf-8 -*-
"""
test_stemming_and_regex.py - Unit tests for Russian stemming, topic regex with 'ё',
and package/module mapping in db.py.
"""

import unittest
from unittest.mock import patch, MagicMock

import db


class TestStemmingAndRegex(unittest.TestCase):
    def test_stem_memory_word(self):
        # 3 letters or fewer: unchanged
        self.assertEqual(db.stem_memory_word("кот"), "кот")
        self.assertEqual(db.stem_memory_word("бот"), "бот")
        self.assertEqual(db.stem_memory_word("ии"), "ии")

        # 4-letter words: truncate 1 character
        self.assertEqual(db.stem_memory_word("утюг"), "утю")
        self.assertEqual(db.stem_memory_word("птур"), "пту")
        self.assertEqual(db.stem_memory_word("мама"), "мам")

        # 5+ letter words: truncate 2 characters
        self.assertEqual(db.stem_memory_word("газген"), "газг")
        self.assertEqual(db.stem_memory_word("машина"), "маши")
        self.assertEqual(db.stem_memory_word("самолёт"), "самол")
        self.assertEqual(db.stem_memory_word("вертолёты"), "вертолё")

    def test_topic_regex_with_yo_and_boundaries(self):
        test_cases = [
            ("Запомни: про самолёт это летающий аппарат", "самолёт"),
            ("Запомни про вертолёт что он летает", "вертолёт"),
            ("Бот, насчет ёжика это колючий зверь", "ёжика"),
            ("по поводу учёбы: Ярик учится в универе", "учёбы"),
            ("запомни об актёре фильм хороший", "актёре фильм хороший")
        ]

        for text, expected_topic in test_cases:
            with patch("db.sync_memories_to_disk"), patch("db.sync_memories_to_cloud"):
                with patch("db.get_db") as mock_get_db:
                    mock_conn = MagicMock()
                    mock_get_db.return_value.__enter__.return_value = mock_conn
                    
                    db.save_bot_memory(fact=text, full_text=text, author="Миша")
                    
                    self.assertTrue(mock_conn.execute.called)
                    call_args = mock_conn.execute.call_args[0]
                    saved_topic = call_args[1][0]
                    self.assertEqual(saved_topic.lower(), expected_topic.lower())

    def test_typing_extensions_not_in_stdlib(self):
        self.assertNotIn("typing_extensions", db.STD_LIB_MODULES)
        # typing_extensions should be allowed as requirement
        self.assertEqual(db.clean_requirement_name("typing_extensions>=4.0.0"), "typing_extensions>=4.0.0")

    def test_package_module_mapping(self):
        self.assertIn("pillow", db.PACKAGE_MODULE_MAPPING)
        self.assertEqual(db.PACKAGE_MODULE_MAPPING["pillow"], "PIL")

    def test_clean_requirement_name_filters_stdlib_and_internal(self):
        # Builtin/stdlib rejected
        self.assertIsNone(db.clean_requirement_name("sys"))
        self.assertIsNone(db.clean_requirement_name("os"))
        self.assertIsNone(db.clean_requirement_name("json"))
        
        # Internal modules rejected
        self.assertIsNone(db.clean_requirement_name("config"))
        self.assertIsNone(db.clean_requirement_name("db"))
        self.assertIsNone(db.clean_requirement_name("dynamic_agent"))

        # Valid 3rd party packages accepted
        self.assertEqual(db.clean_requirement_name("requests"), "requests")
        self.assertEqual(db.clean_requirement_name("pillow"), "pillow")


if __name__ == "__main__":
    unittest.main()
