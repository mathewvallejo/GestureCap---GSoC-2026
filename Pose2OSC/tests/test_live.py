import types
import unittest

from pose2osc.runtime import (
    _correct_handedness_label,
    _existing_capture_count,
    _FrameReadWatchdog,
    _model_landmarks,
    _prepare_preview_window,
    _release_preview_window,
    _select_hands,
    _show_status,
    _status_y_positions,
)
from pose2osc.manifest import GestureModel, Prediction, StateUpdate
from pose2osc.osc import OscConfig, send_prediction
from tests.test_features import open_hand


class DummyClient:
    def __init__(self):
        self.messages = []

    def send_message(self, path, value):
        self.messages.append((path, value))


def prediction(label="open", accepted=True, confidence=0.82):
    return Prediction(
        label=label if accepted else None,
        accepted=accepted,
        distance=0.1,
        confidence=confidence,
        vote_confidence=1.0 if accepted else 0.0,
        distance_confidence=confidence,
        threshold=0.3,
        votes={label: 1.0} if label else {},
    )


class LiveOscTests(unittest.TestCase):
    def test_enter_sends_gate_and_trigger(self):
        client = DummyClient()
        pred = prediction("open")
        state = StateUpdate(
            active_label="open",
            previous_label=None,
            event="enter",
            prediction=pred,
            active=True,
        )

        send_prediction(client, pred, state, OscConfig())

        self.assertIn(("/pose2osc/gesture/open/active", 1), client.messages)
        self.assertIn(("/pose2osc/gesture/open/trigger", 1), client.messages)

    def test_exit_sends_gate_off_and_global_none(self):
        client = DummyClient()
        pred = prediction(label=None, accepted=False, confidence=0.0)
        state = StateUpdate(
            active_label=None,
            previous_label="open",
            event="exit",
            prediction=pred,
            active=False,
        )

        send_prediction(client, pred, state, OscConfig())

        self.assertIn(("/pose2osc/gesture/open/active", 0), client.messages)
        self.assertIn(("/pose2osc/gesture/open/confidence", 0.0), client.messages)
        self.assertIn(("/pose2osc/state/active", ["none", 0.0]), client.messages)

    def test_select_both_hands_orders_right_then_left_for_model(self):
        left = [(1.0, 0.0, 0.0)] * 21
        right = [(2.0, 0.0, 0.0)] * 21
        result = fake_result([("Left", right), ("Right", left)])

        selected = _select_hands(result, "Both")
        model_landmarks = _model_landmarks(selected)

        self.assertEqual([label for label, _ in selected], ["Right", "Left"])
        self.assertEqual(model_landmarks[:21], right)
        self.assertEqual(model_landmarks[21:], left)

    def test_select_both_allows_one_visible_hand(self):
        right = [(2.0, 0.0, 0.0)] * 21
        result = fake_result([("Left", right)])

        selected = _select_hands(result, "Both")

        self.assertEqual([label for label, _ in selected], ["Right"])
        self.assertEqual(_model_landmarks(selected), right)

    def test_handedness_correction_can_be_disabled(self):
        self.assertEqual(_correct_handedness_label("Left"), "Right")
        self.assertEqual(
            _correct_handedness_label("Left", correct_handedness=False),
            "Left",
        )

    def test_existing_capture_count_resumes_from_manifest_metadata(self):
        model = GestureModel()
        model.add_samples(
            "filter_grab",
            [open_hand(), open_hand(scale=1.01)],
            handedness="Right",
            metadata={"capture_count": 4},
        )
        model.label_metadata["filter_grab"]["capture_count"] = 4

        self.assertEqual(_existing_capture_count(model, "filter_grab"), 4)

    def test_prominent_status_line_gets_extra_spacing(self):
        positions = _status_y_positions(
            ["Performance mode", "Gesture 1", "Confidence: 0.8"],
            prominent_line=1,
        )

        self.assertGreater(positions[2] - positions[1], positions[1] - positions[0])


    def test_frame_read_watchdog_returns_frames(self):
        frame = object()
        watchdog = _FrameReadWatchdog(0, timeout_seconds=1.0)

        self.assertIs(watchdog.read(FakeCapture([(True, frame)])), frame)

    def test_frame_read_watchdog_reports_stalled_camera(self):
        watchdog = _FrameReadWatchdog(2, timeout_seconds=0.0)

        with self.assertRaisesRegex(RuntimeError, "camera 2 opened but did not return frames"):
            watchdog.read(FakeCapture([(False, None)]))

    def test_prepare_preview_window_creates_named_window(self):
        cv2 = FakeCv2()

        _prepare_preview_window(cv2, True)

        self.assertEqual(cv2.named_windows, [("Pose2OSC", cv2.WINDOW_NORMAL)])
        self.assertEqual(cv2.resize_windows, [("Pose2OSC", 960, 720)])
        self.assertEqual(cv2.wait_key_delays, [1])

    def test_release_preview_window_flushes_close_events(self):
        cv2 = FakeCv2()

        _release_preview_window(cv2, True)

        self.assertEqual(cv2.destroyed_windows, 1)
        self.assertEqual(len(cv2.wait_key_delays), 5)

    def test_release_preview_window_skips_when_preview_is_disabled(self):
        cv2 = FakeCv2()

        _release_preview_window(cv2, False)

        self.assertEqual(cv2.destroyed_windows, 0)

    def test_prepare_preview_window_skips_when_preview_is_disabled(self):
        cv2 = FakeCv2()

        _prepare_preview_window(cv2, False)

        self.assertEqual(cv2.named_windows, [])

    def test_status_overlay_draws_text_sized_background_boxes(self):
        cv2 = FakeCv2()
        frame = FakeFrame()

        _show_status(cv2, frame, ["Performance mode", "Gesture 1"], prominent_line=1)

        self.assertEqual(len(cv2.rectangles), 2)
        for _, top_left, bottom_right, _, _ in cv2.rectangles:
            self.assertEqual(top_left[0], 9)
            self.assertLess(bottom_right[0], 260)
        self.assertEqual(len(cv2.put_text_calls), 4)


