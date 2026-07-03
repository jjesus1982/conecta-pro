"""Monitoramento DET (Domicílio Eletrônico Trabalhista) — Conecta Mais.

Objetivo: quando chega uma comunicação oficial no DET (fiscalização do trabalho) ou uma
intimação de processo trabalhista, o sistema TRATA sozinho: classifica, extrai o processo,
monta o dossiê (reusa o intake) e escala ao CQB.

REALIDADE TÉCNICA (honesta):
- O certificado A1 IDENTIFICA a empresa (e-CNPJ), mas o DET é acessado via gov.br SSO
  (não há API REST autenticada só por mTLS do certificado). A coleta 100% automática exige
  credenciamento gov.br (OAuth) OU um robô de navegador (Playwright) que faça o login gov.br.
- Enquanto isso, a INGESTÃO ASSISTIDA é 100% funcional: o usuário baixa a comunicação do DET
  (PDF/texto) e sobe aqui — o resto (classificar → dossiê → escalar CQB) é automático.
- Este módulo já deixa o cliente de certificado pronto (status) e o pipeline pronto para o dia
  em que a coleta automática for habilitada (gov.br OAuth).

NÃO fabrica comunicações. Se não há coleta real, retorna estado honesto.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CERT_PATH = os.environ.get("NFE_CERT_PATH_A1", "/app/credentials/certificates/certificado.pfx")
CNPJ_EMPRESA = "35710481000103"
DET_URL = "https://det.sit.trabalho.gov.br"

# ── Fluxo gov.br do DET — descoberto por engenharia reversa (2026-07-02) ──────
# O A1 é aceito no TLS do login por certificado do gov.br, e o OAuth do DET é:
GOVBR_AUTHORIZE = "https://sso.acesso.gov.br/authorize"
GOVBR_CLIENT_ID = "det.sit.trabalho.gov.br"          # gov.br usa o domínio como client_id
GOVBR_REDIRECT_URI = "https://det.sit.trabalho.gov.br/acessogov"
GOVBR_SCOPE = "openid email profile govbr_confiabilidades govbr_empresa"
GOVBR_CERT_LOGIN = "https://certificado.sso.acesso.gov.br/login"  # form: accountId,_csrf,operation,token
# BLOQUEADOR: gov.br está atrás de WAF F5 ASM (cookies TS0185eea4/TS0197b850) que
# devolve HTTP 400 a clientes não-navegador (desafio JS anti-bot). Por isso a coleta
# 100% automática exige um NAVEGADOR REAL (Playwright c/ client-certificate) que resolva
# o desafio do WAF, faça o login gov.br por certificado e complete o OAuth → sessão DET.
# A ingestão assistida (abaixo) não depende disso e funciona 100%.


# ── status da conexão (certificado real) ─────────────────────────────────────
def status_conexao() -> dict[str, Any]:
    """Carrega o A1 e reporta o estado REAL da conexão com o DET (sem fabricar)."""
    try:
        from modules.government_integrations.core.certificate_manager import CertificateManager
        senha = os.environ.get("CERTIFICATE_PASSWORD", "Conecta123")
        cm = CertificateManager(pfx_path=CERT_PATH, password=senha)
        if not cm.load():
            return {"certificado_ok": False, "mensagem": "Falha ao carregar o certificado A1."}
        info = cm.info
        return {
            "certificado_ok": True,
            "titular": info.subject_cn,
            "cnpj": info.cpf_cnpj,
            "valido_ate": info.valid_until.isoformat() if info.valid_until else None,
            "dias_para_expirar": info.days_until_expiry,
            "coleta_automatica": False,
            "modo_atual": "ingestao_assistida",
            "explicacao": (
                "O certificado A1 identifica a empresa (e-CNPJ), mas o DET é acessado via gov.br SSO. "
                "A coleta automática requer credenciamento gov.br (OAuth) ou robô de navegador. "
                "Por ora: baixe a comunicação no DET e envie aqui — o tratamento é automático."
            ),
            "portal_det": DET_URL,
        }
    except Exception as e:  # noqa: BLE001
        logger.error("DET status: %s", e)
        return {"certificado_ok": False, "mensagem": f"Erro ao verificar certificado: {e}"}


# ── tabela ───────────────────────────────────────────────────────────────────
async def ensure_table(db: AsyncSession) -> None:
    await db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS juridico_det_comunicacoes (
            id           SERIAL PRIMARY KEY,
            origem       VARCHAR(30) NOT NULL DEFAULT 'ingestao_assistida',
            tipo         VARCHAR(40),
            titulo       TEXT,
            numero       TEXT,
            orgao        TEXT,
            prazo        TEXT,
            resumo       TEXT,
            processo_id  INTEGER,
            escalonar    BOOLEAN NOT NULL DEFAULT FALSE,
            status       VARCHAR(30) NOT NULL DEFAULT 'nova',
            texto_len    INTEGER,
            created_by   VARCHAR(64),
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))


# ── classificação da comunicação ────────────────────────────────────────────
_PROMPT_CLASSIF = (
    "Você é assistente jurídico. Leia a COMUNICAÇÃO OFICIAL abaixo (DET / Justiça do Trabalho) "
    "e classifique. Responda SOMENTE um JSON:\n"
    "{\n"
    '  "tipo": "processo_trabalhista | intimacao | auto_infracao | notificacao_fiscalizacao | edital | outro",\n'
    '  "titulo": "assunto curto",\n'
    '  "numero": "número do processo/auto/comunicação, ou null",\n'
    '  "orgao": "órgão emissor (Vara/TRT/SIT/DRT), ou null",\n'
    '  "prazo": "prazo/data de audiência se houver, ou null",\n'
    '  "resumo": "1-2 frases do que é e o que exige",\n'
    '  "e_acao_judicial": true|false\n'
    "}\n"
)


async def _classificar(texto: str) -> dict[str, Any]:
    from modules.juridico.parecer_service import _chamar_llm, _parse_json_llm
    r = await _chamar_llm(_PROMPT_CLASSIF, texto[:12000], max_tokens=800)
    if not r:
        return {}
    return _parse_json_llm(r["content"]) or {}


# ── processamento de uma comunicação (o coração) ─────────────────────────────
async def processar_comunicacao(
    db: AsyncSession, texto: str, origem: str, user_id: str | None
) -> dict[str, Any]:
    """Classifica a comunicação; se for ação judicial, dispara o intake (dossiê+defesa) e escala."""
    await ensure_table(db)
    texto = (texto or "").strip()
    if len(texto) < 30:
        return {"ok": False, "mensagem": "Comunicação sem texto suficiente para análise."}

    classif = await _classificar(texto)
    tipo = classif.get("tipo") or "outro"
    e_acao = bool(classif.get("e_acao_judicial")) or tipo in ("processo_trabalhista", "intimacao")

    processo_id = None
    escalonar = False
    intake = None
    if e_acao:
        # dispara o MESMO pipeline de Processos & Defesa
        from modules.juridico import processos_service as PS
        intake = await PS.analisar_processo(
            db, texto=texto, numero=classif.get("numero"),
            tipo="trabalhista", user_id=user_id,
        )
        if intake.get("ok"):
            processo_id = intake.get("id")
            escalonar = bool(intake.get("escalonar"))

    row = await db.execute(text(
        """
        INSERT INTO juridico_det_comunicacoes
            (origem, tipo, titulo, numero, orgao, prazo, resumo, processo_id, escalonar,
             status, texto_len, created_by)
        VALUES (:o,:t,:tit,:num,:org,:pz,:res,:pid,:esc,:st,:tl,:cb)
        RETURNING id, created_at
        """),
        {"o": origem, "t": tipo, "tit": classif.get("titulo"), "num": classif.get("numero"),
         "org": classif.get("orgao"), "pz": classif.get("prazo"), "res": classif.get("resumo"),
         "pid": processo_id, "esc": escalonar,
         "st": "dossie_montado" if processo_id else "classificada",
         "tl": len(texto), "cb": str(user_id) if user_id else None})
    rec = row.mappings().first()

    return {
        "ok": True,
        "id": rec["id"],
        "classificacao": classif,
        "e_acao_judicial": e_acao,
        "processo_id": processo_id,
        "escalonar": escalonar,
        "intake": intake,
        "created_at": rec["created_at"].isoformat() if rec.get("created_at") else None,
        "proxima_acao": (
            "Dossiê montado — revise em Processos & Defesa e encaminhe ao CQB."
            if processo_id else "Comunicação classificada e registrada."
        ),
    }


async def registrar_do_robo(db: AsyncSession, mensagens: list[dict[str, Any]]) -> int:
    """Registra na caixa do ERP as mensagens que o robô leu do DET (idempotente)."""
    await ensure_table(db)
    novos = 0
    for m in mensagens or []:
        assunto = (m.get("assunto") or "").strip()
        orgao = (m.get("orgao") or "").strip()
        data = (m.get("data") or "").strip()
        if not assunto:
            continue
        ex = await db.execute(text(
            "SELECT 1 FROM juridico_det_comunicacoes WHERE titulo=:t AND COALESCE(orgao,'')=:o AND COALESCE(prazo,'')=:d"),
            {"t": assunto, "o": orgao, "d": data})
        if ex.first():
            continue
        tipo = (m.get("tipo") or "comunicado").lower()
        e_fisc = "inspeção" in orgao.lower() or "notific" in tipo
        await db.execute(text(
            """INSERT INTO juridico_det_comunicacoes (origem, tipo, titulo, orgao, prazo, resumo, escalonar, status)
               VALUES ('det_robo', :tipo, :titulo, :orgao, :data, :resumo, :esc, 'nova')"""),
            {"tipo": m.get("tipo") or "comunicado", "titulo": assunto, "orgao": orgao, "data": data,
             "resumo": f"{m.get('tipo')} de {orgao} em {data}", "esc": e_fisc})
        novos += 1
    return novos


async def listar_comunicacoes(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    await ensure_table(db)
    rows = await db.execute(text(
        "SELECT id, origem, tipo, titulo, numero, orgao, prazo, resumo, processo_id, escalonar, "
        "status, created_at FROM juridico_det_comunicacoes ORDER BY created_at DESC LIMIT :l"),
        {"l": int(limit)})
    out = []
    for r in rows.mappings().all():
        out.append({
            "id": r["id"], "origem": r["origem"], "tipo": r["tipo"], "titulo": r["titulo"],
            "numero": r["numero"], "orgao": r["orgao"], "prazo": r["prazo"], "resumo": r["resumo"],
            "processo_id": r["processo_id"], "escalonar": bool(r["escalonar"]), "status": r["status"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return out


async def coletar_automatico(db: AsyncSession) -> dict[str, Any]:
    """Coleta automática do DET. Hoje retorna estado honesto (requer credenciamento gov.br).

    Quando o gov.br OAuth (ou robô de navegador) estiver habilitado, este método buscará as
    comunicações novas e chamará processar_comunicacao para cada uma.
    """
    st = status_conexao()
    return {
        "coletadas": 0,
        "modo": st.get("modo_atual"),
        "coleta_automatica_disponivel": st.get("coleta_automatica", False),
        "mensagem": (
            "Coleta automática ainda não habilitada. O fluxo OAuth do gov.br já foi mapeado "
            "(client_id=det.sit.trabalho.gov.br), mas o gov.br está atrás de um WAF anti-bot (F5 "
            "ASM) que bloqueia clientes sem navegador. Requer robô Playwright (navegador real + "
            "certificado) para passar o WAF e completar o login gov.br. Use a ingestão assistida."
        ),
        "certificado": {"cnpj": st.get("cnpj"), "valido_ate": st.get("valido_ate")},
    }
