"""DGX F1 — Evento/rubrica como DADO (24/09/2026). `rubricas_folha` ganha os atributos do DGX
(período, tipo de dia, crédito, soma ao evento/ponto, banco de horas, desconta benefício, exportação,
DSR/13º/média, base, razão, vale, ausência…) e a aba Rubricas vira cadastro de verdade: listar,
editar, inativar, incluir. O MOTOR (`calculo_service.py`) NÃO muda — é paralelo cego. Quem prova que o
cadastro diz a verdade sobre o motor é `scripts/orq/test_oraculo_rubricas_dizem_a_verdade.py`.

Achado que motivou a semente (sandbox 09/2026, 51 holerites): o motor emitia 8 códigos sem linha na
tabela (0016/0018/0031/0095/0937/1045/1051/1053) e a tabela tinha 5 códigos com OUTRO significado
no holerite (0040 ronda × HE 50%; 0060 VR × Férias; 0061 VT × 1/3 Férias; 0050/0051 insal./peric. ×
afastamento no espelho). Não renomeei nada do que já existia (dado que não criei): a tela mostra a
descrição do holerite ao lado quando diverge, e o `origem_regra` registra a colisão. Decisão do dono.

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` (topo) e chama
`telas(db, out)` ANTES de `montar_grupos` (as abas estão em `_dp_grupos.GRUPOS`, g-folha).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller: ele descobre os builders, o DP importa `router` daqui, e o
#: módulo ainda está pela metade — com o router já definido o ciclo fecha sem erro.
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t  # noqa: E402

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"

# ── enums do DGX (doc 01 §Eventos), em PT-BR snake_case ─────────────────────────────────────
PERIODO = ("dias", "horas", "mes")
TIPO_DIA = ("dia_normal", "falta_justificada", "falta_nao_justificada", "folga", "credito", "atividade_externa")
SOMA_AO_EVENTO = (
    "nao",
    "hora_trabalhada",
    "hora_extra",
    "hora_extra_100",
    "hora_noturna",
    "hora_noturna_reduzida",
    "atraso",
    "adicional_feriado",
    "intrajornada",
)
BANCO_HORAS = ("nao", "soma", "subtrai")
BASE = ("salario_base", "salario_minimo")
PCT_VALOR = ("porcentagem", "valor")
TIPO_BENEFICIO = (
    "",
    "vale_transporte",
    "vale_refeicao",
    "cesta_basica",
    "assistencia_medica",
    "assistencia_odontologica",
    "seguro_de_vida",
    "plr",
    "premio",
    "cartao_de_credito",
    "sesmt",
    "assistencia",
    "perfil_securitario",
)
NATUREZA = ("mensal", "variavel", "anual", "bimestral")

#: (coluna, tipo SQL). Sem DEFAULT de propósito: NULL = "ninguém disse" e o oráculo (c) acusa.
COLUNAS = [
    ("periodo", "text"),
    ("tipo_dia", "text"),
    ("credito", "text"),
    ("soma_ao_evento", "text"),
    ("soma_ao_ponto", "boolean"),
    ("banco_horas", "text"),
    ("desconta_beneficio", "boolean"),
    ("tipo_beneficio_descontado", "text"),
    ("exporta_evento", "boolean"),
    ("codigo_exportacao", "text"),
    ("incide_dsr", "boolean"),
    ("incide_13", "boolean"),
    ("media_13", "boolean"),
    ("base", "text"),
    ("razao", "numeric(12,4)"),
    ("razao_noturna", "numeric(12,4)"),
    ("vale", "boolean"),
    ("ausencia", "boolean"),
    ("hora_extra", "boolean"),
    ("considerar_descanso", "boolean"),
    ("remove_ponto_calculado", "boolean"),
    ("remove_diaria", "boolean"),
    ("comercial", "boolean"),
    ("porcentagem_ou_valor", "text"),
    ("origem_regra", "text"),
]
BOOLS = {c for c, ty in COLUNAS if ty == "boolean"}


def _ev(origem: str, **kw) -> dict:
    """Um evento com os defaults do DGX; `kw` sobrescreve. Toda semente cita a linha do motor/CCT."""
    return {
        "periodo": "mes",
        "tipo_dia": "dia_normal",
        "soma_ao_evento": "nao",
        "soma_ao_ponto": False,
        "banco_horas": "nao",
        "desconta_beneficio": False,
        "tipo_beneficio_descontado": "",
        "exporta_evento": True,
        "codigo_exportacao": "",
        "incide_dsr": False,
        "incide_13": False,
        "media_13": False,
        "base": "salario_base",
        "razao": Decimal("0"),
        "razao_noturna": Decimal("0"),
        "vale": False,
        "ausencia": False,
        "hora_extra": False,
        "considerar_descanso": False,
        "remove_ponto_calculado": False,
        "remove_diaria": False,
        "comercial": False,
        "porcentagem_ou_valor": "valor",
        "origem_regra": origem,
        **kw,
    }


_CS = "calculo_service.py"
#: Semente dos atributos DGX por código. `credito` é derivado do tipo no _ensure (provento=soma, desconto=subtrai).
#: Linhas L… referem-se a `folha/services/calculo_service.py` em 24/09/2026; "Portte NNN" = código na folha do contador.
SEED: dict[str, dict] = {
    # ── 24 existentes ──
    "0001": _ev(
        f"{_CS} L428 (0001 Salário Base; proporcional por admissão/desligamento L340-360; piso CCT L296-310). Portte 1/8781",
        periodo="dias",
        incide_13=True,
        razao=Decimal("1"),
        codigo_exportacao="1",
    ),
    "0010": _ev(
        "cadastro 03/2026 (HE 50%, CCT). ⚠ O motor emite HE 50% com o código 0040 (L605-622: excedente × hora_normal × 1,5); DSR sobre HE em 0090 (L751-770). Portte 249/150",
        periodo="horas",
        soma_ao_evento="hora_extra",
        hora_extra=True,
        incide_dsr=True,
        incide_13=True,
        media_13=True,
        razao=Decimal("1.5"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="249",
    ),
    "0011": _ev(
        "cadastro 03/2026 (HE 100%). O motor NÃO emite HE 100% — sem regra em calculo_service",
        periodo="horas",
        soma_ao_evento="hora_extra_100",
        hora_extra=True,
        incide_dsr=True,
        incide_13=True,
        media_13=True,
        razao=Decimal("2"),
        porcentagem_ou_valor="porcentagem",
    ),
    "0020": _ev(
        f"{_CS} L672-700: horas noturnas reduzidas × hora_normal × 0,20; horas pela ESCALA (7h/plantão, L149-152; decisão Jordan 04/08/2026). DSR NÃO reflete (L757-760, Portte 101/101). Portte 246",
        periodo="horas",
        soma_ao_evento="hora_noturna",
        incide_13=True,
        media_13=True,
        razao=Decimal("0.2"),
        razao_noturna=Decimal("0.2"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="246",
    ),
    "0021": _ev(
        f"{_CS} L702-722: 1h fictícia por plantão × hora_normal × (1+0,20+ronda)×1,5 (Portte 96/96). Portte 247",
        periodo="horas",
        soma_ao_evento="hora_noturna_reduzida",
        hora_extra=True,
        incide_13=True,
        media_13=True,
        razao=Decimal("1.8"),
        razao_noturna=Decimal("2.025"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="247",
    ),
    "0030": _ev(
        f"{_CS} L727-750 (0030 Intrajornada Diurno): plantões diurnos × hora_normal × (1+ronda) × 1,5; só employees.recebe_intrajornada (art. 71 §4º CLT). Portte 244",
        periodo="horas",
        soma_ao_evento="intrajornada",
        hora_extra=True,
        incide_13=True,
        media_13=True,
        razao=Decimal("1.5"),
        razao_noturna=Decimal("1.8"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="244",
    ),
    "0040": _ev(
        "cadastro 03/2026 (ronda 15%, CCT Cl. 23ª). ⚠ COLISÃO: o motor emite ronda como 0018 (L652-665) e usa 0040 para Horas Extras 50% (L605-622). Portte 224",
        incide_13=True,
        razao=Decimal("0.15"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="224",
    ),
    "0041": _ev(
        "cadastro 03/2026 (ronda 30%, regra pré-2020). O motor NÃO emite",
        incide_13=True,
        razao=Decimal("0.3"),
        porcentagem_ou_valor="porcentagem",
    ),
    "0050": _ev(
        "cadastro 03/2026 diz base salário mínimo; o motor calcula insalubridade sobre o SALÁRIO BASE (L636-649, código 0016; Portte 223 = 10% do salário base). ⚠ COLISÃO: espelho Portte usa 0050 = Afastamento Doença ≤15d",
        incide_13=True,
        razao=Decimal("0.1"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="223",
    ),
    "0051": _ev(
        f"{_CS} L622-635 (código 0015 no motor): employees.periculosidade_percentual × salário base. ⚠ COLISÃO: espelho Portte usa 0051 = Afastamento INSS",
        incide_13=True,
        razao=Decimal("0.3"),
        porcentagem_ou_valor="porcentagem",
    ),
    "0060": _ev(
        "cadastro 03/2026: VR R$ 22/dia (VR_DIA L97) — NÃO vai ao holerite, sai no Recibo de VT/VR (L772-773). ⚠ COLISÃO: o motor emite 0060 = Ferias (L458). Portte 9383 é o DESCONTO",
        periodo="dias",
        vale=True,
        razao=Decimal("22"),
        remove_diaria=True,
    ),
    "0061": _ev(
        "cadastro 03/2026: VT R$ 10/dia (VT_DIA L98) — NÃO vai ao holerite (L772-773). ⚠ COLISÃO: o motor emite 0061 = 1/3 Ferias (L472). Portte 48 é o DESCONTO",
        periodo="dias",
        vale=True,
        razao=Decimal("10"),
        remove_diaria=True,
    ),
    "0070": _ev(
        "cadastro 03/2026 (13º 1ª parcela). Folha mensal não emite — 13º tem fluxo próprio (payslip_code 13O-%). ⚠ COLISÃO: espelho Portte usa 0070 = Horas Extras",
        razao=Decimal("0.5"),
        porcentagem_ou_valor="porcentagem",
    ),
    "0071": _ev(
        "cadastro 03/2026 (13º 2ª parcela). Folha mensal não emite — fluxo próprio (13O-%). Portte 8550 só em rescisão",
        razao=Decimal("0.5"),
        porcentagem_ou_valor="porcentagem",
    ),
    "0080": _ev(
        "cadastro 03/2026 'salário + 1/3'. O motor emite férias como 0060 (dias, L458) + 0062 (vantagens, L463) + 0061 (1/3, L472), INSS próprio 1002 (L481) e adiantamento 0937 (L490) — art. 129/142/145 CLT. Portte 3/931",
        periodo="dias",
        tipo_dia="falta_justificada",
        ausencia=True,
        remove_ponto_calculado=True,
        remove_diaria=True,
        desconta_beneficio=True,
        tipo_beneficio_descontado="vale_transporte",
        incide_13=True,
        razao=Decimal("1"),
        codigo_exportacao="3",
    ),
    "0090": _ev(
        f"{_CS} L751-770: HE × fator_dsr (1/6 no 12x36, L189-215; comercial = domingos/dias úteis). Base = SÓ hora extra (Portte 101/101). Portte 250",
        periodo="dias",
        incide_13=True,
        media_13=True,
        razao=Decimal("0.1667"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="250",
    ),
    "0100": _ev(
        "cadastro 03/2026. O motor NÃO emite provento de taxa negocial (só o desconto 1030, L908-918)",
        razao=Decimal("22"),
    ),
    "1001": _ev(
        f"{_CS} L806-826: calcular_inss(base) — base = salário + peric + insal + ronda + intrajornada + HE + noturno + hora reduzida + DSR (+ verbas do espelho com incide_inss). clt_calculator, Portaria MPS/MF 13/2026. Portte 998",
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="998",
    ),
    "1002": _ev(
        f"{_CS} L828-850: calcular_irrf(base INSS − INSS retido, dependentes) — Lei 15.270/2025. ⚠ COLISÃO interna: o motor também emite 1002 = INSS Ferias (L478-486). Portte: não observado em 2026",
        porcentagem_ou_valor="porcentagem",
    ),
    "1010": _ev(
        f"{_CS} L852-862: salário base × 4% (DESC_VT_PCT L99, CCT 2026). Portte 48",
        desconta_beneficio=True,
        tipo_beneficio_descontado="vale_transporte",
        razao=Decimal("0.04"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="48",
    ),
    "1011": _ev(
        f"{_CS} L864-874: salário base × 1% (DESC_VR_PCT L100, CCT 2026). Portte 9383",
        desconta_beneficio=True,
        tipo_beneficio_descontado="vale_refeicao",
        razao=Decimal("0.01"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="9383",
    ),
    "1020": _ev(
        f"{_CS} L876-904: R$ 8,50 titular / R$ 17,00 com dependente (Pyetra 09/09/2026, Servdonto); só quem está no plano. Cadastro dizia 'até R$ 9,00' (sem fonte). Portte 202/254",
        desconta_beneficio=True,
        tipo_beneficio_descontado="assistencia_odontologica",
        razao=Decimal("8.5"),
        codigo_exportacao="202",
    ),
    "1021": _ev(
        "cadastro 03/2026. REMOVIDO do motor (L905-906): sem apólice/valor confirmado pelo DP",
        desconta_beneficio=True,
        tipo_beneficio_descontado="seguro_de_vida",
        razao=Decimal("2"),
    ),
    "1030": _ev(
        f"{_CS} L908-918: R$ 22 nos meses 1/3/5/7/9/11 (TAXA_NEGOCIAL L103-104, CCT SINDECOMPRESTS). Portte 264",
        razao=Decimal("22"),
        codigo_exportacao="264",
    ),
    # ── emitidas pelo motor sem linha na tabela (inseridas por _ensure) ──
    "0015": _ev(
        f"{_CS} L622-635: employees.periculosidade_percentual × salário base (art. 193 CLT). Portte: não observado em 2026",
        incide_13=True,
        razao=Decimal("0.3"),
        porcentagem_ou_valor="porcentagem",
    ),
    "0016": _ev(
        f"{_CS} L636-649: employees.insalubridade_percentual × salário base (NR-15; praticado 10%, folha analítica L7). Portte 223",
        incide_13=True,
        razao=Decimal("0.1"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="223",
    ),
    "0018": _ev(
        f"{_CS} L652-665: employees.adicional_ronda_percentual × salário base (CCT Cl. 23ª, 15%). Portte 224",
        incide_13=True,
        razao=Decimal("0.15"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="224",
    ),
    "0031": _ev(
        f"{_CS} L727-750 (0031 Intrajornada Noturna): plantões noturnos × hora_normal × (1+0,20+ronda) × 1,5; só recebe_intrajornada. Portte 245",
        periodo="horas",
        soma_ao_evento="intrajornada",
        hora_extra=True,
        incide_13=True,
        media_13=True,
        razao=Decimal("1.8"),
        razao_noturna=Decimal("2.025"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="245",
    ),
    "0062": _ev(
        f"{_CS} L448-470: adicionais habituais (peric+insal+ronda) × dias de férias / 30; INSS à parte na 1002 INSS Ferias — não entra em base_inss (L446)",
        periodo="dias",
        razao=Decimal("1"),
    ),
    "0095": _ev(
        f"{_CS} L777-800: R$ 67,54 por filho < 14 (SALARIO_FAMILIA_QUOTA L114; teto R$ 1.819,26 L115; Lei 8.213 art. 66). NÃO incide INSS/IRRF/FGTS. Portte 995",
        razao=Decimal("67.54"),
        codigo_exportacao="995",
    ),
    "0937": _ev(
        f"{_CS} L488-496: (férias + vantagens + 1/3) − INSS férias, pago antes do gozo (art. 145 CLT). Portte 937",
        periodo="dias",
        vale=True,
        razao=Decimal("1"),
        codigo_exportacao="937",
    ),
    "1040": _ev(
        f"{_CS} L920-950: employee_deductions ativos na competência (consignado sobre total de proventos; pensão sobre salário base). Portte 269/271/273/275/9750",
        codigo_exportacao="269",
    ),
    "1045": _ev(
        f"{_CS} L952-1000: 40% do salário base CHEIO (ADIANTAMENTO_PERCENTUAL L112; regra do Jordan 22/09/2026) ou o PIX real de adiantamento (inter_payments dias 14-26). Portte 981",
        vale=True,
        razao=Decimal("0.4"),
        porcentagem_ou_valor="porcentagem",
        codigo_exportacao="981",
    ),
    "1051": _ev(
        f"{_CS} L531-602: time_sheets.unjustified_absent_days × salário/30, só com ≥ 80% de batidas próprias (L580-586). ⚠ NÃO reduz a base INSS no caminho going-forward (L806-817) — reduz só no caminho do espelho (L524-525). Portte 8792",
        periodo="dias",
        tipo_dia="falta_nao_justificada",
        ausencia=True,
        remove_ponto_calculado=True,
        remove_diaria=True,
        desconta_beneficio=True,
        tipo_beneficio_descontado="vale_transporte",
        incide_dsr=True,
        razao=Decimal("1"),
        codigo_exportacao="8792",
    ),
    "1053": _ev(
        f"{_CS} L590-602: time_sheets.dsr_lost_days × salário/30 (art. 6º Lei 605/49). ⚠ idem 1051: não reduz base INSS going-forward. Portte 8794",
        periodo="dias",
        tipo_dia="falta_nao_justificada",
        ausencia=True,
        razao=Decimal("1"),
        codigo_exportacao="8794",
    ),
}

#: Linhas que o motor emite e a tabela não tinha: (codigo, descricao, tipo, natureza, base_calculo, percentual, valor_fixo, inss, irrf, fgts)
NOVAS = [
    (
        "0015",
        "Adicional de Periculosidade",
        "provento",
        "mensal",
        "salario_base * periculosidade_percentual",
        30,
        None,
        True,
        True,
        True,
    ),
    (
        "0016",
        "Adicional de Insalubridade",
        "provento",
        "mensal",
        "salario_base * insalubridade_percentual",
        10,
        None,
        True,
        True,
        True,
    ),
    (
        "0018",
        "Adicional de Ronda",
        "provento",
        "mensal",
        "salario_base * 15% (CCT Cl. 23ª)",
        15,
        None,
        True,
        True,
        True,
    ),
    (
        "0031",
        "Intrajornada Noturna",
        "provento",
        "variavel",
        "plantoes_noturnos * hora_normal * (1+0,20+ronda) * 1,5",
        50,
        None,
        True,
        True,
        True,
    ),
    (
        "0062",
        "Vantagens Ferias",
        "provento",
        "anual",
        "adicionais habituais * dias_ferias / 30",
        None,
        None,
        False,
        False,
        False,
    ),
    (
        "0095",
        "Salario Familia",
        "provento",
        "mensal",
        "R$ 67,54 x filhos < 14 (teto R$ 1.819,26)",
        None,
        Decimal("67.54"),
        False,
        False,
        False,
    ),
    (
        "0937",
        "Adiantamento de Ferias",
        "desconto",
        "anual",
        "(ferias + vantagens + 1/3) - INSS ferias",
        None,
        None,
        False,
        False,
        False,
    ),
    (
        "1040",
        "Emprestimo Consignado / Pensao Alimenticia",
        "desconto",
        "mensal",
        "employee_deductions (valor ou %)",
        None,
        None,
        False,
        False,
        False,
    ),
    (
        "1045",
        "Desc. Adiantamento Salarial",
        "desconto",
        "mensal",
        "salario_base * 40% (dia 20)",
        40,
        None,
        False,
        False,
        False,
    ),
    ("1051", "Faltas", "desconto", "variavel", "dias_falta * salario_base / 30", None, None, False, False, False),
    (
        "1053",
        "DSR sobre Faltas",
        "desconto",
        "variavel",
        "dsr_perdidos * salario_base / 30",
        None,
        None,
        False,
        False,
        False,
    ),
]

_SQL_NOVA = (
    "INSERT INTO rubricas_folha (codigo, descricao, tipo, natureza, base_calculo, percentual, valor_fixo, incide_inss, incide_irrf, incide_fgts, ativo) "
    "VALUES (:c, :d, :t, :n, :bc, :p, :vf, :i1, :i2, :i3, true) ON CONFLICT (codigo) DO NOTHING"
)
_SET_SEED = ", ".join(f"{c} = :{c}" for c, _ in COLUNAS)


async def _ensure(db: AsyncSession) -> None:
    """DDL idempotente + semente. Só preenche atributo DGX onde `origem_regra` ainda é NULL —
    o que o dono editar na tela nunca é sobrescrito."""
    for col, ty in COLUNAS:
        await db.execute(text(f"ALTER TABLE rubricas_folha ADD COLUMN IF NOT EXISTS {col} {ty}"))  # noqa: S608 — nomes fixos
    for c, d, tp, n, bc, p, vf, i1, i2, i3 in NOVAS:
        await db.execute(
            text(_SQL_NOVA), {"c": c, "d": d, "t": tp, "n": n, "bc": bc, "p": p, "vf": vf, "i1": i1, "i2": i2, "i3": i3}
        )
    # credito deriva do tipo (provento=soma, desconto=subtrai) — o DGX pede o campo, a verdade é o tipo.
    sets = _SET_SEED.replace(
        "credito = :credito", "credito = CASE WHEN tipo = 'desconto' THEN 'subtrai' ELSE 'soma' END"
    )
    for cod, ev in SEED.items():
        await db.execute(
            text(f"UPDATE rubricas_folha SET {sets} WHERE codigo = :cod AND origem_regra IS NULL"),  # noqa: S608 — nomes fixos
            {**ev, "cod": cod},
        )
    await db.commit()


# ── tela ─────────────────────────────────────────────────────────────────────────────────────
_SQL_COMP = (
    "SELECT reference_year, reference_month FROM hr_payslips WHERE source_system='conecta' AND payslip_code NOT LIKE '13O-%' "
    "AND make_date(reference_year, reference_month, 1) <= date_trunc('month', now() AT TIME ZONE 'America/Manaus') "
    "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
)
_SQL_USO = (
    "SELECT e->>'codigo', e->>'tipo', min(e->>'descricao'), count(*), round(sum((e->>'valor')::numeric), 2) "
    "FROM hr_payslips p, jsonb_array_elements(p.earnings || p.deductions) e "
    "WHERE p.source_system='conecta' AND p.reference_year=:a AND p.reference_month=:m GROUP BY 1, 2"
)
_SQL_LISTA = (
    "SELECT id, codigo, descricao, tipo, natureza, base_calculo, percentual, valor_fixo, incide_inss, incide_irrf, incide_fgts, ativo, "
    + ", ".join(c for c, _ in COLUNAS)
    + " FROM rubricas_folha ORDER BY ativo DESC, codigo"
)
_SEL = lambda opts: [{"value": o, "label": (o or "—").replace("_", " ")} for o in opts]  # noqa: E731
_SN = [{"value": "nao", "label": "não"}, {"value": "sim", "label": "sim"}]


def _norm(s: str) -> str:
    import unicodedata

    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower())


def _campos(r: dict | None) -> list[dict]:
    """Campos do form (nova e editar). `r` = linha atual (None = nova)."""
    g = lambda k, d="": (r.get(k) if r and r.get(k) is not None else d)  # noqa: E731
    sn = lambda k: ("sim" if (r and r.get(k)) else "nao")  # noqa: E731
    num = lambda k: (str(r[k]) if r and r.get(k) is not None else "")  # noqa: E731
    f = [
        {"key": "codigo", "label": "Código*", "type": "text", "value": g("codigo"), "ph": "0017"},
        {"key": "descricao", "label": "Descrição*", "type": "text", "value": g("descricao"), "ph": "Adicional de …"},
        {
            "key": "tipo",
            "label": "Tipo*",
            "type": "select",
            "value": g("tipo", "provento"),
            "options": _SEL(("provento", "desconto")),
        },
        {
            "key": "natureza",
            "label": "Natureza",
            "type": "select",
            "value": g("natureza", "mensal"),
            "options": _SEL(NATUREZA),
        },
        {
            "key": "periodo",
            "label": "Período",
            "type": "select",
            "value": g("periodo", "mes"),
            "options": _SEL(PERIODO),
        },
        {
            "key": "tipo_dia",
            "label": "Tipo do dia",
            "type": "select",
            "value": g("tipo_dia", "dia_normal"),
            "options": _SEL(TIPO_DIA),
        },
        {"key": "base", "label": "Base", "type": "select", "value": g("base", "salario_base"), "options": _SEL(BASE)},
        {
            "key": "porcentagem_ou_valor",
            "label": "Porcentagem ou valor",
            "type": "select",
            "value": g("porcentagem_ou_valor", "valor"),
            "options": _SEL(PCT_VALOR),
        },
        {"key": "razao", "label": "Razão (fator ou R$)", "type": "text", "value": num("razao"), "ph": "1.5"},
        {"key": "razao_noturna", "label": "Razão noturna", "type": "text", "value": num("razao_noturna"), "ph": "1.8"},
        {
            "key": "base_calculo",
            "label": "Fórmula (texto)",
            "type": "text",
            "value": g("base_calculo"),
            "span": "span 2",
            "ph": "hora_normal * 1.5",
        },
        {"key": "incide_inss", "label": "Incide INSS", "type": "select", "value": sn("incide_inss"), "options": _SN},
        {"key": "incide_irrf", "label": "Incide IRRF", "type": "select", "value": sn("incide_irrf"), "options": _SN},
        {"key": "incide_fgts", "label": "Incide FGTS", "type": "select", "value": sn("incide_fgts"), "options": _SN},
        {"key": "incide_dsr", "label": "Reflete DSR", "type": "select", "value": sn("incide_dsr"), "options": _SN},
        {"key": "incide_13", "label": "Compõe 13º", "type": "select", "value": sn("incide_13"), "options": _SN},
        {"key": "media_13", "label": "Média no 13º", "type": "select", "value": sn("media_13"), "options": _SN},
        {
            "key": "soma_ao_evento",
            "label": "Soma ao evento (ponto)",
            "type": "select",
            "value": g("soma_ao_evento", "nao"),
            "options": _SEL(SOMA_AO_EVENTO),
        },
        {
            "key": "soma_ao_ponto",
            "label": "Soma ao ponto",
            "type": "select",
            "value": sn("soma_ao_ponto"),
            "options": _SN,
        },
        {
            "key": "banco_horas",
            "label": "Banco de horas",
            "type": "select",
            "value": g("banco_horas", "nao"),
            "options": _SEL(BANCO_HORAS),
        },
        {"key": "hora_extra", "label": "É hora extra", "type": "select", "value": sn("hora_extra"), "options": _SN},
        {"key": "ausencia", "label": "É ausência", "type": "select", "value": sn("ausencia"), "options": _SN},
        {"key": "vale", "label": "É vale/adiantamento", "type": "select", "value": sn("vale"), "options": _SN},
        {
            "key": "considerar_descanso",
            "label": "Considerar descanso",
            "type": "select",
            "value": sn("considerar_descanso"),
            "options": _SN,
        },
        {
            "key": "remove_ponto_calculado",
            "label": "Remove ponto calculado",
            "type": "select",
            "value": sn("remove_ponto_calculado"),
            "options": _SN,
        },
        {
            "key": "remove_diaria",
            "label": "Remove diária (VT/VR)",
            "type": "select",
            "value": sn("remove_diaria"),
            "options": _SN,
        },
        {
            "key": "desconta_beneficio",
            "label": "Desconta benefício",
            "type": "select",
            "value": sn("desconta_beneficio"),
            "options": _SN,
        },
        {
            "key": "tipo_beneficio_descontado",
            "label": "Qual benefício",
            "type": "select",
            "value": g("tipo_beneficio_descontado"),
            "options": _SEL(TIPO_BENEFICIO),
        },
        {
            "key": "comercial",
            "label": "Comercial (cobra do cliente)",
            "type": "select",
            "value": sn("comercial"),
            "options": _SN,
        },
        {
            "key": "exporta_evento",
            "label": "Exporta p/ contador",
            "type": "select",
            "value": ("sim" if not r or r.get("exporta_evento") else "nao"),
            "options": _SN,
        },
        {
            "key": "codigo_exportacao",
            "label": "Código no contador (Portte/Domínio)",
            "type": "text",
            "value": g("codigo_exportacao"),
            "ph": "246",
        },
        {
            "key": "origem_regra",
            "label": "Origem da regra (cláusula CCT, lei, linha do motor)*",
            "type": "textarea",
            "value": g("origem_regra"),
            "span": "span 2",
            "ph": "CCT SINDECOMPRESTS 2026 Cl. 23ª / calculo_service.py L…",
        },
    ]
    if r:
        f.insert(0, {"key": "id", "type": "hidden", "label": "id", "value": str(r["id"])})
    return f


async def telas(db, out: dict | None = None) -> dict:
    await _ensure(db)
    mine, safe, _tbl = _helpers(db)
    comp = (await db.execute(text(_SQL_COMP))).first()
    uso: dict[tuple[str, str], tuple[str, int, Decimal]] = {}
    if comp:
        for cod, tp, desc, n, soma in (await db.execute(text(_SQL_USO), {"a": comp[0], "m": comp[1]})).fetchall():
            uso[(cod, tp)] = (desc, int(n), soma)
    comp_txt = f"{int(comp[1]):02d}/{comp[0]}" if comp else "—"
    cols = [
        "id",
        "codigo",
        "descricao",
        "tipo",
        "natureza",
        "base_calculo",
        "percentual",
        "valor_fixo",
        "incide_inss",
        "incide_irrf",
        "incide_fgts",
        "ativo",
        *[c for c, _ in COLUNAS],
    ]
    linhas = [dict(zip(cols, r, strict=True)) for r in (await db.execute(text(_SQL_LISTA))).fetchall()]

    def _linha(r: dict) -> dict:
        u = uso.get((r["codigo"], r["tipo"]))
        inc = (
            "·".join(
                x
                for x, ok in (("INSS", r["incide_inss"]), ("IRRF", r["incide_irrf"]), ("FGTS", r["incide_fgts"]))
                if ok
            )
            or "—"
        )
        refl = (
            "·".join(x for x, ok in (("DSR", r["incide_dsr"]), ("13º", r["incide_13"]), ("média", r["media_13"])) if ok)
            or "—"
        )
        raz = f"{float(r['razao']):g}" if r["razao"] is not None else "—"
        if r["porcentagem_ou_valor"] == "porcentagem" and r["razao"] is not None:
            raz = f"{float(r['razao']) * 100:g}%" if float(r["razao"]) < 1 else f"×{float(r['razao']):g}"
        elif r["razao"] is not None and r["porcentagem_ou_valor"] == "valor" and float(r["razao"]) > 1:
            raz = brl(float(r["razao"]))
        if u:
            cel_uso = t(f"{u[1]} × {brl(float(u[2]))}", 600, _ND)
            _a, _b = _norm(u[0]), _norm(r["descricao"])
            desc_h = b("bate", "ok") if (_a in _b or _b in _a) else b(f"no holerite: {u[0]}", "warn")
        else:
            cel_uso, desc_h = t("—"), b("não emitida", "mut")
        acao = {
            "title": ("Reativar" if not r["ativo"] else "Inativar") + f" — {r['codigo']} {r['descricao']}",
            "endpoint": _ACT + "rubrica-inativar",
            "method": "POST",
            "btnLabel": "Reativar" if not r["ativo"] else "Inativar",
            "submitLabel": "Confirmar",
            "btnStyle": "outline" if r["ativo"] else "primary",
            "okMsg": "Rubrica atualizada. Recarregue a tela.",
            "fields": [{"key": "id", "type": "hidden", "label": "id", "value": str(r["id"])}],
        }
        return {
            "cells": [
                t(r["codigo"], 700, _ND),
                t(r["descricao"], 600, _ND),
                b(r["tipo"], "ok" if r["tipo"] == "provento" else "bad"),
                t((r["periodo"] or "—") + " · " + (r["base"] or "—").replace("_", " ")),
                t(raz),
                t(inc),
                t(refl),
                t(r["codigo_exportacao"] or "—"),
                cel_uso,
                desc_h,
                b("ativa", "ok") if r["ativo"] else b("inativa", "mut"),
            ],
            "edit": {
                "title": f"Editar rubrica {r['codigo']}",
                "endpoint": _ACT + "rubrica-salvar",
                "method": "POST",
                "okMsg": "Rubrica salva. Recarregue a tela.",
                "fields": _campos(r),
            },
            "actions": [acao],
            "filtro": "ativas" if r["ativo"] else "inativas",
        }

    n_at = sum(1 for r in linhas if r["ativo"])
    n_uso_sem = [c for (c, tp) in uso if not any(r["codigo"] == c and r["tipo"] == tp and r["ativo"] for r in linhas)]
    mine["folha-rubricas"] = {
        "title": "Rubricas (eventos da folha)",
        "sub": (
            f"{len(linhas)} rubricas ({n_at} ativas) · uso medido nos holerites de {comp_txt} · atributos do DGX (período, base, razão, "
            f"incidências, reflexos, ponto, benefício, exportação). O motor de folha NÃO lê este cadastro ainda — o oráculo "
            f"`rubricas_dizem_a_verdade` prova que ele diz a verdade sobre o que o motor faz"
            + (
                f" · ⚠ {len(n_uso_sem)} código(s) no holerite sem rubrica ativa: {', '.join(sorted(n_uso_sem))}"
                if n_uso_sem
                else ""
            )
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar código, descrição…",
        "grid": "0.5fr 1.8fr 0.7fr 1fr 0.6fr 0.9fr 0.8fr 0.6fr 1fr 1.3fr 0.6fr",
        "cols": [
            "Código",
            "Descrição",
            "Tipo",
            "Período · base",
            "Razão",
            "Incide",
            "Reflexos",
            "Cód. contador",
            f"Uso {comp_txt}",
            "Descrição no holerite",
            "Status",
        ],
        "rows": [_linha(r) for r in linhas],
    }
    mine["folha-rubrica-nova"] = {
        "title": "Nova rubrica",
        "sub": "Cadastro de evento da folha com os atributos do DGX. Código único; rubrica usada em holerite nunca é apagada — só inativada. "
        "Cadastrar aqui NÃO faz o motor calculá-la: a regra de cálculo continua em calculo_service.py (decisão do dono, F1).",
        "cta": "Salvar rubrica",
        "type": "form",
        "submit": {"endpoint": _ACT + "rubrica-salvar", "okMsg": "Rubrica cadastrada — veja a aba Rubricas."},
        "fields": _campos(None),
    }
    return mine


# ── ações (router definido no topo) ──────────────────────────────────────────────────────────


def _sn(v) -> bool:
    return str(v or "").strip().lower() in ("sim", "true", "1", "s")


def _dec(v, rot: str) -> Decimal:
    s = str(v or "0").strip().replace(",", ".")
    try:
        return Decimal(s or "0")
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"{rot}: número inválido ({s!r}).")


def _enum(v, opts, rot: str) -> str:
    s = str(v or "").strip().lower()
    if s not in opts:
        raise HTTPException(status_code=400, detail=f"{rot}: use um de {', '.join(o or '(vazio)' for o in opts)}.")
    return s


@router.post("/action/rubrica-salvar")
async def rd_rubrica_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    rid = str(payload.get("id") or "").strip()
    codigo = str(payload.get("codigo") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{1,10}", codigo):
        raise HTTPException(status_code=400, detail="Código: 1 a 10 letras/dígitos (ex.: 0017).")
    descricao = str(payload.get("descricao") or "").strip()
    if len(descricao) < 3:
        raise HTTPException(status_code=400, detail="Descrição obrigatória.")
    origem = str(payload.get("origem_regra") or "").strip()
    if len(origem) < 5:
        raise HTTPException(
            status_code=400, detail="Origem da regra obrigatória (cláusula da CCT, lei ou linha do motor)."
        )
    tipo = _enum(payload.get("tipo"), ("provento", "desconto"), "Tipo")
    v = {
        "codigo": codigo,
        "descricao": descricao,
        "tipo": tipo,
        "natureza": _enum(payload.get("natureza") or "mensal", NATUREZA, "Natureza"),
        "base_calculo": str(payload.get("base_calculo") or "").strip() or None,
        "periodo": _enum(payload.get("periodo") or "mes", PERIODO, "Período"),
        "tipo_dia": _enum(payload.get("tipo_dia") or "dia_normal", TIPO_DIA, "Tipo do dia"),
        "credito": "subtrai" if tipo == "desconto" else "soma",
        "soma_ao_evento": _enum(payload.get("soma_ao_evento") or "nao", SOMA_AO_EVENTO, "Soma ao evento"),
        "banco_horas": _enum(payload.get("banco_horas") or "nao", BANCO_HORAS, "Banco de horas"),
        "tipo_beneficio_descontado": _enum(
            payload.get("tipo_beneficio_descontado") or "", TIPO_BENEFICIO, "Qual benefício"
        ),
        "base": _enum(payload.get("base") or "salario_base", BASE, "Base"),
        "porcentagem_ou_valor": _enum(
            payload.get("porcentagem_ou_valor") or "valor", PCT_VALOR, "Porcentagem ou valor"
        ),
        "razao": _dec(payload.get("razao"), "Razão"),
        "razao_noturna": _dec(payload.get("razao_noturna"), "Razão noturna"),
        "codigo_exportacao": str(payload.get("codigo_exportacao") or "").strip(),
        "origem_regra": origem,
        "exporta_evento": _sn(payload.get("exporta_evento", "sim")),
    }
    for k in ("incide_inss", "incide_irrf", "incide_fgts", *(BOOLS - {"exporta_evento"})):
        v[k] = _sn(payload.get(k))
    if v["desconta_beneficio"] and not v["tipo_beneficio_descontado"]:
        raise HTTPException(status_code=400, detail="Desconta benefício = sim exige 'Qual benefício'.")
    v["percentual"] = (v["razao"] * 100) if v["porcentagem_ou_valor"] == "porcentagem" and v["razao"] <= 1 else None
    v["valor_fixo"] = v["razao"] if v["porcentagem_ou_valor"] == "valor" and v["razao"] > 0 else None

    dup = (await db.execute(text("SELECT id FROM rubricas_folha WHERE codigo = :c"), {"c": codigo})).scalar()
    if dup is not None and str(dup) != rid:
        raise HTTPException(
            status_code=409,
            detail=f"Código {codigo} já existe (id {dup}). Edite a rubrica existente ou escolha outro código.",
        )
    sets = ", ".join(f"{k} = :{k}" for k in v)
    if rid:
        if not rid.isdigit():
            raise HTTPException(status_code=400, detail="id inválido.")
        v["id"] = int(rid)
        n = (await db.execute(text(f"UPDATE rubricas_folha SET {sets}, updated_at = now() WHERE id = :id"), v)).rowcount  # noqa: S608
        if not n:
            raise HTTPException(status_code=404, detail="Rubrica não encontrada.")
        msg = f"Rubrica {codigo} atualizada."
    else:
        v["id"] = (
            await db.execute(
                text(
                    f"INSERT INTO rubricas_folha ({', '.join(v)}, ativo) VALUES ({', '.join(':' + k for k in v)}, true) RETURNING id"
                ),
                v,  # noqa: S608
            )
        ).scalar()
        msg = f"Rubrica {codigo} cadastrada (id {v['id']})."
    await db.commit()
    return {
        "ok": True,
        "message": msg + " O motor de folha NÃO lê este cadastro ainda (F1 = paralelo cego).",
        "id": v["id"],
        "codigo": codigo,
    }


@router.post("/action/rubrica-inativar")
async def rd_rubrica_inativar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Alterna ativo/inativo. Nunca apaga: rubrica usada em holerite é história trabalhista. Não deixa
    inativar rubrica que está nos holerites da competência corrente — o oráculo acusaria na hora."""
    await _ensure(db)
    rid = str(payload.get("id") or "").strip()
    if not rid.isdigit():
        raise HTTPException(status_code=400, detail="id inválido.")
    r = (
        await db.execute(text("SELECT codigo, tipo, ativo FROM rubricas_folha WHERE id = :id"), {"id": int(rid)})
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Rubrica não encontrada.")
    if r[2]:
        comp = (await db.execute(text(_SQL_COMP))).first()
        n = 0
        if comp:
            n = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM hr_payslips p WHERE p.source_system='conecta' AND p.reference_year=:a AND p.reference_month=:m "
                        "AND EXISTS (SELECT 1 FROM jsonb_array_elements(p.earnings || p.deductions) e WHERE e->>'codigo' = :c AND e->>'tipo' = :t)"
                    ),
                    {"a": comp[0], "m": comp[1], "c": r[0], "t": r[1]},
                )
            ).scalar()
        if n:
            raise HTTPException(
                status_code=409,
                detail=f"{r[0]} está em {n} holerite(s) de {int(comp[1]):02d}/{comp[0]} — inative depois de fechar a competência.",
            )
    await db.execute(
        text("UPDATE rubricas_folha SET ativo = NOT ativo, updated_at = now() WHERE id = :id"), {"id": int(rid)}
    )
    await db.commit()
    return {"ok": True, "message": f"Rubrica {r[0]} {'inativada' if r[2] else 'reativada'} em {date.today():%d/%m/%Y}."}
