#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import shutil
import subprocess
from io import BytesIO
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib import request

from PIL import Image, ImageDraw, ImageFont, ImageOps
import qrcode


DEFAULT_WIDTH = 1280
PAGE_PADDING = 48
CARD_PADDING = 32
CARD_GAP = 28
MAP_WIDTH = 360
MAP_HEIGHT = 220
QR_SIZE = 112
BACKGROUND = "#F5F1E8"
CARD_BG = "#FFFDF8"
TEXT = "#1F1A17"
MUTED = "#6B625A"
ACCENT = "#B85C38"
BORDER = "#E5D8C8"
PLACEHOLDER_BG = "#EFE5D7"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render activity summary image from activity-structured-geo.json.")
    parser.add_argument("--input", required=True, help="Path to activity-structured-geo.json.")
    parser.add_argument("--output", required=True, help="Path to output PNG.")
    parser.add_argument("--title", default="活动情报速递", help="Poster title.")
    parser.add_argument("--subtitle", default="", help="Optional subtitle.")
    parser.add_argument("--watermark", default="潮匠里", help="Watermark text shown at top-right.")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Canvas width in pixels.")
    parser.add_argument("--download-timeout", type=float, default=10.0, help="Timeout for remote images.")
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_paths(paths: Sequence[str]) -> List[str]:
    result: List[str] = []
    seen = set()
    for item in paths:
        expanded = str(Path(item).expanduser())
        if expanded in seen:
            continue
        if Path(expanded).exists():
            result.append(expanded)
            seen.add(expanded)
    return result


def _fc_match_font(family: str) -> str:
    if not shutil.which("fc-match"):
        return ""
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}\n", family],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    path = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return path if path and Path(path).exists() else ""


@lru_cache(maxsize=4)
def font_candidates(bold: bool = False) -> Tuple[str, ...]:
    candidates: List[str] = []

    env_keys = ["ACTIVITY_PUSH_FONT_PATH"]
    env_keys.append("ACTIVITY_PUSH_FONT_BOLD_PATH" if bold else "ACTIVITY_PUSH_FONT_REGULAR_PATH")
    for key in env_keys:
        value = os.environ.get(key, "").strip()
        if value:
            candidates.append(value)

    system = platform.system().lower()
    if system == "darwin":
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/PingFang.ttc",
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/Hiragino Sans GB.ttc",
                "/System/Library/Fonts/Supplemental/Songti.ttc",
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
                "/usr/share/fonts/opentype/noto/NotoSansSC-Bold.otf" if bold else "/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf",
                "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/noto/NotoSansSC-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoSansSC-Regular.ttf",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/arphic/uming.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ]
        )
        family_names = [
            "Noto Sans CJK SC:bold" if bold else "Noto Sans CJK SC",
            "Noto Sans SC:bold" if bold else "Noto Sans SC",
            "Source Han Sans SC Bold" if bold else "Source Han Sans SC",
            "WenQuanYi Zen Hei",
            "DejaVu Sans:style=Bold" if bold else "DejaVu Sans",
            "sans-serif:style=Bold" if bold else "sans-serif",
        ]
        candidates.extend(path for path in (_fc_match_font(name) for name in family_names) if path)

    return tuple(_existing_paths(candidates))


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in font_candidates(bold):
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_height(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> int:
    if not text:
        return 0
    box = draw.multiline_textbbox((0, 0), text, font=font, spacing=6)
    return int(math.ceil(box[3] - box[1]))


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> List[str]:
    if not text:
        return []
    lines: List[str] = []
    current = ""
    for char in text:
        candidate = current + char
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def wrap_labeled_text(
    draw: ImageDraw.ImageDraw,
    label: str,
    value: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
) -> str:
    prefix = f"{label}："
    if not value:
        return ""
    lines = wrap_text(draw, value, font, max_width - int(draw.textbbox((0, 0), prefix, font=font)[2]))
    if not lines:
        return ""
    wrapped = [f"{prefix}{lines[0]}"]
    indent = " " * len(prefix)
    wrapped.extend(f"{indent}{line}" for line in lines[1:])
    return "\n".join(wrapped)


def build_meta_lines(
    activity: Dict[str, Any],
    draw: ImageDraw.ImageDraw,
    body_font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    content_width: int,
) -> List[str]:
    time_value = build_time_text(activity)
    fields = [
        ("类型", str(activity.get("activityType", "")).strip()),
        ("时间", time_value),
        ("地点", str(activity.get("activityAddress", "")).strip()),
        ("人数", str(activity.get("activityLimitNum", "")).strip()),
        ("说明", str(activity.get("activityDescription", "")).strip()),
    ]
    lines = [wrap_labeled_text(draw, label, value, body_font, content_width) for label, value in fields if value]
    return [line for line in lines if line]


def build_time_text(activity: Dict[str, Any]) -> str:
    start = str(activity.get("activityStartTime", "")).strip()
    end = str(activity.get("activityEndTime", "")).strip()
    if start and end:
        return f"{start} - {end}"
    if start:
        return start
    if end:
        return end
    return ""

def build_qr_image(content: str, size: int = QR_SIZE) -> Optional[Image.Image]:
    if not content:
        return None
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)
    image = qr.make_image(fill_color=TEXT, back_color="white").convert("RGB")
    return ImageOps.fit(image, (size, size), method=Image.Resampling.NEAREST)


