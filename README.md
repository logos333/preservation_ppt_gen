# Preservation PPT Generator

Telegram bot that receives pressure gauge photos, identifies equipment tags via LLM vision, and auto-generates PowerPoint preservation reports.

## Features

- **Photo intake** — Send photos to the bot via Telegram, with or without captions
- **LLM OCR** — Automatically reads yellow equipment tags using vision LLMs (Gemini, OpenAI, Claude) via [LiteLLM](https://github.com/BerriAI/litellm)
- **Presentation generation** — Creates `.pptx` from a template with smart image grid layout (max 3/row, 2 rows/page, auto-pagination)
- **Access control** — Whitelist middleware restricts bot to authorized chat IDs

## Bot Commands

| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/time` | Current date and time |
| `/makeppt` | Process photos with LLM and generate presentation |
| `/cleardata` | Delete all photos |
| `/get_llm_model` | Show active LLM model |

## Setup

### 1. Configure `.env`

```env
BOT_TOKEN=your-telegram-bot-token
USE_WEBHOOK=false
WEBHOOK_URL=https://your-domain.com/webhook
WEBHOOK_PORT=8080

LLM_MODEL=gemini/gemini-2.5-flash
GEMINI_API_KEY=your-key
```

### 2. Install & Run

```bash
pip install -r requirements.txt
python main.py
```

### 3. Docker

```bash
docker build -t preservation-ppt .
docker run --env-file .env -v ./photos:/app/photos preservation-ppt
```

## Project Structure

```
├── main.py          # Bot entry point (polling/webhook)
├── bot.py           # Telegram handlers and commands
├── llm_ocr.py       # LLM vision — tag extraction and photo renaming
├── ppt_gen.py       # PowerPoint generation from template
├── template.pptx    # Presentation template
├── Dockerfile
└── requirements.txt
```
