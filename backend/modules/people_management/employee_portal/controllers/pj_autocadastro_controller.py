"""Autocadastro PJ (prestadores) — 3º trilho, separado de CANDIDATO (ATS) e de CLT.

O prestador PJ se autocadastra por link TOKENIZADO INDIVIDUAL. O token identifica o registro
PRÉ-SEMEADO (já com empresa_id correto + tipo_contrato='pj' + status='pj_pendente') — a pessoa
NÃO escolhe a empresa (casar por nome já deu erro). Ao concluir: UPDATE do registro
pré-semeado (dados PJ + facial) → status 'pj_ativo'. O `empresa_id` NÃO é tocado aqui (vem
do pré-seed) — nunca cai no DEFAULT cego do banco.

NÃO é CLT: sem funil de candidato, sem admissão CLT, sem eSocial/CTPS/exame/holerite. Vai para
o pagamento PJ da empresa dona (Eletrônica→Inter, Patrimonial→Cora, PIX contra nota fiscal).
"""
import json
import os
import re
import uuid as _uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.people_management.employee_portal.services import document_extraction_service as _extractor

router = APIRouter(prefix="/autocadastro-pj", tags=["Autocadastro PJ (prestadores)"])

_STAGING_DIR = Path(os.getenv("CANDIDATO_UPLOAD_DIR", "/app/uploads/candidatos_staging")) / "pj"
_TIPOS_DOC_PJ = {"cartao_cnpj", "contrato_social", "rg", "cpf", "outro"}
_EXT_POR_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf", "image/webp": ".webp"}

# empresa_id (EXPLÍCITO — o banco tem DEFAULT cego = Patrimonial)
_ELETRONICA = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
_PATRIMONIAL = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"

# TOKENS FIXOS DE EMPRESA (autocadastro LIVRE — "manda e esquece"): a pessoa preenche o
# próprio nome, a EMPRESA vem do link (não é a pessoa que escolhe — evita erro de roteamento).
# Um link por empresa, reutilizável pra sempre. Env-overridável.
_TOKENS_EMPRESA = {
    os.getenv("PJ_LINK_ELETRONICA", "pj-eletronica-2026x7a3f9c1"): _ELETRONICA,
    os.getenv("PJ_LINK_PATRIMONIAL", "pj-patrimonial-2026m2b8d4e6"): _PATRIMONIAL,
}

_TERMO_PJ = (
    "TERMO DE CADASTRO DE PRESTADOR DE SERVIÇOS (PJ)\n\n"
    "Declaro, para os devidos fins, que os dados informados são verdadeiros e que atuo como "
    "PRESTADOR DE SERVIÇOS autônomo / pessoa jurídica, SEM vínculo empregatício (CLT) com as "
    "empresas do Grupo Conecta Mais. Estou ciente de que o pagamento se dá contra nota fiscal "
    "de serviço, via PIX, pela empresa contratante. Autorizo o uso dos dados para cadastro, "
    "emissão de pagamentos e verificação de idoneidade em fontes oficiais."
)


def _pix_tipo(chave: str) -> str:
    c = (chave or "").strip()
    d = re.sub(r"\D", "", c)
    if "@" in c:
        return "email"
    if len(d) == 11 and d.isdigit():
        return "cpf"
    if len(d) == 14:
        return "cnpj"
    if len(d) in (10, 11):
        return "telefone"
    return "aleatoria"


def _resolver(db: Session, token: str) -> dict[str, Any] | None:
    """Resolve o token em 2 modos:
    - 'livre': token FIXO de EMPRESA → autocadastro aberto (a pessoa preenche o próprio nome).
    - 'preseed': token INDIVIDUAL → registro pré-semeado (a pessoa só completa)."""
    tok = (token or "").strip()
    if not tok:
        return None
    # 1) token de EMPRESA (autocadastro livre)
    emp_id = _TOKENS_EMPRESA.get(tok)
    if emp_id:
        nome_emp = db.execute(text("SELECT nome_fantasia FROM empresas WHERE id::text=:e"), {"e": emp_id}).scalar()
        return {"modo": "livre", "empresa_id": emp_id, "empresa": nome_emp,
                "id": None, "nome": None, "papel_pj": None, "status": None}
    # 2) token INDIVIDUAL pré-semeado
    r = db.execute(
        text("SELECT e.id::text AS id, e.nome, e.papel_pj, e.status, e.empresa_id::text AS empresa_id, "
             " e.cpf, emp.nome_fantasia AS empresa "
             "FROM employees e LEFT JOIN empresas emp ON emp.id = e.empresa_id "
             "WHERE e.autocadastro_token = :t AND e.tipo_contrato = 'pj'"),
        {"t": tok},
    ).mappings().first()
    if r:
        return {"modo": "preseed", **dict(r)}
    return None


