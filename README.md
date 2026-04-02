# pdf-md-service

PDF to Markdown conversion service using [marker-pdf](https://github.com/VikParuchuri/marker) on GPU, with optional VLM image captioning via an OpenAI-compatible API.

## Architecture

```
                          +-----------------+
  batch_convert.py -----> |   API (FastAPI) | :8080
  (uploads PDFs,          |   lightweight   |
   receives results       |   proxy         |
   via webhook)           +--------+--------+
                                   |
                          +--------v--------+
                          | Ray Serve       | :8000
                          | Dispatcher      |
                          |   |             |
                          |   v             |
                          | MarkerWorker    |  GPU + ProcessPoolExecutor
                          | Actor           |  (shared CUDA memory via IPC)
                          +-----------------+
                                   |
                          +--------v--------+
                          | VLM API         |  (optional, external)
                          | image captioning|
                          +-----------------+
```

- **ray-serve**: Runs marker-pdf on GPU. Models are loaded once and shared across worker processes via `share_memory()`. Large PDFs are chunked by page ranges and processed in parallel.
- **api**: Thin FastAPI gateway that proxies requests to Ray Serve.
- **batch_convert.py**: CLI client that uploads a folder of PDFs and collects results via webhook callbacks.

## Prerequisites

- NVIDIA GPU with Docker support (`nvidia-container-toolkit` installed)
- Docker and Docker Compose
- An OpenAI-compatible VLM endpoint for image captioning (or use `--no-caption` to skip)

## Setup

### 1. Clone the repo

```bash
git clone git@github.com:YOUR_USERNAME/pdf-md-service.git
cd pdf-md-service
```

### 2. Configure environment

Create `infra/.env`:

```bash
VLM_BASE_URL=https://your-vlm-endpoint/v1/
VLM_API_KEY=your-api-key
VLM_MODEL=Qwen2.5-VL-7B-Instruct
# Optional:
# POOL_WORKERS=2        # marker-pdf parallel workers (default: 4, use 2 for 24GB GPUs)
# CHUNK_SIZE=10         # pages per chunk for large PDFs (default: 10)
```

### 3. Build and start

```bash
cd infra
docker compose up -d --build
```

The `ray-serve` container takes ~2 minutes to initialize (model loading). Monitor with:

```bash
docker compose logs -f ray-serve
```

Wait until you see `Dispatcher initialized` in the logs.

### 4. Verify

```bash
curl http://localhost:8080/health
# {"status":"ok"}
```

Ray dashboard is available at `http://localhost:8265`.

## Usage

### Batch conversion (recommended)

Convert an entire folder of PDFs from any machine that can reach the server:

```bash
python batch_convert.py \
  --folder /path/to/your/pdfs \
  --server http://SERVER_IP:8080 \
  --webhook-host YOUR_LOCAL_IP \
  --port 9001 \
  --output /path/to/output
```

**Arguments:**

| Argument | Description |
|---|---|
| `--folder` | Directory containing PDF files |
| `--server` | API server URL (e.g. `http://192.168.1.100:8080`) |
| `--webhook-host` | IP/hostname the server can reach your machine on |
| `--port` | Local port for the webhook receiver (default: 9001) |
| `--output` | Output directory for .md files (default: same as `--folder`) |
| `--no-caption` | Skip VLM image captioning (faster) |

**Running from the same server:**

Use the Docker bridge IP as the webhook host:

```bash
python batch_convert.py \
  --folder /path/to/pdfs \
  --server http://localhost:8080 \
  --webhook-host 172.18.0.1 \
  --port 9001
```

Install client dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run batch_convert.py --folder ./test_pdfs --server http://localhost:8080 --webhook-host 172.18.0.1
```

### API endpoint

You can also call the API directly:

```
POST /convert-batch
Content-Type: multipart/form-data

files:    (one or more PDF files)
webhook_url:  http://your-host:port/webhook
caption:  true|false
```

The server processes PDFs asynchronously and sends results to the webhook URL with these statuses:
- `progress` - per-PDF result as each completes
- `converted` - raw markdown before captioning
- `finished` - batch complete

## Performance tuning

| Setting | Recommendation |
|---|---|
| `POOL_WORKERS=2` | For 24GB GPUs (L4, RTX 4090). Avoids GPU OOM. |
| `POOL_WORKERS=4` | For 48GB+ GPUs (A6000, A100). |
| `--no-caption` | Skips VLM calls. Much faster if you only need raw markdown. |
| `CHUNK_SIZE=10` | Default. Larger values = fewer chunks but less parallelism. |

## Pinned dependencies

The following versions are pinned for performance reasons:

- `marker-pdf==1.8.2` - newer versions are significantly slower and break `share_memory()`
- `torch==2.7.1` - matched to marker-pdf 1.8.2 for GPU memory sharing

Do not upgrade these without benchmarking.

## Stopping

```bash
cd infra
docker compose down
```
