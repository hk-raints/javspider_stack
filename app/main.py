"""
JavSpider Stack - 优化版 FastAPI 主入口 (Async)
全面兼容旧版前端 API 结构，修复过滤逻辑与图片路径
"""
import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, Query, HTTPException, status, Security
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_, delete, text, or_
from sqlalchemy.orm import selectinload

from config import settings
from db.session import get_db, AsyncSessionLocal
from db.models import Actress, Work, Tag, Magnet, MagnetPick, CrawlTask, WorkCast, WorkTag
from app.services.task_queue import shangshu_queue
from app.services.crawler import crawl_actresses_list, save_actresses_to_db
from app.core.security import get_api_key

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from app.core.http_client import http_client
    await http_client.close()

app = FastAPI(title="JavSpider Stack", version="2.1.1", lifespan=lifespan)

# 鉴权
auth_dep = [Depends(get_api_key)] if settings.API_KEY else []

# 静态文件
BASE_DIR = settings.BASE_DIR
for name, path in [
    ("dashboard", BASE_DIR / "dashboard"),
    ("static", BASE_DIR / "static"),
]:
    if path.exists():
        app.mount(f"/{name}" if name != "static" else "/static", StaticFiles(directory=str(path)), name=name)

# ─────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────
@app.websocket("/ws/progress")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    async def broadcast_callback(data: dict):
        try:
            await websocket.send_json(data)
        except Exception:
            pass
    
    shangshu_queue.register_ws_callback(broadcast_callback)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        shangshu_queue.unregister_ws_callback(broadcast_callback)

# ─────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = BASE_DIR / "dashboard" / "index.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return "<h1>JavSpider Stack Dashboard</h1>"

@app.get("/api/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total_actresses = (await db.execute(select(func.count(Actress.id)))).scalar()
    profile_crawled = (await db.execute(select(func.count(Actress.id)).where(Actress.profile_crawled == True))).scalar()
    total_works = (await db.execute(select(func.count(Work.id)))).scalar()
    works_with_magnets = (await db.execute(select(func.count(Work.id)).where(Work.magnets_crawled == True))).scalar()
    total_magnets = (await db.execute(select(func.count(Magnet.id)))).scalar()
    total_tags = (await db.execute(select(func.count(Tag.id)))).scalar()
    
    q_status = shangshu_queue.get_all_progress()
    
    return {
        "total_actresses": total_actresses,
        "profile_crawled": profile_crawled,
        "total_works": total_works,
        "works_with_magnets": works_with_magnets,
        "total_magnets": total_magnets,
        "total_tags": total_tags,
        "queue_size": len(q_status["queue"]),
        "queue_running": q_status["running"]
    }

def fix_avatar_path(path: Optional[str]) -> Optional[str]:
    """修复头像路径，确保能被正确加载"""
    if not path: return path
    if path.startswith("/static") or path.startswith("http"):
        return path
    if path.startswith("/pics/"):
        # 暂时返回全路径
        return f"{settings.JAVBUS_BASE}{path}"
    return path

@app.get("/api/actresses")
async def list_actresses(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    sort_by: str = Query("popularity"),
    sort_order: str = Query("desc"),
    profile_crawled: Optional[str] = Query(None),
    cup: Optional[str] = Query(None),
    min_age: Optional[int] = Query(None),
    max_age: Optional[int] = Query(None),
    min_height: Optional[int] = Query(None),
    max_height: Optional[int] = Query(None),
    min_works: Optional[int] = Query(None),
    max_works: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Actress)
    
    # 基础过滤
    if search:
        stmt = stmt.where(Actress.name.ilike(f"%{search}%"))
    if profile_crawled == "1":
        stmt = stmt.where(Actress.profile_crawled == True)
    elif profile_crawled == "0":
        stmt = stmt.where(Actress.profile_crawled == False)
    if cup:
        stmt = stmt.where(Actress.cup == cup)
    
    # 年龄过滤
    if min_age is not None:
        stmt = stmt.where(Actress.age >= str(min_age))
    if max_age is not None:
        stmt = stmt.where(Actress.age <= str(max_age))
    
    # 身高过滤
    if min_height is not None:
        stmt = stmt.where(Actress.height >= str(min_height))
    if max_height is not None:
        stmt = stmt.where(Actress.height <= str(max_height))
        
    # 作品数量过滤
    if min_works is not None or max_works is not None:
        subq = (
            select(WorkCast.actress_id, func.count(WorkCast.work_id).label("cnt"))
            .group_by(WorkCast.actress_id)
            .subquery()
        )
        stmt = stmt.join(subq, Actress.id == subq.c.actress_id, isouter=True)
        if min_works is not None:
            stmt = stmt.where(func.coalesce(subq.c.cnt, 0) >= min_works)
        if max_works is not None:
            stmt = stmt.where(func.coalesce(subq.c.cnt, 0) <= max_works)

    # 排序
    order_func = desc if sort_order == "desc" else lambda x: x
    if sort_by == "popularity":
        stmt = stmt.order_by(order_func(Actress.popularity_score))
    elif sort_by == "name":
        stmt = stmt.order_by(order_func(Actress.name))
    elif sort_by == "created_at":
        stmt = stmt.order_by(order_func(Actress.created_at))
    else:
        stmt = stmt.order_by(desc(Actress.popularity_score))
    
    # 注意：统计总数要在分页前完成
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar()
    
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    actresses = result.scalars().all()
    
    return {
        "total": total,
        "page": page,
        "total_pages": (total + per_page - 1) // per_page if total else 0,
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "avatar": fix_avatar_path(a.avatar),
                "age": a.age,
                "height": a.height,
                "cup": a.cup,
                "popularity_score": a.popularity_score,
                "profile_crawled": a.profile_crawled,
                "works_crawled": a.works_crawled,
            } for a in actresses
        ]
    }

