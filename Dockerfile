# 用于 HuggingFace Spaces（Docker 模式）
# Spaces 会在运行时把端口注入到环境变量 PORT（默认 7860），server.py 已支持。
FROM python:3.11-slim

WORKDIR /app
COPY . .

# 仅作兜底；运行时 Spaces 注入的 PORT 会覆盖它
ENV PORT=7860

EXPOSE 7860

CMD ["python", "server.py"]
