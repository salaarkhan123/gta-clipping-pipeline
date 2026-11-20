# Debian 13 (trixie), named rather than the moving `slim` tag: its ffmpeg 7.1 is the one production renders with.
# ci/local-ci.sh runs the tests on the same base, so CI renders with the same ffmpeg (tests/test_render_equivalence.py).
FROM python:3.12-slim-trixie

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/opt/hf FASTEMBED_CACHE_PATH=/opt/fastembed

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && ffmpeg -version | head -1 | grep -q '^ffmpeg version 7\.1\.' \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

# Bake every model into the image so workers never download at runtime, and a bad model name fails the build.
ARG WHISPER_MODEL=small.en
ARG WHISPER_INDEX_MODEL=base.en
RUN python -c "from faster_whisper import WhisperModel; [WhisperModel(m, device='cpu', compute_type='int8') for m in ('${WHISPER_MODEL}', '${WHISPER_INDEX_MODEL}')]" \
    && python -c "from fastembed import ImageEmbedding, TextEmbedding; ImageEmbedding('Qdrant/clip-ViT-B-32-vision'); TextEmbedding('Qdrant/clip-ViT-B-32-text')" \
    && chmod -R a+rwX /opt/hf /opt/fastembed

COPY app ./app
COPY scripts ./scripts
# Poster and preview assets for GET /v1/templates/<id>/poster (app/templates.py ASSETS).
COPY templates ./templates

RUN chmod -R a+rX /srv/app /srv/scripts /srv/templates \
    && useradd --create-home app && mkdir -p /srv/data && chown -R app:app /srv/data
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
