"""
数据管理模块 - 批量操作、备份、去重
"""
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from models import Actress, Work, Magnet


class BatchCrawlManager:
    """批量抓取管理器"""
    
    def __init__(self):
        self.queue: List[Dict] = []
        self.running = False
        self.current_actress_id = None
    
    def add_to_queue(self, actress_id: int, actress_name: str, 
                     domain: str = "https://www.javbus.com",
                     strategy: str = "清晰度",
                     mosaic: str = "all"):
        """添加女优到抓取队列"""
        # 检查是否已在队列中
        for item in self.queue:
            if item['actress_id'] == actress_id:
                return False
        
        self.queue.append({
            'actress_id': actress_id,
            'actress_name': actress_name,
            'domain': domain,
            'strategy': strategy,
            'mosaic': mosaic,
            'status': 'pending'
        })
        return True
    
    def remove_from_queue(self, actress_id: int):
        """从队列中移除"""
        self.queue = [item for item in self.queue if item['actress_id'] != actress_id]
    
    def get_queue_status(self) -> List[Dict]:
        """获取队列状态"""
        return self.queue.copy()
    
    def clear_queue(self):
        """清空队列"""
        self.queue = []
    
    def get_queue_position(self, actress_id: int) -> int:
        """获取女优在队列中的位置"""
        for i, item in enumerate(self.queue):
            if item['actress_id'] == actress_id:
                return i + 1
        return -1


