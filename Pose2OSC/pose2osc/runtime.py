"""Camera, MediaPipe, preview, enrollment, and performance runtime."""

from __future__ import annotations

import time
from typing import Any, Iterable, Sequence

from .manifest import GestureModel, GestureStateTracker, LabelStyle, Prediction, StateConfig, bgr_from_hex, label_style
from .osc import OscConfig, send_landmarks, send_no_hand, send_prediction

WINDOW_NAME = "Pose2OSC"
PREVIEW_SCALE = 1.5
PREVIEW_INITIAL_WIDTH = 960
PREVIEW_INITIAL_HEIGHT = 720
DEFAULT_TEXT_COLOR = (0, 255, 0)
TEXT_OUTLINE_COLOR = (0, 0, 0)
TEXT_OUTLINE_EXTRA_THICKNESS = 3
STATUS_BOX_PADDING_X = 9
STATUS_BOX_PADDING_Y = 7
PROMINENT_LINE_SCALE = 1.18
TITLE_LINE_SCALE = 0.82
BODY_LINE_SCALE = 0.66
STATUS_MARGIN = 18
CAMERA_READ_TIMEOUT_SECONDS = 8.0
CAMERA_READ_RETRY_SLEEP_SECONDS = 0.03
PREVIEW_CLOSE_WAITKEY_CYCLES = 5
PREVIEW_CLOSE_SLEEP_SECONDS = 0.02
CAMERA_RELEASE_SLEEP_SECONDS = 0.1




