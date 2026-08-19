"""OSC message configuration, sending, and route descriptions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .manifest import GestureModel, LANDMARK_NAMES, label_style


@dataclass(slots=True)
class OscConfig:
    host: str = "127.0.0.1"
    port: int = 9000
    split_axis_messages: bool = False
    send_landmark_vectors: bool = True
    send_unknown_predictions: bool = False


HAND_KEYS = ("right", "left")


def load_manifest_labels(path: str) -> list[str]:
    manifest = Path(path).expanduser()
    if not manifest.exists():
        return []
    try:
        return GestureModel.load(manifest).labels
    except (OSError, ValueError, KeyError):
        return []


def build_osc_route_text(
    labels: Sequence[str],
    *,
    send_landmark_vectors: bool,
    split_axes: bool,
    send_unknown_predictions: bool,
) -> str:
    lines = [
        "POSE2OSC OSC ROUTING",
        "",
        "Gesture state messages",
        "/pose2osc/state/active [label, confidence]",
        "  Sent while a known gesture is active.",
        "/pose2osc/state/event [event, label, confidence]",
        "  event is enter, switch, or exit.",
        "",
        "Per-gesture messages",
    ]
    if labels:
        for label in labels:
            display_label = label_style(label).display_label
            lines.extend([
                f"{display_label} ({label})",
                f"  /pose2osc/gesture/{label}/active 1|0",
                f"  /pose2osc/gesture/{label}/trigger 1",
                f"  /pose2osc/gesture/{label}/confidence confidence",
            ])
    else:
        lines.append("No enrolled gestures found in the selected manifest yet.")

    lines.extend([
        "",
        "Hand and frame status",
        "/pose2osc/hand/visible 1|0",
        "/pose2osc/hand/num_hands count",
        "/pose2osc/frame [frame_index, timestamp_ms]",
        "",
        "MediaPipe landmark data",
    ])

    if send_landmark_vectors:
        lines.extend([
            "Vector messages are enabled:",
            "/pose2osc/hand/{hand}/{landmark} [x, y, z]",
            "Examples:",
        ])
        lines.extend(_landmark_examples(vector=True))
    else:
        lines.append("Vector messages are off.")

    if split_axes:
        lines.extend([
            "",
            "Split-axis messages are enabled:",
            "/pose2osc/hand/{hand}/{landmark}/x x",
            "/pose2osc/hand/{hand}/{landmark}/y y",
            "/pose2osc/hand/{hand}/{landmark}/z z",
            "Examples:",
        ])
        lines.extend(_landmark_examples(vector=False))

    if send_unknown_predictions:
        lines.extend([
            "",
            "Unknown prediction messages",
            "/pose2osc/state/active [unknown, 0.0]",
            "  Sent when no enrolled gesture is accepted.",
        ])

    return "\n".join(lines) + "\n"


def _landmark_examples(*, vector: bool) -> list[str]:
    examples: list[str] = []
    for hand in HAND_KEYS:
        for landmark in LANDMARK_NAMES[:3]:
            if vector:
                examples.append(f"  /pose2osc/hand/{hand}/{landmark} [x, y, z]")
            else:
                examples.extend([
                    f"  /pose2osc/hand/{hand}/{landmark}/x x",
                    f"  /pose2osc/hand/{hand}/{landmark}/y y",
                    f"  /pose2osc/hand/{hand}/{landmark}/z z",
                ])
    examples.append("  ...continues for all 21 MediaPipe hand landmarks per visible hand")
    return examples


def send_landmarks(
    client: Any,
    hand_key: str,
    landmarks: list[tuple[float, float, float]],
    osc_cfg: OscConfig,
) -> None:
    if not osc_cfg.send_landmark_vectors and not osc_cfg.split_axis_messages:
        return
    for index, (x, y, z) in enumerate(landmarks):
        name = LANDMARK_NAMES[index]
        if osc_cfg.send_landmark_vectors:
            client.send_message(f"/pose2osc/hand/{hand_key}/{name}", [x, y, z])
        if osc_cfg.split_axis_messages:
            client.send_message(f"/pose2osc/hand/{hand_key}/{name}/x", x)
            client.send_message(f"/pose2osc/hand/{hand_key}/{name}/y", y)
            client.send_message(f"/pose2osc/hand/{hand_key}/{name}/z", z)


def send_prediction(client: Any, prediction: Any, state: Any, osc_cfg: OscConfig) -> None:
    if state.event == "switch" and state.previous_label:
        client.send_message(f"/pose2osc/gesture/{state.previous_label}/active", 0)

    if prediction.accepted and state.active_label:
        label = state.active_label
        client.send_message("/pose2osc/state/active", [label, prediction.confidence])
        client.send_message(f"/pose2osc/gesture/{label}/active", 1)
        client.send_message(f"/pose2osc/gesture/{label}/confidence", prediction.confidence)
    elif osc_cfg.send_unknown_predictions:
        client.send_message("/pose2osc/state/active", ["unknown", 0.0])

    if state.event in {"enter", "switch", "exit"}:
        label = state.active_label or state.previous_label or "none"
        client.send_message("/pose2osc/state/event", [state.event, label, prediction.confidence])
        if state.event in {"enter", "switch"} and state.active_label:
            client.send_message(f"/pose2osc/gesture/{state.active_label}/trigger", 1)
        if state.event == "exit" and state.previous_label:
            client.send_message(f"/pose2osc/gesture/{state.previous_label}/active", 0)
            client.send_message(f"/pose2osc/gesture/{state.previous_label}/confidence", 0.0)
            client.send_message("/pose2osc/state/active", ["none", 0.0])


def send_no_hand(client: Any, now_ms: int, frame_index: int) -> None:
    client.send_message("/pose2osc/hand/visible", 0)
    client.send_message("/pose2osc/hand/num_hands", 0)
    client.send_message("/pose2osc/frame", [frame_index, now_ms])

