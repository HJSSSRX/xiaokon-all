from abc import ABC, abstractmethod
from typing import Callable, Dict, Any, Optional, List, Tuple
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import threading
from threading import Lock
import time
import uuid
from enum import Enum

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

class Task:
    def __init__(self, func: Callable, args: tuple = (), kwargs: dict = None, 
                 priority: TaskPriority = TaskPriority.MEDIUM, 
                 timeout: int = 300, retry_attempts: int = 0):
        self.id = str(uuid.uuid4())[:8]
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.priority = priority
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.attempt = 0
        self.status = TaskStatus.PENDING
        self.result = None
        self.error = None
        self.start_time = None
        self.end_time = None

class Scheduler(ABC):
    @abstractmethod
    def submit(self, task: Task) -> str:
        pass
    
    @abstractmethod
    def get_status(self, task_id: str) -> Optional[Task]:
        pass
    
    @abstractmethod
    def cancel(self, task_id: str) -> bool:
        pass
    
    @abstractmethod
    def shutdown(self, wait: bool = True) -> None:
        pass

class ThreadedScheduler(Scheduler):
    def __init__(self, max_workers: int = 8):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: Dict[str, Task] = {}
        self._futures: Dict[str, Any] = {}
        self._lock = Lock()
    
    def submit(self, task: Task) -> str:
        with self._lock:
            self._tasks[task.id] = task
            task.status = TaskStatus.RUNNING
            task.start_time = time.time()
        
        def wrapper():
            for attempt in range(task.retry_attempts + 1):
                try:
                    result = task.func(*task.args, **task.kwargs)
                    with self._lock:
                        task.status = TaskStatus.COMPLETED
                        task.result = result
                        task.end_time = time.time()
                    return result
                except Exception as e:
                    task.attempt = attempt + 1
                    if attempt < task.retry_attempts:
                        time.sleep(2 ** attempt)
                    else:
                        with self._lock:
                            task.status = TaskStatus.FAILED
                            task.error = str(e)
                            task.end_time = time.time()
                        raise
        
        future = self._executor.submit(wrapper)
        self._futures[task.id] = future
        return task.id
    
    def get_status(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)
    
    def cancel(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._futures:
                future = self._futures[task_id]
                if not future.done():
                    future.cancel()
                    task = self._tasks.get(task_id)
                    if task:
                        task.status = TaskStatus.CANCELLED
                    return True
        return False
    
    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

def _process_task_runner(task: Task):
    for attempt in range(task.retry_attempts + 1):
        try:
            return task.func(*task.args, **task.kwargs)
        except Exception:
            task.attempt = attempt + 1
            if attempt < task.retry_attempts:
                time.sleep(2 ** attempt)
            else:
                raise


class ProcessScheduler(Scheduler):
    def __init__(self, max_workers: int = 4):
        self._executor = ProcessPoolExecutor(max_workers=max_workers)
        self._tasks: Dict[str, Task] = {}
        self._futures: Dict[str, Any] = {}
        self._lock = Lock()

    def submit(self, task: Task) -> str:
        with self._lock:
            self._tasks[task.id] = task
            task.status = TaskStatus.RUNNING
            task.start_time = time.time()

        future = self._executor.submit(_process_task_runner, task)
        self._futures[task.id] = future

        def monitor():
            try:
                result = future.result(timeout=task.timeout)
                with self._lock:
                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.end_time = time.time()
            except Exception as e:
                with self._lock:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
                    task.end_time = time.time()

        t = threading.Thread(target=monitor)
        t.daemon = True
        t.start()

        return task.id
    
    def get_status(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)
    
    def cancel(self, task_id: str) -> bool:
        with self._lock:
            if task_id in self._futures:
                future = self._futures[task_id]
                if not future.done():
                    future.cancel()
                    task = self._tasks.get(task_id)
                    if task:
                        task.status = TaskStatus.CANCELLED
                    return True
        return False
    
    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)

_scheduler_instance: Optional[Scheduler] = None
_scheduler_lock = threading.Lock()

def get_scheduler() -> Scheduler:
    global _scheduler_instance
    if _scheduler_instance is not None:
        return _scheduler_instance

    with _scheduler_lock:
        if _scheduler_instance is not None:
            return _scheduler_instance
        _scheduler_instance = ThreadedScheduler()
        return _scheduler_instance

def execute_async(func: Callable, *args, priority: TaskPriority = TaskPriority.MEDIUM, 
                  timeout: int = 300, retry_attempts: int = 0, **kwargs) -> str:
    task = Task(func, args, kwargs, priority, timeout, retry_attempts)
    scheduler = get_scheduler()
    return scheduler.submit(task)

def execute_sync(func: Callable, *args, timeout: int = 300, **kwargs) -> Any:
    result = []
    error = []
    event = threading.Event()

    def wrapper():
        try:
            result.append(func(*args, **kwargs))
        except Exception as e:
            error.append(e)
        finally:
            event.set()

    t = threading.Thread(target=wrapper)
    t.daemon = True
    t.start()

    if event.wait(timeout=timeout):
        if error:
            raise error[0]
        return result[0] if result else None
    else:
        t.join(timeout=1.0)
        raise TimeoutError(f"Task timed out after {timeout} seconds")

def parallel_map(func: Callable, iterable: List, max_workers: int = 4) -> List[Tuple[Any, Any]]:
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(func, item): item for item in iterable}
        for future in as_completed(futures):
            item = futures[future]
            try:
                result = future.result()
                results.append((item, result))
            except Exception as e:
                results.append((item, e))
    return results