#!/usr/bin/env python3
"""Parse CTFHub skill tree from captured JSON data."""
import json

with open('D:/ai/tools/feeder/ctfhub_skilltree.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

tree_resp = data['api_responses'].get('Skill/getTree', {})
print('=== API Status ===')
print('Status:', tree_resp.get('status'))
print('Message:', tree_resp.get('msg'))
print()

tree_root = tree_resp.get('data', {})
print('Root node keys:', sorted(tree_root.keys()))
print('Root title:', tree_root.get('title'))
print('Root id:', tree_root.get('id'))
print('Root children count:', len(tree_root.get('children', [])))

STATE_MAP = {0: 'mastered', 1: 'learning', 2: 'unlearned'}

def print_node(node, indent=0):
    prefix = '  ' * indent
    title = node.get('title', '?')
    node_id = node.get('id', 0)
    state = node.get('user_record_skill_state', '?')
    state_str = STATE_MAP.get(state, 'unknown({})'.format(state))
    task_id = node.get('task_id', 0)
    task_title = node.get('task_title', '')
    finish_count = node.get('finish_count', 0)
    level = node.get('level', 0)
    pid = node.get('pid', 0)
    task_container_state = node.get('task_container_state', 0)
    tid = node.get('tid', '')

    details = 'id={}, level={}'.format(node_id, level)
    if task_id:
        details += ', task_id={}, task="{}", solves={}'.format(task_id, task_title, finish_count)
        if tid:
            details += ', tid={}'.format(tid)
        if task_container_state:
            details += ', container_state={}'.format(task_container_state)
    else:
        details += ', pid={}, {} children'.format(pid, len(node.get('children', [])))

    print('{}[{}] {} ({})'.format(prefix, state_str, title, details))

    for child in node.get('children', []):
        print_node(child, indent + 1)

print()
print('=' * 70)
print('FULL SKILL TREE')
print('=' * 70)
print_node(tree_root)

# Collect statistics
stats = {'total': 0, 'tasks': [], 'categories': [], 'by_state': {}, 'cat_by_state': {}}

def collect_nodes(node, path=''):
    stats['total'] += 1
    title = node.get('title', '')
    current_path = '{}/{}'.format(path, title) if path else title
    state = node.get('user_record_skill_state', -1)
    task_id = node.get('task_id', 0)

    if task_id:
        task_title = node.get('task_title', '')
        entry = {
            'path': current_path,
            'id': node['id'],
            'task_id': task_id,
            'title': task_title,
            'state': state,
            'state_str': STATE_MAP.get(state, '?'),
            'finish_count': node.get('finish_count', 0),
            'level': node.get('level', 0),
            'tid': node.get('tid', ''),
            'container_state': node.get('task_container_state', 0),
        }
        stats['tasks'].append(entry)
        stats['by_state'][state] = stats['by_state'].get(state, 0) + 1
    else:
        entry = {
            'path': current_path,
            'id': node['id'],
            'title': title,
            'state': state,
            'state_str': STATE_MAP.get(state, '?'),
            'children_count': len(node.get('children', [])),
            'level': node.get('level', 0),
            'pid': node.get('pid', 0),
        }
        stats['categories'].append(entry)
        stats['cat_by_state'][state] = stats['cat_by_state'].get(state, 0) + 1

    for child in node.get('children', []):
        collect_nodes(child, current_path)

collect_nodes(tree_root)

print()
print('=' * 70)
print('STATISTICS')
print('=' * 70)
print('Total nodes:', stats['total'])
print('Categories (non-task nodes):', len(stats['categories']))
print('Tasks (leaf nodes with task_id):', len(stats['tasks']))
print()
print('Task states:')
for state in sorted(stats['by_state'].keys()):
    print('  {}: {} tasks'.format(STATE_MAP.get(state, '?'), stats['by_state'][state]))
print()
print('Category states:')
for state in sorted(stats['cat_by_state'].keys()):
    print('  {}: {} categories'.format(STATE_MAP.get(state, '?'), stats['cat_by_state'][state]))

print()
print('=' * 70)
print('CATEGORIES (non-leaf, grouping nodes)')
print('=' * 70)
for c in stats['categories']:
    print('  [{}] {} (id={}, {} children, level={})'.format(
        c['state_str'], c['path'], c['id'], c['children_count'], c['level']))

print()
print('=' * 70)
print('TASKS (leaf nodes with challenge task_id)')
print('=' * 70)
for t in stats['tasks']:
    extra = ''
    if t.get('tid'):
        extra += ' tid={}'.format(t['tid'])
    print('  [{}] {} -> task_id={}, "{}" (solves={}, level={}{})'.format(
        t['state_str'], t['path'], t['task_id'], t['title'],
        t['finish_count'], t['level'], extra))

# Save enriched data
enriched = {
    'tree': tree_root,
    'stats': stats,
    'total_nodes': stats['total'],
    'total_categories': len(stats['categories']),
    'total_tasks': len(stats['tasks']),
}
with open('D:/ai/tools/feeder/ctfhub_skilltree.json', 'w', encoding='utf-8') as f:
    json.dump(enriched, f, ensure_ascii=False, indent=2)
print('\nEnriched data saved to ctfhub_skilltree.json')
