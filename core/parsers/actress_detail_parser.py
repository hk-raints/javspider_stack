"""
女优详情页解析器 - 兵部负责执行

解析 https://www.javbus.com/star/{id}
提取：个人信息 + 作品列表 + 分页
"""
import logging
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from config import JAVBUS_BASE

logger = logging.getLogger("bingbu.actress_detail")


def parse_actress_profile(html: str, javbus_id: str) -> Dict:
    """
    解析女优个人信息

    Returns:
        {
            'name': str,
            'avatar': str,
            'birthday': str,
            'age': str,
            'height': str,
            'cup': str,
            'bust': str,
            'waist': str,
            'hip': str,
            'hobby': str,
        }
    """
    soup = BeautifulSoup(html, "lxml")
    info = {
        "name": "",
        "avatar": "",
        "birthday": "",
        "age": "",
        "height": "",
        "cup": "",
        "bust": "",
        "waist": "",
        "hip": "",
        "hobby": "",
    }

    # ── 提取姓名 ──
    # h3 或 title
    h3 = soup.find("h3")
    if h3:
        info["name"] = h3.get_text(strip=True)
    else:
        title_tag = soup.find("title")
        if title_tag:
            # 格式：三上悠亜 - 女優 - 影片 - JavBus
            info["name"] = title_tag.text.split(" - ")[0].strip()

    # ── 提取头像 ──
    # javbus 女优页头像通常在 .star-box 或第一个大图
    for selector in [".star-box img", ".actress-img img", ".photo-frame img"]:
        img = soup.select_one(selector)
        if img:
            info["avatar"] = img.get("src", "") or img.get("data-src", "")
            break
    if not info["avatar"]:
        # 备选：找 /pics/actress/ 路径的图片
        for img in soup.find_all("img", src=True):
            src = img.get("src", "")
            if "/actress/" in src or "/stars/" in src:
                info["avatar"] = src
                break

    # ── 提取个人信息 ──
    # javbus 结构：<p><span class="info">生日:</span> 1993-08-16</p>
    # 或 <p><span>身高:</span> 159cm</p>
    # 字段映射：中文/繁体标签 → 英文字段
    FIELD_MAP = {
        "生日": "birthday",
        "年齢": "age",
        "年齡": "age",
        "身高": "height",
        "罩杯": "cup",
        "胸围": "bust",
        "胸圍": "bust",
        "腰围": "waist",
        "腰圍": "waist",
        "臀围": "hip",
        "臀圍": "hip",
        "爱好": "hobby",
        "愛好": "hobby",
    }

    # 找包含信息的容器
    info_container = (
        soup.find("div", class_="star-box-info")
        or soup.find("div", class_="actress-info")
        or soup.find("div", class_="info")
        or soup.body
    )

    for p_tag in info_container.find_all("p"):
        text = p_tag.get_text(" ", strip=True)

        for label_cn, field in FIELD_MAP.items():
            if label_cn in text:
                # 去除标签部分，提取值
                value = text.replace(label_cn, "").replace(":", "").replace("：", "").strip()
                if value and not info[field]:
                    info[field] = value
                break

    # 备用：用正则直接从全文提取
    full_text = soup.get_text(" ")
    _patterns = {
        "birthday": r"生[日期][:\s：]?\s*([\d\-／/]+)",
        "age": r"年[齢齡][:\s：]?\s*(\d+)",
        "height": r"身高[:\s：]?\s*(\d+\s*cm)",
        "cup": r"罩杯[:\s：]?\s*([A-Za-z]+)",
        "bust": r"胸[围圍][:\s：]?\s*(\d+\s*cm)",
        "waist": r"腰[围圍][:\s：]?\s*(\d+\s*cm)",
        "hip": r"臀[围圍][:\s：]?\s*(\d+\s*cm)",
    }
    for field, pattern in _patterns.items():
        if not info[field]:
            m = re.search(pattern, full_text, re.IGNORECASE)
            if m:
                info[field] = m.group(1).strip()

    logger.info(f"解析女优信息: {info['name']} ({javbus_id})")
    return info


def parse_actress_works(html: str) -> List[Dict]:
    """
    解析女优作品列表（一页）

    Returns:
        List of {
            'code': str,        # 番号，如 SSIS-956
            'title': str,
            'cover': str,
            'release_date': str,
            'work_url': str,
        }
    """
    soup = BeautifulSoup(html, "lxml")
    works = []

    # 作品容器：#waterfall 下的 .movie-box 或 a.movie-box
    waterfall = soup.find("div", id="waterfall")
    if not waterfall:
        waterfall = soup.body

    for a_tag in waterfall.find_all("a", class_="movie-box"):
        href = a_tag.get("href", "")
        if not href:
            continue

        work_url = href if href.startswith("http") else f"{JAVBUS_BASE}{href}"

        # 番号：从 URL 最后一段提取
        code = href.rstrip("/").split("/")[-1].upper()

        # 封面图
        cover = ""
        img = a_tag.find("img")
        if img:
            cover = img.get("src", "") or img.get("data-src", "")

        # 标题
        title = a_tag.get("title", "")
        if not title:
            title_el = a_tag.find(class_="photo-info") or a_tag.find("span")
            if title_el:
                title = title_el.get_text(strip=True)

        # 日期
        release_date = ""
        date_el = a_tag.find("date")
        if date_el:
            release_date = date_el.get_text(strip=True)
        else:
            # 备用：从 photo-info 中找日期格式字符串
            info_el = a_tag.find(class_="photo-info")
            if info_el:
                date_m = re.search(r"\d{4}-\d{2}-\d{2}", info_el.get_text())
                if date_m:
                    release_date = date_m.group(0)

        works.append({
            "code": code,
            "title": title,
            "cover": cover,
            "release_date": release_date,
            "work_url": work_url,
        })

    logger.info(f"本页解析到 {len(works)} 个作品")
    return works


def parse_actress_works_pages(html: str, base_url: str) -> int:
    """
    解析女优作品页的总页数

    Returns:
        总页数（默认1）
    """
    soup = BeautifulSoup(html, "lxml")

    pagination = (
        soup.find("ul", class_="pagination")
        or soup.find("ul", class_="pagination-lg")
    )

    if not pagination:
        return 1

    max_page = 1
    for a in pagination.find_all("a", href=True):
        href = a.get("href", "")
        # /star/okq/2 格式
        m = re.search(r"/star/[^/]+/(\d+)/?$", href)
        if m:
            page_num = int(m.group(1))
            if page_num > max_page:
                max_page = page_num

    return max_page
