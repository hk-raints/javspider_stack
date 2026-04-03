"""
JavSpider Stack - 一键启动脚本 (支持 Win/Mac/Linux)
用法: python start.py
"""
import subprocess
import sys
import os
import socket
import platform

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
        return False
    print(f"[OK] Python {ver.major}.{ver.minor}.{ver.micro}")
    return True

def get_venv_python():
    """获取虚拟环境中的 python 路径"""
    is_win = platform.system() == "Windows"
    for venv_name in [".venv", ".venv_v2"]:
        if is_win:
            p = os.path.join(venv_name, "Scripts", "python.exe")
        else:
            p = os.path.join(venv_name, "bin", "python")
        if os.path.exists(p):
            return p
    return sys.executable # 找不到则使用当前 python

def upgrade_db(venv_python):
    """使用 Alembic 升级数据库"""
    print("[DB] 正在升级数据库结构 (Alembic) ...")
    try:
        subprocess.run([venv_python, "-m", "alembic", "upgrade", "head"], check=True)
        print("[OK] 数据库已是最新版本")
    except Exception as e:
        print(f"[WARNING] 数据库升级失败 (可能尚未初始化): {e}")

def main():
    print("=" * 40)
    print("  JavSpider Stack v2.1")
    print("=" * 40)

    if not check_python():
        return

    venv_python = get_venv_python()
    print(f"[INFO] 使用 Python: {venv_python}")

    # 1. 升级数据库
    upgrade_db(venv_python)

    # 2. 找可用端口
    port = find_free_port(8088)

    # 3. 启动服务
    print()
    print("=" * 40)
    print(f"  启动服务中 ...")
    print(f"  访问地址: http://localhost:{port}")
    print("  按 Ctrl+C 停止服务")
    print("=" * 40)

    # 启动 uvicorn
    # 注意：现在使用 app.main:app
    server_cmd = [
        venv_python, "-m", "uvicorn",
        "app.main:app",
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
