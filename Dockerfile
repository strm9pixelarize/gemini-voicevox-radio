FROM python:3.12-slim

# ffmpeg: MP3 化とジングル変換用。tzdata: TZ=Asia/Tokyo を効かせるため
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY py/ /app/py/

CMD ["python", "/app/py/tools/run_scheduler.py"]
