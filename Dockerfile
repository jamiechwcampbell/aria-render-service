FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.source="https://github.com/jamiechwcampbell/aria-render-service"
ENV HF_HOME=/opt/kokoro-cache TTS_THREADS=4 PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fontconfig libsndfile1 libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /data/render-service
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm
# Cache weights/config/voices where a /data mount cannot hide them.
COPY scripts/preload_kokoro.py scripts/preload_kokoro.py
RUN python scripts/preload_kokoro.py
COPY app app
COPY fonts fonts
COPY library library
COPY handler.py ./
COPY scripts/check_image.py scripts/check_image.py
RUN mkdir -p /usr/local/share/fonts/poppins \
    && cp fonts/Poppins-ExtraBold.ttf /usr/local/share/fonts/poppins/ \
    && fc-cache -f
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
# A missing model or language dependency must fail CI, not download at startup.
RUN python scripts/check_image.py
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
