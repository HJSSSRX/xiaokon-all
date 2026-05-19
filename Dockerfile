FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tools/ ./tools/
COPY prompts/ ./prompts/
COPY config/ ./config/

EXPOSE 8765

CMD ["python", "tools/collab_hub.py", "serve", "/app/cases/default", "--port", "8765", "--bind", "0.0.0.0"]