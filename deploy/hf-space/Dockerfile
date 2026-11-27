# The nightly API on a Hugging Face Docker Space (free CPU). Built from the repo root:
#   docker build -f deploy/hf-space/Dockerfile .
# The deploy workflow uploads this file, api/ and worker/ to the Space, which builds it.
FROM python:3.11-slim

# Spaces run the container as uid 1000.
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

# Dependencies first, so code changes reuse this layer. CPU-only torch (see requirements-embed).
COPY --chown=user api/requirements.txt api/requirements-models.txt api/
COPY --chown=user worker/requirements.txt worker/requirements-embed.txt worker/
RUN pip install -r api/requirements-models.txt

USER user
# Bake both models into the image so a cold start does not download them.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5', device='cpu'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2', device='cpu')"

COPY --chown=user api/ api/
COPY --chown=user worker/ worker/

EXPOSE 7860
CMD ["uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "7860"]
