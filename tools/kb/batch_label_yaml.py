#!/usr/bin/env python3
"""Add domain tags to YAML-only (not frontmatter) solved files."""
import os, yaml

kb_root = 'knowledge'
target_dir = 'solved/2025pinghang'
domain_map = {'S': 'server_forensics', 'N': 'network_forensics'}

for root, dirs, files in os.walk(os.path.join(kb_root, target_dir)):
    for f in sorted(files):
        if not f.endswith('.yaml'):
            continue
        fpath = os.path.join(root, f)
        prefix = f[0]
        if prefix not in domain_map:
            continue
        dkw = domain_map[prefix]

        with open(fpath, 'r', encoding='utf-8') as fh:
            content = fh.read()

        try:
            data = yaml.safe_load(content)
        except Exception:
            print(f'  PARSE ERROR: {fpath}')
            continue

        if data is None:
            data = {}
        # Tags must be in 'meta' block for YAML files (see transactions.py _read_file_items)
        meta = data.setdefault('meta', {})
        if 'tags' not in meta:
            meta['tags'] = [dkw]
        elif dkw not in meta.get('tags', []):
            meta['tags'].append(dkw)
        else:
            print(f'  SKIP: {os.path.basename(fpath)} (already has {dkw})')
            continue

        new_content = yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=None)
        with open(fpath, 'w', encoding='utf-8') as fh:
            fh.write(new_content)
        print(f'  FIXED: {os.path.basename(fpath)} -> +{dkw}')

print('Done.')
