output "r2_audio_bucket" {
  value = cloudflare_r2_bucket.audio.name
}

output "r2_reports_bucket" {
  value = cloudflare_r2_bucket.reports.name
}

output "r2_models_bucket" {
  value = cloudflare_r2_bucket.models.name
}

output "queue_name" {
  value = cloudflare_queue.jobs.name
}

output "quotas_kv_id" {
  value = cloudflare_workers_kv_namespace.quotas.id
}

output "pages_project" {
  value = cloudflare_pages_project.web.name
}
