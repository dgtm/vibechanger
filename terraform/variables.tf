variable "project_id" {
  description = "Globally unique GCP project ID to create and use"
  type        = string
}

variable "project_name" {
  description = "Display name for the GCP project"
  type        = string
  default     = "toner"
}

variable "billing_account" {
  description = "Billing account ID to link to the project, for example 000000-000000-000000"
  type        = string
  default     = null
}

variable "org_id" {
  description = "Organization ID to create the project under. Leave null for personal/no-org projects."
  type        = string
  default     = null
}

variable "folder_id" {
  description = "Folder ID to create the project under. Leave null unless using a GCP organization folder."
  type        = string
  default     = null
}

variable "region" {
  description = "GCP region for Cloud Run Job and buckets"
  type        = string
  default     = "us-central1"
}

variable "job_name" {
  description = "Cloud Run Job name"
  type        = string
  default     = "video-ai-job"
}

variable "container_image" {
  description = "Container image for the Cloud Run job"
  type        = string
}

variable "hf_downloader_container_image" {
  description = "Container image for the Hugging Face downloader Cloud Run job"
  type        = string
}

variable "service_account_id" {
  description = "Short account ID for the Cloud Run service account"
  type        = string
  default     = "video-ai-job-sa"
}

variable "hf_downloader_service_account_id" {
  description = "Short account ID for the Hugging Face downloader service account"
  type        = string
  default     = "hf-downloader-job-sa"
}

variable "hf_downloader_job_name" {
  description = "Cloud Run Job name for downloading Hugging Face models"
  type        = string
  default     = "hf-downloader-job"
}

variable "hf_downloader_model_id" {
  description = "Default Hugging Face repo ID downloaded by the hf_downloader job"
  type        = string
  default     = "TMElyralab/MuseTalk"
}

variable "hf_downloader_models" {
  description = "Comma-separated known model components to download if they are missing"
  type        = string
  default     = "musetalkV15,sd-vae,whisper,dwpose,syncnet,face-parse-bisent,resnet18,cosyvoice3,wetext"
}

variable "hf_downloader_model_prefix" {
  description = "Destination prefix inside the models bucket for the downloaded Hugging Face repo"
  type        = string
  default     = ""
}

variable "artifact_repository_id" {
  description = "Artifact Registry Docker repository ID for job images"
  type        = string
  default     = "ai"
}

variable "models_bucket_name" {
  description = "Globally unique bucket name for model weights"
  type        = string
}

variable "data_bucket_name" {
  description = "Globally unique bucket name for input/output assets"
  type        = string
}

variable "cpu" {
  description = "vCPU for each task. L4 GPU jobs require at least 4 CPU."
  type        = string
  default     = "4"
}

variable "memory" {
  description = "Memory for each task. L4 GPU jobs require at least 16Gi memory."
  type        = string
  default     = "16Gi"
}

variable "hf_downloader_cpu" {
  description = "vCPU for the Hugging Face downloader task"
  type        = string
  default     = "4"
}

variable "hf_downloader_memory" {
  description = "Memory for the Hugging Face downloader task"
  type        = string
  default     = "16Gi"
}

variable "gpu_type" {
  description = "GPU type to attach"
  type        = string
  default     = "nvidia-l4"
}

variable "parallelism" {
  description = "How many tasks run at once"
  type        = number
  default     = 1
}

variable "task_count" {
  description = "Number of tasks per execution"
  type        = number
  default     = 1
}

variable "task_timeout_seconds" {
  description = "Per-task timeout in seconds. GPU jobs max out at 3600 seconds."
  type        = number
  default     = 3600

  validation {
    condition     = var.task_timeout_seconds > 0 && var.task_timeout_seconds <= 3600
    error_message = "GPU-backed Cloud Run jobs must use a timeout between 1 and 3600 seconds."
  }
}

variable "hf_downloader_task_timeout_seconds" {
  description = "Per-task timeout in seconds for the Hugging Face downloader job"
  type        = number
  default     = 3600

  validation {
    condition     = var.hf_downloader_task_timeout_seconds > 0
    error_message = "The Hugging Face downloader task timeout must be greater than 0 seconds."
  }
}

variable "input_prefix" {
  description = "Folder prefix in the data bucket for inputs"
  type        = string
  default     = "inputs"
}

variable "output_prefix" {
  description = "Folder prefix in the data bucket for outputs"
  type        = string
  default     = "outputs"
}

variable "ui_uploader_service_account_id" {
  description = "Short account ID for the UI upload/signing service account"
  type        = string
  default     = "video-ui-uploader-sa"
}

variable "create_ui_uploader_key" {
  description = "Whether to create a long-lived JSON key for local development"
  type        = bool
  default     = true
}
