# 使用官方 Python 3.12 镜像作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（如：sqlite3, 浏览器依赖）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    sqlite3 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装 Python 库
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安装 Playwright 浏览器（如需使用浏览器爬虫）
RUN playwright install chromium --with-deps

# 复制项目文件
COPY . .

# 创建数据存储目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8088

# 启动应用
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8088"]
