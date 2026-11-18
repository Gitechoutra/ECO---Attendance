"""Download the OpenCV Zoo face models used for attendance verification.

Usage (from backend/):  .venv\\Scripts\\python -m scripts.download_models
Models: YuNet face detector (MIT) and SFace recognizer (Apache-2.0) from github.com/opencv/opencv_zoo.
"""
import sys
import urllib.request
from pathlib import Path

from app.core.config import settings

MODELS = {
    "face_detection_yunet_2023mar.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
    "face_recognition_sface_2021dec.onnx":
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
}
MIN_SIZE = {"face_detection_yunet_2023mar.onnx": 200_000, "face_recognition_sface_2021dec.onnx": 30_000_000}


def main() -> int:
    root = Path(settings.FACE_MODELS_PATH)
    root.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.items():
        target = root / name
        if target.exists() and target.stat().st_size >= MIN_SIZE[name]:
            print(f"[ok] {name} already present")
            continue
        print(f"[..] downloading {name} ...")
        urllib.request.urlretrieve(url, target)
        if target.stat().st_size < MIN_SIZE[name]:
            target.unlink()
            print(f"[error] {name} download looks incomplete (Git LFS pointer?). Download it manually from {url}")
            return 1
        print(f"[ok] {name} ({target.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
