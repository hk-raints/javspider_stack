"""
任务队列管理 - 异步版本
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import deque
from sqlalchemy import select, delete

from db.session import AsyncSessionLocal
from db.models import CrawlTask, Actress

logger = logging.getLogger("app.services.task_queue")

@dataclass
class TaskProgress:
    actress_id: int
    actress_name: str
    task_id: int
    status: str = "pending"
    current_msg: str = ""
    done_works: int = 0
    total_works: int = 0
    done_magnets: int = 0
    logs: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def add_log(self, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self.logs.append(f"[{ts}] {msg}")
        if len(self.logs) > 100:
            self.logs = self.logs[-100:]
        self.current_msg = msg

    def to_dict(self) -> Dict[str, Any]:
        return {
            "actress_id": self.actress_id,
            "actress_name": self.actress_name,
            "task_id": self.task_id,
            "status": self.status,
            "current_msg": self.current_msg,
            "done_works": self.done_works,
            "total_works": self.total_works,
            "done_magnets": self.done_magnets,
            "logs": self.logs[-20:],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress_pct": int(self.done_works / max(self.total_works, 1) * 100),
        }

class TaskQueue:
    def __init__(self):
        self._queue: deque = deque()
        self._running: bool = False
        self._current_task_id: Optional[int] = None
        self._progress_map: Dict[int, TaskProgress] = {}
        self._ws_callbacks: List = []
        self._lock = asyncio.Lock()

    def register_ws_callback(self, callback):
        if callback not in self._ws_callbacks:
            self._ws_callbacks.append(callback)

    def unregister_ws_callback(self, callback):
        if callback in self._ws_callbacks:
            self._ws_callbacks.remove(callback)

    async def _broadcast(self):
        data = self.get_all_progress()
        for cb in list(self._ws_callbacks):
            try:
                await cb(data)
            except Exception:
                pass

    async def add_to_queue(self, actress_id: int, actress_name: str) -> Optional[int]:
        async with self._lock:
            for item in self._queue:
                if item["actress_id"] == actress_id:
                    return None
            
            if actress_id in self._progress_map and self._progress_map[actress_id].status == "running":
                return None

            async with AsyncSessionLocal() as db:
                task = CrawlTask(actress_id=actress_id, status="pending")
                db.add(task)
                await db.commit()
                await db.refresh(task)
                task_id = task.id

            progress = TaskProgress(actress_id=actress_id, actress_name=actress_name, task_id=task_id)
            progress.add_log("已加入队列")
            self._progress_map[actress_id] = progress
            self._queue.append({"actress_id": actress_id, "actress_name": actress_name, "task_id": task_id})
            return task_id

    async def remove_from_queue(self, actress_id: int) -> bool:
        async with self._lock:
            for item in list(self._queue):
                if item["actress_id"] == actress_id:
                    progress = self._progress_map.get(actress_id)
                    if progress and progress.status == "running":
                        return False
                    
                    self._queue.remove(item)
                    self._progress_map.pop(actress_id, None)
                    async with AsyncSessionLocal() as db:
                        await db.execute(delete(CrawlTask).where(CrawlTask.id == item["task_id"]))
                        await db.commit()
                    return True
            return False

    def get_queue_status(self) -> List[Dict]:
        return [
            {
                "actress_id": i["actress_id"],
                "actress_name": i["actress_name"],
                "status": self._progress_map.get(i["actress_id"]).status if i["actress_id"] in self._progress_map else "pending"
            }
            for i in self._queue
        ]

    def get_all_progress(self) -> Dict:
        return {
            "queue": self.get_queue_status(),
            "running": self._running,
            "progress_map": {aid: p.to_dict() for aid, p in self._progress_map.items()},
        }

    async def start(self):
        if self._running: return
        self._running = True
        asyncio.create_task(self._process_loop())

    async def _process_loop(self):
        from app.services.crawler import crawl_actress_full
        try:
            while self._queue:
                item = self._queue[0]
                actress_id, task_id = item["actress_id"], item["task_id"]
                progress = self._progress_map.get(actress_id)
                if not progress:
                    self._queue.popleft()
                    continue

                progress.status = "running"
                progress.started_at = datetime.utcnow().isoformat()
                progress.add_log("▶️ 开始执行")
                self._current_task_id = task_id

                async with AsyncSessionLocal() as db:
                    await db.execute(select(CrawlTask).where(CrawlTask.id == task_id))
                    # 此处更新状态已经在 crawl_actress_full 中完成，这里仅确保进度对象状态一致
                
                await self._broadcast()

                async def on_progress(msg, done, total):
                    if actress_id in self._progress_map:
                        p = self._progress_map[actress_id]
                        p.add_log(msg)
                        if done > 0: p.done_works = done
                        if total > 0: p.total_works = total
                        await self._broadcast()

                success = await crawl_actress_full(actress_id, task_id, AsyncSessionLocal, on_progress)
                
                progress.status = "completed" if success else "failed"
                progress.finished_at = datetime.utcnow().isoformat()
                progress.add_log("✅ 完成" if success else "❌ 失败")
                await self._broadcast()
                
                self._queue.popleft()
                self._current_task_id = None
                if self._queue: await asyncio.sleep(5)
        finally:
            self._running = False
            await self._broadcast()

shangshu_queue = TaskQueue()
