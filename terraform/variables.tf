variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone"
  type        = string
  default     = "us-central1-a"
}

variable "machine_type" {
  description = "Machine type for GPU VM"
  type        = string
  default     = "n1-standard-8"
}

variable "disk_size_gb" {
  description = "Boot disk size for GPU VM in GB"
  type        = number
  default     = 100
}

variable "gpu_type" {
  description = "GPU accelerator type"
  type        = string
  default     = "nvidia-tesla-t4"
}

variable "repo_url" {
  description = "Git repository URL to clone on VMs"
  type        = string
}

variable "webapp_machine_type" {
  description = "Machine type for webapp CPU VM"
  type        = string
  default     = "e2-small"
}