def camera_test(
    *,
    camera: int = 0,
    handedness: str | None = None,
    correct_handedness: bool = True,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Open the camera preview without enrollment or OSC output."""

    cv2, mp = _load_camera_dependencies()
    _prepare_preview_window(cv2, True)
    with _open_capture(cv2, camera, width, height) as capture:
        frame_watchdog = _FrameReadWatchdog(camera)
        hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=_max_hands_for_mode(handedness),
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        try:
            while True:
                frame = frame_watchdog.read(capture)
                if frame is None:
                    continue
                result = _process_frame(cv2, hands, frame)
                selected = _select_hands(
                    result,
                    handedness,
                    correct_handedness=correct_handedness,
                )
                detected = _hand_mode_label(selected) if selected else _missing_hand_message(handedness)
                _show_status(
                    cv2,
                    frame,
                    [
                        "Camera test",
                        f"Detected: {detected}" if selected else detected,
                        "Press q to quit",
                    ],
                    mp=mp,
                    result=result,
                    prominent_line=0,
                )
                if _should_stop(cv2, True):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            hands.close()
            _release_preview_window(cv2, True)

def enroll_from_camera(
    *,
    label: str | Sequence[str],
    model_path: str,
    seconds: float = 2.0,
    capture_frames: int = 45,
    target_captures: int = 5,
    camera: int = 0,
    max_samples: int = 64,
    handedness: str | None = None,
    correct_handedness: bool = True,
    show: bool = False,
    timed: bool = False,
    replace: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> int:
    """Record a short held gesture and append it to a JSON model file."""

    labels = _coerce_labels(label)
    interactive = show and not timed
    if len(labels) > 1 and not interactive:
        raise ValueError("enrolling multiple gesture labels in one session requires --show")

    cv2, mp = _load_camera_dependencies()
    _prepare_preview_window(cv2, show)
    model = _load_or_new_model(model_path)
    # Resolve display labels/colors before the loop so UI text and manifest metadata match.
    label_styles = _label_styles(model, labels)
    frames: list[list[tuple[float, float, float]]] = []
    recent_frames: list[tuple[str, list[tuple[float, float, float]]]] = []
    detected_handedness: str | None = None
    active_label_index = 0
    capture_counts = {
        gesture_label: 0 if replace else _existing_capture_count(model, gesture_label)
        for gesture_label in labels
    }
    saved_sample_count = 0
    replaced_labels: set[str] = set()

    with _open_capture(cv2, camera, width, height) as capture:
        frame_watchdog = _FrameReadWatchdog(camera)
        hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=_max_hands_for_mode(handedness),
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        try:
            if interactive:
                while True:
                    frame = frame_watchdog.read(capture)
                    if frame is None:
                        continue

                    active_label = labels[active_label_index]
                    active_style = label_styles[active_label]
                    active_color = bgr_from_hex(active_style.color)
                    result = _process_frame(cv2, hands, frame)
                    selected = _select_hands(result, handedness, correct_handedness=correct_handedness)
                    if selected:
                        detected_handedness = _hand_mode_label(selected)
                        landmarks = _model_landmarks(selected)
                        # Spacebar capture saves a short rolling pose window, not just one frame.
                        recent_frames.append((detected_handedness, landmarks))
                        if len(recent_frames) > max(1, capture_frames):
                            recent_frames.pop(0)

                    capture_count = capture_counts[active_label]
                    current_mode = recent_frames[-1][0] if recent_frames else None
                    matching_recent_frames = [
                        landmarks
                        for mode, landmarks in recent_frames
                        if mode == current_mode
                    ]
                    status = [
                        "Gesture capture mode",
                        active_style.display_label,
                        f"Slot: {active_label_index + 1}/{len(labels)}",
                        "Press Space to capture",
                        "Press q to quit",
                        f"Captured: {capture_count}/{target_captures}",
                    ]
                    if len(labels) > 1:
                        status.insert(3, "Press n for next | p for previous")
                    if current_mode:
                        status.append(
                            f"Detected: {current_mode} | Buffer: {len(matching_recent_frames)}/{capture_frames}"
                        )
                    if capture_count >= target_captures:
                        if len(labels) > 1 and active_label_index < len(labels) - 1:
                            status.append("Target reached: press n for next gesture")
                        else:
                            status.append("Target reached: press q to finish or Space for more")
                    if not selected:
                        status.append(_missing_hand_message(handedness))
                    _show_status(
                        cv2,
                        frame,
                        status,
                        mp=mp,
                        result=result,
                        line_colors=_line_colors(len(status), 1, active_color),
                        prominent_line=1,
                    )
                    if _window_was_closed(cv2):
                        break
                    key = _read_key(cv2)

                    if key in {27, ord("q")}:
                        break
                    if key in {10, 13, ord("n")}:
                        if active_label_index < len(labels) - 1:
                            active_label_index += 1
                            recent_frames.clear()
                            detected_handedness = None
                        continue
                    if key == ord("p"):
                        if active_label_index > 0:
                            active_label_index -= 1
                            recent_frames.clear()
                            detected_handedness = None
                        continue
                    if key == ord(" "):
                        if not matching_recent_frames or not current_mode:
                            continue
                        if replace and active_label not in replaced_labels:
                            model.remove_label(active_label)
                            replaced_labels.add(active_label)
                        capture_counts[active_label] += 1
                        capture_count = capture_counts[active_label]
                        added = model.add_samples(
                            active_label,
                            matching_recent_frames,
                            handedness=current_mode,
                            # These fields are copied into label_metadata for later runtime display.
                            metadata={
                                "capture_mode": "spacebar",
                                "capture_count": capture_count,
                                "capture_frames": len(matching_recent_frames),
                                "capture_seconds": None,
                                "hand_mode": current_mode,
                                "display_label": active_style.display_label,
                                "color": active_style.color,
                            },
                            max_samples=max_samples,
                        )
                        saved_sample_count += added
                        model.save(model_path)
                        feedback = [
                            "Captured and saved",
                            active_style.display_label,
                            f"Hand mode: {current_mode}",
                            f"Samples added: {added}",
                            f"Captured: {capture_count}/{target_captures}",
                            "Press Space to capture again",
                            "Press q to quit",
                        ]
                        if len(labels) > 1:
                            feedback.insert(-1, "Press n for next gesture")
                        _show_status(
                            cv2,
                            frame,
                            feedback,
                            mp=mp,
                            result=result,
                            line_colors=_line_colors(len(feedback), 1, active_color),
                            prominent_line=1,
                        )
                        _read_key(cv2, delay_ms=250)
                return saved_sample_count
            else:
                active_style = label_styles[labels[0]]
                start = time.monotonic()
                while time.monotonic() - start < seconds:
                    frame = frame_watchdog.read(capture)
                    if frame is None:
                        continue
                    result = _process_frame(cv2, hands, frame)
                    selected = _select_hands(result, handedness, correct_handedness=correct_handedness)
                    if selected:
                        detected_handedness = _hand_mode_label(selected)
                        landmarks = _model_landmarks(selected)
                        frames.append(landmarks)

                    if show:
                        remaining = max(0.0, seconds - (time.monotonic() - start))
                        _show_status(
                            cv2,
                            frame,
                            [
                                "Timed capture mode",
                                active_style.display_label,
                                f"Remaining: {remaining:0.1f}s",
                                "Press q to quit",
                            ],
                            mp=mp,
                            result=result,
                            line_colors=_line_colors(4, 1, bgr_from_hex(active_style.color)),
                            prominent_line=1,
                        )
                        if _should_stop(cv2, show):
                            break
        except KeyboardInterrupt:
            return saved_sample_count
        finally:
            hands.close()
            _release_preview_window(cv2, show)

    if not frames:
        raise RuntimeError("no hand landmarks were captured during enrollment")

    if replace:
        model.remove_label(labels[0])

    sample_count = model.add_samples(
        labels[0],
        frames,
        handedness=detected_handedness or handedness,
        metadata={
            "capture_mode": "timed",
            "capture_count": 1,
            "capture_frames": len(frames),
            "capture_seconds": seconds,
            "hand_mode": detected_handedness or handedness,
            "display_label": label_styles[labels[0]].display_label,
            "color": label_styles[labels[0]].color,
        },
        max_samples=max_samples,
    )
    model.save(model_path)
    return sample_count


def run_osc_camera(
    *,
    model_path: str,
    osc: OscConfig | None = None,
    camera: int = 0,
    handedness: str | None = None,
    correct_handedness: bool = True,
    show: bool = False,
    width: int | None = None,
    height: int | None = None,
    state_config: StateConfig | None = None,
) -> None:
    """Run the one-frame recognizer and stream OSC to Max/MSP."""

    cv2, mp = _load_camera_dependencies()
    _prepare_preview_window(cv2, show)
    udp_client = _load_osc_client()
    model = GestureModel.load(model_path)
    tracker = GestureStateTracker(state_config or StateConfig())
    osc_cfg = osc or OscConfig()
    client = udp_client.SimpleUDPClient(osc_cfg.host, osc_cfg.port)
    frame_index = 0

    with _open_capture(cv2, camera, width, height) as capture:
        frame_watchdog = _FrameReadWatchdog(camera)
        hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=_max_hands_for_mode(handedness),
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        try:
            while True:
                frame = frame_watchdog.read(capture)
                if frame is None:
                    continue
                frame_index += 1
                result = _process_frame(cv2, hands, frame)
                selected = _select_hands(result, handedness, correct_handedness=correct_handedness)
                now_ms = int(time.time() * 1000)

                if not selected:
                    prediction = _unknown_prediction(model)
                    state = tracker.update(prediction)
                    send_prediction(client, prediction, state, osc_cfg)
                    send_no_hand(client, now_ms, frame_index)
                    if show:
                        _show_status(
                            cv2,
                            frame,
                            [
                                "Performance mode",
                                "none",
                                _missing_hand_message(handedness),
                                "Press q to quit",
                            ],
                            mp=mp,
                            result=result,
                            prominent_line=1,
                        )
                    if _should_stop(cv2, show):
                        break
                    continue

                detected_handedness = _hand_mode_label(selected)
                prediction = _predict_selection(model, selected)
                state = tracker.update(prediction)

                # OSC sends raw landmarks continuously; gesture state is a separate gate/trigger layer.
                client.send_message("/pose2osc/hand/visible", 1)
                client.send_message("/pose2osc/hand/num_hands", len(selected))
                for hand_label, landmarks in selected:
                    send_landmarks(client, hand_label.lower(), landmarks, osc_cfg)
                send_prediction(client, prediction, state, osc_cfg)
                client.send_message("/pose2osc/frame", [frame_index, now_ms])

                if show:
                    label = state.active_label or "none"
                    display_label = _display_label(model, label)
                    label_color = _label_color_bgr(model, label)
                    _show_status(
                        cv2,
                        frame,
                        [
                            "Performance mode",
                            display_label,
                            f"Detected: {detected_handedness}",
                            f"Confidence: {prediction.confidence:0.2f}",
                            "Press q to quit",
                        ],
                        mp=mp,
                        result=result,
                        line_colors=_line_colors(5, 1, label_color),
                        prominent_line=1,
                    )
                if _should_stop(cv2, show):
                    break
        except KeyboardInterrupt:
            pass
        finally:
            hands.close()
            _release_preview_window(cv2, show)


def _load_or_new_model(path: str) -> GestureModel:
    from pathlib import Path

    model_path = Path(path)
    if model_path.exists():
        return GestureModel.load(model_path)
    return GestureModel()


def _coerce_labels(label: str | Sequence[str]) -> list[str]:
    raw_labels = [label] if isinstance(label, str) else list(label)
    labels: list[str] = []
    seen: set[str] = set()
    for raw_label in raw_labels:
        clean_label = str(raw_label).strip()
        if not clean_label:
            raise ValueError("gesture labels cannot be empty")
        if clean_label in seen:
            raise ValueError(f"duplicate gesture label: {clean_label}")
        labels.append(clean_label)
        seen.add(clean_label)
    if not labels:
        raise ValueError("at least one gesture label is required")
    return labels


def _existing_capture_count(model: GestureModel, label: str) -> int:
    metadata_count = model.label_metadata.get(label, {}).get("capture_count")
    if isinstance(metadata_count, int):
        return metadata_count

    capture_ids = {
        sample.metadata.get("capture_count")
        for sample in model.samples
        if sample.label == label and sample.metadata.get("capture_count") is not None
    }
    return len(capture_ids)


def _label_styles(model: GestureModel, labels: Sequence[str]) -> dict[str, LabelStyle]:
    return {
        label: label_style(label, model.label_metadata.get(label), index)
        for index, label in enumerate(labels)
    }


def _display_label(model: GestureModel, label: str) -> str:
    if label == "none":
        return label
    return label_style(label, model.label_metadata.get(label)).display_label


def _label_color_bgr(model: GestureModel, label: str) -> tuple[int, int, int]:
    if label == "none":
        return (0, 255, 0)
    return bgr_from_hex(label_style(label, model.label_metadata.get(label)).color)


def _line_colors(
    count: int,
    index: int,
    color: tuple[int, int, int],
) -> list[tuple[int, int, int] | None]:
    colors: list[tuple[int, int, int] | None] = [None] * count
    if 0 <= index < count:
        colors[index] = color
    return colors


def _load_camera_dependencies() -> tuple[Any, Any]:
    try:
        import cv2  # type: ignore
        import mediapipe as mp  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Live camera commands require optional dependencies. "
            "Install them with: python -m pip install -e '.[live]'"
        ) from exc
    return cv2, mp


def _load_osc_client() -> Any:
    try:
        from pythonosc import udp_client  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "OSC output requires python-osc. Install with: python -m pip install -e '.[live]'"
        ) from exc
    return udp_client


class _FrameReadWatchdog:
    def __init__(
        self,
        camera: int,
        *,
        timeout_seconds: float = CAMERA_READ_TIMEOUT_SECONDS,
    ) -> None:
        self.camera = camera
        self.timeout_seconds = timeout_seconds
        self.last_success = time.monotonic()

    def read(self, capture: Any) -> Any | None:
        ok, frame = capture.read()
        if ok and frame is not None:
            self.last_success = time.monotonic()
            return frame

        elapsed = time.monotonic() - self.last_success
        if elapsed >= self.timeout_seconds:
            raise RuntimeError(
                f"camera {self.camera} opened but did not return frames for "
                f"{self.timeout_seconds:0.0f}s. Close other camera apps, check "
                "camera permissions, or try a different camera index."
            )
        time.sleep(CAMERA_READ_RETRY_SLEEP_SECONDS)
        return None


class _CaptureContext:
    def __init__(self, capture: Any) -> None:
        self.capture = capture

    def __enter__(self) -> Any:
        return self.capture

    def __exit__(self, *_: object) -> None:
        self.capture.release()
        time.sleep(CAMERA_RELEASE_SLEEP_SECONDS)


def _open_capture(
    cv2: Any,
    camera: int,
    width: int | None,
    height: int | None,
) -> _CaptureContext:
    capture = cv2.VideoCapture(camera)
    if width:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    if height:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not capture.isOpened():
        raise RuntimeError(f"could not open camera {camera}")
    return _CaptureContext(capture)


def _process_frame(cv2: Any, hands: Any, frame: Any) -> Any:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb.flags.writeable = False
    return hands.process(rgb)


def _max_hands_for_mode(handedness: str | None) -> int:
    return 1 if _specific_single_hand(handedness) else 2


def _specific_single_hand(handedness: str | None) -> bool:
    return bool(handedness and handedness.lower() in {"right", "left"})


def _missing_hand_message(handedness: str | None) -> str:
    if _specific_single_hand(handedness):
        return f"Waiting for {handedness} hand"
    return "No hand detected"


def _select_hands(
    result: Any,
    desired_handedness: str | None,
    *,
    correct_handedness: bool = True,
) -> list[tuple[str, list[tuple[float, float, float]]]]:
    if not result.multi_hand_landmarks:
        return []

    handedness_labels = _handedness_labels(
        result.multi_handedness,
        correct_handedness=correct_handedness,
    )
    selected: list[tuple[str, list[tuple[float, float, float]]]] = []
    for index, hand_landmarks in enumerate(result.multi_hand_landmarks):
        label = handedness_labels[index] if index < len(handedness_labels) else "unknown"
        if desired_handedness and desired_handedness.lower() != "any":
            if _specific_single_hand(desired_handedness) and label.lower() != desired_handedness.lower():
                continue
        selected.append((
            _canonical_hand_label(label),
            [
                (float(landmark.x), float(landmark.y), float(landmark.z))
                for landmark in hand_landmarks.landmark
            ],
        ))

    by_label = {label.lower(): landmarks for label, landmarks in selected}
    if "right" in by_label and "left" in by_label:
        return [("Right", by_label["right"]), ("Left", by_label["left"])]

    return selected[:1]


def _canonical_hand_label(label: str) -> str:
    lower = label.lower()
    if lower == "right":
        return "Right"
    if lower == "left":
        return "Left"
    return label


def _hand_mode_label(selected: Sequence[tuple[str, Sequence[tuple[float, float, float]]]]) -> str:
    if len(selected) == 2:
        labels = {label.lower() for label, _ in selected}
        if labels == {"right", "left"}:
            return "Both"
    return selected[0][0] if selected else "Any"


def _model_landmarks(
    selected: Sequence[tuple[str, list[tuple[float, float, float]]]],
) -> list[tuple[float, float, float]]:
    if len(selected) == 2:
        by_label = {label.lower(): landmarks for label, landmarks in selected}
        if "right" in by_label and "left" in by_label:
            return list(by_label["right"]) + list(by_label["left"])
    return list(selected[0][1]) if selected else []


def _predict_selection(
    model: GestureModel,
    selected: Sequence[tuple[str, list[tuple[float, float, float]]]],
) -> Prediction:
    candidates: list[tuple[str, list[tuple[float, float, float]]]] = []
    if len(selected) == 2:
        candidates.append(("Both", _model_landmarks(selected)))
    for label, landmarks in selected:
        candidates.append((label, list(landmarks)))

    predictions = [
        model.predict(landmarks, hand_mode)
        for hand_mode, landmarks in candidates
        if landmarks
    ]
    accepted = [prediction for prediction in predictions if prediction.accepted]
    if accepted:
        return max(accepted, key=lambda prediction: prediction.confidence)
    if predictions:
        return max(predictions, key=lambda prediction: prediction.confidence)
    return _unknown_prediction(model)


def _handedness_labels(
    multi_handedness: Iterable[Any] | None,
    *,
    correct_handedness: bool = True,
) -> list[str]:
    labels: list[str] = []
    if not multi_handedness:
        return labels
    for item in multi_handedness:
        try:
            labels.append(_correct_handedness_label(
                str(item.classification[0].label),
                correct_handedness=correct_handedness,
            ))
        except (AttributeError, IndexError):
            labels.append("unknown")
    return labels


def _correct_handedness_label(label: str, *, correct_handedness: bool = True) -> str:
    if not correct_handedness:
        return label
    lower = label.lower()
    if lower == "left":
        return "Right"
    if lower == "right":
        return "Left"
    return label



def _unknown_prediction(model: GestureModel) -> Prediction:
    return Prediction(
        label=None,
        accepted=False,
        distance=float("inf"),
        confidence=0.0,
        vote_confidence=0.0,
        distance_confidence=0.0,
        threshold=model.recognition_config.fallback_distance_threshold,
        votes={},
    )


def _draw_mediapipe_landmarks(mp: Any, frame: Any, result: Any) -> None:
    if not result or not result.multi_hand_landmarks:
        return

    drawing_utils = mp.solutions.drawing_utils
    drawing_styles = getattr(mp.solutions, "drawing_styles", None)
    landmark_style = None
    connection_style = None
    if drawing_styles:
        landmark_style = drawing_styles.get_default_hand_landmarks_style()
        connection_style = drawing_styles.get_default_hand_connections_style()

    for hand_landmarks in result.multi_hand_landmarks:
        drawing_utils.draw_landmarks(
            frame,
            hand_landmarks,
            mp.solutions.hands.HAND_CONNECTIONS,
            landmark_style,
            connection_style,
        )


def _prepare_preview_window(cv2: Any, show: bool) -> None:
    if not show:
        return
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, PREVIEW_INITIAL_WIDTH, PREVIEW_INITIAL_HEIGHT)
    cv2.waitKey(1)


def _release_preview_window(cv2: Any, show: bool) -> None:
    if not show:
        return
    cv2.destroyAllWindows()
    for _ in range(PREVIEW_CLOSE_WAITKEY_CYCLES):
        cv2.waitKey(1)
        time.sleep(PREVIEW_CLOSE_SLEEP_SECONDS)


def _show_status(
    cv2: Any,
    frame: Any,
    text: str | Sequence[str],
    *,
    mp: Any | None = None,
    result: Any | None = None,
    line_colors: Sequence[tuple[int, int, int] | None] | None = None,
    prominent_line: int | None = None,
) -> None:
    if mp is not None and result is not None:
        _draw_mediapipe_landmarks(mp, frame, result)

    # Mirror first for performer intuition, then enlarge the rendered camera view.
    preview = _scaled_preview(cv2, cv2.flip(frame, 1))
    lines = [text] if isinstance(text, str) else list(text)
    y_positions = _status_y_positions(lines, prominent_line)
    for index, line in enumerate(lines):
        is_prominent = index == prominent_line
        scale = (
            PROMINENT_LINE_SCALE
            if is_prominent
            else TITLE_LINE_SCALE if index == 0 else BODY_LINE_SCALE
        )
        thickness = 3 if is_prominent else 2 if index == 0 else 1
        color = (
            line_colors[index]
            if line_colors is not None and index < len(line_colors) and line_colors[index]
            else DEFAULT_TEXT_COLOR
        )
        origin = (STATUS_MARGIN, y_positions[index])
        text_size, baseline = cv2.getTextSize(
            str(line),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            thickness,
        )
        text_width, text_height = text_size
        cv2.rectangle(
            preview,
            (
                origin[0] - STATUS_BOX_PADDING_X,
                origin[1] - text_height - STATUS_BOX_PADDING_Y,
            ),
            (
                origin[0] + text_width + STATUS_BOX_PADDING_X,
                origin[1] + baseline + STATUS_BOX_PADDING_Y,
            ),
            (0, 0, 0),
            -1,
        )
        cv2.putText(
            preview,
            str(line),
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            TEXT_OUTLINE_COLOR,
            thickness + TEXT_OUTLINE_EXTRA_THICKNESS,
            cv2.LINE_AA,
        )
        cv2.putText(
            preview,
            str(line),
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
    cv2.imshow(WINDOW_NAME, preview)


def _scaled_preview(cv2: Any, frame: Any) -> Any:
    if PREVIEW_SCALE == 1.0:
        return frame
    return cv2.resize(
        frame,
        None,
        fx=PREVIEW_SCALE,
        fy=PREVIEW_SCALE,
        interpolation=cv2.INTER_LINEAR,
    )


def _status_y_positions(
    lines: Sequence[str],
    prominent_line: int | None,
) -> list[int]:
    y = 42
    positions: list[int] = []
    for index, _ in enumerate(lines):
        positions.append(y)
        y += 46 if index == prominent_line else 34
    return positions


def _read_key(cv2: Any, delay_ms: int = 1) -> int:
    return cv2.waitKey(delay_ms) & 0xFF


def _should_stop(cv2: Any, show: bool) -> bool:
    if not show:
        return False
    if _window_was_closed(cv2):
        return True
    key = _read_key(cv2)
    return key in {27, ord("q")}


def _window_was_closed(cv2: Any) -> bool:
    try:
        return cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1
    except Exception:
        return False
