"""Funil de CANDIDATO — Fase 1 (autocadastro do candidato a uma vaga).

Visão do Jordan (2026-07-18): o candidato agendado pelo RH preenche TODOS os dados
com o mesmo rigor do eSocial, escolhe o CARGO que está concorrendo, informa a CHAVE
PIX e cadastra a SELFIE (facial) — tudo numa tela só. Vira um registro de candidato
ISOLADO da produção (employees.status='candidato'): como a folha, o RH-desempenho e
os demais consumidores de produção filtram status='ativo', o candidato não polui
nenhum dado real. Na APROVAÇÃO (fase futura) o status vira 'ativo' e a informação se
espalha pelos módulos (DP/RH/financeiro/operacional).

Fase 1 = SÓ criar o candidato + facial. NÃO cria login (candidato não acessa o portal
antes de aprovado) e NÃO aloca posto/turno (isso é a aprovação). O acompanhamento de
status (fase 2), a esteira de aprovação no RH (fase 3), a propagação (fase 4) e o gate
de acesso ao portal (fase 5) vêm depois.

Montado sob /portal (aggregator) → /people-management/portal/candidato/*, ISENTO do
gate de módulo DP. Autocadastro é PÚBLICO (pré-login), protegido por token.
"""

import hashlib
import json
import os
import re
import threading
import uuid as _uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi import status as http_status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database.session import get_sync_db_dependency
from modules.people_management.employee_portal.services import document_extraction_service as _extractor

_STAGING_DIR = Path(os.getenv("CANDIDATO_UPLOAD_DIR", "/app/uploads/candidatos_staging"))
_TIPOS_DOC = {"rg", "cpf", "comprovante_endereco", "curriculo", "ctps", "certidao_nascimento", "outro"}


def _disparar_verificacao_bg(employee_id: str) -> None:
    """Roda o dossiê+score (incl. robô Receita) em thread daemon, com sessão própria."""
    def _run() -> None:
        try:
            from core.database.session import SyncSessionLocal
            from modules.people_management.hr.services import background_check_service as _bg
            db2 = SyncSessionLocal()
            try:
                _bg.verificar(db2, employee_id, via_robo=True)
            finally:
                db2.close()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()


router = APIRouter(prefix="/candidato", tags=["Funil de Candidato"])

# Token do link de autocadastro do candidato (pré-login). Override por env.
_TOKEN = os.getenv("CANDIDATO_AUTOCADASTRO_TOKEN", "conecta-vaga-2026")

# Obrigatórios com rigor eSocial (espelham o onboarding de produção) + cargo pleiteado.
_OBRIGATORIOS = {
    "nome": "Nome completo", "email": "E-mail", "cpf": "CPF",
    "data_nascimento": "Data de nascimento", "telefone": "Telefone",
    "cep": "CEP", "logradouro": "Logradouro", "bairro": "Bairro", "cidade": "Cidade",
    "nome_mae": "Nome da mãe", "nome_pai": "Nome do pai",
    "naturalidade": "Naturalidade", "uf_nascimento": "UF de nascimento",
    "nacionalidade": "Nacionalidade", "rg": "RG", "estado_civil": "Estado civil",
    "cargo_pleiteado": "Cargo pleiteado", "pix_key": "Chave PIX",
    # PIS NÃO é obrigatório — nem todos têm/sabem o número (regra Jordan 2026-07-20)
}


class CandidatoBody(BaseModel):
    token: str
    nome: str = Field(..., min_length=3)
    email: str
    cpf: str
    data_nascimento: str
    telefone: str
    cep: str
    logradouro: str
    numero: str | None = None
    complemento: str | None = None
    bairro: str
    cidade: str
    uf: str | None = None
    nome_mae: str
    nome_pai: str  # obrigatório — a certidão de antecedentes da PF exige filiação completa
    naturalidade: str
    uf_nascimento: str  # UF de nascimento (≠ UF do endereço) — exigida no antecedentes PF
    nacionalidade: str
    rg: str
    estado_civil: str
    pis: str | None = None  # opcional — nem todos têm/sabem o PIS
    cargo_pleiteado: str
    pix_key: str
    pix_key_type: str | None = None  # cpf/email/telefone/aleatoria (inferido se vazio)
    face_descriptor: list[float] | None = None  # 128 floats da selfie (FacialCapture)
    sessao: str | None = None  # staging_token dos documentos anexados (Fase 6.1)
    dependentes: list[dict] | None = None  # filhos p/ salário-família (nome, nascimento)


