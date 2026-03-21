"""
爬虫核心服务 - 兵部执行 + 户部存储

整合 HTTP 客户端和解析器，实现完整的爬取流程：
1. 爬取全站女优列表（分页）
2. 爬取女优个人信息
3. 爬取女优作品列表
4. 爬取作品详情（导演/制作商/标签/演员等）
5. 爬取磁力链接并筛选最优
"""
import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Callable, Awaitable
from sqlalchemy.orm import Session
import httpx

from config import JAVBUS_BASE, JAVBUS_ACTRESSES_URL, BASE_DIR
from core.http_client import get_client
from core.parsers.actress_list_parser import parse_actresses_page, parse_total_pages
from core.parsers.actress_detail_parser import (
    parse_actress_profile, parse_actress_works, parse_actress_works_pages
)
from core.parsers.work_detail_parser import parse_work_detail, build_magnet_ajax_url
from core.parsers.magnet_parser import parse_magnets, pick_best_magnet
from db.session import SessionLocal
from db.models import Actress, Work, Tag, WorkTag, WorkCast, Magnet, MagnetPick, CrawlTask

logger = logging.getLogger("bingbu.crawler_service")

# 封面下载目录
COVERS_DIR = BASE_DIR / "static" / "covers"
COVERS_DIR.mkdir(parents=True, exist_ok=True)

# 线程池（用于在 asyncio 中运行同步 HTTP 请求）
_executor = ThreadPoolExecutor(max_workers=2)


