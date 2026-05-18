#!/usr/bin/env python3
"""从JS文件中提取中文数据"""
import requests
import re

url = 'https://forensics.didctf.com/assets/index-BedWg9WK.js'
r = requests.get(url)
content = r.text

# 查找所有包含中文的字符串
chinese_pattern = re.compile(r'"([^"]*[\u4e00-\u9fff][^"]*)"')
matches = chinese_pattern.findall(content)

print(f"找到 {len(matches)} 个包含中文的字符串")

# 按长度排序
matches.sort(key=len, reverse=True)

# 显示前20个最长的
print("\n=== 最长的中文字符串 ===")
for i, s in enumerate(matches[:20]):
    print(f"\n{i+1}. 长度: {len(s)}")
    # 检查是否看起来像JSON或结构化数据
    if s.count('{') > 2 or s.count('[') > 2:
        print(f"   类型: 可能是JSON数据")
    elif s.count('\\n') > 2:
        print(f"   类型: 多行文本")
    else:
        print(f"   类型: 普通文本")
    print(f"   内容: {s[:150]}...")

# 查找可能的JSON数据
print("\n=== 查找JSON结构 ===")
json_pattern = re.compile(r'(\{[\s\S]*?"name"[\s\S]*?"children"[\s\S]*?\})')
json_matches = json_pattern.findall(content)
print(f"找到 {len(json_matches)} 个包含name和children的对象")

if json_matches:
    print("\n第一个匹配:")
    print(json_matches[0][:500], "...")