def load_image(source: str, timeout: float) -> Optional[Image.Image]:
    if not source:
        return None
    try:
        if source.startswith("file://"):
            return Image.open(source[7:]).convert("RGB")
        local_path = Path(source)
        if local_path.exists():
            return Image.open(local_path).convert("RGB")
        with request.urlopen(source, timeout=timeout) as resp:
            return Image.open(BytesIO(resp.read())).convert("RGB")
    except Exception:
        return None


def has_coordinates(activity: Dict[str, Any]) -> bool:
    lng = str(activity.get("activityLongitudeGCJ02", "")).strip()
    lat = str(activity.get("activityLatitudeGCJ02", "")).strip()
    if not lng or not lat:
        return False
    try:
        float(lng)
        float(lat)
    except ValueError:
        return False
    return True


def draw_qr_block(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    link_url: str,
    left: int,
    top: int,
    fonts: Dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont],
) -> int:
    block_box = (left, top, left + QR_SIZE, top + QR_SIZE)
    draw.rounded_rectangle(block_box, radius=22, fill="#F8F2E9", outline=BORDER, width=2)

    qr_left = left
    qr_top = top
    qr = build_qr_image(link_url, QR_SIZE)
    qr_box = (qr_left, qr_top, qr_left + QR_SIZE, qr_top + QR_SIZE)
    if qr is not None:
        image.paste(qr, (qr_left, qr_top))
        draw.rounded_rectangle(qr_box, radius=16, outline=BORDER, width=2)
    else:
        return 0
    return QR_SIZE


def draw_watermark(
    image: Image.Image,
    width: int,
    watermark: str,
    fonts: Dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont],
) -> None:
    if not watermark.strip():
        return

    overlay = Image.new("RGBA", (210, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle((10, 18, 170, 122), radius=24, outline=(184, 92, 56, 170), width=3, fill=(255, 253, 248, 135))
    draw.rounded_rectangle((22, 30, 158, 110), radius=18, outline=(184, 92, 56, 120), width=1)
    text_box = draw.textbbox((0, 0), watermark, font=fonts["watermark"])
    text_x = 90 - (text_box[2] - text_box[0]) / 2
    text_y = 70 - (text_box[3] - text_box[1]) / 2
    draw.text((text_x, text_y), watermark, fill=(184, 92, 56, 185), font=fonts["watermark"])
    draw.arc((0, 8, 178, 130), start=205, end=340, fill=(184, 92, 56, 120), width=2)
    draw.arc((2, 10, 180, 132), start=20, end=155, fill=(184, 92, 56, 90), width=2)

    rotated = overlay.rotate(-8, resample=Image.Resampling.BICUBIC, expand=True)
    paste_left = width - PAGE_PADDING - rotated.size[0]
    image.paste(rotated, (paste_left, 8), rotated)


def render_card(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    activity: Dict[str, Any],
    index: int,
    top: int,
    width: int,
    timeout: float,
    fonts: Dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont],
) -> int:
    card_left = PAGE_PADDING
    card_right = width - PAGE_PADDING
    card_inner_width = card_right - card_left - CARD_PADDING * 2

    title = f"{index}. {str(activity.get('activityName', '')).strip() or '未命名活动'}"
    source_url = str(activity.get("sourceUrl", "")).strip()
    show_map = has_coordinates(activity) and bool(str(activity.get("activityStaticMapUrl", "")).strip())
    show_qr = bool(source_url)
    show_side_column = show_map or show_qr
    text_width = card_inner_width - MAP_WIDTH - 24 if show_side_column else card_inner_width
    title_lines = wrap_text(draw, title, fonts["title"], text_width)
    meta_lines = build_meta_lines(activity, draw, fonts["body"], text_width)

    title_height = text_height(draw, "\n".join(title_lines), fonts["title"])
    meta_height = sum(text_height(draw, line, fonts["body"]) for line in meta_lines) + max(len(meta_lines) - 1, 0) * 12
    right_column_height = 0
    if show_map:
        right_column_height += MAP_HEIGHT
    if show_qr:
        if right_column_height:
            right_column_height += 28
        right_column_height += QR_SIZE
    content_height = max(title_height + 20 + meta_height, right_column_height)
    card_height = CARD_PADDING * 2 + content_height

    card_box = (card_left, top, card_right, top + card_height)
    draw.rounded_rectangle(card_box, radius=28, fill=CARD_BG, outline=BORDER, width=2)

    content_left = card_left + CARD_PADDING
    content_top = top + CARD_PADDING
    side_left = card_right - CARD_PADDING - MAP_WIDTH
    side_top = content_top

    draw.multiline_text(
        (content_left, content_top),
        "\n".join(title_lines),
        fill=TEXT,
        font=fonts["title"],
        spacing=8,
    )

    line_top = content_top + title_height + 20
    for line in meta_lines:
        draw.multiline_text((content_left, line_top), line, fill=TEXT, font=fonts["body"], spacing=6)
        line_top += text_height(draw, line, fonts["body"]) + 12

    if show_map:
        map_box = (side_left, side_top, side_left + MAP_WIDTH, side_top + MAP_HEIGHT)
        static_map = load_image(str(activity.get("activityStaticMapUrl", "")).strip(), timeout)
        if static_map is not None:
            fitted = ImageOps.fit(static_map, (MAP_WIDTH, MAP_HEIGHT), method=Image.Resampling.LANCZOS)
            image.paste(fitted, (side_left, side_top))
            draw.rounded_rectangle(map_box, radius=24, outline=BORDER, width=2)

    if show_qr:
        qr_top = side_top + (MAP_HEIGHT + 28 if show_map else 0)
        draw_qr_block(image, draw, source_url, side_left, qr_top, fonts)
    return top + card_height + CARD_GAP


def build_empty_state(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    width: int,
    top: int,
    fonts: Dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont],
) -> int:
    card_box = (PAGE_PADDING, top, width - PAGE_PADDING, top + 220)
    draw.rounded_rectangle(card_box, radius=28, fill=CARD_BG, outline=BORDER, width=2)
    title = "最近 24 小时未发现新的活动文章"
    body = "可保留这张图作为当天空结果的归档凭证。"
    draw.text((PAGE_PADDING + CARD_PADDING, top + 56), title, fill=TEXT, font=fonts["title"])
    draw.text((PAGE_PADDING + CARD_PADDING, top + 120), body, fill=MUTED, font=fonts["body"])
    return top + 220


