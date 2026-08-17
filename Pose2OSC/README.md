# Pose2OSC

Pose2OSC is a desktop app for recording hand gestures from a webcam and using
those gestures to send live OSC messages. It is designed for Max/MSP
instruments, interactive performance patches, and other OSC-based systems.

The project is app-centered for performers: users launch the app, record
gestures in Set Gesture mode, then switch to Performance mode to send OSC. The
same runtime is also exposed through a small command-line interface, which makes
camera troubleshooting and development much easier without changing the app
workflow.

## Quick Start

Pose2OSC requires Python 3.10 or newer. Python 3.11 is recommended when it is
available.

1. Download or clone this folder.
2. Double-click `Launch Pose2OSC.command`.
3. Wait for the first-launch setup to finish if dependencies need to be
   installed.
4. In the app, leave the default Manifest file selected.
5. Use Set Gesture to record gestures.
6. Use Performance to recognize gestures and send OSC.

The first launch creates a local `.venv` folder and installs the required Python
packages if they are missing. After that, launches should be much faster.

If double-clicking does not work, open Terminal in this folder and run:

```bash
python3 launch_pose2osc.py
```

If dependencies are missing, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python launch_pose2osc.py
```

## Command-Line Check

The GUI launches the same runtime used by the command line. If the preview ever
seems stuck in the app, test the camera directly from Terminal in this folder:

```bash
.venv/bin/python pose2osc/cli.py camera-test
```

Useful commands:

```bash
.venv/bin/python pose2osc/cli.py camera-test --camera 0
.venv/bin/python pose2osc/cli.py enroll --manifest models/gestures.json --generated 12
.venv/bin/python pose2osc/cli.py perform --manifest models/gestures.json --port 9000
.venv/bin/python pose2osc/cli.py routes --manifest models/gestures.json
```

If `camera-test` opens a preview, the camera/OpenCV layer is working and any
remaining problem is probably in the GUI launch path or selected settings. If
`camera-test` does not open a preview, check camera permissions, camera index,
and whether another app is using the webcam.

## What The App Does

Pose2OSC uses MediaPipe to track hands from a live camera. In Set Gesture mode,
it saves examples of held poses into a gesture manifest. In Performance mode, it
loads that manifest, recognizes the saved gestures live, and sends OSC messages
for both gesture state and continuous hand landmarks.

The recognizer is intentionally lightweight:

- no neural network at runtime
- one-frame KNN gesture prediction
- normalized hand-shape features
- low-latency default state tracking
- continuous landmark OSC output alongside gesture triggers

## Project Structure

```text
Pose2OSC/
  Launch Pose2OSC.command      macOS double-click launcher
  launch_pose2osc.py           Python launcher for the GUI
  README.md                    user and developer guide
  pyproject.toml               package metadata and dependencies
  models/                      local gesture manifests created by the app
  pose2osc/
    app.py                     GUI wrapper around the CLI runtime
    cli.py                     camera-test, enroll, perform, and routes commands
    runtime.py                 camera, MediaPipe, preview, enrollment, performance
    manifest.py                JSON manifests, labels, features, and recognition
    osc.py                     OSC sending and route descriptions
  tests/                       unit tests for manifest, runtime, CLI, OSC, and app helpers