class DatabaseBackup:
    """数据库备份管理"""
    
    def __init__(self, db_path: str, backup_dir: str = "data/backups"):
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def create_backup(self, prefix: str = "backup") -> Tuple[bool, str]:
        """创建数据库备份"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{prefix}_{timestamp}.db"
            backup_path = self.backup_dir / backup_name
            
            # 使用 SQLite 的在线备份功能
            source = sqlite3.connect(str(self.db_path))
            dest = sqlite3.connect(str(backup_path))
            
            source.backup(dest)
            
            dest.close()
            source.close()
            
            return True, str(backup_path)
        except Exception as e:
            return False, str(e)
    
    def list_backups(self) -> List[Dict]:
        """列出所有备份"""
        backups = []
        for f in self.backup_dir.glob("*.db"):
            stat = f.stat()
            backups.append({
                'name': f.name,
                'path': str(f),
                'size_mb': round(stat.st_size / (1024 * 1024), 2),
                'created_at': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
        return sorted(backups, key=lambda x: x['created_at'], reverse=True)
    
    def restore_backup(self, backup_path: str) -> Tuple[bool, str]:
        """从备份恢复数据库"""
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                return False, "备份文件不存在"
            
            # 先备份当前数据库
            self.create_backup(prefix="pre_restore")
            
            # 复制备份文件覆盖当前数据库
            shutil.copy2(backup_file, self.db_path)
            
            return True, "恢复成功"
        except Exception as e:
            return False, str(e)
    
    def delete_backup(self, backup_path: str) -> Tuple[bool, str]:
        """删除备份文件"""
        try:
            Path(backup_path).unlink()
            return True, "删除成功"
        except Exception as e:
            return False, str(e)
    
    def auto_cleanup(self, keep_days: int = 30, keep_count: int = 10):
        """自动清理旧备份"""
        cutoff = datetime.now() - timedelta(days=keep_days)
        backups = self.list_backups()
        
        deleted = 0
        for i, backup in enumerate(backups):
            # 保留最新的 keep_count 个备份
            if i < keep_count:
                continue
            
            # 删除超过 keep_days 天的备份
            backup_time = datetime.strptime(backup['created_at'], "%Y-%m-%d %H:%M:%S")
            if backup_time < cutoff:
                try:
                    Path(backup['path']).unlink()
                    deleted += 1
                except:
                    pass
        
        return deleted


class DataDeduplicator:
    """数据去重管理"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def find_duplicate_works(self) -> List[Dict]:
        """查找重复的作品（同一女优下相同番号）"""
        # 查找重复的 (actress_id, code) 组合
        duplicates = self.db.query(
            Work.actress_id,
            Work.code,
            func.count(Work.id).label('count')
        ).group_by(
            Work.actress_id,
            Work.code
        ).having(
            func.count(Work.id) > 1
        ).all()
        
        result = []
        for dup in duplicates:
            works = self.db.query(Work).filter(
                Work.actress_id == dup.actress_id,
                Work.code == dup.code
            ).order_by(Work.created_at).all()
            
            result.append({
                'actress_id': dup.actress_id,
                'code': dup.code,
                'count': dup.count,
                'works': [{
                    'id': w.id,
                    'title': w.title,
                    'date': w.date,
                    'created_at': w.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    'magnets_count': len(w.magnets)
                } for w in works]
            })
        
        return result
    
    def find_duplicate_magnets(self) -> List[Dict]:
        """查找重复的磁力链接"""
        duplicates = self.db.query(
            Magnet.work_id,
            Magnet.url,
            func.count(Magnet.id).label('count')
        ).group_by(
            Magnet.work_id,
            Magnet.url
        ).having(
            func.count(Magnet.id) > 1
        ).all()
        
        result = []
        for dup in duplicates:
            magnets = self.db.query(Magnet).filter(
                Magnet.work_id == dup.work_id,
                Magnet.url == dup.url
            ).order_by(Magnet.created_at).all()
            
            work = self.db.query(Work).get(dup.work_id)
            
            result.append({
                'work_id': dup.work_id,
                'work_code': work.code if work else None,
                'url': dup.url[:100] + '...' if len(dup.url) > 100 else dup.url,
                'count': dup.count,
                'magnets': [{
                    'id': m.id,
                    'quality_score': m.quality_score,
                    'created_at': m.created_at.strftime("%Y-%m-%d %H:%M:%S")
                } for m in magnets]
            })
        
        return result
    
    def find_similar_magnets(self, similarity_threshold: float = 0.9) -> List[Dict]:
        """查找相似的磁力链接（同一作品的不同版本）"""
        # 获取所有有多个磁力的作品
        works = self.db.query(Work).filter(
            Work.id.in_(
                self.db.query(Magnet.work_id).group_by(
                    Magnet.work_id
                ).having(func.count(Magnet.id) > 1)
            )
        ).all()
        
        result = []
        for work in works:
            magnets = self.db.query(Magnet).filter(
                Magnet.work_id == work.id
            ).order_by(Magnet.quality_score.desc()).all()
            
            if len(magnets) > 1:
                result.append({
                    'work_id': work.id,
                    'work_code': work.code,
                    'work_title': work.title,
                    'magnets_count': len(magnets),
                    'best_magnet': {
                        'id': magnets[0].id,
                        'quality_score': magnets[0].quality_score,
                        'resolution': magnets[0].resolution,
                        'size_mb': magnets[0].size_mb,
                        'subtitle': magnets[0].subtitle
                    },
                    'all_magnets': [{
                        'id': m.id,
                        'quality_score': m.quality_score,
                        'resolution': m.resolution,
                        'size_mb': m.size_mb,
                        'subtitle': m.subtitle,
                        'url': m.url[:80] + '...' if len(m.url) > 80 else m.url
                    } for m in magnets]
                })
        
        return result
    
    def deduplicate_works(self, keep: str = 'first') -> Tuple[int, str]:
        """去重作品
        
        Args:
            keep: 'first' 保留最早的, 'last' 保留最新的
        """
        duplicates = self.find_duplicate_works()
        
        if not duplicates:
            return 0, "没有发现重复作品"
        
        deleted_count = 0
        errors = []
        
        for dup in duplicates:
            works = dup['works']
            if keep == 'first':
                # 保留第一个，删除其余
                to_delete = works[1:]
            else:
                # 保留最后一个，删除其余
                to_delete = works[:-1]
            
            for w in to_delete:
                try:
                    work = self.db.query(Work).get(w['id'])
                    if work:
                        # 先删除关联的磁力
                        self.db.query(Magnet).filter(Magnet.work_id == work.id).delete()
                        self.db.delete(work)
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"删除作品 {w['id']} 失败: {str(e)}")
        
        self.db.commit()
        
        msg = f"已删除 {deleted_count} 个重复作品"
        if errors:
            msg += f"，{len(errors)} 个失败"
        
        return deleted_count, msg
    
    def deduplicate_magnets(self, keep: str = 'best') -> Tuple[int, str]:
        """去重磁力链接
        
        Args:
            keep: 'best' 保留质量最高的, 'first' 保留最早的
        """
        duplicates = self.find_duplicate_magnets()
        
        if not duplicates:
            return 0, "没有发现重复磁力链接"
        
        deleted_count = 0
        errors = []
        
        for dup in duplicates:
            magnets_data = dup['magnets']
            
            if keep == 'best':
                # 按质量分数排序，保留最高的
                sorted_magnets = sorted(magnets_data, key=lambda x: x['quality_score'], reverse=True)
                to_delete = sorted_magnets[1:]
            else:
                # 保留最早的
                to_delete = magnets_data[1:]
            
            for m in to_delete:
                try:
                    magnet = self.db.query(Magnet).get(m['id'])
                    if magnet:
                        self.db.delete(magnet)
                        deleted_count += 1
                except Exception as e:
                    errors.append(f"删除磁力 {m['id']} 失败: {str(e)}")
        
        self.db.commit()
        
        msg = f"已删除 {deleted_count} 个重复磁力链接"
        if errors:
            msg += f"，{len(errors)} 个失败"
        
        return deleted_count, msg
    
    def get_dedup_stats(self) -> Dict:
        """获取去重统计"""
        return {
            'duplicate_works': len(self.find_duplicate_works()),
            'duplicate_magnets': len(self.find_duplicate_magnets()),
            'works_with_multiple_magnets': len(self.find_similar_magnets())
        }


