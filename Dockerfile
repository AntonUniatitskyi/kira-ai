FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y docker.io && \
    apt-get install -y nmap && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY sql ./sql

CMD ["python", "-m", "bot.main"]
