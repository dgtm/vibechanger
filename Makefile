# concise makefile for video worker workflows

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Core project config
PROJECT_ID ?= toner-ai
REGION ?= europe-west1
ARTIFACT_REPOSITORY ?= ai
IMAGE_TAG ?= latest
DOCKER_PLATFORM ?= linux/amd64

# Infra + cloud resources
TERRAFORM_DIR ?= terraform
TFVARS ?= main.tfvars
UI_UPLOADER_KEY_PATH ?= $(HOME)/.config/gcp/video-ui-uploader-sa-key.json
IAM_USER ?= dipeshgtm@gmail.com
VIDEO_AI_JOB ?= video-ai-job
HF_DOWNLOADER_JOB ?= hf-downloader-job
MODELS_BUCKET ?= toner-ai-video-ai-models
DATA_BUCKET ?= toner-ai-video-ai-data
INPUT_PREFIX ?= inputs

# Images
VIDEO_AI_IMAGE ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(ARTIFACT_REPOSITORY)/video-worker:$(IMAGE_TAG)
HF_DOWNLOADER_IMAGE ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(ARTIFACT_REPOSITORY)/hf-downloader:$(IMAGE_TAG)

# Runtime knobs
LOG_POLL_SECONDS ?= 10
DUMMY_TEXT ?=
DUMMY_TTS_LANGUAGE ?= en
DUMMY_TTS_MODEL ?= /models/cosyvoice/Fun-CosyVoice3-0.5B-2512
DUMMY_TTS_PROMPT_TEXT ?= This is a short reference sample in English.
DUMMY_TTS_SPEED ?= 1.0
TEXT_STYLE ?= confident
SOURCE_TEXT ?=
WHISPER_MODEL_PATH ?= /models/faster-whisper-base

# Downloader knobs
HF_MODELS ?= musetalkV15,sd-vae,whisper,dwpose,syncnet,face-parse-bisent,resnet18,cosyvoice3,wetext
HF_MODEL_ID ?= TMElyralab/MuseTalk
HF_MODEL_PREFIX ?=
DOWNLOAD_URL ?=
GDRIVE_ID ?=
DOWNLOAD_FILENAME ?=

# Local workflow
LOCAL_INPUT_VIDEO ?= local/input/input.mp4
LOCAL_OUTPUT_DIR ?= local/output
LOCAL_MODEL ?= faster-whisper-base
LOCAL_MODEL_DIR ?= models/$(LOCAL_MODEL)
LOCAL_AUDIO ?=

export PROJECT_ID REGION VIDEO_AI_JOB LOG_POLL_SECONDS
export DUMMY_TEXT DUMMY_TTS_LANGUAGE DUMMY_TTS_MODEL DUMMY_TTS_PROMPT_TEXT DUMMY_TTS_SPEED TEXT_STYLE SOURCE_TEXT WHISPER_MODEL_PATH

.PHONY: help \
  auth-login auth-adc auth-project auth-status \
  artifact-registry-create docker-auth docker-build docker-push docker-publish \
  docker-build-video-ai docker-build-hf-downloader docker-push-video-ai docker-push-hf-downloader docker-publish-video-ai docker-publish-hf-downloader \
  upload-input run \
  hf-download hf-download-repo hf-download-url \
  local-venv local-download-model local-transcribe local-run local-dummy-audio \
  ui \
  terraform-init terraform-fmt terraform-fmt-check terraform-validate terraform-plan terraform-apply terraform-apply-with-ui-key terraform-destroy terraform-bootstrap-iam

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "%-24s %s\n", $$1, $$2}' | sort

# ---------- Auth ----------
auth-login: ## gcloud auth login
	gcloud auth login

auth-adc: ## gcloud application-default login
	gcloud auth application-default login

auth-project: ## set active gcloud project
	gcloud config set project $(PROJECT_ID)

auth-status: ## show auth + active project
	gcloud auth list
	gcloud config get-value project

# ---------- Build + publish ----------
artifact-registry-create: auth-project ## create Artifact Registry docker repo
	gcloud artifacts repositories create $(ARTIFACT_REPOSITORY) --repository-format=docker --location=$(REGION) --description="Container images for video AI jobs"

docker-auth: ## configure docker auth for Artifact Registry
	gcloud auth configure-docker $(REGION)-docker.pkg.dev

docker-build-video-ai: ## build video worker image
	docker build --platform=$(DOCKER_PLATFORM) --cache-from $(VIDEO_AI_IMAGE) -t $(VIDEO_AI_IMAGE) jobs/video_ai

docker-build-hf-downloader: ## build hf downloader image
	docker build --platform=$(DOCKER_PLATFORM) -t $(HF_DOWNLOADER_IMAGE) jobs/hf_downloader

docker-build: docker-build-video-ai docker-build-hf-downloader ## build both images

docker-push-video-ai: ## push video worker image
	docker push $(VIDEO_AI_IMAGE)

docker-push-hf-downloader: ## push hf downloader image
	docker push $(HF_DOWNLOADER_IMAGE)

docker-push: docker-push-video-ai docker-push-hf-downloader ## push both images

docker-publish-video-ai: auth-project docker-auth docker-build-video-ai docker-push-video-ai ## build+push video worker

docker-publish-hf-downloader: auth-project docker-auth docker-build-hf-downloader docker-push-hf-downloader ## build+push hf downloader

docker-publish: docker-publish-video-ai docker-publish-hf-downloader ## build+push both images

