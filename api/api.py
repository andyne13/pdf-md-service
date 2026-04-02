import os
from fastapi import FastAPI, UploadFile, File, Form
import httpx

app = FastAPI(title="PDF → Markdown Batch API")

RAY_SERVE_URL = os.getenv(
    "RAY_SERVE_URL",
    "http://ray-serve:8000/PdfToMarkdownService",
)


@app.post("/convert-batch")
async def convert_batch(
    files: list[UploadFile] = File(...),
    webhook_url: str = Form(...),
    caption: str = Form("true"),
):
    data = {"webhook_url": webhook_url, "caption": caption}

    multipart_files = [
        ("files", (f.filename, await f.read(), f.content_type))
        for f in files
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(RAY_SERVE_URL, data=data, files=multipart_files)

    return resp.json()


@app.get("/health")
async def health():
    return {"status": "ok"}