@app.get("/api/actress/{actress_id}")
async def get_actress_detail(actress_id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Actress).where(Actress.id == actress_id)
    actress = (await db.execute(stmt)).scalar_one_or_none()
    if not actress:
        raise HTTPException(status_code=404, detail="Actress not found")
    
    data = {c.name: getattr(actress, c.name) for c in actress.__table__.columns}
    data["avatar"] = fix_avatar_path(actress.avatar)
    return data

@app.get("/api/actress/{actress_id}/works")
async def get_actress_works(
    actress_id: int, 
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    stmt = (
        select(Work)
        .join(WorkCast)
        .where(WorkCast.actress_id == actress_id)
        .order_by(desc(Work.release_date))
        .options(selectinload(Work.picked_magnet))
    )
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar()
    
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    works = (await db.execute(stmt)).scalars().all()
    
    return {
        "total": total,
        "page": page,
        "total_pages": (total + per_page - 1) // per_page if total else 0,
        "items": [
            {
                "id": w.id,
                "code": w.code,
                "title": w.title,
                "cover": w.cover,
                "release_date": w.release_date,
                "picked_magnet": {
                    "size_str": w.picked_magnet.size_str,
                    "priority_level": w.picked_magnet.priority_level
                } if w.picked_magnet else None
            } for w in works
        ]
    }

@app.get("/api/works")
async def list_works(
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=200),
    search: Optional[str] = Query(None),
    actress_name: Optional[str] = Query(None),
    studio: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    has_magnet: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Work).options(
        selectinload(Work.picked_magnet),
        selectinload(Work.actresses),
        selectinload(Work.tags)
    )
    
    if search:
        stmt = stmt.where(or_(Work.code.ilike(f"%{search}%"), Work.title.ilike(f"%{search}%")))
    if actress_name:
        stmt = stmt.join(WorkCast).join(Actress).where(Actress.name.ilike(f"%{actress_name}%"))
    if studio:
        stmt = stmt.where(Work.studio.ilike(f"%{studio}%"))
    if tag:
        stmt = stmt.join(WorkTag).join(Tag).where(Tag.name == tag)
    if has_magnet == "yes":
        stmt = stmt.where(Work.magnets_crawled == True)
    
    stmt = stmt.order_by(desc(Work.release_date))
    
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar()
    
    stmt = stmt.offset((page - 1) * per_page).limit(per_page)
    works = (await db.execute(stmt)).scalars().all()
    
    return {
        "total": total,
        "page": page,
        "total_pages": (total + per_page - 1) // per_page if total else 0,
        "items": [
            {
                "id": w.id,
                "code": w.code,
                "title": w.title,
                "cover": w.cover,
                "release_date": w.release_date,
                "picked_magnet": {
                    "size_str": w.picked_magnet.size_str,
                    "magnet_url": w.picked_magnet.magnet_url,
                    "priority_level": w.picked_magnet.priority_level
                } if w.picked_magnet else None,
                "cast": [{"id": a.id, "name": a.name} for a in w.actresses],
                "tags": [t.name for t in w.tags]
            } for w in works
        ]
    }

@app.get("/api/work/{work_id}")
async def get_work_detail(work_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Work)
        .where(Work.id == work_id)
        .options(
            selectinload(Work.magnets),
            selectinload(Work.picked_magnet),
            selectinload(Work.actresses),
            selectinload(Work.tags)
        )
    )
    work = (await db.execute(stmt)).scalar_one_or_none()
    if not work:
        raise HTTPException(status_code=404, detail="Work not found")
    
    return {
        "id": work.id,
        "code": work.code,
        "title": work.title,
        "cover": work.cover,
        "work_url": work.work_url,
        "release_date": work.release_date,
        "director": work.director,
        "studio": work.studio,
        "label": work.label,
        "series": work.series,
        "total_magnets": len(work.magnets),
        "picked_magnet": work.picked_magnet,
        "magnets": sorted(work.magnets, key=lambda x: x.priority_level),
        "cast": [{"id": a.id, "name": a.name} for a in work.actresses],
        "tags": [{"id": t.id, "name": t.name} for t in work.tags]
    }

@app.post("/api/batch/add", dependencies=auth_dep)
async def batch_add(actress_ids: List[int], db: AsyncSession = Depends(get_db)):
    added = []
    for aid in actress_ids:
        stmt = select(Actress).where(Actress.id == aid)
        actress = (await db.execute(stmt)).scalar_one_or_none()
        if actress:
            task_id = await shangshu_queue.add_to_queue(aid, actress.name)
            if task_id: added.append(aid)
    return {"status": "success", "added": added}

@app.post("/api/batch/start", dependencies=auth_dep)
async def batch_start():
    await shangshu_queue.start()
    return {"status": "started"}

@app.get("/api/batch/progress")
async def batch_progress():
    return shangshu_queue.get_all_progress()

@app.post("/api/batch/remove/{actress_id}", dependencies=auth_dep)
async def batch_remove(actress_id: int):
    success = await shangshu_queue.remove_from_queue(actress_id)
    return {"status": "success" if success else "error"}

@app.post("/api/batch/clear", dependencies=auth_dep)
async def batch_clear():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CrawlTask).where(CrawlTask.status == "pending"))
        await db.commit()
    shangshu_queue._queue.clear()
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.SERVER_HOST, port=settings.SERVER_PORT)
