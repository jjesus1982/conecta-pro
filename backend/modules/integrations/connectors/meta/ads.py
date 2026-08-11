"""
Meta Ads (Marketing API) → Conecta PRO

Puxa CAMPANHA e GASTO da conta de anúncios da Conecta Mais para
`marketing_campaigns`, que já tem as colunas certas (`budget`, `spent`,
`utm_campaign`). Fecha o laço que hoje está aberto:

    gasto do anúncio (Meta)  ÷  leads gerados (CRM, por utm_campaign)  =  CAC

Sem isto, marketing decide por sensação: o Conecta PRO sabe quantos leads
vieram de cada campanha (quando o link carrega `[c:<slug>]`), mas não sabe
quanto cada uma custou.

**Não precisa de App Review.** Ler a PRÓPRIA conta de anúncios com um System
User do próprio Business Manager é acesso a ativo próprio. Review é exigido
para agir em nome de terceiros (ex.: mensageria de Instagram) — outro trilho.

Dorme até o token estar configurado, no mesmo padrão do `capi.py`: nenhuma
chamada, nenhum erro, nenhum ruído.

Configuração (env):
  META_ADS_TOKEN       -> System User token com `ads_read` (SECRET; vazio = desligado)
  META_AD_ACCOUNT_ID   -> id da conta de anúncios, com o prefixo (ex.: act_123456789)
  META_GRAPH_VERSION   -> versão da Graph API (default v21.0, mesmo do capi.py)

Uso:
  from modules.integrations.connectors.meta.ads import sincronizar_campanhas
  resultado = await sincronizar_campanhas(db)          # últimos 30 dias
  resultado = await sincronizar_campanhas(db, dias=7)
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta

import aiohttp
from sqlalchemy import text

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.facebook.com"
_TIMEOUT = aiohttp.ClientTimeout(total=30)


def _dia(valor: str | None) -> date | None:
    """'2026-08-01T00:00:00-0400' → date(2026, 8, 1).

    `start_date`/`end_date` são colunas DATE e o asyncpg não aceita string:
    estoura "'str' object has no attribute 'toordinal'". Recorte de 10 chars
    não basta — tem que virar objeto date.
    """
    if not valor:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _token() -> str:
    # Lido a cada chamada para refletir mudança de env sem rebuild (igual capi.py).
    return os.getenv("META_ADS_TOKEN", "").strip()


def _conta() -> str:
    c = os.getenv("META_AD_ACCOUNT_ID", "").strip()
    return c if c.startswith("act_") or not c else f"act_{c}"


def ads_ativo() -> bool:
    """True quando há token E conta configurados. Sem isso, dorme."""
    return bool(_token() and _conta())


async def _get(sessao: aiohttp.ClientSession, caminho: str, params: dict) -> dict | None:
    versao = os.getenv("META_GRAPH_VERSION", "v21.0")
    url = f"{_GRAPH}/{versao}/{caminho}"
    try:
        async with sessao.get(url, params={**params, "access_token": _token()}, timeout=_TIMEOUT) as r:
            corpo = await r.json()
            if r.status != 200:
                # A Meta devolve o motivo em error.message — logar isso vale mais que o status.
                erro = (corpo or {}).get("error", {})
                logger.error(
                    "Meta Ads: HTTP %s em %s — %s (code=%s subcode=%s)",
                    r.status, caminho, erro.get("message"), erro.get("code"), erro.get("error_subcode"),
                )
                return None
            return corpo
    except Exception as e:  # noqa: BLE001 — rede/timeout nunca derruba quem chamou
        logger.error("Meta Ads: falha em %s: %s", caminho, e)
        return None


async def sincronizar_campanhas(db, *, dias: int = 30) -> dict:
    """Traz campanhas + gasto do período e grava em `marketing_campaigns`.

    Idempotente: casa por `external_id` = id da campanha na Meta (chave estável;
    o NOME o marketing renomeia). **`utm_campaign` NÃO é tocada** — ela guarda o
    slug que o link carrega (`[c:lote2]`) e é a chave de junção com `leads`.
    Gravar o id numérico da Meta ali quebraria o join para sempre.
    """
    if not ads_ativo():
        return {"ok": False, "motivo": "META_ADS_TOKEN/META_AD_ACCOUNT_ID ausentes — sincronia dorme"}

    desde = (date.today() - timedelta(days=dias)).isoformat()
    ate = date.today().isoformat()
    vistos, gravados = 0, 0

    async with aiohttp.ClientSession() as s:
        campanhas = await _get(
            s,
            f"{_conta()}/campaigns",
            {"fields": "id,name,status,daily_budget,lifetime_budget,start_time,stop_time", "limit": 200},
        )
        if campanhas is None:
            return {"ok": False, "motivo": "Meta não respondeu (ver log)"}

        # Insights numa chamada só, agrupado por campanha — evita N+1 na Graph API.
        insights = await _get(
            s,
            f"{_conta()}/insights",
            {
                "level": "campaign",
                "fields": "campaign_id,spend,impressions,clicks",
                "time_range": f'{{"since":"{desde}","until":"{ate}"}}',
                "limit": 500,
            },
        )
    gasto = {
        i["campaign_id"]: i for i in ((insights or {}).get("data") or []) if i.get("campaign_id")
    }

    for c in (campanhas.get("data") or []):
        vistos += 1
        ins = gasto.get(c["id"], {})
        # Meta devolve orçamento em CENTAVOS (string). Dividir aqui, uma vez.
        orcamento = c.get("daily_budget") or c.get("lifetime_budget")
        orcamento = (float(orcamento) / 100) if orcamento else None
        await db.execute(
            text(
                """
                INSERT INTO marketing_campaigns
                    (id, name, type, status, budget, spent, start_date, end_date,
                     utm_source, utm_medium, external_id, created_at, updated_at)
                VALUES (gen_random_uuid(), :nome, 'meta_ads', :status, :orc, :gasto,
                        :inicio, :fim, 'meta', 'paid', :cid, now(), now())
                -- O predicado é OBRIGATÓRIO aqui: ux_marketing_campaigns_external_id
                -- é um índice PARCIAL (WHERE external_id IS NOT NULL), e o Postgres
                -- não infere índice parcial sem que o ON CONFLICT repita o predicado.
                -- Sem ele: "there is no unique or exclusion constraint matching the
                -- ON CONFLICT specification" já na primeira campanha.
                ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO UPDATE SET
                    name = excluded.name, status = excluded.status,
                    budget = coalesce(excluded.budget, marketing_campaigns.budget),
                    spent = excluded.spent, updated_at = now()
                    -- utm_campaign de fora do SET de propósito: é do humano/link, não da Meta
                """
            ),
            {
                "nome": (c.get("name") or "(sem nome)")[:255],
                "status": (c.get("status") or "").lower()[:40],
                "orc": orcamento,
                "gasto": float(ins.get("spend") or 0),
                "inicio": _dia(c.get("start_time")),
                "fim": _dia(c.get("stop_time")),
                "cid": c["id"],
            },
        )
        gravados += 1
    await db.commit()
    logger.info("Meta Ads: %s campanhas vistas, %s gravadas (janela %sd)", vistos, gravados, dias)
    return {"ok": True, "campanhas": vistos, "gravadas": gravados, "desde": desde, "ate": ate}


# ── Importação por CSV — a via que não depende de token ────────────────────
# Existe porque o token da Marketing API está travado numa verificação por SMS
# que a Meta simplesmente não entrega (duas linhas testadas, ambas recebendo SMS
# de outras origens normalmente). O dado que o negócio precisa é gasto por
# campanha; a API era só o encanamento. O Gerenciador de Anúncios exporta o mesmo
# conteúdo em CSV, e ele cai nas MESMAS colunas — `cac_por_campanha` não muda.

# A exportação sai no idioma da conta e os títulos mudam. Casar por conteúdo, não
# por posição: posição quebra quando alguém reordena as colunas na tela.
_COLUNAS = {
    "id": ("identificação da campanha", "identificacao da campanha", "campaign id"),
    "nome": ("nome da campanha", "campaign name"),
    "gasto": ("valor gasto", "amount spent"),
    "inicio": ("início dos relatórios", "inicio dos relatorios", "reporting starts"),
    "fim": ("término dos relatórios", "termino dos relatorios", "reporting ends"),
}


def _achar_coluna(cabecalho: list[str], chave: str) -> str | None:
    """Acha o título real da coluna. 'Valor gasto (BRL)' casa com 'valor gasto'."""
    for titulo in cabecalho:
        limpo = (titulo or "").strip().lower()
        if any(limpo.startswith(alvo) for alvo in _COLUNAS[chave]):
            return titulo
    return None


def _numero(valor: str | None) -> float:
    """'1.234,56' e '1234.56' → float. A exportação pt-BR usa vírgula decimal."""
    t = (valor or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return 0.0
    if "," in t:  # pt-BR: ponto é milhar, vírgula é decimal
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return 0.0


async def importar_csv(db, caminho: str) -> dict:
    """Lê um export do Gerenciador de Anúncios e grava em `marketing_campaigns`.

    Idempotente pelo mesmo `external_id` da sincronia por API — então importar o
    CSV hoje e ligar a API amanhã **atualiza as mesmas linhas**, não duplica.
    Sem "Identificação da campanha" no arquivo, cai no nome com prefixo `csv:`
    (menos estável — o marketing renomeia campanha —, mas é o que há).
    """
    import csv

    # utf-8-sig: o CSV da Meta vem com BOM, e sem isso o PRIMEIRO título fica
    # com '﻿' colado e nunca casa.
    with open(caminho, encoding="utf-8-sig", newline="") as f:
        amostra = f.read(4096)
        f.seek(0)
        try:
            dialeto = csv.Sniffer().sniff(amostra, delimiters=",;\t")
        except csv.Error:
            dialeto = csv.excel  # arquivo de uma coluna só — vírgula serve
        linhas = list(csv.DictReader(f, dialect=dialeto))

    if not linhas:
        return {"ok": False, "motivo": "CSV vazio"}

    cab = list(linhas[0].keys())
    col = {k: _achar_coluna(cab, k) for k in _COLUNAS}
    if not col["nome"] or not col["gasto"]:
        return {
            "ok": False,
            "motivo": f"CSV sem coluna de nome e/ou de gasto — títulos lidos: {cab[:8]}",
        }

    gravados = 0
    for r in linhas:
        nome = (r.get(col["nome"]) or "").strip()
        if not nome:
            continue
        cid = (r.get(col["id"]) or "").strip() if col["id"] else ""
        await db.execute(
            text(
                """
                INSERT INTO marketing_campaigns
                    (id, name, type, status, spent, start_date, end_date,
                     utm_source, utm_medium, external_id, created_at, updated_at)
                VALUES (gen_random_uuid(), :nome, 'meta_ads', 'imported', :gasto,
                        :inicio, :fim, 'meta', 'paid', :cid, now(), now())
                ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO UPDATE SET
                    name = excluded.name, spent = excluded.spent, updated_at = now()
                    -- utm_campaign fora do SET, igual à sincronia por API
                """
            ),
            {
                "nome": nome[:255],
                "gasto": _numero(r.get(col["gasto"])),
                "inicio": _dia(r.get(col["inicio"])) if col["inicio"] else None,
                "fim": _dia(r.get(col["fim"])) if col["fim"] else None,
                "cid": cid or f"csv:{nome[:80]}",
            },
        )
        gravados += 1
    await db.commit()
    logger.info("Meta Ads CSV: %s campanhas importadas de %s", gravados, caminho)
    return {"ok": True, "campanhas": gravados, "por_id": bool(col["id"])}


async def cac_por_campanha(db, *, dias: int = 30) -> list[dict]:
    """CAC por campanha: gasto da Meta ÷ leads que o Conecta PRO atribuiu a ela.

    A junção é `marketing_campaigns.utm_campaign` × `leads.utm_campaign` — e ela
    exige DUAS coisas que hoje faltam: (1) alguém preencher `utm_campaign` na
    campanha, com o mesmo slug do link; (2) o link do wa.me carregar `[c:<slug>]`.
    Sem isso o CAC sai como **None, não 0**: "nenhum lead" e "não sei quantos"
    são coisas diferentes, e um 0 faria a campanha parecer fracasso quando o que
    há é ausência de medição.
    """
    linhas = (
        await db.execute(
            text(
                """
                SELECT c.name, c.utm_campaign, c.status,
                       coalesce(c.spent, 0) AS gasto,
                       count(l.id) FILTER (WHERE l.created_at >= now() - make_interval(days => :d)) AS leads
                  FROM marketing_campaigns c
                  LEFT JOIN leads l ON l.utm_campaign = c.utm_campaign
                 WHERE c.type = 'meta_ads'
                 GROUP BY c.id, c.name, c.utm_campaign, c.status, c.spent
                 ORDER BY gasto DESC
                """
            ),
            {"d": dias},
        )
    ).mappings().all()
    saida = []
    for r in linhas:
        leads = r["leads"] or 0
        saida.append(
            {
                "campanha": r["name"],
                "status": r["status"],
                "gasto": float(r["gasto"]),
                "leads": leads,
                # None (não 0) quando não há lead atribuído: é ausência de dado, não CAC infinito.
                "cac": round(float(r["gasto"]) / leads, 2) if leads else None,
            }
        )
    return saida
