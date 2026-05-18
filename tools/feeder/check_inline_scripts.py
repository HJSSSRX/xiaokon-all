#!/usr/bin/env python3
"""检查内联脚本中的数据"""
import requests
from bs4 import BeautifulSoup
import re

url = 'https://forensics.didctf.com/knowledge'
r = requests.get(url)
soup = BeautifulSoup(r.text, 'html.parser')

# 获取所有内联脚本
inline_scripts = soup.find_all('script', src=False)
print(f'找到 {len(inline_scripts)} 个内联脚本')

for i, script in enumerate(inline_scripts):
    content = script.string
    if content:
        print(f"\n=== 内联脚本 {i+1} ===")
        print(f"长度: {len(content)}")
        
        # 检查是否包含JSON数据
        if '{' in content and '}' in content:
            # 查找可能的JSON对象
            brace_count = 0
            start_pos = -1
            for j, char in enumerate(content):
                if char == '{':
                    if brace_count == 0:
                        start_pos = j
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_pos != -1:
                        obj_str = content[start_pos:j+1]
                        if len(obj_str) > 50:
                            print(f"找到JSON对象，长度: {len(obj_str)}")
                            print(f"前200字符: {obj_str[:200]}...")
                        start_pos = -1
        
        # 检查是否包含window变量
        window_pattern = re.compile(r'window\.[a-zA-Z_]+\s*=')
        matches = window_pattern.findall(content)
        if matches:
            print(f"找到 {len(matches)} 个window变量赋值")
            for match in matches[:5]:
                print(f"  {match}")

# 检查HTML注释中的数据
comments = soup.find_all(string=lambda text: isinstance(text, str) and '<!--' in text)
print(f"\n找到 {len(comments)} 个注释")
for comment in comments[:3]:
    if len(comment) > 50:
        print(f"注释内容: {comment[:100]}...")
