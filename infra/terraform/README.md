# Asculto Stage-1 infrastructure (Terraform)

One root module per provider, applied in order. Remote state is stored in
Cloudflare R2 (S3-compatible) and one workspace is used per environment.

```text
cloudflare/   R2 buckets, Queues, KV, Pages, DNS        (apply first: also holds state)
neon/         Neon Postgres project/branch/db/role      (EU region)
modal/        Modal secret + deploy hook                (batch/GPU)
github/       repo settings, branch protection, secrets (CI/CD wiring)
envs/         shared *.tfvars
```

## Backend (R2)

Each module reads `backend.hcl` (gitignored; copy from `backend.hcl.example`):

```hcl
bucket = "asculto-tfstate"
key    = "cloudflare/terraform.tfstate"
region = "auto"
endpoints = { s3 = "https://<account_id>.r2.cloudflarestorage.com" }
access_key = "<R2 access key id>"
secret_key = "<R2 secret access key>"
skip_credentials_validation = true
skip_region_validation      = true
skip_requesting_account_id  = true
```

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
cd cloudflare && terraform init -backend-config=backend.hcl
terraform plan  -var-file=../envs/prod.tfvars
terraform apply -var-file=../envs/prod.tfvars
```

## Data residency

EU-first (plan A2): set `r2_location = "EEUR"`, Neon `region_id = "aws-eu-central-1"`,
and pin compute to EU. Adding US later is a transfer/compliance change, not a
schema change.

## Validation

```bash
terraform fmt -recursive
terraform validate
```

State is encrypted at rest by R2 (SSE) and never committed.
