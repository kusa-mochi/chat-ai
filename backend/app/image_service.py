from __future__ import annotations

import html
import uuid
from pathlib import Path

from app.config import Settings


class ImageService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.output_dir = Path(settings.generated_images_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_image(self, prompt: str, source_text: str) -> str:
      # LAN-only mode: keep image generation local without external providers.
      _ = prompt
      return self._write_placeholder_svg(source_text)

    def _write_placeholder_svg(self, source_text: str) -> str:
        safe = html.escape(source_text[:220])
        filename = f"{uuid.uuid4()}.svg"
        file_path = self.output_dir / filename
        svg = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1024\" height=\"1024\" viewBox=\"0 0 1024 1024\">
  <defs>
    <linearGradient id=\"g\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">
      <stop offset=\"0%\" stop-color=\"#11223a\" />
      <stop offset=\"100%\" stop-color=\"#2d4f73\" />
    </linearGradient>
  </defs>
  <rect width=\"1024\" height=\"1024\" fill=\"url(#g)\" />
  <rect x=\"80\" y=\"80\" width=\"864\" height=\"864\" rx=\"24\" fill=\"rgba(255,255,255,0.08)\" />
  <text x=\"120\" y=\"210\" fill=\"#f7fafc\" font-size=\"46\" font-family=\"serif\">Story Illustration Preview</text>
  <foreignObject x=\"120\" y=\"280\" width=\"784\" height=\"540\">
    <div xmlns=\"http://www.w3.org/1999/xhtml\" style=\"color:#e2e8f0;font-size:34px;line-height:1.4;font-family:serif;\">{safe}</div>
  </foreignObject>
</svg>
"""
        file_path.write_text(svg, encoding="utf-8")
        return f"/generated-images/{filename}"
