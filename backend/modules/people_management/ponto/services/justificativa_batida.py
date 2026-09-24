"""O ciclo da justificativa e a batida que falta — DGX Y3 (24/09/2026).

## Por que existe

A frente X2 (`DGX_X2_atraso_falta.md`) mediu duas coisas e não fechou nenhuma das duas:

1. **13 justificativas na base, 13 pendentes, 0 aprovadas**, a mais antiga parada desde
   21/07/2026. Existe rota de aprovar (`PUT /ponto/justificativa/{id}/revisar`) e existe tela
   («Revisar justificativas») — o que não existe é a **fila**: quem está esperando há quanto
   tempo, por qual dia, com qual anexo. E recusar não exige motivo.
2. **64 % do «atraso» de 09/2026 (20.445 min nas duas competências) é batida de ENTRADA
   faltando**, não atraso: gente que trabalhou e só bateu na saída. A X2 já separou esses
   minutos numa coluna própria; ninguém nunca viu a lista com nome e dia.

## O que este módulo NÃO faz

**Não muda um centavo.** Aprovar uma justificativa aqui chama o MESMO serviço de sempre
(`PunchService.revisar_justificativa` — o estado da justificativa é dele, não nosso) e depois
**reapura a conferência da X2** (`ponto_folha_conferencia`), onde o dia aprovado vira abono e a
linha da pessoa passa a `sentido='passivo'` se aquele dia já tiver sido descontado na folha.
É uma **proposta de devolução**, escrita numa tabela de conferência de onde ninguém paga.
`hr_payslips` não é tocado — o oráculo prova Σ|Δ| = R$ 0,00.

## A régua da batida faltando

Reusada, não recriada: `mapa_de_ponto._carregar` traz o turno esperado (com a coorte de quem é
cobrado no dia), a janela de presença e as batidas; `punch_type` diz qual batida é qual.
Pendência = **turno já encerrado** + **alguém bateu** (ou houve check-in manual) + falta
`entrada` ou falta `saida`. Turno sem batida nenhuma não entra: isso é falta/descoberto, e já
tem tela.

### Três correções que o oráculo obrigou (24/09/2026), e os números que elas valem

1. **A janela de presença não serve para procurar a SAÍDA.** Ela termina no fim planejado — é
   feita para decidir quem chegou — e a saída vem depois dele: 16:02 num turno que acaba 16:00.
   Procurar a saída ali acusava **706 turnos certos de 737**. A cauda é a mesma `JANELA_PRE_TURNO`
   (2 h) que a casa já usa antes do turno, agora simétrica.
2. **Batida que existe FORA do turno previsto não é batida faltando** — é escala lançada errada.
   MAURICIO tem turno 07:00–19:00 e trabalha 19:00–07:00; cobrar dele 17 saídas que ele bateu
   seria cobrar o erro de quem lançou a escala. Vai para um balde próprio, fora do total.
3. **Check-in manual do supervisor não é batida de entrada.** EDIWILSON tem check-in manual às
   19:02 num turno 07:00–19:00, e a X2 lê isso como 722 min de «atraso» e descarta o dia. Se o
   check-in valesse como entrada aqui, esta tela diria «completo» exatamente no dia que a X2
   tira do dinheiro.

### Duas afirmações honestas que a tela faz, e o oráculo prova

* **Entrada faltando não entra na conta de atraso.** A X2 marca o turno como `entrada_ausente`
  quando o «atraso» alcança 50 % da jornada — que é o que acontece quando a primeira batida da
  janela é a de saída. Aquele minuto sai do dinheiro.
* **Nenhum dos dois vira falta automática.** `espelho_service` só conta falta em «dia de escala
  sem **nenhuma** batida» (L660-673). Dia com batida — ainda que só uma — nunca entra em
  `time_sheets.unjustified_absent_days`, que é de onde o motor de folha desconta 1051/1053.

O contrário **não** vale, e o oráculo conta em vez de travar: a X2 descarta pelo TEMPO, então ela
também tira do dinheiro o dia em que a batida de entrada existe mas foi lançada horas depois
(JEOVANE, 20/09: turno 06:00–18:00, batida `entrada` às 17:25). Não é batida faltando e não entra
nesta tela; também não é atraso de verdade e por isso a X2 acerta em descartar.

Saída faltando é outra história e a tela diz isso: com a entrada registrada, o atraso do dia é
medido do jeito certo e conta. O que falta ali é a hora de saída, que é jornada — problema de
espelho, não de atraso.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from sqlalchemy import text

#: Prazo (em dias) depois do qual uma justificativa parada vira alerta. Parâmetro, não constante:
#: lido por `core.parametros.param`, semeado com 5, editável na tela de parâmetros (F4).
PARAM_PRAZO = "ponto.justificativa_prazo_dias"
PRAZO_PADRAO = 5

_SEED_PRAZO = text(
    "INSERT INTO system_configs (id, chave, nome, valor, valor_padrao, tipo, valor_type, grupo, "
    " descricao, metadata, is_editavel, scope) VALUES (gen_random_uuid(), :chave, "
    " 'Ponto: prazo para revisar justificativa (dias)', :v, :v, CAST('integer' AS setting_type), "
    " 'integer', 'ponto', 'Dias corridos que uma justificativa de ponto pode ficar pendente antes "
    "de virar alerta no painel do sistema.', CAST(:meta AS jsonb), true, 'global') "
    "ON CONFLICT (chave) DO NOTHING"
)


async def _ensure(db) -> None:
    """Semeia o parâmetro de prazo. Idempotente (`ON CONFLICT DO NOTHING`); nenhuma tabela nova —
    a fila lê `gp_justifications` e a pendência de batida é derivada do mapa de ponto na hora."""
    await db.execute(
        text("ALTER TABLE system_configs ADD COLUMN IF NOT EXISTS valor_por_empresa jsonb NOT NULL DEFAULT '{}'::jsonb")
    )
    await db.execute(
        _SEED_PRAZO,
        {"chave": PARAM_PRAZO, "v": str(PRAZO_PADRAO), "meta": json.dumps({"frente": "dgx-y3"})},
    )
    await db.commit()


async def prazo_dias(db) -> int:
    from core.parametros import param

    try:
        return int(await param(db, PARAM_PRAZO, default=PRAZO_PADRAO) or PRAZO_PADRAO)
    except (TypeError, ValueError):
        return PRAZO_PADRAO


# ── A. a fila da justificativa ────────────────────────────────────────────────────────────────

#: A fila. O «dia justificado» não tem campo próprio em `gp_justifications` (medido em 24/09:
#: a tabela guarda `punch_id` e `created_at`, nunca a data do dia) — é o dia da batida ligada e,
#: sem ela, o da criação. A tela marca qual dos dois foi, como a X2 faz.
SQL_FILA = """
SELECT j.justification_id, j.employee_id, coalesce(e.nome, '?') AS nome,
       coalesce(e.posto_atual_nome, '—') AS posto,
       j.justification_type, coalesce(j.category, '') AS category, coalesce(j.reason, '') AS reason,
       lower(coalesce(j.status, '')) AS status, j.created_at, coalesce(j.source, '') AS source,
       coalesce(cp.punch_timestamp::date, j.created_at::date) AS dia,
       (cp.punch_timestamp IS NULL) AS dia_por_criacao,
       coalesce(jsonb_array_length(j.attachments), 0) AS anexos,
       (CAST((now() AT TIME ZONE 'America/Manaus') AS date) - j.created_at::date) AS dias_parada
  FROM gp_justifications j
  LEFT JOIN gp_clock_punches cp ON cp.punch_id = j.punch_id
  LEFT JOIN employees e ON e.id::text = j.employee_id
 WHERE lower(coalesce(j.status, '')) IN ('pendente', 'pending', 'em_analise')
 ORDER BY j.created_at
