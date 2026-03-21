"""
JavSpider Stack - Windows 一键启动脚本
用法: python start.py
或直接双击此文件运行
"""
import subprocess
import sys
import os
import shutil
import time
import socket

def find_free_port(start=8088):
    """查找可用端口"""
    for port in range(start, start + 100):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(('', port))
            s.close()
            return port
        except OSError:
            continue
    return start

def check_python():
    """检查 Python 版本"""
    ver = sys.version_info
    if ver.major < 3 or (ver.major == 3 and ver.minor < 10):
        print(f"[ERROR] 需要 Python 3.10+，当前版本: {ver.major}.{ver.minor}")
        print("下载地址: https://www.python.org/downloads/")
        return False
    print(f"[OK] Python {ver.major}.{ver.minor}.{ver.micro}")
    return True

def get_venv():
    """获取虚拟环境路径"""
    if os.path.isdir(".venv"):
        return ".venv"
    if os.path.isdir(".venv_v2"):
        return ".venv_v2"
    return None

def create_venv(venv_path):
    """创建虚拟环境"""
    print("[BUILD] 创建虚拟环境 ...")
    subprocess.run([sys.executable, "-m", "venv", venv_path], check=True)
    print("[OK] 虚拟环境创建完成")

def install_deps(venv_python):
    """安装依赖"""
    print("[INSTALL] 安装依赖（首次较慢）...")
    pip = os.path.join(os.path.dirname(venv_python), "pip.exe")
    subprocess.run([pip, "install", "-q", "--upgrade", "pip"], check=True)
    subprocess.run([pip, "install", "-q", "-r", "requirements.txt"], check=True)
    print("[OK] 依赖安装完成")

def init_db(venv_python):
    """初始化数据库"""
    print("[DB] 初始化数据库 ...")
    result = subprocess.run(
        [venv_python, "-c", "from db import init_db; init_db(); print('[OK] 数据库就绪')"],
        capture_output=True, text=True
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("[ERROR]", result.stderr.strip())

def get_local_ip():
    """获取局域网 IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    print("=" * 40)
    print("  JavSpider Stack")
    print("=" * 40)
    print()

    # 1. 检查 Python
    if not check_python():
        input("\n按回车退出...")
        return

    # 2. 找或创建虚拟环境
    venv = get_venv()
    if not venv:
        venv = ".venv"
        create_venv(venv)

    venv_python = os.path.join(venv, "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        print(f"[ERROR] 找不到 Python: {venv_python}")
        input("\n按回车退出...")
        return

    # 3. 安装依赖
    install_deps(venv_python)

    # 4. 初始化数据库
    init_db(venv_python)

    # 5. 找可用端口
    port = find_free_port(8088)
    local_ip = get_local_ip()

    # 6. 启动服务
    print()
    print("=" * 40)
    print(f"  启动服务中 ...")
    print()
    print(f"  本机访问: http://localhost:{port}")
    print(f"  局域网:   http://{local_ip}:{port}")
    print()
    print("  按 Ctrl+C 停止服务")
    print("=" * 40)

    # 切换到脚本所在目录
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 启动 uvicorn
    server_cmd = [
        venv_python, "-m", "uvicorn",
        "api.main:app",
        "--host", "0.0.0.0",
        "--port", str(port),
        "--reload"
    ]
    try:
        subprocess.run(server_cmd)
    except KeyboardInterrupt:
        print("\n[INFO] 服务已停止")

if __name__ == "__main__":
    main()