def fake_result(hands):
    return types.SimpleNamespace(
        multi_hand_landmarks=[
            types.SimpleNamespace(
                landmark=[
                    types.SimpleNamespace(x=x, y=y, z=z)
                    for x, y, z in landmarks
                ]
            )
            for _, landmarks in hands
        ],
        multi_handedness=[
            types.SimpleNamespace(
                classification=[types.SimpleNamespace(label=label)]
            )
            for label, _ in hands
        ],
    )


class FakeFrame:
    shape = (480, 640, 3)


class FakeCv2:
    FONT_HERSHEY_SIMPLEX = 0
    INTER_LINEAR = 1
    LINE_AA = 16
    WINDOW_NORMAL = 0

    def __init__(self):
        self.rectangles = []
        self.put_text_calls = []
        self.named_windows = []
        self.resize_windows = []
        self.wait_key_delays = []
        self.destroyed_windows = 0

    def namedWindow(self, window_name, flag):
        self.named_windows.append((window_name, flag))

    def resizeWindow(self, window_name, width, height):
        self.resize_windows.append((window_name, width, height))

    def waitKey(self, delay):
        self.wait_key_delays.append(delay)
        return -1

    def destroyAllWindows(self):
        self.destroyed_windows += 1

    def flip(self, frame, flip_code):
        return frame

    def resize(self, frame, size, fx, fy, interpolation):
        return frame

    def rectangle(self, *args):
        self.rectangles.append(args)

    def getTextSize(self, text, font_face, scale, thickness):
        return ((round(len(text) * 10 * scale), round(20 * scale)), 5)

    def putText(self, *args):
        self.put_text_calls.append(args)

    def imshow(self, window_name, frame):
        self.window_name = window_name
        self.frame = frame


class FakeCapture:
    def __init__(self, reads):
        self.reads = list(reads)

    def read(self):
        if self.reads:
            return self.reads.pop(0)
        return False, None


if __name__ == "__main__":
    unittest.main()
