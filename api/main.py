"""
JavSpider Stack - FastAPI 主入口

路由规划：
GET  /                      - 前端看板主页
GET  /api/actresses         - 女优列表（分页/搜索）
POST /api/actresses/crawl-all  - 爬取全站女优列表
GET  /api/actress/{id}      - 女优详情（含个人信息）
GET  /api/actress/{id}/works - 女优作品列表（分页/筛选）
GET  /api/works             - 全部作品列表（分页/筛选）
GET  /api/work/{id}         - 作品详情（含所有磁力）
GET  /api/tags              - 所有标签
GET  /api/tags/stats        - 标签使用统计

POST /api/batch/add         - 添加女优到批量爬取队列
POST /api/batch/remove/{id} - 从队列移除
POST /api/batch/clear       - 清空队列
POST /api/batch/start       - 启动批量爬取
GET  /api/batch/queue       - 获取队列状态
GET  /api/batch/progress    - 获取所有进度

WS  /ws/progress            - WebSocket 实时进度推送
"""
import asyncio
import json
import logging
import os
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from config import SERVER_HOST, SERVER_PORT
from db.session import get_db
from db.models import Actress, Work, Tag, WorkTag, WorkCast, Magnet, MagnetPick, CrawlTask
from db import init_db
from services.task_queue import shangshu_queue
from services.crawler_service import crawl_actresses_list, save_actresses_to_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("api")

app = FastAPI(title="JavSpider Stack", version="2.0.0")

# 静态文件（如有）
static_dir = Path(__file__).parent.parent / "dashboard"
if static_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(static_dir)), name="dashboard")

# 静态资源目录（CSS / JS）
resources_dir = Path(__file__).parent.parent / "static"
if resources_dir.exists():
    app.mount("/static", StaticFiles(directory=str(resources_dir)), name="resources")

# 封面图片目录
covers_dir = Path(__file__).parent.parent / "static" / "covers"
if covers_dir.exists():
    app.mount("/static/covers", StaticFiles(directory=str(covers_dir)), name="covers")

# 女优头像目录
avatars_dir = Path(__file__).parent.parent / "static" / "avatars"
if avatars_dir.exists():
    app.mount("/static/avatars", StaticFiles(directory=str(avatars_dir)), name="avatars")


@app.on_event("startup")
async def startup():
    """应用启动时初始化数据库"""
    init_db()
    logger.info("数据库初始化完成")


# ─────────────────────────────────────────────
# WebSocket 连接管理
# ─────────────────────────────────────────────

class WSManager:
    def __init__(self):
        self.connections: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)
        logger.info(f"WebSocket 连接，当前 {len(self.connections)} 个连接")

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)
        logger.info(f"WebSocket 断开，当前 {len(self.connections)} 个连接")

    async def broadcast(self, data: dict):
        disconnected = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.disconnect(ws)


ws_manager = WSManager()


async def ws_broadcast_callback(data: dict):
    """队列进度变化时广播给所有 WebSocket 客户端"""
    await ws_manager.broadcast({"type": "queue_progress", "data": data})


