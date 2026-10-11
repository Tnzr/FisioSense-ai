output "project_id" {
  value = neon_project.app.id
}

output "database" {
  value = neon_database.app.name
}

output "role" {
  value = neon_role.app.name
}

output "connection_host" {
  value     = neon_project.app.database_host
  sensitive = true
}
