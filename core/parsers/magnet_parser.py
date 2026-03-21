"""
磁力链接解析器 - 兵部负责执行

解析 /ajax/uncledatoolsbyajax.php 接口返回的 HTML
提取所有磁力候选，包含：名称、URL、大小、分享日期
并计算筛选所需的优先级标记
"""
import logging
import re
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from config import MAGNET_PRIORITY

logger = logging.getLogger("bingbu.magnet")


def parse_magnets(html: str) -> List[Dict]:
    """
    解析磁力 AJAX 返回的 HTML，提取所有磁力候选

    Returns:
        List of {
            'name': str,          # 磁力名称（链接文本）
            'magnet_url': str,    # magnet:?xt=... 完整地址
            'size_str': str,      # 原始大小字符串，如 9.31GB
            'size_mb': float,     # 大小（MB）
            'share_date': str,    # 分享日期
            'is_uc': bool,
            'is_u': bool,
            'is_4k': bool,
            'is_uncensored': bool,
            'is_c': bool,
            'priority_level': int,  # 1=UC,2=U,3=4K,4=uncensored,5=C,99=普通
        }
    """
    soup = BeautifulSoup(html, "lxml")
    magnets = []

    # 检查是否无磁力
    no_magnet_text = soup.get_text()
    if "There is no magnet link for this video" in no_magnet_text:
        logger.info("该作品暂无磁力链接")
        return []

    # 磁力链接在 <tr> 行中，每行包含：
    # <td> 磁力名（a href="magnet:..."） </td>
    # <td> 文件大小 </td>
    # <td> 分享日期 </td>
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        # 第一列：磁力链接
        a_tag = tds[0].find("a", href=re.compile(r"^magnet:"))
        if not a_tag:
            continue

        magnet_url = a_tag.get("href", "")
        name = a_tag.get_text(strip=True)

        # 第二列：文件大小
        size_str = ""
        if len(tds) >= 2:
            size_str = tds[1].get_text(strip=True)

        # 第三列：分享日期
        share_date = ""
        if len(tds) >= 3:
            share_date = tds[2].get_text(strip=True)

        # 转换大小为 MB
        size_mb = _parse_size_to_mb(size_str)

        # 计算优先级标记
        flags = _calc_priority_flags(name)

        magnet_entry = {
            "name": name,
            "magnet_url": magnet_url,
            "size_str": size_str,
            "size_mb": size_mb,
            "share_date": share_date,
            **flags,
        }
        magnets.append(magnet_entry)

    logger.info(f"解析到 {len(magnets)} 条磁力候选")
    return magnets


def _parse_size_to_mb(size_str: str) -> float:
    """
    解析大小字符串为 MB

    Examples:
        "9.31GB" -> 9534.46
        "1.2GB"  -> 1228.8
        "512MB"  -> 512.0
        "1.5TB"  -> 1536000.0
    """
    if not size_str:
        return 0.0

    s = size_str.strip().upper().replace(" ", "")
    m = re.match(r"([\d.]+)\s*(TB|GB|MB|KB|B)?", s)
    if not m:
        return 0.0

    val = float(m.group(1))
    unit = m.group(2) or "MB"

    factor = {"B": 1/1024/1024, "KB": 1/1024, "MB": 1.0, "GB": 1024.0, "TB": 1024.0 * 1024}
    return round(val * factor.get(unit, 1.0), 2)


def _calc_priority_flags(name: str) -> Dict:
    """
    根据磁力名称计算优先级标记

    规则（按优先级排列）：
    1. -UC  (优先级1)
    2. -U   (优先级2，注意不能误判 -UC)
    3. -4K  (优先级3)
    4. uncensored（优先级4）
    5. -C   (优先级5，注意不能误判 -UC）

    无特殊标记：优先级99
    """
    name_upper = name.upper()

    is_uc = bool(re.search(r"-UC\b", name_upper))
    is_4k = bool(re.search(r"-4K\b", name_upper))
    is_uncensored = "UNCENSORED" in name_upper and not is_uc
    # -U 但不是 -UC
    is_u = bool(re.search(r"-U\b", name_upper)) and not is_uc
    # -C 但不是 -UC
    is_c = bool(re.search(r"-C\b", name_upper)) and not is_uc

    if is_uc:
        priority = 1
    elif is_u:
        priority = 2
    elif is_4k:
        priority = 3
    elif is_uncensored:
        priority = 4
    elif is_c:
        priority = 5
    else:
        priority = 99

    return {
        "is_uc": is_uc,
        "is_u": is_u,
        "is_4k": is_4k,
        "is_uncensored": is_uncensored,
        "is_c": is_c,
        "priority_level": priority,
    }


def pick_best_magnet(magnets: List[Dict]) -> Optional[Dict]:
    """
    按规则筛选最优磁力（户部-磁力筛选逻辑）

    规则：
    1. 优先筛选包含特殊标记的（-UC > -U > -4K > uncensored > -C）
    2. 在同优先级中选择最大的
    3. 如果最大文件大小相差 ≤10%，按优先级保留最高优先级的一条
    4. 如果无任何特殊标记，直接选最大的

    Returns:
        最优磁力字典，带 'pick_reason' 字段
        None 表示无可用磁力
    """
    if not magnets:
        return None

    from config import MAGNET_SIZE_DIFF_THRESHOLD

    # 按优先级分组
    priority_groups: Dict[int, List[Dict]] = {}
    for m in magnets:
        pl = m["priority_level"]
        priority_groups.setdefault(pl, []).append(m)

    # 找最高优先级（数字最小）
    best_priority = min(priority_groups.keys())

    if best_priority == 99:
        # 无特殊标记，直接选最大
        best = max(magnets, key=lambda x: x["size_mb"])
        best = dict(best)
        best["pick_reason"] = f"无特殊标记，选最大({best['size_str']})"
        return best

    # 有特殊标记：在最高优先级组中找最大
    candidates = priority_groups[best_priority]
    best_in_group = max(candidates, key=lambda x: x["size_mb"])
    max_size = best_in_group["size_mb"]

    # 检查是否有更大的（来自更低优先级）
    # 如果更低优先级的最大比当前最高优先级最大超过10%，则不采用
    all_max = max(magnets, key=lambda x: x["size_mb"])
    if all_max["priority_level"] != best_priority:
        size_diff = (all_max["size_mb"] - max_size) / max_size if max_size > 0 else 0
        if size_diff > MAGNET_SIZE_DIFF_THRESHOLD:
            # 大小差超过10%，说明高优先级里有更大的值得用
            # 但规则是优先判断特殊标记，所以还是用高优先级的
            pass

    best = dict(best_in_group)
    priority_label = {1: "-UC", 2: "-U", 3: "-4K", 4: "uncensored", 5: "-C"}.get(best_priority, "普通")
    best["pick_reason"] = f"优先级{priority_label}，最大({best['size_str']})"
    return best
