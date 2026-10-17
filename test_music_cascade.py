# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch, MagicMock
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import media_finder

class TestMusicCascade(unittest.TestCase):
    def test_parse_music_query(self):
        title, author = media_finder.parse_music_query("DELTARUNE - It's TV Time! от InstrumentManiac")
        self.assertEqual(title, "DELTARUNE - It's TV Time!")
        self.assertEqual(author, "InstrumentManiac")

        title2, author2 = media_finder.parse_music_query("Megalovania by Toby Fox")
        self.assertEqual(title2, "Megalovania")
        self.assertEqual(author2, "Toby Fox")

        title3, author3 = media_finder.parse_music_query("DELTARUNE - It's TV Time!")
        self.assertEqual(title3, "DELTARUNE - It's TV Time!")
        self.assertIsNone(author3)

    def test_score_music_candidate_penalizes_covers(self):
        cover_cand = {
            "title": "It's TV Time! WITH LYRICS - Deltarune Cover Juno Songs",
            "uploader": "NoFace42804",
            "duration": 338
        }
        score = media_finder.score_music_candidate(cover_cand, "DELTARUNE - It's TV Time!")
        # Should be heavily penalized (below 0)
        self.assertLess(score, 0)

    def test_score_music_candidate_rewards_author_and_ost(self):
        ost_cand = {
            "title": "27. It's TV Time! (DELTARUNE Chapter 3+4 Soundtrack)",
            "uploader": "Toby Fox - Topic",
            "duration": 171
        }
        score = media_finder.score_music_candidate(ost_cand, "DELTARUNE - It's TV Time!")
        # Should be awarded for OST and - Topic
        self.assertGreater(score, 150)

        im_cand = {
            "title": "DELTARUNE - It's TV Time!",
            "uploader": "InstrumentManiac",
            "duration": 171
        }
        im_score = media_finder.score_music_candidate(im_cand, "DELTARUNE - It's TV Time!", target_artist="InstrumentManiac")
        self.assertGreater(im_score, 200)

    @patch("media_finder.fetch_candidates")
    @patch("media_finder.download_via_ytdlp")
    def test_find_and_download_music_picks_winner(self, mock_ytdlp, mock_fetch):
        # Candidates from YouTube and SoundCloud
        mock_fetch.side_effect = [
            # YouTube candidates
            [
                {"source": "youtube", "id": "vid123", "url": "https://youtube.com/watch?v=vid123", "title": "DELTARUNE - It's TV Time!", "uploader": "InstrumentManiac", "duration": 170}
            ],
            # SoundCloud candidates (covers)
            [
                {"source": "soundcloud", "id": "sc1", "url": "https://soundcloud.com/noface/juno-cover", "title": "It's TV Time! WITH LYRICS Cover", "uploader": "NoFace42804", "duration": 300}
            ]
        ]
        mock_ytdlp.return_value = ("/fake/music/track.mp3", "DELTARUNE - It's TV Time! - InstrumentManiac")

        with patch("os.path.exists", return_value=False):
            track, title = media_finder.find_and_download_music("DELTARUNE - It's TV Time! от InstrumentManiac")
            self.assertEqual(track, "/fake/music/track.mp3")
            self.assertIn("InstrumentManiac", title)
            # Ensure it chose YouTube direct URL rather than the SoundCloud cover!
            called_url = mock_ytdlp.call_args[0][1]
            self.assertEqual(called_url, "https://youtube.com/watch?v=vid123")

    @patch("media_finder.fetch_candidates")
    @patch("media_finder.download_via_ytdlp")
    @patch("media_finder.stream_invidious_video_id")
    def test_find_and_download_music_invidious_fallback_on_403(self, mock_stream, mock_ytdlp, mock_fetch):
        # YouTube returns winner, but yt-dlp fails (e.g. 403)
        mock_fetch.side_effect = [
            [{"source": "youtube", "id": "vid123", "url": "https://youtube.com/watch?v=vid123", "title": "DELTARUNE - It's TV Time!", "uploader": "InstrumentManiac", "duration": 170}],
            []
        ]
        mock_ytdlp.return_value = (None, "")
        mock_stream.return_value = ("/fake/music/invidious.mp3", "DELTARUNE - It's TV Time! - InstrumentManiac")

        with patch("os.path.exists", return_value=False):
            track, title = media_finder.find_and_download_music("DELTARUNE - It's TV Time! от InstrumentManiac")
            self.assertEqual(track, "/fake/music/invidious.mp3")
            self.assertIn("InstrumentManiac", title)
            mock_stream.assert_called_with("vid123", "DELTARUNE - It's TV Time!", "InstrumentManiac", unittest.mock.ANY, timeout=20)

if __name__ == "__main__":
    unittest.main()
