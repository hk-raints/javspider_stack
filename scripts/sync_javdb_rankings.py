#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 JAVDB 同步演员热度排名数据

使用 agent-browser 浏览器自动化访问 JAVDB，
抓取演员热度数据并更新本地数据库的 popularity_score 字段。

使用方式:
    python scripts/sync_javdb_rankings.py --limit 100 --pages 3

前置要求:
    1. agent-browser 已安装: npm install -g agent-browser && agent-browser install
"""
import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ── 项目路径设置 ──
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import text
from db.session import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("javdb_sync")


# ── JAVDB URL ──
JAVDB_BASE = "https://javdb.com"
JAVDB_ACTORS_URL = f"{JAVDB_BASE}/actors"
# 排名页：月榜演员（无翻页限制，一次性显示 ~96 位）
JAVDB_RANKINGS_URL = f"{JAVDB_BASE}/rankings/actors"


# ── agent-browser 辅助函数 ──────────────────────────────────────────

def _run(cmd: str, timeout: int = 30) -> str:
    """执行 shell 命令，返回 stdout"""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip()


def _browse(url: str, delay: float = 3.5):
    """打开页面，等待加载"""
    _run(f'agent-browser open "{url}"')
    time.sleep(delay)


def _click_age_gate():
    """若出现年龄验证，点击通过"""
    snapshot = _run("agent-browser snapshot -i")
    for line in snapshot.split("\n"):
        if "是,我已滿18歲" in line:
            m = re.search(r"\[ref=(e\d+)\]", line)
            if m:
                ref = m.group(1)
                _run(f"agent-browser click @{ref}")
                logger.info(f"已点击年龄验证按钮 @{ref}")
                time.sleep(2.5)
                return True
    return False


def _extract_actors() -> list[dict]:
    """
    从当前页面提取演员数据（两步法：执行 JS → 读取结果）

    演员 HTML 结构（主列表）：
    <div class="box actor-box">
      <a href="/actors/CODE">
        <figure class="image"><img ...></figure>
        <strong>NAME</strong>
      </a>
    </div>
    """
    import shlex

    # JS 代码：全部用双引号（与 Python 单引号字符串配合 shlex.quote 使用）
    # /\s+/g 在 Python 字符串中写成 \\s+
    # 排名页和演员页都使用 div.box.actor-box 选择演员
    js_code = (
        "window.__R__=(function(){"
        "var b=document.querySelectorAll('div.box.actor-box a[href^=\"/actors/\"]');"
        "var r=[];"
        "for(var i=0;i<b.length;i++){"
        "var a=b[i];"
        "var s=a.querySelector('strong');"
        "if(!s)continue;"
        "var n=s.textContent.replace(/\\s+/g,' ').trim();"
        "var h=a.getAttribute('href');"
        "if(!h)continue;"
        "var c=h.split('/actors/')[1];"
        "if(!c||c.indexOf('/')>-1)continue;"
        "if(!n)continue;"
        "r.push({n:n,c:c,u:a.href});"
        "}"
        "return JSON.stringify(r)"
        "})()"
    )
    escaped = shlex.quote(js_code)

    def _run_cmd(cmd_list):
        r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=20)
        return r.stdout.strip()

    # 步骤1：执行 JS（bash -c + shlex.quote 处理引号）
    _run_cmd(["bash", "-c", f"agent-browser eval {escaped}"])
    time.sleep(0.3)

    # 步骤2：读取结果
    result = _run_cmd(["bash", "-c", "agent-browser eval 'window.__R__'"])

    if not result or result in ("null", "undefined") or len(result) < 5:
        logger.debug(f"eval 返回为空: {result[:80] if result else 'None'}")
        return []

    try:
        # agent-browser eval 返回双重 JSON 编码：json.loads 第一次得到字符串，第二次得到列表
        data = json.loads(json.loads(result))
        if not isinstance(data, list):
            logger.warning(f"期望 list，得到 {type(data)}")
            return []
        valid = [x for x in data
                 if isinstance(x, dict) and x.get("c") and x.get("n")]
        if len(valid) != len(data):
            logger.info(f"过滤 {len(data)-len(valid)} 条无效记录")
        return [{"name": x["n"], "code": x["c"],
                 "url": x.get("u", f"https://javdb.com/actors/{x['c']}")} for x in valid]
    except json.JSONDecodeError as e:
        logger.warning(f"JSON 解析失败: {e}, 内容: {result[:200]}")
        return []


# ── 热度计算 ─────────────────────────────────────────────────────────

def calculate_popularity_score(page: int, position: int) -> float:
    """
    根据演员在 JAVDB 列表中的页面位置计算热度分

    算法：
    - 第1页演员得分 80~101
    - 第5页演员得分 20~41
    - 同页内按位置线性衰减

    热度分 = (6 - page) * 20 + (61 - position) / 3
    """
    score = (6 - page) * 20 + (61 - position) / 3.0
    return round(score, 2)


# ── 核心抓取逻辑 ───────────────────────────────────────────────────────

def crawl_javdb_actors(max_pages: int = 5) -> list[dict]:
    """
    从 JAVDB 排名页抓取演员列表。

    注意：JAVDB 有反爬保护，pagination (URL ?page=N) 无法正常工作，
    所有 page 参数都返回第1页的内容。因此本函数直接抓取排名页的完整演员列表，
    不依赖翻页参数。
    """
    all_actors: list[dict] = []
    seen_codes: set[str] = set()

    # 打开排名页（处理年龄验证）
    logger.info("正在打开 JAVDB 排名页...")
    _browse(JAVDB_RANKINGS_URL, delay=5)
    _click_age_gate()
    time.sleep(1)

    actors = _extract_actors()
    logger.info(f"提取到 {len(actors)} 位演员（排名页）")

    if not actors:
        logger.warning("排名页无数据，尝试备用演员页...")
        _browse(JAVDB_ACTORS_URL, delay=4)
        _click_age_gate()
        actors = _extract_actors()
        logger.info(f"备用演员页提取到 {len(actors)} 位演员")

    # 遍历提取到的演员，按顺序分配排名
    for i, actor in enumerate(actors):
        code = actor["code"]
        if code not in seen_codes:
            seen_codes.add(code)
            # page=1 for all (pagination not available)
            # position = i+1 (rank in the list)
            all_actors.append({**actor, "page": 1, "position": i + 1})

    logger.info(f"去重后共 {len(all_actors)} 位演员")
    return all_actors


# ── 数据库更新 ─────────────────────────────────────────────────────────

def update_database(actors: list[dict]) -> int:
    """通过演员姓名匹配，更新本地 popularity_score"""
    db = SessionLocal()
    updated = 0

    try:
        # 确保 javdb_code 列存在
        try:
            db.execute(text(
                "ALTER TABLE actresses ADD COLUMN javdb_code VARCHAR(64)"
            ))
            db.commit()
        except Exception:
            db.rollback()

        for actor in actors:
            name = actor["name"]
            code = actor["code"]
            score = calculate_popularity_score(actor["page"], actor["position"])

            result = db.execute(
                text("""
                    UPDATE actresses
                    SET popularity_score = :score,
                        javdb_code = :code
                    WHERE name = :name
                """),
                {"score": score, "code": code, "name": name},
            )
            if result.rowcount > 0:
                updated += result.rowcount
                logger.debug(f"  ✅ {name} → {score} (javdb:{code})")

        db.commit()
        logger.info(f"数据库更新完成：{updated} 条")
    finally:
        db.close()

    return updated


# ── 主入口 ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="从 JAVDB 同步演员热度数据")
    parser.add_argument("--pages", "-p", type=int, default=5,
                        help="抓取 JAVDB 前几页（默认5页）")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅打印，不写入数据库")
    args = parser.parse_args()

    logger.info("=" * 55)
    logger.info("JAVDB 演员热度数据同步工具")
    logger.info("=" * 55)

    if shutil.which("agent-browser") is None:
        logger.error("agent-browser 未安装！请运行:")
        logger.error("  npm install -g agent-browser && agent-browser install")
        sys.exit(1)

    # 抓取
    actors = crawl_javdb_actors(max_pages=args.pages)

    if not actors:
        logger.error("未能获取演员数据！")
        sys.exit(1)

    # 预览
    logger.info(f"\n抓取完成，共 {len(actors)} 位演员（按 JAVDB 排名）:")
    for i, a in enumerate(actors[:15], 1):
        score = calculate_popularity_score(a["page"], a["position"])
        logger.info(f"  {i:2d}. {a['name']:<20} "
                    f"(第{a['page']}页/#{a['position']}) → {score}")

    if len(actors) > 15:
        logger.info(f"  ... 还有 {len(actors)-15} 位")

    if args.dry_run:
        logger.info("\n[Dry Run] 未写入数据库")
        return

    updated = update_database(actors)
    logger.info(f"\n✅ 完成：{updated} 条记录已更新热度分。")
    _run("agent-browser close")


if __name__ == "__main__":
    main()
