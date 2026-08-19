"""Command-line entry point for Pose2OSC.

The GUI intentionally launches this same script, so Terminal testing and app
behavior exercise the same runtime path.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pose2osc.manifest import StateConfig, generated_gesture_labels, label_style
    from pose2osc.osc import OscConfig, build_osc_route_text, load_manifest_labels
    from pose2osc.runtime import camera_test, enroll_from_camera, raw_camera_test, run_osc_camera
else:
    from .manifest import StateConfig, generated_gesture_labels, label_style
    from .osc import OscConfig, build_osc_route_text, load_manifest_labels
    from .runtime import camera_test, enroll_from_camera, raw_camera_test, run_osc_camera


HAND_CHOICES = ("Auto", "Right", "Left", "Both", "Any")
DEFAULT_GENERATED_GESTURES = 12


def _handle_stop_signal(_signum: int, _frame: object | None) -> None:
    raise KeyboardInterrupt


def _install_signal_handlers() -> None:
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_stop_signal)


def _install_parent_watchdog() -> None:
    raw_parent_pid = os.environ.get("POSE2OSC_PARENT_PID")
    if not raw_parent_pid:
        return
    try:
        parent_pid = int(raw_parent_pid)
    except ValueError:
        return
    if parent_pid <= 0:
        return

    def watch_parent() -> None:
        while True:
            time.sleep(1.0)
            try:
                os.kill(parent_pid, 0)
            except OSError:
                os.kill(os.getpid(), signal.SIGINT)
                time.sleep(2.0)
                os._exit(130)

    threading.Thread(target=watch_parent, name="Pose2OSCParentWatchdog", daemon=True).start()


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_manifest_path() -> str:
    return str(project_root() / "models" / "gestures.json")


def parse_label_text(text: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for chunk in text.replace(",", "\n").splitlines():
        for raw_label in chunk.split():
            label = raw_label.strip()
            if not label:
                continue
            if label in seen:
                raise ValueError(f"duplicate gesture label: {label}")
            labels.append(label)
            seen.add(label)
    return labels


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pose2OSC gesture enrollment and OSC performance tool.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    camera = subparsers.add_parser("camera-test", help="Open the camera preview without OSC or enrollment.")
    camera.add_argument("--raw", action="store_true", help="Use OpenCV only and skip MediaPipe import/hand tracking.")
    _add_camera_args(camera)
    camera.set_defaults(func=_run_camera_test)

    enroll = subparsers.add_parser("enroll", help="Enroll gestures into a JSON manifest.")
    enroll.add_argument("--manifest", default=default_manifest_path(), help="Gesture manifest JSON path.")
    enroll.add_argument("--label", action="append", dest="labels", default=[], help="Custom gesture label. Repeat for more labels.")
    enroll.add_argument("--labels", dest="labels_text", default="", help="Space, comma, or newline separated custom labels.")
    enroll.add_argument("--generated", type=int, default=None, help="Generate numbered labels, for example gesture_1 through gesture_12.")
    enroll.add_argument("--start-index", type=int, default=1, help="First generated gesture number.")
    enroll.add_argument("--seconds", type=float, default=2.0, help="Timed capture duration in seconds.")
    enroll.add_argument("--capture-frames", type=int, default=45, help="Recent frames saved for each Spacebar capture.")
    enroll.add_argument("--target-captures", type=int, default=5, help="Suggested captures per gesture.")
    enroll.add_argument("--max-samples", type=int, default=64, help="Maximum stored frames from each capture.")
    enroll.add_argument("--timed", action="store_true", help="Use timed capture instead of Spacebar capture.")
    enroll.add_argument("--replace", action="store_true", help="Replace existing samples for the enrolled label.")
    enroll.add_argument("--no-preview", action="store_true", help="Disable the preview window.")
    _add_camera_args(enroll)
    enroll.set_defaults(func=_run_enroll)

    perform = subparsers.add_parser("perform", help="Recognize gestures and send OSC.")
    perform.add_argument("--manifest", default=default_manifest_path(), help="Gesture manifest JSON path.")
    perform.add_argument("--host", default="127.0.0.1", help="OSC receiver host.")
    perform.add_argument("--port", type=int, default=9000, help="OSC receiver port.")
    perform.add_argument("--split-axes", action="store_true", help="Send /x, /y, and /z routes for every landmark.")
    perform.add_argument("--no-landmark-vectors", action="store_true", help="Disable vector landmark messages.")
    perform.add_argument("--send-unknown", action="store_true", help="Send unknown state when no gesture is accepted.")
    perform.add_argument("--enter-frames", type=int, default=1, help="Frames needed to enter a gesture.")
    perform.add_argument("--exit-frames", type=int, default=1, help="Frames needed to exit a gesture.")
    perform.add_argument("--switch-frames", type=int, default=1, help="Frames needed to switch gestures.")
    perform.add_argument("--no-preview", action="store_true", help="Disable the preview window.")
    _add_camera_args(perform)
    perform.set_defaults(func=_run_perform)

    routes = subparsers.add_parser("routes", help="Print OSC routes for a manifest and settings.")
    routes.add_argument("--manifest", default=default_manifest_path(), help="Gesture manifest JSON path.")
    routes.add_argument("--split-axes", action="store_true", help="Include split-axis landmark routes.")
    routes.add_argument("--no-landmark-vectors", action="store_true", help="Hide vector landmark routes.")
    routes.add_argument("--send-unknown", action="store_true", help="Include unknown prediction routes.")
    routes.set_defaults(func=_run_routes)

    return parser


def _add_camera_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--camera", type=int, default=0, help="Camera index. Built-in webcams are usually 0.")
    parser.add_argument("--hand", choices=HAND_CHOICES, default="Auto", help="Hand mode to track.")
    parser.add_argument("--no-correct-handedness", action="store_true", help="Do not correct MediaPipe handedness for the mirrored preview.")
    parser.add_argument("--width", type=int, default=None, help="Optional camera width request.")
    parser.add_argument("--height", type=int, default=None, help="Optional camera height request.")


def _run_camera_test(args: argparse.Namespace) -> int:
    if args.raw:
        print("Opening Pose2OSC raw camera test (OpenCV only)...", flush=True)
        raw_camera_test(
            camera=args.camera,
            width=args.width,
            height=args.height,
        )
        return 0

    print("Opening Pose2OSC camera test...", flush=True)
    camera_test(
        camera=args.camera,
        handedness=args.hand,
        correct_handedness=not args.no_correct_handedness,
        width=args.width,
        height=args.height,
    )
    return 0


def _run_enroll(args: argparse.Namespace) -> int:
    labels = _resolve_enroll_labels(args)
    if len(labels) > 1 and (args.timed or args.no_preview):
        raise ValueError("Multiple gesture labels require preview on and timed capture off.")

    display_labels = "', '".join(label_style(label).display_label for label in labels)
    mode = "replace" if args.replace else "append"
    print(f"Starting Set Gesture for '{display_labels}'", flush=True)
    print(f"Manifest: {args.manifest}", flush=True)
    print(f"Capture mode: {mode}", flush=True)
    print("Opening camera preview...", flush=True)

    sample_count = enroll_from_camera(
        label=labels,
        model_path=args.manifest,
        seconds=args.seconds,
        capture_frames=args.capture_frames,
        target_captures=args.target_captures,
        camera=args.camera,
        max_samples=args.max_samples,
        handedness=args.hand,
        correct_handedness=not args.no_correct_handedness,
        show=not args.no_preview,
        timed=args.timed,
        replace=args.replace,
        width=args.width,
        height=args.height,
    )
    print(f"Saved {sample_count} samples", flush=True)
    return 0


def _run_perform(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest).expanduser()
    if not manifest.exists():
        raise ValueError(
            "Performance needs a saved gesture manifest. Use Load to select one, "
            "or use Set Gesture to create one first."
        )
    if not 1 <= args.port <= 65535:
        raise ValueError("OSC port must be between 1 and 65535.")

    print("Starting Performance", flush=True)
    print(f"Manifest: {args.manifest}", flush=True)
    print(f"OSC: {args.host}:{args.port}", flush=True)
    print("Opening camera preview...", flush=True)

    run_osc_camera(
        model_path=args.manifest,
        osc=OscConfig(
            host=args.host,
            port=args.port,
            split_axis_messages=args.split_axes,
            send_landmark_vectors=not args.no_landmark_vectors,
            send_unknown_predictions=args.send_unknown,
        ),
        camera=args.camera,
        handedness=args.hand,
        correct_handedness=not args.no_correct_handedness,
        show=not args.no_preview,
        width=args.width,
        height=args.height,
        state_config=StateConfig(
            enter_frames=args.enter_frames,
            exit_frames=args.exit_frames,
            switch_frames=args.switch_frames,
        ),
    )
    return 0


def _run_routes(args: argparse.Namespace) -> int:
    labels = load_manifest_labels(args.manifest)
    print(
        build_osc_route_text(
            labels,
            send_landmark_vectors=not args.no_landmark_vectors,
            split_axes=args.split_axes,
            send_unknown_predictions=args.send_unknown,
        ),
        end="",
    )
    return 0


def _resolve_enroll_labels(args: argparse.Namespace) -> list[str]:
    custom_labels = list(args.labels or []) + parse_label_text(args.labels_text or "")
    if custom_labels:
        return custom_labels
    count = args.generated if args.generated is not None else DEFAULT_GENERATED_GESTURES
    return generated_gesture_labels(count, args.start_index)


def main(argv: Sequence[str] | None = None) -> int:
    _install_signal_handlers()
    _install_parent_watchdog()
    previous_runtime_log = os.environ.get("POSE2OSC_RUNTIME_LOG")
    if previous_runtime_log is None:
        os.environ["POSE2OSC_RUNTIME_LOG"] = "1"
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("Session interrupted", flush=True)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", flush=True)
        return 1
    finally:
        if previous_runtime_log is None:
            os.environ.pop("POSE2OSC_RUNTIME_LOG", None)
        else:
            os.environ["POSE2OSC_RUNTIME_LOG"] = previous_runtime_log


if __name__ == "__main__":
    raise SystemExit(main())
