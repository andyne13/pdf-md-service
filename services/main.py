from services.config import settings
from services.dispatcher import Dispatcher

app = Dispatcher.bind(
    vlm_base_url=settings.VLM_BASE_URL,
    vlm_api_key=settings.VLM_API_KEY,
    vlm_model=settings.VLM_MODEL,
    caption_prompt=settings.CAPTION_PROMPT,
    chunk_size=settings.CHUNK_SIZE,
    pool_workers=settings.POOL_WORKERS,
)
