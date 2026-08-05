# syntax=docker/dockerfile:1
# AI Secretary - 多阶段构建

# === 构建阶段 ===
FROM python:3.12-slim AS builder

WORKDIR /build

# 安装编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖到独立目录
COPY pyproject.toml .
COPY app/ app/
RUN pip install --no-cache-dir --user .

# === 运行阶段 ===
FROM python:3.12-slim

# 设置时区为上海
ENV TZ=Asia/Shanghai
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 创建非 root 用户
RUN groupadd -r appuser && useradd -r -g appuser appuser

# 从构建阶段复制依赖
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# 复制应用代码
COPY start_server.py .
COPY app/ app/
COPY config/ config/
COPY plugins/ plugins/

# 创建数据目录并设置权限
RUN mkdir -p data/chroma && \
    chown -R appuser:appuser /app /home/appuser

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["python", "start_server.py"]