import argparse
import sys
from pathlib import Path

import soundfile as sf


HERE = Path(__file__).resolve()
if len(HERE.parents) >= 3:
    REPO_ROOT = HERE.parents[2]
else:
    REPO_ROOT = Path.cwd()
COSYVOICE_ROOT = REPO_ROOT / "CosyVoice"
if not COSYVOICE_ROOT.exists():
    COSYVOICE_ROOT = Path("/opt/CosyVoice")
MATCHA_ROOT = COSYVOICE_ROOT / "third_party" / "Matcha-TTS"
if str(COSYVOICE_ROOT) not in sys.path:
    sys.path.insert(0, str(COSYVOICE_ROOT))
if str(MATCHA_ROOT) not in sys.path:
    sys.path.insert(0, str(MATCHA_ROOT))

from cosyvoice.cli.cosyvoice import CosyVoice3


DEFAULT_MODEL_DIR = "/models/cosyvoice/Fun-CosyVoice3-0.5B-2512"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--reference-audio", required=True)
    parser.add_argument("--prompt-text", required=True)
    parser.add_argument("--model-dir", default=DEFAULT_MODEL_DIR)
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    reference_audio = Path(args.reference_audio)
    if not reference_audio.exists():
        raise FileNotFoundError(f"Reference audio does not exist: {reference_audio}")

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        raise FileNotFoundError(
            f"CosyVoice model directory does not exist: {model_dir}. "
            "Download model files first."
        )

    cosyvoice3_yaml = model_dir / "cosyvoice3.yaml"
    if not cosyvoice3_yaml.exists():
        raise FileNotFoundError(f"Expected CosyVoice3 config not found: {cosyvoice3_yaml}")

    prompt_text = args.prompt_text.strip()
    if "<|endofprompt|>" not in prompt_text:
        prompt_text = f"<|endofprompt|>{prompt_text}"

    print(f"Loading CosyVoice3 model from: {model_dir}")
    cosyvoice = CosyVoice3(model_dir=str(model_dir))
    for result in cosyvoice.inference_zero_shot(
        args.text,
        prompt_text,
        str(reference_audio),
        stream=False,
        speed=args.speed,
    ):
        audio = result["tts_speech"]

        if audio.dim() == 1:
            audio = audio.unsqueeze(0)

        audio = audio.detach().cpu().numpy()
        if audio.ndim == 2:
            audio = audio.T
        sf.write(str(output_path), audio, 24000)
        break

    print(f"Wrote CosyVoice audio: {output_path}")


if __name__ == "__main__":
    main()
