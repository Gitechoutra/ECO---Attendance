"""Face detection, embedding and challenge–response liveness verification.

Models: OpenCV Zoo YuNet (detection + 5 landmarks) and SFace (128-d embeddings), loaded from FACE_MODELS_PATH.

Liveness (presentation-attack resistance) is challenge–response:
  * the server issues a random head-pose sequence plus a single-use nonce that expires in 90 s;
  * the browser captures a burst of live camera frames while prompting the user (no file picker);
  * the server requires: exactly one face per frame, consistent identity across frames, the requested
    pose changes in the requested order, real inter-frame motion, and a plausible capture duration.
This defeats static photos and pre-recorded videos that cannot follow a random sequence. It is not a
certified ISO 30107-3 PAD system; see docs/SECURITY.md for limitations.
"""
import base64
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from app.core.config import settings

DETECTOR_FILE = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_FILE = "face_recognition_sface_2021dec.onnx"

YAW_TURN = 0.17       # |yaw| above this counts as a turn
YAW_CENTER = 0.08     # |yaw| below this counts as facing the camera
MIN_FRAMES, MAX_FRAMES = 6, 24
MIN_FACE_PX = 70


class FaceError(Exception):
    """User-facing verification failure."""


@dataclass
class FrameAnalysis:
    embedding: np.ndarray
    yaw: float
    score: float
    box: tuple
    gray_small: np.ndarray


class FaceEngine:
    _lock = threading.Lock()
    _instance = None

    def __init__(self):
        root = Path(settings.FACE_MODELS_PATH)
        det, rec = root / DETECTOR_FILE, root / RECOGNIZER_FILE
        if not det.exists() or not rec.exists():
            raise FaceError("Face recognition models are not installed. Run scripts/download_models.py.")
        self.detector = cv2.FaceDetectorYN.create(str(det), "", (320, 320), 0.8, 0.3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(rec), "")
        self._mutex = threading.Lock()

    @classmethod
    def get(cls) -> "FaceEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = FaceEngine()
            return cls._instance

    def analyze(self, img: np.ndarray) -> FrameAnalysis:
        h, w = img.shape[:2]
        with self._mutex:  # OpenCV DNN objects are not thread-safe
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(img)
            if faces is None or len(faces) == 0:
                raise FaceError("No face detected. Make sure your face is well lit and fully visible.")
            strong = [f for f in faces if f[-1] >= 0.85]
            if len(strong) > 1:
                raise FaceError("More than one face detected. Only the employee should be in frame.")
            face = max(faces, key=lambda f: f[-1])
            if face[2] < MIN_FACE_PX or face[3] < MIN_FACE_PX:
                raise FaceError("Face is too far from the camera. Move closer.")
            aligned = self.recognizer.alignCrop(img, face)
            feat = self.recognizer.feature(aligned).flatten().astype(np.float32)
        feat /= np.linalg.norm(feat) + 1e-9
        re, le, nose = face[4:6], face[6:8], face[8:10]
        eye_mid_x = (re[0] + le[0]) / 2
        eye_dist = abs(le[0] - re[0]) + 1e-6
        yaw = float((nose[0] - eye_mid_x) / eye_dist)  # >0: user turned to THEIR left (unmirrored camera frame)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        x, y, fw, fh = [int(v) for v in face[:4]]
        return FrameAnalysis(feat, yaw, float(face[-1]), (x, y, fw, fh), cv2.resize(gray, (64, 48)))


def decode_frame(data_url: str) -> np.ndarray:
    try:
        b64 = data_url.split(",", 1)[1] if data_url.startswith("data:") else data_url
        raw = base64.b64decode(b64, validate=False)
        if len(raw) > 2_500_000:
            raise FaceError("Frame too large")
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    except FaceError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FaceError("Invalid camera frame") from exc
    if img is None:
        raise FaceError("Invalid camera frame")
    return img


def pose_state(yaw: float) -> str | None:
    if yaw > YAW_TURN:
        return "left"
    if yaw < -YAW_TURN:
        return "right"
    if abs(yaw) < YAW_CENTER:
        return "center"
    return None


def follows_sequence(yaws: list[float], steps: list[str]) -> bool:
    """True if the observed pose states contain `steps` as an ordered subsequence."""
    observed = []
    for y in yaws:
        s = pose_state(y)
        if s and (not observed or observed[-1] != s):
            observed.append(s)
    i = 0
    for s in observed:
        if i < len(steps) and s == steps[i]:
            i += 1
    return i == len(steps)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / ((np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9))


def check_liveness(analyses: list[FrameAnalysis], steps: list[str], timestamps: list[float]) -> dict:
    if len(analyses) < MIN_FRAMES:
        raise FaceError("Not enough frames captured. Please retry.")
    span = (max(timestamps) - min(timestamps)) / 1000.0 if timestamps else 0
    if span < 1.2 or span > 40:
        raise FaceError("Capture timing was invalid. Please retry the live check.")
    if any(b <= a for a, b in zip(timestamps, timestamps[1:])):
        raise FaceError("Capture timing was invalid. Please retry the live check.")

    ref = analyses[0].embedding
    consistency = min(cosine(ref, a.embedding) for a in analyses[1:])
    if consistency < 0.45:
        raise FaceError("Different faces were detected during capture.")

    diffs = [float(np.mean(cv2.absdiff(a.gray_small, b.gray_small))) for a, b in zip(analyses, analyses[1:])]
    moving = sum(1 for d in diffs if d > 1.5)
    if moving < max(2, len(diffs) // 3):
        raise FaceError("No natural movement detected. Static images are not accepted.")

    yaws = [a.yaw for a in analyses]
    if max(yaws) - min(yaws) < 0.3:
        raise FaceError("Head movement was not detected. Follow the on-screen prompts.")
    if not follows_sequence(yaws, steps):
        raise FaceError("The requested head movements were not completed in order. Please retry.")
    return {"frames": len(analyses), "yaw_range": round(max(yaws) - min(yaws), 3),
            "consistency": round(consistency, 3), "duration_s": round(span, 2)}


def analyze_frames(frames: list[str]) -> list[FrameAnalysis]:
    if not frames or len(frames) > MAX_FRAMES:
        raise FaceError(f"Between {MIN_FRAMES} and {MAX_FRAMES} frames are required.")
    engine = FaceEngine.get()
    out = []
    failures = 0
    for f in frames:
        try:
            out.append(engine.analyze(decode_frame(f)))
        except FaceError as e:
            failures += 1
            if "More than one face" in str(e):
                raise
            if failures > len(frames) // 3:
                raise
    return out


def embedding_to_bytes(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def bytes_to_embedding(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


def mean_embedding(analyses: list[FrameAnalysis]) -> np.ndarray:
    m = np.mean([a.embedding for a in analyses], axis=0)
    return m / (np.linalg.norm(m) + 1e-9)


def match_score(analyses: list[FrameAnalysis], enrolled: np.ndarray) -> tuple[float, float]:
    sims = [cosine(a.embedding, enrolled) for a in analyses]
    return float(np.median(sims)), float(min(sims))