def _inferir_tipo_pix(chave: str) -> str:
    c = (chave or "").strip()
    digs = re.sub(r"\D", "", c)
    if "@" in c:
        return "email"
    if len(digs) == 11 and c.replace(".", "").replace("-", "").isdigit():
        return "cpf"
    if len(digs) == 14:
        return "cnpj"
    if len(digs) in (10, 11):
        return "telefone"
    if re.fullmatch(r"[0-9a-fA-F-]{32,36}", c):
        return "aleatoria"
    return "aleatoria"


@router.get("/cargos")
def cargos_disponiveis(
    token: str = Query(...),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Funções que a empresa REALMENTE trabalha (cargos dos funcionários ativos),
    dentro da nossa realidade — NÃO os 51 cargos da CCT inteira. Sem salário na tela."""
    if token != _TOKEN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Link inválido ou expirado.")
    rows = db.execute(
        text(
            "SELECT DISTINCT cargo FROM employees "
            "WHERE status='ativo' AND coalesce(is_homologacao, false) = false "
            "  AND cargo IS NOT NULL AND trim(cargo) <> '' "
            "ORDER BY cargo"
        )
    ).fetchall()
    return {"cargos": [{"nome": r[0]} for r in rows]}


_STATUS_LABEL = {
    "candidato": "Em análise",
    "aprovado": "Aprovado! 🎉",
    "reprovado": "Não aprovado",
    "ativo": "Aprovado — acesso liberado",
}


@router.get("/status")
def status_candidatura(
    token: str = Query(...),
    cpf: str = Query(...),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Acompanhamento público do status da candidatura, pelo CPF (sem login).

    O candidato NÃO acessa o portal antes de aprovado — aqui ele só vê o andamento.
    """
    if token != _TOKEN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Link inválido ou expirado.")
    digs = re.sub(r"\D", "", cpf or "")
    if len(digs) != 11:
        raise HTTPException(status_code=422, detail="Informe um CPF válido (11 dígitos).")
    row = db.execute(
        text(
            "SELECT nome, matricula, cargo, status, created_at "
            "FROM employees "
            "WHERE regexp_replace(coalesce(cpf,''),'\\D','','g') = :c "
            "  AND status IN ('candidato','aprovado','reprovado','ativo') "
            "  AND coalesce(is_homologacao, false) = false "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"c": digs},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Nenhuma candidatura encontrada para este CPF.")
    st = row["status"]
    return {
        "protocolo": row["matricula"],
        "nome": row["nome"],
        "cargo_pleiteado": row["cargo"],
        "status": st,
        "status_label": _STATUS_LABEL.get(st, "Em análise"),
        "aprovado": st in ("aprovado", "ativo"),
        "reprovado": st == "reprovado",
        "criado_em": row["created_at"].isoformat() if row["created_at"] else None,
    }


_EXT_POR_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                 "image/heic": ".heic", "application/pdf": ".pdf"}

# ── Termo de consentimento (MINUTA — revisar com o jurídico) ──
_TERMO_VERSAO = os.getenv("CANDIDATO_TERMO_VERSAO", "1.0")
_TERMO_TEXTO = (
    "TERMO DE CONSENTIMENTO E AUTORIZAÇÃO — PROCESSO SELETIVO E ADMISSÃO\n\n"
    "Ao aceitar este termo, eu, candidato(a) identificado(a) pelo CPF informado, declaro e autorizo:\n\n"
    "1. VERACIDADE. Declaro que todas as informações e documentos que forneço neste cadastro são "
    "verdadeiros e de minha inteira responsabilidade.\n\n"
    "2. TRATAMENTO DE DADOS (LGPD). Autorizo a CONECTA MAIS a coletar, armazenar e tratar meus dados "
    "pessoais e os documentos que eu anexar, exclusivamente para o processo seletivo, a eventual admissão "
    "e o cumprimento de obrigações trabalhistas, previdenciárias e legais, nos termos da Lei nº 13.709/2018 (LGPD).\n\n"
    "3. VERIFICAÇÃO. Autorizo a CONECTA MAIS a conferir e validar as informações e documentos apresentados, "
    "inclusive mediante consulta a fontes públicas e oficiais pertinentes à avaliação da minha candidatura "
    "e à admissão.\n\n"
    "4. FINALIDADE E GUARDA. Estou ciente de que meus dados serão usados apenas para as finalidades acima e "
    "guardados pelo prazo necessário ao processo e às obrigações legais, podendo eu solicitar acesso, correção "
    "ou exclusão conforme a LGPD.\n\n"
    "5. REGISTRO. Este aceite é registrado com data, hora e endereço de conexão (IP) como prova da minha "
    "manifestação de vontade.\n\n"
    "Li e estou de acordo com os termos acima."
)


def _termo_hash() -> str:
    canonico = f"{_TERMO_VERSAO}\n{_TERMO_TEXTO}".encode()
    return hashlib.sha256(canonico).hexdigest()


def _ip_do_request(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()  # 1º IP = o do candidato (atrás do proxy)
    return request.client.host if request.client else None


class TermoAceiteBody(BaseModel):
    token: str
    sessao: str
    nome: str | None = None
    cpf: str | None = None
    rubrica: str | None = None  # PNG base64 (data URL) da assinatura, opcional
    aceite: bool = False


@router.get("/termo")
def obter_termo(token: str = Query(...)) -> dict[str, Any]:
    """Texto e versão do termo de consentimento para exibir antes do cadastro."""
    if token != _TOKEN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Link inválido ou expirado.")
    return {"versao": _TERMO_VERSAO, "hash": _termo_hash(), "texto": _TERMO_TEXTO}


@router.post("/termo-aceite", status_code=201)
def registrar_aceite(
    body: TermoAceiteBody,
    request: Request,
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Registra o aceite do termo com valor probatório (texto+versão+hash+CPF+IP+UA+
    rubrica+timestamp), ligado à sessão do candidato. Sem login — assina por token."""
    if body.token != _TOKEN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Link inválido ou expirado.")
    if not body.aceite:
        raise HTTPException(status_code=422, detail="É necessário aceitar o termo para prosseguir.")
    sessao_safe = re.sub(r"[^a-zA-Z0-9_-]", "", body.sessao or "")[:64]
    if not sessao_safe:
        raise HTTPException(status_code=422, detail="Sessão inválida.")
    rid = db.execute(
        text(
            "INSERT INTO candidate_consents (staging_token, termo_versao, termo_hash, termo_texto, "
            " nome, cpf, ip_address, user_agent, rubrica_png, aceito) "
            "VALUES (:s, :v, :h, :txt, :nome, :cpf, :ip, :ua, :rub, true) RETURNING id::text"
        ),
        {"s": sessao_safe, "v": _TERMO_VERSAO, "h": _termo_hash(), "txt": _TERMO_TEXTO,
         "nome": (body.nome or "").strip() or None, "cpf": (body.cpf or "").strip() or None,
         "ip": _ip_do_request(request), "ua": request.headers.get("user-agent", "")[:500],
         "rub": body.rubrica},
    ).scalar()
    db.commit()
    return {"success": True, "consentimento_id": rid, "versao": _TERMO_VERSAO,
            "registrado_em": "agora", "message": "Consentimento registrado."}


@router.post("/documento")
def upload_documento(
    token: str = Form(...),
    sessao: str = Form(...),
    tipo: str = Form(...),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_sync_db_dependency),
) -> dict[str, Any]:
    """Recebe um documento (foto/PDF), EXTRAI os campos com IA e devolve pra
    PRÉ-PREENCHER o formulário. Arquiva na área de staging (ligada ao candidato
    na hora do autocadastro pela `sessao`). Extração é sugestão — o candidato revisa."""
    if token != _TOKEN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Link inválido ou expirado.")
    tipo = tipo if tipo in _TIPOS_DOC else "outro"
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
    campos = res.get("campos", {})

    doc_id = db.execute(
        text(
            "INSERT INTO candidate_documents (staging_token, tipo, file_path, mime_type, original_name, "
            " extracted, extract_status) "
            "VALUES (:s, :t, :p, :m, :o, CAST(:e AS jsonb), :st) RETURNING id::text"
        ),
        {"s": sessao_safe, "t": tipo, "p": str(fpath), "m": arquivo.content_type,
         "o": arquivo.filename, "e": json.dumps(campos), "st": res.get("status")},
    ).scalar()
    db.commit()

    return {
        "documento_id": doc_id,
        "tipo": tipo,
        "status": res.get("status"),   # ok | vazio | erro
        "campos": campos,              # dict com os campos do form já prontos p/ mesclar
        "mensagem": (
            f"{len(campos)} campo(s) preenchido(s) automaticamente." if campos
            else "Documento anexado. Não consegui ler campos — preencha manualmente."
        ),
    }


@router.post("/autocadastro", status_code=201)
def autocadastro_candidato(body: CandidatoBody, db: Session = Depends(get_sync_db_dependency)) -> dict[str, Any]:
    """Autocadastro público (token) de um CANDIDATO a uma vaga.

    Cria employees.status='candidato' (isolado da produção) com dados eSocial, cargo
    pleiteado, chave PIX e a selfie (face_descriptor). NÃO cria login nem aloca posto.
    """
    if body.token != _TOKEN:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Link de vaga inválido ou expirado.")

    faltando = [lbl for campo, lbl in _OBRIGATORIOS.items()
                if not str(getattr(body, campo, "") or "").strip()]
    if faltando:
        raise HTTPException(status_code=422, detail=f"Campos obrigatórios faltando: {', '.join(faltando)}")

    email = body.email.strip().lower()
    if db.execute(text("SELECT 1 FROM users WHERE lower(email)=:e"), {"e": email}).fetchone():
        raise HTTPException(status_code=409, detail="Já existe um cadastro com este e-mail.")
    cpf_digits = re.sub(r"\D", "", body.cpf or "")
    if cpf_digits and db.execute(
        text("SELECT 1 FROM employees WHERE regexp_replace(coalesce(cpf,''),'\\D','','g')=:c AND status='candidato'"),
        {"c": cpf_digits},
    ).fetchone():
        raise HTTPException(status_code=409, detail="Já existe uma candidatura com este CPF.")

    # protocolo sequencial (CAND-0001) pela contagem de candidatos
    n = db.execute(text("SELECT count(*) FROM employees WHERE status='candidato'")).scalar() or 0
    protocolo = f"CAND-{n + 1:04d}"

    pix_tipo = (body.pix_key_type or "").strip().lower() or _inferir_tipo_pix(body.pix_key)
    face_json = json.dumps(body.face_descriptor) if body.face_descriptor else None

    employee_id = db.execute(
        text(
            "INSERT INTO employees (id, nome, email, cpf, data_nascimento, telefone, cep, "
            " logradouro, numero, complemento, bairro, cidade, uf, nome_mae, nome_pai, naturalidade, "
            " nacionalidade, rg, estado_civil, pis, cargo, matricula, status, is_homologacao, "
            " pix_key, pix_key_type, pix, face_descriptor, face_enrolled_at, "
            " biometria_facial, cliente_nome, dependentes, created_at) "
            "VALUES (gen_random_uuid(), :nome, :email, :cpf, :nasc, :tel, :cep, :log, :num, :comp, "
            " :bairro, :cidade, :uf, :mae, :pai, :natu, :naci, :rg, :ec, :pis, :cargo, :mat, 'candidato', false, "
            " :pixk, :pixt, :pixk, :face, CASE WHEN :face IS NULL THEN NULL ELSE now() END, "
            " CASE WHEN :face IS NULL THEN false ELSE true END, 'CANDIDATO', CAST(:deps AS jsonb), now()) "
            "RETURNING id::text"
        ),
        {
            "nome": body.nome.strip(), "email": email, "cpf": body.cpf, "nasc": body.data_nascimento,
            "tel": body.telefone, "cep": body.cep, "log": body.logradouro, "num": body.numero,
            "comp": body.complemento, "bairro": body.bairro, "cidade": body.cidade, "uf": body.uf,
            "mae": body.nome_mae, "pai": body.nome_pai,
            "natu": f"{(body.naturalidade or '').strip()}/{(body.uf_nascimento or '').strip().upper()}",
            "naci": body.nacionalidade,
            "rg": body.rg, "ec": body.estado_civil, "pis": body.pis,
            "cargo": body.cargo_pleiteado.strip(), "mat": protocolo,
            "pixk": body.pix_key.strip(), "pixt": pix_tipo, "face": face_json,
            "deps": json.dumps(body.dependentes) if body.dependentes else None,
        },
    ).scalar()

    # Fase 6.1: liga os documentos anexados e o consentimento (staging) ao candidato.
    docs_vinculados = 0
    consentimento_ok = False
    if body.sessao:
        sess = re.sub(r"[^a-zA-Z0-9_-]", "", body.sessao)[:64]
        if sess:
            docs_vinculados = db.execute(
                text("UPDATE candidate_documents SET employee_id = CAST(:e AS uuid) "
                     "WHERE staging_token = :s AND employee_id IS NULL"),
                {"e": employee_id, "s": sess},
            ).rowcount
            consentimento_ok = db.execute(
                text("UPDATE candidate_consents SET employee_id = CAST(:e AS uuid) "
                     "WHERE staging_token = :s AND employee_id IS NULL"),
                {"e": employee_id, "s": sess},
            ).rowcount > 0
    db.commit()

    # Fase 6.2: dispara a verificação (dossiê + score, incl. robô Receita) em background,
    # "a partir do momento que o candidato coloca o CPF" — sem travar a resposta.
    _disparar_verificacao_bg(employee_id)

    return {
        "success": True,
        "employee_id": employee_id,
        "protocolo": protocolo,
        "nome": body.nome.strip(),
        "cargo_pleiteado": body.cargo_pleiteado.strip(),
        "facial_ok": bool(face_json),
        "documentos_vinculados": docs_vinculados,
        "consentimento_registrado": consentimento_ok,
        "dependentes": len(body.dependentes) if body.dependentes else 0,
        "status": "candidato",
        "status_label": "Em análise",
        "message": "Candidatura recebida! Você está concorrendo à vaga. Acompanhe o status pelo app.",
        "proximo_passo": "O RH vai analisar sua candidatura. Você será avisado se for aprovado.",
    }
