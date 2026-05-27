import os
import shutil
import zipfile
from pathlib import Path

import gdown
import requests
from google.cloud import storage
from huggingface_hub import snapshot_download
from modelscope import snapshot_download as modelscope_snapshot_download


BUCKET_NAME = os.environ["BUCKET_NAME"]
MODEL_PREFIX = os.environ.get("MODEL_PREFIX", "").strip("/")
MODELS = [name.strip() for name in os.environ.get("MODELS", "").split(",") if name.strip()]
MODEL_ID = os.environ.get("MODEL_ID")
ALLOW_PATTERNS = os.environ.get("ALLOW_PATTERNS")
DOWNLOAD_URL = os.environ.get("DOWNLOAD_URL")
GDRIVE_ID = os.environ.get("GDRIVE_ID")
DOWNLOAD_FILENAME = os.environ.get("DOWNLOAD_FILENAME")
HF_TOKEN = os.environ.get("HF_TOKEN")

WORK_DIR = Path("/tmp/model")

COMPONENTS = {
    "musetalkV15": {
        "type": "hf",
        "repo_id": "TMElyralab/MuseTalk",
        "prefix": "",
        "files": ["musetalkV15/musetalk.json", "musetalkV15/unet.pth"],
    },
    "sd-vae": {
        "type": "hf",
        "repo_id": "stabilityai/sd-vae-ft-mse",
        "prefix": "sd-vae",
        "files": ["config.json", "diffusion_pytorch_model.safetensors"],
    },
    "whisper": {
        "type": "hf",
        "repo_id": "openai/whisper-tiny",
        "prefix": "whisper",
        "files": [
            "added_tokens.json",
            "config.json",
            "generation_config.json",
            "merges.txt",
            "normalizer.json",
            "preprocessor_config.json",
            "pytorch_model.bin",
            "special_tokens_map.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
        ],
    },
    "whisper-small": {
        "type": "hf",
        "repo_id": "openai/whisper-small",
        "prefix": "whisper-small",
    },
    "dwpose": {
        "type": "hf",
        "repo_id": "yzd-v/DWPose",
        "prefix": "dwpose",
        "files": ["dw-ll_ucoco_384.pth"],
    },
    "syncnet": {
        "type": "hf",
        "repo_id": "ByteDance/LatentSync",
        "prefix": "syncnet",
        "files": ["latentsync_syncnet.pt"],
    },
    "face-parse-bisent": {
        "type": "gdrive",
        "gdrive_id": "154JgKpzCPW82qINcVieuPH3fZ2e0P812",
        "prefix": "face-parse-bisent",
        "filename": "79999_iter.pth",
    },
    "resnet18": {
        "type": "url",
        "url": "https://download.pytorch.org/models/resnet18-5c106cde.pth",
        "prefix": "face-parse-bisent",
        "filename": "resnet18-5c106cde.pth",
    },
    "cosyvoice3": {
        "type": "hf",
        "repo_id": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        "prefix": "cosyvoice/Fun-CosyVoice3-0.5B-2512",
        "targets": ["cosyvoice3.yaml"],
    },
    "wetext": {
        "type": "modelscope",
        "repo_id": "pengzhendong/wetext",
        "prefix": "cosyvoice/wetext",
    },
}


def blob_name(prefix: str, relative_path: Path | str) -> str:
    relative = str(relative_path)
    return f"{prefix}/{relative}" if prefix else relative


def all_targets_exist(bucket: storage.Bucket, targets: list[str]) -> bool:
    missing = [target for target in targets if not bucket.blob(target).exists()]
    if missing:
        print("Missing:", ", ".join(missing))
        return False
    print("Already present:", ", ".join(targets))
    return True


def component_targets(component: dict) -> list[str]:
    if "targets" in component:
        return [blob_name(component["prefix"], file_name) for file_name in component["targets"]]
    if "files" in component:
        return [blob_name(component["prefix"], file_name) for file_name in component["files"]]
    if "filename" in component:
        return [blob_name(component["prefix"], component["filename"])]
    return []


def reset_work_dir() -> None:
    shutil.rmtree(WORK_DIR, ignore_errors=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)


def upload_dir_to_gcs(local_dir: Path, bucket: storage.Bucket, prefix: str) -> None:
    for path in local_dir.rglob("*"):
        if path.is_file():
            relative_path = path.relative_to(local_dir)
            target = blob_name(prefix, relative_path)
            bucket.blob(target).upload_from_filename(str(path))
            print(f"Uploaded gs://{bucket.name}/{target}")


