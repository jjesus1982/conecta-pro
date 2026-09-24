"""DGX Y5 — o que o COLABORADOR vê (24/09/2026). Prefixo `_` = o discovery pula.

`portal_do_funcionario.build` chama `telas(db, out, me)` no fim, depois dos lotes 3/4/5.
Não há `router` aqui: as rotas novas moram no lugar certo do portal
(`employee_portal/controllers/self_service_controller.py`, escopadas por `_employee_id`),
e esta frente só PENDURA os botões nas telas que já existem — nenhum arquivo de `frontend/`
muda, porque o shell do redesign já sabe renderizar `docs` (DocButtons → fetch com Bearer →
download) e `type: table`.

O que liga, e de onde veio:
- Meu crachá (F6/T1) — botão na tela `dados-pessoais`.
- Recibo e aviso de férias (U2) — botões POR LINHA na tela `ferias`, só nas aprovadas.
- Meu espelho de ponto — botões do mês corrente e do anterior na tela `ponto`.
- Comprovante do pagamento — o `pix_e2e_id` já vinha no JSON; aqui ele vira COLUNA visível,
  que é como a pessoa confere a entrada no extrato dela.
- Minhas justificativas (gp_justifications) — tela nova; ele escrevia e nunca mais via.
- Como o benefício é concedido (`beneficio_tipos`, F3) — coluna nova em `beneficios`.

O que NÃO entra, de propósito: `folha_beneficio_conferencia`, `ponto_folha_conferencia` e
`banco_horas_conferencia`. São a nossa apuração paralela; o colaborador vê o que RECEBEU.
"""

from __future__ import annotations

import logging
from datetime import date as _date

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, doc, t

_log = logging.getLogger(__name__)
_ND = "#0F1B3A"
_SS = "/api/v1/people-management/portal/self-service"

# abas novas; as outras telas desta frente são colunas/botões em telas que já existem.
# `meus-pagamentos` existia só como rota JSON (o Jordan mandou 46 pessoas para um menu que
# não havia em 22/09) — tela sem porta não existe.
EXTRA_MENU: list[dict] = [
    {"id": "meus-pagamentos", "label": "Meus pagamentos", "icon": "M3 3v18h18"},
    {"id": "minhas-justificativas", "label": "Minhas justificativas", "icon": "M3 3v18h18"},
]

_JUST = {
    "pendente": ("Em análise pelo DP", "warn"),
    "aprovada": ("Aprovada", "ok"),
    "rejeitada": ("Não aceita", "bad"),
}
_FER = {
    "submitted": ("Pedida", "warn"),
    "approved": ("Aprovada", "ok"),
    "rejected": ("Rejeitada", "bad"),
    "cancelled": ("Cancelada", "mut"),
    "canceled": ("Cancelada", "mut"),
}


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:  # noqa: BLE001
        return "—"


def _mes_anterior(hoje: _date) -> tuple[int, int]:
    return (12, hoje.year - 1) if hoje.month == 1 else (hoje.month - 1, hoje.year)


