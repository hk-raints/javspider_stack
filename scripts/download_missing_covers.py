#!/usr/bin/env python3
"""下载缺失的作品封面到本地"""

import os
import sys
import sqlite3
import requests
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / 'data' / 'javbus.db'
COVERS_DIR = BASE_DIR / 'static' / 'covers'
JAVBUS_BASE = "https://www.javbus.com"

COVERS_DIR.mkdir(parents=True, exist_ok=True)


def get_works_without_local_covers():
    """获取需要下载封面的作品（排除已有本地文件的）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取所有作品
    cursor.execute("""
        SELECT id, code, cover FROM works
        WHERE cover IS NOT NULL AND cover != ''
        ORDER BY id
    """)
    all_works = cursor.fetchall()

    # 获取已有的本地封面文件
    existing_files = set()
    if COVERS_DIR.exists():
        for f in COVERS_DIR.iterdir():
            if f.suffix in ['.jpg', '.jpeg', '.png', '.webp']:
                existing_files.add(f.name)

    print(f"数据库作品数: {len(all_works)}")
    print(f"已有封面文件: {len(existing_files)}")

    # 找出需要下载的
    to_download = []
    for work_id, code, cover in all_works:
        if not cover:
            continue
        # 计算可能的本地文件名
        filename = cover.replace('/pics/cover/', '').replace('/', '_')
        # 也检查以 /static/covers/ 开头的（新版格式）
        if cover.startswith('/static/covers/'):
            filename = cover.replace('/static/covers/', '')
        else:
            filename = cover.replace('/pics/cover/', '').replace('/', '_')

        if filename not in existing_files:
            to_download.append((work_id, code, cover, filename))

    conn.close()
    return to_download


def download_cover(work_id: int, code: str, cover_url: str, filename: str) -> bool:
    """下载单个封面"""
    local_path = COVERS_DIR / filename

    # 如果已存在则跳过
    if local_path.exists():
        return True

    try:
        # 构建完整 URL
        if cover_url.startswith('http'):
            full_url = cover_url
        else:
            full_url = JAVBUS_BASE + cover_url

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": JAVBUS_BASE + "/",
        }

        resp = requests.get(full_url, headers=headers, timeout=30, allow_redirects=True)

        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(local_path, "wb") as f:
                f.write(resp.content)
            return True
        else:
            print(f"  [失败] {code}: HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"  [错误] {code}: {e}")
        return False


def main():
    print("=" * 50)
    print("开始下载缺失的作品封面...")
    print("=" * 50)

    to_download = get_works_without_local_covers()
    total = len(to_download)
    print(f"\n需要下载: {total} 个封面\n")

    if total == 0:
        print("所有封面都已下载完成！")
        return

    success = 0
    failed = 0

    # 使用线程池并发下载
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(download_cover, work_id, code, cover, filename): (work_id, code)
            for work_id, code, cover, filename in to_download
        }

        for i, future in enumerate(as_completed(futures)):
            if future.result():
                success += 1
            else:
                failed += 1

            # 每 20 个打印进度
            if (i + 1) % 20 == 0 or (i + 1) == total:
                print(f"进度: {i+1}/{total} (成功: {success}, 失败: {failed})")

    print("\n" + "=" * 50)
    print(f"完成! 成功: {success}, 失败: {failed}")
    print(f"封面保存在: {COVERS_DIR}")
    print("=" * 50)


if __name__ == '__main__':
    main()