# 注册广播回调
shangshu_queue.register_ws_callback(ws_broadcast_callback)


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """WebSocket 实时进度推送"""
    await ws_manager.connect(websocket)
    # 立即发送当前状态
    await websocket.send_json({
        "type": "queue_progress",
        "data": shangshu_queue.get_all_progress()
    })
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# ─────────────────────────────────────────────
# 前端主页
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    """返回前端看板 HTML"""
    dashboard_file = Path(__file__).parent.parent / "dashboard" / "index.html"
    if dashboard_file.exists():
        return HTMLResponse(content=dashboard_file.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>看板文件未找到</h1>")


# ─────────────────────────────────────────────
# 女优 API
# ─────────────────────────────────────────────

@app.get("/api/actresses")
def list_actresses(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    profile_crawled: Optional[bool] = Query(None),
    db: Session = Depends(get_db)
):
    """
    获取女优列表（分页+搜索）
    """
    q = db.query(Actress)

    if search:
        q = q.filter(Actress.name.like(f"%{search}%"))
    if profile_crawled is not None:
        q = q.filter(Actress.profile_crawled == profile_crawled)

    total = q.count()
    items = q.order_by(Actress.name.asc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "items": [_actress_to_dict(a) for a in items],
    }


@app.get("/api/actresses/with-works")
def list_actresses_with_works(
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """获取有作品的女优列表（用于作品筛选）
    
    只返回通过 WorkCast 表真正建立了作品关联的女优。
    如果 WorkCast 为空，返回空列表。
    """
    from sqlalchemy import func
    
    # 从 WorkCast 获取有作品的女优
    if db.query(WorkCast).count() > 0:
        actress_ids = db.query(WorkCast.actress_id).distinct().all()
        actresses = db.query(Actress).filter(Actress.id.in_([a[0] for a in actress_ids])).limit(limit).all()
    else:
        # WorkCast 为空，说明还没有建立作品-女优关联，返回空列表
        actresses = []
    
    return [{"id": a.id, "name": a.name, "avatar": (JAVBUS_BASE + a.avatar) if a.avatar and not a.avatar.startswith("http") else (a.avatar or "")} for a in actresses]


@app.get("/api/actress/{actress_id}")
def get_actress(actress_id: int, db: Session = Depends(get_db)):
    """获取女优详情（含个人信息）"""
    a = db.query(Actress).get(actress_id)
    if not a:
        return JSONResponse({"error": "女优不存在"}, status_code=404)
    return _actress_to_dict(a, detail=True)


@app.get("/api/actress/{actress_id}/works")
def get_actress_works(
    actress_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    search: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    has_magnet: Optional[bool] = Query(None),
    sort_by: str = Query("release_date"),  # release_date|code
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db)
):
    """获取女优作品列表（分页+筛选）"""
    # 通过 WorkCast 关联查询
    q = db.query(Work).join(WorkCast, Work.id == WorkCast.work_id).filter(
        WorkCast.actress_id == actress_id
    )

    if search:
        q = q.filter(Work.code.like(f"%{search}%") | Work.title.like(f"%{search}%"))
    if date_from:
        q = q.filter(Work.release_date >= date_from)
    if date_to:
        q = q.filter(Work.release_date <= date_to)
    if tag:
        q = q.join(WorkTag, Work.id == WorkTag.work_id).join(Tag).filter(Tag.name.like(f"%{tag}%"))
    if has_magnet is True:
        q = q.filter(Work.magnets_crawled == True)

    if sort_by == "release_date":
        q = q.order_by(Work.release_date.desc() if sort_order == "desc" else Work.release_date.asc())
    elif sort_by == "code":
        q = q.order_by(Work.code.desc() if sort_order == "desc" else Work.code.asc())

    total = q.count()
    works = q.offset((page - 1) * per_page).limit(per_page).all()

    # 预加载所有关联数据（解决 N+1 问题）
    work_ids = [w.id for w in works]
    preload = _preload_work_relations(db, work_ids)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "items": [_work_to_dict(w, db, preload) for w in works],
    }


# ─────────────────────────────────────────────
# 作品 API
# ─────────────────────────────────────────────

