# Deployment

## Prerequisites

- Docker
- NVIDIA Container Toolkit
- An NVIDIA GPU (e.g. L4)
- VLM API credentials set in your environment

## Run

```bash
cd infra
export VLM_BASE_URL="https://api.openai.com/v1"
export VLM_API_KEY="sk-..."
export VLM_MODEL="gpt-4o-mini"
docker compose up --build
```
