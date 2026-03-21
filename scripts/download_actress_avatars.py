#!/usr/bin/env python3
"""
下载已爬个人信息女优的头像到本地
"""
import os
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from db.session import engine
from sqlalchemy.orm import Session
from db.models import Actress

# 配置
AVATARS_DIR = "static/avatars"
JAVBUS_BASE = "https://www.javbus.com"
TIMEOUT = 15
MAX_WORKERS = 5

def ensure_dir(path):
    """确保目录存在"""
    os.makedirs(path, exist_ok=True)

def download_avatar(actress_name: str, avatar_path: str) -> dict:
    """下载单个女优头像"""
    if not avatar_path or avatar_path.startswith("http"):
        return {"name": actress_name, "status": "skipped", "reason": "无效路径"}

    # 跳过本地已有的头像
    local_path = os.path.join(AVATARS_DIR, avatar_path.split("/")[-1])
    if os.path.exists(local_path):
        return {"name": actress_name, "status": "skipped", "reason": "已存在"}

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
                return {"name": actress_name, "status": "success", "path": local_path}
            else:
                return {"name": actress_name, "status": "failed", "reason": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"name": actress_name, "status": "failed", "reason": str(e)}

def main():
    ensure_dir(AVATARS_DIR)

    db = Session(bind=engine)
    try:
        # 查询已爬取个人信息且有头像的女优
        actresses = db.query(Actress).filter(
            Actress.profile_crawled == True,
            Actress.avatar.isnot(None),
            Actress.avatar != "",
            ~Actress.avatar.startswith("http"),
            ~Actress.avatar.startswith("static/")
        ).all()

        print(f"找到 {len(actresses)} 个需要下载头像的女优")
        if not actresses:
            print("没有需要下载的头像")
            return

        results = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(download_avatar, a.name, a.avatar): a
                for a in actresses
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result["status"] == "success":
                    print(f"  ✅ {result['name']}: {result['path']}")
                elif result["status"] == "skipped":
                    print(f"  ⏭️ {result['name']}: {result['reason']}")
                else:
                    print(f"  ❌ {result['name']}: {result['reason']}")

        success = sum(1 for r in results if r["status"] == "success")
        print(f"\n完成: {success}/{len(results)} 成功下载")

    finally:
        db.close()

if __name__ == "__main__":
    main()
