output "project_id" {
  description = "GCP project ID"
  value       = var.project_id
}

output "zone" {
  description = "GCP zone"
  value       = var.zone
}

output "gpu_vm_external_ip" {
  description = "External IP of the GPU VM"
  value       = google_compute_instance.gpu_vm.network_interface[0].access_config[0].nat_ip
}

output "gpu_vm_internal_ip" {
  description = "Internal IP of the GPU VM"
  value       = google_compute_instance.gpu_vm.network_interface[0].network_ip
}

output "webapp_vm_external_ip" {
  description = "External IP of the webapp VM"
  value       = google_compute_instance.webapp_vm.network_interface[0].access_config[0].nat_ip
}

output "distilbert_endpoint" {
  description = "DistilBERT inference endpoint"
  value       = "http://${google_compute_instance.gpu_vm.network_interface[0].access_config[0].nat_ip}:8001"
}

output "resnet50_endpoint" {
  description = "ResNet-50 inference endpoint"
  value       = "http://${google_compute_instance.gpu_vm.network_interface[0].access_config[0].nat_ip}:8002"
}

output "prometheus_url" {
  description = "Prometheus web UI"
  value       = "http://${google_compute_instance.gpu_vm.network_interface[0].access_config[0].nat_ip}:9090"
}

output "metrics_agent_url" {
  description = "Metrics agent Prometheus endpoint"
  value       = "http://${google_compute_instance.gpu_vm.network_interface[0].access_config[0].nat_ip}:8080/metrics"
}

output "webapp_url" {
  description = "Web application URL"
  value       = "http://${google_compute_instance.webapp_vm.network_interface[0].access_config[0].nat_ip}:5000"
}

output "ssh_gpu_vm" {
  description = "SSH command for GPU VM"
  value       = "gcloud compute ssh ml-serving-gpu-vm --zone=${var.zone} --project=${var.project_id}"
}

output "ssh_webapp_vm" {
  description = "SSH command for webapp VM"
  value       = "gcloud compute ssh ml-serving-webapp-vm --zone=${var.zone} --project=${var.project_id}"
}
