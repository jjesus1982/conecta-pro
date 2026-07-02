"""Pareceres Jurídicos com IA (módulo Jurídico do Conecta PRO).

Princípio: **a IA fundamenta, o humano certifica**. O parecer é gerado como um documento
estruturado (RELATÓRIO → FUNDAMENTAÇÃO → CONCLUSÃO), SEMPRE com disclaimer e flag de
escalonamento. A IA NUNCA inventa lei/jurisprudência — quando não tem base segura, ela
o declara e recomenda escalonamento ao advogado responsável.

Empresa: segurança patrimonial / agentes de portaria (CCT SINDECOMPRESTS).
Áreas cobertas: trabalhista, cível, tributária.

O parecer é persistido em `juridico_pareceres` com status='rascunho' (o responsável jurídico
certifica/aprova depois). PDF no padrão-ouro (pdf_branding) com assinatura digital da empresa.

Se o LLM faltar em runtime → resposta honesta "IA indisponível", sem fabricar conteúdo.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Áreas suportadas + contexto jurídico específico de cada uma ──────────────
AREAS: dict[str, str] = {
    "trabalhista": (
        "Direito do Trabalho brasileiro (CLT). A empresa atua em SEGURANÇA PATRIMONIAL "
        "com AGENTES DE PORTARIA (NÃO vigilância armada). A base salarial e os adicionais "
        "seguem a CCT do SINDECOMPRESTS (Convenção Coletiva vigente, categoria de asseio/"
        "conservação e portaria no Amazonas). Considere jornada 12x36, adicional noturno, "
        "insalubridade quando aplicável, intervalo, banco de horas e verbas rescisórias."
    ),
    "civel": (
        "Direito Civil e Contratual brasileiro (Código Civil, Lei nº 10.406/2002). "
        "Contexto de prestação de serviços de portaria/segurança patrimonial a condomínios "
        "e empresas. Considere responsabilidade civil, cláusulas contratuais, inadimplemento, "
        "rescisão, multa e foro."
    ),
    "tributaria": (
        "Direito Tributário brasileiro. A empresa é prestadora de serviços de portaria/"
        "segurança patrimonial em Manaus/AM. Considere ISS (município de Manaus), PIS/COFINS, "
        "regime tributário (Lucro Real / Simples Nacional conforme o CNPJ), retenções e "
        "eventuais liminares (PIS/COFINS, INSS). Não afirme enquadramento sem base."
    ),
}

_DISCLAIMER = (
    "Este parecer foi FUNDAMENTADO com apoio de inteligência artificial e tem caráter "
    "meramente OPINATIVO e informativo. NÃO substitui a análise e a certificação de advogado "
    "habilitado (OAB). A IA não constitui fonte de direito e pode conter imprecisões; nenhuma "
    "norma, jurisprudência ou súmula deve ser considerada válida sem conferência na fonte oficial. "
    "A decisão final e a responsabilidade técnica são do responsável jurídico da empresa."
)


def _system_prompt(area: str) -> str:
    """Monta o system prompt jurídico específico da área."""
    ctx = AREAS.get(area, AREAS["civel"])
    return (
        "Você é um assistente jurídico sênior que redige PARECERES para o departamento "
        "jurídico de uma empresa brasileira. "
        f"ÁREA: {area.upper()}. CONTEXTO: {ctx}\n\n"
        "REGRAS INVIOLÁVEIS:\n"
        "1. NUNCA invente leis, artigos, súmulas, jurisprudência ou números de processo. "
        "Se não tiver certeza absoluta da referência normativa, diga expressamente que a "
        "fundamentação precisa ser confirmada na fonte oficial e sinalize escalonamento.\n"
        "2. A IA FUNDAMENTA, o humano CERTIFICA. Este é um RASCUNHO opinativo.\n"
        "3. Se o caso envolver risco alto, urgência, litígio em curso, matéria penal, ou "
        "insuficiência de informações, marque escalonar=true e recomende advogado habilitado.\n"
        "4. Escreva em português jurídico claro, objetivo e impessoal.\n\n"
        "FORMATO DE SAÍDA — responda EXCLUSIVAMENTE com um JSON válido (sem markdown, sem "
        "texto fora do JSON) no schema:\n"
        "{\n"
        '  "relatorio": "síntese dos fatos e da questão posta (texto)",\n'
        '  "fundamentacao": "análise jurídica fundamentada, citando normas SOMENTE se seguro (texto, pode ter parágrafos separados por \\n)",\n'
        '  "conclusao": "conclusão objetiva e recomendação prática (texto)",\n'
        '  "escalonar": true|false,\n'
        '  "motivo_escalonamento": "por que escalar ao advogado, ou string vazia se escalonar=false"\n'
        "}"
    )


async def _chamar_llm(system_prompt: str, user_content: str, max_tokens: int = 3000) -> dict[str, Any] | None:
    """Chama o ClaudeProvider. Retorna None se a IA estiver indisponível (sem fabricar)."""
    try:
        from modules.ai.conversation.services.llm_provider import ClaudeProvider

        provider = ClaudeProvider()
        if not provider.api_key:
            logger.warning("Parecer IA: ANTHROPIC_API_KEY ausente — IA indisponível")
            return None
        resp = await provider.generate(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        return {"content": resp.content, "model": resp.model}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Parecer IA: falha ao chamar LLM: {e}")
        return None


def _parse_json_llm(raw: str) -> dict[str, Any] | None:
    """Extrai o JSON da resposta do LLM de forma tolerante (pode vir cercado de texto)."""
    if not raw:
        return None
    s = raw.strip()
    # remove cercas de markdown se houver
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        s = s.removeprefix("json").strip()
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        # tenta achar o primeiro { ... } balanceado
        ini = s.find("{")
        fim = s.rfind("}")
        if ini != -1 and fim != -1 and fim > ini:
            try:
                return json.loads(s[ini : fim + 1])
            except Exception:  # noqa: BLE001
                return None
    return None


async def _ensure_table(db: AsyncSession) -> None:
    """Cria a tabela juridico_pareceres se ainda não existir (idempotente, sem migration)."""
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS juridico_pareceres (
                id           SERIAL PRIMARY KEY,
                area         VARCHAR(40)  NOT NULL,
                titulo       TEXT         NOT NULL,
                contexto     TEXT,
                parecer      TEXT,
                conclusao    TEXT,
                escalonar    BOOLEAN      NOT NULL DEFAULT FALSE,
                status       VARCHAR(20)  NOT NULL DEFAULT 'rascunho',
                pdf_path     TEXT,
                created_by   VARCHAR(64),
                created_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
            """
        )
    )


