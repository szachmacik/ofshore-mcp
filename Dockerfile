FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir mcp[cli] httpx fastmcp
COPY src/server.py .
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "fastmcp", "run", "server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8080"]
