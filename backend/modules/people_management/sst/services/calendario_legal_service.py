"""Calendário Legal SST — radar único de TODOS os vencimentos legais do módulo.

Agrega, por FATO no banco (nunca fabricado), os vencimentos que sustentam o
compliance SST da empresa:

- PCMSO (sst_pcmso.vigencia_fim) — NR-7
- LTCAT (sst_ltcat.validade_fim) — se NULL, item HONESTO "validade não registrada"
- PGR (gp_risks) — não há campo de data de revisão no banco: item honesto
- CAs dos EPIs do CATÁLOGO (health_epi_catalog.ca_validade) — NR-6
- Treinamentos NR vencendo/vencidos (sst_treinamentos.vencimento) — NR-1
- ASOs vencendo/vencidos (gp_asos.data_validade, agregado) — NR-7
- Fichas de EPI pendentes de assinatura (sst_fichas_epi) — NR-6

Cada item: {titulo, categoria, vencimento|null, dias_restantes, criticidade,
acao_sugerida, fonte}.

Criticidade (calculada, nunca opinativa):
- "vencido"  — vencimento < hoje
- "atencao"  — vence em até 30 dias (ou pendência acionável sem data)
- "ok"       — vence em mais de 30 dias
- "sem_data" — não há data registrada no banco (honesto, cinza)
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Ordem de urgência para o sort do payload (frontend também ordena)
_ORDEM_CRITICIDADE = {"vencido": 0, "atencao": 1, "ok": 2, "sem_data": 3}


def _criticidade(vencimento: date | None, hoje: date) -> str:
    if vencimento is None:
        return "sem_data"
    dias = (vencimento - hoje).days
    if dias < 0:
        return "vencido"
    if dias <= 30:
        return "atencao"
    return "ok"


def _item(
    titulo: str,
    categoria: str,
    vencimento: date | None,
    hoje: date,
    acao_sugerida: str,
    fonte: str,
    criticidade: str | None = None,
) -> dict[str, Any]:
    crit = criticidade or _criticidade(vencimento, hoje)
    return {
        "titulo": titulo,
        "categoria": categoria,
        "vencimento": vencimento.isoformat() if vencimento else None,
        "dias_restantes": (vencimento - hoje).days if vencimento else None,
        "criticidade": crit,
        "acao_sugerida": acao_sugerida,
        "fonte": fonte,
    }


async def montar_calendario_legal(db: AsyncSession) -> dict[str, Any]:
    """Monta o calendário legal SST inteiro a partir dos fatos no banco."""
    hoje = date.today()
    itens: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # 1. PCMSO — vigência (NR-7)
    # ------------------------------------------------------------------
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT medico_coordenador, vigencia_inicio, vigencia_fim "
                    "FROM sst_pcmso ORDER BY vigencia_fim DESC"
                )
            )
        ).mappings().all()
        if rows:
            for r in rows:
                itens.append(
                    _item(
                        titulo=f"PCMSO — fim da vigência (coord. {r['medico_coordenador']})",
                        categoria="pcmso",
                        vencimento=r["vigencia_fim"],
                        hoje=hoje,
                        acao_sugerida=(
                            "Renovar o PCMSO com o médico coordenador antes do fim da "
                            "vigência (NR-7) e anexar o novo documento."
                        ),
                        fonte="sst_pcmso.vigencia_fim",
                    )
                )
        else:
            itens.append(
                _item(
                    titulo="PCMSO — nenhum programa registrado",
                    categoria="pcmso",
                    vencimento=None,
                    hoje=hoje,
                    acao_sugerida="Registrar o PCMSO vigente (médico coordenador, vigência e arquivo) — NR-7.",
                    fonte="sst_pcmso (0 registros)",
                )
            )
    except Exception as exc:  # tabela ausente etc. — nunca inventar
        logger.error("calendario-legal: falha ao ler sst_pcmso: %s", exc)

    # ------------------------------------------------------------------
    # 2. LTCAT — validade (se NULL: item honesto)
    # ------------------------------------------------------------------
    try:
        rows = (
            await db.execute(
                text("SELECT status, responsavel_tecnico, validade_fim FROM sst_ltcat ORDER BY created_at DESC")
            )
        ).mappings().all()
        if rows:
            for r in rows:
                if r["validade_fim"] is None:
                    itens.append(
                        _item(
                            titulo=f"LTCAT ({r['status']}) — validade não registrada",
                            categoria="ltcat",
                            vencimento=None,
                            hoje=hoje,
                            acao_sugerida=(
                                "Registrar a validade do LTCAT (validade_fim) na tela de LTCAT — "
                                "sem a data não é possível monitorar o vencimento."
                            ),
                            fonte="sst_ltcat.validade_fim (NULL)",
                        )
                    )
                else:
                    itens.append(
                        _item(
                            titulo=f"LTCAT — fim da validade ({r['status']})",
                            categoria="ltcat",
                            vencimento=r["validade_fim"],
                            hoje=hoje,
                            acao_sugerida="Revisar/reemitir o LTCAT com o responsável técnico antes do vencimento.",
                            fonte="sst_ltcat.validade_fim",
                        )
                    )
        else:
            itens.append(
                _item(
                    titulo="LTCAT — nenhum laudo registrado",
                    categoria="ltcat",
                    vencimento=None,
                    hoje=hoje,
                    acao_sugerida="Elaborar e registrar o LTCAT (responsável técnico + validade).",
                    fonte="sst_ltcat (0 registros)",
                )
            )
    except Exception as exc:
        logger.error("calendario-legal: falha ao ler sst_ltcat: %s", exc)

    # ------------------------------------------------------------------
    # 3. PGR — revisão (HONESTO: banco não tem data de revisão do PGR)
    # ------------------------------------------------------------------
    try:
        riscos = (await db.execute(text("SELECT count(*) FROM gp_risks"))).scalar() or 0
        itens.append(
            _item(
                titulo=f"PGR — data de revisão não registrada ({riscos} risco(s) mapeado(s))",
                categoria="pgr",
                vencimento=None,
                hoje=hoje,
                acao_sugerida=(
                    "O inventário de riscos (gp_risks) existe, mas o banco não guarda a data de "
                    "elaboração/revisão do PGR. Registrar a data da última revisão para o radar "
                    "monitorar o ciclo de 2 anos (NR-1)."
                ),
                fonte="gp_risks (sem campo de data de revisão)",
            )
        )
    except Exception as exc:
        logger.error("calendario-legal: falha ao ler gp_risks: %s", exc)

    # ------------------------------------------------------------------
    # 4. CAs dos EPIs do CATÁLOGO (NR-6) — com data: 1 item por EPI;
    #    sem data: 1 item agregado honesto
    # ------------------------------------------------------------------
    try:
        rows = (
            await db.execute(
                text(
                    "SELECT nome, ca_numero, ca_validade FROM health_epi_catalog "
                    "WHERE ativo = true ORDER BY ca_validade NULLS LAST, nome"
                )
            )
        ).mappings().all()
        sem_validade = [r for r in rows if r["ca_validade"] is None]
        for r in rows:
            if r["ca_validade"] is not None:
                itens.append(
                    _item(
                        titulo=f"CA {r['ca_numero'] or 's/nº'} — {r['nome']}",
                        categoria="epi_ca",
                        vencimento=r["ca_validade"],
                        hoje=hoje,
                        acao_sugerida=(
                            "Verificar renovação do CA no CAEPI/MTE e substituir o EPI do catálogo "
                            "se o certificado não for renovado (NR-6)."
                        ),
                        fonte="health_epi_catalog.ca_validade",
                    )
                )
        if sem_validade:
            nomes = ", ".join(r["nome"] for r in sem_validade[:5])
            itens.append(
                _item(
                    titulo=f"{len(sem_validade)} CA(s) de EPI sem validade registrada",
                    categoria="epi_ca",
                    vencimento=None,
                    hoje=hoje,
                    acao_sugerida=(
                        f"Registrar a validade do CA no catálogo de EPIs ({nomes}) — consulte o "
                        "CAEPI/MTE pelo número do CA."
                    ),
                    fonte="health_epi_catalog.ca_validade (NULL)",
                )
            )
    except Exception as exc:
        logger.error("calendario-legal: falha ao ler health_epi_catalog: %s", exc)

    # ------------------------------------------------------------------
    # 5. Treinamentos NR (sst_treinamentos.vencimento) — agregados
    # ------------------------------------------------------------------
    try:
        t = (
            await db.execute(
                text(
                    "SELECT count(*) AS total, "
                    "count(*) FILTER (WHERE vencimento < current_date) AS vencidos, "
                    "max(vencimento) FILTER (WHERE vencimento < current_date) AS venc_max, "
                    "count(*) FILTER (WHERE vencimento >= current_date "
                    "  AND vencimento <= current_date + 30) AS vencendo_30d, "
                    "min(vencimento) FILTER (WHERE vencimento >= current_date) AS proximo "
                    "FROM sst_treinamentos"
                )
            )
        ).mappings().first()
        if t and t["total"]:
            if t["vencidos"]:
                itens.append(
                    _item(
                        titulo=f"{t['vencidos']} treinamento(s) NR vencido(s)",
                        categoria="treinamento_nr",
                        vencimento=t["venc_max"],
                        hoje=hoje,
                        acao_sugerida="Reciclar os treinamentos NR vencidos (NR-1) e anexar os certificados.",
                        fonte="sst_treinamentos.vencimento < hoje",
                    )
                )
            if t["vencendo_30d"]:
                itens.append(
                    _item(
                        titulo=f"{t['vencendo_30d']} treinamento(s) NR vencem em 30 dias",
                        categoria="treinamento_nr",
                        vencimento=t["proximo"],
                        hoje=hoje,
                        acao_sugerida="Agendar a reciclagem dos treinamentos NR antes do vencimento.",
                        fonte="sst_treinamentos.vencimento <= hoje+30d",
                    )
                )
        else:
            itens.append(
                _item(
                    titulo="Treinamentos NR — nenhum registro",
                    categoria="treinamento_nr",
                    vencimento=None,
                    hoje=hoje,
                    acao_sugerida=(
                        "Nenhum treinamento NR registrado no banco. Registrar os treinamentos "
                        "realizados (NR-1/NR-6, brigada, primeiros socorros) com certificado."
                    ),
                    fonte="sst_treinamentos (0 registros)",
                )
            )
    except Exception as exc:
        logger.error("calendario-legal: falha ao ler sst_treinamentos: %s", exc)

    # ------------------------------------------------------------------
    # 6. ASOs (gp_asos.data_validade) — agregados, link p/ esteira de exames
    # ------------------------------------------------------------------
    try:
        a = (
            await db.execute(
                text(
                    "SELECT "
                    "count(*) FILTER (WHERE data_validade < current_date) AS vencidos, "
                    "count(DISTINCT employee_id) FILTER (WHERE data_validade < current_date) AS funcs_vencidos, "
                    "max(data_validade) FILTER (WHERE data_validade < current_date) AS venc_max, "
                    "count(*) FILTER (WHERE data_validade >= current_date "
                    "  AND data_validade <= current_date + 30) AS vencendo_30d, "
                    "min(data_validade) FILTER (WHERE data_validade >= current_date) AS proximo "
                    "FROM gp_asos WHERE data_validade IS NOT NULL"
                )
            )
        ).mappings().first()
        if a and a["vencidos"]:
            itens.append(
                _item(
                    titulo=f"{a['vencidos']} ASO(s) vencido(s) ({a['funcs_vencidos']} funcionário(s))",
                    categoria="aso",
                    vencimento=a["venc_max"],
                    hoje=hoje,
                    acao_sugerida=(
                        "Usar o plano de regularização (Exames/ASOs → agendar em lote) para "
                        "recolocar os periódicos em dia (NR-7)."
                    ),
                    fonte="gp_asos.data_validade < hoje",
                )
            )
        if a and a["vencendo_30d"]:
            itens.append(
                _item(
                    titulo=f"{a['vencendo_30d']} ASO(s) vencem em 30 dias",
                    categoria="aso",
                    vencimento=a["proximo"],
                    hoje=hoje,
                    acao_sugerida="Agendar os exames periódicos antes do vencimento (esteira de Exames/ASOs).",
                    fonte="gp_asos.data_validade <= hoje+30d",
                )
            )
    except Exception as exc:
        logger.error("calendario-legal: falha ao ler gp_asos: %s", exc)

    # ------------------------------------------------------------------
    # 7. Fichas de EPI pendentes de assinatura (NR-6) — pendência sem data
    # ------------------------------------------------------------------
    try:
        f = (
            await db.execute(
                text(
                    "SELECT count(*) AS n, count(DISTINCT employee_id) AS funcs "
                    "FROM sst_fichas_epi WHERE status = 'pendente_assinatura'"
                )
            )
        ).mappings().first()
        if f and f["n"]:
            itens.append(
                _item(
                    titulo=f"{f['n']} ficha(s) de EPI pendente(s) de assinatura",
                    categoria="ficha_epi",
                    vencimento=None,
                    hoje=hoje,
                    acao_sugerida=(
                        f"Cobrar a assinatura digital de {f['funcs']} funcionário(s) pelo Portal "
                        "do Funcionário (comprovação de entrega — NR-6)."
                    ),
                    fonte="sst_fichas_epi.status = 'pendente_assinatura'",
                    criticidade="atencao",  # pendência acionável, ainda que sem data de vencimento
                )
            )
    except Exception as exc:
        logger.error("calendario-legal: falha ao ler sst_fichas_epi: %s", exc)

    # Ordena por urgência: vencido → atenção → ok → sem_data; dentro, pela data
    itens.sort(
        key=lambda i: (
            _ORDEM_CRITICIDADE.get(i["criticidade"], 9),
            i["vencimento"] or "9999-12-31",
        )
    )

    resumo = {"vencido": 0, "atencao": 0, "ok": 0, "sem_data": 0}
    for i in itens:
        resumo[i["criticidade"]] = resumo.get(i["criticidade"], 0) + 1

    return {
        "gerado_em": hoje.isoformat(),
        "total": len(itens),
        "resumo": resumo,
        "itens": itens,
    }
