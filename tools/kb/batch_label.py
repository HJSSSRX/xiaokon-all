#!/usr/bin/env python3
"""Batch-add domain labels to knowledge files missing them."""
import os, sys, yaml

kb_root = sys.argv[1] if len(sys.argv) > 1 else 'knowledge'

DOMAIN_KEYWORDS = {
    'skills/binary': 'binary_analysis',
    'skills/cloud': 'cloud',
    'skills/computer': 'computer_forensics',
    'skills/crypto': 'crypto',
    'skills/iot': 'iot',
    'skills/mobile': 'mobile_forensics',
    'skills/network': 'network_forensics',
    'skills/server': 'server_forensics',
    'skills/stego_crypto': 'stego_crypto',
    'skills/web': 'web',
    'skills/memory': 'memory_forensics',
}

SOLVED_DOMAIN = {
    '2025pinghang/S': 'server_forensics',
    '2025pinghang/N': 'network_forensics',
    '2026fic': 'computer_forensics',
    '2024fic_01_computer': 'computer_forensics',
    '2024fic_02_pve': 'cloud',
    '2024fic_03_openwrt': 'iot',
    '2024fic_04_cloud': 'cloud',
    '2024fic_05_server': 'server_forensics',
    '2024fic_06_data': 'computer_forensics',
    'pattern_aes_xor': 'crypto',
    'pattern_deepin_mail': 'computer_forensics',
    'pattern_disk_image': 'computer_forensics',
    'pattern_malware_static': 'binary_analysis',
    'pattern_spammimic': 'stego_crypto',
    'pattern_wps_et': 'computer_forensics',
    'test_stego_png': 'stego_crypto',
}

ALL_TAGS = set(DOMAIN_KEYWORDS.values())

def file_has_domain(fm):
    tags = fm.get('tags', []) or []
    tools = fm.get('tools', []) or []
    cats = fm.get('categories', []) or []
    all_items = set()
    for lst in [tags, tools, cats]:
        if isinstance(lst, list):
            for x in lst:
                all_items.add(str(x).lower())
    return bool(all_items & ALL_TAGS)

def infer_domain(path):
    for prefix, keyword in DOMAIN_KEYWORDS.items():
        if path.startswith(prefix):
            return keyword
    for prefix, keyword in SOLVED_DOMAIN.items():
        if prefix in path:
            return keyword
    return None

fixed = 0
skipped = 0

for root, dirs, files in os.walk(kb_root):
    for f in files:
        if not (f.endswith('.md') or f.endswith('.yaml')):
            continue
        fpath = os.path.join(root, f).replace('\\', '/')
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                content = fh.read()
        except UnicodeDecodeError:
            with open(fpath, 'r', encoding='gbk', errors='replace') as fh2:
                content = fh2.read()
            print(f'  WARN: non-UTF8 encoding in {fpath}, used GBK fallback')

        if not content.startswith('---'):
            # No frontmatter, try a different approach
            continue

        end = content.find('---', 3)
        if end < 0:
            continue

        fm_text = content[3:end]
        try:
            fm = yaml.safe_load(fm_text) or {}
        except Exception:
            continue

        if file_has_domain(fm):
            skipped += 1
            continue

        rel = os.path.relpath(fpath, kb_root).replace('\\', '/')
        keyword = infer_domain(rel)
        if not keyword:
            print(f'  SKIP (cant infer): {rel}')
            skipped += 1
            continue

        # Add domain keyword to tags
        tags = fm.get('tags', [])
        if tags is None:
            tags = []
        if not isinstance(tags, list):
            tags = []
        if keyword not in tags:
            tags.append(keyword)
        fm['tags'] = tags

        # Rebuild frontmatter
        new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=None).rstrip()
        new_content = f'---\n{new_fm}\n---\n{content[end+3:]}'
        # Strip trailing newline from original content end
        new_content = new_content.rstrip() + '\n'

        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(new_content)

        print(f'  FIXED: {rel}  -> +{keyword}')
        fixed += 1

print(f'\nDone: {fixed} fixed, {skipped} already OK')