"""

#: O que a folha já descontou de falta na competência do dia justificado — é o que transforma
#: «aprovada» em «passivo a devolver». Mesma fonte da X2 (rubricas 1051/1053 do holerite próprio).
SQL_DESCONTOU = """
SELECT round(sum((d->>'valor')::numeric), 2) AS valor
  FROM hr_payslips p CROSS JOIN LATERAL jsonb_array_elements(p.deductions) d
 WHERE p.source_system = 'conecta' AND p.payslip_code NOT LIKE '13O-%'
   AND p.employee_id::text = :eid AND p.reference_year = :a AND p.reference_month = :m
   AND d->>'codigo' IN ('1051', '1053')
"""


async def fila(db) -> list[dict]:
    """As justificativas pendentes, com dias parados e o que a folha descontou naquele mês."""
    linhas = [dict(r) for r in (await db.execute(text(SQL_FILA))).mappings().all()]
    for ln in linhas:
        dia: date = ln["dia"]
        v = (await db.execute(text(SQL_DESCONTOU), {"eid": ln["employee_id"], "a": dia.year, "m": dia.month})).scalar()
        ln["folha_desconto_mes"] = float(v or 0)
    return linhas


async def revisar(db, justification_id: str, acao: str, reviewer_id: str, motivo: str | None) -> dict:
    """Defere ou indefere — **pelo serviço que já existe** — e propõe o efeito na folha.

    `PunchService.revisar_justificativa` é quem muda o estado da justificativa (a mesma função
    que a rota `PUT /ponto/justificativa/{id}/revisar` chama; não há um segundo escritor). O que
    esta função acrescenta é o que faltava no ciclo:

      · **recusar exige motivo** (≥ 5 caracteres) — indeferir sem dizer por quê é uma resposta
        que o colaborador não consegue contestar;
      · **aprovar reapura a conferência da X2** na competência do dia justificado: o dia entra
        como abono e a linha vira `sentido='passivo'` se aquele mês já teve desconto de falta.
        É PROPOSTA — `hr_payslips` não é tocado.
    """
    acao = (acao or "").strip().lower()
    if acao not in ("aprovar", "rejeitar"):
        raise ValueError("Ação deve ser 'aprovar' ou 'rejeitar'.")
    motivo = (motivo or "").strip()
    if acao == "rejeitar" and len(motivo) < 5:
        raise ValueError("Recusar exige motivo (ao menos 5 caracteres) — é a resposta que o colaborador vai ler.")

    from modules.people_management.ponto.services.punch_service import PunchService

    r = await PunchService(db).revisar_justificativa(justification_id, acao, reviewer_id, motivo or None)
    await db.commit()

    dia = (
        await db.execute(
            text(
                "SELECT coalesce(cp.punch_timestamp::date, j.created_at::date) FROM gp_justifications j "
                "LEFT JOIN gp_clock_punches cp ON cp.punch_id = j.punch_id "
                "WHERE j.justification_id = :jid"
            ),
            {"jid": justification_id},
        )
    ).scalar()

    efeito = {"competencia": None, "abonado": False, "passivo": 0.0, "pessoas_passivo": 0}
    if acao == "aprovar" and dia:
        from modules.people_management.folha.services.atraso_falta_conferencia import apurar

        comp = f"{dia.year:04d}-{dia.month:02d}"
        res = await apurar(db, comp)
        efeito = {
            "competencia": comp,
            "abonado": True,
            "passivo": float(res["passivo"]["valor"]),
            "pessoas_passivo": int(res["passivo"]["pessoas"]),
        }
    return {"justificativa": r, "dia": dia.isoformat() if dia else None, "efeito": efeito}


# ── B. a batida que falta ─────────────────────────────────────────────────────────────────────

#: Janela padrão das telas e do caçador. Um turno só é pendência depois de acabar: turno em curso
#: sem saída ainda não é batida faltando.
JANELA_DIAS_PADRAO = 60

#: Meia-volta em torno do turno previsto: se a batida que «falta» existe AQUI e não na janela do
#: turno, o problema é a escala lançada, não a batida. Calibragem, não lei.
VOLTA_DO_TURNO = timedelta(hours=12)


async def batidas_faltando(db, de: date, ate: date, agora: datetime | None = None) -> list[dict]:
    """Turnos encerrados em que a pessoa trabalhou e falta a batida de entrada e/ou de saída.

    Régua importada do mapa de ponto (frente 04): o mesmo `_carregar` (turno esperado, coorte,
    janela de presença, batidas) e o mesmo `classificar` — a coluna «o que o mapa conclui hoje»
    é literalmente o estado que o mapa pinta, sem segunda opinião.
    """
    from modules.operacional.presence.controllers.presence_controller import (
        JANELA_PRE_TURNO,
        _janela_presenca,
        _janela_turno,
    )
    from modules.people_management.ponto import mapa_de_ponto as mp

    turnos, batidas, _geo, tol, regras = await mp._carregar(db, de, ate)
    agora = agora or mp.agora_manaus()
    out: list[dict] = []
    for t in turnos:
        dia, ini, fim = t["shift_date"], t["planned_start_time"], t["planned_end_time"]
        dt_ini, dt_fim = _janela_turno(dia, ini, fim)
        if agora < dt_fim + JANELA_PRE_TURNO:
            continue  # turno em curso (ou recém-encerrado) — ainda dá tempo de bater a saída
        j_ini, j_fim = _janela_presenca(dia, ini, fim)
        # A janela de PRESENÇA termina no fim planejado (é feita para decidir quem chegou), e a
        # saída vem DEPOIS dele: às 16:02 de um turno que acaba 16:00. Usar a janela de presença
        # para procurar a saída acusava 706 turnos certos de 737 — medido em 24/09. A cauda é a
        # MESMA `JANELA_PRE_TURNO` (2 h) que a casa já usa antes do turno, agora simétrica.
        f_saida = max(j_fim, dt_fim + JANELA_PRE_TURNO)
        todas = batidas.get(t["employee_id"], [])
        na_janela = [b for b in todas if j_ini <= b["punch_timestamp"] <= f_saida]
        manual = t.get("actual_start_time")
        if not na_janela and manual is None:
            continue  # ninguém bateu nada: é falta/descoberto, e isso tem tela própria
        # O check-in MANUAL do supervisor (`shifts.actual_start_time`) prova que a pessoa estava
        # lá; NÃO é a batida de entrada. Medido em 24/09: EDIWILSON tem check-in manual às 19:02
        # num turno 07:00–19:00 — a conferência da X2 lê isso como 722 min de «atraso» e descarta
        # o dia como `entrada_ausente`. Se o check-in valesse como entrada aqui, esta tela diria
        # «batida completa» exatamente no dia que a X2 tira do dinheiro. As duas réguas têm de
        # dizer a mesma coisa. Ele mantém a linha em cena (houve trabalho) e aparece na coluna.
        tipos_entrada = {(b.get("punch_type") or "").lower() for b in todas if j_ini <= b["punch_timestamp"] <= j_fim}
        tipos_saida = {(b.get("punch_type") or "").lower() for b in na_janela}
        tem_entrada = "entrada" in tipos_entrada
        tem_saida = "saida" in tipos_saida
        if tem_entrada and tem_saida:
            continue
        # A batida existe, mas FORA do turno previsto? Então não falta batida — falta acertar a
        # escala. Medido em 24/09: MAURICIO ALVES CHAGAS tem turno lançado 07:00–19:00 e trabalha
        # 19:00–07:00; a entrada dele às 18:44 cai na janela e vira «11 h de atraso», e a saída
        # das 06:50 do dia seguinte fica de fora. Cobrar dele 18 saídas que ele bateu seria
        # cobrar o erro de quem lançou a escala. Vai para um balde próprio, fora do total.
        fora = {
            (b.get("punch_type") or "").lower()
            for b in todas
            if dt_ini - VOLTA_DO_TURNO <= b["punch_timestamp"] <= dt_fim + VOLTA_DO_TURNO
            and not (j_ini <= b["punch_timestamp"] <= f_saida)
        }
        escala_divergente = (not tem_entrada and "entrada" in fora) or (not tem_saida and "saida" in fora)
        falta = "entrada e saída" if not tem_entrada and not tem_saida else ("entrada" if not tem_entrada else "saída")
        tol_min = mp._tolerancia(tol, t, regras)
        estado, _bat = mp.classificar(t, todas, tol_min, agora)
        out.append(
            {
                "employee_id": t["employee_id"],
                "nome": t["nome"],
                "dia": dia.isoformat(),
                "posto": t["posto"],
                "cliente": t["cliente"],
                "turno": f"{ini:%H:%M}–{fim:%H:%M}",
                "falta": falta,
                "tem_entrada": tem_entrada,
                "tem_saida": tem_saida,
                "batidas": [
                    f"{(b.get('punch_type') or '?')} {b['punch_timestamp']:%H:%M}"
                    for b in sorted(na_janela, key=lambda x: x["punch_timestamp"])
                ],
                "n_batidas": len(na_janela),
                "estado_mapa": estado or "aguardando",
                "tolerancia_min": tol_min,
                "checkin_manual": manual is not None,
                "escala_divergente": escala_divergente,
            }
        )
    out.sort(key=lambda x: (x["dia"], x["nome"]), reverse=True)
    return out


async def resumo_batidas(db, dias: int = JANELA_DIAS_PADRAO, hoje: date | None = None) -> dict:
    """A lista da janela + o agregado por pessoa, que é como o supervisor cobra."""
    ate = hoje or date.today()
    de = ate - timedelta(days=dias)
    todas = await batidas_faltando(db, de, ate)
    linhas = [x for x in todas if not x["escala_divergente"]]
    escala = [x for x in todas if x["escala_divergente"]]
    por_pessoa: dict[str, dict] = {}
    for ln in linhas:
        p = por_pessoa.setdefault(ln["nome"], {"entrada": 0, "saida": 0, "ambas": 0, "dias": 0})
        p["dias"] += 1
        chave = "ambas" if ln["falta"].startswith("entrada e") else ("entrada" if not ln["tem_entrada"] else "saida")
        p[chave] += 1
    por_escala: dict[str, int] = {}
    for ln in escala:
        por_escala[ln["nome"]] = por_escala.get(ln["nome"], 0) + 1
    return {
        "de": de.isoformat(),
        "ate": ate.isoformat(),
        "linhas": linhas,
        "por_pessoa": por_pessoa,
        "escala_divergente": escala,
        "escala_por_pessoa": por_escala,
    }
