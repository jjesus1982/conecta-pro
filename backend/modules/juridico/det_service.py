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
    # inteiro-teor da comunicação (populado pelo robô quando abre a mensagem no DET)
    await db.execute(text(
        "ALTER TABLE juridico_det_comunicacoes ADD COLUMN IF NOT EXISTS inteiro_teor TEXT"))


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


# pistas de que a comunicação é uma ação/intimação judicial (dispara o dossiê)
_PISTAS_JUDICIAL = (
    "reclamante", "reclamada", "vara do trabalho", "trt", "audiência", "audiencia",
    "processo n", "processo nº", "processo no", "intimação", "intimacao", "citação",
    "citacao", "reclamação trabalhista", "reclamacao trabalhista", "justiça do trabalho",
    "justica do trabalho", "juízo", "juizo", "contestação", "contestacao",
)


def _parece_judicial(tipo: str, titulo: str, teor: str | None) -> bool:
    """Heurística leve: só chama o LLM/dossiê quando a comunicação tem cara de processo."""
    blob = f"{tipo or ''} {titulo or ''} {teor or ''}".lower()
    if tipo and tipo.lower() in ("intimacao", "intimação", "processo_trabalhista"):
        return True
    return any(p in blob for p in _PISTAS_JUDICIAL)


async def _ligar_dossie(db: AsyncSession, comunicacao_id: int, texto: str) -> None:
    """Monta o dossiê de defesa para uma intimação e o liga à comunicação (idempotente por linha)."""
    try:
        from modules.juridico import processos_service as PS
        intake = await PS.analisar_processo(db, texto=texto, numero=None, tipo="trabalhista", user_id=None)
    except Exception as e:  # noqa: BLE001
        logger.warning("DET dossiê auto: %s", e)
        return
    if not intake.get("ok"):
        return
    await db.execute(text(
        "UPDATE juridico_det_comunicacoes SET processo_id=:pid, escalonar=:esc, status='dossie_montado' WHERE id=:id"),
        {"pid": intake.get("id"), "esc": bool(intake.get("escalonar")), "id": comunicacao_id})


async def registrar_do_robo(db: AsyncSession, mensagens: list[dict[str, Any]]) -> int:
    """Registra na caixa do ERP as mensagens que o robô leu do DET (idempotente).

    Quando a mensagem traz inteiro-teor e tem cara de intimação judicial, MONTA o dossiê
    de defesa automaticamente e liga o processo à comunicação (o que o Jordan pediu:
    "baixa o inteiro-teor de cada comunicação e liga as intimações ao dossiê").
    """
    await ensure_table(db)
    novos = 0
    for m in mensagens or []:
        assunto = (m.get("assunto") or "").strip()
        orgao = (m.get("orgao") or "").strip()
        data = (m.get("data") or "").strip()
        if not assunto:
            continue
        teor = (m.get("inteiro_teor") or "").strip() or None
        tipo = (m.get("tipo") or "comunicado").lower()
        ex = await db.execute(text(
            "SELECT id, inteiro_teor, processo_id FROM juridico_det_comunicacoes "
            "WHERE titulo=:t AND COALESCE(orgao,'')=:o AND COALESCE(prazo,'')=:d"),
            {"t": assunto, "o": orgao, "d": data})
        row = ex.mappings().first()
        if row:
            # já existe — se o inteiro-teor chegou agora (2ª passada), completa o registro
            if teor and not (row.get("inteiro_teor") or "").strip():
                await db.execute(text(
                    "UPDATE juridico_det_comunicacoes SET inteiro_teor=:teor WHERE id=:id"),
                    {"teor": teor, "id": row["id"]})
                # teor tardio de intimação ainda sem dossiê → monta agora
                if not row.get("processo_id") and _parece_judicial(tipo, assunto, teor):
                    await _ligar_dossie(db, row["id"], teor)
            continue
        e_fisc = "inspeção" in orgao.lower() or "notific" in tipo
        ins = await db.execute(text(
            """INSERT INTO juridico_det_comunicacoes (origem, tipo, titulo, orgao, prazo, resumo, inteiro_teor, escalonar, status)
               VALUES ('det_robo', :tipo, :titulo, :orgao, :data, :resumo, :teor, :esc, 'nova')
               RETURNING id"""),
            {"tipo": m.get("tipo") or "comunicado", "titulo": assunto, "orgao": orgao, "data": data,
             "resumo": f"{m.get('tipo')} de {orgao} em {data}", "teor": teor, "esc": e_fisc})
        new_id = ins.scalar()
        novos += 1
        # intimação judicial com inteiro-teor → monta o dossiê e liga
        if teor and _parece_judicial(tipo, assunto, teor):
            await _ligar_dossie(db, new_id, teor)
    return novos


