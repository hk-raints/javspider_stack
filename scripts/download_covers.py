#!/usr/bin/env python3
"""下载作品封面到本地"""

import os
import sys
import sqlite3
import requests
from urllib.parse import urljoin
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'javbus.db')
COVERS_DIR = os.path.join(BASE_DIR, 'static', 'covers')
JAVBUS_BASE = "https://www.javbus.com"

def get_works_without_covers():
    """获取所有需要下载封面的作品"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, code, cover FROM works 
        WHERE cover IS NOT NULL AND cover != ''
        ORDER BY id
    """)
    works = cursor.fetchall()
    conn.close()
    return works

def download_cover(work_id, code, cover_path):
    """下载单个封面"""
    # 将 /pics/cover/xxx_b.jpg 转换为本地文件名
    filename = cover_path.replace('/pics/cover/', '').replace('/', '_')
    local_path = os.path.join(COVERS_DIR, filename)
    
    # 如果已存在则跳过
    if os.path.exists(local_path):
        return local_path
    
    # 下载高清版本 (将 _b 替换为更高清的版本如果需要)
    url = JAVBUS_BASE + cover_path
    
    try:
        # 使用更长的超时和更大的重试
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.javbus.com/',
        }
        resp = requests.get(url, headers=headers, timeout=30, allow_redirects=True)
        
        if resp.status_code == 200 and len(resp.content) > 1000:
            with open(local_path, 'wb') as f:
                f.write(resp.content)
            return local_path
        else:
            print(f"  [失败] {code}: HTTP {resp.status_code}, {len(resp.content)} bytes")
            return None
    except Exception as e:
        print(f"  [错误] {code}: {e}")
        return None

def main():
    print("=" * 50)
    print("开始下载作品封面...")
    print("=" * 50)
    
    works = get_works_without_covers()
    total = len(works)
    print(f"共 {total} 个作品需要下载封面\n")
    
    # 检查已有数量
    existing = len([f for f in os.listdir(COVERS_DIR) if f.endswith('.jpg')])
    print(f"已有 {existing} 个封面本地文件\n")
    
    success = 0
    failed = 0
    
    for i, (work_id, code, cover) in enumerate(works):
        # 检查本地是否已有
        filename = cover.replace('/pics/cover/', '').replace('/', '_')
        local_path = os.path.join(COVERS_DIR, filename)
        
        if os.path.exists(local_path):
            success += 1
            continue
        
        result = download_cover(work_id, code, cover)
        
        if result:
            success += 1
        else:
            failed += 1
        
        # 每 10 个打印进度
        if (i + 1) % 10 == 0:
            print(f"进度: {i+1}/{total} (成功: {success}, 失败: {failed})")
        
        # 礼貌延迟
        time.sleep(0.3)
    
    print("\n" + "=" * 50)
    print(f"完成! 成功: {success}, 失败: {failed}")
    print(f"封面保存在: {COVERS_DIR}")
    print("=" * 50)

if __name__ == '__main__':
    main()
