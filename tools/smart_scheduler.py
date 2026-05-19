#!/usr/bin/env python3
"""Smart Task Scheduler - Intelligent task assignment and workflow management.

This module provides:
- Automatic task analysis and role matching
- Priority-based scheduling
- Adaptive workload balancing
- Progress tracking and status monitoring
"""

import json
import os
import sys
import time
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
from dataclasses import dataclass

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from tools.core import execute_async, execute_sync, parallel_map, TaskPriority
from tools.core import get_cache, get_scheduler, load_yaml, save_yaml, now_str
from tools.core import run_tool, run_tool_with_retry, get_tool_router

class TaskType(Enum):
    MEMORY_ANALYSIS = "memory_analysis"
    DISK_ANALYSIS = "disk_analysis"
    NETWORK_ANALYSIS = "network_analysis"
    MOBILE_ANALYSIS = "mobile_analysis"
    WEB_PENTEST = "web_pentest"
    CRYPTO_ANALYSIS = "crypto_analysis"
    STEGO_ANALYSIS = "stego_analysis"
    REVERSE_ENGINEERING = "reverse_engineering"
    LOG_ANALYSIS = "log_analysis"
    DATA_RECOVERY = "data_recovery"

class TaskDifficulty(Enum):
    EASY = 1
    MEDIUM = 2
    HARD = 3
    EXPERT = 4

@dataclass
class AnalysisTask:
    id: str
    type: TaskType
    description: str
    difficulty: TaskDifficulty
    evidence_path: str
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: List[str] = None
    estimated_time_minutes: int = 60
    assigned_role: str = ""
    status: str = "pending"
    progress: int = 0
    result: Optional[Dict] = None
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []

ROLE_CAPABILITIES = {
    "computer_analyst": [
        TaskType.MEMORY_ANALYSIS,
        TaskType.DISK_ANALYSIS,
        TaskType.LOG_ANALYSIS,
        TaskType.DATA_RECOVERY,
    ],
    "mobile_analyst": [
        TaskType.MOBILE_ANALYSIS,
    ],
    "network_analyst": [
        TaskType.NETWORK_ANALYSIS,
        TaskType.LOG_ANALYSIS,
    ],
    "web_pentester": [
        TaskType.WEB_PENTEST,
    ],
    "stego_crypto_analyst": [
        TaskType.CRYPTO_ANALYSIS,
        TaskType.STEGO_ANALYSIS,
    ],
    "binary_analyst": [
        TaskType.REVERSE_ENGINEERING,
        TaskType.CRYPTO_ANALYSIS,
    ],
}

DIFFICULTY_WEIGHTS = {
    TaskDifficulty.EASY: 1,
    TaskDifficulty.MEDIUM: 2,
    TaskDifficulty.HARD: 4,
    TaskDifficulty.EXPERT: 8,
}

