# Pose2OSC OSC Outputs For Max

Default receive port:

```text
9000
```

Top-level prefix:

```text
/pose2osc
```

## Global Gesture State

```text
/pose2osc/state/active
/pose2osc/state/event
```

Payloads:

```text
/pose2osc/state/active label confidence
/pose2osc/state/event enter|switch|exit label confidence
```

If unknown predictions are enabled:

```text
/pose2osc/state/active unknown 0.0
```

When a gesture exits:

```text
/pose2osc/state/active none 0.0
```

## User Gesture Routes

Current manifest:

```text
gesture_1
gesture_2
gesture_3
gesture_4
gesture_5
gesture_6
gesture_7
gesture_8
gesture_9
gesture_10
gesture_11
gesture_12
gesture_13
```

Each gesture has three routes:

```text
/pose2osc/gesture/gesture_1/active
/pose2osc/gesture/gesture_1/trigger
/pose2osc/gesture/gesture_1/confidence
/pose2osc/gesture/gesture_2/active
/pose2osc/gesture/gesture_2/trigger
/pose2osc/gesture/gesture_2/confidence
/pose2osc/gesture/gesture_3/active
/pose2osc/gesture/gesture_3/trigger
/pose2osc/gesture/gesture_3/confidence
/pose2osc/gesture/gesture_4/active
/pose2osc/gesture/gesture_4/trigger
/pose2osc/gesture/gesture_4/confidence
/pose2osc/gesture/gesture_5/active
/pose2osc/gesture/gesture_5/trigger
/pose2osc/gesture/gesture_5/confidence
/pose2osc/gesture/gesture_6/active
/pose2osc/gesture/gesture_6/trigger
/pose2osc/gesture/gesture_6/confidence
/pose2osc/gesture/gesture_7/active
/pose2osc/gesture/gesture_7/trigger
/pose2osc/gesture/gesture_7/confidence
/pose2osc/gesture/gesture_8/active
/pose2osc/gesture/gesture_8/trigger
/pose2osc/gesture/gesture_8/confidence
/pose2osc/gesture/gesture_9/active
/pose2osc/gesture/gesture_9/trigger
/pose2osc/gesture/gesture_9/confidence
/pose2osc/gesture/gesture_10/active
/pose2osc/gesture/gesture_10/trigger
/pose2osc/gesture/gesture_10/confidence
/pose2osc/gesture/gesture_11/active
/pose2osc/gesture/gesture_11/trigger
/pose2osc/gesture/gesture_11/confidence
/pose2osc/gesture/gesture_12/active
/pose2osc/gesture/gesture_12/trigger
/pose2osc/gesture/gesture_12/confidence
/pose2osc/gesture/gesture_13/active
/pose2osc/gesture/gesture_13/trigger
/pose2osc/gesture/gesture_13/confidence
```

Payloads:

```text
/pose2osc/gesture/{gesture_label}/active 1|0
/pose2osc/gesture/{gesture_label}/trigger 1
/pose2osc/gesture/{gesture_label}/confidence confidence
```

For more gestures, continue the same pattern:

```text
/pose2osc/gesture/gesture_14/active
/pose2osc/gesture/gesture_14/trigger
/pose2osc/gesture/gesture_14/confidence
```

## Hand And Frame Status

```text
/pose2osc/hand/visible
/pose2osc/hand/num_hands
/pose2osc/frame
```

Payloads:

```text
/pose2osc/hand/visible 1|0
/pose2osc/hand/num_hands 0|1|2
/pose2osc/frame frame_index timestamp_ms
```

## MediaPipe Landmark Names

These names are used for both `right` and `left` hands:

```text
wrist
thumb_cmc
thumb_mcp
thumb_ip
thumb_tip
index_mcp
index_pip
index_dip
index_tip
middle_mcp
middle_pip
middle_dip
middle_tip
ring_mcp
ring_pip
ring_dip
ring_tip
pinky_mcp
pinky_pip
pinky_dip
pinky_tip
```

## Landmark Vector Routes

Enabled by the Landmark vectors option. Each route sends three floats:

```text
/pose2osc/hand/{right|left}/{landmark} x y z
```

Expanded vector routes:

