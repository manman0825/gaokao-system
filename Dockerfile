FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080  # 改为云托管要求的8080端口
CMD ["gunicorn", "main:app", "-b", "0.0.0.0:8080"]  # 修正参数格式+改端口