import json
import os
import re
import secrets
import subprocess
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import storage
from pydantic import BaseModel


PROJECT_ID = os.environ.get("PROJECT_ID", "toner-ai")
REGION = os.environ.get("REGION", "europe-west1")
VIDEO_POST_JOB = os.environ.get("VIDEO_POST_JOB", "video-post-job")
COSYVOICE_JOB = os.environ.get("COSYVOICE_JOB", "cosyvoice3-job")
DATA_BUCKET = os.environ.get("DATA_BUCKET", "toner-ai-video-ai-data")
INPUT_PREFIX = os.environ.get("INPUT_PREFIX", "inputs")

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

app = FastAPI(title="Video AI Trigger UI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

storage_client = storage.Client(project=PROJECT_ID)


class SignUploadResponse(BaseModel):
    upload_url: str
    object_path: str
    content_type: str


class SignUploadRequest(BaseModel):
    content_type: str


class RunRequest(BaseModel):
    object_path: str
    text_style: str = "confident"
    source_text: str = ""


class RunResponse(BaseModel):
    execution_name: str


class OutputVideoResponse(BaseModel):
    video_url: str
    object_path: str


class OutputVideoItem(BaseModel):
    video_url: str
    object_path: str
    updated: str
    input_video_url: str | None = None
    input_object_path: str | None = None


class OutputVideosResponse(BaseModel):
    items: list[OutputVideoItem]


def execute_job(job_name: str, req: RunRequest, extra_env: dict[str, str] | None = None) -> RunResponse:
    base_name = Path(req.object_path).name
    video_path = f"/data/{INPUT_PREFIX}/{base_name}"
    env = {
        "VIDEO_PATH": video_path,
        "TEXT_STYLE": req.text_style,
        "SOURCE_TEXT": req.source_text,
    }
    if extra_env:
        env.update(extra_env)
    env_payload = ",".join(f"{k}={v}" for k, v in env.items())
    cmd = [
        "gcloud",
        "run",
        "jobs",
        "execute",
        job_name,
        f"--region={REGION}",
        f"--update-env-vars={env_payload}",
        "--format=json",
    ]
    print(f"Executing Cloud Run job: {job_name}")
    try:
        proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
        payload = json.loads(proc.stdout)
        execution_name = payload.get("metadata", {}).get("name", "")
        if not execution_name:
            raise ValueError("Missing execution name from gcloud response")
        return RunResponse(execution_name=execution_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run job {job_name}: {exc}") from exc


def find_output_blob(object_path: str) -> storage.Blob:
    input_name = Path(object_path).name
    input_stem = Path(input_name).stem
    output_prefix = "outputs/"
    preferred_prefixes = [f"{output_prefix}musetalk/v15/", f"{output_prefix}musetalk/", output_prefix]
    generated_dir_token = f"{input_stem}_generated/"

    for prefix in preferred_prefixes:
        candidates = sorted(
            (
                blob
                for blob in storage_client.list_blobs(DATA_BUCKET, prefix=prefix)
                if blob.name.lower().endswith(".mp4")
                and (
                    generated_dir_token in blob.name
                    or input_stem in Path(blob.name).stem
                )
            ),
            key=lambda b: b.updated or b.time_created,
            reverse=True,
        )
        if candidates:
            return candidates[0]

    fallback = sorted(
        (
            blob
            for blob in storage_client.list_blobs(DATA_BUCKET, prefix=output_prefix)
            if blob.name.lower().endswith(".mp4")
        ),
        key=lambda b: b.updated or b.time_created,
        reverse=True,
    )
    if fallback:
        return fallback[0]
    raise HTTPException(status_code=404, detail="No output MP4 found in outputs/")


def list_output_blobs(limit: int) -> list[storage.Blob]:
    prefixes = ["outputs/musetalk/v15/", "outputs/musetalk/", "outputs/"]
    seen: set[str] = set()
    all_mp4: list[storage.Blob] = []
    for prefix in prefixes:
        for blob in storage_client.list_blobs(DATA_BUCKET, prefix=prefix):
            if not blob.name.lower().endswith(".mp4"):
                continue
            if blob.name in seen:
                continue
            seen.add(blob.name)
            all_mp4.append(blob)
    all_mp4.sort(key=lambda b: b.updated or b.time_created, reverse=True)
    return all_mp4[:limit]


def guess_input_blob_for_output(output_blob: storage.Blob) -> storage.Blob | None:
    # Common output pattern: outputs/musetalk/v15/<input_stem>_generated/...mp4
    name = output_blob.name
    marker = "_generated/"
    bucket = storage_client.bucket(DATA_BUCKET)

    stem: str | None = None
    if marker in name:
        stem = name.split(marker, 1)[0].split("/")[-1]
    if not stem:
        # Fallback: detect hex-like run IDs in output names.
        match = re.search(r"([a-f0-9]{8,32})", name)
        if match:
            stem = match.group(1)
    if not stem:
        return None

    # First try exact expected filenames.
    for ext in (".mp4", ".webm", ".mov", ".mkv"):
        candidate = bucket.blob(f"{INPUT_PREFIX}/{stem}{ext}")
        if candidate.exists():
            return candidate

    # Fallback: any input object that starts with the same stem.
    prefix = f"{INPUT_PREFIX}/{stem}"
    candidates = sorted(
        (blob for blob in storage_client.list_blobs(DATA_BUCKET, prefix=prefix) if not blob.name.endswith("/")),
        key=lambda b: b.updated or b.time_created,
        reverse=True,
    )
    if candidates:
        return candidates[0]
    return None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.post("/api/sign-upload", response_model=SignUploadResponse)
def sign_upload(req: SignUploadRequest) -> SignUploadResponse:
    run_id = secrets.token_hex(8)
    content_type = req.content_type or "video/webm"
    ext = ".webm"
    if "mp4" in content_type:
        ext = ".mp4"
    object_path = f"{INPUT_PREFIX}/{run_id}{ext}"
    bucket = storage_client.bucket(DATA_BUCKET)
    blob = bucket.blob(object_path)
    try:
        upload_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=15),
            method="PUT",
            content_type=content_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create signed URL: {exc}") from exc
    return SignUploadResponse(upload_url=upload_url, object_path=object_path, content_type=content_type)


@app.post("/api/run", response_model=RunResponse)
def run_job(req: RunRequest) -> RunResponse:
    return execute_job(VIDEO_POST_JOB, req, {"PIPELINE_STAGE": "musetalk"})


@app.post("/api/run-step1", response_model=RunResponse)
def run_step1(req: RunRequest) -> RunResponse:
    return execute_job(VIDEO_POST_JOB, req, {"PIPELINE_STAGE": "transform"})


@app.post("/api/run-step2", response_model=RunResponse)
def run_step2(req: RunRequest) -> RunResponse:
    return execute_job(COSYVOICE_JOB, req)


@app.post("/api/run-step3", response_model=RunResponse)
def run_step3(req: RunRequest) -> RunResponse:
    return execute_job(VIDEO_POST_JOB, req, {"PIPELINE_STAGE": "musetalk"})


@app.get("/api/output-video", response_model=OutputVideoResponse)
def output_video(object_path: str) -> OutputVideoResponse:
    blob = find_output_blob(object_path)
    try:
        signed_url = blob.generate_signed_url(version="v4", expiration=timedelta(minutes=15), method="GET")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to sign output URL: {exc}") from exc
    return OutputVideoResponse(video_url=signed_url, object_path=blob.name)


@app.get("/api/output-videos", response_model=OutputVideosResponse)
def output_videos(limit: int = 5) -> OutputVideosResponse:
    limit = max(1, min(limit, 20))
    items: list[OutputVideoItem] = []
    for blob in list_output_blobs(limit):
        try:
            signed_url = blob.generate_signed_url(version="v4", expiration=timedelta(minutes=15), method="GET")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to sign output URL: {exc}") from exc
        updated = (blob.updated or blob.time_created).isoformat() if (blob.updated or blob.time_created) else ""
        input_blob = guess_input_blob_for_output(blob)
        input_video_url = None
        input_object_path = None
        if input_blob is not None:
            try:
                input_video_url = input_blob.generate_signed_url(version="v4", expiration=timedelta(minutes=15), method="GET")
                input_object_path = input_blob.name
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to sign input URL: {exc}") from exc
        items.append(
            OutputVideoItem(
                video_url=signed_url,
                object_path=blob.name,
                updated=updated,
                input_video_url=input_video_url,
                input_object_path=input_object_path,
            )
        )
    return OutputVideosResponse(items=items)


@app.get("/api/status/{execution_name}")
def job_status(execution_name: str) -> dict:
    cmd = [
        "gcloud",
        "run",
        "jobs",
        "executions",
        "describe",
        execution_name,
        f"--region={REGION}",
        "--format=json",
    ]
    try:
        proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
        payload = json.loads(proc.stdout)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch job status: {exc}") from exc

    conditions = payload.get("status", {}).get("conditions", [])
    complete = False
    success = False
    for cond in conditions:
        if cond.get("type") == "Completed":
            complete = cond.get("status") == "True"
            success = cond.get("state") == "CONDITION_SUCCEEDED"
            break
    return {
        "execution_name": execution_name,
        "complete": complete,
        "success": success,
        "raw_status": payload.get("status", {}),
    }