```

Local gesture manifests such as `models/gestures.json` are ignored by Git so
performer-specific training data does not accidentally get uploaded.

## App Overview

The top Session area applies to both modes. It chooses the manifest file, camera
index, hand tracking mode, preview behavior, and optional camera size.

The main tabs choose what Pose2OSC is doing:

- Set Gesture records or updates saved hand poses.
- Performance recognizes saved gestures and sends OSC.

The Manifest panel shows what is saved in the selected manifest. The Output
panel shows the exact command the GUI launched, followed by runtime messages and
errors in plain text.

## Session Controls

Manifest file is the JSON file where gestures are saved. The default is
`models/gestures.json`.

Load opens an existing performer manifest from a folder. Use this when you want
to switch to a different saved `.json` gesture set.

New lets you choose the path and filename for a new performer manifest. The file
is created when you enroll gestures into it.

Camera chooses the camera index. Most built-in webcams are `0`. If the wrong
camera opens, try `1` or `2`.

Hand chooses what Pose2OSC watches:

- Auto is best for most users and accepts one or two visible hands.
- Right watches only the right hand.
- Left watches only the left hand.
- Both allows two-hand poses while still tolerating one visible hand.
- Any accepts whichever hand MediaPipe reports.

Correct handedness should normally stay on. Pose2OSC corrects MediaPipe's
left/right labels for the unmirrored camera feed while showing a mirrored
performer-friendly preview.

Preview window should normally stay on. It opens the live camera view with
tracking, status text, and capture prompts.

Width and Height are optional camera size requests. Leave them blank unless you
need a specific resolution.

## Set Gesture Mode

Use Set Gesture when you want to create or improve saved gestures.

Generated creates labels such as `gesture_1`, `gesture_2`, through the
default `gesture_12`. This is the easiest option for a new user.

Count controls how many generated gestures to create. The app default is `12`.

Start number chooses the first generated gesture number. Count `2` and Start
number `4` creates `gesture_4` and `gesture_5`.

Labels lets you type custom gesture names such as `delay_hold` or
`filter_grab`. Separate multiple labels with spaces, commas, or new lines.

Seconds is used only when Timed capture is on. In normal preview capture, you
press Space when your hand is ready.

Frames per capture is how many recent hand frames are saved each time you press
Space. The default `45` captures a small window of natural variation.

Target captures is the recommended number of Space presses per gesture. The
preview shows progress such as `Captured: 3/5`.

Max samples limits how many frames from one enrollment are stored. The default
`64` keeps recognition fast.

Timed capture uses countdown-style capture instead of the Spacebar workflow.
Leave it off unless you specifically need timed capture.

Replace existing samples removes old samples for that gesture before saving the
new capture. Leave it off to add more examples to an existing gesture.

In the preview window:

- Hold the pose you want to save.
- Press Space to capture it.
- Press `n` for the next generated or listed gesture.
- Press `p` for the previous gesture.
- Press `q` or Esc to finish.

For multiple gestures in one session, Preview must be on and Timed capture must
be off.

## Performance Mode

Use Performance after your manifest contains saved gestures.

OSC host is the receiver address. Use `127.0.0.1` when Max/MSP is running on the
same computer.

OSC port is the receiver port. The default is `9000`; make sure this matches the
port in your Max patch or OSC receiver.

Split axes sends separate `/x`, `/y`, and `/z` messages for each landmark.

Landmark vectors sends each landmark as one vector message containing `x y z`.
Leave this on unless you only want split-axis messages.

Unknown predictions sends an explicit `unknown` state when no saved gesture is
accepted. Most users can leave this off.

Show OSC routes opens an in-app reference panel listing the gesture and landmark
OSC paths for the currently selected manifest and OSC settings. This is useful
when pairing Pose2OSC with Max/MSP route objects.

Enter frames controls how many matching frames are needed before a gesture turns
on. The default `1` is lowest latency.

Exit frames controls how many non-matching frames are needed before a gesture
turns off. Raise this to `2` or `3` if gestures flicker off too easily.

Switch frames controls how many frames are needed to switch from one active
gesture to another. The default `1` keeps switching immediate.

Stop ends the active Set Gesture or Performance session. You can also press `q`
or Esc in the preview window.

## OSC Messages

Pose2OSC sends three families of OSC messages: enrolled gesture state, live hand
and frame status, and individual MediaPipe hand landmarks.

### Enrolled Gesture Messages

Each gesture enrolled in the selected manifest gets its own routes. If your
manifest contains `gesture_1`, Pose2OSC can send:

```text
/pose2osc/gesture/gesture_1/active 1
/pose2osc/gesture/gesture_1/trigger 1
/pose2osc/gesture/gesture_1/confidence 0.92
```

`active` is `1` while the gesture is active and `0` when it exits. `trigger` is
sent with value `1` when the gesture enters or switches in. `confidence` is the
recognizer confidence for the active gesture, and is sent as `0.0` on exit.

Global gesture state is also sent:

```text
/pose2osc/state/active gesture_1 0.92
/pose2osc/state/event enter gesture_1 0.92
```

`/pose2osc/state/active` carries the current label and confidence.
`/pose2osc/state/event` carries `enter`, `switch`, or `exit`, followed by the
label and confidence.

On exit, Pose2OSC sends:

```text
/pose2osc/state/event exit gesture_1 0.0
/pose2osc/gesture/gesture_1/active 0
/pose2osc/gesture/gesture_1/confidence 0.0
/pose2osc/state/active none 0.0
```

If Unknown predictions is enabled, Pose2OSC can also send:

```text
/pose2osc/state/active unknown 0.0
```

### Hand And Frame Status

These messages describe whether a hand is visible and identify each camera
frame:

```text
/pose2osc/hand/visible 1
/pose2osc/hand/num_hands 1
/pose2osc/frame 284 1786543210000
```

When no hand is visible, `visible` is `0` and `num_hands` is `0`.
`/pose2osc/frame` carries `[frame_index, timestamp_ms]`.

### MediaPipe Landmark Messages

When Landmark vectors is enabled, each visible hand sends one vector message per
MediaPipe landmark:

```text
/pose2osc/hand/right/index_mcp 0.42 0.71 -0.18
/pose2osc/hand/left/wrist 0.52 0.63 -0.05
```

The route pattern is:

```text
/pose2osc/hand/{right|left}/{landmark} x y z
```

When Split axes is enabled, each landmark also sends separate axis routes:

```text
/pose2osc/hand/right/index_mcp/x 0.42
/pose2osc/hand/right/index_mcp/y 0.71
/pose2osc/hand/right/index_mcp/z -0.18
```

The route pattern is:

```text
/pose2osc/hand/{right|left}/{landmark}/{x|y|z} value
```

The landmark names are:

```text
wrist
thumb_cmc, thumb_mcp, thumb_ip, thumb_tip
index_mcp, index_pip, index_dip, index_tip
middle_mcp, middle_pip, middle_dip, middle_tip
ring_mcp, ring_pip, ring_dip, ring_tip
pinky_mcp, pinky_pip, pinky_dip, pinky_tip
```

In the app, turn on Show OSC routes in Performance mode to see a route reference
for the current manifest and OSC options.

## Troubleshooting

If no camera opens, try Camera `1` or `2`, close other camera apps, and check
camera permissions for Terminal or Python. The Output panel should report the
exact CLI command it launched and when Pose2OSC is opening the camera preview.
It also reports an error if the camera opens but does not return frames.

If the GUI does not show a preview, run `.venv/bin/python pose2osc/cli.py
camera-test` from Terminal in this folder. That separates camera/runtime issues
from GUI launch issues.

If Performance does not start, make sure the selected manifest exists and
contains enrolled gestures. Use Load to select an existing performer `.json`
file, or use Set Gesture to create a new one first.

If the preview opens but no hand is detected, improve lighting, move your hand
fully into frame, and avoid very busy backgrounds.

If Performance starts but Max/MSP receives nothing, confirm the OSC port, confirm
Max is listening on that port, and use `127.0.0.1` when both apps are on the
same computer.

If gestures trigger unreliably, add more captures per gesture in Set Gesture.
Capture the same pose several times with small changes in position and distance
from the camera.

If gestures flicker during Performance, keep Enter frames at `1` and raise Exit
frames to `2` or `3`.

## Development

Run tests with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -t .
```

The tests do not open the camera. Live camera behavior should be checked with
`camera-test` first, then from the app. OSC behavior should be checked manually
with Max/MSP or another OSC receiver.
