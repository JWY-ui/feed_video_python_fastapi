# FastAPI 应用镜像
FROM python:3.12-slim

WORKDIR /app

# 先复制依赖文件（利用 Docker 缓存层）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 再复制项目代码
COPY . .

# 创建上传目录
RUN mkdir -p uploads/avatars uploads/videos uploads/covers uploads/tmp

EXPOSE 8080

# --proxy-headers: without it every request behind the reverse proxy looks like
#   it came from the proxy's IP, and the per-IP rate limiter becomes one global
#   bucket. --forwarded-allow-ips trusts the proxy (the port is bound to
#   127.0.0.1 in compose, so the backend is not directly reachable).
# --workers: in-process state was moved to Redis (upload sessions, notification
#   bus, agent session locks), so more than one worker is now safe. Default 1
#   to keep a small server's memory footprint down; raise WEB_CONCURRENCY when
#   needed.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS:-*} --workers ${WEB_CONCURRENCY:-1}"]
