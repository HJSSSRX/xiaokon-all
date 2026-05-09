"""
解析 银行卡交易记录_51683E.tmp (OLE / xlsx 混合)
查找保险柜编号 + 密码 (computer Q9/Q10)
"""
import os
import shutil
import zipfile
import re
from pathlib import Path

SRC = r"E:\ffffff-JIANCAI\2026FIC团体赛\case\binary\vhd_extracted\银行卡交易记录_51683E.tmp"
WORK = Path(r"E:\ffffff-JIANCAI\2026FIC团体赛\case\binary\vhd_extracted\bank_parsed")
WORK.mkdir(exist_ok=True)

# 1. file magic
with open(SRC, "rb") as f:
    head = f.read(16)
print(f"前 16 字节: {head.hex()}")
print(f"D0 CF 11 E0 = OLE2 / 50 4B 03 04 = ZIP")

# 复制为 .xls 试 OLE
shutil.copy(SRC, WORK / "bank.xls")
shutil.copy(SRC, WORK / "bank.xlsx")  # 试 ZIP 解压
shutil.copy(SRC, WORK / "bank.zip")

# 2. 试 ZIP 解压
print("\n=== 试 ZIP 解压 ===")
try:
    with zipfile.ZipFile(WORK / "bank.zip") as z:
        names = z.namelist()
        print(f"ZIP 内 {len(names)} 个文件:")
        for n in names[:20]:
            print(f"  {n}")
        z.extractall(WORK / "ooxml")
        print(f"解压到 {WORK / 'ooxml'}")
except zipfile.BadZipFile as e:
    print(f"ZIP 失败: {e}")

# 3. 试 olefile
print("\n=== 试 olefile ===")
try:
    import olefile  # type: ignore
    o = olefile.OleFileIO(WORK / "bank.xls")
    print(f"OLE streams: {o.listdir()}")
    o.close()
except ImportError:
    print("olefile 未安装")
except Exception as e:
    print(f"olefile 失败: {e}")

# 4. 试 pandas/xlrd
print("\n=== 试 pandas read_excel ===")
try:
    import pandas as pd  # type: ignore
    for engine in ["openpyxl", "xlrd"]:
        try:
            df = pd.read_excel(WORK / "bank.xls", engine=engine)
            print(f"engine={engine} 成功:")
            print(df.head(20).to_string())
            print(f"\n列名: {list(df.columns)}")
            print(f"行数: {len(df)}")
            break
        except Exception as e:
            print(f"engine={engine} 失败: {e}")
except ImportError:
    print("pandas 未装")

# 5. 直接看 ooxml 解压后的 sheet1.xml
xl = WORK / "ooxml"
if xl.exists():
    print("\n=== ooxml 内容 ===")
    sheets = list(xl.rglob("*.xml"))
    print(f"XML 文件数: {len(sheets)}")
    for s in sheets:
        print(f"  {s.relative_to(xl)}: {s.stat().st_size} 字节")

    # 关键: sharedStrings.xml + sheet1.xml
    ss = xl / "xl" / "sharedStrings.xml"
    if ss.exists():
        text = ss.read_text(encoding="utf-8", errors="ignore")
        print(f"\nsharedStrings.xml 前 3000 字符:")
        print(text[:3000])
        # 关键词: 保险柜 / 密码 / 编号
        for kw in ["保险柜", "密码", "编号", "safe", "password"]:
            for m in re.finditer(kw, text):
                start = max(0, m.start() - 50)
                end = min(len(text), m.end() + 100)
                print(f"\n找到 '{kw}' @{m.start()}:\n  {text[start:end]}")

print("\n完成")
