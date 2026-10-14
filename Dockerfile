FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/usr/local/bin:/root/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    bash \
    tar \
    gzip \
    ffmpeg \
    imagemagick \
    fonts-dejavu-core \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-ron \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- -d /usr/local/bin || true
RUN if [ ! -f /usr/local/bin/agy ] && [ -f /root/.local/bin/agy ]; then cp /root/.local/bin/agy /usr/local/bin/agy; fi || true
RUN chmod +x /usr/local/bin/agy 2>/dev/null || true

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
RUN mkdir -p /app/media /app/saved_memes

EXPOSE 10000

CMD ["python3", "keep_alive.py"]
