import signal
import subprocess
import unittest

from pose2osc.app import MANIFEST_FILETYPES, manifest_dialog_settings, stop_pose2osc_process
from pose2osc.cli import default_manifest_path


class AppHelperTests(unittest.TestCase):
    def test_manifest_dialog_settings_keep_current_filename(self):
        settings = manifest_dialog_settings(
            "/tmp/performer_a.json",
            title="Load Gesture Manifest",
        )

        self.assertEqual(settings["title"], "Load Gesture Manifest")
        self.assertEqual(settings["initialfile"], "performer_a.json")
        self.assertIn(("JSON manifests", "*.json"), settings["filetypes"])

    def test_manifest_dialog_uses_default_filename_when_empty(self):
        settings = manifest_dialog_settings("", title="New Gesture Manifest")

        self.assertEqual(settings["initialfile"], "gestures.json")
        self.assertEqual(settings["defaultextension"], ".json")
        self.assertEqual(settings["filetypes"], MANIFEST_FILETYPES)
        self.assertTrue(default_manifest_path().endswith("models/gestures.json"))


class StopProcessTests(unittest.TestCase):
    def test_stop_process_sends_interrupt_before_terminate(self):
        process = FakeProcess()
        messages: list[str] = []

        return_code = stop_pose2osc_process(process, messages.append)

        self.assertEqual(return_code, 0)
        if hasattr(signal, "SIGINT"):
            self.assertEqual(process.signals, [signal.SIGINT])
        self.assertFalse(process.terminated)
        self.assertIn("Stopping active Pose2OSC session\n", messages)

    def test_stop_process_forces_after_timeout(self):
        process = FakeProcess(timeout_once=True)
        messages: list[str] = []

        return_code = stop_pose2osc_process(process, messages.append)

        self.assertEqual(return_code, 0)
        self.assertTrue(process.terminated)
        self.assertIn("Pose2OSC did not stop cleanly; forcing it to close\n", messages)


class FakeProcess:
    returncode = None

    def __init__(self, *, timeout_once: bool = False) -> None:
        self.timeout_once = timeout_once
        self.signals: list[int] = []
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        if self.timeout_once:
            self.timeout_once = False
            raise subprocess.TimeoutExpired("pose2osc", timeout)
        self.returncode = 0
        return self.returncode


if __name__ == "__main__":
    unittest.main()
