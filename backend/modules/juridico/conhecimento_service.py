"""Base de Conhecimento + Playbook do Jurídico Conecta Mais.

Duas capacidades que fazem o Jurídico IA "aprender" a realidade da empresa:

1. BASE DE CONHECIMENTO (juridico_conhecimento) — precedentes/pareceres/teses da PRÓPRIA
   empresa (casos reais e seus desfechos). A IA recupera os relevantes ao analisar um caso
   novo — passa a citar a experiência da Conecta Mais, não só a lei genérica.

2. PLAYBOOK (juridico_playbook) — o "como agir" por tipo de situação, codificado a partir
   dos procedimentos reais (ex.: abandono → carta de comparecimento 72h → justa causa art.482).

Recuperação simples por ÁREA + sobreposição de palavras-chave (RAG-lite, sem vetores).
Injetável no prompt do consultor e da análise de processos.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ── tabelas ──────────────────────────────────────────────────────────────────
async def ensure_tables(db: AsyncSession) -> None:
    await db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS juridico_conhecimento (
            id             SERIAL PRIMARY KEY,
            tipo           VARCHAR(20) NOT NULL DEFAULT 'precedente',
            area           VARCHAR(20) NOT NULL,
            titulo         TEXT NOT NULL,
            palavras_chave TEXT,
            resumo         TEXT,
            fundamentacao  TEXT,
            desfecho       TEXT,
            fonte          TEXT,
            ativo          BOOLEAN NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))
    await db.execute(text(
        """
        CREATE TABLE IF NOT EXISTS juridico_playbook (
            id             SERIAL PRIMARY KEY,
            situacao       TEXT NOT NULL,
            area           VARCHAR(20) NOT NULL,
            gatilho        TEXT,
            passos         JSONB,
            base_legal     TEXT,
            documentos     JSONB,
            ativo          BOOLEAN NOT NULL DEFAULT TRUE,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    ))


