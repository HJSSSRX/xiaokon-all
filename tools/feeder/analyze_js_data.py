#!/usr/bin/env python3
"""分析JS文件中的思维导图数据"""
import requests
import re
import json

def analyze_js_for_mindmap(js_url):
    """分析JS文件查找思维导图数据"""
    print(f"正在分析JS文件: {js_url}")
    r = requests.get(js_url)
    js_content = r.text
    
    print(f"JS文件大小: {len(js_content)} 字符")
    
    # 查找包含children的大对象
    print("\n=== 查找包含children的对象 ===")
    # 使用非贪婪匹配查找大对象
    objects = []
    brace_count = 0
    start_pos = -1
    
    for i, char in enumerate(js_content):
        if char == '{':
            if brace_count == 0:
                start_pos = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_pos != -1:
                obj_str = js_content[start_pos:i+1]
                if len(obj_str) > 100 and '"children"' in obj_str:
                    objects.append(obj_str)
                start_pos = -1
    
    print(f"找到 {len(objects)} 个包含children的对象")
    
    for i, obj_str in enumerate(objects[:3]):
        print(f"\n对象 {i+1}:")
        print(f"长度: {len(obj_str)}")
        print(f"前500字符:\n{obj_str[:500]}...")
        
        # 尝试解析为JSON
        try:
            data = json.loads(obj_str)
            print("✓ 可解析为JSON")
            print(f"键: {list(data.keys())[:10]}")
        except:
            print("✗ 无法直接解析为JSON")
    
    # 查找包含中文的字符串（可能是知识数据）
    print("\n=== 查找包含中文的长字符串 ===")
    # 匹配包含中文的字符串
    chinese_pattern = re.compile(r'"([^"]*[\u4e00-\u9fff][^"]*)"')
    matches = chinese_pattern.findall(js_content)
    
    chinese_strings = [m for m in matches if len(m) > 50]
    print(f"找到 {len(chinese_strings)} 个包含中文的长字符串")
    
    for i, s in enumerate(chinese_strings[:5]):
        print(f"\n字符串 {i+1}:")
        print(f"长度: {len(s)}")
        print(f"内容: {s[:100]}...")
    
    return objects, chinese_strings

if __name__ == "__main__":
    js_url = "https://forensics.didctf.com/assets/index-BedWg9WK.js"
    objects, strings = analyze_js_for_mindmap(js_url)
    
    # 如果找到对象，保存第一个到文件
    if objects:
        with open("mindmap_data.json", "w", encoding="utf-8") as f:
            f.write(objects[0])
        print("\n已保存第一个对象到 mindmap_data.json")
