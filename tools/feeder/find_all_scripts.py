#!/usr/bin/env python3
"""查找并分析页面中的所有脚本"""
import requests
from bs4 import BeautifulSoup

url = 'https://forensics.didctf.com/knowledge'
r = requests.get(url)
soup = BeautifulSoup(r.text, 'html.parser')

# 获取所有脚本
scripts = soup.find_all('script', src=True)
print(f'找到 {len(scripts)} 个脚本:')
for script in scripts:
    print(f'  {script["src"]}')

# 检查是否有其他资源
links = soup.find_all('link', href=True)
print(f'\n找到 {len(links)} 个链接:')
for link in links[:5]:
    print(f'  {link["href"]}')

# 检查内联脚本
inline_scripts = soup.find_all('script', src=False)
print(f'\n找到 {len(inline_scripts)} 个内联脚本')

# 检查meta标签
meta_tags = soup.find_all('meta')
print(f'\n找到 {len(meta_tags)} 个meta标签')
for meta in meta_tags:
    if 'content' in meta.attrs and len(meta['content']) > 50:
        print(f'  {meta.get("name", "")}: {meta["content"][:50]}...')
