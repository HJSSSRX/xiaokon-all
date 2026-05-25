"""
answer_format_lint.py — C3 方案: 答案格式校验工具

用途:
  扫描 answers.yaml 里所有已提交的答案,对照内置格式规则库或
  questions_meta.yaml 里的 "ref_format" 字段,检测格式不符的答案。

  可独立运行(输出 lint 报告),也可被 captain.py import 用于自动标 disputed。

用法:
  python tools/answer_format_lint.py                             # 扫全部
  python tools/answer_format_lint.py --cat mobile_forensics      # 只扫一类
  python tools/answer_format_lint.py --fix                       # 自动标 disputed (需 Hub 在线)
  python tools/answer_format_lint.py --json                      # JSON 输出
"""
from __future__ import annotations
import argparse
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import yaml

# ─── 内置格式规则库 ───────────────────────────────────────────────────────────
# 格式: name -> (regex_pattern, description, example)
# 用于 questions_meta.yaml 里 ref_format 字段的匹配
FORMAT_RULES = {
    # 哈希
    "md5":      (r"^[0-9a-f]{32}$",   "MD5 (32 hex lowercase)", "c4ca4238a0b923820dcc509a6f75849b"),
    "sha1":     (r"^[0-9a-f]{40}$",   "SHA1 (40 hex lowercase)", "da39a3ee5e6b4b0d3255bfef95601890afd80709"),
    "sha256":   (r"^[0-9a-f]{64}$",   "SHA256 (64 hex lowercase)", "e3b0c44298fc1c149afbf4c8996fb924"),
    "sm3":      (r"^[0-9A-Fa-f]{64}$","SM3 (64 hex, 大小写均可)", "09D001DAC..."),
    # 网络
    "ip":       (r"^(25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)\.(25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)\.(25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)\.(25[0-5]|2[0-4]\d|1\d{2}|[1-9]\d|\d)$", "IPv4 地址", "1.1.1.1"),
    "port":     (r"^\d{1,5}$",        "端口号 (纯数字 1-65535)", "443"),
    "url_http": (r"^https?://",        "URL (http/https 开头)", "http://a.b.c/d"),
    "domain_port": (r"^[\w.-]+:\d+$", "域名:端口", "a.b.c:80"),
    "domain":   (r"^[\w.-]+\.[a-z]{2,}$", "纯域名 (不含协议)", "abc.com"),
    "email":    (r"^[^@]+@[^@]+\.[^@]+$", "邮件地址", "user@example.com"),
    # 日期/时间
    "date_ymd8":    (r"^\d{8}$",                   "日期 yyyymmdd", "20260101"),
    "date_iso":     (r"^\d{4}-\d{2}-\d{2}$",       "日期 yyyy-mm-dd", "2026-01-01"),
    "date_slash":   (r"^\d{4}/\d{1,2}/\d{1,2}$",   "日期 yyyy/m/d", "2026/1/1"),
    "datetime_docker": (r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z$",
                        "Docker 时间戳", "2020-01-01T00:00:00.012345678Z"),
    # 版本号
    "version_xy":   (r"^\d+\.\d+$",          "版本 x.y", "0.9"),
    "version_vxyz": (r"^v\d+\.\d+\.\d+$",    "版本 vx.y.z", "v1.1.1"),
    "version_model":(r"^[A-Za-z]\w*\d+\.\d+","AI 模型版本 (字母+数字.数字)", "Fic2.6"),
    # 文件/路径
    "path_unix":    (r"^/[\w./\-]+",          "Unix 绝对路径", "/etc/nginx/conf.d"),
    "filename":     (r"^[\w\-]+\.[a-z0-9]+$", "文件名 (含扩展名)", "admin.php"),
    "file_ext":     (r"^[a-z0-9]{1,8}$",      "文件扩展名 (不含.)", "vhd"),
    # 数字
    "integer":      (r"^\d+$",                "纯整数", "42"),
    "float2":       (r"^\d+\.\d{2}$",         "浮点 2 位小数", "1.00"),
    # 字符串
    "telegram_id":  (r"^@[\w]+$",             "Telegram 用户名 (@...)", "@abc123"),
    "uuid":         (r"^[0-9a-f-]{8,}$",      "UUID/PARTUUID", "a1b2-c3d4"),
    # 钱包
    "eth_wallet":   (r"^0x[0-9a-fA-F]{40}$",  "ETH 钱包地址", "0xAbCd..."),
    "btc_bech32":   (r"^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,}$", "BTC 地址", "bc1q..."),
    "usdt_trc20":   (r"^T[0-9A-Za-z]{33}$",   "USDT TRC20 地址", "T..."),
    "crypto_generic": (r"^[0-9A-Fa-f]{40,130}$", "通用加密哈希/地址", "3e627d90..."),
    # ICP
    "icp":          (r"^[a-zA-Z0-9\u4e00-\u9fa5\-]+\d+$", "ICP 备案号", "icp123"),
    # 多选
    "multi_choice": (r"^[A-E]((?:[,，、\s]*[A-E])+)?$", "多选 (如 ACD)", "ACD"),
}

