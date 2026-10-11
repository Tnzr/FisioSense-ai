terraform {
  required_version = ">= 1.6"
  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.9"
    }
  }
  backend "s3" {}
}

provider "neon" {
  api_key = var.neon_api_key
}

resource "neon_project" "app" {
  name       = var.project
  region_id  = var.region_id # EU-first per plan A2
  pg_version = var.pg_version

  # scale-to-zero friendly; tune retention to your audit needs
  history_retention_seconds = var.history_retention_seconds
}

resource "neon_role" "app" {
  project_id = neon_project.app.id
  branch_id  = neon_project.app.default_branch_id
  name       = "${var.project}_app"
}

resource "neon_database" "app" {
  project_id = neon_project.app.id
  branch_id  = neon_project.app.default_branch_id
  name       = var.project
  owner_name = neon_role.app.name
}
