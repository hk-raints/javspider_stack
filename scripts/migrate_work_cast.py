"""
一次性数据迁移：为已有作品建立女优关联
通过解析 work.title 中的女优姓名，与 actresses.name 精确匹配
策略：按空格分词，只匹配全为日文/中日韩字符的词
"""
import sqlite3
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 1. 加载所有女优姓名（精确匹配）
cur.execute("SELECT id, name FROM actresses")
actresses = {name.strip(): aid for aid, name in cur.fetchall()}
print(f"加载了 {len(actresses)} 位女优")

# 匹配全为 CJK/假名的词（即人名）
jp_word_pattern = re.compile(r'^[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]+$')

# 2. 读取所有作品
cur.execute("SELECT id, title FROM works")
works = cur.fetchall()
print(f"处理 {len(works)} 部作品...")

# 3. 遍历，建立关联
inserted = 0
for work_id, title in works:
    if not title:
        continue
    # 按空格分词
    tokens = title.split()
    for token in tokens:
        token = token.strip()
        if jp_word_pattern.match(token) and token in actresses:
            try:
                cur.execute(
                    "INSERT OR IGNORE INTO work_cast (work_id, actress_id) VALUES (?, ?)",
                    (work_id, actresses[token])
                )
                if cur.rowcount > 0:
                    inserted += 1
            except Exception:
                pass

conn.commit()

# 验证
cur.execute("SELECT COUNT(*) FROM work_cast")
total_cast = cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT actress_id) FROM work_cast")
actresses_with_works = cur.fetchone()[0]
cur.execute("SELECT COUNT(DISTINCT work_id) FROM work_cast")
works_with_actresses = cur.fetchone()[0]

print(f"\n✅ 迁移完成")
print(f"   新增 work_cast 记录：{inserted} 条")
print(f"   有作品关联的女优：{actresses_with_works} 人")
print(f"   有女优关联的作品：{works_with_actresses} 部")
print(f"   work_cast 总记录：{total_cast} 条")

conn.close()
