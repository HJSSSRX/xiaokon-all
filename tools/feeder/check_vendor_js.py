#!/usr/bin/env python3
"""检查vendor JS文件"""
import requests
import re

js_files = [
    '/assets/vendor-BrY4K9U-.js',
    '/assets/antd-Com6ngjr.js',
    '/assets/index-BedWg9WK.js'
]

for js_file in js_files:
    url = 'https://forensics.didctf.com' + js_file
    print(f'分析: {js_file}')
    
    try:
        r = requests.get(url, timeout=30)
        content = r.text
        
        # 检查是否包含中文（知识数据通常包含中文）
        chinese_count = len(re.findall(r'[\u4e00-\u9fff]', content))
        print(f'  中文字符数量: {chinese_count}')
        
        # 检查是否包含思维导图相关关键词
        keywords = ['children', 'node', 'tree', 'mindmap', 'knowledge']
        for kw in keywords:
            count = content.lower().count(kw)
            if count > 0:
                print(f'  "{kw}" 出现 {count} 次')
        
        # 检查是否有大的JSON结构
        brace_count = content.count('{')
        bracket_count = content.count('[')
        print(f'  大括号: {brace_count}, 方括号: {bracket_count}')
        
        # 查找长字符串
        long_strings = re.findall(r'"([^"]{300,})"', content)
        print(f'  长字符串数量: {len(long_strings)}')
        
    except Exception as e:
        print(f'  错误: {e}')
    
    print()
