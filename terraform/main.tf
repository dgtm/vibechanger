terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  region = var.region
}

resource "google_project" "project" {
  name            = var.project_name
  project_id      = var.project_id
  org_id          = var.org_id
  folder_id       = var.folder_id
  billing_account = var.billing_account
}

resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "cloudbuild.googleapis.com",
  ])

  project            = google_project.project.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "job" {
  project      = google_project.project.project_id
  account_id   = var.service_account_id
  display_name = "Cloud Run Job service account"
}

resource "google_service_account" "hf_downloader" {
  project      = google_project.project.project_id
  account_id   = var.hf_downloader_service_account_id
  display_name = "Hugging Face downloader Cloud Run Job service account"
}

resource "google_service_account" "ui_uploader" {
  project      = google_project.project.project_id
  account_id   = var.ui_uploader_service_account_id
  display_name = "UI uploader/signer service account"
}

resource "google_storage_bucket" "models" {
  project                     = google_project.project.project_id
  name                        = var.models_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  depends_on = [google_project_service.services]
}

resource "google_storage_bucket" "data" {
  project                     = google_project.project.project_id
  name                        = var.data_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  cors {
    origin          = ["http://localhost:8000", "http://127.0.0.1:8000", "http://localhost:3000", "http://127.0.0.1:3000"]
    method          = ["GET", "HEAD", "PUT", "POST", "OPTIONS"]
    response_header = ["Content-Type", "x-goog-resumable", "x-goog-content-length-range"]
    max_age_seconds = 3600
  }

  depends_on = [google_project_service.services]
}

resource "google_storage_bucket_iam_member" "job_models_viewer" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.job.email}"
}

resource "google_storage_bucket_iam_member" "hf_downloader_models_admin" {
  bucket = google_storage_bucket.models.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.hf_downloader.email}"
}

resource "google_storage_bucket_iam_member" "job_data_admin" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.job.email}"
}

resource "google_storage_bucket_iam_member" "ui_uploader_data_admin" {
  bucket = google_storage_bucket.data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.ui_uploader.email}"
}

resource "google_service_account_iam_member" "ui_uploader_token_creator_self" {
  service_account_id = google_service_account.ui_uploader.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_service_account.ui_uploader.email}"
}

resource "google_service_account_key" "ui_uploader" {
  count              = var.create_ui_uploader_key ? 1 : 0
  service_account_id = google_service_account.ui_uploader.name
}

resource "google_artifact_registry_repository" "ai" {
  project       = google_project.project.project_id
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "Container images for video AI jobs"
  format        = "DOCKER"

  depends_on = [google_project_service.services]
}

resource "google_cloud_run_v2_job" "hf_downloader" {
  project             = google_project.project.project_id
  name                = var.hf_downloader_job_name
  location            = var.region
  deletion_protection = false

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.hf_downloader.email
      timeout         = "${var.hf_downloader_task_timeout_seconds}s"
      max_retries     = 0

      volumes {
        name = "models"
        gcs {
          bucket = google_storage_bucket.models.name
        }
      }

      containers {
        image = var.hf_downloader_container_image

        resources {
          limits = {
            cpu    = var.hf_downloader_cpu
            memory = var.hf_downloader_memory
          }
        }

        env {
          name  = "MODELS_DIR"
          value = "/models"
        }

        env {
          name  = "HF_HOME"
          value = "/tmp/huggingface"
        }

        env {
          name  = "TMP_DIR"
          value = "/tmp"
        }

        env {
          name  = "MODEL_ID"
          value = var.hf_downloader_model_id
        }

        env {
          name  = "MODELS"
          value = var.hf_downloader_models
        }

        env {
          name  = "BUCKET_NAME"
          value = google_storage_bucket.models.name
        }

        env {
          name  = "MODEL_PREFIX"
          value = var.hf_downloader_model_prefix
        }

        volume_mounts {
          name       = "models"
          mount_path = "/models"
        }
      }
    }
  }

  depends_on = [
    google_project_service.services,
    google_storage_bucket_iam_member.hf_downloader_models_admin,
  ]
}

resource "google_cloud_run_v2_job" "video_ai" {
  project             = google_project.project.project_id
  name                = var.job_name
  location            = var.region
  deletion_protection = false

  template {
    task_count  = var.task_count
    parallelism = var.parallelism

    template {
      service_account               = google_service_account.job.email
      timeout                       = "${var.task_timeout_seconds}s"
      max_retries                   = 0
      gpu_zonal_redundancy_disabled = true

      node_selector {
        accelerator = var.gpu_type
      }

      volumes {
        name = "models"
        gcs {
          bucket    = google_storage_bucket.models.name
          read_only = true
        }
      }

      volumes {
        name = "data"
        gcs {
          bucket = google_storage_bucket.data.name
        }
      }

      containers {
        image = var.container_image

        resources {
          limits = {
            cpu              = var.cpu
            memory           = var.memory
            "nvidia.com/gpu" = "1"
          }
        }

        env {
          name  = "MODELS_DIR"
          value = "/models"
        }

        env {
          name  = "DATA_DIR"
          value = "/data"
        }

        env {
          name  = "TMP_DIR"
          value = "/tmp"
        }

        env {
          name  = "INPUT_PREFIX"
          value = var.input_prefix
        }

        env {
          name  = "OUTPUT_PREFIX"
          value = var.output_prefix
        }

        volume_mounts {
          name       = "models"
          mount_path = "/models"
        }

        volume_mounts {
          name       = "data"
          mount_path = "/data"
        }
      }
    }
  }

  depends_on = [
    google_project_service.services,
    google_storage_bucket_iam_member.job_models_viewer,
    google_storage_bucket_iam_member.job_data_admin,
  ]
}

output "cloud_run_job_name" {
  value = google_cloud_run_v2_job.video_ai.name
}

output "project_id" {
  value = google_project.project.project_id
}

output "hf_downloader_cloud_run_job_name" {
  value = google_cloud_run_v2_job.hf_downloader.name
}

output "cloud_run_job_location" {
  value = google_cloud_run_v2_job.video_ai.location
}

output "service_account_email" {
  value = google_service_account.job.email
}

output "hf_downloader_service_account_email" {
  value = google_service_account.hf_downloader.email
}

output "ui_uploader_service_account_email" {
  value = google_service_account.ui_uploader.email
}

output "models_bucket" {
  value = google_storage_bucket.models.name
}

output "data_bucket" {
  value = google_storage_bucket.data.name
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.ai.name
}

output "ui_uploader_service_account_key_private_key" {
  value       = var.create_ui_uploader_key ? google_service_account_key.ui_uploader[0].private_key : null
  sensitive   = true
  description = "Base64-encoded JSON key material for the UI uploader service account (only when create_ui_uploader_key=true)."
}
