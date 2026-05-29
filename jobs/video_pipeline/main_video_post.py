import os
import shlex
import subprocess
from pathlib import Path

import yaml
from faster_whisper import WhisperModel

MUSETALK_HOME = Path(os.environ.get("MUSETALK_HOME", "/opt/MuseTalk"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
INPUT_DIR = Path(os.environ.get("INPUT_DIR", DATA_DIR / "inputs"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", DATA_DIR / "outputs"))
CONFIG_PATH = Path(os.environ.get("INFERENCE_CONFIG", "/tmp/musetalk-inference.yaml"))

VIDEO_PATH = Path(os.environ.get("VIDEO_PATH", INPUT_DIR / "input.mp4"))
AUDIO_PATH = Path(os.environ.get("AUDIO_PATH", INPUT_DIR / "input.wav"))
GENERATED_AUDIO_PATH = Path(os.environ.get("GENERATED_AUDIO_PATH", INPUT_DIR / "generated.wav"))

BBOX_SHIFT = os.environ.get("BBOX_SHIFT")
RESULT_DIR = Path(os.environ.get("RESULT_DIR", OUTPUT_DIR / "musetalk"))
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "/usr/bin/ffmpeg")

UNET_MODEL_PATH = Path(os.environ.get("UNET_MODEL_PATH", "/models/musetalkV15/unet.pth"))
UNET_CONFIG = Path(os.environ.get("UNET_CONFIG", "/models/musetalkV15/musetalk.json"))
VERSION = os.environ.get("MUSETALK_VERSION", "v15")

DUMMY_TTS_PYTHON = os.environ.get("DUMMY_TTS_PYTHON", "python")
DUMMY_TTS_LANGUAGE = os.environ.get("DUMMY_TTS_LANGUAGE", "en")
WHISPER_MODEL_PATH = os.environ.get("WHISPER_MODEL_PATH", "/models/faster-whisper-base")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
TEXT_STYLE = os.environ.get("TEXT_STYLE", "confident")
TEXT_STYLE_VERBOSE = os.environ.get("TEXT_STYLE_VERBOSE", "1").strip().lower() not in {"0", "false", "no", "off"}
SOURCE_TEXT = os.environ.get("SOURCE_TEXT", os.environ.get("DUMMY_TEXT", "")).strip()
PIPELINE_STAGE = os.environ.get("PIPELINE_STAGE", "all").strip().lower()
TRANSFORMED_TEXT_PATH = Path(os.environ.get("TRANSFORMED_TEXT_PATH", INPUT_DIR / "transformed.txt"))


def require_file(path: Path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{description} does not exist: {path}")


def run(command: list[str], cwd: Path | None = None) -> None:
    print("Running:", " ".join(command))
    subprocess.run(command, check=True, cwd=cwd)


def extract_audio_from_video(video_path: Path, audio_path: Path) -> None:
    run([
        FFMPEG_PATH,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ])


def ensure_musetalk_video_input(video_path: Path) -> Path:
    if video_path.suffix.lower() == ".mp4":
        return video_path
    converted_path = video_path.with_suffix(".mp4")
    run([
        FFMPEG_PATH,
        "-y",
        "-i",
        str(video_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(converted_path),
    ])
    print(f"Converted input for MuseTalk: {video_path} -> {converted_path}")
    return converted_path


def transcribe_audio(audio_path: Path) -> str:
    require_file(audio_path, "Audio to transcribe")
    model = WhisperModel(WHISPER_MODEL_PATH, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    segments_iter, info = model.transcribe(str(audio_path), language=DUMMY_TTS_LANGUAGE)
    text = " ".join(segment.text.strip() for segment in segments_iter if segment.text.strip()).strip()
    if not text:
        raise ValueError(f"Whisper produced empty transcription for {audio_path}")
    print(f"Transcription ({audio_path.name}, lang={info.language}): {text}")
    return text


def transform_text(source_text: str) -> str:
    cmd = [
        DUMMY_TTS_PYTHON,
        "/app/text_style_transform.py",
        "--text",
        source_text,
        "--style",
        TEXT_STYLE,
    ]
    if TEXT_STYLE_VERBOSE:
        print(f"Text transform command: {shlex.join(cmd)}")
    env = os.environ.copy()
    env.update({"USE_TF": "0", "TRANSFORMERS_NO_TF": "1", "USE_FLAX": "0", "TRANSFORMERS_NO_FLAX": "1"})
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        if stderr:
            print(f"Text transform failed; using original text. stderr: {stderr}")
        return source_text.strip()

    transformed = result.stdout.strip()
    if not transformed:
        return source_text.strip()
    print(f"Transformed text ({TEXT_STYLE}): {transformed}")
    return transformed


def write_inference_config(video_path: Path, audio_path: Path) -> None:
    task = {"video_path": str(video_path), "audio_path": str(audio_path)}
    if BBOX_SHIFT not in (None, ""):
        task["bbox_shift"] = int(BBOX_SHIFT)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        yaml.safe_dump({"task_0": task}, file, sort_keys=False)


def run_musetalk() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    run([
        "python",
        "-m",
        "scripts.inference",
        "--inference_config",
        str(CONFIG_PATH),
        "--result_dir",
        str(RESULT_DIR),
        "--unet_model_path",
        str(UNET_MODEL_PATH),
        "--unet_config",
        str(UNET_CONFIG),
        "--version",
        VERSION,
        "--ffmpeg_path",
        FFMPEG_PATH,
    ], cwd=MUSETALK_HOME)


def main() -> None:
    require_file(VIDEO_PATH, "Input video")
    if PIPELINE_STAGE in {"transform", "all"}:
        extract_audio_from_video(VIDEO_PATH, AUDIO_PATH)
        full_transcript = transcribe_audio(AUDIO_PATH)
        source_text = SOURCE_TEXT or full_transcript
        transformed = transform_text(source_text)
        TRANSFORMED_TEXT_PATH.write_text(transformed, encoding="utf-8")
        print(f"Wrote transformed text: {TRANSFORMED_TEXT_PATH}")

    if PIPELINE_STAGE in {"musetalk", "all"}:
        require_file(UNET_MODEL_PATH, "MuseTalk V15 model")
        require_file(UNET_CONFIG, "MuseTalk V15 config")
        require_file(GENERATED_AUDIO_PATH, "Generated audio from CosyVoice step")
        musetalk_video = ensure_musetalk_video_input(VIDEO_PATH)
        write_inference_config(musetalk_video, GENERATED_AUDIO_PATH)
        run_musetalk()


if __name__ == "__main__":
    main()
