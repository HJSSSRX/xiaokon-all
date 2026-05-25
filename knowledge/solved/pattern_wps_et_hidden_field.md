---
tags: [office_forensics, wps, et, xlsx, hidden_data, xml, descr, computer_forensics]
tools: [python, zipfile, unzip]
category: computer_forensics
difficulty: easy
source: fic2026
date: 2026-05-05
verified: true
---

# Title: WPS .et 文件隐藏字段提取 (descr 属性)

## Problem
检材中有 `.et` 文件 (WPS Spreadsheet)，题目要求提取隐藏的编号或密码。

## Solution Steps

1. 识别文件结构 — `.et` 本质是 ZIP 压缩包
   ```bash
   file xxx.et           # 应显示 "Zip archive data"
   unzip -l xxx.et       # 列出内部文件
   ```

2. 提取 XML 并搜索 `descr` 属性
   ```python
   import zipfile, re, glob
   for f in glob.glob('/tmp/*.et'):
       z = zipfile.ZipFile(f)
       for name in z.namelist():
           if name.endswith('.xml'):
               data = z.read(name).decode('utf-8', 'ignore')
               for m in re.finditer(r'descr="([^"]*)"', data):
                   print(f, name, m.group(1))
   ```

3. 关键 XML 路径
   - `drs/shapexml.xml` — 形状对象的 `descr` 属性，常藏隐藏文本
   - `drs/downrev.xml` — 低版本兼容数据
   - `xl/worksheets/sheet1.xml` — 单元格数据

4. CSV 伴随文件检查
   ```bash
   cat pass8.csv
   # 可能包含: 虚拟卡号, CVV, 密码等
   ```

## FIC2026 实战数据
| 文件 | descr 值 |
|------|---------|
| 保险箱的秘密.et | `565033` |
| pass1.et | `538037` |
| pass3.et | `593037` |
| pass5.et | `669033` |
| pass6.et | `583196` |

## Key Takeaways
- `.et` = ZIP 包，和 `.xlsx` 结构相同
- 隐藏信息通常在 `descr` (description) 属性中
- 批量处理: 遍历所有 `.et` → 解压 → 正则匹配 `descr="..."`
- 同时检查同目录下的 `.csv` 文件
