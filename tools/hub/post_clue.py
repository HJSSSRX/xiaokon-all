"""
POST 关于保险柜信息的关键 finding
+ 关闭 vhd 解析这条线 (binary 已破出 Q3/Q4/Q5)
"""
import urllib.request
import json

HUB = "http://127.0.0.1:8765"


def post_log(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{HUB}/log",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.read().decode("utf-8")


# 1. VHD 内容确认 finding
vhd_content = {
    "kind": "finding",
    "from": "main_designer",
    "summary": "[VHD 解密成功 + 内容确认] vc_rc4_decrypted.vhd (10MB) 内 2 个文件 → 无保险柜信息",
    "detail": (
        "binary_analyst 已 RC4 解密 vc → vc_rc4_decrypted.vhd, 挂载 (NTFS) 后内含:\n"
        "1. usdt_transaction_ledger_70_records.xlsx (13KB) — 70 条 USDT 钱包转账记录\n"
        "2. 银行卡交易记录_51683E.tmp (23KB, OLE2 .xls) — 10 条普通银行卡交易\n"
        "3. desktop.ini / IndexerVolumeGuid / WPSettings.dat (Windows 系统文件)\n\n"
        "已用 xlrd + openpyxl 完整解析两个 Excel:\n"
        "- usdt: 70 条交易, 收款黄金 6000 USDT (R68), 卖给 TrdkLpZVM6PA... (2026-01-27)\n"
        "- bank: 10 条工资/消费/转账, 卡尾号 8866\n\n"
        "**两个文件均无保险柜编号/密码**.\n"
        "computer Q9 (保险柜编号 1) Q10 (保险柜密码 123456) 答案应该在别处:\n"
        "- 优先怀疑 mobile.miui.notes 笔记内容 (mobile_analyst 已查 todo.db 但未必查 notes)\n"
        "- 或 mobile 聊天记录 (Telegram/微信等)\n"
        "- 或 lha PC 的其他位置 (deepin-voice-note 表里 note_id=4+ 没看)"
    ),
    "type": "instruction",
    "target_roles": ["mobile_analyst", "computer_analyst"],
}

# 2. 给 mobile_analyst 的具体指令
mobile_instr = {
    "kind": "finding",
    "from": "main_designer",
    "summary": "[mobile_analyst 任务] computer Q9/Q10 保险柜信息线索: 重查 miui.notes 全部笔记",
    "detail": (
        "computer Q9 = 保险柜编号 (参考格式 1)\n"
        "computer Q10 = 保险柜密码 (参考格式 123456)\n\n"
        "已知 (binary VHD 解密后) 这两个答案不在 vhd 内, 必然在 mobile 或 PC 其他位置.\n\n"
        "建议 mobile_analyst 全量提取 miui.notes 数据库:\n"
        "/data/user/0/com.miui.notes/databases/notes.db (或类似名字)\n"
        "全表扫描 SELECT * FROM notes 看每条笔记内容.\n\n"
        "之前 F-M002 仅查 todo.db 找日期. 完整笔记内容未导出过."
    ),
    "type": "instruction",
    "target_roles": ["mobile_analyst"],
}

# 3. 给 computer_analyst 的指令
computer_instr = {
    "kind": "finding",
    "from": "main_designer",
    "summary": "[computer_analyst 任务] computer Q9/Q10 保险柜信息: 重查 deepin-voice-note 全部笔记",
    "detail": (
        "F-C004 已确认 deepin-voice-note1.0.db 表 vnote_items_tbl 有:\n"
        "- note_id=1: 黄金换现金联系方式 (Q3)\n"
        "- note_id=2: 视频网站技术 联系 uuutalk\n"
        "- note_id=3: 矿机参数\n\n"
        "请检查 note_id >= 4 的所有笔记 (可能有保险柜内容).\n"
        "另查:\n"
        "- ~/.config/deepin/deepin-voice-note/* 全部\n"
        "- ~/Documents/ + ~/Desktop/ 文件\n"
        "- WPS/Office 历史文件 (~/.config/cn.wps.qing)\n"
        "- 浏览器 Bookmarks / History / Cookies\n"
        "- 邮件 (Q2 邮箱已知 hf133..., 但邮件内容呢?)"
    ),
    "type": "instruction",
    "target_roles": ["computer_analyst"],
}

print("=== POST VHD 内容 finding ===")
print(post_log(vhd_content))
print()
print("=== POST mobile 指令 ===")
print(post_log(mobile_instr))
print()
print("=== POST computer 指令 ===")
print(post_log(computer_instr))
