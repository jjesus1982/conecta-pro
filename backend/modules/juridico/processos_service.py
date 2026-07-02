"""Intake de Processos — o Escritório Jurídico IA recebe um processo (trabalhista/cível/
tributário), extrai as partes e pedidos, VARRE o ERP inteiro montando o dossiê probatório
do sujeito e produz uma ANÁLISE DE DEFESA fundamentada no dado real do sistema.

Fluxo:
  1. Recebe o texto do processo (PDF extraído ou colado).
  2. IA extrai entidades: reclamante (nome/CPF), tipo, período, PEDIDOS.
  3. Resolve o funcionário e monta o dossiê via context_engine (dado real, cross-módulo).
  4. IA cruza cada PEDIDO com as provas do dossiê → provas favoráveis, lacunas, risco,
     recomendação; síntese e estratégia geral. Escala ao escritório se alto risco.
  5. Persiste em juridico_processos.

Princípios: IA assiste e fundamenta, humano/escritório certifica. Nunca inventa prova —
usa só o que o context_engine encontrou (veracidade). Sem IA/chave → registra honesto.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.juridico import context_engine as CE
from modules.juridico.parecer_service import _chamar_llm, _parse_json_llm

logger = logging.getLogger(__name__)

TIPOS = {"trabalhista", "civel", "tributaria"}

_DISCLAIMER = (
    "Esta análise é gerada por IA a partir dos dados do próprio ERP (dado real) e serve como "
    "apoio à defesa — NÃO substitui o advogado responsável. Peças, prazos e teses devem ser "
    "revisados e certificados pelo escritório antes de qualquer protocolo."
)


def _reparar_json(raw: str) -> dict[str, Any] | None:
    """Tenta recuperar um JSON truncado (fecha colchetes/chaves abertos). Best-effort."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s.strip("`")
        s = s.removeprefix("json").strip()
    ini = s.find("{")
    if ini == -1:
        return None
    s = s[ini:]
    # remove possível vírgula/fragmento final e fecha estruturas abertas
    for corte in range(len(s), max(0, len(s) - 400), -1):
        frag = s[:corte].rstrip().rstrip(",")
        fechar = []
        dentro_str = False
        esc = False
        for ch in frag:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                dentro_str = not dentro_str
            elif not dentro_str and ch in "{[":
                fechar.append("}" if ch == "{" else "]")
            elif not dentro_str and ch in "}]":
                if fechar:
                    fechar.pop()
        if dentro_str:
            frag += '"'
        candidato = frag + "".join(reversed(fechar))
        try:
            return json.loads(candidato)
        except Exception:  # noqa: BLE001
            continue
    return None


# ── extração de texto do PDF ─────────────────────────────────────────────────
def extrair_texto_pdf(data: bytes) -> str:
    """Extrai texto de um PDF (PyMuPDF). Devolve '' se falhar."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        partes = [pag.get_text() for pag in doc]
        doc.close()
        return "\n".join(partes).strip()
    except Exception as e:  # noqa: BLE001
        logger.error("Falha ao extrair PDF do processo: %s", e)
        return ""


# ── tabela ───────────────────────────────────────────────────────────────────
async def _ensure_table(db: AsyncSession) -> None:
    await db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS juridico_processos (
            id             SERIAL PRIMARY KEY,
            numero         TEXT,
            tipo           VARCHAR(20) NOT NULL DEFAULT 'trabalhista',
            reclamante     TEXT,
            reclamante_cpf VARCHAR(20),
            employee_id    VARCHAR(64),
            pedidos        JSONB,
            entidades      JSONB,
            dossie_resumo  JSONB,
            analise        JSONB,
            escalonar      BOOLEAN NOT NULL DEFAULT FALSE,
            status         VARCHAR(30) NOT NULL DEFAULT 'analisado',
            texto_len      INTEGER,
            created_by     VARCHAR(64),
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))
    await db.execute(text("ALTER TABLE juridico_processos ALTER COLUMN status TYPE VARCHAR(40)"))


# ── resumo compacto do dossiê para a IA ──────────────────────────────────────
def _resumir_dossie(dossie: dict[str, Any]) -> dict[str, Any]:
    """Condensa o dossiê em um mapa {secao: {disponivel, total, prova, amostra}} para a IA."""
    out: dict[str, Any] = {}
    for nome, sec in (dossie.get("secoes") or {}).items():
        if not isinstance(sec, dict):
            continue
        amostra = None
        itens = sec.get("itens") or []
        if itens:
            it = itens[0]
            amostra = {k: it[k] for k in list(it)[:8]}
        out[nome] = {
            "disponivel": sec.get("disponivel"),
            "total": sec.get("total"),
            "prova": sec.get("prova"),
            "amostra": amostra,
        }
    return out


# ── prompts ──────────────────────────────────────────────────────────────────
def _prompt_extracao() -> str:
    return (
        "Você é assistente jurídico. Leia a petição/processo e EXTRAIA os dados objetivos. "
        "Responda SOMENTE um JSON válido no formato:\n"
        "{\n"
        '  "reclamante": "nome do reclamante/autor (pessoa que processa)",\n'
        '  "reclamante_cpf": "CPF só dígitos, ou null",\n'
        '  "tipo_acao": "trabalhista|civel|tributaria",\n'
        '  "periodo": "período do vínculo/fatos se citado, ou null",\n'
        '  "pedidos": ["cada pedido/verba pleiteada como item de lista (ex.: horas extras, '
        'adicional noturno, verbas rescisórias, danos morais, adicional de insalubridade)"]\n'
        "}\n"
        "Não invente. Se algo não constar, use null ou lista vazia."
    )


def _prompt_defesa(area: str) -> str:
    return (
        f"Você é o advogado interno (área {area}) da CONECTA MAIS, empresa de segurança/portaria. "
        "Recebeu um processo contra a empresa e um DOSSIÊ com as provas REAIS existentes no ERP "
        "(cada seção indica se há dado 'disponivel', a contagem e o que aquela fonte prova). "
        "Cruze CADA pedido do processo com as provas do dossiê. Baseie-se SOMENTE nas provas "
        "listadas — se uma prova essencial não está disponível, aponte como LACUNA/risco (não "
        "invente que existe). Cite artigos (CLT/CCT/CDC/lei) apenas se seguro.\n"
        "Responda SOMENTE um JSON válido:\n"
        "{\n"
        '  "por_pedido": [\n'
        '    {"pedido": "...", "provas_favoraveis": ["seções/provas do dossiê que defendem"],\n'
        '     "provas_faltantes": ["o que falta e precisa ser buscado/produzido"],\n'
        '     "como_obter": ["onde/como conseguir cada prova faltante: módulo do ERP, contador/Domínio, '
        'portal do governo (eSocial/FGTS/NFS-e), extrato bancário, testemunha, etc."],\n'
        '     "risco": "baixo|medio|alto", "recomendacao": "ação prática objetiva"}\n'
        "  ],\n"
        '  "estrategia_geral": "tese central e ordem de defesa (texto)",\n'
        '  "documentos_a_juntar": ["documentos a juntar na contestação — marque (ERP) se já existe no sistema '
        'ou (OBTER) se precisa ser conseguido"],\n'
        '  "prazo_critico": "audiência/prazo de defesa se constar nos autos, ou null",\n'
        '  "sintese": "avaliação global e probabilidade de êxito da defesa (texto)",\n'
        '  "escalonar": true|false\n'
        "}\n"
    )


# ── análise principal ────────────────────────────────────────────────────────
async def analisar_processo(
    db: AsyncSession,
    texto: str,
    numero: str | None,
    tipo: str | None,
    user_id: str | None,
    employee_hint: str | None = None,
) -> dict[str, Any]:
    """Analisa um processo: extrai entidades, monta dossiê real e produz análise de defesa."""
    await _ensure_table(db)
    tipo = (tipo or "trabalhista").strip().lower()
    if tipo not in TIPOS:
        tipo = "trabalhista"
    texto = (texto or "").strip()

    if len(texto) < 40 and not employee_hint:
        return {"ok": False, "mensagem": "Texto do processo insuficiente para análise."}

    # 1) extração de entidades
    entidades: dict[str, Any] = {}
    ex = await _chamar_llm(_prompt_extracao(), texto[:15000], max_tokens=1500)
    if ex:
        entidades = _parse_json_llm(ex["content"]) or {}
    if entidades.get("tipo_acao") in TIPOS:
        tipo = entidades["tipo_acao"]

    # 2) resolver funcionário (hint > cpf > nome)
    alvo = employee_hint or entidades.get("reclamante_cpf") or entidades.get("reclamante") or ""
    dossie = await CE.dossie_funcionario(db, alvo) if alvo else {"encontrado": False}
    achou = bool(dossie.get("encontrado"))

    funcionario = dossie.get("funcionario") if achou else None
    eid = str(funcionario["id"]) if funcionario else None
    dossie_resumo = _resumir_dossie(dossie) if achou else {}

    # panorama da empresa (regularidade FGTS/INSS/CND) — sempre útil p/ defesa
    try:
        panorama = await CE.panorama_empresa(db)
        panorama_compacto = {k: {"disponivel": v.get("disponivel"), "total": v.get("total"),
                                 "amostra": (v.get("itens") or [{}])[0]}
                             for k, v in (panorama.get("secoes") or {}).items()}
    except Exception:  # noqa: BLE001
        panorama_compacto = {}

    # 3) análise de defesa cruzando pedidos x provas reais (roda mesmo sem achar o sujeito)
    analise: dict[str, Any] = {}
    escalonar = True
    contexto_ia = {
        "processo": {"numero": numero, "tipo": tipo,
                     "reclamante": entidades.get("reclamante"),
                     "periodo": entidades.get("periodo"),
                     "pedidos": entidades.get("pedidos") or []},
        "sujeito_encontrado_no_erp": achou,
        "funcionario": ({k: funcionario.get(k) for k in
                         ("nome", "cargo", "data_admissao", "data_demissao", "salario_base")}
                        if funcionario else None),
        "dossie_provas": dossie_resumo,
        "panorama_empresa": panorama_compacto,
        "observacao_vinculo": (
            None if achou else
            "ATENÇÃO: o reclamante NÃO consta na base de EMPREGADOS CLT do ERP. Em ação de "
            "reconhecimento de vínculo/pejotização isso é central: analise a tese de INEXISTÊNCIA "
            "de vínculo empregatício (prestação autônoma via CNPJ próprio). Oriente onde buscar as "
            "provas (contrato de prestação de serviços PJ; NFS-e emitidas pelo prestador; "
            "comprovantes de pagamento a ele como FORNECEDOR no módulo Financeiro/contas a pagar; "
            "ausência de exclusividade/subordinação; e-mails/ordens). Se as provas não estiverem no "
            "ERP, indique a fonte externa (contador/Domínio, portal da NFS-e, extratos bancários)."
        ),
    }
    an = await _chamar_llm(
        _prompt_defesa(tipo),
        "Analise a defesa cruzando os pedidos com as provas do dossiê e o panorama.\n\n"
        + json.dumps(contexto_ia, ensure_ascii=False, default=str),
        max_tokens=8000,
    )
    if an:
        analise = _parse_json_llm(an["content"]) or _reparar_json(an["content"]) or {}
        escalonar = bool(analise.get("escalonar", achou is False))
    else:
        analise = {"sintese": "IA indisponível — dossiê/panorama montados, análise textual pendente."}

    status = "analisado" if achou else "nao_localizado_clt"

    # 4) persistir
    row = await db.execute(text(
        """
        INSERT INTO juridico_processos
            (numero, tipo, reclamante, reclamante_cpf, employee_id, pedidos, entidades,
             dossie_resumo, analise, escalonar, status, texto_len, created_by)
        VALUES
            (:numero, :tipo, :recl, :cpf, :eid, :pedidos, :entidades, :dossie, :analise,
             :escalonar, :status, :tlen, :cby)
        RETURNING id, created_at
        """),
        {
            "numero": numero, "tipo": tipo,
            "recl": entidades.get("reclamante"),
            "cpf": entidades.get("reclamante_cpf"),
            "eid": eid,
            "pedidos": json.dumps(entidades.get("pedidos") or [], ensure_ascii=False),
            "entidades": json.dumps(entidades, ensure_ascii=False, default=str),
            "dossie": json.dumps(dossie_resumo, ensure_ascii=False, default=str),
            "analise": json.dumps(analise, ensure_ascii=False, default=str),
            "escalonar": escalonar, "status": status,
            "tlen": len(texto), "cby": str(user_id) if user_id else None,
        },
    )
    rec = row.mappings().first()

    return {
        "ok": True,
        "id": rec["id"],
        "numero": numero,
        "tipo": tipo,
        "status": status,
        "entidades": entidades,
        "funcionario": funcionario,
        "dossie": dossie if dossie.get("encontrado") else {"encontrado": False},
        "dossie_resumo": dossie_resumo,
        "analise": analise,
        "escalonar": escalonar,
        "disclaimer": _DISCLAIMER,
        "created_at": rec["created_at"].isoformat() if rec.get("created_at") else None,
    }


CQB_EMAIL = "contato@cqbadvogados.com.br"
CQB_NOME = "CQB Advogados e Associados"


def _html_email_cqb(p: dict[str, Any]) -> str:
    """Monta o corpo HTML do encaminhamento ao escritório CQB a partir do processo persistido."""
    ent = p.get("entidades") or {}
    an = p.get("analise") or {}
    if isinstance(ent, str):
        ent = json.loads(ent or "{}")
    if isinstance(an, str):
        an = json.loads(an or "{}")

    def esc(t: Any) -> str:
        return (str(t or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    linhas = []
    for pp in (an.get("por_pedido") or []):
        fav = "".join(f"<li>{esc(x)}</li>" for x in (pp.get("provas_favoraveis") or [])) or "<li><i>—</i></li>"
        falt = "".join(f"<li>{esc(x)}</li>" for x in (pp.get("provas_faltantes") or [])) or "<li><i>—</i></li>"
        obt = "".join(f"<li>{esc(x)}</li>" for x in (pp.get("como_obter") or [])) or "<li><i>—</i></li>"
        linhas.append(
            f"<div style='margin:14px 0;padding:12px;border:1px solid #E2E8F0;border-radius:8px'>"
            f"<div style='font-weight:600'>{esc(pp.get('pedido'))} "
            f"<span style='color:#B45309;font-size:12px'>[risco: {esc(pp.get('risco'))}]</span></div>"
            f"<div style='color:#166534;margin-top:6px'><b>Provas favoráveis</b><ul>{fav}</ul></div>"
            f"<div style='color:#B91C1C'><b>Lacunas / a produzir</b><ul>{falt}</ul></div>"
            f"<div style='color:#1D4ED8'><b>Como obter</b><ul>{obt}</ul></div>"
            f"<div style='background:#EFF6FF;padding:8px;border-radius:6px'><b>Recomendação:</b> "
            f"{esc(pp.get('recomendacao'))}</div></div>"
        )
    docs = "".join(f"<li>{esc(x)}</li>" for x in (an.get("documentos_a_juntar") or []))
    return (
        f"<div style='font-family:Arial,sans-serif;color:#1F2937;max-width:720px'>"
        f"<h2 style='color:#1E3A8A'>Encaminhamento de Processo — Conecta Mais</h2>"
        f"<p>Prezados <b>{esc(CQB_NOME)}</b>,</p>"
        f"<p>Encaminhamos o processo abaixo com o <b>dossiê e a análise de defesa preliminar</b> "
        f"produzidos internamente pelo nosso Jurídico, para vossa apreciação e condução.</p>"
        f"<table style='font-size:14px;margin:10px 0'>"
        f"<tr><td style='padding:2px 8px'><b>Processo</b></td><td>{esc(p.get('numero') or '—')}</td></tr>"
        f"<tr><td style='padding:2px 8px'><b>Área</b></td><td>{esc(p.get('tipo'))}</td></tr>"
        f"<tr><td style='padding:2px 8px'><b>Reclamante</b></td><td>{esc(ent.get('reclamante') or p.get('reclamante'))}</td></tr>"
        f"<tr><td style='padding:2px 8px'><b>Prazo crítico</b></td><td>{esc(an.get('prazo_critico') or '—')}</td></tr>"
        f"</table>"
        f"<h3 style='color:#1E3A8A'>Estratégia de defesa (tese central)</h3>"
        f"<p style='white-space:pre-line'>{esc(an.get('estrategia_geral'))}</p>"
        f"<h3 style='color:#1E3A8A'>Análise por pedido</h3>{''.join(linhas)}"
        + (f"<h3 style='color:#1E3A8A'>Documentos a juntar</h3><ul>{docs}</ul>" if docs else "")
        + f"<h3 style='color:#1E3A8A'>Síntese</h3><p style='white-space:pre-line'>{esc(an.get('sintese'))}</p>"
        f"<hr style='border:none;border-top:1px solid #E5E7EB;margin:16px 0'>"
        f"<p style='font-size:12px;color:#6B7280'>{esc(_DISCLAIMER)} Documento gerado pelo "
        f"Escritório Jurídico IA do Conecta PRO. O dossiê completo está disponível no sistema.</p>"
        f"</div>"
    )


async def preparar_ou_enviar_cqb(
    db: AsyncSession, id: str, confirmar: bool, destinatario: str | None = None
) -> dict[str, Any]:
    """Prévia (confirmar=False) ou ENVIO real (confirmar=True) do processo ao CQB por e-mail."""
    p = await obter_processo(db, id)
    if not p:
        return {"ok": False, "mensagem": "Processo não encontrado"}
    destino = (destinatario or CQB_EMAIL).strip()
    assunto = f"[Conecta Mais] Encaminhamento de processo {p.get('numero') or ('#' + str(p['id']))} — defesa preliminar"
    html = _html_email_cqb(p)

    if not confirmar:
        return {"ok": True, "preview": True, "destinatario": destino, "assunto": assunto,
                "html": html, "aviso": "Prévia — nada foi enviado. Envie com confirmar=true."}

    # envio real (validado: core/mailer, remetente noreply@conectamais.pro)
    try:
        from core.mailer import send_email
        enviado = await send_email(destino, assunto, html)
    except Exception as e:  # noqa: BLE001
        logger.error("Falha ao enviar processo ao CQB: %s", e)
        return {"ok": False, "mensagem": f"Falha no envio: {e}"}
    if enviado:
        try:
            await db.execute(text(
                "UPDATE juridico_processos SET status='encaminhado_cqb' WHERE CAST(id AS TEXT)=:id"),
                {"id": str(id)})
        except Exception:  # noqa: BLE001
            pass
    return {"ok": bool(enviado), "enviado": bool(enviado), "destinatario": destino,
            "assunto": assunto, "mensagem": "Encaminhado ao CQB." if enviado else "SMTP não confirmou o envio."}


async def listar_processos(db: AsyncSession, limit: int = 50) -> list[dict[str, Any]]:
    await _ensure_table(db)
    rows = await db.execute(text(
        "SELECT id, numero, tipo, reclamante, employee_id, status, escalonar, created_at "
        "FROM juridico_processos ORDER BY created_at DESC LIMIT :l"), {"l": int(limit)})
    out = []
    for r in rows.mappings().all():
        out.append({
            "id": r["id"], "numero": r["numero"], "tipo": r["tipo"],
            "reclamante": r["reclamante"], "employee_id": r["employee_id"],
            "status": r["status"], "escalonar": bool(r["escalonar"]),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return out


async def obter_processo(db: AsyncSession, id: str) -> dict[str, Any] | None:
    await _ensure_table(db)
    row = await db.execute(text(
        "SELECT id, numero, tipo, reclamante, reclamante_cpf, employee_id, pedidos, entidades, "
        "dossie_resumo, analise, escalonar, status, created_at "
        "FROM juridico_processos WHERE CAST(id AS TEXT)=:id"), {"id": str(id)})
    r = row.mappings().first()
    if not r:
        return None
    return {
        "id": r["id"], "numero": r["numero"], "tipo": r["tipo"],
        "reclamante": r["reclamante"], "reclamante_cpf": r["reclamante_cpf"],
        "employee_id": r["employee_id"], "pedidos": r["pedidos"], "entidades": r["entidades"],
        "dossie_resumo": r["dossie_resumo"], "analise": r["analise"],
        "escalonar": bool(r["escalonar"]), "status": r["status"],
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "disclaimer": _DISCLAIMER,
    }
