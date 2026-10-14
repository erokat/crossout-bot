FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/root/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    bash \
    ffmpeg \
    imagemagick \
    fonts-dejavu-core \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://antigravity.google/cli/install.sh | bash || true

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/
RUN mkdir -p /app/media /app/saved_memes

EXPOSE 10000

CMD ["python3", "keep_alive.py"]
