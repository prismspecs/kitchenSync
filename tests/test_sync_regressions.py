#!/usr/bin/env python3
"""Regression tests for sync stability behavior."""

import importlib
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


sys.modules.setdefault("vlc", MagicMock())
sys.modules.setdefault("gi", MagicMock())
sys.modules.setdefault("gi.repository", MagicMock())


import collaborator
import leader
from video.drivers import gst_driver
from ui import window_manager


class TestLeaderConfigTargeting(unittest.TestCase):
    """Broadcast config updates addressed to a collaborator must never be
    applied by the leader (this once demoted the leader to a collaborator)."""

    def _make_dummy(self):
        dummy = SimpleNamespace(
            config=SimpleNamespace(
                device_id="pi5_1",
                clean_and_save_config=MagicMock(),
            ),
            command_manager=SimpleNamespace(send_command=MagicMock()),
        )
        dummy._message_targets_this_device = (
            lambda msg: leader.LeaderPi._message_targets_this_device(dummy, msg)
        )
        return dummy

    def test_update_for_other_device_is_ignored(self):
        dummy = self._make_dummy()
        msg = {
            "type": "config_update",
            "target_device_id": "pi4_1",
            "updates": {"role": "collaborator", "device_id": "pi4_1"},
        }
        leader.LeaderPi._handle_config_update(dummy, msg, ("192.168.1.165", 5006))
        dummy.config.clean_and_save_config.assert_not_called()

    def test_update_for_this_device_is_applied(self):
        dummy = self._make_dummy()
        msg = {
            "type": "config_update",
            "target_device_id": "pi5_1",
            "updates": {"tick_interval": "0.05"},
        }
        leader.LeaderPi._handle_config_update(dummy, msg, ("192.168.1.165", 5006))
        dummy.config.clean_and_save_config.assert_called_once()

    def test_config_request_for_other_device_is_ignored(self):
        dummy = self._make_dummy()
        msg = {"type": "config_request", "target_device_id": "pi4_1"}
        leader.LeaderPi._handle_config_request(dummy, msg, ("192.168.1.165", 5006))
        dummy.command_manager.send_command.assert_not_called()


class TestGstDriverSetSpeed(unittest.TestCase):
    def test_instant_rate_change_uses_none_seek_types(self):
        fake_event = object()
        fake_gst = SimpleNamespace(
            SECOND=1_000_000_000,
            Format=SimpleNamespace(TIME="time"),
            SeekFlags=SimpleNamespace(INSTANT_RATE_CHANGE=4),
            SeekType=SimpleNamespace(NONE="none"),
            Event=SimpleNamespace(new_seek=MagicMock(return_value=fake_event)),
            init=MagicMock(),
            StateChangeReturn=SimpleNamespace(FAILURE=0, SUCCESS=1),
            State=SimpleNamespace(PAUSED=3, PLAYING=4),
        )

        original_gst = gst_driver.Gst
        original_available = gst_driver.GST_AVAILABLE
        gst_driver.Gst = fake_gst
        gst_driver.GST_AVAILABLE = True

        try:
            driver = gst_driver.GstDriver.__new__(gst_driver.GstDriver)
            driver.pipeline = MagicMock()
            driver.pipeline.send_event.return_value = True
            driver.pipeline.get_state.return_value = (None, 3, None) # State.PLAYING is 4, PAUSED is 3. Mocking success and PAUSED.
            driver.current_rate = 1.0

            success = driver.set_speed(1.02)

            self.assertTrue(success)
            fake_gst.Event.new_seek.assert_called_once_with(
                1.02,
                fake_gst.Format.TIME,
                fake_gst.SeekFlags.INSTANT_RATE_CHANGE,
                fake_gst.SeekType.NONE,
                0,
                fake_gst.SeekType.NONE,
                -1,
            )
            driver.pipeline.send_event.assert_called_once_with(fake_event)
            self.assertEqual(driver.current_rate, 1.02)
        finally:
            gst_driver.Gst = original_gst
            gst_driver.GST_AVAILABLE = original_available

    def test_preferred_sink_names_prioritize_x11_acceleration(self):
        driver = gst_driver.GstDriver.__new__(gst_driver.GstDriver)

        with patch.dict(os.environ, {"DISPLAY": ":0", "WAYLAND_DISPLAY": ""}, clear=False):
            sink_names = driver._preferred_sink_names()

        self.assertEqual(sink_names[:2], ["glimagesink", "xvimagesink"])

    def test_preferred_sink_names_prioritize_kms_without_display(self):
        driver = gst_driver.GstDriver.__new__(gst_driver.GstDriver)

        with patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}, clear=False):
            sink_names = driver._preferred_sink_names()

        self.assertEqual(sink_names[:2], ["kmssink", "glimagesink"])


