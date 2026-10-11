variable "neon_api_key" {
  type      = string
  sensitive = true
}

variable "project" {
  type    = string
  default = "asculto"
}

variable "region_id" {
  type        = string
  description = "Neon region; EU-first per plan A2"
  default     = "aws-eu-central-1"
}

variable "pg_version" {
  type    = number
  default = 17
}

variable "history_retention_seconds" {
  type    = number
  default = 21600
}
