FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /data/render-service
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir -r requirements.txt
COPY app app
COPY fonts fonts
COPY library library
COPY handler.py start.sh ./
ENV HF_HOME=/data/cache TTS_THREADS=4
EXPOSE 8000
CMD ["python", "-u", "handler.py"]