@router.get("/dados")
def dados_prestador(token: str = Query(...), db: Session = Depends(get_sync_db_dependency)) -> dict[str, Any]:
    """Empresa de destino (do link) + dados se for pré-semeado. A pessoa NUNCA escolhe a empresa."""
    p = _resolver(db, token)
    if not p:
        raise HTTPException(status_code=403, detail="Link inválido ou expirado. Peça o link do seu cadastro.")
    return {"modo": p["modo"], "nome": p.get("nome"), "papel": p.get("papel_pj"), "empresa": p["empresa"],
            "ja_concluido": p.get("status") == "pj_ativo"}


@router.get("/termo")
def termo_pj(token: str = Query(...), db: Session = Depends(get_sync_db_dependency)) -> dict[str, Any]:
    if not _resolver(db, token):
        raise HTTPException(status_code=403, detail="Link inválido ou expirado.")
    return {"texto": _TERMO_PJ}


@router.post("/documento")
def documento_pj(
    token: str = Form(...),
    sessao: str = Form(...),
    tipo: str = Form("outro"),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Upload de documento PJ (cartão CNPJ / contrato social / RG). OCR opcional pré-preenche."""
    if not _resolver(db, token):
        raise HTTPException(status_code=403, detail="Link inválido ou expirado.")
    tipo = tipo if tipo in _TIPOS_DOC_PJ else "outro"
    sessao_safe = re.sub(r"[^a-zA-Z0-9_-]", "", sessao or "")[:64]
    if not sessao_safe:
        raise HTTPException(status_code=422, detail="Sessão inválida.")
    data = arquivo.file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Arquivo vazio.")
    if len(data) > 12_000_000:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx. 12 MB).")
    pasta = _STAGING_DIR / sessao_safe
    pasta.mkdir(parents=True, exist_ok=True)
    ext = _EXT_POR_MIME.get((arquivo.content_type or "").lower()) or (Path(arquivo.filename or "").suffix or ".bin")
    fpath = pasta / f"{tipo}_{_uuid.uuid4().hex[:8]}{ext}"
    fpath.write_bytes(data)
    res = _extractor.extrair(data, arquivo.content_type or "", tipo)
    db.execute(
        text("INSERT INTO candidate_documents (staging_token, tipo, file_path, mime_type, original_name, "
             " extracted, extract_status) VALUES (:s, :t, :p, :m, :o, CAST(:e AS jsonb), :st)"),
        {"s": f"pj_{sessao_safe}", "t": tipo, "p": str(fpath), "m": arquivo.content_type,
         "o": arquivo.filename, "e": json.dumps(res.get("campos", {})), "st": res.get("status")},
    )
    db.commit()
    return {"tipo": tipo, "status": res.get("status"), "campos": res.get("campos", {})}


class PJConcluirBody(BaseModel):
    token: str
    nome: str | None = None  # obrigatório no modo 'livre' (token de empresa); no pré-seed já existe
    cnpj: str | None = None
    cnpj_pendente: bool = False
    razao_social: str | None = None
    regime_tributario: str | None = None
    inscricao_municipal: str | None = None
    telefone: str
    email: str
    pix_key: str
    pix_key_type: str | None = None
    banco: str | None = None
    agencia: str | None = None
    conta: str | None = None
    papel_pj: str | None = None
    face_descriptor: list[float] | None = None  # selfie (identidade biométrica do prestador)
    sessao: str | None = None


@router.post("/concluir", status_code=200)
def concluir_pj(body: PJConcluirBody, db: Session = Depends(get_sync_db_dependency)) -> dict[str, Any]:
    """Conclui o cadastro PJ → status 'pj_ativo'. Dois modos:
    - 'livre' (token de EMPRESA): INSERT de um novo registro, empresa_id do TOKEN (nunca o default).
    - 'preseed' (token individual): UPDATE do registro pré-semeado, empresa_id intocado."""
    p = _resolver(db, body.token)
    if not p:
        raise HTTPException(status_code=403, detail="Link inválido ou expirado.")

    cnpj_d = re.sub(r"\D", "", body.cnpj or "")
    if not cnpj_d and not body.cnpj_pendente:
        raise HTTPException(status_code=422, detail="Informe o CNPJ ou marque 'ainda não tenho CNPJ'.")
    if cnpj_d and len(cnpj_d) != 14:
        raise HTTPException(status_code=422, detail="CNPJ inválido (precisa de 14 dígitos).")
    for campo, lbl in (("telefone", "Telefone"), ("email", "E-mail"), ("pix_key", "Chave PIX")):
        if not str(getattr(body, campo, "") or "").strip():
            raise HTTPException(status_code=422, detail=f"Campo obrigatório: {lbl}")

    face_json = json.dumps(body.face_descriptor) if body.face_descriptor else None
    pix_tipo = (body.pix_key_type or "").strip().lower() or _pix_tipo(body.pix_key)
    pend = bool(body.cnpj_pendente or not cnpj_d)

    if p["modo"] == "livre":
        nome = (body.nome or "").strip()
        if not nome:
            raise HTTPException(status_code=422, detail="Informe seu nome completo.")
        # dedup leve: mesma chave PIX já cadastrada como PJ ativo → evita duplicado óbvio
        pix_d = re.sub(r"\D", "", body.pix_key or "")
        if pix_d and len(pix_d) in (11, 14):
            dup = db.execute(
                text("SELECT nome FROM employees WHERE regexp_replace(coalesce(pix_key,''),'\\D','','g')=:c "
                     "AND tipo_contrato='pj' AND status='pj_ativo'"),
                {"c": pix_d},
            ).scalar()
            if dup:
                raise HTTPException(status_code=409, detail="Já existe um prestador cadastrado com essa chave PIX.")
        eid = str(_uuid.uuid4())
        db.execute(
            text("INSERT INTO employees (id, nome, tipo_contrato, empresa_id, status, cnpj, cnpj_pendente, "
                 " razao_social, regime_tributario, inscricao_municipal, telefone, email, pix_key, pix_key_type, "
                 " banco, agencia, conta, papel_pj, face_descriptor, face_enrolled_at, created_at, updated_at) "
                 "VALUES (CAST(:i AS uuid), :nome, 'pj', CAST(:emp AS uuid), 'pj_ativo', :cnpj, :pend, :rs, :rt, "
                 " :im, :tel, :email, :pixk, :pixt, :banco, :ag, :conta, :papel, :face, "
                 " CASE WHEN :face IS NULL THEN NULL ELSE now() END, now(), now())"),
            {"i": eid, "nome": nome, "emp": p["empresa_id"], "cnpj": body.cnpj, "pend": pend,
             "rs": body.razao_social, "rt": body.regime_tributario, "im": body.inscricao_municipal,
             "tel": body.telefone, "email": body.email.strip().lower(), "pixk": body.pix_key, "pixt": pix_tipo,
             "banco": body.banco, "ag": body.agencia, "conta": body.conta, "papel": body.papel_pj, "face": face_json},
        )
    else:
        if p["status"] == "pj_ativo":
            raise HTTPException(status_code=409, detail="Este cadastro já foi concluído.")
        eid = p["id"]
        db.execute(
            text("UPDATE employees SET status='pj_ativo', cnpj=:cnpj, cnpj_pendente=:pend, "
                 " razao_social=:rs, regime_tributario=:rt, inscricao_municipal=:im, telefone=:tel, "
                 " email=:email, pix_key=:pixk, pix_key_type=:pixt, banco=:banco, agencia=:ag, "
                 " conta=:conta, papel_pj=coalesce(nullif(:papel,''), papel_pj), face_descriptor=:face, "
                 " face_enrolled_at=CASE WHEN :face IS NULL THEN face_enrolled_at ELSE now() END, "
                 " updated_at=now() WHERE id::text=:e"),
            {"cnpj": body.cnpj, "pend": pend, "rs": body.razao_social, "rt": body.regime_tributario,
             "im": body.inscricao_municipal, "tel": body.telefone, "email": body.email.strip().lower(),
             "pixk": body.pix_key, "pixt": pix_tipo, "banco": body.banco, "ag": body.agencia,
             "conta": body.conta, "papel": body.papel_pj or "", "face": face_json, "e": eid},
        )

    if body.sessao:
        ss = re.sub(r"[^a-zA-Z0-9_-]", "", body.sessao)[:64]
        db.execute(
            text("UPDATE candidate_documents SET employee_id=CAST(:e AS uuid) WHERE staging_token=:s"),
            {"e": eid, "s": f"pj_{ss}"},
        )
    db.commit()
    return {"ok": True, "empresa": p["empresa"], "status": "pj_ativo",
            "mensagem": f"Cadastro concluído! Você está registrado como prestador PJ da {p['empresa']}."}
