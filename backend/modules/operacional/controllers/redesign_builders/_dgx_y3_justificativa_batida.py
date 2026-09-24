"""DGX Y3 — o ciclo da justificativa fecha, e a batida que falta ganha nome (24/09/2026).

Duas abas em **g-ponto**:

* **`justificativas-fila`** — a fila do DP. Toda justificativa pendente, com **há quantos dias
  está parada**, o dia justificado, o motivo, o anexo, e o que a folha já descontou de falta
  naquele mês. Por linha: **Deferir** e **Indeferir com motivo**.
  A aba «Revisar justificativas» que já existia tem os dois botões e não tem nada disso — ela
  mostra nome, motivo e o dia da criação em DD/MM. A rota de aprovar é a MESMA
  (`PunchService.revisar_justificativa`); o que faltava era a fila e o efeito.
* **`batida-faltando`** — quem trabalhou e não tem a batida de entrada e/ou de saída, com o turno
  previsto, as batidas que existem e **o que o mapa de ponto conclui hoje**. Por linha:
  **Lançar batida** (a ação `ponto-ajuste` que já existe, com pessoa e dia da própria linha) e
  **Justificar** (a rota `POST /ponto/justificativa` que já existe).

**Nada aqui muda um centavo.** Deferir chama o serviço de sempre e, em seguida, reapura a
conferência da X2: o dia vira abono e a linha passa a «passivo a devolver» se aquele mês teve
desconto de falta. É PROPOSTA, escrita em `ponto_folha_conferencia` — `hr_payslips` intacto.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` (topo) e chama
`telas(db, out)` no FIM do `build()`; as abas ficam no FIM do g-ponto em `_dp_grupos`.
"""

from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (mesma mina de import circular da F1/W5/X2)
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t  # noqa: E402
from modules.people_management.ponto.services import justificativa_batida as jb  # noqa: E402

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"

ABAS = (
    ("justificativas-fila", "Fila de justificativas"),
    ("batida-faltando", "Batida faltando"),
)

_CATEGORIAS = (
    ("saude", "Saúde"),
    ("familiar", "Familiar"),
    ("transito", "Trânsito"),
    ("transporte_publico", "Transporte público"),
    ("acidente", "Acidente"),
    ("outro", "Outro"),
)


