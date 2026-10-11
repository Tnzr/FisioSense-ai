variable "modal_token_id" {
  type      = string
  sensitive = true
}

variable "modal_token_secret" {
  type      = string
  sensitive = true
}

variable "secret_name" {
  type    = string
  default = "asculto-llm"
}

variable "secret_version" {
  type    = string
  default = "1"
}

variable "llm_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "llm_base_url" {
  type    = string
  default = "https://api.openai.com/v1"
}

variable "app_file" {
  type    = string
  default = "deploy/worker-modal.py"
}

variable "repo_root" {
  type    = string
  default = "."
}

variable "deploy_revision" {
  type    = string
  default = "1"
}