async def gerar_parecer(
    db: AsyncSession,
    area: str,
    titulo: str,
    contexto: str,
    user_id: str | None,
) -> dict[str, Any]:
    """Gera um PARECER jurídico estruturado com IA e persiste em juridico_pareceres.

    Retorna o dict do parecer criado. Se a IA estiver indisponível, persiste um registro
    honesto (status='ia_indisponivel') sem fabricar conteúdo jurídico.
    """
    area = (area or "civel").strip().lower()
    if area not in AREAS:
        area = "civel"

    await _ensure_table(db)

    system = _system_prompt(area)
    user_content = (
        f"TÍTULO DA CONSULTA: {titulo}\n\n"
        f"CONTEXTO / FATOS E QUESTÃO POSTA:\n{contexto}\n\n"
        "Redija o parecer no formato JSON especificado."
    )
    llm = await _chamar_llm(system, user_content)

    if llm is None:
        # Honestidade: não fabrica. Registra o pedido como indisponível.
        row = await db.execute(
            text(
                """
                INSERT INTO juridico_pareceres
                    (area, titulo, contexto, parecer, conclusao, escalonar, status, created_by)
                VALUES
                    (:area, :titulo, :contexto, :parecer, :conclusao, :escalonar, :status, :created_by)
                RETURNING id, created_at
                """
            ),
            {
                "area": area,
                "titulo": titulo,
                "contexto": contexto,
                "parecer": None,
                "conclusao": None,
                "escalonar": True,
                "status": "ia_indisponivel",
                "created_by": str(user_id) if user_id else None,
            },
        )
        rec = row.mappings().first()
        return {
            "id": rec["id"],
            "area": area,
            "titulo": titulo,
            "contexto": contexto,
            "status": "ia_indisponivel",
            "ia_disponivel": False,
            "escalonar": True,
            "mensagem": (
                "IA indisponível no momento. O pedido foi registrado, mas nenhum parecer foi "
                "gerado — encaminhe ao responsável jurídico."
            ),
            "disclaimer": _DISCLAIMER,
            "created_at": rec["created_at"].isoformat() if rec.get("created_at") else None,
        }

    parsed = _parse_json_llm(llm["content"])
    if not parsed:
        # A IA respondeu mas fora do formato — não inventamos estrutura; guardamos o texto cru.
        relatorio = ""
        fundamentacao = llm["content"].strip()
        conclusao = ""
        escalonar = True
        motivo = "Resposta da IA fora do formato esperado — requer revisão humana."
    else:
        relatorio = str(parsed.get("relatorio", "")).strip()
        fundamentacao = str(parsed.get("fundamentacao", "")).strip()
        conclusao = str(parsed.get("conclusao", "")).strip()
        escalonar = bool(parsed.get("escalonar", False))
        motivo = str(parsed.get("motivo_escalonamento", "")).strip()

    # corpo completo do parecer (relatório → fundamentação → conclusão)
    partes = []
    if relatorio:
        partes.append(f"I. RELATÓRIO\n\n{relatorio}")
    if fundamentacao:
        partes.append(f"II. FUNDAMENTAÇÃO\n\n{fundamentacao}")
    if conclusao:
        partes.append(f"III. CONCLUSÃO\n\n{conclusao}")
    parecer_texto = "\n\n".join(partes) if partes else fundamentacao

    row = await db.execute(
        text(
            """
            INSERT INTO juridico_pareceres
                (area, titulo, contexto, parecer, conclusao, escalonar, status, created_by)
            VALUES
                (:area, :titulo, :contexto, :parecer, :conclusao, :escalonar, :status, :created_by)
            RETURNING id, created_at
            """
        ),
        {
            "area": area,
            "titulo": titulo,
            "contexto": contexto,
            "parecer": parecer_texto,
            "conclusao": conclusao,
            "escalonar": escalonar,
            "status": "rascunho",
            "created_by": str(user_id) if user_id else None,
        },
    )
    rec = row.mappings().first()

    return {
        "id": rec["id"],
        "area": area,
        "titulo": titulo,
        "contexto": contexto,
        "relatorio": relatorio,
        "fundamentacao": fundamentacao,
        "conclusao": conclusao,
        "parecer": parecer_texto,
        "escalonar": escalonar,
        "motivo_escalonamento": motivo,
        "status": "rascunho",
        "ia_disponivel": True,
        "modelo_ia": llm["model"],
        "disclaimer": _DISCLAIMER,
        "created_by": str(user_id) if user_id else None,
        "created_at": rec["created_at"].isoformat() if rec.get("created_at") else None,
    }


