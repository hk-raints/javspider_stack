"""
爬虫核心服务 - 异步版本 (增强头像下载)
"""
import asyncio
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from config import settings, USER_AGENTS
from app.core.http_client import http_client
from core.parsers.actress_list_parser import parse_actresses_page
from core.parsers.actress_detail_parser import (
    parse_actress_profile, parse_actress_works, parse_actress_works_pages
)
from core.parsers.work_detail_parser import parse_work_detail, build_magnet_ajax_url
from core.parsers.magnet_parser import parse_magnets, pick_best_magnet
from db.models import Actress, Work, Tag, WorkTag, WorkCast, Magnet, MagnetPick, CrawlTask

logger = logging.getLogger("app.services.crawler")

# 目录配置
COVERS_DIR = settings.BASE_DIR / "static" / "covers"
AVATARS_DIR = settings.BASE_DIR / "static" / "avatars"
COVERS_DIR.mkdir(parents=True, exist_ok=True)
AVATARS_DIR.mkdir(parents=True, exist_ok=True)

async def download_image(url: str, save_dir: Path, referer: str = settings.JAVBUS_BASE) -> Optional[str]:
    """通用图片下载"""
    if not url or url.startswith("/static") or url.startswith("http://localhost"):
        return url

    # 处理相对路径
    full_url = url if url.startswith("http") else f"{settings.JAVBUS_BASE}{url}"
    
    # 提取文件名
    filename = url.split("/")[-1]
    if "?" in filename: filename = filename.split("?")[0]
    
    # 为了避免重名，可以加入路径特征
    if "/pics/actress/" in url:
        filename = f"avatar_{filename}"
    elif "/pics/cover/" in url:
        filename = f"cover_{filename}"
        
    local_path = save_dir / filename
    
    # 映射路径 (相对于 static 的外部路径)
    sub_dir = save_dir.name # "covers" or "avatars"
    web_path = f"/static/{sub_dir}/{filename}"

    if local_path.exists():
        return web_path

    try:
        resp = await http_client.get(full_url, extra_headers={"Referer": referer})
        if resp and resp.status_code == 200:
            with open(local_path, "wb") as f:
                f.write(resp.content)
            return web_path
    except Exception as e:
        logger.warning(f"图片下载失败: {full_url}, {e}")
    return None

async def download_work_cover(cover_url: str) -> Optional[str]:
    return await download_image(cover_url, COVERS_DIR)

async def download_actress_avatar(avatar_url: str) -> Optional[str]:
    return await download_image(avatar_url, AVATARS_DIR)

async def crawl_actresses_list(
    progress_callback: Optional[Callable] = None,
    max_pages: int = 2000
) -> List[Dict]:
    all_actresses = []
    
    async def notify(msg, cur=0, total=0):
        if progress_callback:
            await progress_callback(msg, cur, total)

    page = 1
    consecutive_empty = 0
    while page <= max_pages:
        url = f"{settings.JAVBUS_ACTRESSES_URL}/{page}" if page > 1 else settings.JAVBUS_ACTRESSES_URL
        resp = await http_client.get(url)
        if not resp:
            await notify(f"⚠️ 第{page}页请求失败", page, max_pages)
            page += 1
            continue

        page_actresses = parse_actresses_page(resp.text)
        if not page_actresses:
            consecutive_empty += 1
            if consecutive_empty >= 3: break
            page += 1
            continue

        consecutive_empty = 0
        all_actresses.extend(page_actresses)
        await notify(f"第{page}页完成，共 {len(all_actresses)} 人", page, max_pages)
        page += 1
    
    unique = []
    seen = set()
    for a in all_actresses:
        if a["javbus_id"] not in seen:
            seen.add(a["javbus_id"])
            unique.append(a)
    return unique

async def save_actresses_to_db(actresses: List[Dict], db: AsyncSession):
    for a_data in actresses:
        stmt = select(Actress).where(Actress.javbus_id == a_data["javbus_id"])
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.name = a_data["name"]
            existing.profile_url = a_data["profile_url"]
            # 暂时不在这里下载头像，由单独任务执行或展示时懒加载
            if a_data.get("avatar") and not existing.avatar:
                existing.avatar = a_data["avatar"]
            existing.updated_at = datetime.utcnow()
        else:
            new_actress = Actress(
                name=a_data["name"],
                javbus_id=a_data["javbus_id"],
                profile_url=a_data["profile_url"],
                avatar=a_data.get("avatar", ""),
            )
            db.add(new_actress)
    await db.commit()

