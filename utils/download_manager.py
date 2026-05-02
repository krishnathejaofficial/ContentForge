"""
utils/download_manager.py — Package final output (video + metadata) into a ZIP.
"""
import json
import zipfile
from pathlib import Path
from typing import Dict


def create_download_package(
    video_path: str,
    metadata: Dict,
    output_dir: str = "output"
) -> str:
    """
    Creates a ZIP file containing:
    - The rendered video (.mp4)
    - caption.txt  (platform-specific captions)
    - metadata.json (full metadata)

    Returns the path to the ZIP file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    base_name = Path(video_path).stem
    zip_path = output_dir / f"{base_name}_package.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add video
        if Path(video_path).exists():
            zf.write(video_path, arcname=Path(video_path).name)

        # Add caption text
        caption_text = _build_caption_text(metadata)
        zf.writestr("caption.txt", caption_text)

        # Add metadata JSON
        zf.writestr("metadata.json", json.dumps(metadata, indent=2, ensure_ascii=False))

    return str(zip_path)


def _build_caption_text(metadata: Dict) -> str:
    lines = []
    lines.append("=== ContentForge Export ===\n")

    if "platforms" in metadata:
        for platform, data in metadata["platforms"].items():
            lines.append(f"\n--- {platform.upper()} ---")
            if "caption" in data:
                lines.append(data["caption"])
            elif "title" in data:
                lines.append(f"Title: {data['title']}")
                lines.append(f"Description: {data.get('description','')}")

    lines.append("\n\n=== Hashtags ===")
    hashtags = metadata.get("hashtags", [])
    if hashtags:
        lines.append(" ".join(f"#{h}" for h in hashtags))

    return "\n".join(lines)