@app.get("/api/works")
def list_works(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=100),
    search: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    studio: Optional[str] = Query(None),
    director: Optional[str] = Query(None),
    actress_id: Optional[int] = Query(None, description="按女优ID筛选"),
    actress_name: Optional[str] = Query(None, description="按女优名字筛选"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    has_magnet: Optional[bool] = Query(None),
    sort_by: str = Query("release_date"),
    sort_order: str = Query("desc"),
    db: Session = Depends(get_db)
):
    """全部作品列表（分页+多维筛选，用于数据分析）"""
    q = db.query(Work)

    if search:
        q = q.filter(Work.code.like(f"%{search}%") | Work.title.like(f"%{search}%"))
    if studio:
        q = q.filter(Work.studio.like(f"%{studio}%"))
    if director:
        q = q.filter(Work.director.like(f"%{director}%"))
    if actress_id:
        # 优先从 WorkCast 查询，如果没有数据则从女优表查询
        q = q.join(WorkCast, Work.id == WorkCast.work_id, isouter=True).filter(WorkCast.actress_id == actress_id)
    if actress_name:
        # 优先从 WorkCast 查询，如果没有数据则直接搜索作品标题
        from sqlalchemy import or_
        # 先尝试 WorkCast
        q = q.outerjoin(WorkCast, Work.id == WorkCast.work_id).outerjoin(
            Actress, WorkCast.actress_id == Actress.id
        ).filter(
            or_(Actress.name.like(f"%{actress_name}%"), Work.title.like(f"%{actress_name}%"))
        ).distinct()
    if date_from:
        q = q.filter(Work.release_date >= date_from)
    if date_to:
        q = q.filter(Work.release_date <= date_to)
    if tag:
        q = q.join(WorkTag, Work.id == WorkTag.work_id).join(Tag).filter(Tag.name.like(f"%{tag}%"))
    if has_magnet is True:
        q = q.filter(Work.magnets_crawled == True)

    if sort_by == "release_date":
        q = q.order_by(Work.release_date.desc() if sort_order == "desc" else Work.release_date.asc())
    elif sort_by == "code":
        q = q.order_by(Work.code.desc() if sort_order == "desc" else Work.code.asc())

    total = q.count()
    works = q.offset((page - 1) * per_page).limit(per_page).all()

    # 预加载所有关联数据（解决 N+1 问题）
    work_ids = [w.id for w in works]
    preload = _preload_work_relations(db, work_ids)

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "items": [_work_to_dict(w, db, preload) for w in works],
    }


@app.get("/api/work/{work_id}")
def get_work_detail(work_id: int, db: Session = Depends(get_db)):
    """获取作品详情（含全部磁力候选 + 筛选结果 + 标签 + 演员）"""
    work = db.query(Work).get(work_id)
    if not work:
        return JSONResponse({"error": "作品不存在"}, status_code=404)

    # 磁力候选（全部，按优先级+大小排序）
    magnets = db.query(Magnet).filter(Magnet.work_id == work_id).order_by(
        Magnet.priority_level.asc(), Magnet.size_mb.desc()
    ).all()

    # 最优磁力
    picked = db.query(MagnetPick).filter(MagnetPick.work_id == work_id).first()

    # 标签
    tags = db.query(Tag).join(WorkTag).filter(WorkTag.work_id == work_id).all()

    # 演员
    cast = db.query(Actress).join(WorkCast).filter(WorkCast.work_id == work_id).all()

    return {
        "id": work.id,
        "code": work.code,
        "title": work.title,
        "cover": work.cover,
        "release_date": work.release_date,
        "director": work.director,
        "studio": work.studio,
        "label": work.label,
        "series": work.series,
        "work_url": work.work_url,
        "detail_crawled": work.detail_crawled,
        "magnets_crawled": work.magnets_crawled,
        "tags": [{"id": t.id, "name": t.name} for t in tags],
        "cast": [_actress_to_dict(a) for a in cast],
        "magnets": [{
            "id": m.id,
            "name": m.name,
            "magnet_url": m.magnet_url,
            "size_str": m.size_str,
            "size_mb": m.size_mb,
            "share_date": m.share_date,
            "priority_level": m.priority_level,
            "is_uc": m.is_uc,
            "is_u": m.is_u,
            "is_4k": m.is_4k,
            "is_uncensored": m.is_uncensored,
            "is_c": m.is_c,
        } for m in magnets],
        "picked_magnet": {
            "name": picked.name,
            "magnet_url": picked.magnet_url,
            "size_str": picked.size_str,
            "size_mb": picked.size_mb,
            "share_date": picked.share_date,
            "priority_level": picked.priority_level,
            "pick_reason": picked.pick_reason,
        } if picked else None,
        "total_magnets": len(magnets),
    }


