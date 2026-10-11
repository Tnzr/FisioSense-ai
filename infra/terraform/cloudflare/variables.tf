variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "account_id" {
  type = string
}

variable "zone_id" {
  type        = string
  description = "Cloudflare zone for the Asculto domain"
  default     = ""
}

variable "domain" {
  type        = string
  description = "Apex domain, e.g. asculto.com (leave empty before registration)"
  default     = ""
}

variable "workers_subdomain" {
  type    = string
  default = "asculto"
}

variable "project" {
  type    = string
  default = "asculto"
}

variable "environment" {
  type    = string
  default = "prod"
}

variable "r2_location" {
  type        = string
  description = "R2 location hint; EU-first per plan A2"
  default     = "EEUR"
}
