import os
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
REFERENCE_AUDIO_PATH = Path(os.environ.get("REFERENCE_AUDIO_PATH", INPUT_DIR / "reference.wav"))
GENERATED_AUDIO_PATH = Path(os.environ.get("GENERATED_AUDIO_PATH", INPUT_DIR / "generated.wav"))

BBOX_SHIFT = os.environ.get("BBOX_SHIFT")
RESULT_DIR = Path(os.environ.get("RESULT_DIR", OUTPUT_DIR / "musetalk"))
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "/usr/bin/ffmpeg")

UNET_MODEL_PATH = Path(os.environ.get("UNET_MODEL_PATH", "/models/musetalkV15/unet.pth"))
UNET_CONFIG = Path(os.environ.get("UNET_CONFIG", "/models/musetalkV15/musetalk.json"))
VERSION = os.environ.get("MUSETALK_VERSION", "v15")

DUMMY_TTS_PYTHON = os.environ.get("DUMMY_TTS_PYTHON", "python")
DUMMY_TTS_LANGUAGE = os.environ.get("DUMMY_TTS_LANGUAGE", "en")
DUMMY_TTS_MODEL = os.environ.get("DUMMY_TTS_MODEL", "/models/cosyvoice/Fun-CosyVoice3-0.5B-2512")
DUMMY_TTS_SPEED = os.environ.get("DUMMY_TTS_SPEED", "1.0")

WHISPER_MODEL_PATH = os.environ.get("WHISPER_MODEL_PATH", "/models/faster-whisper-base")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")

REFERENCE_MAX_SECONDS = float(os.environ.get("REFERENCE_MAX_SECONDS", "18"))
TEXT_STYLE = os.environ.get("TEXT_STYLE", "confident")
SOURCE_TEXT = os.environ.get("SOURCE_TEXT", os.environ.get("DUMMY_TEXT", "")).strip()


def require_file(path: Path, description: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{description} does not exist: {path}")


def resolve_cosyvoice_model_dir() -> Path:
    configured = Path(DUMMY_TTS_MODEL)
    if (configured / "cosyvoice3.yaml").exists():
        return configured

    models_root = Path("/models")
    candidates = sorted(models_root.rglob("cosyvoice3.yaml")) if models_root.exists() else []
    if candidates:
        discovered = candidates[0].parent
        print(f"Configured CosyVoice3 model dir missing config; using discovered dir: {discovered}")
        return discovered

    raise FileNotFoundError(
        "CosyVoice3 config does not exist. "
        f"Checked configured path: {configured / 'cosyvoice3.yaml'} and no cosyvoice3.yaml found under /models"
    )


def run(command: list[str], cwd: Path | None = None) -> None:
    print("Running:", " ".join(command))
    subprocess.run(command, check=True, cwd=cwd)


def write_inference_config(audio_path: Path) -> None:
    task = {"video_path": str(VIDEO_PATH), "audio_path": str(audio_path)}
    if BBOX_SHIFT not in (None, ""):
        task["bbox_shift"] = int(BBOX_SHIFT)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        yaml.safe_dump({"task_0": task}, file, sort_keys=False)
    print(f"Wrote inference config: {CONFIG_PATH}")


def extract_audio_from_video(video_path: Path, audio_path: Path) -> None:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
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
        ]
    )


def trim_reference_audio(source_audio: Path, reference_audio: Path) -> None:
    reference_audio.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            FFMPEG_PATH,
            "-y",
            "-i",
            str(source_audio),
            "-t",
            str(REFERENCE_MAX_SECONDS),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(reference_audio),
        ]
    )


def transcribe_audio(audio_path: Path) -> str:
    require_file(audio_path, "Audio to transcribe")
    try:
        model = WhisperModel(
            WHISPER_MODEL_PATH,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        segments_iter, info = model.transcribe(str(audio_path), language=DUMMY_TTS_LANGUAGE)
        segments = list(segments_iter)
    except RuntimeError as exc:
        message = str(exc)
        if "libcublas.so.12" not in message:
            raise
        print(
            "Whisper CUDA runtime is unavailable (missing libcublas.so.12). "
            "Falling back to CPU int8 transcription."
        )
        model = WhisperModel(
            WHISPER_MODEL_PATH,
            device="cpu",
            compute_type="int8",
        )
        segments_iter, info = model.transcribe(str(audio_path), language=DUMMY_TTS_LANGUAGE)
        segments = list(segments_iter)
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
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
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    transformed = result.stdout.strip()
    if not transformed:
        raise ValueError("Text transform returned empty output")
    print(f"Transformed text ({TEXT_STYLE}): {transformed}")
    return transformed


def synthesize_audio(text: str, prompt_text: str, reference_audio: Path, model_dir: Path) -> Path:
    require_file(reference_audio, "Reference audio for CosyVoice3")
    run(
        [
            DUMMY_TTS_PYTHON,
            "/app/cosyvoice3_tts.py",
            "--text",
            text,
            "--output",
            str(GENERATED_AUDIO_PATH),
            "--reference-audio",
            str(reference_audio),
            "--prompt-text",
            prompt_text,
            "--model-dir",
            str(model_dir),
            "--speed",
            DUMMY_TTS_SPEED,
        ]
    )
    return GENERATED_AUDIO_PATH


def run_musetalk() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    run(
        [
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
        ],
        cwd=MUSETALK_HOME,
    )


def main() -> None:
    require_file(VIDEO_PATH, "Input video")
    require_file(UNET_MODEL_PATH, "MuseTalk V15 model")
    require_file(UNET_CONFIG, "MuseTalk V15 config")
    model_dir = resolve_cosyvoice_model_dir()

    extract_audio_from_video(VIDEO_PATH, AUDIO_PATH)
    trim_reference_audio(AUDIO_PATH, REFERENCE_AUDIO_PATH)

    full_transcript = transcribe_audio(AUDIO_PATH)
    sample_transcript = transcribe_audio(REFERENCE_AUDIO_PATH)
    source_text = SOURCE_TEXT or full_transcript
    transformed_text = transform_text(source_text)
    generated_audio = synthesize_audio(transformed_text, sample_transcript, REFERENCE_AUDIO_PATH, model_dir)
    write_inference_config(generated_audio)
    run_musetalk()


if __name__ == "__main__":
    main()