class TestCollaboratorStartHandling(unittest.TestCase):
    def test_configured_collaborator_video_is_preferred_over_leader_video(self):
        dummy = SimpleNamespace(
            config=SimpleNamespace(video_file="collaborator_video.mp4"),
            system_state=SimpleNamespace(is_running=False),
            video_path=None,
            active_session_key=None,
            video_manager=SimpleNamespace(
                find_video_file=MagicMock(return_value="media/collaborator_video.mp4")
            ),
            video_player=SimpleNamespace(
                load=MagicMock(return_value=True),
                get_duration=MagicMock(return_value=10.0),
            ),
            stop_playback=MagicMock(),
            start_playback=MagicMock(),
            _update_sync_params=MagicMock(),
            midi_scheduler=None,
        )

        collaborator.CollaboratorPi._handle_start_command(
            dummy,
            {
                "type": "start",
                "video_file": "leader_video.mp4",
                "leader_id": "leader-1",
                "start_time": 100.0,
            },
        )

        dummy.video_manager.find_video_file.assert_called_once_with(
            target_file="collaborator_video.mp4", use_cache=False
        )
        dummy.video_player.load.assert_called_once_with("media/collaborator_video.mp4")
        dummy.start_playback.assert_called_once()
        self.assertEqual(dummy.video_path, "media/collaborator_video.mp4")
        self.assertEqual(dummy.active_session_key, ("leader-1", "collaborator_video.mp4", 100.0))

    def test_duplicate_running_start_same_session_is_ignored(self):
        dummy = SimpleNamespace(
            config=SimpleNamespace(video_file="test_video.mp4"),
            system_state=SimpleNamespace(is_running=True),
            video_path="media/test_video.mp4",
            active_session_key=("leader-1", "test_video.mp4", 100.0),
            video_manager=SimpleNamespace(find_video_file=MagicMock(return_value="media/test_video.mp4")),
            video_player=SimpleNamespace(load=MagicMock(), get_duration=MagicMock(return_value=10.0)),
            stop_playback=MagicMock(),
            start_playback=MagicMock(),
            _update_sync_params=MagicMock(),
        )

        collaborator.CollaboratorPi._handle_start_command(
            dummy,
            {
                "type": "start",
                "video_file": "test_video.mp4",
                "leader_id": "leader-1",
                "start_time": 100.0,
                "sync_params": {"max_drift": 0.5},
            },
        )

        dummy.stop_playback.assert_not_called()
        dummy.start_playback.assert_not_called()
        dummy.video_player.load.assert_not_called()

    def test_duplicate_running_start_without_identity_is_ignored(self):
        dummy = SimpleNamespace(
            config=SimpleNamespace(video_file="test_video.mp4"),
            system_state=SimpleNamespace(is_running=True),
            video_path="media/test_video.mp4",
            active_session_key=None,
            video_manager=SimpleNamespace(find_video_file=MagicMock(return_value="media/test_video.mp4")),
            video_player=SimpleNamespace(load=MagicMock(), get_duration=MagicMock(return_value=10.0)),
            stop_playback=MagicMock(),
            start_playback=MagicMock(),
            _update_sync_params=MagicMock(),
        )

        collaborator.CollaboratorPi._handle_start_command(
            dummy,
            {"type": "start", "video_file": "test_video.mp4"},
        )

        dummy.stop_playback.assert_not_called()
        dummy.start_playback.assert_not_called()
        dummy.video_player.load.assert_not_called()

    def test_duplicate_running_start_new_session_restarts_playback(self):
        dummy = SimpleNamespace(
            config=SimpleNamespace(video_file="test_video.mp4"),
            system_state=SimpleNamespace(is_running=True),
            video_path="media/test_video.mp4",
            active_session_key=("leader-1", "test_video.mp4", 100.0),
            video_manager=SimpleNamespace(find_video_file=MagicMock(return_value="media/test_video.mp4")),
            video_player=SimpleNamespace(load=MagicMock(return_value=True), get_duration=MagicMock(return_value=10.0)),
            stop_playback=MagicMock(),
            start_playback=MagicMock(),
            _update_sync_params=MagicMock(),
            midi_scheduler=None,
        )

        collaborator.CollaboratorPi._handle_start_command(
            dummy,
            {
                "type": "start",
                "video_file": "test_video.mp4",
                "leader_id": "leader-1",
                "start_time": 200.0,
            },
        )

        dummy.stop_playback.assert_called_once()
        dummy.video_player.load.assert_called_once_with("media/test_video.mp4")
        dummy.start_playback.assert_called_once()
        self.assertEqual(dummy.active_session_key, ("leader-1", "test_video.mp4", 200.0))


