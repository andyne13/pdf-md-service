import argparse
import asyncio
import uvicorn
import httpx
from fastapi import FastAPI, Request
from pathlib import Path
import time

# -------------------------
# Webhook receiver
# -------------------------

app = FastAPI()
finished_event = asyncio.Event()
pdf_file_map = {}
output_dir = None
completed_count = 0
total_count = 0
start_time = 0


@app.post("/webhook")
async def webhook(request: Request):
    global completed_count
    payload = await request.json()
    status = payload.get("status")

    if status == "converted":
        filename = payload["filename"]
        index = payload["index"]
        result = payload.get("result")
        elapsed = time.time() - start_time

        if result is not None and index in pdf_file_map:
            out_path = output_dir / pdf_file_map[index].with_suffix(".md").name
            out_path.write_text(result, encoding="utf-8")
            chars = len(result)
            print(f"  [CONVERTED] {filename} -> {out_path.name} ({chars} chars, {elapsed:.1f}s)")
        else:
            print(f"  [CONVERTED] {filename} FAILED ({elapsed:.1f}s)")

    elif status == "progress":
        filename = payload["filename"]
        index = payload["index"]
        result = payload.get("result")
        completed_count = payload.get("completed", completed_count + 1)
        total = payload.get("total", total_count)
        elapsed = time.time() - start_time

        if result is not None and index in pdf_file_map:
            out_path = output_dir / pdf_file_map[index].with_suffix(".md").name
            out_path.write_text(result, encoding="utf-8")
            chars = len(result)
            print(
                f"  [DONE {completed_count}/{total}] {filename} -> {out_path.name}"
                f" ({chars} chars, {elapsed:.1f}s)"
            )
        else:
            print(f"  [DONE {completed_count}/{total}] {filename} FAILED ({elapsed:.1f}s)")

    elif status == "finished":
        finished_event.set()

    elif status == "error":
        print(f"  ERROR: {payload.get('error', 'unknown')}")
        finished_event.set()

    return {"status": "ok"}


# -------------------------
# Client logic
# -------------------------

async def send_batch(pdf_files, server_url: str, webhook_url: str, caption: bool = True):
    async with httpx.AsyncClient(timeout=300) as client:
        files = [
            ("files", (pdf.name, pdf.read_bytes(), "application/pdf"))
            for pdf in pdf_files
        ]

        data = {"webhook_url": webhook_url, "caption": str(caption).lower()}

        print(f"Uploading batch of {len(pdf_files)} PDFs (caption={caption})...")
        resp = await client.post(f"{server_url}/convert-batch", data=data, files=files)
        resp.raise_for_status()
        print(f" -> Server accepted batch: {resp.json()}")


async def convert_folder(
    folder: Path, server_url: str, port: int, webhook_host: str,
    caption: bool = True, out_dir: Path = None,
):
    global pdf_file_map, output_dir, total_count, start_time

    # Start webhook server
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    webhook_url = f"http://{webhook_host}:{port}/webhook"

    pdf_files = sorted(folder.glob("*.pdf"))
    if not pdf_files:
        print("No PDF files found.")
        server.should_exit = True
        await server_task
        return

    output_dir = out_dir or folder
    output_dir.mkdir(parents=True, exist_ok=True)

    total_count = len(pdf_files)
    pdf_file_map = {i: pdf for i, pdf in enumerate(pdf_files)}

    print(f"Found {total_count} PDFs to convert.")
    print(f"Output: {output_dir.resolve()}")
    print(f"Webhook: {webhook_url}")
    print()

    start_time = time.time()

    await send_batch(pdf_files, server_url, webhook_url, caption=caption)
    print(f"\nProcessing...\n")

    await finished_event.wait()

    total_time = time.time() - start_time
    saved = len(list(output_dir.glob("*.md")))
    print(f"\nDone in {total_time:.1f}s ({saved}/{total_count} saved to {output_dir.resolve()})")

    server.should_exit = True
    await server_task


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch PDF -> Markdown converter")
    parser.add_argument("--folder", required=True, help="Folder containing PDFs")
    parser.add_argument("--server", required=True, help="API server URL, e.g. http://1.2.3.4:8080")
    parser.add_argument("--port", type=int, default=9001, help="Local webhook port")
    parser.add_argument(
        "--webhook-host", required=True,
        help="IP/hostname the server can reach this machine on (e.g. 192.168.1.50)",
    )
    parser.add_argument("--output", help="Output directory (default: same as --folder)")
    parser.add_argument("--no-caption", action="store_true", help="Disable VLM image captioning")
    args = parser.parse_args()

    asyncio.run(convert_folder(
        Path(args.folder), args.server, args.port, args.webhook_host,
        caption=not args.no_caption,
        out_dir=Path(args.output) if args.output else None,
    ))