async def listar_pareceres(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    """Lista os pareceres mais recentes (metadados, sem o corpo completo)."""
    await _ensure_table(db)
    rows = await db.execute(
        text(
            """
            SELECT id, area, titulo, escalonar, status, pdf_path, created_by, created_at
            FROM juridico_pareceres
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"limit": int(limit)},
    )
    out = []
    for r in rows.mappings().all():
        out.append(
            {
                "id": r["id"],
                "area": r["area"],
                "titulo": r["titulo"],
                "escalonar": bool(r["escalonar"]),
                "status": r["status"],
                "tem_pdf": bool(r["pdf_path"]),
                "created_by": r["created_by"],
                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            }
        )
    return out


async def obter_parecer(db: AsyncSession, id: str) -> dict[str, Any] | None:
    """Retorna o parecer completo por id, ou None se não existir."""
    await _ensure_table(db)
    row = await db.execute(
        text(
            """
            SELECT id, area, titulo, contexto, parecer, conclusao, escalonar,
                   status, pdf_path, created_by, created_at
            FROM juridico_pareceres
            WHERE CAST(id AS TEXT) = :id
            """
        ),
        {"id": str(id)},
    )
    r = row.mappings().first()
    if not r:
        return None
    return {
        "id": r["id"],
        "area": r["area"],
        "titulo": r["titulo"],
        "contexto": r["contexto"],
        "parecer": r["parecer"],
        "conclusao": r["conclusao"],
        "escalonar": bool(r["escalonar"]),
        "status": r["status"],
        "pdf_path": r["pdf_path"],
        "created_by": r["created_by"],
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "disclaimer": _DISCLAIMER,
    }


# ── PDF padrão-ouro (pdf_branding) ───────────────────────────────────────────
def gerar_pdf_parecer(parecer_dict: dict[str, Any]) -> bytes:
    """Gera o PDF do parecer no padrão-ouro Conecta Mais (pdf_branding).

    Cabeçalho/rodapé oficiais, seções, DISCLAIMER no rodapé do corpo e campo de assinatura
    digital do responsável jurídico (empresa).
    """
    import io

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services import pdf_branding as B

    st = B.styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=40 * mm,
        bottomMargin=16 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
    )
    W = A4[0] - 32 * mm
    story: list = []

    area = str(parecer_dict.get("area", "")).upper() or "—"
    titulo = parecer_dict.get("titulo", "—")
    created_at = parecer_dict.get("created_at")
    if isinstance(created_at, datetime):
        data_str = created_at.strftime("%d/%m/%Y")
    elif isinstance(created_at, str) and created_at:
        data_str = created_at[:10]
    else:
        data_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    def _p(txt: str, style_key: str = "corpo"):
        # preserva quebras de parágrafo do texto do LLM
        safe = (str(txt) or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace("\n", "<br/>")
        return Paragraph(safe, st[style_key])

    # ── Cabeçalho do documento (metadados) ──
    meta = Table(
        [
            [Paragraph("<b>Área</b>", st["cell"]), Paragraph(area, st["cell"]),
             Paragraph("<b>Data</b>", st["cell"]), Paragraph(data_str, st["cell"])],
            [Paragraph("<b>Título</b>", st["cell"]), Paragraph(str(titulo), st["cell"]),
             Paragraph("<b>Status</b>", st["cell"]),
             Paragraph(str(parecer_dict.get("status", "rascunho")).upper(), st["cell"])],
        ],
        colWidths=[24 * mm, W / 2 - 24 * mm, 24 * mm, W / 2 - 24 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (0, -1), B.FUNDO_CLARO),
                ("BACKGROUND", (2, 0), (2, -1), B.FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 5 * mm))

    # ── Seções do parecer ──
    relatorio = parecer_dict.get("relatorio")
    fundamentacao = parecer_dict.get("fundamentacao")
    conclusao = parecer_dict.get("conclusao")
    corpo = parecer_dict.get("parecer")

    if relatorio or fundamentacao or conclusao:
        if relatorio:
            story += B.secao("I. RELATÓRIO", st)
            story.append(_p(relatorio))
            story.append(Spacer(1, 3 * mm))
        if fundamentacao:
            story += B.secao("II. FUNDAMENTAÇÃO", st)
            story.append(_p(fundamentacao))
            story.append(Spacer(1, 3 * mm))
        if conclusao:
            story += B.secao("III. CONCLUSÃO", st)
            story.append(_p(conclusao))
    elif corpo:
        story += B.secao("PARECER", st)
        story.append(_p(corpo))
    else:
        story += B.secao("PARECER", st)
        story.append(_p("Parecer não disponível — IA indisponível no momento da geração."))

    # flag de escalonamento
    if parecer_dict.get("escalonar"):
        story.append(Spacer(1, 4 * mm))
        alerta = Table(
            [[Paragraph(
                "<b>ESCALONAMENTO RECOMENDADO:</b> este parecer envolve matéria sensível ou "
                "informação insuficiente. Encaminhe ao advogado responsável antes de qualquer decisão.",
                ParagraphStyle("al", parent=st["corpo"], textColor=colors.HexColor("#B45309")),
            )]],
            colWidths=[W],
        )
        alerta.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.8, B.LARANJA),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7ED")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(alerta)

    # ── DISCLAIMER (rodapé do corpo) ──
    story.append(Spacer(1, 5 * mm))
    disc = Table(
        [[Paragraph(
            f'<font size="7.5" color="#6B7280"><b>AVISO LEGAL: </b>{_DISCLAIMER}</font>',
            ParagraphStyle("disc", parent=st["small"], fontSize=7.5, leading=10),
        )]],
        colWidths=[W],
    )
    disc.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9E1F2")),
                ("BACKGROUND", (0, 0), (-1, -1), B.FUNDO_CLARO),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(disc)

    # ── Assinatura digital do responsável jurídico (empresa) ──
    story += B.campos_assinatura(
        st,
        responsavel_cargo="Responsável Jurídico",
        data_str=data_str,
        digital_empresa=True,
        data_empresa=data_str,
        funcionario_label="Ciente / Solicitante",
        espaco_antes=8,
    )

    doc.build(
        story,
        onFirstPage=lambda cv, dc: B.header_footer(cv, dc, titulo="PARECER JURÍDICO", seal_watermark=True),
        onLaterPages=lambda cv, dc: B.header_footer(cv, dc, titulo="PARECER JURÍDICO", seal_watermark=True),
    )
    return buf.getvalue()
