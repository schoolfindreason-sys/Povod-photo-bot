# Povod Photo Bot

Telegram bot for editing product/bouquet photos through ProxyAPI.

## Render settings

Build command:
`pip install -r requirements.txt`

Start command:
`uvicorn main:web --host 0.0.0.0 --port $PORT`

Environment variables:
- `TELEGRAM_BOT_TOKEN`
- `PROXYAPI_KEY`

Optional:
- `IMAGE_MODEL` (default: `openai/gpt-image-1`)
- `IMAGE_QUALITY` (default: `medium`)
- `IMAGE_SIZE` (default: `1024x1536`)

Do not commit API keys or Telegram tokens to GitHub.
