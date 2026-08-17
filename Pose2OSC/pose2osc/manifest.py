"""Gesture manifests, labels, feature extraction, and recognition.

This module is the durable center of Pose2OSC's saved gesture data. It owns the
JSON manifest format, generated labels, display colors, hand-shape feature
extraction, KNN prediction, and low-latency gesture state tracking.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any, Iterable, Sequence

Point3 = tuple[float, float, float]

LANDMARK_NAMES: tuple[str, ...] = (
    "wrist",
    "thumb_cmc",
    "thumb_mcp",
    "thumb_ip",
    "thumb_tip",
    "index_mcp",
    "index_pip",
    "index_dip",
    "index_tip",
    "middle_mcp",
    "middle_pip",
    "middle_dip",
    "middle_tip",
    "ring_mcp",
    "ring_pip",
    "ring_dip",
    "ring_tip",
    "pinky_mcp",
    "pinky_pip",
    "pinky_dip",
    "pinky_tip",
)

FINGER_CHAINS: tuple[tuple[int, int, int, int], ...] = (
    (1, 2, 3, 4),
    (5, 6, 7, 8),
    (9, 10, 11, 12),
    (13, 14, 15, 16),
    (17, 18, 19, 20),
)

TIP_INDICES: tuple[int, ...] = (4, 8, 12, 16, 20)
MCP_INDICES: tuple[int, ...] = (2, 5, 9, 13, 17)
PALM_INDICES: tuple[int, ...] = (0, 5, 9, 13, 17)

PAIRWISE_DISTANCE_INDICES: tuple[tuple[int, int], ...] = (
    (4, 8),
    (4, 12),
    (4, 16),
    (4, 20),
    (8, 12),
    (8, 16),
    (8, 20),
    (12, 16),
    (12, 20),
    (16, 20),
    (5, 17),
    (0, 9),
)


@dataclass(slots=True)
class FeatureConfig:
    """Controls the hand-shape vector used by the recognizer.

    The defaults favor "same hand shape anywhere in the camera frame". Raw
    camera-space landmark streams should still be sent to Max/MSP separately
    for continuous theremin-style control.
    """

    origin: str = "wrist"
    include_z: bool = True
    include_normalized_points: bool = True
    include_pairwise_distances: bool = True
    include_joint_angles: bool = True
    mirror_left_hand: bool = True
    rotation_invariant_xy: bool = False
    l2_normalize: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "FeatureConfig":
        if not data:
            return cls()
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def coerce_landmarks(landmarks: Sequence[Any]) -> list[Point3]:
    """Accept MediaPipe landmark objects or plain x/y/z sequences."""

    if len(landmarks) != 21:
        raise ValueError(f"expected 21 MediaPipe hand landmarks, got {len(landmarks)}")

    points: list[Point3] = []
    for landmark in landmarks:
        if hasattr(landmark, "x") and hasattr(landmark, "y"):
            x = float(landmark.x)
            y = float(landmark.y)
            z = float(getattr(landmark, "z", 0.0))
        else:
            values = list(landmark)
            if len(values) < 2:
                raise ValueError("each landmark must have at least x and y")
            x = float(values[0])
            y = float(values[1])
            z = float(values[2]) if len(values) > 2 else 0.0
        points.append((x, y, z))
    return points


def normalize_landmarks(
    landmarks: Sequence[Any],
    config: FeatureConfig | None = None,
    handedness: str | None = None,
) -> list[Point3]:
    """Translate and scale landmarks so frame position does not affect matching."""

    cfg = config or FeatureConfig()
    points = coerce_landmarks(landmarks)

    if cfg.origin == "wrist":
        origin = points[0]
    elif cfg.origin == "palm_center":
        origin = _point_centroid(points, PALM_INDICES)
    else:
        raise ValueError(f"unsupported feature origin: {cfg.origin}")

    translated = [_sub(point, origin) for point in points]
    scale = _hand_scale(points)
    normalized = [(x / scale, y / scale, z / scale) for x, y, z in translated]

    if cfg.mirror_left_hand and handedness and handedness.lower().startswith("left"):
        normalized = [(-x, y, z) for x, y, z in normalized]

    if cfg.rotation_invariant_xy:
        normalized = _align_xy_axis(normalized, 9)

    if not cfg.include_z:
        normalized = [(x, y, 0.0) for x, y, _ in normalized]

    return normalized


def extract_features(
    landmarks: Sequence[Any],
    config: FeatureConfig | None = None,
    handedness: str | None = None,
) -> list[float]:
    """Create a compact feature vector from one landmark frame."""

    cfg = config or FeatureConfig()
    if len(landmarks) == 42:
        right_features = _extract_single_hand_features(landmarks[:21], cfg, "Right")
        left_features = _extract_single_hand_features(landmarks[21:], cfg, "Left")
        combined = right_features + left_features
        return _l2_normalize(combined) if cfg.l2_normalize else combined

    return _extract_single_hand_features(landmarks, cfg, handedness)


def _extract_single_hand_features(
    landmarks: Sequence[Any],
    cfg: FeatureConfig,
    handedness: str | None,
) -> list[float]:
    points = normalize_landmarks(landmarks, cfg, handedness)
    features: list[float] = []

    if cfg.include_normalized_points:
        for x, y, z in points:
            features.extend((x, y))
            if cfg.include_z:
                features.append(z)

    if cfg.include_pairwise_distances:
        palm_center = _point_centroid(points, PALM_INDICES)
        for first, second in PAIRWISE_DISTANCE_INDICES:
            features.append(_distance(points[first], points[second]))
        for index in TIP_INDICES:
            features.append(_distance(points[index], points[0]))
            features.append(_distance(points[index], palm_center))
        for tip, mcp in zip(TIP_INDICES, MCP_INDICES, strict=True):
            features.append(_distance(points[tip], points[mcp]))

    if cfg.include_joint_angles:
        for base, lower, upper, tip in FINGER_CHAINS:
            features.append(_joint_angle(points[base], points[lower], points[upper]))
            features.append(_joint_angle(points[lower], points[upper], points[tip]))

    return _l2_normalize(features) if cfg.l2_normalize else features


def _hand_scale(points: Sequence[Point3]) -> float:
    distances = [
        _distance(points[0], points[9]),
        _distance(points[5], points[17]),
        _distance(points[0], points[5]),
        _distance(points[0], points[17]),
    ]
    usable = [value for value in distances if value > 1e-6]
    return median(usable) if usable else 1.0


def _align_xy_axis(points: Sequence[Point3], landmark_index: int) -> list[Point3]:
    x, y, _ = points[landmark_index]
    if abs(x) < 1e-9 and abs(y) < 1e-9:
        return list(points)
    current = math.atan2(y, x)
    target = math.pi / 2.0
    theta = target - current
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    aligned = []
    for px, py, pz in points:
        aligned.append((px * cos_t - py * sin_t, px * sin_t + py * cos_t, pz))
    return aligned


def _joint_angle(a: Point3, b: Point3, c: Point3) -> float:
    ba = _sub(a, b)
    bc = _sub(c, b)
    denom = _norm(ba) * _norm(bc)
    if denom < 1e-9:
        return 0.0
    cosine = max(-1.0, min(1.0, _dot(ba, bc) / denom))
    return math.acos(cosine) / math.pi


def _l2_normalize(values: Iterable[float]) -> list[float]:
    vector = [float(value) for value in values]
    norm = math.sqrt(sum(value * value for value in vector))
    if norm < 1e-12:
        return vector
    return [value / norm for value in vector]


def _point_centroid(points: Sequence[Point3], indices: Sequence[int]) -> Point3:
    count = float(len(indices))
    return (
        sum(points[index][0] for index in indices) / count,
        sum(points[index][1] for index in indices) / count,
        sum(points[index][2] for index in indices) / count,
    )


def _distance(a: Point3, b: Point3) -> float:
    return _norm(_sub(a, b))


def _sub(a: Point3, b: Point3) -> Point3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a: Point3, b: Point3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(point: Point3) -> float:
    return math.sqrt(point[0] * point[0] + point[1] * point[1] + point[2] * point[2])


COLOR_PALETTE = (
    "#00D1FF",
    "#FFB000",
    "#FF4FA3",
    "#35D07F",
    "#A88CFF",
    "#FF6B4A",
    "#46E6B2",
    "#F4D35E",
    "#3A86FF",
    "#C77DFF",
    "#EF476F",
    "#8AC926",
)


@dataclass(frozen=True, slots=True)
class LabelStyle:
    label: str
    display_label: str
    color: str


def generated_gesture_labels(count: int, start_index: int = 1) -> list[str]:
    # Internal labels are lowercase/underscore-safe because they become OSC paths.
    if count < 1:
        raise ValueError("gesture count must be at least 1")
    if start_index < 1:
        raise ValueError("gesture start index must be at least 1")
    return [
        f"gesture_{index}"
        for index in range(start_index, start_index + count)
    ]


def label_style(
    label: str,
    metadata: dict[str, Any] | None = None,
    index: int | None = None,
) -> LabelStyle:
    values = metadata or {}
    # Manifest metadata wins so colors/display names stay stable across sessions.
    fallback_color = default_color_hex(label, index)
    return LabelStyle(
        label=label,
        display_label=str(values.get("display_label") or default_display_label(label)),
        color=_normalize_color_hex(values.get("color"), fallback_color),
    )


def default_display_label(label: str) -> str:
    gesture_number = _gesture_number(label)
    if gesture_number is not None:
        return f"Gesture {gesture_number}"
    return label


def default_color_hex(label: str, index: int | None = None) -> str:
    gesture_number = _gesture_number(label)
    if gesture_number is not None:
        # Numbered gestures keep their color even if enrolled in separate sessions.
        return COLOR_PALETTE[(gesture_number - 1) % len(COLOR_PALETTE)]

    if index is not None:
        return COLOR_PALETTE[index % len(COLOR_PALETTE)]

    # Custom labels get a deterministic palette slot instead of a session-random color.
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    return COLOR_PALETTE[digest[0] % len(COLOR_PALETTE)]


def bgr_from_hex(color: str) -> tuple[int, int, int]:
    normalized = _normalize_color_hex(color, COLOR_PALETTE[0])
    red = int(normalized[1:3], 16)
    green = int(normalized[3:5], 16)
    blue = int(normalized[5:7], 16)
    return (blue, green, red)


def _normalize_color_hex(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if (
        len(text) == 7
        and text.startswith("#")
        and all(char in "0123456789abcdefABCDEF" for char in text[1:])
    ):
        return f"#{text[1:].upper()}"
    return fallback


def _gesture_number(label: str) -> int | None:
    prefix = "gesture_"
    if not label.startswith(prefix):
        return None
    suffix = label[len(prefix):]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _label_sort_key(label: str) -> tuple[int, int | str, str]:
    gesture_number = _gesture_number(label)
    if gesture_number is not None:
        return (0, gesture_number, label)
    return (1, label.lower(), label)


@dataclass(slots=True)
class RecognitionConfig:
    k: int = 3
    min_vote_confidence: float = 0.55
    fallback_distance_threshold: float = 0.38
    min_label_distance_threshold: float = 0.22
    max_label_distance_threshold: float = 0.65
    threshold_stddevs: float = 2.5

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "RecognitionConfig":
        if not data:
            return cls()
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in allowed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GestureSample:
    label: str
    features: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "features": self.features,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GestureSample":
        return cls(
            label=str(data["label"]),
            features=[float(value) for value in data["features"]],
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class Prediction:
    label: str | None
    accepted: bool
    distance: float
    confidence: float
    vote_confidence: float
    distance_confidence: float
    threshold: float
    votes: dict[str, float]

    @property
    def is_known(self) -> bool:
        return self.label is not None and self.accepted


class GestureModel:
    """A user-trained KNN recognizer over normalized hand-shape features."""

    version = 2

    def __init__(
        self,
        feature_config: FeatureConfig | None = None,
        recognition_config: RecognitionConfig | None = None,
        samples: Sequence[GestureSample] | None = None,
        thresholds: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
        label_metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.feature_config = feature_config or FeatureConfig()
        self.recognition_config = recognition_config or RecognitionConfig()
        self.samples: list[GestureSample] = list(samples or [])
        self.thresholds: dict[str, float] = dict(thresholds or {})
        self.metadata: dict[str, Any] = {
            "format": "pose2osc_manifest",
            "created_at": _utc_now(),
            **(metadata or {}),
        }
        self.label_metadata: dict[str, dict[str, Any]] = {
            str(label): dict(values)
            for label, values in (label_metadata or {}).items()
        }
        if self.samples and not self.thresholds:
            self.fit_thresholds()

    @property
    def labels(self) -> list[str]:
        return sorted({sample.label for sample in self.samples}, key=_label_sort_key)

    def add_sample(
        self,
        label: str,
        landmarks: Sequence[Any],
        handedness: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GestureSample:
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("gesture label cannot be empty")
        hand_mode = _normalize_hand_mode(handedness)
        sample = GestureSample(
            label=clean_label,
            features=extract_features(landmarks, self.feature_config, hand_mode),
            metadata={
                "created_at": datetime.now(timezone.utc).isoformat(),
                "hand_mode": hand_mode,
                **(metadata or {}),
            },
        )
        self.samples.append(sample)
        self._update_label_metadata(clean_label, hand_mode, metadata)
        self.fit_thresholds()
        return sample

    def add_samples(
        self,
        label: str,
        frames: Sequence[Sequence[Any]],
        handedness: str | None = None,
        metadata: dict[str, Any] | None = None,
        max_samples: int | None = 64,
    ) -> int:
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("gesture label cannot be empty")
        hand_mode = _normalize_hand_mode(handedness)
        selected_frames = _uniform_sample(frames, max_samples)
        for index, frame in enumerate(selected_frames):
            frame_metadata = {
                "frame_index": index,
                "source": "enrollment",
                "handedness": hand_mode,
                "hand_mode": hand_mode,
                **(metadata or {}),
            }
            self.samples.append(
                GestureSample(
                    label=clean_label,
                    features=extract_features(frame, self.feature_config, hand_mode),
                    metadata={
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        **frame_metadata,
                    },
                )
            )
        self._update_label_metadata(clean_label, hand_mode, metadata)
        self.fit_thresholds()
        return len(selected_frames)

    def remove_label(self, label: str) -> int:
        before = len(self.samples)
        self.samples = [sample for sample in self.samples if sample.label != label]
        self.thresholds.pop(label, None)
        self.label_metadata.pop(label, None)
        self.fit_thresholds()
        return before - len(self.samples)

    def predict(self, landmarks: Sequence[Any], handedness: str | None = None) -> Prediction:
        if not self.samples:
            return Prediction(
                label=None,
                accepted=False,
                distance=math.inf,
                confidence=0.0,
                vote_confidence=0.0,
                distance_confidence=0.0,
                threshold=self.recognition_config.fallback_distance_threshold,
                votes={},
            )

        hand_mode = _normalize_hand_mode(handedness)
        vector = extract_features(landmarks, self.feature_config, hand_mode)
        compatible_samples = [
            sample for sample in self.samples
            if _sample_is_compatible(sample, vector, hand_mode)
        ]
        if not compatible_samples:
            return Prediction(
                label=None,
                accepted=False,
                distance=math.inf,
                confidence=0.0,
                vote_confidence=0.0,
                distance_confidence=0.0,
                threshold=self.recognition_config.fallback_distance_threshold,
                votes={},
            )

        neighbors = sorted(
            ((_euclidean(vector, sample.features), sample) for sample in compatible_samples),
            key=lambda item: item[0],
        )
        k = max(1, min(self.recognition_config.k, len(neighbors)))
        nearest = neighbors[:k]

        votes: dict[str, float] = {}
        best_distance_by_label: dict[str, float] = {}
        for distance, sample in nearest:
            votes[sample.label] = votes.get(sample.label, 0.0) + 1.0 / max(distance, 1e-9)
            best_distance_by_label[sample.label] = min(
                best_distance_by_label.get(sample.label, math.inf),
                distance,
            )

        label = max(votes.items(), key=lambda item: item[1])[0]
        total_vote = sum(votes.values())
        vote_confidence = votes[label] / total_vote if total_vote > 0.0 else 0.0
        distance = best_distance_by_label[label]
        threshold = self.thresholds.get(
            label,
            self.recognition_config.fallback_distance_threshold,
        )
        distance_confidence = math.exp(-((distance / max(threshold, 1e-9)) ** 2))
        confidence = vote_confidence * distance_confidence
        accepted = (
            distance <= threshold
            and vote_confidence >= self.recognition_config.min_vote_confidence
        )

        return Prediction(
            label=label if accepted else None,
            accepted=accepted,
            distance=distance,
            confidence=confidence,
            vote_confidence=vote_confidence,
            distance_confidence=distance_confidence,
            threshold=threshold,
            votes=votes,
        )

    def fit_thresholds(self) -> None:
        by_label: dict[str, list[list[float]]] = {}
        for sample in self.samples:
            by_label.setdefault(sample.label, []).append(sample.features)

        thresholds: dict[str, float] = {}
        cfg = self.recognition_config
        for label, vectors in by_label.items():
            group_thresholds = [
                _fit_threshold_for_vectors(group, cfg)
                for group in _group_vectors_by_width(vectors).values()
            ]
            if not group_thresholds:
                thresholds[label] = cfg.fallback_distance_threshold
                continue
            thresholds[label] = max(group_thresholds)
        self.thresholds = thresholds

    def save(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.metadata["updated_at"] = _utc_now()
        output.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "GestureModel":
        data = json.loads(Path(path).read_text())
        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "pose2osc_manifest",
            "version": self.version,
            "metadata": self.metadata,
            "label_metadata": self.label_metadata,
            "feature_config": self.feature_config.to_dict(),
            "recognition_config": self.recognition_config.to_dict(),
            "thresholds": self.thresholds,
            "samples": [sample.to_dict() for sample in self.samples],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GestureModel":
        return cls(
            feature_config=FeatureConfig.from_dict(data.get("feature_config")),
            recognition_config=RecognitionConfig.from_dict(data.get("recognition_config")),
            samples=[GestureSample.from_dict(item) for item in data.get("samples", [])],
            thresholds={
                str(label): float(value)
                for label, value in data.get("thresholds", {}).items()
            },
            metadata=dict(data.get("metadata", {})),
            label_metadata={
                str(label): dict(values)
                for label, values in data.get("label_metadata", {}).items()
            },
        )

    def _update_label_metadata(
        self,
        label: str,
        handedness: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        existing = self.label_metadata.setdefault(label, {})
        label_level_metadata = {
            key: value for key, value in (metadata or {}).items()
            if key not in {
                "capture_mode",
                "capture_count",
                "capture_frames",
                "capture_seconds",
                "hand_mode",
                "handedness",
            }
        }
        existing.update(label_level_metadata)
        if handedness:
            existing["handedness"] = handedness
            existing["last_hand_mode"] = handedness
        label_samples = [
            sample for sample in self.samples
            if sample.label == label
        ]
        existing["hand_modes"] = _hand_mode_counts(
            label_samples
        )
        capture_ids = {
            sample.metadata.get("capture_count")
            for sample in label_samples
            if sample.metadata.get("capture_count") is not None
        }
        if capture_ids:
            existing["capture_count"] = len(capture_ids)
        existing["sample_count"] = len(label_samples)
        existing["updated_at"] = _utc_now()


@dataclass(slots=True)
class StateConfig:
    enter_frames: int = 1
    exit_frames: int = 1
    switch_frames: int = 1


@dataclass(slots=True)
class StateUpdate:
    active_label: str | None
    previous_label: str | None
    event: str
    prediction: Prediction
    active: bool


class GestureStateTracker:
    """Turns one-frame predictions into enter/hold/exit events.

    Defaults are intentionally immediate for performance instruments. Raising
    exit_frames to 2 or 3 can soften dropouts without adding entry latency.
    """

    def __init__(self, config: StateConfig | None = None) -> None:
        self.config = config or StateConfig()
        self.active_label: str | None = None
        self.candidate_label: str | None = None
        self.candidate_count = 0
        self.exit_count = 0

    def update(self, prediction: Prediction) -> StateUpdate:
        if prediction.accepted and prediction.label:
            self.exit_count = 0
            label = prediction.label
            if self.active_label == label:
                self.candidate_label = None
                self.candidate_count = 0
                return StateUpdate(label, None, "hold", prediction, True)

            if self.candidate_label == label:
                self.candidate_count += 1
            else:
                self.candidate_label = label
                self.candidate_count = 1

            required = (
                self.config.switch_frames
                if self.active_label is not None
                else self.config.enter_frames
            )
            if self.candidate_count >= max(1, required):
                previous = self.active_label
                self.active_label = label
                self.candidate_label = None
                self.candidate_count = 0
                event = "switch" if previous is not None else "enter"
                return StateUpdate(label, previous, event, prediction, True)

            return StateUpdate(
                self.active_label,
                None,
                "pending",
                prediction,
                self.active_label is not None,
            )

        self.candidate_label = None
        self.candidate_count = 0
        if self.active_label is None:
            self.exit_count = 0
            return StateUpdate(None, None, "none", prediction, False)

        self.exit_count += 1
        if self.exit_count >= max(1, self.config.exit_frames):
            exited = self.active_label
            self.active_label = None
            self.exit_count = 0
            return StateUpdate(None, exited, "exit", prediction, False)

        return StateUpdate(self.active_label, None, "hold", prediction, True)


def _uniform_sample(
    frames: Sequence[Sequence[Any]],
    max_samples: int | None,
) -> list[Sequence[Any]]:
    if max_samples is None or max_samples <= 0 or len(frames) <= max_samples:
        return list(frames)
    if max_samples == 1:
        return [frames[len(frames) // 2]]
    step = (len(frames) - 1) / float(max_samples - 1)
    return [frames[round(index * step)] for index in range(max_samples)]


def _vector_centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    width = len(vectors[0])
    return [sum(vector[index] for vector in vectors) / len(vectors) for index in range(width)]


def _group_vectors_by_width(vectors: Sequence[Sequence[float]]) -> dict[int, list[Sequence[float]]]:
    by_width: dict[int, list[Sequence[float]]] = {}
    for vector in vectors:
        by_width.setdefault(len(vector), []).append(vector)
    return by_width


def _fit_threshold_for_vectors(
    vectors: Sequence[Sequence[float]],
    cfg: RecognitionConfig,
) -> float:
    if len(vectors) < 2:
        return cfg.fallback_distance_threshold
    centroid = _vector_centroid(vectors)
    distances = [_euclidean(vector, centroid) for vector in vectors]
    fitted = mean(distances) + pstdev(distances) * cfg.threshold_stddevs
    return min(
        cfg.max_label_distance_threshold,
        max(cfg.min_label_distance_threshold, fitted),
    )


def _euclidean(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"feature length mismatch: {len(a)} != {len(b)}")
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def _sample_is_compatible(sample: GestureSample, vector: Sequence[float], hand_mode: str | None) -> bool:
    if len(sample.features) != len(vector):
        return False
    sample_mode = _normalize_hand_mode(
        sample.metadata.get("hand_mode")
        or sample.metadata.get("handedness")
    )
    if not sample_mode or not hand_mode:
        return True
    return sample_mode == hand_mode


def _hand_mode_counts(samples: Iterable[GestureSample]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        mode = _normalize_hand_mode(
            sample.metadata.get("hand_mode")
            or sample.metadata.get("handedness")
        ) or "Unknown"
        counts[mode] = counts.get(mode, 0) + 1
    return counts


def _normalize_hand_mode(handedness: Any) -> str | None:
    if handedness is None:
        return None
    value = str(handedness).strip().lower()
    if not value:
        return None
    if value in {"right", "r"}:
        return "Right"
    if value in {"left", "l"}:
        return "Left"
    if value in {"both", "two", "2"}:
        return "Both"
    if value in {"any", "auto"}:
        return None
    return str(handedness)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
