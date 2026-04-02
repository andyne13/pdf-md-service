import os

DEFAULT_CAPTION_PROMPT = """\
You are an expert in image description.

## Rules
- Use the language shown in the image.
- Do not describe colors, shapes, or styles unless they are part of the data.
- Never add, infer, or translate information.

## 1. Simple / Non-informative images
- If there is no text or the image is non-informative at all → output "[Image Placeholder]".
- If it contains text → transcribe it exactly, using Markdown if structured (headings, lists, emphasis).
- If it's a logo with text → output only the textual content

## 2. Informative content: tables, charts, diagrams, interfaces, or structured documents.
  1. Transcribe all numerical and categorical values and Format it as markdown structured table.
  2. Provide a concise description of what the graph represents.
  3. Highlight trends, patterns, and key conclusions.

## Output
The output must remain factual, concise, and strictly limited to what is visible in the image."""


class Settings:
    def __init__(self):
        self.VLM_BASE_URL = self._require("VLM_BASE_URL")
        self.VLM_API_KEY = self._require("VLM_API_KEY")
        self.VLM_MODEL = self._require("VLM_MODEL")
        self.CAPTION_PROMPT = os.getenv("CAPTION_PROMPT", DEFAULT_CAPTION_PROMPT)
        self.POOL_WORKERS = int(os.getenv("POOL_WORKERS", "4"))
        self.CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "10"))

    @staticmethod
    def _require(name: str) -> str:
        value = os.getenv(name)
        if not value:
            raise RuntimeError(f"Required environment variable {name} is not set")
        return value


settings = Settings()
