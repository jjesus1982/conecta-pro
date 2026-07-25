"""CFO IA — Conecta Mais (segurança patrimonial / agentes de portaria).

Consultor financeiro especializado (um "CFO" de bolso) que responde ancorado nos NÚMEROS
REAIS do ERP: saldo em conta, recebíveis/pagáveis, MRR, folha, margem, tributos (ISS/FGTS/INSS)
e NFS-e. A IA ASSISTE, o gestor/contador DECIDE. NUNCA inventa número — usa o contexto real
injetado ou diz explicitamente que o dado não está no sistema (ou está desatualizado).

Espelha a arquitetura do Consultor Jurídico (mesmo padrão vencedor: chat + anexo + respostas
estruturadas + contexto real do ERP), aplicado ao domínio financeiro.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constantes
# --------------------------------------------------------------------------- #

# "Lentes" do CFO — afinam a especialidade; o contexto financeiro real é sempre injetado.
AREAS_VALIDAS = ("fluxo_caixa", "resultado", "tributos", "estrategico")

DISCLAIMER_PADRAO = (
    "Apoio financeiro por IA — não substitui a análise do contador/gestor. "
    "Decisões com efeito fiscal/contábil relevante devem ser validadas com a contabilidade."
)

MSG_INDISPONIVEL = (
    "CFO IA indisponível — configurar. O provedor de LLM não está acessível no "
    "momento. Os números do painel abaixo continuam reais; a análise por IA volta assim que "
    "a integração for ajustada."
)

def _contexto_empresa() -> str:
    """Contexto societário VIVO do Grupo (Multi-CNPJ E8) + fatos setoriais fixos."""
    from modules.empresas.services.contexto_grupo import bloco_contexto_grupo

    return (
        bloco_contexto_grupo()
        + """
FATOS SETORIAIS (fixos):
- Atividade: SEGURANÇA PATRIMONIAL — categoria de AGENTES DE PORTARIA. CCT SINDECOMPRESTS
  AM000613/2025 rege pisos/adicionais (piso 2026 = R$ 1.670,00). A folha é o maior custo.
- Tributos na mão de obra: ISS (Manaus), retenção previdenciária de 11% na cessão de mão de
  obra, FGTS (8% s/ folha), IRRF. Contabilidade: Portte (consultoria permanente).
"""
    )


_CONTEXTO_EMPRESA = _contexto_empresa()

# --------------------------------------------------------------------------- #
# System prompt (persona CFO) + lentes por área
# --------------------------------------------------------------------------- #

_REGRAS_COMUNS = f"""Você é o CFO IA do Conecta PRO, ERP da Conecta Mais. Atue como um Diretor
Financeiro experiente e direto: pense em caixa, margem, risco e prazo. A IA assiste; o gestor
e o contador decidem. Responda em português do Brasil, objetivo e prático.

REGRAS INEGOCIÁVEIS:
1. Use SOMENTE os números do bloco "SITUAÇÃO FINANCEIRA REAL AGORA" abaixo. NUNCA invente,
   estime ou arredonde um valor que não esteja lá. Se um número necessário não estiver no
   contexto, diga explicitamente "esse dado não está no sistema" (ou "está desatualizado") —
   é melhor admitir do que fabricar.
2. Sempre que citar um valor, deixe claro de onde vem (ex.: "saldo Inter", "MRR", "folha").
3. Distinga fato (número do sistema) de recomendação/opinião (sua análise de CFO).
4. Sinalize ALTO RISCO / validar com o contador quando envolver: mudança de regime tributário,
   decisão de investimento/endividamento relevante, distribuição de lucros, corte de custos que
   afete a folha, ou qualquer efeito fiscal/contábil irreversível.
5. Seja quantitativo: quando fizer sentido, calcule (margem, runway, % da folha sobre receita,
   ponto de equilíbrio) usando os números reais — e mostre a conta.

FORMATO DA RESPOSTA (Markdown, escaneável):
## Diagnóstico
1–3 frases com a leitura direta da situação (o essencial).
## Números-chave
Os valores reais relevantes para a pergunta, em lista com `-` (cite a fonte de cada um).
## Recomendação
O que fazer, em passos numerados e acionáveis.
## Riscos & atenção
Riscos, prazos, ressalvas (se houver).
## Próximos passos
Ações concretas e curtas.
Regras de formatação: `##` nos títulos, **negrito** em valores/prazos/percentuais, listas com `-`
ou numeradas. Conciso. Omita uma seção que não se aplique.

{_CONTEXTO_EMPRESA}
"""

_PROMPTS_AREA = {
    "fluxo_caixa": _REGRAS_COMUNS + """
LENTE: FLUXO DE CAIXA & CAPITAL DE GIRO.
Foque em saldo disponível, recebíveis (a receber/vencidos), pagáveis (a pagar/vencidos),
descasamento de prazos, runway (por quanto tempo o caixa cobre a folha), necessidade de capital
de giro e prioridade de pagamentos. Alerte inadimplência e concentração de vencimentos.
""",
    "resultado": _REGRAS_COMUNS + """
LENTE: RESULTADO (DRE / CUSTOS / MARGEM).
Foque em receita (MRR/NFS-e), custo da folha (maior custo), margem, ticket médio por cliente,
receita por funcionário e ponto de equilíbrio. Aponte alavancas de margem sem comprometer a
operação (a folha é regida pela CCT — cuidado ao sugerir cortes).
""",
    "tributos": _REGRAS_COMUNS + """
LENTE: TRIBUTOS & ENCARGOS.
Foque em ISS (Manaus), FGTS (8% s/ folha), INSS (patronal + retenção 11% na cessão de mão de
obra), IRRF, PIS/COFINS (com as liminares em discussão) e o impacto do regime (Lucro Real x
Simples) na carga. Conecte com pendências do DET (FGTS/INSS) quando pertinente. Mudança de
regime é ALTO RISCO — recomende validar com o contador (Domínio/TOTVS).
""",
    "estrategico": _REGRAS_COMUNS + """
