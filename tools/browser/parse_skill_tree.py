#!/usr/bin/env python3
"""Parse and display CTFHub skill tree from saved JSON."""
import json

with open("D:/ai/ctfhub_skill_tree.json", "r", encoding="utf-8") as f:
    data = json.load(f)

STATE_MAP = {0: "已掌握", 1: "学习中", 2: "未学习"}


def print_tree(node, indent=0):
    prefix = "  " * indent
    state = STATE_MAP.get(node.get("user_record_skill_state", -1), "?")
    title = node["title"]
    task_id = node.get("task_id", 0)
    task_title = node.get("task_title", "")
    finish_count = node.get("finish_count", 0)

    if task_id:
        print(f"{prefix}{title} [{state}] (task={task_id}, {task_title}, {finish_count} solves)")
    else:
        print(f"{prefix}{title} [{state}] ({finish_count} solves)")

    for child in node.get("children", []):
        print_tree(child, indent + 1)


# Also collect all tasks (leaf nodes with task_id)
def collect_tasks(node, path="", tasks=None):
    if tasks is None:
        tasks = []
    current_path = f"{path}/{node['title']}" if path else node["title"]
    if node.get("task_id"):
        tasks.append({
            "path": current_path,
            "id": node["id"],
            "task_id": node["task_id"],
            "task_title": node["task_title"],
            "state": node["user_record_skill_state"],
            "finish_count": node.get("finish_count", 0),
        })
    for child in node.get("children", []):
        collect_tasks(child, current_path, tasks)
    return tasks


print("=== CTFHub Skill Tree ===\n")
print_tree(data["data"])

tasks = collect_tasks(data["data"])
print(f"\n=== Tasks with IDs ({len(tasks)}) ===")
for t in tasks:
    state = STATE_MAP.get(t["state"], "?")
    print(f"  [{state}] {t['path']}")
    print(f"         task_id={t['task_id']}  title={t['task_title']}")

# Also find all categories (nodes without task_id)
def collect_categories(node, path="", cats=None):
    if cats is None:
        cats = []
    current_path = f"{path}/{node['title']}" if path else node["title"]
    if not node.get("task_id") and node.get("id") != 1:  # skip root
        cats.append({
            "path": current_path,
            "id": node["id"],
            "state": node["user_record_skill_state"],
            "children_count": len(node.get("children", [])),
        })
    for child in node.get("children", []):
        collect_categories(child, current_path, cats)
    return cats

cats = collect_categories(data["data"])
print(f"\n=== Categories ({len(cats)}) ===")
for c in cats:
    state = STATE_MAP.get(c["state"], "?")
    print(f"  [{state}] {c['path']} (id={c['id']}, {c['children_count']} children)")
