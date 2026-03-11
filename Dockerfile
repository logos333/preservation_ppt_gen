FROM python:3.12-slim

LABEL org.opencontainers.image.source=https://github.com/logos333/preservation_ppt_gen

WORKDIR /app

# Зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Исходный код и шаблон
COPY *.py .
COPY template.pptx .

# Папка для фотографий (volume mount рекомендуется)
RUN mkdir -p photos

CMD ["python", "main.py"]
