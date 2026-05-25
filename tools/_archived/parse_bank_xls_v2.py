"""
直接用 xlrd 解析 .xls 的 Workbook 流, 找保险柜编号 + 密码
"""
import re
from pathlib import Path

SRC = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\binary\vhd_extracted\bank_parsed\bank.xls")

# 1. 用 xlrd 直接打开
try:
    import xlrd
    print(f"xlrd version: {xlrd.__version__}")
    book = xlrd.open_workbook(str(SRC), formatting_info=False, on_demand=False)
    print(f"sheets: {book.sheet_names()}")
    for sn in book.sheet_names():
        sheet = book.sheet_by_name(sn)
        print(f"\n=== Sheet: {sn} ({sheet.nrows} rows × {sheet.ncols} cols) ===")
        for r in range(min(sheet.nrows, 50)):
            row = [sheet.cell_value(r, c) for c in range(sheet.ncols)]
            row_str = " | ".join(str(v)[:50] for v in row)
            print(f"R{r}: {row_str}")
except Exception as e:
    print(f"xlrd 失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

# 2. 用 olefile 直接读 Workbook stream raw bytes 看是否带密码保护
print("\n=== olefile Workbook stream ===")
try:
    import olefile
    o = olefile.OleFileIO(str(SRC))
    streams_list = o.listdir()
    print(f"Streams: {streams_list}")
    if "Workbook" in [s[0] for s in streams_list]:
        wb_data = o.openstream("Workbook").read()
        print(f"Workbook size: {len(wb_data)}")
        # BIFF FILEPASS record (0x002F) 表示文件加密
        if b"\x2F\x00" in wb_data[:200]:
            print("⚠️ 发现 FILEPASS record (文件可能加密)")
    if "ETExtData" in [s[0] for s in streams_list]:
        et_data = o.openstream("ETExtData").read()
        print(f"\nETExtData size: {len(et_data)}")
        print(f"前 200 字节 hex:")
        print(et_data[:200].hex())
        print(f"\n含义猜测: ETExtData 是 WPS Office 加密扩展 — 文件**可能加密了**")
        # 找 password hash / salt 字段
        # ETExtData 结构: WPS 自定义, 可能有明文密码 hint
        # 找 utf-16 字符串
        text16 = et_data.decode("utf-16-le", errors="ignore")
        print(f"\nUTF-16 解码片段: {text16[:500]}")
        text8 = et_data.decode("utf-8", errors="ignore")
        chinese = re.findall(r"[\u4e00-\u9fff]+", text16 + text8)
        print(f"\n中文片段: {chinese[:30]}")
    o.close()
except Exception as e:
    print(f"olefile 失败: {type(e).__name__}: {e}")

print("\n完成")