LENTE: FINANCEIRO ESTRATÉGICO.
Foque em precificação de contratos, rentabilidade por cliente/contrato, cenários (o que muda o
caixa/margem), reinvestimento, e a reorganização societária CNPJ1→CNPJ2. Traga uma visão de
CFO para as decisões — sempre ancorada nos números reais.
""",
}

# --------------------------------------------------------------------------- #
# Tabela (idempotente)
# --------------------------------------------------------------------------- #

_DDL = """
CREATE TABLE IF NOT EXISTS financial_cfo_consultas (
    id             BIGSERIAL PRIMARY KEY,
    area           VARCHAR(20)  NOT NULL,
    pergunta       TEXT         NOT NULL,
    resposta       TEXT         NOT NULL,
    escalonar      BOOLEAN      NOT NULL DEFAULT FALSE,
    disclaimer     TEXT         NOT NULL,
    contexto_usado JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_by     VARCHAR(64),
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);
"""


async def _garantir_tabela(db: AsyncSession) -> None:
    await db.execute(text(_DDL))


# --------------------------------------------------------------------------- #
# Motor de contexto financeiro REAL (a sacada — o CFO enxerga os números vivos)
# --------------------------------------------------------------------------- #

async def _num(db: AsyncSession, sql: str, default: float = 0.0) -> float:
    try:
        r = await db.execute(text(sql))
        v = r.scalar()
        return float(v) if v is not None else default
    except Exception as e:  # noqa: BLE001
        logger.debug("cfo _num falhou (%s): %s", sql[:60], e)
        return default


async def _saldo_inter_vivo() -> float | None:
    """Saldo VIVO do Banco Inter (cache Redis 5min → adapter real). None se indisponível."""
    # 1) cache Redis (populado pelo endpoint /financeiro/inter/saldo)
    try:
        from core.cache.redis import get_redis
        redis = await get_redis()
        cached = await redis.get("inter:saldo:cache")
        if cached:
            import json as _j
            d = _j.loads(cached)
            v = d.get("disponivel") if isinstance(d, dict) else d
            if v is not None:
                return float(v)
    except Exception:
        pass
    # 2) adapter real (OAuth2+mTLS) — best-effort, não quebra o painel
    adapter = None
    try:
        import os as _os
        from modules.integrations.banking.adapters.base import BankCredentials
        from modules.integrations.banking.adapters.inter import InterAdapter
        adapter = InterAdapter(BankCredentials(
            client_id=_os.getenv("INTER_CLIENT_ID", ""), client_secret=_os.getenv("INTER_CLIENT_SECRET", ""),
            certificate_path=_os.getenv("INTER_CERT_PATH"), private_key_path=_os.getenv("INTER_KEY_PATH"),
            agency=_os.getenv("INTER_AGENCY"), account=_os.getenv("INTER_ACCOUNT"),
            environment=_os.getenv("INTER_ENVIRONMENT", "production")))
        bal = await adapter.get_balance()
        return float(bal.available)
    except Exception as e:  # noqa: BLE001
        logger.debug("cfo saldo Inter vivo indisponível: %s", e)
        return None
    finally:
        if adapter is not None:
            try:
                await adapter.close()
            except Exception:
                pass


async def _pendencias_acionaveis(db: AsyncSession) -> dict[str, Any]:
    """O que exige AÇÃO agora — para o CFO apontar (e futuramente preparar a ação)."""
    pend: dict[str, Any] = {}
    pend["pagar_vencido_valor"] = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM payable_accounts WHERE status='pendente' AND due_date < CURRENT_DATE")
    pend["pagar_vencido_qtd"] = await _num(db, "SELECT COUNT(*) FROM payable_accounts WHERE status='pendente' AND due_date < CURRENT_DATE")
    pend["pagar_7dias_valor"] = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM payable_accounts WHERE status='pendente' AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 7")
    pend["receber_vencido_valor"] = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM receivable_accounts WHERE status='pendente' AND due_date < CURRENT_DATE")
    pend["receber_vencido_qtd"] = await _num(db, "SELECT COUNT(*) FROM receivable_accounts WHERE status='pendente' AND due_date < CURRENT_DATE")
    # Obrigações fiscais a vencer (se a tabela existir)
    pend["tributos_a_vencer_valor"] = await _num(db, "SELECT COALESCE(SUM(valor_devido),0) FROM fiscal_obligations WHERE status='pendente' AND data_vencimento BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE + 30")
    pend["tributos_a_vencer_qtd"] = await _num(db, "SELECT COUNT(*) FROM fiscal_obligations WHERE status='pendente' AND data_vencimento BETWEEN CURRENT_DATE - 30 AND CURRENT_DATE + 30")
    return pend


async def _cross_modulo(db: AsyncSession) -> dict[str, Any]:
    """Sinais financeiros que vivem em TODOS os outros módulos (comunicação inbound do hub).
    Receita futura (Comercial), passivos/custos (Pessoas), contingências (Jurídico), fiscais (DET)."""
    c: dict[str, Any] = {}
    # COMERCIAL — receita futura
    c["pipeline_aberto"] = await _num(db, "SELECT COALESCE(SUM(value),0) FROM opportunities WHERE lower(COALESCE(stage,'')) NOT IN ('won','lost','closed_won','closed_lost','ganho','perdido')")
    c["pipeline_ponderado"] = await _num(db, "SELECT COALESCE(SUM(value*COALESCE(probability,0)/100.0),0) FROM opportunities WHERE lower(COALESCE(stage,'')) NOT IN ('won','lost','closed_won','closed_lost','ganho','perdido')")
    c["propostas_aceitas_valor"] = await _num(db, "SELECT COALESCE(SUM(total),0) FROM proposals WHERE status='accepted'")
    c["propostas_aceitas_qtd"] = await _num(db, "SELECT COUNT(*) FROM proposals WHERE status='accepted'")
    # PESSOAS / DP — fontes de pagáveis e passivos
    c["reembolsos_a_pagar"] = await _num(db, "SELECT COALESCE(SUM(total_amount),0) FROM reimbursement_requests WHERE status IN ('pendente','aprovado')")
    c["reembolsos_qtd"] = await _num(db, "SELECT COUNT(*) FROM reimbursement_requests WHERE status IN ('pendente','aprovado')")
    c["rescisoes_valor"] = await _num(db, "SELECT COALESCE(SUM(total_amount),0) FROM termination_processes WHERE lower(COALESCE(status,'')) NOT IN ('pago','concluido','finalizado','cancelado','paid','completed')")
    c["rescisoes_qtd"] = await _num(db, "SELECT COUNT(*) FROM termination_processes WHERE lower(COALESCE(status,'')) NOT IN ('pago','concluido','finalizado','cancelado','paid','completed')")
    # JURÍDICO — contingências (passivo potencial)
    c["processos_ativos"] = await _num(db, "SELECT COUNT(*) FROM juridico_processos WHERE lower(COALESCE(status,'')) NOT IN ('arquivado','encerrado','baixado')")
    c["det_pendencias"] = await _num(db, "SELECT COUNT(*) FROM juridico_det_comunicacoes WHERE escalonar")
    # OPERACIONAL — diaristas escalados a pagar (VT+VR), elo Operacional→Financeiro
    c["diaristas_a_pagar_valor"] = await _num(db, "SELECT COALESCE(SUM(valor),0) FROM financial_pagamentos_diaristas WHERE status='a_revisar'")
    c["diaristas_a_pagar_qtd"] = await _num(db, "SELECT COUNT(*) FROM financial_pagamentos_diaristas WHERE status='a_revisar'")
    c["diaristas_sem_pix"] = await _num(db, "SELECT COUNT(*) FROM financial_pagamentos_diaristas WHERE status='sem_pix'")
    return c


async def _aging_buckets(db: AsyncSession, table: str) -> list[dict[str, Any]]:
    """Faixas de aging (a_vencer / 0-30 / 31-60 / 61-90 / +90) por valor em aberto. Dado real."""
    rows = await db.execute(text(f"""
        SELECT CASE
            WHEN due_date >= CURRENT_DATE THEN 'a_vencer'
            WHEN due_date >= CURRENT_DATE - 30 THEN 'ate_30_dias'
            WHEN due_date >= CURRENT_DATE - 60 THEN '31_a_60_dias'
            WHEN due_date >= CURRENT_DATE - 90 THEN '61_a_90_dias'
            ELSE 'acima_90_dias' END AS faixa,
            COUNT(*) qtd, COALESCE(SUM(COALESCE(net_value, gross_value, 0)),0) total
        FROM {table}
        WHERE lower(status::text) IN ('pendente','pending','parcial','partial')
        GROUP BY 1
    """))  # noqa: S608 — table é literal controlado
    ordem = {"a_vencer": 0, "ate_30_dias": 1, "31_a_60_dias": 2, "61_a_90_dias": 3, "acima_90_dias": 4}
    out = [{"faixa": r[0], "quantidade": int(r[1]), "valor_total": float(r[2])} for r in rows.all()]
    return sorted(out, key=lambda x: ordem.get(x["faixa"], 9))


async def panorama(db: AsyncSession) -> dict[str, Any]:
    """Fotografia financeira REAL do ERP agora (fonte da verdade p/ o CFO e p/ o painel)."""
    p: dict[str, Any] = {}
    # Caixa / banco — prioriza o saldo VIVO do Inter; cai p/ a tabela se indisponível
    saldo_vivo = await _saldo_inter_vivo()
    if saldo_vivo is not None:
        p["saldo_banco"] = saldo_vivo
        p["saldo_fonte"] = "Banco Inter (ao vivo)"
    else:
        p["saldo_banco"] = await _num(db, "SELECT COALESCE(SUM(current_balance),0) FROM bank_accounts")
        p["saldo_fonte"] = "cadastro (Inter indisponível no momento)"
    p["pendencias"] = await _pendencias_acionaveis(db)
    p["cross_modulo"] = await _cross_modulo(db)
    try:
        p["previsao_custos"] = await previsao_custos_mensais(db)
    except Exception:  # noqa: BLE001
        p["previsao_custos"] = None
    # Recebíveis / pagáveis (net_value é o valor da conta; remaining quando preenchido)
    p["receber_pendente"] = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM receivable_accounts WHERE status='pendente'")
    p["receber_vencido"] = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM receivable_accounts WHERE status='pendente' AND due_date < CURRENT_DATE")
    p["receber_qtd"] = await _num(db, "SELECT COUNT(*) FROM receivable_accounts WHERE status='pendente'")
    p["pagar_pendente"] = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM payable_accounts WHERE status='pendente'")
    p["pagar_vencido"] = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM payable_accounts WHERE status='pendente' AND due_date < CURRENT_DATE")
    p["pagar_qtd"] = await _num(db, "SELECT COUNT(*) FROM payable_accounts WHERE status='pendente'")
    # Contratos / MRR
    p["contratos"] = await _num(db, "SELECT COUNT(*) FROM contracts")
    p["mrr_contratado"] = await _num(db, "SELECT COALESCE(SUM(monthly_value),0) FROM contracts")
    # NFS-e (faturamento) — FONTE REAL nfse_emitidas_nacional (portal nacional, cStat 100, todo 2026)
    p["nfse_qtd"] = await _num(db, "SELECT COUNT(*) FROM nfse_emitidas_nacional WHERE COALESCE(cancelada,FALSE)=FALSE")
    p["nfse_total"] = await _num(db, "SELECT COALESCE(SUM(valor_servicos),0) FROM nfse_emitidas_nacional WHERE COALESCE(cancelada,FALSE)=FALSE")
    # Multi-CNPJ: quebra do faturamento por empresa (o CFO é do GRUPO — precisa distinguir
    # Lucro Real × Simples, não só o total somado).
    try:
        _rows = await db.execute(text(
            "SELECT e.slug, COUNT(*) qtd, COALESCE(SUM(n.valor_servicos),0) total "
            "FROM nfse_emitidas_nacional n JOIN empresas e ON e.id = n.empresa_id "
            "WHERE COALESCE(n.cancelada,FALSE)=FALSE "
            "GROUP BY e.slug ORDER BY e.slug"))
        p["nfse_por_empresa"] = [
            {"empresa": r["slug"], "qtd": int(r["qtd"]), "total": float(r["total"])}
            for r in _rows.mappings().all()
        ]
    except Exception:  # noqa: BLE001 — breakdown é complementar, não derruba o panorama
        p["nfse_por_empresa"] = []
    # KPIs executivos (reais, recalculados) — fonte autoritativa de MRR/folha/margem
    kpis: dict[str, Any] = {}
    try:
        rows = await db.execute(text(
            "SELECT code, current_value, unit, last_calculated_at FROM executive_kpis ORDER BY display_order"))
        for r in rows.mappings().all():
            kpis[r["code"]] = {"valor": float(r["current_value"]) if r["current_value"] is not None else None,
                               "unidade": r["unit"],
                               "calculado_em": r["last_calculated_at"].isoformat() if r["last_calculated_at"] else None}
    except Exception as e:  # noqa: BLE001
        logger.debug("cfo kpis: %s", e)
    p["kpis"] = kpis
    # Runway simples: saldo / folha mensal (quantos meses o caixa cobre a folha)
    folha = (kpis.get("FOLHA") or {}).get("valor") or 0.0
    p["folha_mensal"] = folha
    p["runway_meses"] = round(p["saldo_banco"] / folha, 1) if folha else None
    # Aging por faixa (para o raio-x executivo) + provisões e resultado mensal
    try:
        p["aging_receber"] = await _aging_buckets(db, "receivable_accounts")
        p["aging_pagar"] = await _aging_buckets(db, "payable_accounts")
    except Exception as e:  # noqa: BLE001
        logger.debug("aging buckets: %s", e)
        p["aging_receber"] = []
        p["aging_pagar"] = []
    prev = p.get("previsao_custos") or {}
    p["provisoes_mensais"] = round(
        sum(i["valor"] for i in (prev.get("itens") or []) if i.get("grupo") == "provisao"), 2)
    p["custo_mensal_total"] = prev.get("total_custo_mensal")
    p["resultado_mensal"] = prev.get("resultado_mensal_estimado")
    return p


_DDL_CUSTOS = """
CREATE TABLE IF NOT EXISTS financial_custos_recorrentes (
    id            BIGSERIAL PRIMARY KEY,
    categoria     VARCHAR(30) NOT NULL,   -- tributo | parcelamento | acordo | fixo | fornecedor
    descricao     TEXT NOT NULL,
    valor         NUMERIC(12,2) NOT NULL,
    dia_vencimento INT,
    parcelas_total INT,                    -- p/ parcelamento/acordo (null = recorrente sem fim)
    parcelas_pagas INT DEFAULT 0,
    ativo         BOOLEAN NOT NULL DEFAULT TRUE,
    observacao    TEXT,
    created_by    VARCHAR(64),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


async def _ensure_custos(db: AsyncSession) -> None:
    await db.execute(text(_DDL_CUSTOS))


async def custos_recorrentes_listar(db: AsyncSession, ativos: bool = True) -> list[dict[str, Any]]:
    await _ensure_custos(db)
    clause = "WHERE ativo = TRUE" if ativos else ""
    rows = await db.execute(text(
        f"""SELECT id, categoria, descricao, valor, dia_vencimento, parcelas_total, parcelas_pagas, ativo, observacao
            FROM financial_custos_recorrentes {clause} ORDER BY categoria, descricao"""))
    out = []
    for r in rows.mappings().all():
        restantes = None
        if r["parcelas_total"] is not None:
            restantes = max(0, int(r["parcelas_total"]) - int(r["parcelas_pagas"] or 0))
        out.append({"id": r["id"], "categoria": r["categoria"], "descricao": r["descricao"],
                    "valor": float(r["valor"]), "dia_vencimento": r["dia_vencimento"],
                    "parcelas_total": r["parcelas_total"], "parcelas_pagas": r["parcelas_pagas"],
                    "parcelas_restantes": restantes, "ativo": bool(r["ativo"]), "observacao": r["observacao"]})
    return out


async def custo_recorrente_criar(db: AsyncSession, categoria: str, descricao: str, valor: float,
                                 dia_vencimento: int | None = None, parcelas_total: int | None = None,
                                 parcelas_pagas: int = 0, observacao: str | None = None,
                                 user_id: str | None = None) -> dict[str, Any]:
    await _ensure_custos(db)
    r = await db.execute(text(
        """INSERT INTO financial_custos_recorrentes
             (categoria, descricao, valor, dia_vencimento, parcelas_total, parcelas_pagas, observacao, created_by)
           VALUES (:c,:d,:v,:dv,:pt,:pp,:obs,:u) RETURNING id"""),
        {"c": categoria, "d": descricao, "v": valor, "dv": dia_vencimento, "pt": parcelas_total,
         "pp": parcelas_pagas, "obs": observacao, "u": str(user_id) if user_id else None})
    await db.commit()
    return {"ok": True, "id": int(r.scalar())}


async def custo_recorrente_remover(db: AsyncSession, custo_id: int) -> dict[str, Any]:
    await _ensure_custos(db)
    await db.execute(text("UPDATE financial_custos_recorrentes SET ativo=FALSE WHERE id=:id"), {"id": custo_id})
    await db.commit()
    return {"ok": True}


async def adimplencia_clientes(db: AsyncSession) -> dict[str, Any]:
    """Saúde de pagamento por cliente: MRR contratado (client_contracts→clients) x o que ENTROU de
    verdade no banco (recebimentos identificados). Casa por token do nome. Dado real dos dois lados."""
    import unicodedata

    def _n(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return " ".join(s.upper().split())

    GEN = {"CONDOMINIO", "RESIDENCIAL", "VILLAGE", "EDIFICIO", "DA", "DE", "DO", "DOS", "PARQUE", "CIDADE", "COND"}
    contratos = [dict(r) for r in (await db.execute(text(
        "SELECT cl.name nome, cc.monthly_value mrr FROM client_contracts cc "
        "JOIN clients cl ON cl.id=cc.client_id WHERE lower(cc.status::text) IN ('ativo','active')"
    ))).mappings().all()]
    recebidos = [dict(r) for r in (await db.execute(text(
        "SELECT COALESCE(NULLIF(trim(counterparty_name),''),'') nome, sum(amount) total, count(*) qtd "
        "FROM bank_transactions WHERE justificativa_categoria='recebimento_cliente' AND amount>0 "
        "AND counterparty_name IS NOT NULL GROUP BY 1"
    ))).mappings().all()]

    def toks(nome):
        return {t for t in _n(nome).split() if t not in GEN and len(t) >= 4}

    ctoks = [(c, toks(c["nome"])) for c in contratos]
    # cada recebimento vai para o ÚNICO contrato de MAIOR sobreposição (evita dupla contagem
    # quando tokens genéricos como VILLA/FLORES aparecem em vários condôminios).
    acc = {c["nome"]: {"recebido": 0.0, "qtd": 0} for c in contratos}
    for r in recebidos:
        rt = toks(r["nome"])
        if not rt:
            continue
        melhor, melhor_score = None, 0
        for c, ct in ctoks:
            score = len(ct & rt)
            if score > melhor_score:
                melhor, melhor_score = c, score
        if melhor and melhor_score > 0:
            acc[melhor["nome"]]["recebido"] += float(r["total"])
            acc[melhor["nome"]]["qtd"] += int(r["qtd"])

    out = []
    total_mrr = total_rec = 0.0
    for c in contratos:
        mrr = float(c["mrr"] or 0)
        recebido = acc[c["nome"]]["recebido"]
        qtd = acc[c["nome"]]["qtd"]
        meses_eq = round(recebido / mrr, 1) if mrr else None
        out.append({"cliente": c["nome"], "mrr_mensal": round(mrr, 2),
                    "recebido_banco": round(recebido, 2), "pagamentos": qtd,
                    "meses_equivalentes": meses_eq})
        total_mrr += mrr
        total_rec += recebido
    out.sort(key=lambda x: x["recebido_banco"], reverse=True)
    return {"clientes": out, "total_mrr_mensal": round(total_mrr, 2),
            "total_recebido": round(total_rec, 2),
            "fonte": "MRR = contratos ativos; recebido = extrato Inter (PIX identificado por nome). Boletos sem nome não entram aqui.",
            "observacao": "meses_equivalentes = recebido ÷ MRR mensal (quantos meses de contrato o cliente já pagou no total)."}


async def projecao_caixa(db: AsyncSession, meses: int = 6) -> dict[str, Any]:
    """Projeção de caixa RECORRENTE (honesta): saldo atual + (MRR − custo mensal total) por mês.
    Não há pagáveis/recebíveis com vencimento futuro no banco, então a projeção é por run-rate
    recorrente (receita contratada − custos mensais reais, incluindo provisões). Marcado como
    projeção; flag de mês em que o caixa fica negativo (gap)."""
    saldo = await _saldo_inter_vivo()
    if saldo is None:
        saldo = await _num(db, "SELECT COALESCE(SUM(current_balance),0) FROM bank_accounts")
    prev = await previsao_custos_mensais(db)
    custo = prev.get("total_custo_mensal", 0.0)
    receita = prev.get("receita_mensal", 0.0)
    resultado = round(receita - custo, 2)

    import datetime as _dt
    hoje = await _num(db, "SELECT EXTRACT(YEAR FROM CURRENT_DATE)*100 + EXTRACT(MONTH FROM CURRENT_DATE)")
    ano, mes = int(hoje) // 100, int(hoje) % 100
    pontos = []
    saldo_corrente = float(saldo or 0)
    primeiro_gap = None
    for i in range(1, meses + 1):
        m = mes + i
        y = ano + (m - 1) // 12
        mm = ((m - 1) % 12) + 1
        saldo_corrente = round(saldo_corrente + resultado, 2)
        rotulo = f"{mm:02d}/{y}"
        pontos.append({"competencia": rotulo, "entrada": receita, "saida": custo,
                       "resultado": resultado, "saldo_projetado": saldo_corrente,
                       "negativo": saldo_corrente < 0})
        if saldo_corrente < 0 and primeiro_gap is None:
            primeiro_gap = rotulo
    return {
        "saldo_atual": round(float(saldo or 0), 2),
        "receita_mensal": receita, "custo_mensal": custo, "resultado_mensal": resultado,
        "pontos": pontos, "primeiro_mes_negativo": primeiro_gap,
        "fonte": "projeção recorrente (MRR contratado − custos mensais reais, inclui provisões)",
        "observacao": "Projeção por run-rate — não há vencimentos futuros cadastrados. Receber cobranças em atraso melhora o caixa.",
    }


async def previsao_custos_mensais(db: AsyncSession) -> dict[str, Any]:
    """Previsibilidade de custos mensais: folha, tributos, diaristas, fornecedores, parcelamentos.

    Sourcing HONESTO: cada item marca a fonte (real / calculado / estimado run-rate / aguardando).
    Não fabrica — onde não há dado, diz 'aguardando'."""
    # KPIs reais
    kpis: dict[str, float] = {}
    try:
        rows = await db.execute(text("SELECT code, current_value FROM executive_kpis"))
        for r in rows.all():
            kpis[r[0]] = float(r[1]) if r[1] is not None else 0.0
    except Exception:
        pass
    folha = kpis.get("FOLHA", 0.0)
    fgts = round(folha * 0.08, 2)

    # Diaristas VT+VR — run-rate do extrato Inter (R$32/dia)
    vtvr_qtd = await _num(db, "SELECT COUNT(*) FROM inter_transactions WHERE abs(valor)=32.00 AND data_lancamento >= CURRENT_DATE - make_interval(days=>30)")
    vtvr = vtvr_qtd * 32.0
    # Diaristas diárias (dia 15) — soma dos lançamentos dos últimos 30 dias
    diarias = await _num(db, "SELECT COALESCE(SUM(valor),0) FROM diaria_lancamentos WHERE data >= CURRENT_DATE - make_interval(days=>30)")
    # Fornecedores / contas a pagar pendentes (próximos 30 dias)
    fornecedores = await _num(db, "SELECT COALESCE(SUM(net_value),0) FROM payable_accounts WHERE status='pendente' AND due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 30")
    # Reembolsos a pagar
    reembolsos = await _num(db, "SELECT COALESCE(SUM(total_amount),0) FROM reimbursement_requests WHERE status IN ('pendente','aprovado')")

    receita_kpi = kpis.get("MRR", 0.0)
    iss = round(receita_kpi * 0.05, 2)  # ISS Manaus 5% sobre o faturamento de serviços
    # Provisões trabalhistas — passivo que ACUMULA todo mês e é pago depois (13º em dez, férias no gozo).
    # Provisionar mensalmente evita o "susto" de dezembro. Base = folha real (KPI FOLHA).
    prov_13 = round(folha / 12.0, 2)                       # 13º = 1 folha / 12 meses
    prov_ferias = round(folha * (4.0 / 3.0) / 12.0, 2)     # férias + 1/3 constitucional, / 12
    prov_fgts = round((prov_13 + prov_ferias) * 0.08, 2)   # FGTS 8% sobre as provisões
    itens = [
        {"categoria": "Folha (CLT)", "valor": folha, "fonte": "real (KPI executivo)", "grupo": "folha"},
        {"categoria": "FGTS (8% da folha)", "valor": fgts, "fonte": "calculado", "grupo": "tributo"},
        {"categoria": "ISS (5% do faturamento)", "valor": iss,
         "fonte": "estimado (5% do MRR)" if iss else "aguardando dado", "grupo": "tributo"},
        {"categoria": "Provisão 13º salário (1/12 da folha)", "valor": prov_13,
         "fonte": "calculado (provisão mensal — pago em dez)" if prov_13 else "aguardando folha", "grupo": "provisao"},
        {"categoria": "Provisão férias + 1/3 (1/12 da folha)", "valor": prov_ferias,
         "fonte": "calculado (provisão mensal — pago no gozo)" if prov_ferias else "aguardando folha", "grupo": "provisao"},
        {"categoria": "FGTS sobre provisões (8%)", "valor": prov_fgts,
         "fonte": "calculado" if prov_fgts else "aguardando folha", "grupo": "provisao"},
        {"categoria": "Diaristas — VT+VR diário", "valor": round(vtvr, 2),
         "fonte": f"estimado (run-rate: {int(vtvr_qtd)} pagamentos de R$32 em 30 dias)" if vtvr else "aguardando dado", "grupo": "diaristas"},
        {"categoria": "Diaristas — diárias trabalhadas (dia 15)", "valor": round(diarias, 2),
         "fonte": "lançamentos dos últimos 30 dias" if diarias else "aguardando lançamentos do Operacional", "grupo": "diaristas"},
        {"categoria": "Fornecedores / contas a pagar (30d)", "valor": round(fornecedores, 2),
         "fonte": "real (contas a pagar pendentes)" if fornecedores else "sem contas a vencer em 30d", "grupo": "fornecedor"},
        {"categoria": "Reembolsos (DP)", "valor": round(reembolsos, 2),
         "fonte": "real (pedidos aprovados/pendentes)" if reembolsos else "sem reembolsos", "grupo": "diaristas"},
    ]
    # Custos recorrentes registrados (tributos exatos do contador, parcelamentos, acordos, custos fixos)
    grp_label = {"tributo": "Tributo", "parcelamento": "Parcelamento", "acordo": "Acordo",
                 "fixo": "Custo fixo", "fornecedor": "Fornecedor"}
    for c in await custos_recorrentes_listar(db, ativos=True):
        # parcelamento/acordo só entra enquanto há parcelas restantes
        if c.get("parcelas_restantes") == 0:
            continue
        rot = grp_label.get(c["categoria"], c["categoria"].title())
        extra = f" ({c['parcelas_restantes']} parcelas restantes)" if c.get("parcelas_restantes") else ""
        itens.append({"categoria": f"{rot}: {c['descricao']}{extra}", "valor": c["valor"],
                      "fonte": "registrado", "grupo": c["categoria"], "id": c["id"]})
    total = round(sum(i["valor"] for i in itens), 2)
    # comparação com o caixa
    saldo = await _saldo_inter_vivo()
    if saldo is None:
        saldo = await _num(db, "SELECT COALESCE(SUM(current_balance),0) FROM bank_accounts")
    receita = kpis.get("MRR", 0.0)
    return {
        "itens": itens, "total_custo_mensal": total,
        "receita_mensal": receita, "saldo_atual": saldo,
        "resultado_mensal_estimado": round(receita - total, 2),
        "cobertura_caixa_meses": round(saldo / total, 1) if total else None,
        "observacao": "Estimativas por run-rate são marcadas como tal. Itens 'aguardando' dependem de dado do módulo de origem.",
    }


def _fmt(v: Any) -> str:
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(v)


def _formatar_contexto_financeiro(p: dict[str, Any]) -> str:
    k = p.get("kpis", {})
    def kv(code, campo="valor"):
        return (k.get(code) or {}).get(campo)
    pend = p.get("pendencias", {})
    linhas = [
        "\n=== SITUAÇÃO FINANCEIRA REAL AGORA (fonte da verdade — use SÓ estes números) ===",
        f"- Saldo em conta [{p.get('saldo_fonte', 'Banco Inter')}]: {_fmt(p.get('saldo_banco'))}",
        f"- MRR (receita recorrente mensal): {_fmt(kv('MRR') or p.get('mrr_contratado'))}",
        f"- Folha mensal: {_fmt(kv('FOLHA') or p.get('folha_mensal'))}"
        + (f" ({kv('CUSTO_FOLHA')}% da receita)" if kv('CUSTO_FOLHA') is not None else ""),
        f"- Margem: {kv('MARGEM')}%" if kv('MARGEM') is not None else "- Margem: não disponível",
        f"- Clientes ativos: {int(kv('CLIENTES')) if kv('CLIENTES') else '?'} · Contratos: {int(p.get('contratos') or 0)} · Headcount: {int(kv('HEADCOUNT')) if kv('HEADCOUNT') else '?'}",
        f"- Ticket médio/cliente: {_fmt(kv('TICKET'))}" if kv('TICKET') else "",
        f"- Runway (saldo ÷ folha): {p.get('runway_meses')} meses" if p.get('runway_meses') is not None else "",
        f"- A receber (pendente): {_fmt(p.get('receber_pendente'))} em {int(p.get('receber_qtd') or 0)} contas"
        + (f", dos quais {_fmt(p.get('receber_vencido'))} VENCIDOS" if p.get('receber_vencido') else ""),
        f"- A pagar (pendente): {_fmt(p.get('pagar_pendente'))} em {int(p.get('pagar_qtd') or 0)} contas"
        + (f", dos quais {_fmt(p.get('pagar_vencido'))} VENCIDOS" if p.get('pagar_vencido') else ""),
        f"- NFS-e emitidas: {int(p.get('nfse_qtd') or 0)} (total {_fmt(p.get('nfse_total'))})",
        f"- ISS total: {_fmt(kv('ISS_TOTAL'))}" if kv('ISS_TOTAL') else "",
    ]
    # marca dado incompleto honestamente
    if not p.get("receber_pendente") and p.get("receber_qtd"):
        linhas.append("- OBS: há contas a receber cadastradas mas SEM valor preenchido (dado incompleto no sistema).")
    if not p.get("pagar_pendente") and p.get("pagar_qtd"):
        linhas.append("- OBS: há contas a pagar cadastradas mas SEM valor preenchido (dado incompleto no sistema).")
    # Pendências acionáveis
    if pend:
        linhas.append("--- PENDÊNCIAS QUE EXIGEM AÇÃO ---")
        if pend.get("pagar_vencido_valor"):
            linhas.append(f"- A PAGAR vencido: {_fmt(pend['pagar_vencido_valor'])} em {int(pend.get('pagar_vencido_qtd') or 0)} contas")
        if pend.get("pagar_7dias_valor"):
            linhas.append(f"- A pagar nos próximos 7 dias: {_fmt(pend['pagar_7dias_valor'])}")
        if pend.get("receber_vencido_valor"):
            linhas.append(f"- A RECEBER vencido (cobrar): {_fmt(pend['receber_vencido_valor'])} em {int(pend.get('receber_vencido_qtd') or 0)} contas")
        if pend.get("tributos_a_vencer_valor"):
            linhas.append(f"- Tributos/obrigações a vencer (±30d): {_fmt(pend['tributos_a_vencer_valor'])} em {int(pend.get('tributos_a_vencer_qtd') or 0)} guias")
    # VISÃO CROSS-MÓDULO (o hub financeiro enxerga todos os módulos)
    cm = p.get("cross_modulo", {})
    if cm:
        linhas.append("--- VISÃO CROSS-MÓDULO (todos os módulos) ---")
        if cm.get("pipeline_aberto"):
            linhas.append(f"- Comercial: pipeline aberto {_fmt(cm['pipeline_aberto'])} (ponderado por probabilidade: {_fmt(cm.get('pipeline_ponderado'))}) = receita FUTURA potencial")
        if cm.get("propostas_aceitas_valor"):
            linhas.append(f"- Comercial: {int(cm.get('propostas_aceitas_qtd') or 0)} proposta(s) aceita(s) = {_fmt(cm['propostas_aceitas_valor'])} prestes a virar contrato/receita")
        if cm.get("reembolsos_a_pagar"):
            linhas.append(f"- Pessoas/DP: reembolsos a pagar {_fmt(cm['reembolsos_a_pagar'])} em {int(cm.get('reembolsos_qtd') or 0)} pedidos (pagável)")
        if cm.get("rescisoes_qtd"):
            rv = cm.get("rescisoes_valor") or 0
            linhas.append(f"- Pessoas/DP: {int(cm['rescisoes_qtd'])} rescisão(ões) em aberto" + (f" = {_fmt(rv)} (passivo)" if rv else " (valores ainda não calculados no sistema)"))
        if cm.get("processos_ativos"):
            linhas.append(f"- Jurídico: {int(cm['processos_ativos'])} processo(s) trabalhista(s) ativo(s) = CONTINGÊNCIA (passivo potencial — provisionar)")
        if cm.get("det_pendencias"):
            linhas.append(f"- Fiscal/DET: {int(cm['det_pendencias'])} pendência(s) de fiscalização (FGTS/INSS) a resolver")
        if cm.get("diaristas_a_pagar_qtd"):
            linhas.append(f"- Operacional: {int(cm['diaristas_a_pagar_qtd'])} diarista(s) escalado(s) a pagar VT+VR = {_fmt(cm.get('diaristas_a_pagar_valor'))} (revisar e pagar em lote)")
        if cm.get("diaristas_sem_pix"):
            linhas.append(f"- Operacional: {int(cm['diaristas_sem_pix'])} diarista(s) SEM chave PIX cadastrada (bloqueia pagamento — completar cadastro)")
    # Previsibilidade de custos mensais
    pc = p.get("previsao_custos")
    if pc:
        linhas.append("--- PREVISÃO DE CUSTOS MENSAIS ---")
        for it in pc.get("itens", []):
            if it.get("valor"):
                linhas.append(f"- {it['categoria']}: {_fmt(it['valor'])} [{it['fonte']}]")
        linhas.append(f"- CUSTO MENSAL TOTAL previsto: {_fmt(pc.get('total_custo_mensal'))} · receita {_fmt(pc.get('receita_mensal'))} → resultado estimado {_fmt(pc.get('resultado_mensal_estimado'))}")
        if pc.get("cobertura_caixa_meses") is not None:
            linhas.append(f"- Cobertura do caixa: {pc['cobertura_caixa_meses']} meses de custo")
    cal = (k.get("MRR") or {}).get("calculado_em")
    if cal:
        linhas.append(f"(KPIs recalculados em {cal[:16].replace('T', ' ')})")
    # Capacidades operacionais disponíveis (o CFO pode APONTAR a ação — execução é gate humano)
    linhas.append(
        "CAPACIDADES DO SISTEMA (Banco Inter integrado): é possível EMITIR boleto/PIX de cobrança e "
        "PAGAR boleto/DARF/GPS/TED por dentro do Conecta PRO. Pagamento exige aprovação do gestor por "
        "código OTP (limite R$5.000/dia). Ao recomendar cobrar ou pagar, indique que a ação pode ser "
        "feita no sistema — NUNCA afirme que já pagou/cobrou; isso depende da confirmação do gestor.")
    return "\n".join([x for x in linhas if x]) + "\n=== FIM DA SITUAÇÃO REAL ===\n"


# --------------------------------------------------------------------------- #
# Escalonamento (validar com contador)
# --------------------------------------------------------------------------- #

_GATILHOS = ("regime", "simples", "lucro real", "distribu", "dividendo", "emprést", "emprest",
             "financiamento", "investir", "investimento", "demiss", "corte", "endivid", "sócio",
             "socio", "pró-labore", "pro-labore", "parcelamento", "refis")


def _detectar_risco(pergunta: str) -> bool:
    p = (pergunta or "").lower()
    return any(g in p for g in _GATILHOS)


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #

async def consultar(
    db: AsyncSession,
    area: str,
    pergunta: str,
    user_id: str | None,
    anexo_texto: str | None = None,
    anexo_nome: str | None = None,
) -> dict[str, Any]:
    """Responde uma pergunta financeira ancorada nos números reais do ERP e persiste."""
    area_norm = (area or "").strip().lower()
    if area_norm not in AREAS_VALIDAS:
        raise ValueError(f"Área inválida '{area}'. Válidas: {', '.join(AREAS_VALIDAS)}.")
    if not (pergunta or "").strip() and not (anexo_texto or "").strip():
        raise ValueError("A pergunta não pode ser vazia.")

    await _garantir_tabela(db)
    pano = await panorama(db)
    system_prompt = _PROMPTS_AREA[area_norm] + _formatar_contexto_financeiro(pano)
    contexto_usado = {"area": area_norm, "panorama": pano}

    resposta_texto: str | None = None
    llm_ok = False
    llm_meta: dict[str, Any] = {}
    try:
        import os as _os

        from modules.ai.conversation.services import consultor_hub as _hub
        _extra = await _hub.contexto_compartilhado(db, 'cfo', pergunta)
        _conversa = await _hub.conversa_recente(db, 'cfo')
        if _extra:
            system_prompt = f"{system_prompt}\n\n{_extra}"
        if _conversa:
            system_prompt = f"{system_prompt}\n\n{_conversa}"
        from modules.ai.conversation.services.consultor_conhecimento_service import contexto_para_prompt
        system_prompt = system_prompt + contexto_para_prompt("cfo", pergunta)
        from modules.ai.conversation.services.llm_provider import ClaudeProvider, OpenAIProvider

        # OpenAI é o provider PRIMÁRIO dos consultores (decisão Jordan 2026-07-07:
        # mais barato que Anthropic). Claude fica como fallback se a chave faltar.
        pass  # geração via hub (melhor modelo + fallback)
        user_content = (pergunta or "").strip() or "Faça um diagnóstico financeiro da empresa agora."
        if (anexo_texto or "").strip():
            user_content = (
                f"{user_content}\n\n=== DOCUMENTO ANEXADO"
                f"{f' ({anexo_nome})' if anexo_nome else ''} ===\n"
                f"{anexo_texto.strip()[:14000]}\n=== FIM DO DOCUMENTO ===\n\n"
                "Analise o documento acima à luz da pergunta e dos números reais da empresa."
            )
        resposta_texto, llm_meta = await _hub.gerar(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=system_prompt, max_tokens=2500, temperature=0.2,
        )
        # BUG FIX: llm_ok nunca era setado True após a geração — o CFO caía SEMPRE no
        # ramo "indisponível" e descartava a resposta real do hub (os outros 5
        # consultores usam `if not resposta_texto`). Agora reflete o texto gerado.
        llm_ok = bool((resposta_texto or "").strip())
    except Exception as e:  # noqa: BLE001
        logger.warning("CFO IA: LLM indisponível (%s)", e)
        from modules.ai.conversation.services.llm_credit_alert import alertar_llm_indisponivel
        await alertar_llm_indisponivel("CFO IA (Financeiro)", str(e))
        llm_ok = False

    if not llm_ok:
        resultado = {
            "resposta": MSG_INDISPONIVEL, "escalonar": True, "disclaimer": DISCLAIMER_PADRAO,
            "id": None, "indisponivel": True, "panorama": pano,
        }
        try:
            row = await db.execute(text(
                """INSERT INTO financial_cfo_consultas
                   (area, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by)
                   VALUES (:a,:p,:r,:e,:d, CAST(:c AS jsonb), :u) RETURNING id"""),
                {"a": area_norm, "p": (pergunta or "").strip(), "r": MSG_INDISPONIVEL, "e": True,
                 "d": DISCLAIMER_PADRAO, "c": json.dumps({"llm_indisponivel": True}, default=str),
                 "u": str(user_id) if user_id else None})
            resultado["id"] = int(row.scalar())
        except Exception as e:  # noqa: BLE001
            logger.error("Falha ao persistir consulta CFO indisponível: %s", e)
        return resultado

    resp_lower = resposta_texto.lower()
    escalonar = bool(_detectar_risco(pergunta) or any(
        s in resp_lower for s in ("validar com o contador", "consultar o contador", "alto risco", "contabilidade")))

    consulta_id: int | None = None
    try:
        row = await db.execute(text(
            """INSERT INTO financial_cfo_consultas
               (area, pergunta, resposta, escalonar, disclaimer, contexto_usado, created_by)
               VALUES (:a,:p,:r,:e,:d, CAST(:c AS jsonb), :u) RETURNING id"""),
            {"a": area_norm, "p": (pergunta or "").strip(), "r": resposta_texto, "e": escalonar,
             "d": DISCLAIMER_PADRAO,
             "c": json.dumps({"panorama": pano, "llm": llm_meta}, default=str, ensure_ascii=False),
             "u": str(user_id) if user_id else None})
        consulta_id = int(row.scalar())
    except Exception as e:  # noqa: BLE001
        logger.error("Falha ao persistir consulta CFO: %s", e)

    # aprendizado permanente do hub (best-effort, nunca quebra o chat)
    await _hub.aprender(db, "cfo", pergunta or "", resposta_texto)

    return {
        "resposta": resposta_texto, "escalonar": escalonar, "disclaimer": DISCLAIMER_PADRAO,
        "id": consulta_id, "panorama": pano,
    }


async def listar_consultas(db: AsyncSession, area: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    await _garantir_tabela(db)
    limit = max(1, min(int(limit or 50), 200))
    params: dict[str, Any] = {"lim": limit}
    filtro = ""
    if area:
        an = area.strip().lower()
        if an not in AREAS_VALIDAS:
            raise ValueError(f"Área inválida '{area}'.")
        filtro = "WHERE area = :area"; params["area"] = an
    rows = (await db.execute(text(
        f"""SELECT id, area, pergunta, resposta, escalonar, disclaimer, created_by, created_at
            FROM financial_cfo_consultas {filtro} ORDER BY created_at DESC, id DESC LIMIT :lim"""),
        params)).mappings().all()
    return [{
        "id": int(r["id"]), "area": r["area"], "pergunta": r["pergunta"], "resposta": r["resposta"],
        "escalonar": bool(r["escalonar"]), "disclaimer": r["disclaimer"], "created_by": r["created_by"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in rows]