class ExportManager:
    """数据导出管理"""
    
    def __init__(self, db: Session, export_dir: str = "data/exports"):
        self.db = db
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def export_magnets_txt(self, actress_ids: List[int] = None, 
                           min_score: int = 0,
                           include_subtitle_only: bool = False) -> Tuple[bool, str, str]:
        """导出磁力链接为 TXT 文件
        
        Returns:
            (success, message, file_path)
        """
        try:
            # 构建查询
            query = self.db.query(Magnet).join(Work).join(Actress)
            
            if actress_ids:
                query = query.filter(Actress.id.in_(actress_ids))
            
            if min_score > 0:
                query = query.filter(Magnet.quality_score >= min_score)
            
            if include_subtitle_only:
                query = query.filter(Magnet.subtitle == True)
            
            magnets = query.order_by(
                Actress.name,
                Work.date.desc(),
                Magnet.quality_score.desc()
            ).all()
            
            if not magnets:
                return False, "没有符合条件的磁力链接", ""
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"magnets_{timestamp}.txt"
            filepath = self.export_dir / filename
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# JavSpider Stack 磁力链接导出\n")
                f.write(f"# 导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"# 总数: {len(magnets)}\n")
                f.write(f"# 最低分数: {min_score}\n\n")
                
                current_actress = None
                for m in magnets:
                    work = m.work
                    actress = work.actress
                    
                    # 女优分隔
                    if actress.name != current_actress:
                        if current_actress is not None:
                            f.write("\n")
                        f.write(f"\n### {actress.name} ###\n\n")
                        current_actress = actress.name
                    
                    # 写入信息
                    f.write(f"[{work.code}] {work.title}\n")
                    f.write(f"  日期: {work.date} | 分数: {m.quality_score} | ")
                    f.write(f"清晰度: {m.resolution or '未知'} | 大小: {m.size_mb:.0f}MB")
                    if m.subtitle:
                        f.write(" | 字幕")
                    f.write("\n")
                    f.write(f"  {m.url}\n\n")
            
            return True, f"成功导出 {len(magnets)} 个磁力链接", str(filepath)
            
        except Exception as e:
            return False, f"导出失败: {str(e)}", ""
    
    def export_magnets_csv(self, actress_ids: List[int] = None,
                           min_score: int = 0) -> Tuple[bool, str, str]:
        """导出磁力链接为 CSV 文件"""
        try:
            import csv
            
            # 构建查询
            query = self.db.query(Magnet).join(Work).join(Actress)
            
            if actress_ids:
                query = query.filter(Actress.id.in_(actress_ids))
            
            if min_score > 0:
                query = query.filter(Magnet.quality_score >= min_score)
            
            magnets = query.order_by(
                Actress.name,
                Work.date.desc(),
                Magnet.quality_score.desc()
            ).all()
            
            if not magnets:
                return False, "没有符合条件的磁力链接", ""
            
            # 生成文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"magnets_{timestamp}.csv"
            filepath = self.export_dir / filename
            
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    '女优', '番号', '标题', '日期', '磁力链接', 
                    '质量分数', '清晰度', '大小(MB)', '字幕', '编码'
                ])
                
                for m in magnets:
                    work = m.work
                    actress = work.actress
                    writer.writerow([
                        actress.name,
                        work.code,
                        work.title,
                        work.date,
                        m.url,
                        m.quality_score,
                        m.resolution or '',
                        round(m.size_mb, 2),
                        '是' if m.subtitle else '否',
                        m.codec or ''
                    ])
            
            return True, f"成功导出 {len(magnets)} 条记录", str(filepath)
            
        except Exception as e:
            return False, f"导出失败: {str(e)}", ""
    
    def export_works_json(self, actress_ids: List[int] = None) -> Tuple[bool, str, str]:
        """导出作品数据为 JSON"""
        try:
            import json
            
            query = self.db.query(Work).join(Actress)
            
            if actress_ids:
                query = query.filter(Actress.id.in_(actress_ids))
            
            works = query.order_by(Actress.name, Work.date.desc()).all()
            
            if not works:
                return False, "没有符合条件的作品", ""
            
            # 构建数据结构
            data = []
            for work in works:
                work_data = {
                    'code': work.code,
                    'title': work.title,
                    'date': work.date,
                    'actress': work.actress.name,
                    'cover': work.cover,
                    'magnets': [{
                        'url': m.url,
                        'quality_score': m.quality_score,
                        'resolution': m.resolution,
                        'size_mb': m.size_mb,
                        'subtitle': m.subtitle,
                        'codec': m.codec
                    } for m in work.magnets]
                }
                data.append(work_data)
            
            # 写入文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"works_{timestamp}.json"
            filepath = self.export_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            return True, f"成功导出 {len(works)} 个作品", str(filepath)
            
        except Exception as e:
            return False, f"导出失败: {str(e)}", ""
    
    def list_exports(self) -> List[Dict]:
        """列出所有导出文件"""
        exports = []
        for f in self.export_dir.glob("*"):
            if f.is_file() and f.suffix in ['.txt', '.csv', '.json']:
                stat = f.stat()
                exports.append({
                    'name': f.name,
                    'path': str(f),
                    'size_kb': round(stat.st_size / 1024, 2),
                    'created_at': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    'type': f.suffix[1:].upper()
                })
        return sorted(exports, key=lambda x: x['created_at'], reverse=True)


# 全局批量抓取管理器
batch_manager = BatchCrawlManager()
