"""
四阶段流水线队列管理器
借鉴自 jav-scrapy 的 QueueManager 实现
"""
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum
import time
import psutil  # 用于资源监控

logger = logging.getLogger(__name__)


class QueueType(Enum):
    """队列类型"""
    INDEX = "index"          # 索引页队列
    DETAIL = "detail"        # 详情页队列
    WRITE = "write"          # 写入队列
    DOWNLOAD = "download"    # 下载队列


@dataclass
class QueueStats:
    """队列统计信息"""
    queue_type: QueueType
    size: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    concurrency: int = 1
    avg_process_time: float = 0.0


class ResourceMonitor:
    """资源监控器"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.cpu_history: List[float] = []
        self.memory_history: List[float] = []
        self.max_history_size = 60  # 保留60个采样点
    
    def get_cpu_usage(self) -> float:
        """获取CPU使用率"""
        cpu = psutil.cpu_percent(interval=0.1)
        self.cpu_history.append(cpu)
        if len(self.cpu_history) > self.max_history_size:
            self.cpu_history.pop(0)
        return cpu
    
    def get_memory_usage(self) -> float:
        """获取内存使用率"""
        mem = psutil.virtual_memory().percent
        self.memory_history.append(mem)
        if len(self.memory_history) > self.max_history_size:
            self.memory_history.pop(0)
        return mem
    
    def get_avg_cpu(self, last_n: int = 10) -> float:
        """获取最近N次CPU使用率平均值"""
        if not self.cpu_history:
            return 0.0
        recent = self.cpu_history[-last_n:]
        return sum(recent) / len(recent)
    
    def get_avg_memory(self, last_n: int = 10) -> float:
        """获取最近N次内存使用率平均值"""
        if not self.memory_history:
            return 0.0
        recent = self.memory_history[-last_n:]
        return sum(recent) / len(recent)
    
    def is_overloaded(self, cpu_threshold: float = 80.0, mem_threshold: float = 80.0) -> bool:
        """检查是否过载"""
        avg_cpu = self.get_avg_cpu(5)
        avg_mem = self.get_avg_memory(5)
        return avg_cpu > cpu_threshold or avg_mem > mem_threshold
    
    def get_stats(self) -> Dict[str, Any]:
        """获取资源统计信息"""
        return {
            "cpu_usage": self.get_cpu_usage(),
            "avg_cpu": self.get_avg_cpu(),
            "memory_usage": self.get_memory_usage(),
            "avg_memory": self.get_avg_memory(),
            "is_overloaded": self.is_overloaded(),
            "elapsed_time": (datetime.now() - self.start_time).total_seconds()
        }


class AsyncTask:
    """异步任务"""
    
    def __init__(self, task_id: str, data: Any, priority: int = 0):
        self.task_id = task_id
        self.data = data
        self.priority = priority
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[Exception] = None
    
    def start(self):
        """标记任务开始"""
        self.started_at = datetime.now()
    
    def complete(self):
        """标记任务完成"""
        self.completed_at = datetime.now()
    
    def fail(self, error: Exception):
        """标记任务失败"""
        self.error = error
        self.completed_at = datetime.now()
    
    def get_duration(self) -> float:
        """获取任务耗时"""
        if not self.started_at or not self.completed_at:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()


class AsyncQueue:
    """异步队列"""
    
    def __init__(self, queue_type: QueueType, concurrency: int = 1):
        self.queue_type = queue_type
        self.concurrency = concurrency
        self.queue: asyncio.Queue = asyncio.Queue()
        self.processing_tasks: Dict[str, AsyncTask] = {}
        self.completed_tasks: List[AsyncTask] = []
        self.failed_tasks: List[AsyncTask] = []
        self.stats = QueueStats(queue_type=queue_type, concurrency=concurrency)
        self.workers: List[asyncio.Task] = []
        self.running = False
        self.processor: Optional[Callable] = None
    
    async def put(self, task_id: str, data: Any, priority: int = 0):
        """添加任务到队列"""
        task = AsyncTask(task_id, data, priority)
        await self.queue.put(task)
        self.stats.size += 1
        logger.debug(f"[{self.queue_type.value}] Task {task_id} added to queue")
    
    async def start(self, processor: Callable):
        """启动队列处理"""
        if self.running:
            return
        
        self.running = True
        self.processor = processor
        
        # 启动worker
        for i in range(self.concurrency):
            worker = asyncio.create_task(self._worker(f"{self.queue_type.value}-worker-{i}"))
            self.workers.append(worker)
        
        logger.info(f"[{self.queue_type.value}] Queue started with {self.concurrency} workers")
    
    async def _worker(self, worker_id: str):
        """Worker处理任务"""
        logger.info(f"[{worker_id}] Started")
        
        while self.running or not self.queue.empty():
            try:
                # 设置超时避免永久阻塞
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            
            try:
                self.stats.size -= 1
                self.stats.processing += 1
                task.start()
                self.processing_tasks[task.task_id] = task
                
                logger.info(f"[{worker_id}] Processing task {task.task_id}")
                
                # 处理任务
                await self.processor(task.data)
                
                # 任务完成
                task.complete()
                self.stats.processing -= 1
                self.stats.completed += 1
                self.completed_tasks.append(task)
                del self.processing_tasks[task.task_id]
                
                # 更新平均处理时间
                duration = task.get_duration()
                if duration > 0:
                    n = self.stats.completed
                    self.stats.avg_process_time = (
                        (self.stats.avg_process_time * (n - 1) + duration) / n
                    )
                
                logger.info(f"[{worker_id}] Task {task.task_id} completed in {duration:.2f}s")
                
            except Exception as e:
                logger.error(f"[{worker_id}] Task {task.task_id} failed: {e}")
                task.fail(e)
                self.stats.processing -= 1
                self.stats.failed += 1
                self.failed_tasks.append(task)
                del self.processing_tasks[task.task_id]
    
    async def stop(self):
        """停止队列处理"""
        logger.info(f"[{self.queue_type.value}] Stopping queue...")
        self.running = False
        
        # 等待所有worker完成
        for worker in self.workers:
            worker.cancel()
        
        # 等待worker取消
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        
        logger.info(f"[{self.queue_type.value}] Queue stopped")
    
    def update_concurrency(self, new_concurrency: int):
        """动态调整并发数"""
        old_concurrency = self.concurrency
        self.concurrency = new_concurrency
        self.stats.concurrency = new_concurrency
        logger.info(f"[{self.queue_type.value}] Concurrency updated: {old_concurrency} -> {new_concurrency}")
    
    def get_stats(self) -> QueueStats:
        """获取队列统计信息"""
        self.stats.size = self.queue.qsize()
        self.stats.processing = len(self.processing_tasks)
        return self.stats


class PipelineQueueManager:
    """四阶段流水线队列管理器"""
    
    def __init__(
        self,
        base_concurrency: int = 2,
        resource_monitor: Optional[ResourceMonitor] = None
    ):
        self.base_concurrency = base_concurrency
        self.resource_monitor = resource_monitor or ResourceMonitor()
        
        # 初始化四个队列
        self.queues: Dict[QueueType, AsyncQueue] = {}
        
        # 并发倍数配置
        self.concurrency_multipliers = {
            QueueType.INDEX: 1.0,      # 索引页: 1x
            QueueType.DETAIL: 0.75,    # 详情页: 0.75x
            QueueType.WRITE: 2.0,      # 写入: 2x
            QueueType.DOWNLOAD: 0.5    # 下载: 0.5x
        }
        
        self.running = False
        self.monitor_task: Optional[asyncio.Task] = None
    
    def create_queue(
        self,
        queue_type: QueueType,
        processor: Callable,
        custom_concurrency: Optional[int] = None
    ) -> AsyncQueue:
        """创建队列"""
        multiplier = self.concurrency_multipliers.get(queue_type, 1.0)
        concurrency = custom_concurrency or max(1, int(self.base_concurrency * multiplier))
        
        queue = AsyncQueue(queue_type, concurrency)
        self.queues[queue_type] = queue
        return queue
    
    async def start_queue(self, queue_type: QueueType, processor: Callable):
        """启动指定队列"""
        if queue_type not in self.queues:
            queue = self.create_queue(queue_type, processor)
        else:
            queue = self.queues[queue_type]
        
        await queue.start(processor)
        logger.info(f"Started {queue_type.value} queue with concurrency {queue.concurrency}")
    
    async def add_task(
        self,
        queue_type: QueueType,
        task_id: str,
        data: Any,
        priority: int = 0
    ):
        """添加任务到指定队列"""
        if queue_type not in self.queues:
            raise ValueError(f"Queue {queue_type.value} not initialized")
        
        await self.queues[queue_type].put(task_id, data, priority)
    
    async def start_all(self, processors: Dict[QueueType, Callable]):
        """启动所有队列"""
        self.running = True
        
        for queue_type, processor in processors.items():
            await self.start_queue(queue_type, processor)
        
        # 启动监控任务
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info("All queues started")
    
    async def stop_all(self):
        """停止所有队列"""
        self.running = False
        
        # 停止监控
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # 停止所有队列
        for queue in self.queues.values():
            await queue.stop()
        
        logger.info("All queues stopped")
    
    async def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                await self._adjust_concurrency()
                await self._log_stats()
                await asyncio.sleep(10)  # 每10秒检查一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
    
    async def _adjust_concurrency(self):
        """动态调整并发数"""
        if self.resource_monitor.is_overloaded():
            logger.warning("System overloaded, reducing concurrency")
            
            # 所有队列降低并发
            for queue in self.queues.values():
                new_concurrency = max(1, int(queue.concurrency * 0.6))
                queue.update_concurrency(new_concurrency)
        else:
            # 恢复并发
            for queue in self.queues.values():
                multiplier = self.concurrency_multipliers.get(queue.queue_type, 1.0)
                target_concurrency = max(1, int(self.base_concurrency * multiplier))
                
                if queue.concurrency < target_concurrency:
                    queue.update_concurrency(target_concurrency)
    
    async def _log_stats(self):
        """记录统计信息"""
        stats = self.get_all_stats()
        resource_stats = self.resource_monitor.get_stats()
        
        logger.info(
            f"Pipeline Stats - "
            f"CPU: {resource_stats['cpu_usage']:.1f}% | "
            f"Memory: {resource_stats['memory_usage']:.1f}% | "
            f"Index: {stats[QueueType.INDEX]} | "
            f"Detail: {stats[QueueType.DETAIL]} | "
            f"Write: {stats[QueueType.WRITE]} | "
            f"Download: {stats[QueueType.DOWNLOAD]}"
        )
    
    def get_all_stats(self) -> Dict[QueueType, QueueStats]:
        """获取所有队列统计信息"""
        return {
            queue_type: queue.get_stats()
            for queue_type, queue in self.queues.items()
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """获取汇总信息"""
        stats = self.get_all_stats()
        total_size = sum(s.size for s in stats.values())
        total_processing = sum(s.processing for s in stats.values())
        total_completed = sum(s.completed for s in stats.values())
        total_failed = sum(s.failed for s in stats.values())
        
        return {
            "total_size": total_size,
            "total_processing": total_processing,
            "total_completed": total_completed,
            "total_failed": total_failed,
            "queues": {
                qtype.value: {
                    "size": s.size,
                    "processing": s.processing,
                    "completed": s.completed,
                    "failed": s.failed,
                    "concurrency": s.concurrency,
                    "avg_time": s.avg_process_time
                }
                for qtype, s in stats.items()
            },
            "resource": self.resource_monitor.get_stats()
        }


# 使用示例
async def example_usage():
    """使用示例"""
    
    # 创建处理器函数
    async def process_index(data):
        print(f"Processing index: {data}")
        await asyncio.sleep(1)
    
    async def process_detail(data):
        print(f"Processing detail: {data}")
        await asyncio.sleep(2)
    
    async def process_write(data):
        print(f"Processing write: {data}")
        await asyncio.sleep(0.5)
    
    async def process_download(data):
        print(f"Processing download: {data}")
        await asyncio.sleep(3)
    
    # 创建管理器
    manager = PipelineQueueManager(base_concurrency=4)
    
    # 定义处理器
    processors = {
        QueueType.INDEX: process_index,
        QueueType.DETAIL: process_detail,
        QueueType.WRITE: process_write,
        QueueType.DOWNLOAD: process_download
    }
    
    # 启动所有队列
    await manager.start_all(processors)
    
    # 添加任务
    for i in range(10):
        await manager.add_task(QueueType.INDEX, f"task-{i}", {"id": i})
    
    # 等待一段时间
    await asyncio.sleep(15)
    
    # 获取统计
    summary = manager.get_summary()
    print(f"Summary: {summary}")
    
    # 停止所有队列
    await manager.stop_all()


if __name__ == "__main__":
    asyncio.run(example_usage())
