#!/usr/bin/env python3
"""思维导图图片解析 — OCR → 树结构 → 知识库数据"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json

import pytesseract
from PIL import Image

TESSERACT_PATH = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
if TESSERACT_PATH.exists():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_PATH)


@dataclass
class MindMapNode:
    text: str
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0
    level: int = 0
    children: list["MindMapNode"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "level": self.level,
            "children": [c.to_dict() for c in self.children],
        }


def parse_mindmap_image(
    image_path: str,
    lang: str = "chi_sim+eng",
) -> MindMapNode:
    """从思维导图图片解析出树结构"""
    img = Path(image_path)
    if not img.exists():
        return MindMapNode(text=f"[ERROR: 文件不存在: {image_path}]")

    try:
        image = Image.open(img)
        data = pytesseract.image_to_data(
            image, lang=lang, output_type=pytesseract.Output.DICT,
            config="--psm 6",
        )

        words = _extract_words(data)
        if not words:
            return MindMapNode(text="[NO_TEXT_FOUND]")

        rows = _group_into_rows(words)
        return _rows_to_tree(rows)

    except Exception as e:
        return MindMapNode(text=f"[OCR_ERROR: {e}]")


def _extract_words(data: dict) -> list[dict]:
    """从tesseract输出提取词级别数据（level=5）"""
    words = []
    n = len(data.get("text", []))
    for i in range(n):
        # level 5 = word
        if data["level"][i] != 5:
            continue
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x": data["left"][i],
            "y": data["top"][i],
            "w": data["width"][i],
            "h": data["height"][i],
        })
    return _dedup_overlaps(words)


def _group_into_rows(words: list[dict]) -> list[list[dict]]:
    """按y坐标将词分组为行"""
    if not words:
        return []

    # 按y排序
    sorted_words = sorted(words, key=lambda w: (w["y"], w["x"]))
    rows = []
    current_row = [sorted_words[0]]
    current_y = sorted_words[0]["y"]

    for w in sorted_words[1:]:
        if abs(w["y"] - current_y) < 20:
            current_row.append(w)
        else:
            rows.append(sorted(current_row, key=lambda w: w["x"]))
            current_row = [w]
            current_y = w["y"]

    rows.append(sorted(current_row, key=lambda w: w["x"]))
    return rows


def _dedup_overlaps(words: list[dict]) -> list[dict]:
    """移除OCR伪影 + 修正异常宽的CJK单字边界框"""
    if len(words) < 2:
        return words

    # 修正异常宽的CJK单字
    for w in words:
        text = w["text"]
        if len(text) == 1 and ord(text) > 0x2000 and w["w"] > 40:
            w["w"] = min(w["w"], 30)

    sorted_w = sorted(words, key=lambda w: (w["y"], w["x"]))

    # 按行分组后在每组内去重
    rows = _group_into_rows(sorted_w)
    result = []
    for row in rows:
        deduped = []
        for w in row:
            # 检查是否与已保留的同文字词重叠或紧邻
            dup = False
            for kept in deduped:
                if w["text"] == kept["text"] and abs(w["x"] - kept["x"]) < 40:
                    if w["w"] > kept["w"]:
                        deduped.remove(kept)
                        deduped.append(w)
                    dup = True
                    break
            if not dup:
                # 检查与上一个词的重叠
                if deduped:
                    prev = deduped[-1]
                    prev_right = prev["x"] + prev["w"]
                    w_right = w["x"] + w["w"]
                    overlap_start = max(w["x"], prev["x"])
                    overlap_end = min(w_right, prev_right)
                    if overlap_start < overlap_end:
                        overlap_w = overlap_end - overlap_start
                        min_w = min(w["w"], prev["w"])
                        if overlap_w > min_w * 0.5:
                            if w["w"] > prev["w"]:
                                deduped[-1] = w
                            continue
                deduped.append(w)
        result.extend(deduped)
    return result


def _merge_words_to_nodes(words: list[dict], gap_threshold: int = 20) -> list[dict]:
    """将同一行内的词按x间距合并为节点"""
    if not words:
        return []

    nodes = []
    current_text = words[0]["text"]
    current_x = words[0]["x"]
    current_y = words[0]["y"]
    current_w = words[0]["w"]
    current_h = words[0]["h"]

    for w in words[1:]:
        gap = w["x"] - (current_x + current_w)
        if gap < gap_threshold:
            # 同一个节点，合并
            current_text += " " + w["text"] if current_text else w["text"]
            current_w = w["x"] + w["w"] - current_x
            current_h = max(current_h, w["h"])
        else:
            # 新节点
            nodes.append({"text": current_text, "x": current_x, "y": current_y,
                          "w": current_w, "h": current_h})
            current_text = w["text"]
            current_x = w["x"]
            current_y = w["y"]
            current_w = w["w"]
            current_h = w["h"]

    nodes.append({"text": current_text, "x": current_x, "y": current_y,
                  "w": current_w, "h": current_h})
    return nodes


def _rows_to_tree(rows: list[list[dict]]) -> MindMapNode:
    """将行结构转换为树"""
    # 每行内的词合并为节点
    row_nodes = [_merge_words_to_nodes(row) for row in rows]

    if not row_nodes or not row_nodes[0]:
        return MindMapNode(text="[EMPTY]")

    # 第一行取居中的节点作为根
    root = _pick_root(row_nodes[0])
    root.level = 0

    # 逐行attach
    for level_idx in range(1, len(row_nodes)):
        parent_row = _flatten_tree_at_level(root, level_idx - 1)
        for node in row_nodes[level_idx]:
            child = MindMapNode(
                text=node["text"], x=node["x"], y=node["y"],
                w=node["w"], h=node["h"], level=level_idx,
            )
            # 找水平位置最近的父节点
            parent = _find_nearest_parent(parent_row, child)
            parent.children.append(child)

    return root


def _pick_root(nodes: list[dict]) -> MindMapNode:
    """选取居中的节点作为根节点"""
    if len(nodes) == 1:
        n = nodes[0]
        return MindMapNode(text=n["text"], x=n["x"], y=n["y"], w=n["w"], h=n["h"])

    center_x = sum(n["x"] + n["w"] / 2 for n in nodes) / len(nodes)
    root = min(nodes, key=lambda n: abs((n["x"] + n["w"] / 2) - center_x))

    # 其他节点也作为根的直接孩子
    r = MindMapNode(text=root["text"], x=root["x"], y=root["y"], w=root["w"], h=root["h"])
    for n in nodes:
        if n != root:
            r.children.append(MindMapNode(
                text=n["text"], x=n["x"], y=n["y"], w=n["w"], h=n["h"], level=1,
            ))
    return r


def _flatten_tree_at_level(root: MindMapNode, target_level: int) -> list[MindMapNode]:
    """获取树中指定层级的所有节点"""
    result = []
    def walk(node: MindMapNode):
        if node.level == target_level:
            result.append(node)
        for child in node.children:
            walk(child)
    walk(root)
    return result


def _find_nearest_parent(parents: list[MindMapNode], child: MindMapNode) -> MindMapNode:
    """找水平位置最近的父节点"""
    if not parents:
        return MindMapNode(text="[ORPHAN]")
    child_cx = child.x + child.w / 2
    return min(parents, key=lambda p: abs((p.x + p.w / 2) - child_cx))


def mindmap_to_kb(root: MindMapNode, kb_dir: str):
    """将解析后的思维导图树导入知识库"""
    import sys
    from tools.feeder.organizer import organize_mindmap_to_kb

    data = _tree_to_mindmap_data(root)
    organize_mindmap_to_kb(data, kb_dir)
    return data


def _tree_to_mindmap_data(root: MindMapNode) -> dict:
    """将树结构转换为 organize_mindmap_to_kb 期望的格式"""
    categories = []
    knowledge_items = []
    cat_id = 0

    def walk(node: MindMapNode, parent_category: str = ""):
        nonlocal cat_id
        if node.level == 1:
            cat_id += 1
            category = node.text
            categories.append({"id": str(cat_id), "name": category})
            for child in node.children:
                knowledge_items.append({
                    "title": child.text,
                    "category": category,
                })
                walk(child, category)
        elif parent_category and node.children:
            for child in node.children:
                knowledge_items.append({
                    "title": child.text,
                    "category": parent_category,
                })
                walk(child, parent_category)

    walk(root)

    return {
        "categories": categories,
        "knowledge_items": knowledge_items,
    }


def mindmap_tree_to_json(root: MindMapNode, indent: int = 2) -> str:
    """将思维导图树输出为JSON"""
    return json.dumps(root.to_dict(), ensure_ascii=False, indent=indent)
