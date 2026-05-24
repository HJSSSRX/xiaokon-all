#!/usr/bin/env python3
"""OCR引擎 — 基于Tesseract的文字识别"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytesseract
from PIL import Image

# Tesseract安装路径 (Windows)
TESSERACT_PATH = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
if TESSERACT_PATH.exists():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_PATH)


@dataclass
class OCRResult:
    text: str = ""
    language: str = "unknown"
    confidence: float = 0.0
    blocks: list = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "confidence": self.confidence,
            "blocks_count": len(self.blocks),
            "error": self.error,
        }


def image_to_text(
    image_path: str,
    lang: str = "chi_sim+eng",
    config: str = "--psm 3",
) -> OCRResult:
    """识别图片中的文字"""
    img = Path(image_path)
    if not img.exists():
        return OCRResult(error=f"文件不存在: {image_path}")

    try:
        image = Image.open(img)
        data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
        text = " ".join(
            word for word in data.get("text", []) if word.strip()
        )
        conf_values = [int(c) for c in data.get("conf", []) if c != "-1"]
        avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0

        blocks = _parse_blocks(data)

        return OCRResult(
            text=text,
            language=lang,
            confidence=round(avg_conf, 1),
            blocks=blocks,
        )
    except Exception as e:
        return OCRResult(error=str(e))


def image_to_data(image_path: str, lang: str = "chi_sim+eng") -> OCRResult:
    """识别图片中的文字并返回带位置信息的结构化数据"""
    img = Path(image_path)
    if not img.exists():
        return OCRResult(error=f"文件不存在: {image_path}")

    try:
        image = Image.open(img)
        data = pytesseract.image_to_data(image, lang=lang, output_type=pytesseract.Output.DICT)

        blocks = _parse_blocks(data)
        text = " ".join(b["text"] for b in blocks if b["text"].strip())

        conf_values = [b["conf"] for b in blocks if b["conf"] > 0]
        avg_conf = sum(conf_values) / len(conf_values) if conf_values else 0.0

        return OCRResult(
            text=text,
            language=lang,
            confidence=round(avg_conf, 1),
            blocks=blocks,
        )
    except Exception as e:
        return OCRResult(error=str(e))


def screenshot_to_text(
    image_path: str, lang: str = "chi_sim+eng"
) -> OCRResult:
    """识别截图中的文字（自动优化）"""
    return image_to_text(
        image_path,
        lang=lang,
        config="--psm 6",
    )


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python ocr.py <image_path> [lang]")
        print("  lang 默认: chi_sim+eng")
        sys.exit(1)

    image_path = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else "chi_sim+eng"

    result = image_to_text(image_path, lang=lang)
    if result.error:
        print(f"[ERROR] {result.error}")
    else:
        print(f"=== OCR Result (置信度: {result.confidence}%) ===")
        print(result.text)


def _parse_blocks(data: dict) -> list[dict]:
    """将tesseract的原始输出data解析为可用的block列表"""
    blocks = []
    current_block = None

    for i in range(len(data.get("text", []))):
        block_num = data["block_num"][i]
        text = (data["text"][i] or "").strip()
        if not text:
            continue

        conf = data["conf"][i]
        conf_val = int(conf) if conf != "-1" else 0

        if current_block is None or current_block["block_num"] != block_num:
            current_block = {
                "block_num": block_num,
                "text": text,
                "conf": conf_val,
                "x": data["left"][i],
                "y": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
            }
            blocks.append(current_block)
        else:
            current_block["text"] += " " + text
            current_block["conf"] = max(current_block["conf"], conf_val)

    return blocks
