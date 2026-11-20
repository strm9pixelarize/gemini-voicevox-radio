FROM python:3.12-slim

# ffmpeg: MP3 化とジングル変換用。tzdata: TZ=Asia/Tokyo を効かせるため
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tzdata \
    && rm -rf /var/lib/apt/lists/*

# PyYAML: 曜日別の番組表 (schedule/*.yaml) を scheduler が読むため。
# プロジェクト唯一の外部依存 (2026-11-20 追加)
RUN pip install --no-cache-dir pyyaml

WORKDIR /app
COPY py/ /app/py/
COPY prompts/ /app/prompts/
COPY schedule/ /app/schedule/

CMD ["python", "/app/py/tools/run_scheduler.py"]