class TestCollaboratorLoopHandling(unittest.TestCase):
    def test_loop_boundary_uses_wrapped_deviation(self):
        video_player = SimpleNamespace(
            is_playing=True,
            is_seeking=False,
            get_position=MagicMock(return_value=9.95),
            get_duration=MagicMock(return_value=10.0),
            seek=MagicMock(),
            set_speed=MagicMock(),
        )
        dummy = SimpleNamespace(
            video_player=video_player,
            config=SimpleNamespace(),  # no sync_mode attr -> defaults to udp
            debug_deviation_mode=False,
            deviation_samples=[-0.10, -0.10],
            max_samples=3,
            startup_sync_count=3,
            FAST_SYNC_THRESHOLD=3,
            _settle_until=0,
            max_drift=0.5,
            min_drift=0.01,
            kp=0.1,
            min_rate=0.9,
            max_rate=1.2,
            _log_deviation=MagicMock(),
        )
        dummy._normalize_loop_time = lambda media_time: collaborator.CollaboratorPi._normalize_loop_time(dummy, media_time)
        dummy._normalize_loop_deviation = lambda video_pos, leader_time: collaborator.CollaboratorPi._normalize_loop_deviation(dummy, video_pos, leader_time)

        collaborator.CollaboratorPi._maintain_video_sync(dummy, 0.05)

        video_player.seek.assert_not_called()
        video_player.set_speed.assert_called_once()
        self.assertAlmostEqual(video_player.set_speed.call_args.args[0], 1.01)


class TestGstDriverLooping(unittest.TestCase):
    def test_eos_resets_cached_position_before_seek(self):
        original_gst = gst_driver.Gst
        original_available = gst_driver.GST_AVAILABLE
        gst_driver.Gst = SimpleNamespace(MessageType=SimpleNamespace(EOS="eos", SEGMENT_DONE="segment_done"))
        gst_driver.GST_AVAILABLE = True

        try:
            driver = gst_driver.GstDriver.__new__(gst_driver.GstDriver)
            driver._cached_position = 12.34
            driver._last_poll_time = 50.0
            driver.seek = MagicMock()

            message = SimpleNamespace(type="eos")
            gst_driver.GstDriver._on_bus_message(driver, None, message)

            self.assertEqual(driver._cached_position, 0.0)
            driver.seek.assert_called_once_with(0)
        finally:
            gst_driver.Gst = original_gst
            gst_driver.GST_AVAILABLE = original_available


class TestCursorHiding(unittest.TestCase):
    def test_hide_mouse_cursor_starts_unclutter_on_x11(self):
        original_started = window_manager._cursor_hider_started
        try:
            window_manager._cursor_hider_started = False

            with patch.dict(
                os.environ,
                {"DISPLAY": ":0", "XDG_SESSION_TYPE": "x11", "WAYLAND_DISPLAY": ""},
                clear=False,
            ):
                with patch("ui.window_manager.shutil.which", return_value="/usr/bin/unclutter"):
                    with patch("ui.window_manager.subprocess.Popen") as popen:
                        success = window_manager.hide_mouse_cursor()

            self.assertTrue(success)
            popen.assert_called_once_with(
                ["/usr/bin/unclutter", "-idle", "0", "-root"],
                stdout=window_manager.subprocess.DEVNULL,
                stderr=window_manager.subprocess.DEVNULL,
                start_new_session=True,
            )
        finally:
            window_manager._cursor_hider_started = original_started


if __name__ == "__main__":
    unittest.main()