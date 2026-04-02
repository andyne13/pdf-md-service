from typing import List, Dict


def inject_captions(markdown: str, images: List[Dict], captions: List[str]) -> str:
    """
    Replace bare image references ![](path) with <image_description> tags
    containing VLM-generated captions. Produces text-only markdown suitable
    for LLM consumption (no dangling image paths).
    """
    for img, caption in zip(images, captions):
        if not caption:
            continue
        target = f"![]({img['path']})"
        replacement = f"<image_description>{caption}</image_description>"
        markdown = markdown.replace(target, replacement)
    return markdown
