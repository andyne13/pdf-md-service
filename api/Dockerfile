FROM python:3.11-slim

WORKDIR /app

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/api.py .

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]

