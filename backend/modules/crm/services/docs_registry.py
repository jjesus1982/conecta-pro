"""
Registro de documentos gerados (crm_documents) + link público tokenizado de download.
Usado por todos os geradores (proposta, contrato, relatório, recibo, OS, aditivo, atestado) para
PERSISTIR o PDF e devolver uma URL clicável (Cowork/navegador).
"""

from __future__ import annotations

import os
import secrets
import uuid

from sqlalchemy import text

PUBLIC_ERP = os.getenv("PUBLIC_ERP_URL", "https://erp.conectamais.pro").rstrip("/")
DOCS_DIR = "/app/uploads/docs"


async def salvar_pdf(
    db,
    tipo: str,
    titulo: str,
    pdf_bytes: bytes,
    *,
    ref_tipo: str | None = None,
    ref_id: str | None = None,
    teste: bool = False,
) -> dict:
    did = str(uuid.uuid4())
    token = secrets.token_urlsafe(18)
    os.makedirs(DOCS_DIR, exist_ok=True)
    path = f"{DOCS_DIR}/{did}.pdf"
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    kb = round(len(pdf_bytes) / 1024, 1)
    await db.execute(
        text("""
        INSERT INTO crm_documents (id, tipo, titulo, arquivo, token, ref_tipo, ref_id, tamanho_kb, teste, created_at)
        VALUES (:id, :tipo, :titulo, :arq, :tok, :rt, :ri, :kb, :teste, now())
    """),
        {
            "id": did,
            "tipo": tipo,
            "titulo": (titulo or "")[:255],
            "arq": path,
            "tok": token,
            "rt": ref_tipo,
            "ri": ref_id,
            "kb": kb,
            "teste": teste,
        },
    )
    await db.commit()
    return {
        "id": did,
        "tipo": tipo,
        "titulo": titulo,
        "tamanho_kb": kb,
        "download_url": f"{PUBLIC_ERP}/api/v1/crm/docs/download/{did}?t={token}",
    }