class SmartScheduler:
    def __init__(self, case_dir: str):
        self.case_dir = Path(case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: Dict[str, AnalysisTask] = {}
        self._workloads: Dict[str, int] = {}
        self._cache = get_cache()
        self._scheduler = get_scheduler()
        
    def load_tasks(self):
        tasks_file = self.case_dir / "tasks.json"
        if tasks_file.exists():
            with open(tasks_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for task_id, task_data in data.items():
                    self._tasks[task_id] = AnalysisTask(
                        id=task_id,
                        type=TaskType(task_data["type"]),
                        description=task_data["description"],
                        difficulty=TaskDifficulty(task_data["difficulty"]),
                        evidence_path=task_data["evidence_path"],
                        priority=TaskPriority(task_data.get("priority", 2)),
                        dependencies=task_data.get("dependencies", []),
                        estimated_time_minutes=task_data.get("estimated_time_minutes", 60),
                        assigned_role=task_data.get("assigned_role", ""),
                        status=task_data.get("status", "pending"),
                        progress=task_data.get("progress", 0),
                        result=task_data.get("result"),
                    )
    
    def save_tasks(self):
        tasks_file = self.case_dir / "tasks.json"
        data = {}
        for task_id, task in self._tasks.items():
            data[task_id] = {
                "type": task.type.value,
                "description": task.description,
                "difficulty": task.difficulty.value,
                "evidence_path": task.evidence_path,
                "priority": task.priority.value,
                "dependencies": task.dependencies,
                "estimated_time_minutes": task.estimated_time_minutes,
                "assigned_role": task.assigned_role,
                "status": task.status,
                "progress": task.progress,
                "result": task.result,
            }
        with open(tasks_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def add_task(self, task: AnalysisTask):
        self._tasks[task.id] = task
    
    def get_task(self, task_id: str) -> Optional[AnalysisTask]:
        return self._tasks.get(task_id)
    
    def analyze_evidence(self, evidence_path: str) -> List[TaskType]:
        path = Path(evidence_path)
        extensions = {
            ".dmp": [TaskType.MEMORY_ANALYSIS],
            ".raw": [TaskType.DISK_ANALYSIS],
            ".e01": [TaskType.DISK_ANALYSIS],
            ".vmdk": [TaskType.DISK_ANALYSIS],
            ".vhd": [TaskType.DISK_ANALYSIS],
            ".pcap": [TaskType.NETWORK_ANALYSIS],
            ".pcapng": [TaskType.NETWORK_ANALYSIS],
            ".apk": [TaskType.MOBILE_ANALYSIS, TaskType.REVERSE_ENGINEERING],
            ".ipa": [TaskType.MOBILE_ANALYSIS, TaskType.REVERSE_ENGINEERING],
            ".zip": [TaskType.STEGO_ANALYSIS, TaskType.CRYPTO_ANALYSIS],
            ".rar": [TaskType.STEGO_ANALYSIS, TaskType.CRYPTO_ANALYSIS],
            ".7z": [TaskType.STEGO_ANALYSIS, TaskType.CRYPTO_ANALYSIS],
            ".jpg": [TaskType.STEGO_ANALYSIS],
            ".jpeg": [TaskType.STEGO_ANALYSIS],
            ".png": [TaskType.STEGO_ANALYSIS],
            ".bmp": [TaskType.STEGO_ANALYSIS],
            ".gif": [TaskType.STEGO_ANALYSIS],
            ".txt": [TaskType.CRYPTO_ANALYSIS],
            ".enc": [TaskType.CRYPTO_ANALYSIS],
            ".hash": [TaskType.CRYPTO_ANALYSIS],
            ".evtx": [TaskType.LOG_ANALYSIS],
            ".log": [TaskType.LOG_ANALYSIS],
            ".exe": [TaskType.REVERSE_ENGINEERING],
            ".dll": [TaskType.REVERSE_ENGINEERING],
            ".bin": [TaskType.REVERSE_ENGINEERING, TaskType.CRYPTO_ANALYSIS],
            ".dat": [TaskType.CRYPTO_ANALYSIS],
        }
        
        ext = path.suffix.lower()
        if ext in extensions:
            return extensions[ext]
        
        if path.is_dir():
            return [TaskType.DISK_ANALYSIS]
        
        return [TaskType.DATA_RECOVERY]
    
    def estimate_difficulty(self, evidence_path: str, task_type: TaskType) -> TaskDifficulty:
        path = Path(evidence_path)
        
        size_gb = 0
        if path.is_file():
            size_gb = path.stat().st_size / (1024 ** 3)
        
        if size_gb > 10:
            return TaskDifficulty.EXPERT
        elif size_gb > 2:
            return TaskDifficulty.HARD
        elif size_gb > 0.5:
            return TaskDifficulty.MEDIUM
        
        complex_types = [
            TaskType.REVERSE_ENGINEERING,
            TaskType.CRYPTO_ANALYSIS,
            TaskType.WEB_PENTEST,
        ]
        if task_type in complex_types:
            return TaskDifficulty.HARD
        
        return TaskDifficulty.EASY
    
    def suggest_roles(self, task_type: TaskType) -> List[str]:
        roles = []
        for role, capabilities in ROLE_CAPABILITIES.items():
            if task_type in capabilities:
                roles.append(role)
        return roles
    
    def calculate_workload(self, role: str) -> int:
        if role not in self._workloads:
            self._workloads[role] = 0
        
        active_tasks = [
            t for t in self._tasks.values() 
            if t.assigned_role == role and t.status == "running"
        ]
        
        total = 0
        for task in active_tasks:
            weight = DIFFICULTY_WEIGHTS[task.difficulty]
            priority_multiplier = task.priority.value
            total += weight * priority_multiplier
        
        return total
    
    def assign_task(self, task: AnalysisTask) -> str:
        candidates = self.suggest_roles(task.type)
        if not candidates:
            return ""
        
        best_role = ""
        min_workload = float('inf')
        
        for role in candidates:
            workload = self.calculate_workload(role)
            if workload < min_workload:
                min_workload = workload
                best_role = role
        
        if best_role:
            task.assigned_role = best_role
            task.status = "assigned"
            self._workloads[best_role] = min_workload + DIFFICULTY_WEIGHTS[task.difficulty]
        
        return best_role
    
    def auto_generate_tasks(self, evidence_dir: str) -> List[str]:
        evidence_path = Path(evidence_dir)
        if not evidence_path.exists():
            return []
        
        task_ids = []
        
        for item in evidence_path.rglob("*"):
            if item.is_file():
                task_types = self.analyze_evidence(str(item))
                for task_type in task_types:
                    difficulty = self.estimate_difficulty(str(item), task_type)
                    task = AnalysisTask(
                        id=f"TASK-{len(self._tasks)+1:04d}",
                        type=task_type,
                        description=f"Analyze {item.name}",
                        difficulty=difficulty,
                        evidence_path=str(item),
                        priority=self._get_priority(difficulty),
                        estimated_time_minutes=self._estimate_time(difficulty),
                    )
                    self.add_task(task)
                    self.assign_task(task)
                    task_ids.append(task.id)
        
        self.save_tasks()
        return task_ids
    
    def _get_priority(self, difficulty: TaskDifficulty) -> TaskPriority:
        if difficulty in [TaskDifficulty.HARD, TaskDifficulty.EXPERT]:
            return TaskPriority.HIGH
        return TaskPriority.MEDIUM
    
    def _estimate_time(self, difficulty: TaskDifficulty) -> int:
        base_times = {
            TaskDifficulty.EASY: 30,
            TaskDifficulty.MEDIUM: 60,
            TaskDifficulty.HARD: 120,
            TaskDifficulty.EXPERT: 240,
        }
        return base_times[difficulty]
    
    _TOOL_COMMANDS = {
        TaskType.MEMORY_ANALYSIS: [
            ("volatility3", ["-f", "{evidence}", "windows.pslist"]),
            ("volatility3", ["-f", "{evidence}", "windows.netscan"]),
            ("volatility3", ["-f", "{evidence}", "windows.cmdline"]),
            ("volatility3", ["-f", "{evidence}", "windows.dlllist"]),
        ],
        TaskType.DISK_ANALYSIS: [
            ("fsstat", ["{evidence}"]),
            ("fls", ["-r", "{evidence}"]),
        ],
        TaskType.NETWORK_ANALYSIS: [
            ("tshark", ["-r", "{evidence}", "-q", "-z", "io,phs"]),
            ("tshark", ["-r", "{evidence}", "-z", "conv,tcp"]),
        ],
        TaskType.LOG_ANALYSIS: [
            ("strings", ["-n", "8", "{evidence}"]),
        ],
        TaskType.STEGO_ANALYSIS: [
            ("binwalk", ["{evidence}"]),
            ("strings", ["-n", "6", "{evidence}"]),
        ],
        TaskType.CRYPTO_ANALYSIS: [
            ("strings", ["-n", "4", "{evidence}"]),
        ],
        TaskType.REVERSE_ENGINEERING: [
            ("file", ["{evidence}"]),
            ("strings", ["-n", "6", "{evidence}"]),
        ],
        TaskType.MOBILE_ANALYSIS: [
            ("unzip", ["-l", "{evidence}"]),
        ],
        TaskType.DATA_RECOVERY: [
            ("file", ["{evidence}"]),
            ("strings", ["-n", "6", "{evidence}"]),
        ],
        TaskType.WEB_PENTEST: [
            ("curl", ["-sI", "{evidence}"]),
        ],
    }

    def execute_task(self, task_id: str) -> str:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status != "assigned":
            raise ValueError(f"Task {task_id} not assigned")

        task.status = "running"
        self.save_tasks()

        commands = self._TOOL_COMMANDS.get(task.type, [])
        evidence = task.evidence_path

        def run_analysis():
            result = {
                "task_id": task.id,
                "type": task.type.value,
                "evidence": evidence,
                "steps": [],
                "findings": [],
                "tool_results": [],
                "completed_at": now_str(),
            }

            router = get_tool_router()
            available_tools = set()

            for tool_name, arg_template in commands:
                if tool_name not in available_tools:
                    if router.is_available(tool_name):
                        available_tools.add(tool_name)
                    else:
                        result["steps"].append(f"Skipped {tool_name} — not available")
                        continue

                args = [a.format(evidence=evidence) for a in arg_template]
                step_desc = f"{tool_name} {' '.join(args)}"
                result["steps"].append(step_desc)

                tool_result = run_tool_with_retry(tool_name, *args, timeout=120, retries=1)
                result["tool_results"].append(tool_result)

                if tool_result["success"]:
                    output_preview = tool_result["stdout"][:1000]
                    if output_preview.strip():
                        result["findings"].append(
                            f"[{tool_name}] {output_preview[:200]}"
                        )
                else:
                    result["findings"].append(
                        f"[{tool_name}] ERROR: {tool_result['stderr'][:200]}"
                    )

            if not result["findings"]:
                result["findings"].append(
                    f"No tools available for {task.type.value}"
                )

            result["completed_at"] = now_str()
            return result

        return execute_async(
            run_analysis,
            priority=task.priority,
            timeout=max(task.estimated_time_minutes * 60, 600)
        )
    
    def get_progress(self) -> Dict[str, Any]:
        progress = {
            "total_tasks": len(self._tasks),
            "by_status": {},
            "by_role": {},
            "by_type": {},
        }
        
        for task in self._tasks.values():
            status = task.status
            progress["by_status"][status] = progress["by_status"].get(status, 0) + 1
            
            role = task.assigned_role or "unassigned"
            progress["by_role"][role] = progress["by_role"].get(role, 0) + 1
            
            task_type = task.type.value
            progress["by_type"][task_type] = progress["by_type"].get(task_type, 0) + 1
        
        return progress
    
    def update_task_status(self, task_id: str, status: str, result: Optional[Dict] = None):
        task = self._tasks.get(task_id)
        if task:
            task.status = status
            if result:
                task.result = result
                if status == "completed":
                    task.progress = 100
            self.save_tasks()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Smart Task Scheduler")
    parser.add_argument("--case-dir", required=True, help="Case directory")
    parser.add_argument("--auto-generate", action="store_true", help="Auto generate tasks from evidence")
    parser.add_argument("--evidence-dir", help="Directory containing evidence files")
    parser.add_argument("--execute", help="Execute a specific task")
    parser.add_argument("--progress", action="store_true", help="Show progress")
    args = parser.parse_args()
    
    scheduler = SmartScheduler(args.case_dir)
    scheduler.load_tasks()
    
    if args.auto_generate and args.evidence_dir:
        task_ids = scheduler.auto_generate_tasks(args.evidence_dir)
        print(f"Generated {len(task_ids)} tasks:")
        for tid in task_ids:
            task = scheduler.get_task(tid)
            print(f"  {tid}: {task.type.value} - {task.description} (assigned to: {task.assigned_role})")
    
    if args.execute:
        try:
            future_id = scheduler.execute_task(args.execute)
            print(f"Task {args.execute} submitted as {future_id}")
        except Exception as e:
            print(f"Error: {e}")
    
    if args.progress:
        progress = scheduler.get_progress()
        print(json.dumps(progress, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()