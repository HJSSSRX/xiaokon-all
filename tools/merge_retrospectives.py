#!/usr/bin/env python3
"""
合并远程机上传的经验 (retrospective) 到知识库。

数据源:
- Hub `/log` 端点: kind="retrospective" 的所有日志
- knowledge_base/retrospectives/{role}/*.yaml 直接写的文件

合并目标:
- 关联到具体题目 (含 qid 字段的 retro): 写入 problems/{cat}/{qid}.yaml 的
  `role_specific_lessons` 字段
- 通用经验 (无 qid): 留在 retrospectives/ 目录, 仅出现在全局 INDEX

最后重建 INDEX.yaml。

用法:
    python tools/merge_retrospectives.py
    python tools/merge_retrospectives.py --dry-run        # 只看不写
    python tools/merge_retrospectives.py --hub-only       # 只从 Hub 拉
"""
from __future__ import annotations
import argparse
import json
import sys
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    print("请先 pip install pyyaml", file=sys.stderr)
    sys.exit(1)


HUB = "http://127.0.0.1:8765"
KB = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\knowledge_base")
PROBLEMS = KB / "problems" / "fic2026_initial"
RETROS = KB / "retrospectives"
INDEX_FILE = KB / "INDEX.yaml"

CATS_LONG_TO_SHORT = {
    "computer_forensics": "computer",
    "mobile_forensics": "mobile",
    "server_forensics": "server",
    "internet_forensics": "internet",
    "binary_forensics": "binary",
}


def fetch_hub_retros() -> list[dict]:
    """从 Hub 拉所有 kind=retrospective 的日志"""
    try:
        with urllib.request.urlopen(f"{HUB}/logs?kind=retrospective", timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"⚠ Hub 拉取失败 (可能没启动 / 没该 endpoint): {e}", file=sys.stderr)
        # 备选: 拉所有 logs 然后过滤
        try:
            with urllib.request.urlopen(f"{HUB}/logs", timeout=5) as r:
                all_logs = json.loads(r.read())
            return [l for l in all_logs if l.get("kind") == "retrospective"]
        except Exception as e2:
            print(f"⚠ 备选也失败: {e2}", file=sys.stderr)
            return []


def load_local_retros() -> list[dict]:
    """加载本地 retrospectives/ 目录下的 yaml"""
    out = []
    if not RETROS.exists():
        return out
    for f in RETROS.rglob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data["_source_path"] = str(f)
                out.append(data)
        except Exception as e:
            print(f"⚠ 解析 {f} 失败: {e}", file=sys.stderr)
    return out


def normalize_retro(retro: dict) -> dict:
    """统一字段命名: from/role, category_forensics → category 短名, qid 大写"""
    role = retro.get("role") or retro.get("from", "")
    if role.endswith("_analyst"):
        pass  # 已是 X_analyst 形式
    cat_long = retro.get("category", "")
    cat_short = CATS_LONG_TO_SHORT.get(cat_long, cat_long.replace("_forensics", ""))
    qid = retro.get("qid", "").strip().upper()
    return {
        "role": role,
        "category": cat_short,
        "qid": qid,
        "topic": retro.get("topic", ""),
        "content": retro.get("content", ""),
        "tags": retro.get("tags") or [],
        "actionable": retro.get("actionable", ""),
        "evidence_path": retro.get("evidence_path", ""),
        "estimated_time_cost_min": retro.get("estimated_time_cost_min"),
        "related_qids": retro.get("related_qids") or [],
        "related_techniques": retro.get("related_techniques") or [],
        "_raw": retro,
    }


def merge_to_problem(retro: dict, dry_run: bool = False) -> bool:
    """把 retro 合并到对应的 problems/{cat}/{qid}.yaml"""
    cat = retro["category"]
    qid = retro["qid"]
    if not cat or not qid:
        return False
    p_path = PROBLEMS / cat / f"{qid}.yaml"
    if not p_path.exists():
        print(f"  ⚠ 题目卡不存在: {p_path}")
        return False

    data = yaml.safe_load(p_path.read_text(encoding="utf-8")) or {}
    role_lessons = data.setdefault("role_specific_lessons", {})
    role = retro["role"] or "unknown"
    role_block = role_lessons.setdefault(role, [])

    entry = {
        "topic": retro["topic"],
        "content": retro["content"],
        "actionable": retro["actionable"],
    }
    if retro["evidence_path"]:
        entry["evidence_path"] = retro["evidence_path"]
    if retro["estimated_time_cost_min"]:
        entry["estimated_time_cost_min"] = retro["estimated_time_cost_min"]

    # 去重: 同 role 同 topic 同 content 不重复
    sig = (entry["topic"], entry["content"][:100])
    existing_sigs = [(e.get("topic"), str(e.get("content", ""))[:100]) for e in role_block]
    if sig in existing_sigs:
        return False

    role_block.append(entry)

    if not dry_run:
        with p_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=100)
    return True