def upload_file_to_gcs(local_path: Path, bucket: storage.Bucket, prefix: str) -> None:
    target = blob_name(prefix, local_path.name)
    bucket.blob(target).upload_from_filename(str(local_path))
    print(f"Uploaded gs://{bucket.name}/{target}")


def download_url(url: str, output_path: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with output_path.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)


def download_hf_component(component: dict, bucket: storage.Bucket) -> None:
    reset_work_dir()
    snapshot_download(
        repo_id=component["repo_id"],
        local_dir=str(WORK_DIR),
        allow_patterns=component.get("files"),
        token=HF_TOKEN,
    )
    upload_dir_to_gcs(WORK_DIR, bucket, component["prefix"])


def download_modelscope_component(component: dict, bucket: storage.Bucket) -> None:
    reset_work_dir()
    modelscope_snapshot_download(model_id=component["repo_id"], local_dir=str(WORK_DIR))
    upload_dir_to_gcs(WORK_DIR, bucket, component["prefix"])


def download_gdrive_component(component: dict, bucket: storage.Bucket) -> None:
    reset_work_dir()
    output_path = WORK_DIR / component["filename"]
    gdown.download(id=component["gdrive_id"], output=str(output_path), quiet=False)
    upload_file_to_gcs(output_path, bucket, component["prefix"])


def download_url_component(component: dict, bucket: storage.Bucket) -> None:
    reset_work_dir()
    output_path = WORK_DIR / component["filename"]
    download_url(component["url"], output_path)
    upload_file_to_gcs(output_path, bucket, component["prefix"])


def download_zip_url_component(component: dict, bucket: storage.Bucket) -> None:
    reset_work_dir()
    archive_path = WORK_DIR / component["filename"]
    extract_dir = WORK_DIR / "extract"
    download_url(component["url"], archive_path)
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extract_dir)
    upload_dir_to_gcs(extract_dir, bucket, component["prefix"])


def download_named_component(name: str, bucket: storage.Bucket) -> None:
    if name not in COMPONENTS:
        raise ValueError(f"Unknown model component '{name}'. Known components: {', '.join(COMPONENTS)}")

    component = COMPONENTS[name]
    targets = component_targets(component)
    if targets and all_targets_exist(bucket, targets):
        print(f"Skipping {name}; all target files already exist.")
        return

    print(f"Downloading {name}...")
    if component["type"] == "hf":
        download_hf_component(component, bucket)
    elif component["type"] == "modelscope":
        download_modelscope_component(component, bucket)
    elif component["type"] == "gdrive":
        download_gdrive_component(component, bucket)
    elif component["type"] == "url":
        download_url_component(component, bucket)
    elif component["type"] == "zip_url":
        download_zip_url_component(component, bucket)
    else:
        raise ValueError(f"Unsupported component type: {component['type']}")


def download_ad_hoc(bucket: storage.Bucket) -> None:
    reset_work_dir()

    if GDRIVE_ID:
        if not DOWNLOAD_FILENAME:
            raise ValueError("DOWNLOAD_FILENAME is required when GDRIVE_ID is set.")
        output_path = WORK_DIR / DOWNLOAD_FILENAME
        gdown.download(id=GDRIVE_ID, output=str(output_path), quiet=False)
        upload_file_to_gcs(output_path, bucket, MODEL_PREFIX)
    elif DOWNLOAD_URL:
        filename = DOWNLOAD_FILENAME or DOWNLOAD_URL.rstrip("/").rsplit("/", 1)[-1]
        output_path = WORK_DIR / filename
        download_url(DOWNLOAD_URL, output_path)
        upload_file_to_gcs(output_path, bucket, MODEL_PREFIX)
    else:
        if not MODEL_ID:
            raise ValueError("MODEL_ID is required for ad hoc Hugging Face downloads.")
        snapshot_download(
            repo_id=MODEL_ID,
            local_dir=str(WORK_DIR),
            allow_patterns=ALLOW_PATTERNS.split(",") if ALLOW_PATTERNS else None,
            token=HF_TOKEN,
        )
        upload_dir_to_gcs(WORK_DIR, bucket, MODEL_PREFIX)


def main() -> None:
    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)

    if MODELS:
        for model in MODELS:
            download_named_component(model, bucket)
    else:
        download_ad_hoc(bucket)


if __name__ == "__main__":
    main()
