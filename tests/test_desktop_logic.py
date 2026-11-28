"""Tests for the Qt-free logic behind the NEXUS desktop interface.

These cover the orb renderer, the state logic, audio levels, read-only data
access and statistics formatting. They do not need PySide6 or a display, so
they say nothing about how the window looks; that has to be checked by eye.
"""

import os
import sqlite3
import struct
import sys
import tempfile
import unittest
import wave
from unittest import mock

import numpy as np

from desktop import audio_levels, data_access, system_stats
from desktop.orb_engine import (
    QUALITY,
    STATE_PARAMS,
    VALID_STATES,
    OrbEngine,
    box_blur,
    build_lut,
    downsample,
    splat,
    upsample,
)
from desktop.status_logic import describe_state, mic_status, state_from_status


class StateLogicTests(unittest.TestCase):

    def test_idle_when_nothing_happens(self):
        self.assertEqual(state_from_status(None), "idle")
        self.assertEqual(state_from_status(""), "idle")

    def test_recording_means_listening(self):
        self.assertEqual(state_from_status(None, recording=True), "listening")
        self.assertEqual(state_from_status("Thinking", recording=True), "listening")

    def test_speaking_from_flag_or_label(self):
        self.assertEqual(state_from_status(None, speaking=True), "speaking")
        self.assertEqual(state_from_status("Speaking"), "speaking")

    def test_researching_label(self):
        self.assertEqual(state_from_status("Researching"), "researching")
        self.assertEqual(state_from_status("Researching sources"), "researching")

    def test_other_activity_is_thinking(self):
        for label in ("Thinking", "Transcribing", "Preparing speech", "Calculating"):
            self.assertEqual(state_from_status(label), "thinking")

    def test_busy_without_label_is_thinking(self):
        self.assertEqual(state_from_status(None, busy=True), "thinking")

    def test_every_state_has_a_caption_and_engine_parameters(self):
        for state in ("idle", "listening", "thinking", "speaking", "researching", "error"):
            self.assertIn(state, VALID_STATES)
            self.assertTrue(describe_state(state))

    def test_mic_status(self):
        self.assertEqual(mic_status(False, False, False), "OFFLINE")
        self.assertEqual(mic_status(True, True, False), "RECORDING")
        self.assertEqual(mic_status(True, False, True), "BUSY")
        self.assertEqual(mic_status(True, False, False), "READY")


