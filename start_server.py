"""AI Secretary 启动入口

使用方式：
    python start_server.py
    # 或直接运行
    python -m app.main
"""

import os
import sys

# 确保项目根目录在路径中
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    from app.common.config import init_config

    config = init_config()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
    )