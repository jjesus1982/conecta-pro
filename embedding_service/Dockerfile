# Sidecar de embedding local (Fase 2.B) — CPU, ONNX (fastembed), isolado.
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Pré-baixa o modelo no BUILD (evita download no 1º request + falha de permissão runtime).
ENV EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

EXPOSE 8900
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8900", "--workers", "1"]
