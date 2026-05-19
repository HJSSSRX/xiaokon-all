#!/usr/bin/env python3
"""System Monitor - Track system health and performance metrics."""

import psutil
import time
import json
from datetime import datetime
from typing import Dict, Any

class SystemMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.metrics_history = []
    
    def get_cpu_metrics(self) -> Dict[str, Any]:
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "cpu_cores": psutil.cpu_count(logical=True),
            "cpu_frequency": psutil.cpu_freq().current if psutil.cpu_freq() else None,
        }
    
    def get_memory_metrics(self) -> Dict[str, Any]:
        mem = psutil.virtual_memory()
        return {
            "total_gb": mem.total / (1024 ** 3),
            "available_gb": mem.available / (1024 ** 3),
            "used_gb": mem.used / (1024 ** 3),
            "used_percent": mem.percent,
        }
    
    def get_disk_metrics(self) -> Dict[str, Any]:
        disk = psutil.disk_usage('/')
        return {
            "total_gb": disk.total / (1024 ** 3),
            "used_gb": disk.used / (1024 ** 3),
            "free_gb": disk.free / (1024 ** 3),
            "used_percent": disk.percent,
        }
    
    def get_network_metrics(self) -> Dict[str, Any]:
        net = psutil.net_io_counters()
        return {
            "bytes_sent_mb": net.bytes_sent / (1024 ** 2),
            "bytes_recv_mb": net.bytes_recv / (1024 ** 2),
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        }
    
    def get_process_metrics(self) -> Dict[str, Any]:
        process = psutil.Process()
        return {
            "pid": process.pid,
            "memory_percent": process.memory_percent(),
            "cpu_percent": process.cpu_percent(),
            "threads": process.num_threads(),
            "open_files": len(process.open_files()),
        }
    
    def get_uptime(self) -> float:
        return time.time() - self.start_time
    
    def get_all_metrics(self) -> Dict[str, Any]:
        return {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": self.get_uptime(),
            "cpu": self.get_cpu_metrics(),
            "memory": self.get_memory_metrics(),
            "disk": self.get_disk_metrics(),
            "network": self.get_network_metrics(),
            "process": self.get_process_metrics(),
        }
    
    def collect_and_store(self):
        metrics = self.get_all_metrics()
        self.metrics_history.append(metrics)
        
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]
        
        return metrics
    
    def get_summary(self) -> Dict[str, Any]:
        if not self.metrics_history:
            return {}
        
        avg_cpu = sum(m['cpu']['cpu_percent'] for m in self.metrics_history) / len(self.metrics_history)
        avg_mem = sum(m['memory']['used_percent'] for m in self.metrics_history) / len(self.metrics_history)
        
        return {
            "samples": len(self.metrics_history),
            "avg_cpu_percent": round(avg_cpu, 2),
            "avg_memory_percent": round(avg_mem, 2),
            "peak_cpu_percent": max(m['cpu']['cpu_percent'] for m in self.metrics_history),
            "peak_memory_percent": max(m['memory']['used_percent'] for m in self.metrics_history),
        }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="System Monitor")
    parser.add_argument("--interval", type=int, default=5, help="Collection interval in seconds")
    parser.add_argument("--count", type=int, default=10, help="Number of samples to collect")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    monitor = SystemMonitor()
    
    for i in range(args.count):
        metrics = monitor.collect_and_store()
        
        if args.json:
            print(json.dumps(metrics, indent=2))
        else:
            print(f"\n=== Sample {i+1} ===")
            print(f"Time: {metrics['timestamp']}")
            print(f"CPU: {metrics['cpu']['cpu_percent']}%")
            print(f"Memory: {metrics['memory']['used_percent']}% ({metrics['memory']['used_gb']:.2f} GB)")
            print(f"Disk: {metrics['disk']['used_percent']}% ({metrics['disk']['used_gb']:.2f} GB)")
        
        if i < args.count - 1:
            time.sleep(args.interval)
    
    if not args.json:
        summary = monitor.get_summary()
        print(f"\n=== Summary ===")
        print(f"Samples: {summary['samples']}")
        print(f"Average CPU: {summary['avg_cpu_percent']}%")
        print(f"Average Memory: {summary['avg_memory_percent']}%")
        print(f"Peak CPU: {summary['peak_cpu_percent']}%")
        print(f"Peak Memory: {summary['peak_memory_percent']}%")

if __name__ == "__main__":
    main()