# ─────────────────────────────────────────────
# 标签 API（数据分析用）
# ─────────────────────────────────────────────

@app.get("/api/tags")
def list_tags(
    search: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """获取所有标签"""
    q = db.query(Tag)
    if search:
        q = q.filter(Tag.name.like(f"%{search}%"))
    tags = q.order_by(Tag.name.asc()).limit(limit).all()
    return [{"id": t.id, "name": t.name} for t in tags]


@app.get("/api/tags/stats")
def tag_stats(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """标签使用频次统计（数据分析）"""
    from sqlalchemy import func
    stats = db.query(
        Tag.id, Tag.name,
        func.count(WorkTag.work_id).label("count")
    ).join(WorkTag).group_by(Tag.id).order_by(func.count(WorkTag.work_id).desc()).limit(limit).all()

    return [{"id": s.id, "name": s.name, "count": s.count} for s in stats]


# ─────────────────────────────────────────────
# 全站女优列表爬取 API
# ─────────────────────────────────────────────

_actresses_crawl_running = False
_actresses_crawl_progress = {"status": "idle", "msg": "", "current": 0, "total": 0, "count": 0}


@app.post("/api/actresses/crawl-all")
async def crawl_all_actresses(background: BackgroundTasks, db: Session = Depends(get_db)):
    """
    爬取全站所有女优列表（分页），保存到数据库
    这是中书省接受的第一道旨意
    """
    global _actresses_crawl_running, _actresses_crawl_progress

    if _actresses_crawl_running:
        return {"ok": False, "msg": "已有女优列表爬取任务在运行"}

    _actresses_crawl_running = True
    _actresses_crawl_progress = {"status": "running", "msg": "开始...", "current": 0, "total": 0, "count": 0}

    async def job():
        global _actresses_crawl_running, _actresses_crawl_progress

        async def on_progress(msg: str, current: int, total: int):
            _actresses_crawl_progress.update({
                "status": "running",
                "msg": msg,
                "current": current,
                "total": total,
            })
            await ws_manager.broadcast({"type": "actresses_crawl", "data": _actresses_crawl_progress})

        try:
            actresses = await crawl_actresses_list(on_progress)
            db2 = next(get_db())
            save_actresses_to_db(actresses, db2)
            _actresses_crawl_progress.update({
                "status": "completed",
                "msg": f"✅ 完成！共 {len(actresses)} 位女优",
                "count": len(actresses),
            })
        except Exception as e:
            _actresses_crawl_progress.update({
                "status": "failed",
                "msg": f"❌ 失败: {e}",
            })
            logger.error(f"全站女优爬取失败: {e}", exc_info=True)
        finally:
            _actresses_crawl_running = False
            await ws_manager.broadcast({"type": "actresses_crawl", "data": _actresses_crawl_progress})

    background.add_task(job)
    return {"ok": True, "msg": "全站女优列表爬取已启动，请通过 WebSocket 接收进度"}


@app.get("/api/actresses/crawl-all/progress")
def get_actresses_crawl_progress():
    """获取全站女优爬取进度（REST 备用）"""
    return _actresses_crawl_progress


# ─────────────────────────────────────────────
# 批量爬取 API（尚书省调度）
# ─────────────────────────────────────────────

@app.post("/api/batch/add")
def add_to_batch(actress_ids: List[int], db: Session = Depends(get_db)):
    """批量添加女优到爬取队列"""
    added = []
    failed = []

    for actress_id in actress_ids:
        a = db.query(Actress).get(actress_id)
        if not a:
            failed.append({"id": actress_id, "reason": "不存在"})
            continue

        task_id = shangshu_queue.add_to_queue(actress_id, a.name)
        if task_id:
            added.append({"id": actress_id, "name": a.name, "task_id": task_id})
        else:
            failed.append({"id": actress_id, "name": a.name, "reason": "已在队列中"})

    return {
        "ok": True,
        "added": added,
        "failed": failed,
        "queue_size": len(shangshu_queue._queue),
    }


@app.post("/api/batch/remove/{actress_id}")
def remove_from_batch(actress_id: int):
    """从队列中移除女优"""
    success = shangshu_queue.remove_from_queue(actress_id)
    return {"ok": success, "msg": "已移除" if success else "移除失败（可能正在运行）"}


@app.post("/api/batch/clear")
def clear_batch():
    """清空队列（仅清 pending）"""
    shangshu_queue.clear_queue()
    return {"ok": True}


@app.post("/api/batch/start")
async def start_batch(background: BackgroundTasks):
    """启动批量爬取"""
    if not shangshu_queue._queue:
        return {"ok": False, "msg": "队列为空"}
    if shangshu_queue._running:
        return {"ok": False, "msg": "已在运行中"}

    background.add_task(shangshu_queue.start)
    return {"ok": True, "msg": f"已启动批量爬取，共 {len(shangshu_queue._queue)} 个女优"}


@app.get("/api/batch/queue")
def get_batch_queue():
    """获取队列状态"""
    return shangshu_queue.get_queue_status()


@app.get("/api/batch/progress")
def get_batch_progress():
    """获取所有任务进度（REST 备用）"""
    return shangshu_queue.get_all_progress()


# ─────────────────────────────────────────────
# 统计 API
# ─────────────────────────────────────────────

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """全局统计数据"""
    from sqlalchemy import func

    return {
        "total_actresses": db.query(Actress).count(),
        "profile_crawled": db.query(Actress).filter(Actress.profile_crawled == True).count(),
        "total_works": db.query(Work).count(),
        "works_with_magnets": db.query(Work).filter(Work.magnets_crawled == True).count(),
        "total_magnets": db.query(Magnet).count(),
        "total_tags": db.query(Tag).count(),
        "queue_size": len(shangshu_queue._queue),
        "queue_running": shangshu_queue._running,
    }


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

JAVBUS_BASE = "https://www.javbus.com"
STATIC_AVATARS_DIR = Path(__file__).parent.parent / "static" / "avatars"

def _actress_to_dict(a: Actress, detail: bool = False) -> dict:
    # 处理头像 URL：优先返回本地头像
    avatar = a.avatar or ""
    if avatar and not avatar.startswith("http"):
        # 检查本地是否有头像
        avatar_filename = avatar.split("/")[-1]
        local_path = STATIC_AVATARS_DIR / avatar_filename
        if local_path.exists():
            avatar = f"/static/avatars/{avatar_filename}"
        else:
            avatar = JAVBUS_BASE + avatar
    
    d = {
        "id": a.id,
        "name": a.name,
        "javbus_id": a.javbus_id,
        "profile_url": a.profile_url,
        "avatar": avatar,
        "profile_crawled": a.profile_crawled,
        "works_crawled": a.works_crawled,
        # 始终返回基本信息
        "birthday": a.birthday,
        "age": a.age,
        "height": a.height,
        "cup": a.cup,
        "bust": a.bust,
        "waist": a.waist,
        "hip": a.hip,
        "hobby": a.hobby,
    }
    if detail:
        d.update({
            # 详情模式可以扩展更多
        })
    return d


def _work_to_dict(
    w: Work,
    db: Session,
    preload: Optional[dict] = None
) -> dict:
    """
    将 Work ORM 对象转换为字典。
    
    Args:
        w: Work ORM 对象
        db: 数据库 session（仅在 preload 为空时用于单次查询）
        preload: 可选，预加载的数据字典，包含:
            - picked: dict {work_id: MagnetPick}  # work_id → MagnetPick
            - tags: dict {work_id: [Tag, ...]}  # work_id → 标签列表
            - cast: dict {work_id: [Actress, ...]}  # work_id → 演员列表
    """
    # 使用预加载数据（推荐），避免 N+1 查询
    if preload:
        picked = preload.get("picked", {}).get(w.id)
        tags = preload.get("tags", {}).get(w.id, [])
        cast = preload.get("cast", {}).get(w.id, [])
    else:
        # 兜底：单次查询（仅详情页用）
        picked = db.query(MagnetPick).filter(MagnetPick.work_id == w.id).first()
        tags = db.query(Tag).join(WorkTag).filter(WorkTag.work_id == w.id).all()
        cast = db.query(Actress).join(WorkCast).filter(WorkCast.work_id == w.id).all()

    # 处理封面 URL - 转换为本地文件路径
    cover = w.cover or ""
    if cover:
        # 如果是 /pics/cover/xxx.jpg 格式，转换为本地路径
        if cover.startswith("/pics/cover/"):
            filename = cover.replace("/pics/cover/", "").replace("/", "_")
            local_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'covers', filename)
            if os.path.exists(local_path):
                cover = f"/static/covers/{filename}"
            else:
                # 本地文件不存在才用 JavBus URL
                cover = JAVBUS_BASE + cover
        # 如果已经是本地路径则直接使用
        elif not cover.startswith("/static/") and not cover.startswith("http"):
            cover = JAVBUS_BASE + cover

    return {
        "id": w.id,
        "code": w.code,
        "title": w.title,
        "cover": cover,
        "release_date": w.release_date,
        "director": w.director,
        "studio": w.studio,
        "label": w.label,
        "series": w.series,
        "detail_crawled": w.detail_crawled,
        "magnets_crawled": w.magnets_crawled,
        "tags": [t.name for t in tags],
        "cast": [{"id": a.id, "name": a.name, "javbus_id": a.javbus_id,
                  "avatar": (JAVBUS_BASE + a.avatar) if a.avatar and not a.avatar.startswith("http") else (a.avatar or "")}
                 for a in cast],
        "picked_magnet": {
            "name": picked.name,
            "magnet_url": picked.magnet_url,
            "size_str": picked.size_str,
            "size_mb": picked.size_mb,
            "pick_reason": picked.pick_reason,
        } if picked else None,
    }


def _preload_work_relations(db: Session, work_ids: List[int]) -> dict:
    """
    批量预加载多个作品的关联数据，解决 N+1 查询问题。
    返回结构：{work_id: data}
    """
    preload = {
        "picked": {},   # work_id -> MagnetPick or None
        "tags": {},     # work_id -> [Tag, ...]
        "cast": {},     # work_id -> [Actress, ...]
    }
    if not work_ids:
        return preload

    # 批量加载 MagnetPick
    picks = db.query(MagnetPick).filter(MagnetPick.work_id.in_(work_ids)).all()
    for p in picks:
        preload["picked"][p.work_id] = p

    # 批量加载 Tags（通过 WorkTag 关联）
    tag_rows = (
        db.query(Tag, WorkTag.work_id)
        .join(WorkTag, Tag.id == WorkTag.tag_id)
        .filter(WorkTag.work_id.in_(work_ids))
        .all()
    )
    for tag, work_id in tag_rows:
        preload["tags"].setdefault(work_id, []).append(tag)

    # 批量加载演员（通过 WorkCast 关联）
    cast_rows = (
        db.query(Actress, WorkCast.work_id)
        .join(WorkCast, Actress.id == WorkCast.actress_id)
        .filter(WorkCast.work_id.in_(work_ids))
        .all()
    )
    for actress, work_id in cast_rows:
        preload["cast"].setdefault(work_id, []).append(actress)

    return preload
