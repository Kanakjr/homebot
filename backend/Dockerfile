FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8321

# Run Telegram bot in background and API in foreground (dashboard + cloudflared use :8321)
CMD ["sh", "-c", "python -u main.py & exec python -u api.py"]
