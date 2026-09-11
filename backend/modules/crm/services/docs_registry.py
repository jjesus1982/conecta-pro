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
# Pasta padrão no Google Drive do Jordan (documentos gerados pelo Conecta PRO).
GDRIVE_DOCS_FOLDER = os.getenv("GDRIVE_DOCS_FOLDER", "1wrgjMheUh0uC_LM9yPGb48iQ_TVmvYn7")


def _slug_arquivo(titulo: str, ext: str = "pdf") -> str:
    import re

    base = re.sub(r"[^\w\s.-]", "", (titulo or "documento")).strip().replace(" ", "_")[:80]
    return f"{base or 'documento'}.{ext}"


async def salvar_pdf(
    db,
    tipo: str,
    titulo: str,
    pdf_bytes: bytes,
    *,
    ref_tipo: str | None = None,
    ref_id: str | None = None,
    teste: bool = False,
    drive: bool = False,
    drive_folder: str | None = None,
    filename: str | None = None,
) -> dict:
    did = str(uuid.uuid4())
    # token_urlsafe usa base64url, que inclui "_" e "-". Link colado em chat que renderiza
    # markdown perde "__" no fim (vira marcador de ênfase) e o download dá 404 — aconteceu
    # com o contrato CTR-2026-00019 em 19/08/2026. token_hex usa só [0-9a-f]: sobrevive a
    # markdown, a quebra de linha e a cópia manual. 32 hex = 128 bits, mais entropia que os
    # 18 bytes anteriores em termos de espaço de busca prático.
    token = secrets.token_hex(16)
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
    resultado = {
        "id": did,
        "tipo": tipo,
        "titulo": titulo,
        "tamanho_kb": kb,
        "download_url": f"{PUBLIC_ERP}/api/v1/crm/docs/download/{did}?t={token}",
    }
    if drive:
        try:
            from modules.gdrive.services.gdrive_service import GDriveService

            svc = GDriveService()
            if svc.esta_conectado():  # inicializa o _service (obrigatório antes do upload)
                up = svc.fazer_upload_arquivo(
                    path, drive_folder or GDRIVE_DOCS_FOLDER,
                    file_name=filename or _slug_arquivo(titulo, "pdf"),
                )
                if up and up.get("webViewLink"):
                    resultado["drive_url"] = up["webViewLink"]
                else:
                    resultado["drive_erro"] = "upload não retornou link"
            else:
                resultado["drive_erro"] = "Google Drive não conectado (autorize em Integrações)"
        except Exception as exc:  # noqa: BLE001 — Drive é best-effort; download_url sempre volta
            resultado["drive_erro"] = str(exc)[:150]
    return resultado


# ── Entrada de documentos (upload/anexo) ──────────────────────────────────────────────
# Item 2.2 do relatório de campo do Jordan (11/09/2026). O registro morava no ERP e o
# ARTEFATO morava fora: contrato final em .docx, planilha aberta de custo, deck, parecer
# jurídico do cliente. Resultado — versões soltas em pasta local e risco real de assinar a
# errada (existiam duas versões do deck do The Sun na mesma pasta).
#
# `salvar_pdf` cobre o que o sistema GERA. Isto cobre o que ENTRA.

# Extensões aceitas → mime. Lista fechada de propósito: anexo é arquivo que vai para o
# registro de um cliente, não um depósito genérico.
EXT_ACEITAS = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "txt": "text/plain", "csv": "text/csv", "xml": "application/xml",
}
ENTIDADES = {"contrato", "cliente", "proposta", "oportunidade", "os", "visita", "lead"}
CATEGORIAS = {"contrato_assinado", "minuta", "proposta", "planilha", "parecer",
              "apresentacao", "anexo"}