def rebuild_index(dry_run: bool = False):
    """重建 INDEX.yaml"""
    index = {
        "problems": [],
        "techniques": [],
        "retrospectives": [],
        "stats": {},
    }

    # problems
    for f in PROBLEMS.rglob("*.yaml"):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            index["problems"].append({
                "qid": data.get("qid"),
                "category": data.get("category"),
                "question_no": data.get("question_no"),
                "file": str(f.relative_to(KB)).replace("\\", "/"),
                "keywords": data.get("keywords") or [],
                "result": data.get("result"),
                "has_lessons": bool(data.get("lessons")),
                "has_role_specific": bool(data.get("role_specific_lessons")),
            })
        except Exception:
            continue

    # techniques
    tdir = KB / "techniques"
    if tdir.exists():
        for f in tdir.rglob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                index["techniques"].append({
                    "slug": data.get("slug"),
                    "name": data.get("name"),
                    "category": data.get("category"),
                    "file": str(f.relative_to(KB)).replace("\\", "/"),
                    "seen_in": data.get("seen_in") or [],
                })
            except Exception:
                continue

    # retrospectives
    if RETROS.exists():
        for f in RETROS.rglob("*.yaml"):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                index["retrospectives"].append({
                    "role": data.get("role"),
                    "topic": data.get("topic"),
                    "qid": data.get("qid"),
                    "file": str(f.relative_to(KB)).replace("\\", "/"),
                })
            except Exception:
                continue

    # stats
    by_result = {}
    by_cat = {}
    for p in index["problems"]:
        by_result[p.get("result", "?")] = by_result.get(p.get("result", "?"), 0) + 1
        by_cat[p.get("category", "?")] = by_cat.get(p.get("category", "?"), 0) + 1
    index["stats"] = {
        "total_problems": len(index["problems"]),
        "total_techniques": len(index["techniques"]),
        "total_retrospectives": len(index["retrospectives"]),
        "by_result": by_result,
        "by_category": by_cat,
    }

    if not dry_run:
        with INDEX_FILE.open("w", encoding="utf-8") as f:
            yaml.safe_dump(index, f, allow_unicode=True, sort_keys=False, width=120)

    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只看不写")
    ap.add_argument("--hub-only", action="store_true", help="只从 Hub 拉")
    ap.add_argument("--local-only", action="store_true", help="只从本地 retrospectives/ 读")
    ap.add_argument("--no-rebuild-index", action="store_true", help="跳过 INDEX.yaml 重建")
    args = ap.parse_args()

    print("=== 拉取经验数据 ===")
    retros_raw = []
    if not args.local_only:
        h = fetch_hub_retros()
        print(f"  Hub: {len(h)} 条")
        retros_raw.extend(h)
    if not args.hub_only:
        l = load_local_retros()
        print(f"  本地: {len(l)} 条")
        retros_raw.extend(l)

    if not retros_raw:
        print("\n⚪ 暂无经验数据 (远程机尚未上传)")
        if not args.no_rebuild_index:
            print("\n=== 重建 INDEX.yaml ===")
            idx = rebuild_index(dry_run=args.dry_run)
            print(f"  problems={idx['stats']['total_problems']}, techniques={idx['stats']['total_techniques']}, retrospectives={idx['stats']['total_retrospectives']}")
        return

    print(f"\n=== 合并到题目卡 ===")
    merged = 0
    skipped = 0
    for raw in retros_raw:
        retro = normalize_retro(raw)
        if not retro["qid"]:
            skipped += 1
            continue  # 通用经验不合并到题目卡
        if merge_to_problem(retro, dry_run=args.dry_run):
            merged += 1
            print(f"  ✓ {retro['role']} → {retro['category']}/{retro['qid']}: {retro['topic']}")

    print(f"\n合并: {merged} 条 | 跳过 (通用/无 qid): {skipped} 条")

    if not args.no_rebuild_index:
        print("\n=== 重建 INDEX.yaml ===")
        idx = rebuild_index(dry_run=args.dry_run)
        print(f"  problems={idx['stats']['total_problems']}")
        print(f"  techniques={idx['stats']['total_techniques']}")
        print(f"  retrospectives={idx['stats']['total_retrospectives']}")
        print(f"  by_result={idx['stats']['by_result']}")


if __name__ == "__main__":
    main()
