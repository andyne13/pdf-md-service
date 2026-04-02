FROM nvidia/cuda:12.2.0-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    python3 python3-pip git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY infra/ray_serve/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY core/ core/
COPY services/ services/

COPY infra/ray_serve/start.sh .
COPY infra/ray_serve/serve_config.yaml .
RUN chmod +x start.sh

CMD ["./start.sh"]
