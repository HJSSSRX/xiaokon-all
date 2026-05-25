"""
任务 c: 标记 server F-S006~F-S025 的中文丢失 finding。

策略: 不删除 (会破坏 references), 加 meta 字段:
  _encoding_lost: true
  _encoding_note: "原 summary 中文因 PowerShell ConvertTo-Json UTF-8 bug 丢失;
                   残留 ASCII 答案部分仍可用; 等 server_analyst 拉 v3.1 后用
                   Python urllib 重 POST 恢复完整中文。"

这样:
  - 主表能识别这些 finding 为 "数据残缺"状态
  - 未来训练数据筛选时可剔除 _encoding_lost=true 的条目
  - 不破坏现有 cross-reference (F-S006 等 ID 仍然存在)
"""
import yaml, sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

YAML_PATH = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\shared\findings.yaml")

with YAML_PATH.open(encoding="utf-8") as f:
    findings = yaml.safe_load(f) or []

NOTE = (
    "原 summary 中文因 PowerShell ConvertTo-Json UTF-8 bug 丢失 "
    "(F-S006~F-S025 期间发生)。残留的 ASCII 部分(答案值/IP/UUID/版本号等)仍可用。"
    "完整中文上下文需要 server_analyst 拉 v3.1 + 改用 Python urllib 重 POST 后恢复。"
)

fixed = 0
for f in findings:
    if not isinstance(f, dict):
        continue
    fid = f.get("id", "")
    if not fid.startswith("F-S"):
        continue
    summary = f.get("summary", "") or ""
    # 启发式判断: summary 以 ? 开头 或者 ?字符 >= 3 个 -> 中文丢失
    has_q_prefix = summary.startswith("?")
    q_count = summary.count("?")
    has_cjk = any("\u4e00" <= c <= "\u9fff" for c in summary)

    is_lost = (has_q_prefix or q_count >= 3) and not has_cjk

    if is_lost:
        if f.get("_encoding_lost"):
            print(f"  -- {fid}: 已标记")
            continue
        f["_encoding_lost"] = True
        f["_encoding_note"] = NOTE
        if not f.get("detail"):
            f["detail"] = (
                f"[ENCODING_LOST] 原中文丢失。残留 ASCII 摘要: '{summary}'. "
                "可从此摘要的英文/数字部分提取答案 (例: ngrok 域名/IP/UUID/版本)。"
            )
        fixed += 1
        print(f"  ✓ {fid}: marked. residual ASCII = '{summary[:60]}'")
    else:
        if has_cjk:
            print(f"  -- {fid}: 中文正常, skip")

print(f"\n共标记 {fixed} 条 finding 为 encoding_lost。")

if fixed > 0:
    # 写回前先备份
    backup = YAML_PATH.with_suffix(".yaml.bak_before_fix")
    backup.write_bytes(YAML_PATH.read_bytes())
    print(f"备份: {backup}")
    with YAML_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(findings, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"已写回 {YAML_PATH}")
