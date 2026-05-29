import os
import subprocess
import sys
from pathlib import Path

from faster_whisper import WhisperModel

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
INPUT_DIR = Path(os.environ.get("INPUT_DIR", DATA_DIR / "inputs"))
VIDEO_PATH = Path(os.environ.get("VIDEO_PATH", INPUT_DIR / "input.mp4"))
AUDIO_PATH = Path(os.environ.get("AUDIO_PATH", INPUT_DIR / "input.wav"))
REFERENCE_AUDIO_PATH = Path(os.environ.get("REFERENCE_AUDIO_PATH", INPUT_DIR / "reference.wav"))
GENERATED_AUDIO_PATH = Path(os.environ.get("GENERATED_AUDIO_PATH", INPUT_DIR / "generated.wav"))

FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "/usr/bin/ffmpeg")
DUMMY_TTS_PYTHON = os.environ.get("DUMMY_TTS_PYTHON", "python")
DUMMY_TTS_LANGUAGE = os.environ.get("DUMMY_TTS_LANGUAGE", "en")
DUMMY_TTS_MODEL = os.environ.get("DUMMY_TTS_MODEL", "/models/cosyvoice/Fun-CosyVoice3-0.5B-2512")
DUMMY_TTS_SPEED = os.environ.get("DUMMY_TTS_SPEED", "1.0")
WHISPER_MODEL_PATH = os.environ.get("WHISPER_MODEL_PATH", "/models/faster-whisper-base")
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "auto")
REFERENCE_MAX_SECONDS = float(os.environ.get("REFERENCE_MAX_SECONDS", "18"))
SOURCE_TEXT = os.environ.get("SOURCE_TEXT", os.environ.get("DUMMY_TEXT", "")).strip()
TRANSFORMED_TEXT_PATH = Path(os.environ.get("TRANSFORMED_TEXT_PATH", INPUT_DIR / "transformed.txt"))


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


def run(command: list[str]) -> None:
    print("Running:", " ".join(command))
    subprocess.run(command, check=True)


def log_runtime_versions() -> None:
    print(f"Python version: {sys.version.split()[0]}")
    try:
        import torch  # type: ignore

        print(f"Torch version: {torch.__version__} (cuda={torch.version.cuda})")
    except Exception as exc:
        print(f"Torch import failed: {exc}")
    try:
        import torchaudio  # type: ignore

        print(f"Torchaudio version: {torchaudio.__version__}")
    except Exception as exc:
        print(f"Torchaudio import failed: {exc}")


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


def trim_reference_audio(source_audio: Path, reference_audio: Path) -> None:
    run([
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
    ])


def transcribe_audio(audio_path: Path) -> str:
    require_file(audio_path, "Audio to transcribe")
    model = WhisperModel(WHISPER_MODEL_PATH, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    segments_iter, info = model.transcribe(str(audio_path), language=DUMMY_TTS_LANGUAGE)
    text = " ".join(segment.text.strip() for segment in segments_iter if segment.text.strip()).strip()
    if not text:
        raise ValueError(f"Whisper produced empty transcription for {audio_path}")
    print(f"Transcription ({audio_path.name}, lang={info.language}): {text}")
    return text


def synthesize_audio(text: str, prompt_text: str, reference_audio: Path, model_dir: Path) -> None:
    require_file(reference_audio, "Reference audio for CosyVoice3")
    run([
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
    ])


def main() -> None:
    log_runtime_versions()
    require_file(VIDEO_PATH, "Input video")
    model_dir = resolve_cosyvoice_model_dir()
    extract_audio_from_video(VIDEO_PATH, AUDIO_PATH)
    trim_reference_audio(AUDIO_PATH, REFERENCE_AUDIO_PATH)

    full_transcript = transcribe_audio(AUDIO_PATH)
    sample_transcript = transcribe_audio(REFERENCE_AUDIO_PATH)
    file_source_text = ""
    if TRANSFORMED_TEXT_PATH.exists():
        file_source_text = TRANSFORMED_TEXT_PATH.read_text(encoding="utf-8").strip()
        if file_source_text:
            print(f"Using transformed text from {TRANSFORMED_TEXT_PATH}")
    source_text = file_source_text or SOURCE_TEXT or full_transcript
    synthesize_audio(source_text, sample_transcript, REFERENCE_AUDIO_PATH, model_dir)


if __name__ == "__main__":
    main()
