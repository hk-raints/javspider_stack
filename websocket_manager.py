"""
WebSocket 管理器 - 用于实时推送爬虫进度和日志
"""
import asyncio
import json
from typing import Dict, List, Set
from datetime import datetime


class CrawlProgress:
    """爬虫进度追踪器"""
    
    def __init__(self, actress_id: int, actress_name: str):
        self.actress_id = actress_id
        self.actress_name = actress_name
        self.total_works = 0
        self.completed_works = 0
        self.total_magnets = 0
        self.status = "starting"  # starting, running, completed, error
        self.logs: List[Dict] = []
        self.start_time = datetime.now()
        self.end_time = None
        self.error_message = None
        
    def to_dict(self) -> Dict:
        return {
            "actress_id": self.actress_id,
            "actress_name": self.actress_name,
            "total_works": self.total_works,
            "completed_works": self.completed_works,
            "total_magnets": self.total_magnets,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "elapsed_seconds": self.elapsed_seconds,
            "logs": self.logs[-50:],  # 只返回最近50条日志
            "error": self.error_message
        }
    
    @property
    def progress_percent(self) -> int:
        if self.total_works == 0:
            return 0
        return int((self.completed_works / self.total_works) * 100)
    
    @property
    def elapsed_seconds(self) -> int:
        end = self.end_time or datetime.now()
        return int((end - self.start_time).total_seconds())
    
    def add_log(self, message: str, level: str = "info"):
        """添加日志条目"""
        self.logs.append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "message": message,
            "level": level
        })
    
    def update_progress(self, completed: int = None, total: int = None, magnets: int = None):
        """更新进度"""
        if completed is not None:
            self.completed_works = completed
        if total is not None:
            self.total_works = total
        if magnets is not None:
            self.total_magnets = magnets
    
    def complete(self):
        """标记完成"""
        self.status = "completed"
        self.end_time = datetime.now()
    
    def set_error(self, message: str):
        """标记错误"""
        self.status = "error"
        self.error_message = message
        self.end_time = datetime.now()


class WebSocketManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # actress_id -> Set[websocket]
        self.connections: Dict[int, Set] = {}
        # actress_id -> CrawlProgress
        self.progress: Dict[int, CrawlProgress] = {}
        
    def register_progress(self, actress_id: int, actress_name: str) -> CrawlProgress:
        """注册新的爬虫任务"""
        progress = CrawlProgress(actress_id, actress_name)
        self.progress[actress_id] = progress
        return progress
    
    def get_progress(self, actress_id: int) -> CrawlProgress:
        """获取进度对象"""
        return self.progress.get(actress_id)
    
    def remove_progress(self, actress_id: int):
        """移除进度追踪"""
        if actress_id in self.progress:
            del self.progress[actress_id]
    
    async def connect(self, websocket, actress_id: int):
        """客户端连接"""
        if actress_id not in self.connections:
            self.connections[actress_id] = set()
        self.connections[actress_id].add(websocket)
        
        # 发送当前进度状态
        progress = self.get_progress(actress_id)
        if progress:
            await websocket.send_json({
                "type": "progress",
                "data": progress.to_dict()
            })
    
    def disconnect(self, websocket, actress_id: int):
        """客户端断开连接"""
        if actress_id in self.connections:
            self.connections[actress_id].discard(websocket)
    
    async def broadcast_progress(self, actress_id: int):
        """广播进度更新"""
        if actress_id not in self.connections:
            return
            
        progress = self.get_progress(actress_id)
        if not progress:
            return
            
        message = {
            "type": "progress",
            "data": progress.to_dict()
        }
        
        # 收集断开的连接
        disconnected = set()
        for ws in self.connections[actress_id]:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.add(ws)
        
        # 清理断开的连接
        for ws in disconnected:
            self.connections[actress_id].discard(ws)
    
    async def broadcast_log(self, actress_id: int, message: str, level: str = "info"):
        """广播日志消息"""
        progress = self.get_progress(actress_id)
        if progress:
            progress.add_log(message, level)
            await self.broadcast_progress(actress_id)


# 全局 WebSocket 管理器实例
manager = WebSocketManager()
