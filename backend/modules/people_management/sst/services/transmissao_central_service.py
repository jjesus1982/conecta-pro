"""Central de Transmissão eSocial — fila assistida do backlog SST (Missão M2).

Monta a FILA do que falta transmitir ao eSocial, com segurança, em lotes
assistidos por humano:

- S-2220 (ASO): gp_asos com status='realizado' e sem recibo (recibo_s2220).
- S-2230 (Afastamento): sst_afastamentos de tipo mapeável na Tabela 18 e
  sem recibo (recibo_s2230).
- S-2240 (Condições Ambientais): funcionários ATIVOS cuja função tem riscos
  CODIFICADOS na Tabela 24 (gp_risks.cod_agente_nocivo, do LTCAT/PGR reais)
  e sem recibo próprio (sst_s2240_transmissoes.recibo_s2240).

REGRAS INEGOCIÁVEIS:
1. NUNCA incluir item "já no governo" (espelho oficial: espelho_recibo nas
   tabelas locais / esocial_eventos_espelho para S-2240) — anti-duplicidade.
2. GATE HUMANO (MB): S-2240 da função ASG NÃO transmitir — o código biológico
   está em disputa (03.01.999 no laudo vs 03.01.007) e aguarda confirmação da
   Márcia/MB. Itens ASG aparecem na fila BLOQUEADOS com o motivo explícito.
3. Dry-run honesto: cada item candidato passa por montar_xml_evento_sst (gera
   o XML SEM transmitir); ValueError = dado obrigatório faltante — o item
   aparece com o erro literal ("aguardando dado", nunca fabricado).
4. Este módulo NÃO transmite nada — quem transmite são as tasks Celery
   (fila gov.esocial), disparadas pelo endpoint de lote sob confirmação
   humana. Enfileirado ≠ aceito: recibo real vem do beat esocial-pull-recibos.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from modules.people_management.hr.services.esocial_service import (
    _cargo_token,
    montar_xml_evento_sst,
)

logger = logging.getLogger(__name__)

TIPOS_FILA = ("S-2220", "S-2230", "S-2240")

# Tipos de afastamento com código na Tabela 18 do eSocial (S-2230)
TIPOS_S2230_MAPEAVEIS = ("doenca", "acidente_trabalho", "acidente_trajeto", "licenca_maternidade")

GATE_MB_MOTIVO = (
    "aguardando confirmação MB código biológico — S-2240 da função ASG está no GATE "
    "HUMANO: o laudo usa 03.01.999 e a Tabela 24 sugere 03.01.007; a Márcia/MB "
    "precisa confirmar antes de qualquer transmissão (evento legal irreversível)."
)

NOTA_HONESTIDADE = (
    "Enfileirado ≠ aceito: a transmissão é REAL (eSocial produção) e o recibo oficial "
    "só existe quando o beat esocial-pull-recibos (2h) o casar. Itens já existentes no "
    "governo (espelho oficial) NUNCA entram na fila. Dado obrigatório ausente aparece "
    "como erro honesto — nunca é fabricado."
)


def _ambiente() -> str:
    amb = (os.getenv("ESOCIAL_AMBIENTE") or "producaorestrita").strip().lower()
    return "producao" if amb in ("producao", "producao_real", "prod", "1") else amb


async def _cpfs_com_espelho_verificado(db: Any) -> set[str]:
    """CPFs cuja caixa do governo JÁ foi consultada pelo espelho (janela consumida).

    Só para esses dá para afirmar 'ausente no governo'; os demais são
    'nao_verificado' (honestidade sobre a cobertura do espelho).
    """
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT cpf FROM esocial_espelho_janelas "
                "WHERE status IN ('consultada', 'vazia')"
            )
        )
    ).scalars().all()
    return {r for r in rows if r}


async def _cpfs_s2240_no_governo(db: Any) -> set[str]:
    """CPFs com S-2240 VÁLIDO no espelho oficial (recibo não excluído por S-3000)."""
    rows = (
        await db.execute(
            text(
                "SELECT DISTINCT esp.cpf_trabalhador FROM esocial_eventos_espelho esp "
                "WHERE esp.tipo = 'S-2240' AND esp.nr_recibo IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM esocial_eventos_espelho ex "
                "  WHERE ex.tipo = 'S-3000' AND ex.xml_completo LIKE "
                "  '%<nrRecEvt>' || esp.nr_recibo || '</nrRecEvt>%')"
            )
        )
    ).scalars().all()
    return {r for r in rows if r}


def _situacao_espelho(cpf: str | None, verificados: set[str]) -> str:
    return "ausente" if (cpf and cpf in verificados) else "nao_verificado"


async def _dry_run(db: Any, tipo: str, ref_id: str) -> tuple[bool, str | None]:
    """Gera o XML SEM transmitir. Retorna (ok, erro honesto)."""
    try:
        await montar_xml_evento_sst(db, tipo, ref_id)
        return True, None
    except ValueError as exc:  # dado obrigatório ausente — erro de DADO, honesto
        return False, str(exc)
    except Exception as exc:  # noqa: BLE001 — falha técnica ≠ dado; nunca mascarar
        logger.warning("Dry-run %s %s: falha técnica: %s", tipo, ref_id, exc)
        return False, f"falha técnica no dry-run (não é dado faltante): {exc}"


def _novo_resumo() -> dict[str, int]:
    return {
        "candidatos": 0,
        "prontos": 0,
        "erro_dado": 0,
        "ja_no_governo": 0,
        "aguardando_recibo": 0,
        "gate_mb": 0,
    }


# ============================================================================
# Filas por tipo
# ============================================================================


async def _fila_s2220(db: Any, verificados: set[str]) -> dict[str, Any]:
    resumo = _novo_resumo()
    itens: list[dict[str, Any]] = []
    rows = (
        await db.execute(
            text(
                "SELECT a.aso_id AS ref_id, a.tipo, a.data_realizacao, a.esocial_status, "
                " a.esocial_protocolo, a.espelho_recibo, a.espelho_fonte, "
                " e.nome, e.cargo, regexp_replace(e.cpf, '\\D', '', 'g') AS cpf "
                "FROM gp_asos a JOIN employees e ON e.id = a.employee_id "
                "WHERE a.status = 'realizado' AND a.recibo_s2220 IS NULL "
                "ORDER BY a.data_realizacao, e.nome"
            )
        )
    ).mappings().all()
    for r in rows:
        resumo["candidatos"] += 1
        if r["espelho_recibo"]:  # JÁ NO GOVERNO — nunca entra na fila
            resumo["ja_no_governo"] += 1
            continue
        if r["esocial_status"] == "transmitida" and r["esocial_protocolo"]:
            resumo["aguardando_recibo"] += 1  # em trânsito — ver acompanhamento
            continue
        ok, erro = await _dry_run(db, "S-2220", str(r["ref_id"]))
        item = {
            "tipo": "S-2220",
            "ref_id": str(r["ref_id"]),
            "funcionario": r["nome"],
            "cargo": r["cargo"],
            "detalhe": f"ASO {r['tipo'] or '?'} realizado em {r['data_realizacao']}",
            "situacao_espelho": _situacao_espelho(r["cpf"], verificados),
            "esocial_status": r["esocial_status"],
            "dry_run_ok": ok,
            "dry_run_erro": erro,
            "pronto": ok,
            "motivo_bloqueio": None if ok else erro,
        }
        resumo["prontos" if ok else "erro_dado"] += 1
        itens.append(item)
    return {"resumo": resumo, "itens": itens}


async def _fila_s2230(db: Any, verificados: set[str]) -> dict[str, Any]:
    resumo = _novo_resumo()
    itens: list[dict[str, Any]] = []
    rows = (
        await db.execute(
            text(
                "SELECT a.id::text AS ref_id, a.tipo, a.data_inicio, a.status, "
                " a.esocial_status, a.esocial_protocolo, a.espelho_recibo, "
                " e.nome, e.cargo, regexp_replace(e.cpf, '\\D', '', 'g') AS cpf "
                "FROM sst_afastamentos a JOIN employees e ON e.id = a.employee_id "
                "WHERE lower(a.tipo) = ANY(:tipos) AND a.recibo_s2230 IS NULL "
                "ORDER BY a.data_inicio, e.nome"
            ),
            {"tipos": list(TIPOS_S2230_MAPEAVEIS)},
        )
    ).mappings().all()
    for r in rows:
        resumo["candidatos"] += 1
        if r["espelho_recibo"]:
            resumo["ja_no_governo"] += 1
            continue
        if r["esocial_status"] == "transmitida" and r["esocial_protocolo"]:
            resumo["aguardando_recibo"] += 1
            continue
        ok, erro = await _dry_run(db, "S-2230", str(r["ref_id"]))
        itens.append(
            {
                "tipo": "S-2230",
                "ref_id": str(r["ref_id"]),
                "funcionario": r["nome"],
                "cargo": r["cargo"],
                "detalhe": f"Afastamento {r['tipo']} desde {r['data_inicio']} ({r['status']})",
                "situacao_espelho": _situacao_espelho(r["cpf"], verificados),
                "esocial_status": r["esocial_status"],
                "dry_run_ok": ok,
                "dry_run_erro": erro,
                "pronto": ok,
                "motivo_bloqueio": None if ok else erro,
            }
        )
        resumo["prontos" if ok else "erro_dado"] += 1
    return {"resumo": resumo, "itens": itens}


async def _funcoes_com_risco_codificado(db: Any) -> set[str]:
    """Tokens de função (PGR) com pelo menos 1 risco codificado na Tabela 24."""
    import json

    rows = (
        await db.execute(
            text(
                "SELECT funcoes_aplicaveis FROM gp_risks "
                "WHERE cod_agente_nocivo IS NOT NULL AND COALESCE(status, '') <> 'encerrado'"
            )
        )
    ).scalars().all()
    tokens: set[str] = set()
    for raw in rows:
        valor = raw
        if isinstance(valor, str):
            try:
                valor = json.loads(valor)
            except ValueError:
                valor = []
        if isinstance(valor, list):
            tokens.update(str(t) for t in valor)
    return tokens


async def _fila_s2240(db: Any, verificados: set[str]) -> dict[str, Any]:
    resumo = _novo_resumo()
    itens: list[dict[str, Any]] = []
    funcoes_codificadas = await _funcoes_com_risco_codificado(db)
    cpfs_governo = await _cpfs_s2240_no_governo(db)
    rows = (
        await db.execute(
            text(
                "SELECT e.id::text AS ref_id, e.nome, e.cargo, "
                " regexp_replace(e.cpf, '\\D', '', 'g') AS cpf, "
                " t.esocial_status, t.esocial_protocolo, t.recibo_s2240 "
                "FROM employees e "
                "LEFT JOIN sst_s2240_transmissoes t ON t.employee_id = e.id "
                "WHERE e.status = 'ativo' OR e.status IS NULL "
                "ORDER BY e.nome"
            )
        )
    ).mappings().all()
    for r in rows:
        token = _cargo_token(r["cargo"])
        if not token or token not in funcoes_codificadas:
            continue  # função sem risco codificado no LTCAT — não há evento a gerar
        resumo["candidatos"] += 1
        if r["recibo_s2240"] or (r["cpf"] and r["cpf"] in cpfs_governo):
            resumo["ja_no_governo"] += 1  # nunca entra na fila
            continue
        if r["esocial_status"] in ("enfileirada", "transmitida") and (
            r["esocial_protocolo"] or r["esocial_status"] == "enfileirada"
        ):
            resumo["aguardando_recibo"] += 1
            continue
        base = {
            "tipo": "S-2240",
            "ref_id": str(r["ref_id"]),
            "funcionario": r["nome"],
            "cargo": r["cargo"],
            "situacao_espelho": _situacao_espelho(r["cpf"], verificados),
            "esocial_status": r["esocial_status"],
        }
        if token == "ASG":
            # GATE HUMANO — não roda nem dry-run: nada deve encorajar transmissão
            resumo["gate_mb"] += 1
            itens.append(
                {
                    **base,
                    "detalhe": "Condições ambientais — função ASG (código biológico em disputa)",
                    "dry_run_ok": None,
                    "dry_run_erro": None,
                    "pronto": False,
                    "motivo_bloqueio": GATE_MB_MOTIVO,
                }
            )
            continue
        ok, erro = await _dry_run(db, "S-2240", str(r["ref_id"]))
        itens.append(
            {
                **base,
                "detalhe": f"Condições ambientais — função {token} (riscos do LTCAT/PGR)",
                "dry_run_ok": ok,
                "dry_run_erro": erro,
                "pronto": ok,
                "motivo_bloqueio": None if ok else erro,
            }
        )
        resumo["prontos" if ok else "erro_dado"] += 1
    return {"resumo": resumo, "itens": itens}


# ============================================================================
# API do serviço
# ============================================================================


async def fila_transmissao(db: Any, tipos: list[str] | None = None) -> dict[str, Any]:
    """Fila completa (ou por tipo) com resumo — leitura pura, NADA é transmitido."""
    pedidos = [t for t in (tipos or TIPOS_FILA) if t in TIPOS_FILA] or list(TIPOS_FILA)
    verificados = await _cpfs_com_espelho_verificado(db)
    builders = {"S-2220": _fila_s2220, "S-2230": _fila_s2230, "S-2240": _fila_s2240}

    por_tipo: dict[str, Any] = {}
    geral = _novo_resumo()
    for tipo in pedidos:
        por_tipo[tipo] = await builders[tipo](db, verificados)
        for k, v in por_tipo[tipo]["resumo"].items():
            geral[k] += v

    return {
        "gerado_em": datetime.now(UTC).isoformat(),
        "ambiente": _ambiente(),
        "honestidade": NOTA_HONESTIDADE,
        "gate_mb": GATE_MB_MOTIVO,
        "resumo_geral": geral,
        "tipos": por_tipo,
    }


async def validar_lote(
    db: Any, tipo: str, ref_ids: list[str], max_itens: int = 20
) -> dict[str, Any]:
    """Revalida cada ref contra a fila ATUAL antes de enfileirar (dupla checagem).

    Retorna {'aprovados': [itens prontos], 'pulados': [{'ref_id', 'motivo'}]}.
    O teto de 20 itens por lote é do desenho (lotes assistidos, rate suave).
    """
    tipo = str(tipo).upper().strip()
    if tipo not in TIPOS_FILA:
        raise ValueError(f"tipo '{tipo}' inválido — a Central transmite {', '.join(TIPOS_FILA)}.")
    max_itens = max(1, min(int(max_itens or 20), 20))

    verificados = await _cpfs_com_espelho_verificado(db)
    builders = {"S-2220": _fila_s2220, "S-2230": _fila_s2230, "S-2240": _fila_s2240}
    fila = await builders[tipo](db, verificados)
    por_ref = {i["ref_id"]: i for i in fila["itens"]}

    aprovados: list[dict[str, Any]] = []
    pulados: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for ref in ref_ids:
        ref = str(ref).strip()
        if not ref or ref in vistos:
            continue
        vistos.add(ref)
        item = por_ref.get(ref)
        if item is None:
            pulados.append(
                {
                    "ref_id": ref,
                    "motivo": (
                        "fora da fila atual — inexistente, já no governo (espelho), "
                        "já com recibo, ou aguardando recibo de transmissão anterior."
                    ),
                }
            )
            continue
        if not item["pronto"]:
            pulados.append({"ref_id": ref, "motivo": item["motivo_bloqueio"] or "não pronto"})
            continue
        if len(aprovados) >= max_itens:
            pulados.append(
                {"ref_id": ref, "motivo": f"acima do teto do lote ({max_itens} itens) — envie no próximo lote."}
            )
            continue
        aprovados.append(item)
    return {"aprovados": aprovados, "pulados": pulados, "max_itens": max_itens}


async def acompanhamento(db: Any, limite: int = 50) -> dict[str, Any]:
    """Últimas transmissões NOSSAS (fonte: colunas esocial_* das tabelas de origem).

    Agrupa: aguardando_recibo (protocolo real, recibo ainda não casado pelo
    pull 2h), aceitos (recibo real casado) e rejeitados/erro.
    """
    limite = max(1, min(int(limite or 50), 200))
    rows = (
        await db.execute(
            text(
                "SELECT * FROM ("
                " SELECT 'S-2220' AS tipo, a.aso_id AS ref_id, e.nome AS funcionario, "
                "  a.esocial_status, a.esocial_protocolo, a.recibo_s2220 AS recibo, a.updated_at "
                " FROM gp_asos a JOIN employees e ON e.id = a.employee_id "
                " WHERE a.esocial_status IS NOT NULL AND a.esocial_status <> 'nao_transmitida' "
                " UNION ALL "
                " SELECT 'S-2230', f.id::text, e.nome, "
                "  f.esocial_status, f.esocial_protocolo, f.recibo_s2230, f.updated_at "
                " FROM sst_afastamentos f JOIN employees e ON e.id = f.employee_id "
                " WHERE f.esocial_status IS NOT NULL AND f.esocial_status <> 'nao_transmitida' "
                " UNION ALL "
                " SELECT 'S-2210', c.cat_id, e.nome, "
                "  c.esocial_status, c.esocial_protocolo, c.numero_recibo_esocial, c.updated_at "
                " FROM gp_cats c JOIN employees e ON e.id::text = c.employee_id "
                " WHERE c.esocial_status IS NOT NULL AND c.esocial_status <> 'nao_transmitida' "
                " UNION ALL "
                " SELECT 'S-2240', t.employee_id::text, e.nome, "
                "  t.esocial_status, t.esocial_protocolo, t.recibo_s2240, t.atualizado_em "
                " FROM sst_s2240_transmissoes t JOIN employees e ON e.id = t.employee_id "
                " WHERE t.esocial_status IS NOT NULL"
                ") u ORDER BY u.updated_at DESC NULLS LAST LIMIT :lim"
            ),
            {"lim": limite},
        )
    ).mappings().all()

    eventos = [dict(r) for r in rows]
    for ev in eventos:
        ev["updated_at"] = ev["updated_at"].isoformat() if ev.get("updated_at") else None
        if ev["recibo"]:
            ev["grupo"] = "recibo_casado"
        elif ev["esocial_status"] in ("rejeitada", "erro"):
            ev["grupo"] = "rejeitado_ou_erro"
        elif ev["esocial_protocolo"] or ev["esocial_status"] in ("transmitida", "enfileirada"):
            ev["grupo"] = "aguardando_recibo"
        else:
            ev["grupo"] = "outro"

    contagem = {"aguardando_recibo": 0, "recibo_casado": 0, "rejeitado_ou_erro": 0, "outro": 0}
    for ev in eventos:
        contagem[ev["grupo"]] += 1

    return {
        "gerado_em": datetime.now(UTC).isoformat(),
        "honestidade": (
            "Protocolo e recibo são SEMPRE os devolvidos pelo governo. 'Aguardando recibo' "
            "significa transmitido com protocolo real; o recibo é casado pelo beat "
            "esocial-pull-recibos a cada 2h — nada aqui é fabricado."
        ),
        "contagem": contagem,
        "eventos": eventos,
    }
