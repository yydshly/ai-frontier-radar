#!/usr/bin/env python
"""Build a montage image from generated scene PNGs for visual debugging.

Usage:
    python scripts/make_content_video_montage.py <video_dir>

Arguments:
    video_dir  — e.g. runtime/generated_videos/radar_2026-06-12/<input_hash>

Output:
    <video_dir>/montage.jpg

The montage shows all scenes scaled to 270x480 in a grid (3 per row),
with the scene filename and scene_type above each thumbnail.
After generation, prints: "请打开 montage.jpg 进行视觉验收"
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_montage(video_dir: Path, thumb_w: int = 270, thumb_h: int = 480, per_row: int = 3) -> Path | None:
    """Build a montage of scene PNGs in video_dir.

    Returns the path to the output montage.jpg, or None if scenes/ not found.
    """
    from PIL import Image, ImageDraw, ImageFont

    scenes_dir = video_dir / "scenes"
    if not scenes_dir.exists():
        print(f"未找到 scenes 目录: {scenes_dir}")
        print("请设置 CONTENT_VIDEO_KEEP_INTERMEDIATE=true 后重新生成。")
        return None

    # Collect scene PNGs sorted by name
    scene_files = sorted(scenes_dir.glob("scene_*.png"))
    if not scene_files:
        print(f"未找到 scene_*.png 文件 in {scenes_dir}")
        return None

    print(f"找到 {len(scene_files)} 个 scene 文件")

    # Load and resize each scene
    thumbs = []
    for sf in scene_files:
        try:
            img = Image.open(sf)
            img.thumbnail((thumb_w, thumb_h), Image.LANCZOS)
            # Store scene_id extracted from filename e.g. scene_01
            scene_id = sf.stem
            thumbs.append((scene_id, img))
        except Exception as exc:
            print(f"  跳过 {sf.name}: {exc}")
            continue

    if not thumbs:
        print("没有可用的 scene 图片")
        return None

    rows_needed = (len(thumbs) + per_row - 1) // per_row
    spacer = 10
    header_h = 50
    label_h = 30
    bg_color = (10, 10, 15)
    header_color = (52, 211, 153)

    montage_w = per_row * thumb_w + (per_row + 1) * spacer
    montage_h = header_h + rows_needed * (thumb_h + label_h + spacer) + spacer

    montage = Image.new("RGB", (montage_w, montage_h), bg_color)
    draw = ImageDraw.Draw(montage)

    # Draw header
    try:
        header_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 18)
    except Exception:
        header_font = ImageFont.load_default()
    header_text = "Content Video Storyboard Montage"
    hbbox = draw.textbbox((0, 0), header_text, font=header_font)
    hx = (montage_w - (hbbox[2] - hbbox[0])) // 2
    draw.text((hx, 14), header_text, font=header_font, fill=header_color)

    # Draw thin accent line under header
    draw.rectangle([(spacer, header_h - 2), (montage_w - spacer, header_h - 1)], fill=header_color)

    for idx, (scene_id, img) in enumerate(thumbs):
        row = idx // per_row
        col = idx % per_row
        x = spacer + col * (thumb_w + spacer)
        y = header_h + spacer + row * (thumb_h + label_h + spacer)

        # Paste thumbnail (centered in its cell)
        offset_x = x + (thumb_w - img.width) // 2
        offset_y = y + label_h + (thumb_h - img.height) // 2
        if img.mode == "RGBA":
            montage.paste(img, (offset_x, offset_y), img.split()[3])
        else:
            montage.paste(img, (offset_x, offset_y))

        # Draw label above thumbnail
        try:
            label_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 13)
        except Exception:
            label_font = ImageFont.load_default()
        label_draw = ImageDraw.Draw(montage)
        # Scene id label
        label_draw.text((x + 4, y + 4), scene_id, fill=(160, 160, 160), font=label_font)

    output_path = video_dir / "montage.jpg"
    try:
        montage.save(str(output_path), format="JPEG", quality=85)
        print(f"已生成 montage: {output_path}")
        print("请打开 montage.jpg 进行视觉验收")
        return output_path
    except Exception as exc:
        print(f"保存 montage 失败: {exc}")
        return None


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/make_content_video_montage.py <video_dir>")
        print("示例: python scripts/make_content_video_montage.py runtime/generated_videos/radar_2026-06-12/01b04108ed4401a7")
        return 1

    video_dir = Path(sys.argv[1]).resolve()
    if not video_dir.is_dir():
        print(f"目录不存在: {video_dir}")
        return 1

    result = make_montage(video_dir)
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