def _dm(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


async def telas(db, out: dict | None = None) -> dict:
    await jb._ensure(db)
    mine, _safe, _tbl = _helpers(db)
    prazo = await jb.prazo_dias(db)

    # ── A. a fila da justificativa ────────────────────────────────────────────────────────
    fila = await jb.fila(db)
    atrasadas = [x for x in fila if int(x["dias_parada"] or 0) > prazo]
    mais_velha = max((int(x["dias_parada"] or 0) for x in fila), default=0)

    def _acao(r: dict, dec: str, lbl: str, estilo: str, campos: list[dict]) -> dict:
        ok = "Justificativa deferida." if dec == "aprovar" else "Justificativa indeferida, com o motivo registrado."
        return {
            "title": f"{lbl}: {r['nome']}",
            "endpoint": f"{_ACT}y3-justificativa-revisar?jid={r['justification_id']}",
            "method": "POST",
            "btnLabel": lbl,
            "submitLabel": lbl,
            "btnStyle": estilo,
            "okMsg": ok,
            "showResult": True,
            "fixed": {"acao": dec},
            "fields": campos,
        }

    def _linha_fila(r: dict) -> dict:
        dias = int(r["dias_parada"] or 0)
        desc = float(r["folha_desconto_mes"] or 0)
        return {
            "cells": [
                t(r["nome"][:30], 700, _ND),
                t(_dm(r["dia"].isoformat()) + (" (criação)" if r["dia_por_criacao"] else "")),
                b(f"{dias} dia(s)", "bad" if dias > prazo else ("warn" if dias >= prazo else "mut")),
                t((r["justification_type"] or "—").replace("_", " ")),
                t((r["reason"] or "—")[:110]),
                b(f"{r['anexos']} anexo(s)", "info") if r["anexos"] else t("sem anexo", 400, "#94A3B8"),
                t(brl(desc), 700, "#B91C1C") if desc else t("não"),
            ],
            "docs": [
                {"label": "Motivo declarado", "value": r["reason"] or "—"},
                {
                    "label": "De onde veio",
                    "value": f"{r['source'] or 'app'} · registrada em "
                    f"{r['created_at']:%d/%m/%Y %H:%M} · posto {r['posto']}",
                },
                {
                    "label": "Se for deferida",
                    "value": (
                        f"O dia {_dm(r['dia'].isoformat())} entra como ABONO na conferência ponto × folha "
                        f"({r['dia'].strftime('%m/%Y')}). "
                        + (
                            f"Aquele mês já descontou {brl(desc)} de falta desta pessoa — a linha dela vira "
                            "«passivo a devolver» na aba «Falta justificada: conferência». "
                            if desc
                            else "Aquele mês não descontou falta desta pessoa: nada a devolver. "
                        )
                        + "**O holerite não muda** — a devolução é uma proposta, e quem paga é o dono."
                    ),
                },
            ],
            "filtros": {"Prazo": "estourado" if dias > prazo else "no prazo", "Tipo": r["justification_type"] or "—"},
            "actions": [
                _acao(
                    r,
                    "aprovar",
                    "Deferir",
                    "primary",
                    [{"key": "motivo", "label": "Observação (opcional)", "type": "text"}],
                ),
                _acao(
                    r,
                    "rejeitar",
                    "Indeferir",
                    "danger",
                    [
                        {
                            "key": "motivo",
                            "label": "Motivo da recusa* (mín. 5 caracteres)",
                            "type": "textarea",
                            "ph": "É a resposta que o colaborador vai ler.",
                        }
                    ],
                ),
            ],
        }

    mine["justificativas-fila"] = {
        "title": "Fila de justificativas de ponto",
        "sub": (
            f"**{len(fila)} pendente(s)**"
            + (f", a mais antiga parada há **{mais_velha} dias**" if fila else "")
            + f". Prazo de revisão: **{prazo} dia(s)** (parâmetro `{jb.PARAM_PRAZO}`) — "
            + (
                f"**{len(atrasadas)} passaram do prazo** e aparecem no painel de alertas do sistema. "
                if atrasadas
                else "nenhuma passou do prazo. "
            )
            + "Deferir chama o mesmo serviço de sempre e, em seguida, reapura a conferência ponto × folha: "
            "o dia vira abono e, se aquele mês descontou falta desta pessoa, a linha dela entra como "
            "**passivo a devolver**. **Nenhum holerite é tocado** — a devolução é proposta, não pagamento. "
            "Indeferir **exige motivo**: é a resposta que o colaborador vai ler."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar pessoa, motivo…",
        "grid": "1.4fr 0.8fr 0.8fr 0.8fr 2.6fr 0.9fr 0.9fr",
        "cols": ["Pessoa", "Dia", "Parada há", "Tipo", "Motivo", "Anexo", "Mês descontou falta?"],
        "filtros": [{"key": "Prazo", "label": "Prazo"}, {"key": "Tipo", "label": "Tipo"}],
        "rows": [_linha_fila(r) for r in fila]
        or [{"cells": [t("Nenhuma justificativa pendente", 500)] + [t("—")] * 6}],
    }

    # ── B. a batida que falta ─────────────────────────────────────────────────────────────
    resumo = await jb.resumo_batidas(db, dias=jb.JANELA_DIAS_PADRAO)
    linhas, por_pessoa = resumo["linhas"], resumo["por_pessoa"]
    n_entrada = sum(1 for x in linhas if not x["tem_entrada"])
    n_saida = sum(1 for x in linhas if not x["tem_saida"])

    def _linha_batida(r: dict) -> dict:
        eid, dia = r["employee_id"], r["dia"]
        batidas = ", ".join(r["batidas"]) or ("check-in manual do supervisor" if r["checkin_manual"] else "nenhuma")
        return {
            "cells": [
                t(r["nome"][:30], 700, _ND),
                t(_dm(dia)),
                t(r["turno"]),
                t(f"{r['posto'][:24]} · {r['cliente'][:18]}"),
                b(f"falta {r['falta']}", "bad" if not r["tem_entrada"] else "warn"),
                t(batidas[:70]),
                t((r["estado_mapa"] or "—").replace("_", " ")),
            ],
            "docs": [
                {
                    "label": "O que o mapa de ponto conclui hoje",
                    "value": (
                        f"«{(r['estado_mapa'] or '—').replace('_', ' ')}» — régua da frente 04, tolerância de "
                        f"{r['tolerancia_min']} min. "
                        + (
                            "Sem a batida de ENTRADA, a primeira batida da janela é a de saída e o mapa lê o "
                            "turno inteiro como atraso. Por isso a conferência da X2 marca este dia como "
                            "`entrada_ausente` e o **tira da conta de dinheiro**: não é atraso, é batida que "
                            "não houve."
                            if not r["tem_entrada"]
                            else "A entrada está registrada, então o atraso deste dia foi medido do jeito certo "
                            "e conta. O que falta é a hora de saída — isso é jornada, e aparece no espelho, "
                            "não no atraso."
                        )
                    ),
                },
                {
                    "label": "E a falta?",
                    "value": (
                        "Este dia **não vira falta automática**. O espelho só conta falta em dia de escala "
                        "**sem nenhuma batida**, e aqui houve batida. Enquanto a batida falta, é pendência de "
                        "operação — não desconto."
                    ),
                },
                {"label": "Batidas do turno", "value": batidas},
            ],
            "filtros": {"Falta": r["falta"], "Posto": r["posto"][:24]},
            "actions": [
                {
                    "title": f"Lançar batida — {r['nome']} · {_dm(dia)}",
                    "endpoint": f"{_ACT}ponto-ajuste?eid={eid}&dia={dia}",
                    "method": "POST",
                    "btnLabel": "Lançar batida",
                    "submitLabel": "Lançar",
                    "btnStyle": "primary",
                    "okMsg": "Batida lançada — fica na trilha de auditoria como ajuste do DP.",
                    "fields": [
                        {
                            "key": "punch_type",
                            "label": "Qual batida*",
                            "type": "select",
                            "options": [{"value": "entrada", "label": "Entrada"}, {"value": "saida", "label": "Saída"}],
                            "value": "entrada" if not r["tem_entrada"] else "saida",
                        },
                        {
                            "key": "hora",
                            "label": "Hora real (HH:MM)*",
                            "type": "text",
                            "ph": r["turno"].split("–")[0 if not r["tem_entrada"] else 1],
                        },
                        {"key": "motivo", "label": "Motivo* (mín. 5 caracteres)", "type": "textarea"},
                    ],
                },
                {
                    "title": f"Justificar — {r['nome']} · {_dm(dia)}",
                    "endpoint": "/api/v1/people-management/ponto/justificativa",
                    "method": "POST",
                    "btnLabel": "Justificar",
                    "submitLabel": "Registrar",
                    "btnStyle": "secondary",
                    "okMsg": "Justificativa registrada — nasce PENDENTE, aparece na aba «Fila de justificativas».",
                    "fixed": {"employee_id": eid, "justification_type": "atraso"},
                    "fields": [
                        {
                            "key": "category",
                            "label": "Motivo*",
                            "type": "select",
                            "options": [{"value": v, "label": lb} for v, lb in _CATEGORIAS],
                        },
                        {
                            "key": "reason",
                            "label": "O que aconteceu* (mín. 5 caracteres)",
                            "type": "textarea",
                            "value": f"Batida de {r['falta']} não registrada em {_dm(dia)} "
                            f"(turno {r['turno']}, {r['posto']}). ",
                        },
                    ],
                },
            ],
        }

    piores = sorted(por_pessoa.items(), key=lambda kv: -kv[1]["dias"])[:5]
    mine["batida-faltando"] = {
        "title": "Batida faltando — quem trabalhou e não bateu",
        "sub": (
            f"**{len(linhas)} dia(s)-pessoa** em {len(por_pessoa)} pessoa(s), entre {resumo['de'][8:10]}/"
            f"{resumo['de'][5:7]} e {resumo['ate'][8:10]}/{resumo['ate'][5:7]}: falta a ENTRADA em "
            f"{n_entrada} e a SAÍDA em {n_saida}. Turno sem batida nenhuma **não** entra aqui — aquilo é "
            f"falta/descoberto e tem tela própria. Enquanto a batida falta, o dia **não entra na conta de "
            f"atraso** (a conferência da X2 o separa como `entrada_ausente`) e **não vira falta automática** "
            f"(o espelho só conta dia sem nenhuma batida). É dívida de OPERAÇÃO — app, aparelho, "
            f"treinamento — e quem resolve é o supervisor. "
            + (
                "Quem mais deve: " + " · ".join(f"{n.split()[0].title()} ({p['dias']}d)" for n, p in piores) + "."
                if piores
                else ""
            )
            + (
                f" Fora desta conta: **{len(resumo['escala_divergente'])} dia(s)** em que a batida EXISTE, só que "
                "fora do turno previsto — ali não falta batida, falta acertar a escala lançada."
                if resumo["escala_divergente"]
                else ""
            )
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar pessoa, posto…",
        "grid": "1.4fr 0.6fr 0.9fr 1.8fr 1fr 1.8fr 1fr",
        "cols": ["Pessoa", "Dia", "Turno previsto", "Posto", "Falta", "Batidas do turno", "O mapa conclui"],
        "filtros": [{"key": "Falta", "label": "Qual batida"}, {"key": "Posto", "label": "Posto"}],
        "rows": [_linha_batida(r) for r in linhas]
        or [{"cells": [t("Nenhuma batida faltando na janela", 500)] + [t("—")] * 6}],
    }

    # a frente roda DEPOIS de `montar_grupos`: anexa as abas ao fim do g-ponto, como a X2 faz
    grupo = (out or {}).get("g-ponto")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in ABAS:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-ponto", tid)
    if out is not None:
        out.update(mine)
    return mine


@router.post("/action/y3-justificativa-revisar")
async def rd_y3_justificativa_revisar(
    current_user: CurrentActiveUser,
    jid: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Defere ou indefere uma justificativa — e diz, na resposta, o efeito PROPOSTO na folha.

    `jid` vem da LINHA da tabela, não do usuário. O revisor é a identidade real de quem está
    logado. Quem muda o estado da justificativa é `PunchService.revisar_justificativa`, o mesmo
    serviço da rota `PUT /ponto/justificativa/{id}/revisar` — não há um segundo escritor.
    """
    try:
        r = await jb.revisar(
            db,
            jid,
            (payload.get("acao") or "").strip(),
            str(current_user.id),
            payload.get("motivo"),
        )
    except ValueError as e:
        # justificativa inexistente é 404; motivo faltando é 422 — mensagens diferentes, códigos
        # diferentes, para o front não dizer "não encontrada" quando o que falta é o motivo.
        texto = str(e)
        raise HTTPException(status_code=404 if "encontrada" in texto else 422, detail=texto) from None

    ef = r["efeito"]
    if ef["abonado"]:
        msg = (
            f"Deferida. O dia {r['dia'][8:10]}/{r['dia'][5:7]} entrou como abono na conferência "
            f"{ef['competencia'][5:7]}/{ef['competencia'][:4]}: {ef['pessoas_passivo']} pessoa(s) com "
            f"passivo a devolver, {brl(ef['passivo'])} no total estimado. Nenhum holerite foi tocado."
        )
    else:
        msg = "Indeferida, com o motivo registrado. Nenhum holerite foi tocado."
    return {"ok": True, "message": msg, "result": r}
