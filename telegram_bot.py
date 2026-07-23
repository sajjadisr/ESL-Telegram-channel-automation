import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

def send_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    if len(text) > 4000:
        text = text[:4000] + "..."
    response = requests.post(url, data={
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
    })
    response.raise_for_status()
    return response.json()