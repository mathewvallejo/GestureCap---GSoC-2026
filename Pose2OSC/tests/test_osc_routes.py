import unittest

from pose2osc.osc import build_osc_route_text


class OscRouteGuideTests(unittest.TestCase):
    def test_route_text_includes_enrolled_gesture_routes(self):
        text = build_osc_route_text(
            ["gesture_1", "filter_grab"],
            send_landmark_vectors=True,
            split_axes=False,
            send_unknown_predictions=False,
        )

        self.assertIn("/pose2osc/gesture/gesture_1/active", text)
        self.assertIn("/pose2osc/gesture/filter_grab/trigger", text)
        self.assertIn("/pose2osc/state/event [event, label, confidence]", text)

    def test_route_text_includes_landmark_vector_and_split_axis_routes(self):
        text = build_osc_route_text(
            ["gesture_1"],
            send_landmark_vectors=True,
            split_axes=True,
            send_unknown_predictions=True,
        )

        self.assertIn("/pose2osc/hand/right/wrist [x, y, z]", text)
        self.assertIn("/pose2osc/hand/right/wrist/x x", text)
        self.assertIn("/pose2osc/state/active [unknown, 0.0]", text)


if __name__ == "__main__":
    unittest.main()
