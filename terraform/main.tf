terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5.0"
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# --- Networking ---

resource "google_compute_network" "ml_vpc" {
  name                    = "ml-serving-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "ml_subnet" {
  name          = "ml-serving-subnet"
  ip_cidr_range = "10.0.1.0/24"
  region        = var.region
  network       = google_compute_network.ml_vpc.id
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "ml-serving-allow-ssh"
  network = google_compute_network.ml_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ml-serving"]
}

resource "google_compute_firewall" "allow_ml_ports" {
  name    = "ml-serving-allow-ml-ports"
  network = google_compute_network.ml_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["8001", "8002", "8080", "9090", "5000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["ml-serving"]
}

# --- Service Account ---

resource "google_service_account" "ml_serving" {
  account_id   = "ml-serving-sa"
  display_name = "ML Serving Service Account"
}

resource "google_project_iam_member" "logging_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.ml_serving.email}"
}

# --- GPU VM ---

resource "google_compute_instance" "gpu_vm" {
  name         = "ml-serving-gpu-vm"
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["ml-serving"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-ssd"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.ml_subnet.id
    access_config {} # Ephemeral public IP
  }

  guest_accelerator {
    type  = var.gpu_type
    count = 1
  }

  scheduling {
    on_host_maintenance = "TERMINATE"
    automatic_restart   = true
  }

  service_account {
    email  = google_service_account.ml_serving.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile("${path.module}/startup-gpu.sh", {
      repo_url = var.repo_url
    })
  }
}

# --- CPU Webapp VM ---

resource "google_compute_instance" "webapp_vm" {
  name         = "ml-serving-webapp-vm"
  machine_type = var.webapp_machine_type
  zone         = var.zone
  tags         = ["ml-serving"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      size  = 20
      type  = "pd-standard"
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.ml_subnet.id
    access_config {} # Ephemeral public IP
  }

  service_account {
    email  = google_service_account.ml_serving.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile("${path.module}/startup-webapp.sh", {
      repo_url   = var.repo_url
      gpu_vm_ip  = google_compute_instance.gpu_vm.network_interface[0].network_ip
    })
  }

  depends_on = [google_compute_instance.gpu_vm]
}
