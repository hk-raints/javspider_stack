"""
女优列表页解析器 - 兵部负责执行

解析 https://www.javbus.com/actresses
以及分页 https://www.javbus.com/actresses/{page}
"""
import logging
import re
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup
from config import JAVBUS_BASE

logger = logging.getLogger("bingbu.actresses_list")


def parse_actresses_page(html: str) -> List[Dict]:
    """
    解析女优列表页，提取女优基本信息

    Returns:
        List of {
            'name': str,       # 女优姓名
            'javbus_id': str,  # 如 okq
            'profile_url': str, # 完整URL
            'avatar': str,     # 头像URL
        }
    """
    soup = BeautifulSoup(html, "lxml")
    actresses = []

    # 女优卡片：<a href="/star/okq" ...>
    # 实际结构：整个 #waterfall 下或 .actress-waterfall 下的 a 标签
    # javbus actresses 页：每个 a 标签包含 img（头像）和 span（姓名）

    # 先找主内容区
    container = (
        soup.find("div", id="waterfall")
        or soup.find("div", class_="star-box-list")
        or soup.find("div", class_="row")
        or soup.body
    )

    if not container:
        logger.warning("未找到女优列表容器")
        return actresses

    for a_tag in container.find_all("a", href=True):
        href = a_tag.get("href", "")

        # 只处理 /star/ 开头的链接
        star_match = re.search(r"/star/([a-zA-Z0-9]+)$", href)
        if not star_match:
            # 兼容完整 URL
            star_match = re.search(r"javbus\.com/star/([a-zA-Z0-9]+)$", href)
        if not star_match:
            continue

        javbus_id = star_match.group(1)

        # 提取姓名：优先 title 属性，其次 span 内容
        name = a_tag.get("title", "").strip()
        if not name:
            span = a_tag.find("span")
            if span:
                name = span.get_text(strip=True)
        if not name:
            continue

        # 提取头像
        img = a_tag.find("img")
        avatar = ""
        if img:
            avatar = img.get("src", "") or img.get("data-src", "")

        # 拼接完整 URL
        if href.startswith("http"):
            profile_url = href
        else:
            profile_url = f"{JAVBUS_BASE}{href}"

        actresses.append({
            "name": name,
            "javbus_id": javbus_id,
            "profile_url": profile_url,
            "avatar": avatar,
        })

    # 去重（同一 javbus_id 可能出现多次）
    seen = set()
    unique = []
    for a in actresses:
        if a["javbus_id"] not in seen:
            seen.add(a["javbus_id"])
            unique.append(a)

    logger.info(f"本页解析到 {len(unique)} 位女优")
    return unique


def parse_total_pages(html: str) -> int:
    """
    解析总页数

    Returns:
        总页数（默认1）
    """
    soup = BeautifulSoup(html, "lxml")

    # 分页：<ul class="pagination"> 或 id="nav"
    pagination = (
        soup.find("ul", class_="pagination")
        or soup.find("ul", class_="pagination-lg")
        or soup.find("div", id="nav")
    )

    if not pagination:
        return 1

    max_page = 1
    for a in pagination.find_all("a", href=True):
        href = a.get("href", "")
        # /actresses/23 或 /actresses/23/
        m = re.search(r"/actresses/(\d+)/?$", href)
        if m:
            page_num = int(m.group(1))
            if page_num > max_page:
                max_page = page_num

    logger.info(f"解析到总页数: {max_page}")
    return max_page