# 基于参考格式字符串 -> 推断规则名 (C2 生成的 ref_format 字段)
REF_FORMAT_HINTS = [
    # (正则匹配 ref_format 字符串,  规则名)
    (r"^[0-9a-f]{32}$",                "md5"),
    (r"^[0-9a-f]{40}$",                "sha1"),
    (r"^[0-9A-Fa-f]{64}",              "sm3"),
    (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "ip"),
    (r"^\d{8}$",                        "date_ymd8"),
    (r"^\d{4}-\d{2}-\d{2}$",           "date_iso"),
    (r"^\d{4}/\d{1,2}/\d{1,2}$",       "date_slash"),
    (r"T\d{2}:\d{2}:\d{2}\.\d+Z",      "datetime_docker"),
    (r"^https?://",                     "url_http"),
    (r"@[a-zA-Z0-9_]+",                "telegram_id"),
    (r"^\d+\.\d{2}$",                  "float2"),
    (r"^v\d+\.\d+\.\d+$",              "version_vxyz"),
    (r"^\d+\.\d+$",                    "version_xy"),
    (r":\d+$",                          "domain_port"),
    (r"^/",                             "path_unix"),
    (r"^0x[0-9a-fA-F]",               "eth_wallet"),
    (r"^T[0-9A-Za-z]{33}$",           "usdt_trc20"),
    (r"[A-Z]+\d+\.\d+",               "version_model"),
    (r"\.",                             "filename"),  # fallback: 含点 = 文件名
    (r"^[a-zA-Z]+$",                   None),         # 纯字母: 无特定规则
    (r"^\d+$",                          "integer"),
]


def infer_rule(ref_format: str) -> str | None:
    """从参考格式字符串推断规则名。"""
    if not ref_format:
        return None
    for pattern, rule in REF_FORMAT_HINTS:
        if re.search(pattern, ref_format):
            return rule
    return None


def check_answer(answer: str, rule_name: str) -> tuple[bool, str]:
    """检查 answer 是否符合 rule_name 规则。返回 (ok, reason)。"""
    if not answer:
        return True, ""   # 空答案不校验 (未答)
    if rule_name not in FORMAT_RULES:
        return True, f"规则 '{rule_name}' 未定义"
    pattern, desc, example = FORMAT_RULES[rule_name]
    if re.match(pattern, answer.strip()):
        return True, ""
    return False, f"期望格式: {desc} (如 '{example}')"


