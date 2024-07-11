# 使用官方 Python 映像作為基礎映像
FROM python:3.12

# 設置工作目錄
WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    ffmpeg \
    vim \
    sqlite3 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install git+https://github.com/BenHsu501/CopyCraftAPI.git

COPY . .

