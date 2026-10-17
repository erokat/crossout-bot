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

    @patch("subprocess.run")
    def test_refine_music_query_via_ai(self, mock_subproc):
        mock_subproc.return_value = MagicMock(return_value=0, returncode=0, stdout="```\nInstrumentManiac - It's TV Time!\n```")
        refined = media_finder.refine_music_query_via_ai("дельторун итс тиви тайм инструментманьяк")
        self.assertEqual(refined, "InstrumentManiac - It's TV Time!")

    @patch("media_finder.refine_music_query_via_ai")
    @patch("media_finder.fetch_candidates")
    @patch("media_finder.download_via_ytdlp")
    @patch("media_finder.search_invidious_audio")
    def test_find_and_download_music_triggers_ai_fallback(self, mock_inv, mock_ytdlp, mock_fetch, mock_refine):
        # Initial search fails to find candidates and fallbacks fail
        # AI refines the query to "Queen - The Show Must Go On"
        # Second search succeeds
        mock_inv.return_value = (None, "")
        mock_refine.return_value = "Queen - The Show Must Go On"
        mock_fetch.side_effect = [
            [], # 1st yt search (empty)
            [], # 1st sc search (empty)
            [{"source": "youtube", "id": "q123", "url": "https://youtube.com/watch?v=q123", "title": "Queen - The Show Must Go On", "uploader": "Queen Official", "duration": 260}], # 2nd yt search
            []  # 2nd sc search
        ]
        def ytdlp_side_effect(source_prefix, target_arg, *args, **kwargs):
            if "youtube.com" in str(target_arg):
                return ("/fake/music/queen.mp3", "Queen - The Show Must Go On")
            return (None, "")
        mock_ytdlp.side_effect = ytdlp_side_effect

        with patch("os.path.exists", return_value=False):
            track, title = media_finder.find_and_download_music("квины шоу маст гоу он", allow_ai_fallback=True)
            self.assertEqual(track, "/fake/music/queen.mp3")
            self.assertEqual(title, "Queen - The Show Must Go On")
            mock_refine.assert_called_once_with("квины шоу маст гоу он")

if __name__ == "__main__":
    unittest.main()
