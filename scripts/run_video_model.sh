#!/usr/bin/env bash
set -euo pipefail

project_id="${PROJECT_ID:-toner-ai}"
region="${REGION:-europe-west1}"
video_ai_job="${VIDEO_AI_JOB:-video-ai-job}"
log_poll_seconds="${LOG_POLL_SECONDS:-10}"

dummy_text="${DUMMY_TEXT:-}"
dummy_tts_language="${DUMMY_TTS_LANGUAGE:-en}"
dummy_tts_model="${DUMMY_TTS_MODEL:-/models/cosyvoice/Fun-CosyVoice3-0.5B-2512}"
dummy_tts_prompt_text="${DUMMY_TTS_PROMPT_TEXT:-This is a short reference sample in English.}"
dummy_tts_speed="${DUMMY_TTS_SPEED:-1.0}"
text_style="${TEXT_STYLE:-confident}"
source_text="${SOURCE_TEXT:-}"
whisper_model_path="${WHISPER_MODEL_PATH:-/models/faster-whisper-base}"

start_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

env_args=()
if [[ -n "${dummy_text}" ]]; then
  env_args+=(
    "--update-env-vars=^__ENV__^DUMMY_TEXT=${dummy_text}__ENV__DUMMY_TTS_LANGUAGE=${dummy_tts_language}__ENV__DUMMY_TTS_MODEL=${dummy_tts_model}__ENV__DUMMY_TTS_PROMPT_TEXT=${dummy_tts_prompt_text}__ENV__DUMMY_TTS_SPEED=${dummy_tts_speed}__ENV__TEXT_STYLE=${text_style}__ENV__SOURCE_TEXT=${source_text}__ENV__WHISPER_MODEL_PATH=${whisper_model_path}"
  )
else
  # Ensure stale dummy settings are cleared so transcription comes from uploaded input video audio.
  env_args+=(
    "--update-env-vars=^__ENV__^DUMMY_TEXT=__ENV__DUMMY_TTS_LANGUAGE=${dummy_tts_language}__ENV__DUMMY_TTS_MODEL=${dummy_tts_model}__ENV__DUMMY_TTS_PROMPT_TEXT=${dummy_tts_prompt_text}__ENV__DUMMY_TTS_SPEED=${dummy_tts_speed}__ENV__TEXT_STYLE=${text_style}__ENV__SOURCE_TEXT=${source_text}__ENV__WHISPER_MODEL_PATH=${whisper_model_path}"
  )
fi

gcloud run jobs execute "${video_ai_job}" \
  --region="${region}" \
  "${env_args[@]}" \
  --wait &
wait_pid="$!"

sleep 5
execution="$(
  gcloud run jobs executions list \
    --job="${video_ai_job}" \
    --region="${region}" \
    --sort-by="~metadata.creationTimestamp" \
    --limit=1 \
    --format="value(metadata.name)"
)"

echo "Tailing logs for ${execution}"
last_ts="${start_ts}"

while kill -0 "${wait_pid}" 2>/dev/null; do
  gcloud logging read \
    "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${video_ai_job}\" AND resource.labels.location=\"${region}\" AND labels.\"run.googleapis.com/execution_name\"=\"${execution}\" AND timestamp>=\"${last_ts}\"" \
    --project="${project_id}" \
    --order=asc \
    --limit=200 \
    --format="value(timestamp,textPayload)" || true
  last_ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  sleep "${log_poll_seconds}"
done

wait "${wait_pid}"

gcloud logging read \
  "resource.type=\"cloud_run_job\" AND resource.labels.job_name=\"${video_ai_job}\" AND resource.labels.location=\"${region}\" AND labels.\"run.googleapis.com/execution_name\"=\"${execution}\" AND timestamp>=\"${last_ts}\"" \
  --project="${project_id}" \
  --order=asc \
  --limit=200 \
  --format="value(timestamp,textPayload)" || true
