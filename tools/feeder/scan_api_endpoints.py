#!/usr/bin/env python3
"""扫描可能的API端点"""
import requests

base_url = 'https://forensics.didctf.com'

# 常见的API端点模式
api_patterns = [
    # 思维导图相关
    '/api/mindmap',
    '/api/mindmap/tree',
    '/api/knowledge',
    '/api/knowledge/tree',
    '/api/knowledge/nodes',
    
    # REST API
    '/api/v1/mindmap',
    '/api/v1/knowledge',
    
    # 数据端点
    '/data/mindmap.json',
    '/data/knowledge.json',
    '/data/tree.json',
    
    # GraphQL
    '/graphql',
    '/api/graphql',
    
    # 其他常见模式
    '/knowledge/api',
    '/mindmap/api',
    '/tree/data',
    '/nodes',
    '/api/nodes',
    '/api/tree',
    
    # 可能的静态数据文件
    '/static/data/mindmap.json',
    '/static/data/tree.json',
    
    # 分页API
    '/api/knowledge/list',
    '/api/knowledge/page',
]

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
}

print("正在扫描API端点...\n")

found_endpoints = []

for endpoint in api_patterns:
    url = base_url + endpoint
    try:
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            content_type = r.headers.get('Content-Type', '')
            
            # 检查是否是JSON
            if 'application/json' in content_type:
                try:
                    data = r.json()
                    size = len(r.text)
                    found_endpoints.append({
                        'url': url,
                        'size': size,
                        'type': 'json',
                        'keys': list(data.keys())[:5] if isinstance(data, dict) else f'array with {len(data)} items'
                    })
                    print(f'✅ {url} (JSON, {size} bytes)')
                except:
                    pass
            else:
                # 检查是否有内容
                if len(r.text) > 100 and len(r.text) < 10000:
                    found_endpoints.append({
                        'url': url,
                        'size': len(r.text),
                        'type': content_type,
                        'preview': r.text[:100]
                    })
                    print(f'⚠️ {url} ({content_type}, {len(r.text)} bytes)')
                    
    except Exception as e:
        pass

print("\n=== 找到的端点 ===")
for ep in found_endpoints:
    print(f"\n{ep['url']}")
    print(f"  类型: {ep['type']}")
    print(f"  大小: {ep['size']} bytes")
    if 'keys' in ep:
        print(f"  数据键: {ep['keys']}")
    elif 'preview' in ep:
        print(f"  预览: {ep['preview']}")