class AudioLevelTests(unittest.TestCase):

    def write_wav(self, samples, rate=22050, width=2, channels=1):
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        handle.close()
        self.addCleanup(os.remove, handle.name)
        with wave.open(handle.name, "wb") as out:
            out.setnchannels(channels)
            out.setsampwidth(width)
            out.setframerate(rate)
            out.writeframes(samples)
        return handle.name

    def test_silence_is_zero_and_loud_is_high(self):
        self.assertEqual(audio_levels.rms_level(np.zeros(512)), 0.0)
        self.assertEqual(audio_levels.rms_level(None), 0.0)
        self.assertGreater(audio_levels.rms_level(np.full(512, 0.2)), 0.95)

    def test_level_is_monotonic(self):
        quiet = audio_levels.rms_level(np.full(512, 0.02))
        louder = audio_levels.rms_level(np.full(512, 0.08))
        self.assertLess(quiet, louder)

    def test_envelope_follows_loudness_in_time(self):
        rate = 22050
        loud = [int(12000 * np.sin(2 * np.pi * 220 * i / rate)) for i in range(rate // 2)]
        soft = [int(400 * np.sin(2 * np.pi * 220 * i / rate)) for i in range(rate // 2)]
        data = struct.pack(f"<{len(loud) + len(soft)}h", *(loud + soft))
        levels, hop = audio_levels.wav_envelope(self.write_wav(data, rate))
        self.assertAlmostEqual(hop, 0.03, delta=0.002)
        early = audio_levels.envelope_at(levels, hop, 0.2)
        late = audio_levels.envelope_at(levels, hop, 0.8)
        self.assertGreater(early, 0.8)
        self.assertLess(late, 0.2)
        self.assertEqual(audio_levels.envelope_at(levels, hop, 99.0), 0.0)
        self.assertEqual(audio_levels.envelope_at(levels, hop, -1.0), 0.0)

    def test_stereo_is_mixed_down(self):
        rate = 22050
        mono = [int(9000 * np.sin(2 * np.pi * 300 * i / rate)) for i in range(rate // 4)]
        stereo = [value for sample in mono for value in (sample, sample)]
        data = struct.pack(f"<{len(stereo)}h", *stereo)
        levels, _hop = audio_levels.wav_envelope(self.write_wav(data, rate, channels=2))
        self.assertIsNotNone(levels)
        self.assertGreater(levels.max(), 0.5)

    def test_unreadable_file_gives_none(self):
        levels, hop = audio_levels.wav_envelope("/no/such/file.wav")
        self.assertIsNone(levels)
        self.assertGreater(hop, 0)
        self.assertEqual(audio_levels.envelope_at(None, hop, 0.1), 0.0)


class OrbEngineTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = OrbEngine("companion")
        for _ in range(10):
            cls.engine.step(1 / 20)
            cls.frame = cls.engine.render().copy()

    def test_frame_shape_and_alpha(self):
        size = self.engine.res
        self.assertEqual(self.frame.shape, (size, size, 4))
        self.assertEqual(self.frame.dtype, np.uint8)
        self.assertTrue((self.frame[..., 3] == 255).all())

    def test_orb_is_lit_in_the_middle_and_dark_at_the_corners(self):
        size = self.engine.res
        middle = self.frame[size // 2 - 8:size // 2 + 8, size // 2 - 8:size // 2 + 8, :3]
        corner = self.frame[:12, :12, :3]
        self.assertGreater(middle.mean(), 60)
        self.assertLess(corner.mean(), 8)

    def test_colour_is_orange_not_blue(self):
        # BGRA order: red must dominate blue everywhere light is present.
        lit = self.frame[..., 2].astype(int) > 40
        self.assertTrue(lit.any())
        self.assertTrue((self.frame[..., 2][lit].astype(int)
                         >= self.frame[..., 0][lit].astype(int)).all())

    def test_same_seed_same_picture(self):
        first = OrbEngine("companion", seed=5)
        second = OrbEngine("companion", seed=5)
        for engine in (first, second):
            for _ in range(3):
                engine.step(0.05)
        self.assertTrue(np.array_equal(first.render(), second.render()))

    def test_every_state_renders_and_differs_from_idle(self):
        brightness = {}
        for state in VALID_STATES:
            engine = OrbEngine("companion")
            engine.set_state(state)
            for _ in range(40):
                engine.step(0.05)
            brightness[state] = float(engine.render()[..., :3].mean())
        self.assertGreater(brightness["thinking"], brightness["idle"])
        self.assertTrue(all(value > 5 for value in brightness.values()))

    def test_audio_level_brightens_the_orb(self):
        quiet = OrbEngine("companion")
        loud = OrbEngine("companion")
        loud.set_state("speaking")
        quiet.set_state("speaking")
        loud.set_level(1.0)
        quiet.set_level(0.0)
        for _ in range(30):
            quiet.step(0.05)
            loud.step(0.05)
        self.assertGreater(loud.render()[..., :3].mean(), quiet.render()[..., :3].mean())

    def test_loud_bursts_launch_shock_waves(self):
        engine = OrbEngine("companion")
        engine.set_state("speaking")
        engine.set_level(0.0)
        engine.step(0.05)
        engine.set_level(0.9)
        engine.step(0.05)
        self.assertEqual(len(engine.waves), 1)

    def test_silence_launches_no_waves(self):
        engine = OrbEngine("companion")
        for _ in range(30):
            engine.step(0.05)
        self.assertEqual(engine.waves, [])

    def test_state_parameters_ease_toward_the_new_state(self):
        engine = OrbEngine("companion")
        engine.set_state("thinking")
        engine.step(0.05)
        energy = engine.params["energy"]
        self.assertGreater(energy, STATE_PARAMS["idle"]["energy"])
        self.assertLess(energy, STATE_PARAMS["thinking"]["energy"])
        for _ in range(100):
            engine.step(0.05)
        self.assertAlmostEqual(engine.params["energy"], STATE_PARAMS["thinking"]["energy"], places=2)

    def test_unknown_state_and_bad_level_are_safe(self):
        engine = OrbEngine("companion")
        engine.set_state("nonsense")
        self.assertEqual(engine.state, "idle")
        engine.set_level("loud")
        self.assertEqual(engine.level_target, 0.0)
        engine.set_level(7)
        self.assertEqual(engine.level_target, 1.0)

    def test_unknown_quality_falls_back(self):
        self.assertEqual(OrbEngine("ultra").quality, "balanced")

    def test_error_state_shifts_colour_ramp_not_hue_family(self):
        normal, alarm = build_lut(0.0), build_lut(1.0)
        self.assertFalse(np.array_equal(normal, alarm))
        # Still warm: red channel (index 2 in BGRA) dominates blue in both.
        for lut in (normal, alarm):
            self.assertTrue((lut[:, 2].astype(int) >= lut[:, 0].astype(int)).all())

    def test_transparent_mode_is_premultiplied(self):
        engine = OrbEngine("companion", transparent=True)
        for _ in range(5):
            engine.step(0.05)
        frame = engine.render()
        self.assertTrue((frame[..., :3].max(axis=2) <= frame[..., 3]).all())
        self.assertEqual(int(frame[0, 0, 3]), 0)

    def test_quality_sizes_divide_for_bloom(self):
        for name, config in QUALITY.items():
            self.assertEqual(config["res"] % 4, 0, name)

    def test_render_reuses_one_buffer(self):
        engine = OrbEngine("companion")
        self.assertIs(engine.render(), engine.frame)


class ImageHelperTests(unittest.TestCase):

    def test_splat_conserves_light(self):
        image = splat(np.array([10.3, 20.7]), np.array([5.5, 8.1]),
                      np.array([1.0, 2.0]), 40, 30)
        self.assertAlmostEqual(float(image.sum()), 3.0, places=4)

    def test_splat_ignores_points_off_screen(self):
        image = splat(np.array([-5.0, 100.0]), np.array([5.0, 5.0]),
                      np.array([1.0, 1.0]), 40, 30)
        self.assertEqual(float(image.sum()), 0.0)

    def test_blur_spreads_but_keeps_total(self):
        image = np.zeros((40, 40), dtype=np.float32)
        image[20, 20] = 100.0
        blurred = box_blur(image, 2)
        self.assertAlmostEqual(float(blurred.sum()), 100.0, places=2)
        self.assertLess(blurred.max(), 100.0)

    def test_down_and_up_sample_sizes(self):
        image = np.ones((8, 8), dtype=np.float32)
        self.assertEqual(downsample(image).shape, (4, 4))
        self.assertEqual(upsample(downsample(image)).shape, (8, 8))


class SystemStatsTests(unittest.TestCase):

    def test_formatting_never_invents_values(self):
        self.assertEqual(system_stats.format_percent(None), "--")
        self.assertEqual(system_stats.format_percent(41.6), "42%")
        self.assertEqual(system_stats.format_battery(None), "--")
        self.assertEqual(system_stats.format_battery({"has_battery": False}), "AC POWER")
        self.assertEqual(
            system_stats.format_battery({"has_battery": True, "percent": 80, "charging": True}),
            "80% CHARGING")
        self.assertEqual(
            system_stats.format_battery({"has_battery": True, "percent": 80, "charging": False}),
            "80%")

    def test_collect_uses_the_reader_and_survives_failures(self):
        class Reader:
            def cpu_percent(self):
                return 25.0

            def memory(self):
                return {"total": 1000, "available": 400}

            def battery(self):
                raise RuntimeError("no battery API")

        data = system_stats.collect(Reader())
        self.assertEqual(data["cpu"], 25.0)
        self.assertAlmostEqual(data["memory"], 60.0)
        self.assertIsNone(data["battery"])


class DataAccessTests(unittest.TestCase):

    def setUp(self):
        folder = tempfile.mkdtemp()
        self.path = os.path.join(folder, "memory.db")
        patcher = mock.patch.object(data_access.Config, "MEMORY_DB", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_database(self):
        connection = sqlite3.connect(self.path)
        connection.executescript(
            "CREATE TABLE memories (id INTEGER PRIMARY KEY, key TEXT, value TEXT,"
            " type TEXT, created_at TEXT);"
            "INSERT INTO memories (key, value, type) VALUES"
            " ('a', '1', 'fact'), ('b', '2', 'fact'), ('c', '3', 'conversation');")
        connection.commit()
        connection.close()

    def test_missing_database_returns_none(self):
        self.assertIsNone(data_access.memory_facts())
        self.assertEqual(data_access.summary_counts()["facts"], None)

    def test_reads_facts_newest_first_and_excludes_conversations(self):
        self.make_database()
        facts = data_access.memory_facts()
        self.assertEqual([f["key"] for f in facts], ["b", "a"])
        self.assertEqual(data_access.summary_counts()["facts"], 2)
        self.assertEqual(data_access.summary_counts()["conversations"], 1)

    def test_missing_table_returns_none_not_an_error(self):
        self.make_database()
        self.assertIsNone(data_access.research_sessions())

    def test_connection_is_read_only(self):
        self.make_database()
        with mock.patch.object(data_access.sqlite3, "connect",
                               wraps=data_access.sqlite3.connect) as connect:
            data_access.memory_facts()
        self.assertTrue(connect.called)
        # A write through the same helper must fail.
        self.assertIsNone(data_access._query("DELETE FROM memories"))
        self.assertEqual(data_access.summary_counts()["facts"], 2)


@unittest.skipUnless(sys.platform == "win32", "Piper playback needs Windows")
class SpeakerHookTests(unittest.TestCase):

    def test_hook_errors_never_break_playback(self):
        from voice.speaker import Speaker

        speaker = Speaker.__new__(Speaker)
        speaker.playback_hook = mock.Mock(side_effect=RuntimeError("ui gone"))
        speaker._notify_playback("start", "x.wav")
        speaker.playback_hook.assert_called_once_with("start", "x.wav")

    def test_no_hook_is_fine(self):
        from voice.speaker import Speaker

        speaker = Speaker.__new__(Speaker)
        speaker.playback_hook = None
        speaker._notify_playback("end", "x.wav")


if __name__ == "__main__":
    unittest.main()
