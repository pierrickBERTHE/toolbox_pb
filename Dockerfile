# Image Linux contenant Python, FFmpeg et la toolbox.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# FFmpeg fournit egalement FFprobe, utilise par les traitements video et image.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installer les dependances avant le code optimise le cache de construction.
COPY pyproject.toml README.md ./
COPY toolbox_pb ./toolbox_pb
RUN pip install .

# Les dossiers sont aussi montes depuis Windows par docker-compose.yml.
RUN mkdir -p /app/data/input /app/data/output /app/data/segment /app/log

CMD ["python", "toolbox_pb/main.py"]