async def anexar_documento(db, *, entidade: str, entidade_id: str, nome: str,
                           conteudo_b64: str, categoria: str = "anexo",
                           descricao: str = "") -> dict:
    """Guarda um arquivo VINDO DE FORA no registro da entidade. Devolve id, token e versão.

    ⚠️ NUNCA sobrescreve. Mesmo `nome` + `categoria` na mesma entidade vira **v2**, e o
    retorno diz qual versão é. Sobrescrever anexo é perder a prova de qual documento o
    cliente assinou — e é exatamente o risco que este item veio resolver.

    A versão NÃO é coluna nova: é a posição do arquivo entre os seus homônimos, por data.
    Contar em vez de guardar evita migration e não pode dessincronizar do que está lá.
    """
    import base64


    ent = (entidade or "").strip().lower()
    if ent not in ENTIDADES:
        raise ValueError(f"entidade inválida: {entidade!r}. Use uma de {sorted(ENTIDADES)}.")
    cat = (categoria or "anexo").strip().lower()
    if cat not in CATEGORIAS:
        raise ValueError(f"categoria inválida: {categoria!r}. Use uma de {sorted(CATEGORIAS)}.")
    nome = (nome or "").strip()
    ext = (nome.rsplit(".", 1)[-1] if "." in nome else "").lower()
    if ext not in EXT_ACEITAS:
        raise ValueError(
            f"extensão {ext!r} não aceita. Aceitas: {sorted(EXT_ACEITAS)}. "
            "O nome do arquivo precisa terminar na extensão (ex.: contrato.docx).")
    try:
        conteudo = base64.b64decode(conteudo_b64 or "", validate=True)
    except Exception as e:  # noqa: BLE001
        raise ValueError("conteudo_b64 não é base64 válido.") from e
    if not conteudo:
        raise ValueError("arquivo vazio.")
    if len(conteudo) > 25 * 1024 * 1024:
        raise ValueError(f"arquivo de {len(conteudo) // 1024 // 1024} MB — o limite é 25 MB.")

    did = str(uuid.uuid4())
    token = secrets.token_hex(16)
    os.makedirs(DOCS_DIR, exist_ok=True)
    path = f"{DOCS_DIR}/{did}.{ext}"
    with open(path, "wb") as fh:
        fh.write(conteudo)

    versao = (await db.execute(text(
        "SELECT count(*) + 1 FROM crm_documents "
        " WHERE ref_tipo = :rt AND ref_id = :ri AND tipo = :t AND titulo = :n "
        "   AND coalesce(arquivado, false) = false"),
        {"rt": ent, "ri": str(entidade_id), "t": cat, "n": nome[:255]})).scalar() or 1

    await db.execute(text("""
        INSERT INTO crm_documents
            (id, tipo, titulo, descricao, arquivo, token, ref_tipo, ref_id, tamanho_kb,
             teste, created_at)
        VALUES (:id, :t, :n, :d, :arq, :tok, :rt, :ri, :kb, false, now())"""),
        {"id": did, "t": cat, "n": nome[:255],
         "d": (descricao or "")[:500] + (f" · v{versao}" if versao > 1 else ""),
         "arq": path, "tok": token, "rt": ent, "ri": str(entidade_id),
         "kb": round(len(conteudo) / 1024, 1)})
    await db.commit()
    return {"ok": True, "id": did, "versao": versao, "nome": nome,
            "mime": EXT_ACEITAS[ext], "tamanho_kb": round(len(conteudo) / 1024, 1),
            "entidade": ent, "entidade_id": str(entidade_id), "categoria": cat,
            "download_url": f"{PUBLIC_ERP}/api/v1/crm/docs/download/{did}?t={token}"}


async def listar_da_entidade(db, *, entidade: str, entidade_id: str) -> dict:
    """Tudo que está pendurado numa entidade — gerado pelo sistema E anexado de fora."""
    rs = (await db.execute(text("""
        SELECT id::text, tipo, titulo, coalesce(descricao,'') AS descricao, token,
               coalesce(tamanho_kb,0) AS kb, created_at,
               row_number() OVER (PARTITION BY tipo, titulo ORDER BY created_at) AS versao
          FROM crm_documents
         WHERE ref_tipo = :rt AND ref_id = :ri AND coalesce(arquivado,false) = false
         ORDER BY created_at DESC"""),
        {"rt": (entidade or "").strip().lower(), "ri": str(entidade_id)})).mappings().all()
    return {"ok": True, "total": len(rs), "documentos": [
        {"id": r["id"], "categoria": r["tipo"], "nome": r["titulo"], "versao": r["versao"],
         "tamanho_kb": float(r["kb"]), "descricao": r["descricao"],
         "criado_em": r["created_at"].isoformat() if r["created_at"] else None,
         "download_url": f"{PUBLIC_ERP}/api/v1/crm/docs/download/{r['id']}?t={r['token']}"}
        for r in rs]}