async def crawl_actress_full(
    actress_id: int,
    task_id: int,
    db_factory: Callable[[], AsyncSession],
    progress_callback: Optional[Callable] = None,
) -> bool:
    async with db_factory() as db:
        async def notify(msg: str, done: int = 0, total: int = 0):
            logger.info(f"[Task {task_id}] {msg}")
            if progress_callback:
                await progress_callback(msg, done, total)
            
            stmt = select(CrawlTask).where(CrawlTask.id == task_id)
            task = (await db.execute(stmt)).scalar_one_or_none()
            if task:
                task.log = (task.log or "") + f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}"
                task.done_works = done
                task.total_works = max(task.total_works, total)
                await db.commit()

        try:
            stmt = select(Actress).where(Actress.id == actress_id)
            actress = (await db.execute(stmt)).scalar_one_or_none()
            if not actress: return False

            await notify(f"开始爬取: {actress.name}")

            # 阶段1: 个人信息 & 头像
            if actress.profile_url:
                resp = await http_client.get(actress.profile_url)
                if resp:
                    profile = parse_actress_profile(resp.text, actress.javbus_id)
                    for key, val in profile.items():
                        if hasattr(actress, key): setattr(actress, key, val)
                    
                    # 下载头像
                    if profile.get("avatar"):
                        local_avatar = await download_actress_avatar(profile["avatar"])
                        if local_avatar: actress.avatar = local_avatar
                    
                    actress.profile_crawled = True
                    await db.commit()

            # 阶段2: 作品列表
            resp = await http_client.get(actress.profile_url)
            if not resp: return False
            
            work_codes = parse_actress_works(resp.text)
            total_pages = parse_actress_works_pages(resp.text, actress.profile_url)
            
            for page in range(2, total_pages + 1):
                url = f"{actress.profile_url}/{page}"
                p_resp = await http_client.get(url)
                if p_resp: work_codes.extend(parse_actress_works(p_resp.text))
            
            # 阶段3: 详情与磁力
            done_works = 0
            for work_info in work_codes:
                code = work_info["code"]
                stmt = select(Work).where(Work.code == code)
                work = (await db.execute(stmt)).scalar_one_or_none()
                
                if work and work.magnets_crawled:
                    # 确保作品与演员建立关联 (如果之前漏了)
                    stmt_c = select(WorkCast).where(and_(WorkCast.work_id == work.id, WorkCast.actress_id == actress.id))
                    if not (await db.execute(stmt_c)).scalar_one_or_none():
                        db.add(WorkCast(work_id=work.id, actress_id=actress.id))
                    done_works += 1
                    continue
                
                resp = await http_client.get(work_info["work_url"])
                if not resp: continue
                
                detail = parse_work_detail(resp.text)
                if not detail: continue
                
                if not work:
                    work = Work(code=code)
                    db.add(work)
                
                # 下载封面
                local_cover = await download_work_cover(detail.get("cover", work_info.get("cover", "")))
                work.title = detail.get("title", work_info.get("title", ""))
                work.cover = local_cover
                work.release_date = detail.get("release_date", "")
                work.detail_crawled = True
                await db.flush()
                
                # 建立关联
                stmt_c = select(WorkCast).where(and_(WorkCast.work_id == work.id, WorkCast.actress_id == actress.id))
                if not (await db.execute(stmt_c)).scalar_one_or_none():
                    db.add(WorkCast(work_id=work.id, actress_id=actress.id))

                # 磁力
                params = detail.get("magnet_params", {})
                ajax_url = build_magnet_ajax_url(params)
                if ajax_url:
                    m_resp = await http_client.get(ajax_url, extra_headers={"Referer": work_info["work_url"]}, is_ajax=True)
                    if m_resp:
                        magnets = parse_magnets(m_resp.text)
                        for m_data in magnets:
                            mag = Magnet(work_id=work.id, **m_data)
                            await db.merge(mag)
                        await db.flush()
                        
                        best = pick_best_magnet(magnets)
                        if best:
                            pick = MagnetPick(work_id=work.id, **best)
                            await db.merge(pick)
                
                work.magnets_crawled = True
                done_works += 1
                await notify(f"✅ {code} 完成", done_works, len(work_codes))
                await db.commit()

            actress.works_crawled = True
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"爬取任务失败: {e}", exc_info=True)
            return False

# 增加一个导入
from sqlalchemy import and_
