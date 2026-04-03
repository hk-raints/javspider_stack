"""
JAVDB 演员页面解析器

解析 https://javdb.com/actors 及演员详情页
提取：演员名、热度指标、作品数等

注意：JAVDB 有 Cloudflare 保护，需通过浏览器自动化工具（如 agent-browser）
获取页面内容后再用本解析器解析。
"""
import logging
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup

logger = logging.getLogger("javdb_parser")


def parse_actors_page(html: str) -> List[Dict]:
    """
    解析演员列表页（如 https://javdb.com/actors）

    Returns:
        List of {
            'name': str,        # 演员姓名
            'javdb_code': str,  # JAVDB 演员代码/URL slug
            'profile_url': str, # 完整详情页URL
            'cover': str,       # 封面图URL
            'works_count': int, # 作品数（如果有）
        }
    """
    soup = BeautifulSoup(html, "lxml")
    actors = []

    # JAVDB 演员列表结构：
    # <a class="box" href="/actors/MLfZ">
    #   <div class="cover">
    #     <img src="...">
    #   </div>
    #   <div class="meta">
    #     <span>演员名</span>
    #     <span>作品数</span>
    #   </div>
    # </a>

    for a_tag in soup.find_all("a", class_="box"):
        href = a_tag.get("href", "")
        if not href or "/actors/" not in href:
            continue

        # 提取 slug
        slug_match = re.search(r"/actors/([A-Za-z0-9_-]+)", href)
        if not slug_match:
            continue
        javdb_code = slug_match.group(1)

        # 提取姓名
        name = ""
        meta = a_tag.find("div", class_="meta")
        if meta:
            spans = meta.find_all("span")
            if spans:
                name = spans[0].get_text(strip=True)

        if not name:
            # 备选：从 title 或 strong
            title_tag = a_tag.find("strong")
            if title_tag:
                name = title_tag.get_text(strip=True)

        # 提取封面图
        cover = ""
        img = a_tag.find("img")
        if img:
            cover = img.get("src", "") or img.get("data-src", "")

        # 提取作品数
        works_count = 0
        if meta:
            text = meta.get_text(strip=True)
            # 格式如 "河北彩花 206"
            m = re.search(r"(\d+)\s*$", text)
            if m:
                works_count = int(m.group(1))

        actors.append({
            "name": name,
            "javdb_code": javdb_code,
            "profile_url": f"https://javdb.com/actors/{javdb_code}",
            "cover": cover,
            "works_count": works_count,
        })

    logger.info(f"解析 JAVDB 演员列表：{len(actors)} 条")
    return actors


def parse_actor_detail_page(html: str, javdb_code: str) -> Dict:
    """
    解析演员详情页，提取热度相关指标

    JAVDB 演员详情页包含：
    - 演员名
    - 作品数（标题里有，如 "河北彩花 206 部影片"）
    - 排序选项卡（按热度/按评分/按时间）

    Returns:
        {
            'name': str,
            'javdb_code': str,
            'total_works': int,       # 总作品数
            'featured_works': int,    # 精选作品数
        }
    """
    soup = BeautifulSoup(html, "lxml")

    result = {
        "name": "",
        "javdb_code": javdb_code,
        "total_works": 0,
        "featured_works": 0,
    }

    # 提取演员名
    # 结构：<h2 class="title">河北彩花</h2> <small>206 部影片</small>
    title_tag = soup.find("h2", class_="title")
    if title_tag:
        result["name"] = title_tag.get_text(strip=True)
        small = title_tag.find("small")
        if small:
            text = small.get_text(strip=True)  # "206 部影片"
            m = re.search(r"(\d+)", text)
            if m:
                result["total_works"] = int(m.group(1))

    if not result["name"]:
        # 备选：从页面 title
        title_elem = soup.find("title")
        if title_elem:
            text = title_elem.get_text(strip=True)
            # 格式：河北彩花 - 演員 - JavDB
            parts = text.split(" - ")
            if parts:
                result["name"] = parts[0].strip()

    # 尝试从 meta 中提取作品数（更精确）
    meta_count = soup.find("meta", attrs={"name": "description"})
    if meta_count:
        desc = meta_count.get("content", "")
        m = re.search(r"(\d+)\s*部", desc)
        if m:
            result["total_works"] = int(m.group(1))

    logger.info(f"解析 JAVDB 演员详情：{result['name']} ({javdb_code}), "
                f"作品数={result['total_works']}")
    return result


