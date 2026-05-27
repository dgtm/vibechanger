import json
import os
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
VIDEO_AI_JOB = os.environ.get("VIDEO_AI_JOB", "video-ai-job")
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
    base_name = Path(req.object_path).name
    video_path = f"/data/{INPUT_PREFIX}/{base_name}"
    env_payload = f"VIDEO_PATH={video_path},TEXT_STYLE={req.text_style},SOURCE_TEXT={req.source_text}"
    cmd = [
        "gcloud",
        "run",
        "jobs",
        "execute",
        VIDEO_AI_JOB,
        f"--region={REGION}",
        f"--update-env-vars={env_payload}",
        "--format=json",
    ]
    try:
        proc = subprocess.run(cmd, check=True, text=True, capture_output=True)
        payload = json.loads(proc.stdout)
        execution_name = payload.get("metadata", {}).get("name", "")
        if not execution_name:
            raise ValueError("Missing execution name from gcloud response")
        return RunResponse(execution_name=execution_name)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to run job: {exc}") from exc


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
