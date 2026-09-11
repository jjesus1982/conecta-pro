"""
Registro de documentos gerados (crm_documents) + link público tokenizado de download.
Usado por todos os geradores (proposta, contrato, relatório, recibo, OS, aditivo, atestado) para
PERSISTIR o PDF e devolver uma URL clicável (Cowork/navegador).
"""

from __future__ import annotations

import base64
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


# Extensões cujo conteúdo vira TEXTO legível. Fora daqui o agente recebe o base64 e a
# informação honesta de que não dá para ler — melhor que um `texto_extraido` vazio, que ele
# interpretaria como "documento em branco".
_TEXTO_DE = {"pdf", "docx", "txt", "md", "csv"}


def _extrair_texto(caminho: str, ext: str) -> tuple[str, int | None, str | None]:
    """Texto, páginas e o motivo quando não deu. Nunca levanta: falhar em ler não é falhar."""
    ext = (ext or "").lower()
    if ext not in _TEXTO_DE:
        return "", None, f"formato .{ext} não vira texto — use o base64 ou o link."
    try:
        if ext == "pdf":
            from PyPDF2 import PdfReader  # noqa: PLC0415

            r = PdfReader(caminho)
            return "\n".join((pg.extract_text() or "") for pg in r.pages), len(r.pages), None
        if ext == "docx":
            import docx  # noqa: PLC0415

            return "\n".join(p.text for p in docx.Document(caminho).paragraphs), None, None
        with open(caminho, encoding="utf-8", errors="replace") as fh:
            return fh.read(), None, None
    except Exception as e:  # noqa: BLE001
        return "", None, f"não consegui extrair o texto ({type(e).__name__}: {e})"


async def baixar(db, *, documento_id: str, formato: str = "base64") -> dict:
    """O documento em base64 E em texto — o agente confere sem abrir binário.

    Item 2.2 do relatório de campo: `anexar` e `listar` existiam, e faltava o terceiro. Sem
    ele, o anexo entrava no ERP e virava um link que o agente não consegue abrir — o mesmo
    defeito da 2.1, só que na volta.

    Guarda de tamanho: acima de 8 MB o base64 sai de cena e ficam texto + link. Um anexo de
    20 MB em base64 são ~27 MB de resposta, que estouram a conversa e não entregam nada.
    """
    import os as _os  # noqa: PLC0415

    row = (await db.execute(text(
        "SELECT id::text, tipo, titulo, arquivo, token, coalesce(tamanho_kb,0) AS kb "
        "  FROM crm_documents WHERE id::text = :i AND coalesce(arquivado,false) = false"),
        {"i": str(documento_id)})).mappings().first()
    if not row:
        raise LookupError(f"Documento não encontrado: {documento_id}")
    caminho = row["arquivo"] or ""
    if not _os.path.exists(caminho):
        # o registro existe e o arquivo não: dizer isso é diferente de "não encontrado",
        # porque a ação do dono é outra (reanexar, não procurar o id de novo).
        raise FileNotFoundError(
            f"O registro {documento_id} existe, mas o arquivo sumiu do disco ({caminho}). "
            "Anexe de novo.")
    ext = caminho.rsplit(".", 1)[-1].lower()
    texto, paginas, motivo = _extrair_texto(caminho, ext)
    with open(caminho, "rb") as fh:
        bruto = fh.read()
    kb = round(len(bruto) / 1024, 1)
    out: dict = {
        "ok": True, "id": row["id"], "nome": row["titulo"], "categoria": row["tipo"],
        "arquivo": {"nome": row["titulo"], "mime": EXT_ACEITAS.get(ext, "application/octet-stream"),
                    "tamanho_kb": kb},
        "texto_extraido": texto, "paginas": paginas,
        "url_alternativa": f"{PUBLIC_ERP}/api/v1/crm/docs/download/{row['id']}?t={row['token']}",
    }
    if motivo:
        out["aviso"] = motivo
    if str(formato).lower() == "texto":
        return out
    if len(bruto) > 8 * 1024 * 1024:
        out["aviso"] = (f"Arquivo de {kb / 1024:.1f} MB — base64 omitido para não estourar a "
                        f"conversa. Use o texto ou `url_alternativa`.")
        return out
    out["arquivo"]["base64"] = base64.b64encode(bruto).decode("ascii")
    return out


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