# ── seed a partir dos casos/documentos REAIS ────────────────────────────────
_CONHECIMENTO_SEED = [
    {
        "tipo": "precedente", "area": "trabalhista",
        "titulo": "Pejotização — reclamação de reconhecimento de vínculo (Ermeson x Conecta Mais)",
        "palavras_chave": "pejotizacao, vinculo, reconhecimento de vinculo, pj, pessoa juridica, tecnico seguranca eletronica, subordinacao, cnpj",
        "resumo": "Ex-prestador PJ pleiteia reconhecimento de vínculo (08/03/2023–20/09/2025) + verbas. Alega pessoalidade, subordinação, habitualidade e onerosidade; que a CTPS não foi anotada.",
        "fundamentacao": "Art. 2º e 3º da CLT (requisitos do vínculo: pessoalidade, onerosidade, habitualidade, subordinação). Súmula 363 do TST. Defesa: demonstrar autonomia (NFS-e emitidas pelo prestador, pagamentos como fornecedor, ausência de subordinação/exclusividade).",
        "desfecho": "Em andamento — processo 0000338-26.2026.5.11.0003 (TRT-11, 3ª VT Manaus), audiência 10/06/2026, valor R$ 72.862,80. Encaminhado ao CQB.",
        "fonte": "Processo 0000338-26.2026.5.11.0003",
    },
    {
        "tipo": "precedente", "area": "trabalhista",
        "titulo": "Justa causa por abandono de emprego (Thais / Fernanda)",
        "palavras_chave": "abandono, abandono de emprego, faltas consecutivas, carta de comparecimento, justa causa, sumico",
        "resumo": "Empregadas faltaram consecutivamente sem justificativa. Empresa enviou carta de comparecimento com prazo de 72h antes de configurar abandono.",
        "fundamentacao": "Art. 482, 'i', da CLT (abandono de emprego). Súmula 32 do TST (presunção de abandono após 30 dias). A carta de comparecimento (notificação para retorno) é a prova da tentativa de reintegração antes da justa causa.",
        "desfecho": "Cartas de comparecimento emitidas (Thais 10/05/2026; Fernanda 03/05/2026). Base para rescisão por justa causa se persistir a ausência.",
        "fonte": "Cartas de comparecimento — abandono (DP)",
    },
    {
        "tipo": "precedente", "area": "trabalhista",
        "titulo": "Gradação de penalidades disciplinares (Thais Ferreira Matos)",
        "palavras_chave": "advertencia, suspensao, gradacao, indisciplina, insubordinacao, transferencia de posto, poder diretivo, disciplinar",
        "resumo": "Sequência disciplinar: advertência (negligência no controle de acesso), advertência (falta/ronda), suspensão (recusa de assinar transferência de posto), carta de abandono.",
        "fundamentacao": "Art. 482 da CLT (justa causa por gradação). Art. 469 da CLT (transferência é exercício regular do poder diretivo quando não lesiva). A gradação documentada sustenta a proporcionalidade da penalidade.",
        "desfecho": "4 medidas registradas (07/2025 a 05/2026). Histórico robusto para eventual justa causa.",
        "fonte": "Advertências e suspensão (DP) — Thais Ferreira Matos",
    },
    {
        "tipo": "precedente", "area": "trabalhista",
        "titulo": "Rescisão indireta ajuizada pelo empregado (Júlio César / Aryelton)",
        "palavras_chave": "rescisao indireta, art 483, falta grave do empregador, suspensao contratual, esocial motivo 44, esocial motivo 17",
        "resumo": "Empregados ajuizaram rescisão indireta. No eSocial gera suspensão contratual (motivo 44) durante a demanda; desligamento por rescisão indireta é motivo 17.",
        "fundamentacao": "Art. 483 da CLT (rescisão indireta por falta grave do empregador). Efeitos equiparados à dispensa sem justa causa (aviso, 13º, férias, FGTS+40%) SE reconhecida. Defesa: comprovar cumprimento das obrigações (pagamentos, jornada, condições).",
        "desfecho": "Júlio: desligamento 02/03/2026 (proc. 0001524-18.2025.5.11.0004). Aryelton: suspensão contratual desde 02/02/2026, audiência em julho/2026.",
        "fonte": "TRCT Júlio César + eSocial (afastamento Aryelton)",
    },
]