```text
/pose2osc/hand/right/wrist
/pose2osc/hand/right/thumb_cmc
/pose2osc/hand/right/thumb_mcp
/pose2osc/hand/right/thumb_ip
/pose2osc/hand/right/thumb_tip
/pose2osc/hand/right/index_mcp
/pose2osc/hand/right/index_pip
/pose2osc/hand/right/index_dip
/pose2osc/hand/right/index_tip
/pose2osc/hand/right/middle_mcp
/pose2osc/hand/right/middle_pip
/pose2osc/hand/right/middle_dip
/pose2osc/hand/right/middle_tip
/pose2osc/hand/right/ring_mcp
/pose2osc/hand/right/ring_pip
/pose2osc/hand/right/ring_dip
/pose2osc/hand/right/ring_tip
/pose2osc/hand/right/pinky_mcp
/pose2osc/hand/right/pinky_pip
/pose2osc/hand/right/pinky_dip
/pose2osc/hand/right/pinky_tip
/pose2osc/hand/left/wrist
/pose2osc/hand/left/thumb_cmc
/pose2osc/hand/left/thumb_mcp
/pose2osc/hand/left/thumb_ip
/pose2osc/hand/left/thumb_tip
/pose2osc/hand/left/index_mcp
/pose2osc/hand/left/index_pip
/pose2osc/hand/left/index_dip
/pose2osc/hand/left/index_tip
/pose2osc/hand/left/middle_mcp
/pose2osc/hand/left/middle_pip
/pose2osc/hand/left/middle_dip
/pose2osc/hand/left/middle_tip
/pose2osc/hand/left/ring_mcp
/pose2osc/hand/left/ring_pip
/pose2osc/hand/left/ring_dip
/pose2osc/hand/left/ring_tip
/pose2osc/hand/left/pinky_mcp
/pose2osc/hand/left/pinky_pip
/pose2osc/hand/left/pinky_dip
/pose2osc/hand/left/pinky_tip
```

## Split Axis Landmark Routes

Enabled by the Split axes option. Each route sends one float:

```text
/pose2osc/hand/{right|left}/{landmark}/x value
/pose2osc/hand/{right|left}/{landmark}/y value
/pose2osc/hand/{right|left}/{landmark}/z value
```

To receive every split-axis route, use every landmark name above for both hands and all three axes.

Expanded split-axis routes:

