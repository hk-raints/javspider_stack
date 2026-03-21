/**
 * JavSpider Stack - 前端应用
 * 包含实时进度、搜索筛选、分页等功能
 */

// ==================== WebSocket 实时进度 ====================

class CrawlProgressMonitor {
    constructor(actressId, actressName) {
        this.actressId = actressId;
        this.actressName = actressName;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.isConnected = false;
        this.heartbeatInterval = null;
    }

    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/crawl/${this.actressId}`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.startHeartbeat();
            this.showProgressPanel();
        };
        
        this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };
        
        this.ws.onclose = () => {
            console.log('WebSocket closed');
            this.isConnected = false;
            this.stopHeartbeat();
            this.attemptReconnect();
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    startHeartbeat() {
        this.heartbeatInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send('ping');
            }
        }, 30000); // 30秒心跳
    }

    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Reconnecting... attempt ${this.reconnectAttempts}`);
            setTimeout(() => this.connect(), 3000);
        }
    }

    handleMessage(message) {
        if (message.type === 'progress') {
            this.updateProgressUI(message.data);
        }
    }

    showProgressPanel() {
        const panel = document.getElementById('progress-panel');
        if (panel) {
            panel.style.display = 'block';
        }
    }

    updateProgressUI(data) {
        // 更新进度条
        const progressBar = document.getElementById('progress-bar');
        const progressText = document.getElementById('progress-text');
        const statusText = document.getElementById('crawl-status');
        
        if (progressBar) {
            progressBar.style.width = `${data.progress_percent}%`;
        }
        
        if (progressText) {
            progressText.textContent = `${data.completed_works} / ${data.total_works} 作品`;
        }
        
        if (statusText) {
            const statusMap = {
                'starting': '启动中...',
                'running': '抓取中...',
                'completed': '已完成',
                'error': '出错'
            };
            statusText.textContent = statusMap[data.status] || data.status;
            statusText.className = `status-${data.status}`;
        }
        
        // 更新统计
        const worksCount = document.getElementById('works-count');
        const magnetsCount = document.getElementById('magnets-count');
        const elapsedTime = document.getElementById('elapsed-time');
        
        if (worksCount) worksCount.textContent = data.completed_works;
        if (magnetsCount) magnetsCount.textContent = data.total_magnets;
        if (elapsedTime) elapsedTime.textContent = this.formatTime(data.elapsed_seconds);
        
        // 更新日志
        this.updateLogUI(data.logs);
        
        // 完成时显示通知
        if (data.status === 'completed') {
            this.showNotification('抓取完成', `${this.actressName} 的作品抓取已完成！`);
            this.disconnect();
        }
        
        // 出错时
        if (data.status === 'error') {
            this.showNotification('抓取失败', data.error || '未知错误', 'error');
        }
    }

    updateLogUI(logs) {
        const logContainer = document.getElementById('log-container');
        if (!logContainer || !logs) return;
        
        logContainer.innerHTML = logs.map(log => `
            <div class="log-entry log-${log.level}">
                <span class="log-time">${log.time}</span>
                <span class="log-message">${this.escapeHtml(log.message)}</span>
            </div>
        `).join('');
        
        // 自动滚动到底部
        logContainer.scrollTop = logContainer.scrollHeight;
    }

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showNotification(title, body, type = 'success') {
        // 浏览器通知
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification(title, {
                body: body,
                icon: '/static/favicon.ico'
            });
        }
        
        // 页面内通知
        this.showToast(title, body, type);
    }

    showToast(title, message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        `;
        
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }
        
        container.appendChild(toast);
        
        // 动画显示
        setTimeout(() => toast.classList.add('show'), 10);
        
        // 3秒后移除
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }

    disconnect() {
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close();
        }
    }
}

// ==================== 作品搜索和筛选 ====================

class WorksManager {
    constructor(actressId) {
        this.actressId = actressId;
        this.currentPage = 1;
        this.perPage = 20;
        this.totalPages = 1;
        this.filters = {
            search: '',
            date_from: '',
            date_to: '',
            has_magnet: null,
            resolution: '',
            sort_by: 'date',
            sort_order: 'desc'
        };
    }

    async loadWorks() {
        const params = new URLSearchParams({
            page: this.currentPage,
            per_page: this.perPage,
            sort_by: this.filters.sort_by,
            sort_order: this.filters.sort_order
        });
        
        if (this.filters.search) params.append('search', this.filters.search);
        if (this.filters.date_from) params.append('date_from', this.filters.date_from);
        if (this.filters.date_to) params.append('date_to', this.filters.date_to);
        if (this.filters.has_magnet !== null) params.append('has_magnet', this.filters.has_magnet);
        if (this.filters.resolution) params.append('resolution', this.filters.resolution);
        
        try {
            const response = await fetch(`/api/actress/${this.actressId}/works?${params}`);
            const data = await response.json();
            
            this.totalPages = data.total_pages;
            this.renderWorks(data.works);
            this.renderPagination(data.total, data.page, data.per_page);
            this.updateResultCount(data.total);
        } catch (error) {
            console.error('Failed to load works:', error);
        }
    }

    renderWorks(works) {
        const container = document.getElementById('works-table-body');
        if (!container) return;
        
        if (works.length === 0) {
            container.innerHTML = '<tr><td colspan="7" class="no-data">暂无数据</td></tr>';
            return;
        }
        
        container.innerHTML = works.map(work => `
            <tr>
                <td>${work.code}</td>
                <td>${work.title}</td>
                <td>${work.date || '-'}</td>
                <td>
                    ${work.best_magnet ? `
                        <input type="text" value="${work.best_magnet.url}" readonly 
                               style="width: 360px;" onclick="this.select();document.execCommand('copy');"/>
                    ` : '—'}
                </td>
                <td>${work.best_magnet ? work.best_magnet.score : ''}</td>
                <td>${work.best_magnet ? work.best_magnet.resolution : ''}</td>
                <td>${work.best_magnet ? Math.round(work.best_magnet.size_mb) : ''}</td>
            </tr>
        `).join('');
    }

    renderPagination(total, currentPage, perPage) {
        const container = document.getElementById('pagination');
        if (!container) return;
        
        const totalPages = Math.ceil(total / perPage);
        if (totalPages <= 1) {
            container.innerHTML = '';
            return;
        }
        
        let html = '';
        
        // 上一页
        html += `<button ${currentPage === 1 ? 'disabled' : ''} onclick="worksManager.goToPage(${currentPage - 1})">上一页</button>`;
        
        // 页码
        const maxButtons = 5;
        let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
        let endPage = Math.min(totalPages, startPage + maxButtons - 1);
        
        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }
        
        if (startPage > 1) {
            html += `<button onclick="worksManager.goToPage(1)">1</button>`;
            if (startPage > 2) html += `<span>...</span>`;
        }
        
        for (let i = startPage; i <= endPage; i++) {
            html += `<button class="${i === currentPage ? 'active' : ''}" onclick="worksManager.goToPage(${i})">${i}</button>`;
        }
        
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) html += `<span>...</span>`;
            html += `<button onclick="worksManager.goToPage(${totalPages})">${totalPages}</button>`;
        }
        
        // 下一页
        html += `<button ${currentPage === totalPages ? 'disabled' : ''} onclick="worksManager.goToPage(${currentPage + 1})">下一页</button>`;
        
        // 页码信息
        html += `<span class="page-info">${currentPage} / ${totalPages} 页 (共 ${total} 条)</span>`;
        
        container.innerHTML = html;
    }

    updateResultCount(total) {
        const el = document.getElementById('result-count');
        if (el) el.textContent = `共 ${total} 个作品`;
    }

    goToPage(page) {
        this.currentPage = page;
        this.loadWorks();
    }

    setFilter(key, value) {
        this.filters[key] = value;
        this.currentPage = 1; // 重置到第一页
        this.loadWorks();
    }

    toggleSort(field) {
        if (this.filters.sort_by === field) {
            this.filters.sort_order = this.filters.sort_order === 'asc' ? 'desc' : 'asc';
        } else {
            this.filters.sort_by = field;
            this.filters.sort_order = 'desc';
        }
        this.loadWorks();
        this.updateSortUI();
    }

    updateSortUI() {
        document.querySelectorAll('.sortable').forEach(el => {
            el.classList.remove('sort-asc', 'sort-desc');
            if (el.dataset.sort === this.filters.sort_by) {
                el.classList.add(`sort-${this.filters.sort_order}`);
            }
        });
    }
}

// ==================== 全局函数 ====================

// 请求浏览器通知权限
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
}

// 启动爬虫并监控进度
async function startCrawlWithProgress(actressId, actressName, form) {
    const formData = new FormData(form);
    const button = form.querySelector('button[type="submit"]');
    const originalText = button.textContent;
    
    button.disabled = true;
    button.textContent = '启动中...';
    
    try {
        // 请求通知权限
        requestNotificationPermission();
        
        // 启动爬虫
        const response = await fetch(form.action, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.ok) {
            // 连接 WebSocket 监控进度
            window.crawlMonitor = new CrawlProgressMonitor(actressId, actressName);
            window.crawlMonitor.connect();
            
            button.textContent = '抓取中...';
        } else {
            alert('启动失败: ' + data.msg);
            button.disabled = false;
            button.textContent = originalText;
        }
    } catch (error) {
        alert('请求失败: ' + error.message);
        button.disabled = false;
        button.textContent = originalText;
    }
}

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    requestNotificationPermission();
});
