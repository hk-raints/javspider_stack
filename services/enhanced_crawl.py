"""
增强版爬虫服务
集成四阶段流水线和防屏蔽机制
"""
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

from core.pipeline_manager import PipelineQueueManager, QueueType
from core.anti_block import AntiBlockManager, ExponentialBackoffRetry
from crawler.quality import score_quality, parse_resolution, parse_codec
from crawler.bridge import _extract_code

logger = logging.getLogger(__name__)


class EnhancedCrawlService:
    """增强版爬虫服务"""
    
    def __init__(
        self,
        db_session,
        ws_manager,
        base_concurrency: int = 4,
        proxies: Optional[List[str]] = None,
        base_urls: Optional[List[str]] = None,
        use_cloudflare_bypass: bool = False
    ):
        self.db = db_session
        self.ws_manager = ws_manager
        
        # 创建四阶段流水线
        self.pipeline = PipelineQueueManager(
            base_concurrency=base_concurrency
        )
        
        # 创建防屏蔽管理器
        self.anti_block = AntiBlockManager(
            proxies=proxies,
            base_urls=base_urls,
            use_cloudflare_bypass=use_cloudflare_bypass
        )
        
        # HTTP客户端
        self.client = None
        
        # 统计信息
        self.stats = {
            "total_works": 0,
            "completed_works": 0,
            "total_magnets": 0,
            "completed_magnets": 0,
            "errors": []
        }
        
        logger.info("EnhancedCrawlService initialized")
    
    async def start(self):
        """启动服务"""
        # 创建HTTP客户端
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
        )
        
        logger.info("EnhancedCrawlService started")
    
    async def stop(self):
        """停止服务"""
        # 停止流水线
        await self.pipeline.stop_all()
        
        # 关闭HTTP客户端
        if self.client:
            await self.client.aclose()
        
        logger.info("EnhancedCrawlService stopped")
    
    async def crawl_actress(
        self,
        actress_id: int,
        actress_name: str,
        strategy: str = "清晰度",
        mosaic: str = "all",
        max_works: int = 0  # 0表示无限制
    ) -> Dict[str, Any]:
        """爬取女优作品 (使用四阶段流水线)"""
        
        # 注册进度
        progress = self.ws_manager.register_progress(actress_id, actress_name)
        progress.add_log(f"开始抓取女优: {actress_name}", "info")
        progress.add_log(f"策略: {strategy}, 马赛克: {mosaic}", "info")
        progress.status = "running"
        
        try:
            # 定义处理器
            processors = {
                QueueType.INDEX: self._process_index_page,
                QueueType.DETAIL: self._process_detail_page,
                QueueType.WRITE: self._process_write,
                QueueType.DOWNLOAD: self._process_download
            }
            
            # 启动所有队列
            await self.pipeline.start_all(processors)
            
            # 第1阶段: 爬取索引页
            await self._fetch_index_pages(actress_name, max_works)
            
            # 等待所有任务完成
            await self._wait_for_completion()
            
            # 完成
            progress.complete()
            progress.add_log(
                f"抓取完成! 共 {self.stats['completed_works']} 个作品, "
                f"{self.stats['completed_magnets']} 个磁力",
                "success"
            )
            
            await self.ws_manager.broadcast_progress(actress_id)
            
            return {
                "status": "completed",
                "works": self.stats['completed_works'],
                "magnets": self.stats['completed_magnets'],
                "errors": len(self.stats['errors'])
            }
            
        except Exception as e:
            progress.set_error(str(e))
            progress.add_log(f"爬虫失败: {str(e)}", "error")
            await self.ws_manager.broadcast_progress(actress_id)
            
            logger.error(f"Crawl failed for actress {actress_name}: {e}")
            raise
    
    async def _fetch_index_pages(
        self,
        actress_name: str,
        max_works: int
    ):
        """第1阶段: 爬取索引页"""
        logger.info(f"Phase 1: Fetching index pages for {actress_name}")
        
        page = 1
        total_fetched = 0
        
        while True:
            if max_works > 0 and total_fetched >= max_works:
                logger.info(f"Reached max works limit: {max_works}")
                break
            
            # 构造URL
            url = self._build_search_url(actress_name, page)
            
            # 爬取索引页
            try:
                task_id = f"index-{actress_name}-{page}"
                await self.pipeline.add_task(
                    QueueType.INDEX,
                    task_id,
                    {
                        "url": url,
                        "actress_name": actress_name,
                        "page": page
                    }
                )
                
                total_fetched += 1
                page += 1
                
                # 延迟
                await self.anti_block.delay_manager.create_delay("index")
                
            except Exception as e:
                logger.error(f"Failed to add index task: {e}")
                break
            
            # 如果没有更多页面,退出
            if page > 10:  # 限制最多10页
                break
    
    async def _process_index_page(self, data: Dict):
        """处理索引页任务"""
        url = data['url']
        actress_name = data['actress_name']
        page = data['page']
        
        logger.info(f"Processing index page: {url}")
        
        try:
            # 获取请求配置
            config = self.anti_block.get_request_config()
            
            # 发送请求
            response = await self.client.get(url, headers=config['headers'])
            response.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 提取作品链接
            work_links = self._extract_work_links(soup)
            
            logger.info(f"Found {len(work_links)} works on page {page}")
            
            # 将作品链接添加到详情页队列
            for i, link in enumerate(work_links):
                task_id = f"detail-{actress_name}-{page}-{i}"
                await self.pipeline.add_task(
                    QueueType.DETAIL,
                    task_id,
                    {
                        "url": link,
                        "actress_name": actress_name,
                        "page": page
                    }
                )
            
            # 标记代理成功
            proxy = config.get('proxy')
            if proxy:
                self.anti_block.proxy_rotator.mark_success(proxy)
                
        except Exception as e:
            logger.error(f"Failed to process index page {url}: {e}")
            self.stats['errors'].append(str(e))
            
            # 标记代理失败
            config = self.anti_block.get_request_config()
            proxy = config.get('proxy')
            if proxy:
                self.anti_block.proxy_rotator.mark_fail(proxy)
    
    def _extract_work_links(self, soup: BeautifulSoup) -> List[str]:
        """提取作品链接"""
        links = []
        
        # JavBus作品链接
        for a in soup.select('a.movie-box'):
            href = a.get('href', '')
            if href and '/jav' in href:
                links.append(href)
        
        return links
    
    async def _process_detail_page(self, data: Dict):
        """处理详情页任务"""
        url = data['url']
        actress_name = data['actress_name']
        
        logger.info(f"Processing detail page: {url}")
        
        try:
            # 获取请求配置
            config = self.anti_block.get_request_config()
            
            # 发送请求
            response = await self.client.get(url, headers=config['headers'])
            response.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 提取作品信息
            work_data = self._extract_work_info(soup, url)
            
            # 提取磁力链接
            magnet_links = self._extract_magnet_links(soup)
            
            # 合并数据
            work_data['magnets'] = magnet_links
            work_data['actress_name'] = actress_name
            
            # 添加到写入队列
            task_id = f"write-{actress_name}-{work_data['code']}"
            await self.pipeline.add_task(
                QueueType.WRITE,
                task_id,
                work_data
            )
            
            # 标记代理成功
            proxy = config.get('proxy')
            if proxy:
                self.anti_block.proxy_rotator.mark_success(proxy)
                
        except Exception as e:
            logger.error(f"Failed to process detail page {url}: {e}")
            self.stats['errors'].append(str(e))
            
            # 标记代理失败
            config = self.anti_block.get_request_config()
            proxy = config.get('proxy')
            if proxy:
                self.anti_block.proxy_rotator.mark_fail(proxy)
    
    def _extract_work_info(self, soup: BeautifulSoup, url: str) -> Dict:
        """提取作品信息"""
        # 标题
        title_elem = soup.select_one('h3')
        title = title_elem.get_text(strip=True) if title_elem else ""
        
        # 番号
        code = _extract_code(title)
        
        # 日期
        date_elem = soup.select_one('span.text')
        date = date_elem.get_text(strip=True) if date_elem else ""
        
        # 封面
        cover_elem = soup.select_one('a.movie-box img')
        cover = cover_elem.get('src', '') if cover_elem else ""
        
        return {
            "code": code,
            "title": title,
            "date": date,
            "cover": cover,
            "url": url
        }
    
    def _extract_magnet_links(self, soup: BeautifulSoup) -> List[Dict]:
        """提取磁力链接"""
        magnets = []
        
        for a in soup.select('a.magnet-link'):
            href = a.get('href', '')
            if href.startswith('magnet:'):
                title = a.get_text(strip=True)
                
                # 解析大小
                size_text = ""
                size_elem = a.parent.select_one('td[style*="color:red"]')
                if size_elem:
                    size_text = size_elem.get_text(strip=True)
                
                magnets.append({
                    "url": href,
                    "title": title,
                    "size": size_text
                })
        
        return magnets
    
    async def _process_write(self, data: Dict):
        """处理写入任务 (保存到数据库)"""
        code = data.get('code')
        
        if not code:
            logger.warning("No code in work data, skipping")
            return
        
        logger.info(f"Writing work {code} to database")
        
        try:
            from models import Actress, Work, Magnet
            
            # 查找女优
            actress = self.db.query(Actress).filter(
                Actress.name == data['actress_name']
            ).first()
            
            if not actress:
                logger.warning(f"Actress {data['actress_name']} not found")
                return
            
            # 检查作品是否已存在
            existing_work = self.db.query(Work).filter(
                Work.code == code,
                Work.actress_id == actress.id
            ).first()
            
            if existing_work:
                logger.info(f"Work {code} already exists, skipping")
                return
            
            # 创建作品
            work = Work(
                actress_id=actress.id,
                code=code,
                title=data.get('title', ''),
                date=data.get('date', ''),
                site='javbus',
                cover=data.get('cover', '')
            )
            self.db.add(work)
            self.db.commit()
            self.db.refresh(work)
            
            # 创建磁力链接
            for magnet_data in data.get('magnets', []):
                # 质量评分
                score = score_quality(magnet_data)
                
                magnet = Magnet(
                    work_id=work.id,
                    url=magnet_data['url'],
                    size_mb=self._parse_size(magnet_data.get('size', '')),
                    resolution=parse_resolution(magnet_data.get('title', '')),
                    codec=parse_codec(magnet_data.get('title', '')),
                    subtitle=False,  # 简化处理
                    quality_score=score,
                    source='javbus',
                    title=magnet_data.get('title', '')
                )
                self.db.add(magnet)
                
                self.stats['completed_magnets'] += 1
            
            self.db.commit()
            self.stats['completed_works'] += 1
            
            logger.info(f"Work {code} saved with {len(magnet_data)} magnets")
            
        except Exception as e:
            logger.error(f"Failed to write work {code}: {e}")
            self.db.rollback()
            self.stats['errors'].append(str(e))
    
    def _parse_size(self, size_text: str) -> float:
        """解析大小 (MB)"""
        if not size_text:
            return 0.0
        
        import re
        m = re.search(r'([\d.]+)\s*([KMGTP]?)B', size_text.upper())
        if not m:
            return 0.0
        
        val = float(m.group(1))
        unit = m.group(2)
        
        factors = {'K': 1/1024, 'M': 1, 'G': 1024, 'T': 1024*1024}
        return val * factors.get(unit, 1)
    
    async def _process_download(self, data: Dict):
        """处理下载任务 (下载封面等资源)"""
        # 简化实现,实际可以下载封面图片
        logger.debug(f"Processing download task: {data.get('code')}")
    
    async def _wait_for_completion(self, timeout: int = 3600):
        """等待所有任务完成"""
        logger.info("Waiting for all tasks to complete...")
        
        start_time = datetime.now()
        
        while True:
            # 检查是否超时
            if (datetime.now() - start_time).total_seconds() > timeout:
                logger.warning("Timeout waiting for completion")
                break
            
            # 获取队列统计
            stats = self.pipeline.get_all_stats()
            
            # 检查是否所有队列都空闲
            all_idle = all(
                s.size == 0 and s.processing == 0
                for s in stats.values()
            )
            
            if all_idle:
                logger.info("All queues are idle")
                break
            
            # 更新进度
            progress = self.ws_manager.progress.get(
                next(iter(self.ws_manager.progress.keys()))
            )
            if progress:
                progress.update_progress(
                    completed=self.stats['completed_works'],
                    magnets=self.stats['completed_magnets']
                )
                await self.ws_manager.broadcast_progress(
                    progress.actress_id
                )
            
            # 等待后继续检查
            await asyncio.sleep(5)
    
    def get_pipeline_stats(self) -> Dict:
        """获取流水线统计信息"""
        return self.pipeline.get_summary()
    
    def get_anti_block_stats(self) -> Dict:
        """获取防屏蔽统计信息"""
        return self.anti_block.get_stats()


# 使用示例
async def example_usage():
    """使用示例"""
    from db import SessionLocal
    from websocket_manager import manager
    
    # 创建数据库会话
    db = SessionLocal()
    
    # 创建爬虫服务
    service = EnhancedCrawlService(
        db_session=db,
        ws_manager=manager,
        base_concurrency=4,
        proxies=[
            "http://proxy1.example.com:8080",
        ],
        base_urls=[
            "https://www.javbus.com",
        ]
    )
    
    try:
        # 启动服务
        await service.start()
        
        # 爬取女优
        result = await service.crawl_actress(
            actress_id=1,
            actress_name="三上悠亜",
            strategy="清晰度",
            mosaic="all",
            max_works=10
        )
        
        print(f"Crawl result: {result}")
        
        # 获取统计信息
        pipeline_stats = service.get_pipeline_stats()
        anti_block_stats = service.get_anti_block_stats()
        
        print(f"Pipeline stats: {pipeline_stats}")
        print(f"Anti-block stats: {anti_block_stats}")
        
    finally:
        # 停止服务
        await service.stop()
        db.close()


if __name__ == "__main__":
    asyncio.run(example_usage())