```text
/pose2osc/hand/right/wrist/x
/pose2osc/hand/right/wrist/y
/pose2osc/hand/right/wrist/z
/pose2osc/hand/right/thumb_cmc/x
/pose2osc/hand/right/thumb_cmc/y
/pose2osc/hand/right/thumb_cmc/z
/pose2osc/hand/right/thumb_mcp/x
/pose2osc/hand/right/thumb_mcp/y
/pose2osc/hand/right/thumb_mcp/z
/pose2osc/hand/right/thumb_ip/x
/pose2osc/hand/right/thumb_ip/y
/pose2osc/hand/right/thumb_ip/z
/pose2osc/hand/right/thumb_tip/x
/pose2osc/hand/right/thumb_tip/y
/pose2osc/hand/right/thumb_tip/z
/pose2osc/hand/right/index_mcp/x
/pose2osc/hand/right/index_mcp/y
/pose2osc/hand/right/index_mcp/z
/pose2osc/hand/right/index_pip/x
/pose2osc/hand/right/index_pip/y
/pose2osc/hand/right/index_pip/z
/pose2osc/hand/right/index_dip/x
/pose2osc/hand/right/index_dip/y
/pose2osc/hand/right/index_dip/z
/pose2osc/hand/right/index_tip/x
/pose2osc/hand/right/index_tip/y
/pose2osc/hand/right/index_tip/z
/pose2osc/hand/right/middle_mcp/x
/pose2osc/hand/right/middle_mcp/y
/pose2osc/hand/right/middle_mcp/z
/pose2osc/hand/right/middle_pip/x
/pose2osc/hand/right/middle_pip/y
/pose2osc/hand/right/middle_pip/z
/pose2osc/hand/right/middle_dip/x
/pose2osc/hand/right/middle_dip/y
/pose2osc/hand/right/middle_dip/z
/pose2osc/hand/right/middle_tip/x
/pose2osc/hand/right/middle_tip/y
/pose2osc/hand/right/middle_tip/z
/pose2osc/hand/right/ring_mcp/x
/pose2osc/hand/right/ring_mcp/y
/pose2osc/hand/right/ring_mcp/z
/pose2osc/hand/right/ring_pip/x
/pose2osc/hand/right/ring_pip/y
/pose2osc/hand/right/ring_pip/z
/pose2osc/hand/right/ring_dip/x
/pose2osc/hand/right/ring_dip/y
/pose2osc/hand/right/ring_dip/z
/pose2osc/hand/right/ring_tip/x
/pose2osc/hand/right/ring_tip/y
/pose2osc/hand/right/ring_tip/z
/pose2osc/hand/right/pinky_mcp/x
/pose2osc/hand/right/pinky_mcp/y
/pose2osc/hand/right/pinky_mcp/z
/pose2osc/hand/right/pinky_pip/x
/pose2osc/hand/right/pinky_pip/y
/pose2osc/hand/right/pinky_pip/z
/pose2osc/hand/right/pinky_dip/x
/pose2osc/hand/right/pinky_dip/y
/pose2osc/hand/right/pinky_dip/z
/pose2osc/hand/right/pinky_tip/x
/pose2osc/hand/right/pinky_tip/y
/pose2osc/hand/right/pinky_tip/z
/pose2osc/hand/left/wrist/x
/pose2osc/hand/left/wrist/y
/pose2osc/hand/left/wrist/z
/pose2osc/hand/left/thumb_cmc/x
/pose2osc/hand/left/thumb_cmc/y
/pose2osc/hand/left/thumb_cmc/z
/pose2osc/hand/left/thumb_mcp/x
/pose2osc/hand/left/thumb_mcp/y
/pose2osc/hand/left/thumb_mcp/z
/pose2osc/hand/left/thumb_ip/x
/pose2osc/hand/left/thumb_ip/y
/pose2osc/hand/left/thumb_ip/z
/pose2osc/hand/left/thumb_tip/x
/pose2osc/hand/left/thumb_tip/y
/pose2osc/hand/left/thumb_tip/z
/pose2osc/hand/left/index_mcp/x
/pose2osc/hand/left/index_mcp/y
/pose2osc/hand/left/index_mcp/z
/pose2osc/hand/left/index_pip/x
/pose2osc/hand/left/index_pip/y
/pose2osc/hand/left/index_pip/z
/pose2osc/hand/left/index_dip/x
/pose2osc/hand/left/index_dip/y
/pose2osc/hand/left/index_dip/z
/pose2osc/hand/left/index_tip/x
/pose2osc/hand/left/index_tip/y
/pose2osc/hand/left/index_tip/z
/pose2osc/hand/left/middle_mcp/x
/pose2osc/hand/left/middle_mcp/y
/pose2osc/hand/left/middle_mcp/z
/pose2osc/hand/left/middle_pip/x
/pose2osc/hand/left/middle_pip/y
/pose2osc/hand/left/middle_pip/z
/pose2osc/hand/left/middle_dip/x
/pose2osc/hand/left/middle_dip/y
/pose2osc/hand/left/middle_dip/z
/pose2osc/hand/left/middle_tip/x
/pose2osc/hand/left/middle_tip/y
/pose2osc/hand/left/middle_tip/z
/pose2osc/hand/left/ring_mcp/x
/pose2osc/hand/left/ring_mcp/y
/pose2osc/hand/left/ring_mcp/z
/pose2osc/hand/left/ring_pip/x
/pose2osc/hand/left/ring_pip/y
/pose2osc/hand/left/ring_pip/z
/pose2osc/hand/left/ring_dip/x
/pose2osc/hand/left/ring_dip/y
/pose2osc/hand/left/ring_dip/z
/pose2osc/hand/left/ring_tip/x
/pose2osc/hand/left/ring_tip/y
/pose2osc/hand/left/ring_tip/z
/pose2osc/hand/left/pinky_mcp/x
/pose2osc/hand/left/pinky_mcp/y
/pose2osc/hand/left/pinky_mcp/z
/pose2osc/hand/left/pinky_pip/x
/pose2osc/hand/left/pinky_pip/y
/pose2osc/hand/left/pinky_pip/z
/pose2osc/hand/left/pinky_dip/x
/pose2osc/hand/left/pinky_dip/y
/pose2osc/hand/left/pinky_dip/z
/pose2osc/hand/left/pinky_tip/x
/pose2osc/hand/left/pinky_tip/y
/pose2osc/hand/left/pinky_tip/z
```

## Native Max oscparse Skeleton

```text
[udpreceive 9000]
|
[oscparse]
|
[route pose2osc]
|
[route state gesture hand frame]
```

Then route each branch:

```text
state -> [route active event]
gesture -> [route gesture_1 gesture_2 gesture_3 gesture_4 gesture_5 gesture_6 gesture_7 gesture_8 gesture_9 gesture_10 gesture_11 gesture_12 gesture_13]
gesture_# -> [route active trigger confidence]
hand -> [route visible num_hands right left]
right -> [route wrist thumb_cmc thumb_mcp thumb_ip thumb_tip index_mcp index_pip index_dip index_tip middle_mcp middle_pip middle_dip middle_tip ring_mcp ring_pip ring_dip ring_tip pinky_mcp pinky_pip pinky_dip pinky_tip]
left -> [route wrist thumb_cmc thumb_mcp thumb_ip thumb_tip index_mcp index_pip index_dip index_tip middle_mcp middle_pip middle_dip middle_tip ring_mcp ring_pip ring_dip ring_tip pinky_mcp pinky_pip pinky_dip pinky_tip]
landmark -> [route x y z] only when Split axes is enabled
```