def estimate_total_height(
    activities: Sequence[Dict[str, Any]],
    width: int,
    fonts: Dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont],
) -> int:
    probe = Image.new("RGB", (width, 10), BACKGROUND)
    draw = ImageDraw.Draw(probe)
    top = PAGE_PADDING + 140
    if not activities:
        return build_empty_state(probe, draw, width, top, fonts) + PAGE_PADDING

    for index, activity in enumerate(activities, start=1):
        top = render_card(probe, draw, activity, index, top, width, timeout=0, fonts=fonts)
    return top + PAGE_PADDING


def render_header(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    width: int,
    title: str,
    subtitle: str,
    count: int,
    watermark: str,
    fonts: Dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont],
) -> None:
    draw.text((PAGE_PADDING, PAGE_PADDING), title, fill=TEXT, font=fonts["headline"])
    meta = subtitle.strip() if subtitle.strip() else f"共 {count} 条活动"
    draw.text((PAGE_PADDING, PAGE_PADDING + 62), meta, fill=MUTED, font=fonts["body"])
    draw_watermark(image, width, watermark, fonts)
    draw.line((PAGE_PADDING, PAGE_PADDING + 108, width - PAGE_PADDING, PAGE_PADDING + 108), fill=BORDER, width=2)


def run_render(args: argparse.Namespace) -> Path:
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = read_json(input_path)
    if not isinstance(data, list):
        raise RuntimeError("input must be a JSON array")

    fonts = {
        "headline": load_font(42, bold=True),
        "title": load_font(31, bold=True),
        "section": load_font(24, bold=True),
        "body": load_font(20),
        "small": load_font(15),
        "watermark": load_font(36, bold=True),
    }
    height = estimate_total_height(data, args.width, fonts)
    image = Image.new("RGB", (args.width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    render_header(
        image,
        draw,
        args.width,
        args.title,
        args.subtitle,
        len(data),
        getattr(args, "watermark", "潮匠里"),
        fonts,
    )
    top = PAGE_PADDING + 140
    if not data:
        build_empty_state(image, draw, args.width, top, fonts)
    else:
        for index, activity in enumerate(data, start=1):
            top = render_card(image, draw, activity, index, top, args.width, args.download_timeout, fonts)

    image.save(output_path, format="PNG")
    return output_path


def main() -> int:
    args = parse_args()
    run_render(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
