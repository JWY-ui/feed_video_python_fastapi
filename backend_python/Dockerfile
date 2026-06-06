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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
