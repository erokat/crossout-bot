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
    unzip \
    ffmpeg \
    imagemagick \
    fonts-dejavu-core \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    tesseract-ocr-ron \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deno.land/install.sh | sh -s -- -y && \
    if [ -f /root/.deno/bin/deno ]; then cp /root/.deno/bin/deno /usr/local/bin/deno && chmod +x /usr/local/bin/deno; fi || true

RUN curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- -d /usr/local/bin || true
RUN if [ ! -f /usr/local/bin/agy ] && [ -f /root/.local/bin/agy ]; then cp /root/.local/bin/agy /usr/local/bin/agy; fi || true
RUN chmod +x /usr/local/bin/agy 2>/dev/null || true

WORKDIR /app

COPY requirements.txt /app/
RUN python -m pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
RUN mkdir -p /app/media /app/saved_memes /app/extensions

EXPOSE 10000

CMD ["python3", "keep_alive.py"]