_PLAYBOOK_SEED = [
    {
        "situacao": "Abandono de emprego (faltas consecutivas sem justificativa)",
        "area": "trabalhista",
        "gatilho": "abandono, faltas consecutivas, empregado sumiu, nao comparece, faltou varios dias",
        "passos": [
            "Registrar formalmente as faltas no controle de ponto (datas exatas).",
            "Enviar CARTA DE COMPARECIMENTO por meio rastreável (telegrama/AR ou notificação com testemunhas), concedendo prazo de 72h para justificar.",
            "Aguardar o prazo; documentar a ausência de resposta.",
            "Configurar o abandono: elemento objetivo (>30 dias — Súmula 32 TST) + elemento subjetivo (ânimo de não retornar).",
            "Formalizar a rescisão por JUSTA CAUSA (art. 482, 'i', CLT) e registrar no eSocial (S-2299 motivo próprio).",
        ],
        "base_legal": "Art. 482, 'i', da CLT; Súmula 32 do TST.",
        "documentos": ["Carta de comparecimento (72h)", "Registro de ponto com as faltas", "Termo de rescisão por justa causa"],
    },
    {
        "situacao": "Aplicação de penalidade disciplinar (gradação)",
        "area": "trabalhista",
        "gatilho": "advertencia, suspensao, indisciplina, insubordinacao, penalidade, punir empregado",
        "passos": [
            "Apurar o fato com objetividade (data, hora, local, testemunhas).",
            "Aplicar a penalidade proporcional: advertência verbal → advertência escrita → suspensão → justa causa.",
            "Documentar por escrito, com ciência do empregado (ou recusa registrada por 2 testemunhas).",
            "Guardar o histórico — a gradação sustenta a proporcionalidade e futura justa causa.",
        ],
        "base_legal": "Art. 482 da CLT; princípios da imediatidade, proporcionalidade e non bis in idem.",
        "documentos": ["Carta de advertência", "Comunicação de suspensão", "Registro de testemunhas"],
    },
    {
        "situacao": "Transferência de posto de trabalho",
        "area": "trabalhista",
        "gatilho": "transferencia, mudanca de posto, remanejamento, realocacao",
        "passos": [
            "Verificar se a transferência é lícita (sem alteração lesiva — mesma função/salário/jornada).",
            "Comunicar formalmente ao empregado, colhendo ciência.",
            "Se houver recusa injustificada, registrar como indisciplina (a transferência regular é exercício do poder diretivo).",
        ],
        "base_legal": "Art. 469 da CLT (transferência); art. 468 (vedação de alteração lesiva).",
        "documentos": ["Comunicação de transferência", "Termo de ciência"],
    },
    {
        "situacao": "Defesa em rescisão indireta ajuizada pelo empregado",
        "area": "trabalhista",
        "gatilho": "rescisao indireta, art 483, falta grave do empregador, empregado processou pedindo rescisao",
        "passos": [
            "Identificar as faltas graves alegadas (atraso salarial, condições, assédio, etc.).",
            "Reunir provas do CUMPRIMENTO das obrigações: holerites, comprovantes de pagamento (PIX), ponto, EPIs.",
            "Demonstrar a ausência de falta grave contínua e imediata.",
            "Se a rescisão indireta for improcedente, o pedido de verbas cai; se procedente, equivale a dispensa sem justa causa.",
        ],
        "base_legal": "Art. 483 da CLT.",
        "documentos": ["Holerites", "Comprovantes de pagamento", "Espelho de ponto", "Fichas de EPI"],
    },
    {
        "situacao": "Defesa em reclamação de reconhecimento de vínculo (pejotização)",
        "area": "trabalhista",
        "gatilho": "pejotizacao, reconhecimento de vinculo, ex-pj processou, vinculo empregaticio, pj",
        "passos": [
            "Reunir o contrato de prestação de serviços PJ (se houver).",
            "Levantar as NFS-e emitidas pelo prestador e os pagamentos a ele como FORNECEDOR (módulo Financeiro/Contas a Pagar).",
            "Demonstrar a ausência dos requisitos do vínculo: sem pessoalidade (podia se fazer substituir), sem subordinação, sem exclusividade, sem controle de jornada.",
            "Se o vínculo for reconhecido, ter os cálculos de compensação (o que já foi pago) prontos.",
        ],
        "base_legal": "Arts. 2º e 3º da CLT; Súmula 363 do TST.",
        "documentos": ["Contrato de prestação de serviços PJ", "NFS-e do prestador", "Comprovantes de pagamento como fornecedor"],
    },
]


async def seed_inicial(db: AsyncSession) -> dict[str, int]:
    """Semeia conhecimento e playbook (idempotente por título/situação)."""
    await ensure_tables(db)
    nc = 0
    for k in _CONHECIMENTO_SEED:
        ex = await db.execute(text("SELECT 1 FROM juridico_conhecimento WHERE titulo=:t"), {"t": k["titulo"]})
        if ex.first():
            continue
        await db.execute(text(
            "INSERT INTO juridico_conhecimento (tipo,area,titulo,palavras_chave,resumo,fundamentacao,desfecho,fonte) "
            "VALUES (:tipo,:area,:titulo,:palavras_chave,:resumo,:fundamentacao,:desfecho,:fonte)"), k)
        nc += 1
    npb = 0
    for p in _PLAYBOOK_SEED:
        ex = await db.execute(text("SELECT 1 FROM juridico_playbook WHERE situacao=:s"), {"s": p["situacao"]})
        if ex.first():
            continue
        await db.execute(text(
            "INSERT INTO juridico_playbook (situacao,area,gatilho,passos,base_legal,documentos) "
            "VALUES (:situacao,:area,:gatilho,CAST(:passos AS jsonb),:base_legal,CAST(:documentos AS jsonb))"),
            {**p, "passos": json.dumps(p["passos"], ensure_ascii=False),
             "documentos": json.dumps(p["documentos"], ensure_ascii=False)})
        npb += 1
    return {"conhecimento_novos": nc, "playbook_novos": npb}


