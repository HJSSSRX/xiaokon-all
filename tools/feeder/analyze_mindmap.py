#!/usr/bin/env python3
"""分析思维导图页面并提取知识结构"""
import requests
import re
import json

def analyze_mindmap_page(url):
    """分析思维导图页面结构"""
    print(f"正在分析页面: {url}")
    
    # 获取页面
    r = requests.get(url)
    html = r.text
    
    # 分析页面结构
    print("\n=== 页面结构分析 ===")
    print(f"页面标题: {re.search(r'<title>(.*?)</title>', html).group(1) if re.search(r'<title>(.*?)</title>', html) else '未知'}")
    
    # 查找script标签
    script_tags = re.findall(r'<script[^>]*src="([^"]+)"', html)
    print(f"\n找到 {len(script_tags)} 个外部脚本:")
    for i, src in enumerate(script_tags):
        print(f"  {i+1}. {src}")
    
    # 检查主要JS文件
    main_js = None
    for src in script_tags:
        if 'index' in src and '.js' in src:
            main_js = src
            break
    
    if main_js:
        print(f"\n=== 分析主JS文件: {main_js} ===")
        js_url = url.rsplit('/', 1)[0] + '/' + main_js if main_js.startswith('/') else main_js
        r = requests.get(js_url)
        js_content = r.text
        
        print(f"JS文件大小: {len(js_content)} 字符")
        
        # 查找关键词
        keywords = ['mindmap', 'node', 'children', 'tree', 'knowledge', 'category', 'topic']
        for kw in keywords:
            count = js_content.lower().count(kw)
            if count > 0:
                print(f"  ✓ '{kw}' 出现 {count} 次")
        
        # 查找JSON结构
        print("\n=== 尝试提取JSON数据 ===")
        
        # 查找可能的JSON数据块
        # 模式1: 查找大的对象字面量
        json_patterns = [
            r'\{[^}]*(?:\n[^}]*)*\}',  # 多行对象
            r'\[[^\]]*(?:\n[^\]]*)*\]',  # 多行数组
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, js_content)
            for match in matches:
                if len(match) > 500 and ('name' in match or 'title' in match or 'label' in match):
                    print(f"找到可能的数据块，长度: {len(match)}")
                    print(f"前200字符: {match[:200]}...")
                    print()
                    break
    
    return html

def extract_mindmap_structure(html):
    """从HTML中提取思维导图结构"""
    # 查找内联数据
    patterns = [
        r'window\.\w+\s*=\s*(\{.*?\});',
        r'data:\s*(\{.*?\})',
        r'const\s+\w+\s*=\s*(\{.*?\});',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                print(f"\n成功提取JSON数据，键: {list(data.keys())[:10]}")
                return data
            except:
                pass
    
    return None

if __name__ == "__main__":
    url = "https://forensics.didctf.com/knowledge"
    html = analyze_mindmap_page(url)
    data = extract_mindmap_structure(html)
    
    if data:
        print("\n=== 提取的数据结构 ===")
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
    else:
        print("\n未找到结构化数据，可能需要使用浏览器渲染")