def parse_actor_ranking_scores(html: str, javdb_code: str) -> Dict[str, float]:
    """
    从演员页面解析热度分数量化指标

    JAVDB 演员详情页显示：
    - 排序选项卡：熱度倒序、評分倒序、想看人數、看過人數

    这里提取"熱度"排序下作品列表中的相对位置和评分信息
    用于计算综合热度分

    Returns:
        {
            'name': str,
            'javdb_code': str,
            'page_views_estimate': int,  # 估算浏览量
            'favorite_count': int,        # 收藏/想看数
            'viewed_count': int,         # 看过数
            'rating_score': float,       # 平均评分
            'rating_count': int,         # 评分次数
        }
    """
    soup = BeautifulSoup(html, "lxml")
    result = {
        "name": "",
        "javdb_code": javdb_code,
        "page_views_estimate": 0,
        "favorite_count": 0,
        "viewed_count": 0,
        "rating_score": 0.0,
        "rating_count": 0,
    }

    # 提取演员名
    title_tag = soup.find("h2", class_="title")
    if title_tag:
        result["name"] = title_tag.get_text(strip=True)
    else:
        title_elem = soup.find("title")
        if title_elem:
            parts = title_elem.get_text(strip=True).split(" - ")
            if parts:
                result["name"] = parts[0].strip()

    # 提取评分信息
    # 格式：  4.35分, 由1636人評價
    full_text = soup.get_text(" ")

    # 评分模式
    rating_pattern = re.compile(
        r"([\d.]+)\s*分\s*[,，]\s*由\s*([\d,，]+)\s*人\s*[評评]\s*價",
        re.IGNORECASE
    )
    for m in rating_pattern.finditer(full_text):
        score = float(m.group(1))
        count_str = m.group(2).replace(",", "").replace("，", "")
        count = int(count_str)
        # 取第一个（最高的）
        if result["rating_score"] == 0.0:
            result["rating_score"] = score
            result["rating_count"] = count

    # 估算页面浏览量
    # JAVDB 显示"想看"和"看过"的人数
    # 模式：加入"想看"清单 / 加入"看过"清单
    viewed_pattern = re.compile(r"加入\"看過\"清单\s*\(?([\d,，]+)\)?", re.IGNORECASE)
    fav_pattern = re.compile(r"加入\"想看\"清单\s*\(?([\d,，]+)\)?", re.IGNORECASE)

    viewed_m = viewed_pattern.search(full_text)
    if viewed_m:
        result["viewed_count"] = int(viewed_m.group(1).replace(",", "").replace("，", ""))

    fav_m = fav_pattern.search(full_text)
    if fav_m:
        result["favorite_count"] = int(fav_m.group(1).replace(",", "").replace("，", ""))

    logger.info(f"JAVDB 演员热度数据：{result['name']} ({javdb_code}), "
                f"看过={result['viewed_count']}, 想看={result['favorite_count']}, "
                f"评分={result['rating_score']} ({result['rating_count']}人)")
    return result


def calculate_javdb_popularity_score(
    total_works: int,
    viewed_count: int,
    favorite_count: int,
    rating_score: float,
    rating_count: int,
) -> float:
    """
    根据 JAVDB 热度指标计算综合热度分

    公式参考 JAVDB 的"熱度倒序"排序逻辑：
    热度分 = 作品数 × 0.5
           + 看过人数 × 0.1
           + 想看人数 × 0.2
           + 评分 × sqrt(评分次数) × 0.1

    归一化到合理范围（0-100）
    """
    score = (
        total_works * 0.5
        + viewed_count * 0.1
        + favorite_count * 0.2
        + rating_score * (rating_count ** 0.5) * 0.1
    )
    return round(score, 4)