# ── recuperação (RAG-lite: área + sobreposição de palavras) ─────────────────
def _tokens(txt: str) -> set[str]:
    return {t for t in re.findall(r"[a-zà-ú0-9]{4,}", (txt or "").lower())}


async def buscar_conhecimento(db: AsyncSession, area: str, texto: str, limit: int = 3) -> list[dict[str, Any]]:
    await ensure_tables(db)
    rows = await db.execute(text(
        "SELECT tipo,area,titulo,palavras_chave,resumo,fundamentacao,desfecho,fonte "
        "FROM juridico_conhecimento WHERE ativo AND (area=:a OR :a='') "), {"a": (area or "").lower()})
    alvo = _tokens(texto)
    scored = []
    for r in rows.mappings().all():
        kw = _tokens((r["palavras_chave"] or "") + " " + (r["titulo"] or "") + " " + (r["resumo"] or ""))
        score = len(alvo & kw)
        if score:
            scored.append((score, dict(r)))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:limit]]


async def buscar_playbook(db: AsyncSession, area: str, texto: str, limit: int = 3) -> list[dict[str, Any]]:
    await ensure_tables(db)
    rows = await db.execute(text(
        "SELECT situacao,area,gatilho,passos,base_legal,documentos FROM juridico_playbook "
        "WHERE ativo AND (area=:a OR :a='')"), {"a": (area or "").lower()})
    alvo = _tokens(texto)
    scored = []
    for r in rows.mappings().all():
        kw = _tokens((r["gatilho"] or "") + " " + (r["situacao"] or ""))
        score = len(alvo & kw)
        if score:
            scored.append((score, dict(r)))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:limit]]


async def contexto_para_prompt(db: AsyncSession, area: str, texto: str) -> str:
    """Monta um bloco de texto com precedentes + playbook relevantes, para injetar no LLM."""
    try:
        prec = await buscar_conhecimento(db, area, texto, limit=3)
        play = await buscar_playbook(db, area, texto, limit=2)
    except Exception:  # noqa: BLE001
        return ""
    if not prec and not play:
        return ""
    partes = ["\n\n=== BASE DE CONHECIMENTO DA CONECTA MAIS (precedentes e procedimentos internos) ==="]
    partes.append("Use isto como a EXPERIÊNCIA da própria empresa; cite quando pertinente.")
    for p in prec:
        partes.append(
            f"\n[PRECEDENTE] {p['titulo']}\n  Resumo: {p['resumo']}\n  Fundamentação: {p['fundamentacao']}"
            f"\n  Desfecho: {p['desfecho']}")
    for pb in play:
        passos = pb.get("passos")
        if isinstance(passos, str):
            passos = json.loads(passos or "[]")
        passos_txt = "; ".join(f"{i+1}) {s}" for i, s in enumerate(passos or []))
        partes.append(f"\n[PLAYBOOK] {pb['situacao']} (base: {pb.get('base_legal')})\n  Passos: {passos_txt}")
    partes.append("=== FIM DA BASE DE CONHECIMENTO ===\n")
    return "\n".join(partes)


async def listar_conhecimento(db: AsyncSession) -> list[dict[str, Any]]:
    await ensure_tables(db)
    rows = await db.execute(text(
        "SELECT id,tipo,area,titulo,resumo,fundamentacao,desfecho,fonte,created_at "
        "FROM juridico_conhecimento WHERE ativo ORDER BY created_at DESC"))
    return [dict(r) for r in rows.mappings().all()]


async def listar_playbook(db: AsyncSession) -> list[dict[str, Any]]:
    await ensure_tables(db)
    rows = await db.execute(text(
        "SELECT id,situacao,area,base_legal,passos,documentos,created_at "
        "FROM juridico_playbook WHERE ativo ORDER BY area, situacao"))
    return [dict(r) for r in rows.mappings().all()]
