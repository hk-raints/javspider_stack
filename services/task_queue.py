"""
任务队列管理 - 尚书省负责调度

维护批量爬取任务队列，保证：
- 同一时间只执行一个女优爬取任务（避免触发反爬）
- 任务状态实时追踪
- 通过 WebSocket 推送进度
"""
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import deque

from db.session import SessionLocal
from db.models import CrawlTask, Actress

logger = logging.getLogger("shangshu.task_queue")


@dataclass
class TaskProgress:
    """单个女优爬取任务的实时进度"""
    actress_id: int
    actress_name: str
    task_id: int
    status: str = "pending"  # pending|running|completed|failed
    current_msg: str = ""
    done_works: int = 0
    total_works: int = 0
    done_magnets: int = 0
    logs: List[str] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def add_log(self, msg: str):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.logs.append(entry)
        # 只保留最近100条
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
            "logs": self.logs[-20:],  # 只传最近20条给前端
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "progress_pct": int(self.done_works / max(self.total_works, 1) * 100),
        }


class TaskQueue:
    """
    尚书省任务队列

    核心功能：
    - 添加女优到爬取队列
    - 顺序执行（每次1个）
    - WebSocket 广播进度
    """

    def __init__(self):
        self._queue: deque = deque()
        self._running: bool = False
        self._current_task_id: Optional[int] = None
        self._progress_map: Dict[int, TaskProgress] = {}  # actress_id -> TaskProgress
        self._ws_callbacks: List = []  # WebSocket 广播回调
        self._lock = asyncio.Lock()

    def register_ws_callback(self, callback):
        """注册 WebSocket 广播回调"""
        if callback not in self._ws_callbacks:
            self._ws_callbacks.append(callback)

    def unregister_ws_callback(self, callback):
        """注销 WebSocket 回调"""
        if callback in self._ws_callbacks:
            self._ws_callbacks.remove(callback)

    async def _broadcast(self):
        """广播所有任务进度到所有 WebSocket 连接"""
        data = self.get_all_progress()
        for cb in list(self._ws_callbacks):
            try:
                await cb(data)
            except Exception as e:
                logger.warning(f"WebSocket 广播失败: {e}")

    def add_to_queue(self, actress_id: int, actress_name: str) -> Optional[int]:
        """
        添加女优到爬取队列

        Returns:
            新建的 task_id，None 表示已在队列中
        """
        # 检查是否已在队列中
        for item in self._queue:
            if item["actress_id"] == actress_id:
                logger.info(f"{actress_name} 已在队列中")
                return None

        # 检查是否正在运行
        if self._current_task_id:
            progress = self._get_progress_by_actress(actress_id)
            if progress and progress.status == "running":
                logger.info(f"{actress_name} 正在运行中")
                return None

        # 创建数据库任务记录
        db = SessionLocal()
        try:
            task = CrawlTask(
                actress_id=actress_id,
                task_type="full",
                status="pending",
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id
        finally:
            db.close()

        # 初始化进度对象
        progress = TaskProgress(
            actress_id=actress_id,
            actress_name=actress_name,
            task_id=task_id,
        )
        progress.add_log(f"已加入队列")
        self._progress_map[actress_id] = progress

        # 加入队列
        self._queue.append({
            "actress_id": actress_id,
            "actress_name": actress_name,
            "task_id": task_id,
        })

        logger.info(f"[尚书省] {actress_name} 加入队列，task_id={task_id}，队列长度={len(self._queue)}")
        return task_id

    def remove_from_queue(self, actress_id: int) -> bool:
        """从队列中移除（仅能移除 pending 状态）"""
        for item in list(self._queue):
            if item["actress_id"] == actress_id:
                # 检查是否为 pending
                progress = self._progress_map.get(actress_id)
                if progress and progress.status == "running":
                    logger.warning(f"无法移除正在运行的任务: {actress_id}")
                    return False
                self._queue.remove(item)
                if actress_id in self._progress_map:
                    del self._progress_map[actress_id]
                # 删除数据库记录
                db = SessionLocal()
                try:
                    db.query(CrawlTask).filter(CrawlTask.id == item["task_id"]).delete()
                    db.commit()
                finally:
                    db.close()
                return True
        return False

    def clear_queue(self):
        """清空所有 pending 任务"""
        pending_ids = [
            item["actress_id"] for item in list(self._queue)
            if self._progress_map.get(item["actress_id"], TaskProgress(0, "", 0)).status != "running"
        ]
        for actress_id in pending_ids:
            self.remove_from_queue(actress_id)

    def get_queue_status(self) -> List[Dict]:
        """获取当前队列状态"""
        result = []
        for item in self._queue:
            progress = self._progress_map.get(item["actress_id"])
            result.append({
                "actress_id": item["actress_id"],
                "actress_name": item["actress_name"],
                "task_id": item["task_id"],
                "status": progress.status if progress else "pending",
                "progress_pct": progress.to_dict()["progress_pct"] if progress else 0,
            })
        return result

    def get_all_progress(self) -> Dict:
        """获取所有任务进度（用于 WebSocket 推送）"""
        return {
            "queue": self.get_queue_status(),
            "running": self._running,
            "progress_map": {
                aid: p.to_dict()
                for aid, p in self._progress_map.items()
            },
        }

    def get_progress(self, actress_id: int) -> Optional[TaskProgress]:
        return self._progress_map.get(actress_id)

    def _get_progress_by_actress(self, actress_id: int) -> Optional[TaskProgress]:
        return self._progress_map.get(actress_id)

    async def start(self):
        """启动队列处理循环"""
        if self._running:
            logger.info("[尚书省] 队列已在运行")
            return

        self._running = True
        logger.info("[尚书省] 任务队列启动")
        await self._process_loop()

    async def _process_loop(self):
        """主处理循环：依次执行队列中的任务"""
        from services.crawler_service import crawl_actress_full

        try:
            while self._queue:
                item = self._queue[0]
                actress_id = item["actress_id"]
                actress_name = item["actress_name"]
                task_id = item["task_id"]

                progress = self._progress_map.get(actress_id)
                if not progress:
                    self._queue.popleft()
                    continue

                progress.status = "running"
                progress.started_at = datetime.utcnow().isoformat()
                progress.add_log(f"▶️ 开始执行")
                self._current_task_id = task_id

                # 更新数据库任务状态
                db = SessionLocal()
                try:
                    task = db.query(CrawlTask).get(task_id)
                    if task:
                        task.status = "running"
                        task.started_at = datetime.utcnow()
                        db.commit()
                finally:
                    db.close()

                await self._broadcast()

                # 定义进度回调
                async def on_progress(msg: str, done: int, total: int):
                    if actress_id in self._progress_map:
                        p = self._progress_map[actress_id]
                        p.add_log(msg)
                        if done > 0:
                            p.done_works = done
                        if total > 0:
                            p.total_works = total
                        await self._broadcast()

                # 执行爬取
                success = await crawl_actress_full(actress_id, task_id, on_progress)

                # 更新完成状态
                progress.status = "completed" if success else "failed"
                progress.finished_at = datetime.utcnow().isoformat()
                progress.add_log("✅ 完成" if success else "❌ 失败")

                await self._broadcast()

                # 从队列移除
                self._queue.popleft()
                self._current_task_id = None

                # 短暂休息后处理下一个
                if self._queue:
                    logger.info("[尚书省] 等待5秒后处理下一个任务")
                    await asyncio.sleep(5)

        finally:
            self._running = False
            logger.info("[尚书省] 任务队列执行完毕")
            await self._broadcast()


# 全局任务队列单例（尚书省）
shangshu_queue = TaskQueue()
