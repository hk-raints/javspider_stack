"""
作品详情页解析器 - 兵部负责执行

解析 https://www.javbus.com/{番号}
提取：番号、日期、导演、制作商、发行商、系列、标签、演员列表
同时提取磁力 AJAX 请求所需参数
"""
import logging
import re
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from config import JAVBUS_BASE

logger = logging.getLogger("bingbu.work_detail")


def parse_work_detail(html: str) -> Optional[Dict]:
    """
    解析作品详情页

    Returns:
        {
            'code': str,            # 识别码/番号
            'title': str,
            'cover': str,
            'release_date': str,
            'director': str,
            'studio': str,          # 制作商
            'label': str,           # 发行商
            'series': str,
            'tags': List[{'name': str, 'genre_id': str}],
            'cast': List[{'name': str, 'javbus_id': str, 'avatar': str}],
            # 磁力请求参数
            'magnet_params': {
                'uid': str,
                'gid': str,
                'uc': str,          # 有码=0，无码=1
            },
        }
        None 表示解析失败
    """
    soup = BeautifulSoup(html, "lxml")
    result = {
        "code": "",
        "title": "",
        "cover": "",
        "release_date": "",
        "director": "",
        "studio": "",
        "label": "",
        "series": "",
        "tags": [],
        "cast": [],
        "magnet_params": {},
    }

    # ── 标题 ──
    h3 = soup.find("h3")
    if h3:
        result["title"] = h3.get_text(strip=True)

    # ── 封面图 ──
    cover_img = soup.find("a", class_="bigImage") or soup.find("a", id="bigImage")
    if cover_img:
        img = cover_img.find("img")
        if img:
            result["cover"] = img.get("src", "")
    if not result["cover"]:
        # 备选：找 /pics/cover/ 路径
        for img in soup.find_all("img", src=True):
            src = img.get("src", "")
            if "/cover/" in src or "/pic/" in src:
                result["cover"] = src
                break

    # ── 信息字段 ──
    # javbus 结构：<div class="info"> 下面一系列 <p>
    # 每个 <p> 格式：<span class="header">字段名:</span> 值（可能是 <a> 链接）
    info_div = (
        soup.find("div", class_="info")
        or soup.find("div", id="info")
    )

    FIELD_MAP = {
        "識別碼": "code",
        "识别码": "code",
        "發行日期": "release_date",
        "发行日期": "release_date",
        "長度": None,   # 片长，忽略
        "导演": "director",
        "導演": "director",
        "製作商": "studio",
        "制作商": "studio",
        "發行商": "label",
        "发行商": "label",
        "系列": "series",
        "類別": "tags",
        "类别": "tags",
    }

    if info_div:
        for p in info_div.find_all("p"):
            span = p.find("span", class_="header") or p.find("span")
            if not span:
                continue

            label = span.get_text(strip=True).rstrip(":：").strip()
            field = FIELD_MAP.get(label)

            if field is None:
                continue

            if field == "tags":
                # 类别：多个 <a class="genre"> 链接
                for a in p.find_all("a"):
                    genre_href = a.get("href", "")
                    genre_id = genre_href.rstrip("/").split("/")[-1]
                    tag_name = a.get_text(strip=True)
                    if tag_name:
                        result["tags"].append({
                            "name": tag_name,
                            "genre_id": genre_id,
                        })
            else:
                # 普通字段：值可能是纯文本或 <a> 链接
                a_tag = p.find("a")
                if a_tag:
                    value = a_tag.get_text(strip=True)
                else:
                    # 去除 span 后剩余文本
                    span.decompose()
                    value = p.get_text(strip=True)
                if value and not result[field]:
                    result[field] = value

    # ── 备用：从全文正则提取番号 ──
    if not result["code"]:
        full_text = soup.get_text(" ")
        m = re.search(r"識別碼[:\s：]*([\w-]+)", full_text)
        if m:
            result["code"] = m.group(1).strip()
        else:
            # 从页面 title 提取
            title_tag = soup.find("title")
            if title_tag:
                m2 = re.search(r"([A-Z]{2,6}-\d{3,6})", title_tag.text.upper())
                if m2:
                    result["code"] = m2.group(1)

    # ── 演员列表 ──
    # <div class="star-show"> 或 <div id="starData">
    star_container = (
        soup.find("div", class_="star-show")
        or soup.find("div", id="starData")
        or soup.find("div", class_="star-box-list")
    )
    if star_container:
        for a in star_container.find_all("a", href=True):
            href = a.get("href", "")
            m = re.search(r"/star/([a-zA-Z0-9]+)/?$", href)
            if not m:
                continue
            star_id = m.group(1)
            name = a.get("title", "") or a.get_text(strip=True)
            avatar = ""
            img = a.find("img")
            if img:
                avatar = img.get("src", "") or img.get("data-src", "")
            if name:
                result["cast"].append({
                    "name": name,
                    "javbus_id": star_id,
                    "avatar": avatar,
                })

    # ── 提取磁力 AJAX 参数 ──
    # 原始 JavSpider 的方法：从 script[3] 中提取 var uid='...'; var gid='...'
    result["magnet_params"] = _extract_magnet_params(soup)

    logger.info(f"解析作品: {result['code']} - {result['title'][:30]}")
    return result if result["code"] else None


def _extract_magnet_params(soup: BeautifulSoup) -> Dict[str, str]:
    """
    从页面 JavaScript 中提取磁力 AJAX 请求参数
    javbus 页面 script 标签中包含：
        var uid='xxx'; var gid='yyy'; var uc=0;
    """
    params = {"uid": "", "gid": "", "uc": "0"}

    for script in soup.find_all("script"):
        text = script.string or ""
        if not text:
            continue

        uid_m = re.search(r"var\s+uid\s*=\s*['\"]?([^'\";\s]+)['\"]?", text)
        gid_m = re.search(r"var\s+gid\s*=\s*['\"]?([^'\";\s]+)['\"]?", text)
        uc_m = re.search(r"var\s+uc\s*=\s*['\"]?([^'\";\s]+)['\"]?", text)

        if uid_m:
            params["uid"] = uid_m.group(1)
        if gid_m:
            params["gid"] = gid_m.group(1)
        if uc_m:
            params["uc"] = uc_m.group(1)

        if params["uid"] and params["gid"]:
            break

    return params


def build_magnet_ajax_url(magnet_params: Dict[str, str], base_url: str = JAVBUS_BASE) -> Optional[str]:
    """
    根据提取的参数构造磁力 AJAX 请求 URL

    javbus AJAX 接口：
    /ajax/uncledatoolsbyajax.php?gid={gid}&uc={uc}&lang=zh&floor={floor}
    """
    uid = magnet_params.get("uid", "")
    gid = magnet_params.get("gid", "")
    uc = magnet_params.get("uc", "0")

    if not gid:
        return None

    # floor 参数：固定值或随机，参考原始爬虫用 827
    import random
    floor = random.randint(100, 9999)

    url = f"{base_url}/ajax/uncledatoolsbyajax.php?gid={gid}&uc={uc}&lang=zh&floor={floor}"
    if uid:
        url += f"&uid={uid}"

    return url
