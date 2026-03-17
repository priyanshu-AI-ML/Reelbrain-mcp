FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data

# System deps: ffmpeg for audio processing by yt-dlp/whisper
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download faster-whisper model so first request is fast
ARG WHISPER_MODEL=small
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')" || true

COPY server.py analyzer.py memory.py watcher.py entrypoint.sh ./

RUN chmod +x entrypoint.sh


# Railway sets $PORT automatically
EXPOSE 8000

# Non-root user
RUN useradd -m -u 1000 mcpuser && chown -R mcpuser:mcpuser /app
RUN mkdir -p /data && chown mcpuser:mcpuser /data
USER mcpuser

CMD ["./entrypoint.sh"]