async def listar_comunicacoes(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    await ensure_table(db)
    rows = await db.execute(text(
        "SELECT id, origem, tipo, titulo, numero, orgao, prazo, resumo, inteiro_teor, processo_id, escalonar, "
        "status, created_at FROM juridico_det_comunicacoes ORDER BY created_at DESC LIMIT :l"),
        {"l": int(limit)})
    out = []
    for r in rows.mappings().all():
        out.append({
            "id": r["id"], "origem": r["origem"], "tipo": r["tipo"], "titulo": r["titulo"],
            "numero": r["numero"], "orgao": r["orgao"], "prazo": r["prazo"], "resumo": r["resumo"],
            "inteiro_teor": r["inteiro_teor"],
            "processo_id": r["processo_id"], "escalonar": bool(r["escalonar"]), "status": r["status"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return out


async def obter_comunicacao(db: AsyncSession, comunicacao_id: int) -> dict[str, Any] | None:
    """Uma comunicação completa (inclui inteiro-teor) para leitura/abertura/PDF na tela."""
    await ensure_table(db)
    r = await db.execute(text(
        "SELECT id, origem, tipo, titulo, numero, orgao, prazo, resumo, inteiro_teor, processo_id, "
        "escalonar, status, created_at FROM juridico_det_comunicacoes WHERE id=:id"),
        {"id": int(comunicacao_id)})
    row = r.mappings().first()
    if not row:
        return None
    return {
        "id": row["id"], "origem": row["origem"], "tipo": row["tipo"], "titulo": row["titulo"],
        "numero": row["numero"], "orgao": row["orgao"], "prazo": row["prazo"], "resumo": row["resumo"],
        "inteiro_teor": row["inteiro_teor"], "processo_id": row["processo_id"],
        "escalonar": bool(row["escalonar"]), "status": row["status"],
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def gerar_pdf_comunicacao(c: dict[str, Any]) -> bytes:
    """PDF padrão-ouro (pdf_branding) de UMA comunicação do DET — para ler/baixar dentro do ERP.

    Reprodução fiel do inteiro-teor lido do Domicílio Eletrônico Trabalhista (uso interno).
    """
    import io
    from datetime import datetime, timezone

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=40 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)
    W = A4[0] - 32 * mm
    story: list = []

    def _p(txt, key="corpo"):
        safe = (str(txt) or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(safe.replace("\n", "<br/>"), st[key])

    data_str = (c.get("created_at") or "")[:10] or datetime.now(timezone.utc).strftime("%d/%m/%Y")
    meta = Table(
        [[Paragraph("<b>Tipo</b>", st["cell"]), Paragraph(str(c.get("tipo") or "—"), st["cell"]),
          Paragraph("<b>Órgão</b>", st["cell"]), Paragraph(str(c.get("orgao") or "—"), st["cell"])],
         [Paragraph("<b>Data</b>", st["cell"]), Paragraph(str(c.get("prazo") or data_str), st["cell"]),
          Paragraph("<b>Nº</b>", st["cell"]), Paragraph(str(c.get("numero") or "—"), st["cell"])]],
        colWidths=[24 * mm, W / 2 - 24 * mm, 24 * mm, W / 2 - 24 * mm])
    meta.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
        ("BACKGROUND", (0, 0), (0, -1), B.FUNDO_CLARO), ("BACKGROUND", (2, 0), (2, -1), B.FUNDO_CLARO),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(_p(f"<b>{c.get('titulo') or 'Comunicação DET'}</b>", "corpo"))
    story.append(Spacer(1, 3 * mm)); story.append(meta); story.append(Spacer(1, 5 * mm))

    teor = (c.get("inteiro_teor") or "").strip()
    story += B.secao("INTEIRO-TEOR", st)
    story.append(_p(teor if teor else "Inteiro-teor ainda não coletado para esta comunicação."))

    if c.get("escalonar"):
        story.append(Spacer(1, 4 * mm))
        al = Table([[Paragraph(
            "<b>ATENÇÃO:</b> comunicação de fiscalização/intimação — verifique o prazo e a ação necessária.",
            ParagraphStyle("al", parent=st["corpo"], textColor=colors.HexColor("#B45309")))]], colWidths=[W])
        al.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, B.LARANJA),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7ED")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
        story.append(al)

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(
        '<font size="7.5" color="#6B7280">Reprodução fiel da comunicação recebida no Domicílio '
        'Eletrônico Trabalhista (DET), coletada pelo Conecta PRO para uso interno. Documento oficial '
        'disponível no portal do DET (det.sit.trabalho.gov.br).</font>',
        ParagraphStyle("disc", parent=st["small"], fontSize=7.5, leading=10)))

    doc.build(story,
              onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="COMUNICAÇÃO DET", seal_watermark=True),
              onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="COMUNICAÇÃO DET", seal_watermark=True))
    return buf.getvalue()


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
