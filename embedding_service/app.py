"""Sidecar de embedding LOCAL (Fase 2.B) — soberania do "saber".

Roda o modelo de embedding na CPU, isolado do backend (mem_limit próprio), sem
depender da OpenAI e sem tocar no host de produção com um LLM pesado. Modelo
MULTILÍNGUE (o conteúdo do ERP é PT-BR). Baixa 1x no build/primeiro uso.

POST /embed  {"texts": ["...", "..."]}  -> {"dim": 384, "vectors": [[...], ...]}
GET  /health -> {"ok": true, "model": "...", "dim": 384}
"""
import os

from fastapi import FastAPI
from pydantic import BaseModel

# Multilíngue (bom p/ português), 384 dims, leve (ONNX, sem torch/GPU).
MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

app = FastAPI(title="Conecta PRO — Embedding local (soberano)")
_model = None
_dim = 384


def _get_model():
    global _model, _dim
    if _model is None:
        from fastembed import TextEmbedding

        _model = TextEmbedding(model_name=MODEL_NAME)
        # descobre a dimensão real com uma amostra
        import numpy as np

        v = list(_model.embed(["dimensão"]))[0]
        _dim = int(len(v))
    return _model


class EmbedIn(BaseModel):
    texts: list[str]


@app.get("/health")
def health():
    try:
        _get_model()
        return {"ok": True, "model": MODEL_NAME, "dim": _dim}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "erro": str(e)[:200]}


@app.post("/embed")
def embed(body: EmbedIn):
    m = _get_model()
    vecs = [list(map(float, v)) for v in m.embed(body.texts or [])]
    return {"dim": _dim, "vectors": vecs, "model": MODEL_NAME}
