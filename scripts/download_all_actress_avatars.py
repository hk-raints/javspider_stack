#!/usr/bin/env python3
"""
批量下载女优头像到本地
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.session import engine
from sqlalchemy.orm import Session
from sqlalchemy import text
import httpx

# 配置
AVATARS_DIR = "static/avatars"
JAVBUS_BASE = "https://www.javbus.com"
TIMEOUT = 15
MAX_WORKERS = 10  # 并发数

def ensure_dir(path):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)

def download_avatar(actress_id: int, actress_name: str, avatar_path: str) -> dict:
    """下载单个女优头像"""
    if not avatar_path or avatar_path.startswith("http"):
        return {"id": actress_id, "name": actress_name, "status": "skipped", "reason": "无效路径"}

    # 提取文件名
    filename = avatar_path.split("/")[-1]
    local_path = os.path.join(AVATARS_DIR, filename)

    # 跳过本地已有的头像
    if os.path.exists(local_path):
        return {"id": actress_id, "name": actress_name, "status": "skipped", "reason": "已存在"}

    url = JAVBUS_BASE + avatar_path
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.javbus.com/",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        }
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200 and len(resp.content) > 1000:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                return {"id": actress_id, "name": actress_name, "status": "success", "path": local_path}
            else:
                return {"id": actress_id, "name": actress_name, "status": "failed", "reason": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"id": actress_id, "name": actress_name, "status": "failed", "reason": str(e)[:50]}

def main():
    ensure_dir(AVATARS_DIR)

    db = Session(bind=engine)
    try:
        # 查询所有有头像路径的女优
        result = db.execute(text('''
            SELECT id, name, avatar FROM actresses 
            WHERE avatar IS NOT NULL AND avatar != '' AND avatar NOT LIKE 'http%'
        '''))
        actresses = [(row[0], row[1], row[2]) for row in result]

        print(f"找到 {len(actresses)} 个需要下载头像的女优")

        # 统计已存在的
        existing = 0
        to_download = []
        for actress_id, name, avatar in actresses:
            filename = avatar.split("/")[-1]
            if os.path.exists(os.path.join(AVATARS_DIR, filename)):
                existing += 1
            else:
                to_download.append((actress_id, name, avatar))

        print(f"已存在: {existing}, 需要下载: {len(to_download)}")

        if not to_download:
            print("所有头像都已下载完成！")
            return

        # 开始下载
        success = 0
        failed = 0
        skipped = 0

        print(f"\n开始下载 {len(to_download)} 个头像...")
        print("-" * 60)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_avatar, aid, name, path): (aid, name)
                for aid, name, path in to_download
            }

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result["status"] == "success":
                    success += 1
                    print(f"[{i}/{len(to_download)}] ✅ {result['name'][:15]:<15} -> {result['path']}")
                elif result["status"] == "failed":
                    failed += 1
                    print(f"[{i}/{len(to_download)}] ❌ {result['name'][:15]:<15} -> {result['reason']}")
                else:
                    skipped += 1

                # 每100个打印进度
                if i % 100 == 0:
                    print(f"\n>>> 进度: {i}/{len(to_download)} 完成")

        print("-" * 60)
        print(f"\n下载完成！成功: {success}, 失败: {failed}, 跳过: {skipped}")

    finally:
        db.close()

if __name__ == "__main__":
    main()
