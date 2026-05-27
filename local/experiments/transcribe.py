import argparse
from pathlib import Path

from faster_whisper import WhisperModel


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe an audio file with faster-whisper.")
    parser.add_argument("audio", type=Path, help="Path to the audio file to transcribe.")
    parser.add_argument("--model", default="models/faster-whisper-base", help="Local model directory.")
    parser.add_argument("--device", default="cpu", help="Device to run on, for example cpu or cuda.")
    parser.add_argument("--compute-type", default="int8", help="CTranslate2 compute type.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
    )

    segments, info = model.transcribe(str(args.audio))
    print(f"Detected language: {info.language} ({info.language_probability:.2f})")

    for segment in segments:
        print(f"[{segment.start:.2f}s -> {segment.end:.2f}s] {segment.text}")


if __name__ == "__main__":
    main()