async def _run_in_thread(func, *args):
    """在线程池中运行同步函数"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, func, *args)


def _download_cover_sync(cover_url: str) -> Optional[str]:
    """同步下载封面图片到本地，返回本地文件路径"""
    if not cover_url or cover_url.startswith("/static"):
        return None

    try:
        # 转换 URL 为本地文件名
        # 例如: /pics/cover/abc_b.jpg -> abc_b.jpg
        filename = cover_url.replace('/pics/cover/', '').replace('/', '_')
        local_path = COVERS_DIR / filename

        # 如果已存在则跳过
        if local_path.exists():
            return str(local_path)

        # 构建完整 URL
        full_url = cover_url if cover_url.startswith("http") else JAVBUS_BASE + cover_url

        # 下载图片
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": JAVBUS_BASE + "/",
        }
        resp = httpx.get(full_url, headers=headers, timeout=30, follow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(local_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"封面下载成功: {filename}")
            return str(local_path)
        else:
            logger.warning(f"封面下载失败: {full_url}, HTTP {resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"封面下载异常: {cover_url}, {e}")
        return None


async def download_work_cover(cover_url: str) -> Optional[str]:
    """下载作品封面到本地，返回本地路径（URL 格式）"""
    if not cover_url:
        return None

    # 如果已经是本地路径则跳过
    if cover_url.startswith("/static"):
        return cover_url

    # 转换路径为 URL 格式
    filename = cover_url.replace('/pics/cover/', '').replace('/', '_')
    local_path = COVERS_DIR / filename

    if local_path.exists():
        return f"/static/covers/{filename}"

    # 在线程中下载
    result = await _run_in_thread(_download_cover_sync, cover_url)
    if result:
        return f"/static/covers/{filename}"
    return None


# ─────────────────────────────────────────────
# 女优列表爬取（中书省 + 兵部协作）
# ─────────────────────────────────────────────

async def crawl_actresses_list(
    progress_callback: Optional[Callable] = None,
    max_pages: int = 2000
) -> List[Dict]:
    """
    爬取全站所有女优列表（自动检测最大页数）

    Args:
        progress_callback: 进度回调 async def(msg: str, current: int, total: int)
        max_pages: 最大爬取页数（默认2000，约10万女优）

    Returns:
        女优信息字典列表
    """
    client = get_client()
    all_actresses = []

    async def notify(msg, cur=0, total=0):
        if progress_callback:
            await progress_callback(msg, cur, total)

    await notify("开始爬取第1页女优列表...")

    # 第一页
    resp = await _run_in_thread(client.get, JAVBUS_ACTRESSES_URL)
    if not resp:
        await notify("❌ 无法访问 javbus.com/actresses，请检查网络")
        return []

    first_page_actresses = parse_actresses_page(resp.text)
    if not first_page_actresses:
        await notify("❌ 第1页无数据，可能是反爬或网络问题")
        return []

    all_actresses.extend(first_page_actresses)
    await notify(f"第1页完成，获得 {len(first_page_actresses)} 位女优", 1, max_pages)

    # 后续分页 - 一直爬到没有新数据
    page = 2
    consecutive_empty = 0  # 连续空页计数
    while page <= max_pages:
        url = f"{JAVBUS_ACTRESSES_URL}/{page}"
        resp = await _run_in_thread(client.get, url)
        if not resp:
            await notify(f"⚠️ 第{page}页请求失败，跳过", page, max_pages)
            page += 1
            continue

        page_actresses = parse_actresses_page(resp.text)
        if not page_actresses:
            consecutive_empty += 1
            # 连续3页空数据，认为已爬完
            if consecutive_empty >= 3:
                await notify(f"✅ 爬取完成！共 {len(all_actresses)} 位女优", page - 1, max_pages)
                break
            page += 1
            continue

        consecutive_empty = 0
        all_actresses.extend(page_actresses)
        await notify(
            f"第{page}页完成，本页 {len(page_actresses)} 位，累计 {len(all_actresses)} 位",
            page, max_pages
        )
        page += 1

    # 去重
    seen = set()
    unique = []
    for a in all_actresses:
        if a["javbus_id"] not in seen:
            seen.add(a["javbus_id"])
            unique.append(a)

    await notify(f"✅ 全站女优爬取完成，共 {len(unique)} 位（去重后）", max_pages, max_pages)
    return unique


def save_actresses_to_db(actresses: List[Dict], db: Session) -> List[Actress]:
    """将爬取的女优列表保存到数据库（upsert）"""
    saved = []
    for a_data in actresses:
        existing = db.query(Actress).filter(
            Actress.javbus_id == a_data["javbus_id"]
        ).first()

        if existing:
            # 更新基本信息
            existing.name = a_data["name"]
            existing.profile_url = a_data["profile_url"]
            if a_data.get("avatar"):
                existing.avatar = a_data["avatar"]
            existing.updated_at = datetime.utcnow()
            saved.append(existing)
        else:
            new_actress = Actress(
                name=a_data["name"],
                javbus_id=a_data["javbus_id"],
                profile_url=a_data["profile_url"],
                avatar=a_data.get("avatar", ""),
            )
            db.add(new_actress)
            saved.append(new_actress)

    db.commit()
    logger.info(f"保存女优 {len(saved)} 条到数据库")
    return saved


# ─────────────────────────────────────────────
# 单个女优完整爬取（尚书省调度的最小单元）
# ─────────────────────────────────────────────

async def crawl_actress_full(
    actress_id: int,
    task_id: int,
    progress_callback: Optional[Callable] = None,
) -> bool:
    """
    爬取一个女优的完整数据：个人信息 + 所有作品 + 每部作品的磁力

    这是尚书省调度的最小执行单元

    Args:
        actress_id: 数据库中的女优 ID
        task_id: 爬取任务 ID（用于更新进度）
        progress_callback: async def(msg, done_works, total_works)

    Returns:
        True 表示成功，False 表示失败
    """
    db: Session = SessionLocal()
    client = get_client()

    async def notify(msg: str, done: int = 0, total: int = 0):
        logger.info(f"[Task {task_id}] {msg}")
        if progress_callback:
            await progress_callback(msg, done, total)
        # 更新任务日志
        task = db.query(CrawlTask).get(task_id)
        if task:
            existing_log = task.log or ""
            task.log = existing_log + f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] {msg}"
            task.done_works = done
            task.total_works = max(task.total_works, total)
            db.commit()

    try:
        actress = db.query(Actress).get(actress_id)
        if not actress:
            await notify(f"❌ 女优 ID {actress_id} 不存在")
            return False

        await notify(f"开始爬取: {actress.name}")

        # ── 阶段1：爬取个人信息 ──
        if not actress.profile_crawled and actress.profile_url:
            await notify("📋 正在获取个人信息...")
            resp = await _run_in_thread(client.get, actress.profile_url)
            if resp:
                profile = parse_actress_profile(resp.text, actress.javbus_id)
                actress.birthday = profile.get("birthday", "")
                actress.age = profile.get("age", "")
                actress.height = profile.get("height", "")
                actress.cup = profile.get("cup", "")
                actress.bust = profile.get("bust", "")
                actress.waist = profile.get("waist", "")
                actress.hip = profile.get("hip", "")
                actress.hobby = profile.get("hobby", "")
                if profile.get("avatar"):
                    actress.avatar = profile["avatar"]
                actress.profile_crawled = True
                db.commit()
                await notify(f"✅ 个人信息爬取完成: {actress.name}")
            else:
                await notify(f"⚠️ 个人信息获取失败，继续爬作品")

        # ── 阶段2：爬取作品列表（分页）──
        await notify("🎬 开始爬取作品列表...")

        work_codes: List[Dict] = []  # 所有作品的基本信息

        # 第一页
        resp = await _run_in_thread(client.get, actress.profile_url)
        if not resp:
            await notify("❌ 无法获取作品列表页")
            return False

        first_works = parse_actress_works(resp.text)
        total_work_pages = parse_actress_works_pages(resp.text, actress.profile_url)
        work_codes.extend(first_works)

        await notify(f"作品第1/{total_work_pages}页，获得 {len(first_works)} 个作品", 0, len(first_works))

        for page in range(2, total_work_pages + 1):
            url = f"{actress.profile_url}/{page}"
            resp = await _run_in_thread(client.get, url)
            if not resp:
                await notify(f"⚠️ 作品第{page}页失败，跳过")
                continue
            page_works = parse_actress_works(resp.text)
            work_codes.extend(page_works)
            await notify(f"作品第{page}/{total_work_pages}页，累计 {len(work_codes)} 个", 0, len(work_codes))

        # 更新任务总数
        task = db.query(CrawlTask).get(task_id)
        if task:
            task.total_works = len(work_codes)
            db.commit()

        await notify(f"📦 共 {len(work_codes)} 个作品，开始爬取详情和磁力...")

        # ── 阶段3：逐个爬取作品详情 + 磁力 ──
        done_works = 0
        done_magnets = 0

        for work_info in work_codes:
            try:
                code = work_info["code"]
                work_url = work_info["work_url"]

                # 检查是否已爬取
                existing_work = db.query(Work).filter(Work.code == code).first()
                if existing_work and existing_work.magnets_crawled:
                    done_works += 1
                    continue

                # 爬取作品详情
                resp = await _run_in_thread(client.get, work_url)
                if not resp:
                    await notify(f"⚠️ {code} 详情获取失败，跳过")
                    done_works += 1
                    continue

                detail = parse_work_detail(resp.text)
                if not detail:
                    await notify(f"⚠️ {code} 解析失败，跳过")
                    done_works += 1
                    continue

                # 保存或更新作品
                work = existing_work or db.query(Work).filter(Work.code == code).first()
                if not work:
                    work = Work(code=code)
                    db.add(work)

                # 下载封面到本地
                raw_cover = detail.get("cover") or work_info.get("cover", "")
                local_cover = await download_work_cover(raw_cover)

                work.title = detail.get("title", work_info.get("title", ""))
                work.work_url = work_url
                work.cover = local_cover or raw_cover  # 优先使用本地路径
                work.release_date = detail.get("release_date") or work_info.get("release_date", "")
                work.director = detail.get("director", "")
                work.studio = detail.get("studio", "")
                work.label = detail.get("label", "")
                work.series = detail.get("series", "")
                work.detail_crawled = True
                db.flush()

                # 保存标签
                for tag_data in detail.get("tags", []):
                    tag = db.query(Tag).filter(Tag.name == tag_data["name"]).first()
                    if not tag:
                        tag = Tag(name=tag_data["name"], javbus_genre_id=tag_data.get("genre_id", ""))
                        db.add(tag)
                        db.flush()
                    # 建立关联
                    exists = db.query(WorkTag).filter(
                        WorkTag.work_id == work.id,
                        WorkTag.tag_id == tag.id
                    ).first()
                    if not exists:
                        db.add(WorkTag(work_id=work.id, tag_id=tag.id))

                # 保存演员关联（WorkCast）
                for cast_data in detail.get("cast", []):
                    cast_actress = db.query(Actress).filter(
                        Actress.javbus_id == cast_data["javbus_id"]
                    ).first()
                    if not cast_actress:
                        cast_actress = Actress(
                            name=cast_data["name"],
                            javbus_id=cast_data["javbus_id"],
                            avatar=cast_data.get("avatar", ""),
                        )
                        db.add(cast_actress)
                        db.flush()

                    exists = db.query(WorkCast).filter(
                        WorkCast.work_id == work.id,
                        WorkCast.actress_id == cast_actress.id
                    ).first()
                    if not exists:
                        db.add(WorkCast(work_id=work.id, actress_id=cast_actress.id))

                db.commit()

                # 爬取磁力链接
                magnet_params = detail.get("magnet_params", {})
                magnet_ajax_url = build_magnet_ajax_url(magnet_params)

                if magnet_ajax_url:
                    magnet_resp = await _run_in_thread(
                        lambda u: get_client().get(
                            u,
                            extra_headers={"Referer": work_url},
                            is_ajax=True
                        ),
                        magnet_ajax_url
                    )

                    if magnet_resp:
                        magnets = parse_magnets(magnet_resp.text)

                        # 保存所有磁力候选
                        for mag_data in magnets:
                            existing_mag = db.query(Magnet).filter(
                                Magnet.work_id == work.id,
                                Magnet.magnet_url == mag_data["magnet_url"]
                            ).first()
                            if not existing_mag:
                                mag = Magnet(
                                    work_id=work.id,
                                    name=mag_data["name"],
                                    magnet_url=mag_data["magnet_url"],
                                    size_str=mag_data["size_str"],
                                    size_mb=mag_data["size_mb"],
                                    share_date=mag_data["share_date"],
                                    is_uc=mag_data["is_uc"],
                                    is_u=mag_data["is_u"],
                                    is_4k=mag_data["is_4k"],
                                    is_uncensored=mag_data["is_uncensored"],
                                    is_c=mag_data["is_c"],
                                    priority_level=mag_data["priority_level"],
                                )
                                db.add(mag)

                        db.commit()

                        # 筛选最优磁力并保存
                        best = pick_best_magnet(magnets)
                        if best:
                            existing_pick = db.query(MagnetPick).filter(
                                MagnetPick.work_id == work.id
                            ).first()
                            if not existing_pick:
                                existing_pick = MagnetPick(work_id=work.id)
                                db.add(existing_pick)
                            existing_pick.name = best["name"]
                            existing_pick.magnet_url = best["magnet_url"]
                            existing_pick.size_str = best["size_str"]
                            existing_pick.size_mb = best["size_mb"]
                            existing_pick.share_date = best["share_date"]
                            existing_pick.priority_level = best["priority_level"]
                            existing_pick.pick_reason = best.get("pick_reason", "")
                            db.commit()

                        done_magnets += len(magnets)
                        work.magnets_crawled = True
                        db.commit()

                done_works += 1
                await notify(
                    f"✅ {code} 完成（{done_works}/{len(work_codes)}），磁力 {len(detail.get('tags', []))} 标签",
                    done_works,
                    len(work_codes)
                )

                # 更新任务进度
                task = db.query(CrawlTask).get(task_id)
                if task:
                    task.done_works = done_works
                    task.done_magnets = done_magnets
                    db.commit()

            except Exception as e:
                logger.error(f"处理作品 {work_info.get('code', '?')} 出错: {e}", exc_info=True)
                done_works += 1
                continue

        # 标记完成
        actress.works_crawled = True
        db.commit()

        # 更新任务状态
        task = db.query(CrawlTask).get(task_id)
        if task:
            task.status = "completed"
            task.done_works = done_works
            task.finished_at = datetime.utcnow()
            db.commit()

        await notify(f"🎉 {actress.name} 爬取完成！{done_works} 个作品", done_works, done_works)
        return True

    except Exception as e:
        logger.error(f"女优 {actress_id} 爬取失败: {e}", exc_info=True)
        task = db.query(CrawlTask).get(task_id)
        if task:
            task.status = "failed"
            task.error_msg = str(e)
            task.finished_at = datetime.utcnow()
            db.commit()
        return False

    finally:
        db.close()