def load_yaml(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or default
    except FileNotFoundError:
        return default


def lint_answers(case_dir: str, cat_filter: str | None = None) -> list[dict]:
    """
    扫描 answers.yaml,返回 lint 结果列表。
    每条结果: {cat, qid, answer, rule, ok, reason, ref_format}
    """
    answers_path = Path(case_dir) / "shared" / "answers.yaml"
    meta_path    = Path(case_dir) / "shared" / "questions_meta.yaml"

    answers = load_yaml(str(answers_path), {})
    meta    = load_yaml(str(meta_path), {})  # {cat: [{qid, ref_format, ...}]}

    # 构建 meta_map: {cat: {qid: ref_format}}
    meta_map: dict[str, dict[str, str]] = {}
    if isinstance(meta, dict):
        for cat, items in meta.items():
            if not isinstance(items, list):
                continue
            meta_map[cat] = {}
            for item in items:
                if isinstance(item, dict) and item.get("qid") and item.get("ref_format"):
                    meta_map[cat][item["qid"]] = item["ref_format"]

    results = []
    if not isinstance(answers, dict):
        return results

    for cat, items in answers.items():
        if cat_filter and cat != cat_filter:
            continue
        if not isinstance(items, list):
            continue
        cat_meta = meta_map.get(cat, {})
        for a in items:
            if not isinstance(a, dict):
                continue
            qid = a.get("qid", "")
            answer = (a.get("answer") or "").strip()
            ref_format = cat_meta.get(qid, "")
            rule = infer_rule(ref_format) if ref_format else None

            if not answer:
                results.append({"cat": cat, "qid": qid, "answer": "", "rule": rule,
                                 "ok": None, "reason": "未答", "ref_format": ref_format})
                continue

            if rule:
                ok, reason = check_answer(answer, rule)
            else:
                ok, reason = True, "(无格式规则)"

            results.append({"cat": cat, "qid": qid, "answer": answer, "rule": rule,
                             "ok": ok, "reason": reason, "ref_format": ref_format})

    return results


def render_report(results: list[dict]) -> str:
    lines = []
    fails = [r for r in results if r["ok"] is False]
    warns = [r for r in results if r["ok"] is None and r["answer"]]  # 空 answer 已答 → 不存在
    oks   = [r for r in results if r["ok"] is True]

    lines.append(f"=== 答案格式 Lint 报告 ===")
    lines.append(f"通过: {len(oks)}  失败: {len(fails)}  未答: {sum(1 for r in results if not r['answer'])}")
    lines.append("")

    if fails:
        lines.append("──── ❌ 格式不符 (需要关注) ────")
        for r in fails:
            lines.append(f"  [{r['cat'][:20]:20s}] {r['qid']:4s}: {(r['answer'] or '(空)')[:40]:40s}")
            lines.append(f"       ref='{r['ref_format']}' rule={r['rule']}")
            lines.append(f"       {r['reason']}")
    else:
        lines.append("  ✅ 无格式不符答案")

    lines.append("")
    lines.append("──── ✅ 通过 ────")
    for r in oks:
        lines.append(f"  [{r['cat'][:20]:20s}] {r['qid']:4s}: {(r['answer'] or '')[:50]}")

    return "\n".join(lines)


def mark_disputed_via_hub(fails: list[dict], hub: str) -> None:
    """把格式不符的答案通过 Hub 标为 disputed。"""
    for r in fails:
        cat, qid, reason = r["cat"], r["qid"], r["reason"]
        url = f"{hub}/answers/{cat}/{qid}/verify"
        payload = json.dumps({
            "verification_status": "disputed",
            "verified_by": "answer_format_lint",
            "verify_note": f"[auto-lint] 格式不符: {reason}  ref='{r['ref_format']}'",
        }, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=payload,
              headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=5).read().decode("utf-8")
            print(f"  marked disputed: {cat}/{qid} → {resp[:60]}")
        except Exception as e:
            print(f"  WARN: {cat}/{qid} mark failed: {e}", file=sys.stderr)


def main():
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    p = argparse.ArgumentParser(description="答案格式 Lint 工具 (C3 方案)")
    p.add_argument("--case",   default=r"E:\ffffff-JIANCAI\2026FIC团体赛\case", help="case 目录")
    p.add_argument("--cat",    default=None,  help="只扫某个 category")
    p.add_argument("--fix",    action="store_true", help="自动标 disputed (需 Hub)")
    p.add_argument("--hub",    default="http://127.0.0.1:8765", help="Hub URL")
    p.add_argument("--json",   action="store_true", help="JSON 输出")
    args = p.parse_args()

    results = lint_answers(args.case, args.cat)
    fails   = [r for r in results if r["ok"] is False]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(render_report(results))

    if args.fix and fails:
        print(f"\n自动标 {len(fails)} 条 disputed...")
        mark_disputed_via_hub(fails, args.hub)


# ─── 供 captain.py import 的简洁接口 ─────────────────────────────────────────

def quick_lint(case_dir: str) -> tuple[list[dict], list[dict]]:
    """
    captain.py 调用: 返回 (fails, results)。
    fails  = 格式不符的答案列表
    results = 全部 lint 结果
    """
    results = lint_answers(case_dir)
    fails   = [r for r in results if r["ok"] is False]
    return fails, results


if __name__ == "__main__":
    main()