# ---------- Run jobs ----------
upload-input: auth-project ## upload local/input/input.mp4 to data bucket
	test -f "$(LOCAL_INPUT_VIDEO)"
	gsutil cp "$(LOCAL_INPUT_VIDEO)" gs://$(DATA_BUCKET)/$(INPUT_PREFIX)/input.mp4

run: upload-input ## run video model job and stream logs
	bash scripts/run_video_model.sh

hf-download: auth-project ## download default HF_MODELS to models bucket
	gcloud run jobs execute $(HF_DOWNLOADER_JOB) --region=$(REGION) --update-env-vars="^|^MODELS=$(HF_MODELS)|BUCKET_NAME=$(MODELS_BUCKET)" --wait

hf-download-repo: auth-project ## download one repo (HF_MODEL_ID) to bucket
	gcloud run jobs execute $(HF_DOWNLOADER_JOB) --region=$(REGION) --update-env-vars="^|^MODELS=|MODEL_ID=$(HF_MODEL_ID)|BUCKET_NAME=$(MODELS_BUCKET)|MODEL_PREFIX=$(HF_MODEL_PREFIX)" --wait

hf-download-url: auth-project ## download direct url/gdrive file to bucket
	gcloud run jobs execute $(HF_DOWNLOADER_JOB) --region=$(REGION) --update-env-vars="^|^BUCKET_NAME=$(MODELS_BUCKET)|MODEL_PREFIX=$(HF_MODEL_PREFIX)|DOWNLOAD_URL=$(DOWNLOAD_URL)|GDRIVE_ID=$(GDRIVE_ID)|DOWNLOAD_FILENAME=$(DOWNLOAD_FILENAME)" --wait

# ---------- Local ----------
local-venv: ## create local python venv for helper scripts
	python3 -m venv .local-venv
	.local-venv/bin/pip install -r local/requirements.txt

local-download-model: ## copy one model folder from models bucket to ./models
	mkdir -p models
	gsutil -m cp -r gs://$(MODELS_BUCKET)/$(LOCAL_MODEL) models/

local-transcribe: ## transcribe LOCAL_AUDIO with local whisper model
	test -n "$(LOCAL_AUDIO)"
	.local-venv/bin/python local/transcribe.py "$(LOCAL_AUDIO)" --model "$(LOCAL_MODEL_DIR)"

local-run: ## run video worker locally with docker + gpu
	mkdir -p $(LOCAL_OUTPUT_DIR)
	docker run --rm --gpus all --platform=$(DOCKER_PLATFORM) -e DATA_DIR=/data -e INPUT_DIR=/data/inputs -e OUTPUT_DIR=/data/outputs -e VIDEO_PATH=/data/inputs/input.mp4 -v "$(PWD)/models:/models:ro" -v "$(PWD)/local/input:/data/inputs:ro" -v "$(PWD)/$(LOCAL_OUTPUT_DIR):/data/outputs" $(VIDEO_AI_IMAGE)

local-dummy-audio: ## generate dummy local audio sample
	mkdir -p local/input
	python3 local/create_dummy_audio.py

# ---------- UI ----------
ui: ## run local UI server
	python3 -m venv .venv-ui
	.venv-ui/bin/pip install -r ui/requirements.txt
	.venv-ui/bin/uvicorn ui.server:app --host 0.0.0.0 --port 8000

# ---------- Terraform ----------
terraform-init: ## terraform init
	terraform -chdir=$(TERRAFORM_DIR) init

terraform-fmt: ## terraform fmt
	terraform -chdir=$(TERRAFORM_DIR) fmt

terraform-fmt-check: ## terraform fmt -check
	terraform -chdir=$(TERRAFORM_DIR) fmt -check

terraform-validate: ## terraform validate
	terraform -chdir=$(TERRAFORM_DIR) validate

terraform-plan: ## terraform plan
	terraform -chdir=$(TERRAFORM_DIR) plan -var-file=$(TFVARS)

terraform-apply: ## terraform apply
	terraform -chdir=$(TERRAFORM_DIR) apply -var-file=$(TFVARS)

terraform-apply-with-ui-key: ## terraform apply + write ui uploader key
	terraform -chdir=$(TERRAFORM_DIR) apply -var-file=$(TFVARS) -var='create_ui_uploader_key=true'
	mkdir -p "$$(dirname '$(UI_UPLOADER_KEY_PATH)')"
	terraform -chdir=$(TERRAFORM_DIR) output -raw ui_uploader_service_account_key_private_key | base64 --decode > '$(UI_UPLOADER_KEY_PATH)'
	chmod 600 '$(UI_UPLOADER_KEY_PATH)'
	@echo "Wrote UI uploader key to $(UI_UPLOADER_KEY_PATH)"
	@echo "Run: export GOOGLE_APPLICATION_CREDENTIALS='$(UI_UPLOADER_KEY_PATH)'"

terraform-destroy: ## terraform destroy
	terraform -chdir=$(TERRAFORM_DIR) destroy -var-file=$(TFVARS)

terraform-bootstrap-iam: auth-project ## bootstrap required IAM roles for user
	gcloud projects add-iam-policy-binding $(PROJECT_ID) --member="user:$(IAM_USER)" --role="roles/iam.serviceAccountAdmin"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) --member="user:$(IAM_USER)" --role="roles/storage.admin"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) --member="user:$(IAM_USER)" --role="roles/run.admin"
	gcloud projects add-iam-policy-binding $(PROJECT_ID) --member="user:$(IAM_USER)" --role="roles/serviceusage.serviceUsageAdmin"
