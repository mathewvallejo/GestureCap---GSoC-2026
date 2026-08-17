import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pose2osc.cli import DEFAULT_GENERATED_GESTURES, _handle_stop_signal, _resolve_enroll_labels, build_parser, main, parse_label_text


class CliConfigTests(unittest.TestCase):
    def test_default_generated_labels_resolve_to_twelve_gestures(self):
        args = build_parser().parse_args(["enroll"])

        labels = _resolve_enroll_labels(args)

        self.assertEqual(len(labels), DEFAULT_GENERATED_GESTURES)
        self.assertEqual(labels[0], "gesture_1")
        self.assertEqual(labels[-1], "gesture_12")

    def test_custom_labels_are_split_for_cli_and_app(self):
        self.assertEqual(
            parse_label_text("delay_hold, filter_grab\nfreeze"),
            ["delay_hold", "filter_grab", "freeze"],
        )

    def test_multi_label_enroll_requires_preview_and_spacebar_capture(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(["enroll", "--label", "one", "--label", "two", "--no-preview"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Multiple gesture labels require preview", buffer.getvalue())

    def test_performance_rejects_missing_manifest_before_camera_runtime(self):
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(buffer):
            exit_code = main(["perform", "--manifest", str(Path(tmp) / "missing.json")])

        self.assertEqual(exit_code, 1)
        self.assertIn("saved gesture manifest", buffer.getvalue())

    def test_routes_command_prints_manifest_routes_without_camera_runtime(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = main(["routes", "--manifest", "/tmp/pose2osc_missing.json", "--split-axes"])

        self.assertEqual(exit_code, 0)
        self.assertIn("POSE2OSC OSC ROUTING", buffer.getvalue())

    def test_stop_signal_handler_raises_keyboard_interrupt(self):
        with self.assertRaises(KeyboardInterrupt):
            _handle_stop_signal(15, None)

    def test_camera_test_command_calls_runtime(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), mock.patch("pose2osc.cli.camera_test") as camera_test:
            exit_code = main(["camera-test", "--camera", "2", "--hand", "Left"])

        self.assertEqual(exit_code, 0)
        camera_test.assert_called_once()
        kwargs = camera_test.call_args.kwargs
        self.assertEqual(kwargs["camera"], 2)
        self.assertEqual(kwargs["handedness"], "Left")


if __name__ == "__main__":
    unittest.main()
