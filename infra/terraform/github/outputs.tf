output "repo_full_name" {
  value = github_repository.repo.full_name
}

output "repo_ssh_url" {
  value = github_repository.repo.ssh_clone_url
}