async def telas(db, out: dict, me=None) -> None:
    """Pendura os documentos e as duas visões que faltavam. Cada bloco é independente."""
    _, _safe, tbl = _helpers(db)
    if not me:
        return  # sem vínculo o builder base já deixou as telas vazias com aviso
    me_lit = f"'{me}'"
    hoje = _date.today()

    # ---- crachá: botão na ficha pessoal ------------------------------------ #
    try:
        if isinstance(out.get("dados-pessoais"), dict):
            out["dados-pessoais"]["docs"] = [doc("Meu crachá", f"{_SS}/meu-cracha/pdf", fmt="pdf")]
    except Exception as exc:  # noqa: BLE001
        _log.warning("y5 crachá: %s", exc)

    # ---- espelho de ponto: mês corrente e anterior -------------------------- #
    try:
        if isinstance(out.get("ponto"), dict):
            mant, aant = _mes_anterior(hoje)
            out["ponto"]["docs"] = [
                doc(f"Espelho {hoje.month:02d}/{hoje.year}", f"{_SS}/meu-espelho/{hoje.month}/{hoje.year}/pdf"),
                doc(f"Espelho {mant:02d}/{aant}", f"{_SS}/meu-espelho/{mant}/{aant}/pdf"),
            ]
    except Exception as exc:  # noqa: BLE001
        _log.warning("y5 espelho: %s", exc)

    # ---- férias: recibo e aviso POR LINHA, só nas aprovadas ----------------- #
    try:
        out["ferias"] = await tbl(
            "Minhas férias",
            "Minhas solicitações — o aviso a assinar aparece em «Assinaturas pendentes»",
            "—",
            ["Início", "Fim", "Dias", "Status"],
            "1fr 1fr 0.7fr 0.9fr",
            f"SELECT v.id::text, v.start_date, v.end_date, v.days_requested, coalesce(v.status::text,'—') "
            f"FROM hr_vacation_requests v WHERE v.employee_id={me_lit} "
            f"ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(_d(r[1])),
                t(_d(r[2])),
                t(str(r[3] or "—")),
                b(*_FER.get((r[4] or "").lower(), ((r[4] or "—").capitalize(), "info"))),
            ],
            docsfn=lambda r: (
                [
                    doc("Recibo", f"{_SS}/minhas-ferias/{r[0]}/recibo/pdf"),
                    doc("Aviso", f"{_SS}/minhas-ferias/{r[0]}/aviso/pdf"),
                ]
                if (r[4] or "").upper() == "APPROVED"
                else []
            ),
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("y5 ferias: %s", exc)

    # ---- pagamentos: o comprovante que a pessoa confere no extrato dela ----- #
    try:
        out["meus-pagamentos"] = await tbl(
            "Meus pagamentos",
            "Adiantamento e saldo da folha · o comprovante é o que você procura no seu extrato",
            "—",
            ["Competência", "Parcela", "Valor", "Pago em", "Comprovante"],
            "1fr 1.2fr 1fr 1fr 1.8fr",
            f"SELECT lpad(p.mes::text,2,'0') || '/' || p.ano, p.parcela, p.valor_liquido, p.data_pagamento, "
            f"       coalesce(p.pix_e2e_id,''), coalesce(p.status,'pendente_pagamento') "
            f"FROM payroll_payments p WHERE p.employee_id={me_lit} "
            f"ORDER BY p.ano DESC, p.mes DESC, p.parcela LIMIT 60",
            lambda r: [
                t(r[0], 600, _ND),
                t({1: "Adiantamento (40%)", 2: "Saldo (60%)"}.get(r[1], f"Parcela {r[1]}")),
                t(brl(r[2]) if r[2] is not None else "—"),
                t(_d(r[3])),
                (t(r[4]) if r[4] else b("sem comprovante", "warn")),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("y5 pagamentos: %s", exc)

    # ---- benefícios: por qual REGRA cada um é concedido (F3) ---------------- #
    try:
        out["beneficios"] = await tbl(
            "Benefícios",
            f"O que você recebe e por qual regra · competência {hoje.month:02d}/{hoje.year} · "
            "o valor efetivamente descontado no mês sai no seu holerite",
            "—",
            ["Benefício", "Operadora", "Desconto (cadastro)", "Como é concedido"],
            "1.1fr 1fr 1fr 2.2fr",
            f"SELECT coalesce(x.type::text,'—'), coalesce(x.provider,'—'), x.employee_contribution, "
            f"       bt.tipo_desconto, bt.coeficiente_desconto, coalesce(x.status::text,'—') "
            f"FROM employee_benefits x LEFT JOIN beneficio_tipos bt ON bt.id = x.beneficio_tipo_id "
            f"WHERE x.employee_id={me_lit} AND x.status = 'active' "
            f"ORDER BY x.type LIMIT 60",
            lambda r: [
                t((r[0] or "—").replace("_", " "), 600, _ND),
                t(r[1]),
                t(brl(r[2]) if r[2] is not None else "—"),
                t(_regra(r[3], r[4])),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("y5 beneficios: %s", exc)

    # ---- justificativas: o que ele escreveu e em que pé está ---------------- #
    try:
        out["minhas-justificativas"] = await tbl(
            "Minhas justificativas",
            "Faltas e atrasos que você justificou — e a decisão do DP",
            "—",
            ["Enviada em", "Tipo", "Motivo", "Situação", "Decidida em"],
            "1fr 0.8fr 2.2fr 1.2fr 1fr",
            f"SELECT j.created_at, j.justification_type, coalesce(j.reason,'—'), "
            f"       lower(coalesce(j.status,'pendente')), j.reviewed_at "
            f"FROM gp_justifications j WHERE j.employee_id = {me_lit} "
            f"ORDER BY j.created_at DESC LIMIT 200",
            lambda r: [
                t(_d(r[0])),
                t("Atraso" if (r[1] or "") == "atraso" else "Falta"),
                t((r[2] or "—")[:120]),
                b(*_JUST.get(r[3], ((r[3] or "—").capitalize(), "info"))),
                t(_d(r[4])),
            ],
        )
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _log.warning("y5 justificativas: %s", exc)


def _regra(tipo_desconto, coef) -> str:
    """A frase da regra — a MESMA do portal (`self_service_controller._frase_regra`)."""
    from modules.people_management.employee_portal.controllers.self_service_controller import _frase_regra

    return _frase_regra(tipo_desconto, coef)
