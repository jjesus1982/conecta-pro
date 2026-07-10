"""Calculadora CLT - Legislação Trabalhista Brasileira.

Implementa todos os cálculos trabalhistas conforme legislação vigente:
INSS faixa progressiva, IRRF, férias, 13o, rescisão, hora extra, etc.

Todos os valores monetários usam Decimal para precisão.

⚠️ VERACIDADE / RISCO JURÍDICO: as constantes abaixo (INSS/IRRF/salário mínimo)
carregam VALORES DE 2024, NÃO os de 2026, e NÃO estão certificadas. A fonte oficial
(Portaria Interministerial MTE/MF do salário mínimo + tabela RFB do IRRF 2026, que
inclui a reforma da isenção) deve ser fornecida pelo DP/Contábil e certificada antes
de uso em folha real. Enquanto TABELAS_LEGAIS_CERTIFICADAS_2026 == False, qualquer
holerite gerado por este módulo é ESTIMATIVA, não valor legal.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# ===========================================================================
# TABELAS DE REFERÊNCIA — ⚠️ VALORES 2024, PENDENTE ATUALIZAÇÃO + CERTIFICAÇÃO 2026
# ===========================================================================

# Gate de honestidade: INSS já é oficial 2026; IRRF ainda pendente (reforma do redutor).
# NOTA: a base salarial da categoria é o PISO da CCT (R$1.670), NÃO o salário mínimo.
# SALARIO_MINIMO abaixo é o mínimo FEDERAL, usado só como base legal de insalubridade (CLT).
INSS_CERTIFICADA_2026 = True  # Portaria Interministerial MPS/MF nº 13
IRRF_CERTIFICADA_2026 = False  # reforma isenção-R$5.000 (redutor) pendente
TABELAS_LEGAIS_CERTIFICADAS_2026 = False  # geral False enquanto IRRF pendente
VIGENCIA_TABELAS_LEGAIS = "2026-INSS / 2024-IRRF"

SALARIO_MINIMO = Decimal("1621.00")  # mínimo FEDERAL 2026 (Portaria nº 13). Base ≠ piso CCT R$1.670
TETO_INSS = Decimal("8475.55")  # teto INSS 2026

# INSS Faixas Progressivas 2026 — OFICIAL Portaria Interministerial MPS/MF nº 13
INSS_FAIXAS: list[tuple[Decimal, Decimal]] = [
    (Decimal("1621.00"), Decimal("0.075")),
    (Decimal("2902.84"), Decimal("0.09")),
    (Decimal("4354.27"), Decimal("0.12")),
    (Decimal("8475.55"), Decimal("0.14")),
]

# IRRF Tabela Progressiva Mensal 2026 — OFICIAL (Lei 15.191/2025; isenção R$2.428,80)
IRRF_FAIXAS: list[tuple[Decimal, Decimal, Decimal]] = [
    (Decimal("2428.80"), Decimal("0.0"), Decimal("0.0")),
    (Decimal("2826.65"), Decimal("0.075"), Decimal("182.16")),
    (Decimal("3751.05"), Decimal("0.15"), Decimal("394.16")),
    (Decimal("4664.68"), Decimal("0.225"), Decimal("675.49")),
    (Decimal("999999999"), Decimal("0.275"), Decimal("908.73")),
]

DEDUCAO_DEPENDENTE_IRRF = Decimal("189.59")
# Redutor da reforma (Lei 15.270/2025): isenção até R$5.000, decresce até R$0 em R$7.350.
# Aplicado só na folha MENSAL (passar rendimento_bruto). Rescisão/férias/13º têm regra própria.
IRRF_REDUTOR_A = Decimal("978.62")
IRRF_REDUTOR_B = Decimal("0.133145")
FGTS_PERCENTUAL = Decimal("0.08")

_TWO = Decimal("0.01")


def _d(value: float | int | str) -> Decimal:
    """Converte para Decimal."""
    return Decimal(str(value))


def calcular_inss(salario_bruto: Decimal) -> Decimal:
    """Calcula INSS faixa progressiva 2026.

    Args:
        salario_bruto: Salário bruto mensal.

    Returns:
        Valor do INSS a descontar.
    """
    if salario_bruto <= 0:
        return Decimal("0")

    inss = Decimal("0")
    base_anterior = Decimal("0")

    for teto_faixa, aliquota in INSS_FAIXAS:
        if salario_bruto <= base_anterior:
            break
        base_faixa = min(salario_bruto, teto_faixa) - base_anterior
        if base_faixa > 0:
            inss += (base_faixa * aliquota).quantize(_TWO, ROUND_HALF_UP)
        base_anterior = teto_faixa

    return inss.quantize(_TWO, ROUND_HALF_UP)


def calcular_irrf(
    base_calculo: Decimal,
    dependentes: int = 0,
    pensao_alimenticia: Decimal = Decimal("0"),
    rendimento_bruto: Decimal | None = None,
) -> Decimal:
    """Calcula IRRF com dedutíveis (tabela 2026 + reforma opcional).

    Args:
        base_calculo: Base de cálculo (bruto - INSS - deduções).
        dependentes: Número de dependentes.
        pensao_alimenticia: Valor de pensão alimentícia.
        rendimento_bruto: Rendimento bruto tributável. Se informado, aplica o redutor
            da reforma (Lei 15.270/2025) — isenção até R$5.000. Use SÓ na folha mensal;
            rescisão/férias/13º têm regra própria (não passar).

    Returns:
        Valor do IRRF a descontar.
    """
    deducoes = (DEDUCAO_DEPENDENTE_IRRF * dependentes) + pensao_alimenticia
    base = base_calculo - deducoes

    if base <= 0:
        return Decimal("0")

    irrf = Decimal("0")
    for teto, aliquota, deducao in IRRF_FAIXAS:
        if base <= teto:
            irrf = (base * aliquota - deducao).quantize(_TWO, ROUND_HALF_UP)
            break

    # Redutor da reforma (só folha mensal, quando rendimento_bruto é informado)
    if rendimento_bruto is not None and rendimento_bruto > 0:
        redutor = IRRF_REDUTOR_A - IRRF_REDUTOR_B * rendimento_bruto
        if redutor > 0:
            irrf = irrf - redutor

    return max(irrf, Decimal("0"))


def calcular_hora_normal(salario_base: Decimal, carga_horaria_mensal: Decimal = Decimal("220")) -> Decimal:
    """Valor da hora normal.

    Args:
        salario_base: Salário base mensal.
        carga_horaria_mensal: Carga horária mensal (padrão 220h para 44h/sem).

    Returns:
        Valor da hora normal.
    """
    if carga_horaria_mensal <= 0:
        return Decimal("0")
    return (salario_base / carga_horaria_mensal).quantize(_TWO, ROUND_HALF_UP)


def calcular_hora_extra_50(valor_hora: Decimal, quantidade_horas: Decimal) -> Decimal:
    """Hora extra 50% (segunda a sábado).

    Args:
        valor_hora: Valor da hora normal.
        quantidade_horas: Quantidade de horas extras.

    Returns:
        Valor total das horas extras 50%.
    """
    return (valor_hora * Decimal("1.5") * quantidade_horas).quantize(_TWO, ROUND_HALF_UP)


def calcular_hora_extra_100(valor_hora: Decimal, quantidade_horas: Decimal) -> Decimal:
    """Hora extra 100% (domingos e feriados).

    Args:
        valor_hora: Valor da hora normal.
        quantidade_horas: Quantidade de horas extras.

    Returns:
        Valor total das horas extras 100%.
    """
    return (valor_hora * Decimal("2.0") * quantidade_horas).quantize(_TWO, ROUND_HALF_UP)


def calcular_adicional_noturno(valor_hora: Decimal, horas_noturnas: Decimal) -> Decimal:
    """Adicional noturno 20% (22h-05h).

    A hora noturna reduzida (52min30s) já deve ser considerada
    na contagem de horas_noturnas pelo chamador.

    Args:
        valor_hora: Valor da hora normal.
        horas_noturnas: Total de horas noturnas trabalhadas.

    Returns:
        Valor do adicional noturno.
    """
    return (valor_hora * Decimal("0.20") * horas_noturnas).quantize(_TWO, ROUND_HALF_UP)


def calcular_dsr_sobre_extras(total_extras: Decimal, dias_uteis: int, domingos_feriados: int) -> Decimal:
    """DSR (Descanso Semanal Remunerado) sobre horas extras.

    Fórmula: (total_extras / dias_úteis) * domingos_e_feriados

    Args:
        total_extras: Valor total de horas extras no mês.
        dias_uteis: Dias úteis trabalhados no mês.
        domingos_feriados: Domingos e feriados no mês.

    Returns:
        Valor do DSR sobre extras.
    """
    if dias_uteis <= 0:
        return Decimal("0")
    return (total_extras / dias_uteis * domingos_feriados).quantize(_TWO, ROUND_HALF_UP)


def calcular_periculosidade(salario_base: Decimal) -> Decimal:
    """Adicional de periculosidade 30%.

    Args:
        salario_base: Salário base mensal.

    Returns:
        Valor do adicional de periculosidade.
    """
    return (salario_base * Decimal("0.30")).quantize(_TWO, ROUND_HALF_UP)


def calcular_insalubridade(grau: str) -> Decimal:
    """Adicional de insalubridade sobre salário mínimo.

    Args:
        grau: 'minimo' (10%), 'medio' (20%) ou 'maximo' (40%).

    Returns:
        Valor do adicional de insalubridade.
    """
    percentuais = {
        "minimo": Decimal("0.10"),
        "medio": Decimal("0.20"),
        "maximo": Decimal("0.40"),
    }
    pct = percentuais.get(grau, Decimal("0"))
    return (SALARIO_MINIMO * pct).quantize(_TWO, ROUND_HALF_UP)


def calcular_ferias(salario_base: Decimal, dias_gozo: int = 30, dias_abono: int = 0) -> dict:
    """Calcula férias + 1/3 constitucional + abono pecuniário.

    Args:
        salario_base: Salário base mensal.
        dias_gozo: Dias de gozo (máximo 30).
        dias_abono: Dias de abono pecuniário (máximo 10).

    Returns:
        Dict com valor_ferias, terco_constitucional, abono_pecuniario, total.
    """
    valor_dia = salario_base / 30
    valor_ferias = (valor_dia * dias_gozo).quantize(_TWO, ROUND_HALF_UP)
    terco = (valor_ferias / 3).quantize(_TWO, ROUND_HALF_UP)
    abono = (valor_dia * dias_abono).quantize(_TWO, ROUND_HALF_UP)
    terco_abono = (abono / 3).quantize(_TWO, ROUND_HALF_UP)
    total = valor_ferias + terco + abono + terco_abono

    return {
        "valor_ferias": valor_ferias,
        "terco_constitucional": terco,
        "abono_pecuniario": abono,
        "terco_abono": terco_abono,
        "total_bruto": total,
    }


def calcular_13_proporcional(salario_base: Decimal, meses_trabalhados: int) -> Decimal:
    """13o salário proporcional.

    Args:
        salario_base: Salário base mensal.
        meses_trabalhados: Meses trabalhados no ano (avos).

    Returns:
        Valor do 13o proporcional.
    """
    meses = min(max(meses_trabalhados, 0), 12)
    return (salario_base * meses / 12).quantize(_TWO, ROUND_HALF_UP)


def _avos_ano_civil(data_demissao: date) -> int:
    """Avos do 13º proporcional: meses do ANO CIVIL da demissão (jan→demissão).

    Regra CLT/Súmula 461 TST: cada mês com fração >= 15 dias trabalhados conta 1 avo.
    A base do 13º é sempre o ano civil (jan a dez), independente da data de admissão.
    O mês da demissão só conta se o último dia de trabalho for >= dia 15.

    Args:
        data_demissao: Último dia de trabalho.

    Returns:
        Número de avos (0..12).
    """
    avos = data_demissao.month - 1  # meses cheios de janeiro até o mês anterior
    if data_demissao.day >= 15:
        avos += 1
    return max(0, min(avos, 12))


def _avos_periodo_aquisitivo(data_admissao: date, data_demissao: date) -> int:
    """Avos das férias proporcionais: meses do PERÍODO AQUISITIVO em curso.

    O período aquisitivo é o ciclo de 12 meses contado a partir do último
    aniversário de admissão. Cada mês com fração >= 15 dias conta 1 avo
    (art. 146 §único CLT / Súmula 171 TST).

    Args:
        data_admissao: Data de admissão.
        data_demissao: Último dia de trabalho.

    Returns:
        Número de avos (0..12).
    """
    # Meses completos de calendário desde a admissão até a demissão.
    meses = (data_demissao.year - data_admissao.year) * 12 + (
        data_demissao.month - data_admissao.month
    )
    # Ajuste pelo dia: se ainda não completou o dia do aniversário no mês da
    # demissão, o mês corrente não fechou — mas conta como avo se >= 15 dias
    # decorridos desde o aniversário do mês.
    if data_demissao.day < data_admissao.day:
        meses -= 1
        dias_no_mes_corrente = data_demissao.day + (30 - data_admissao.day)
    else:
        dias_no_mes_corrente = data_demissao.day - data_admissao.day
    if dias_no_mes_corrente >= 15:
        meses += 1
    # Reduz ao período aquisitivo em curso (0..12).
    resto = meses % 12
    # Se completou exatamente múltiplo de 12 e há fração, resto=0 mas há período novo.
    if resto == 0 and meses > 0 and dias_no_mes_corrente > 0 and meses % 12 == 0:
        # período aquisitivo recém-iniciado sem avos completos além do fechado
        resto = 0
    return max(0, min(resto, 12))


def calcular_aviso_previo_dias(anos_servico: int) -> int:
    """Aviso prévio proporcional ao tempo de serviço.

    30 dias base + 3 dias por ano de serviço, máximo 90 dias.

    Args:
        anos_servico: Anos completos de serviço.

    Returns:
        Dias de aviso prévio.
    """
    dias = 30 + (3 * max(anos_servico, 0))
    return min(dias, 90)


def calcular_fgts_mensal(remuneracao_bruta: Decimal) -> Decimal:
    """FGTS mensal 8%.

    Args:
        remuneracao_bruta: Remuneração bruta mensal.

    Returns:
        Valor do FGTS mensal.
    """
    return (remuneracao_bruta * FGTS_PERCENTUAL).quantize(_TWO, ROUND_HALF_UP)


def calcular_multa_fgts(saldo_fgts: Decimal, tipo_rescisao: str) -> Decimal:
    """Multa FGTS conforme tipo de rescisão.

    Args:
        saldo_fgts: Saldo total do FGTS.
        tipo_rescisao: 'sem_justa_causa' (40%), 'acordo' (20%),
                       'justa_causa'/'pedido_demissao' (0%).

    Returns:
        Valor da multa FGTS.
    """
    percentuais = {
        "sem_justa_causa": Decimal("0.40"),
        "involuntary": Decimal("0.40"),
        "acordo": Decimal("0.20"),
        "mutual_agreement": Decimal("0.20"),
        "justa_causa": Decimal("0"),
        "just_cause": Decimal("0"),
        "pedido_demissao": Decimal("0"),
        "voluntary": Decimal("0"),
    }
    pct = percentuais.get(tipo_rescisao, Decimal("0"))
    return (saldo_fgts * pct).quantize(_TWO, ROUND_HALF_UP)


def calcular_vale_transporte_desconto(salario_base: Decimal) -> Decimal:
    """Desconto de Vale Transporte: 4% do salário base (CCT SINDECOMPRESTS Cl.14ª).

    A CCT fixa 4% (não os 6% máximos da CLT genérica).

    Args:
        salario_base: Salário base mensal.

    Returns:
        Valor do desconto de VT.
    """
    return (salario_base * Decimal("0.04")).quantize(_TWO, ROUND_HALF_UP)


def calcular_saldo_salario(salario_base: Decimal, dias_trabalhados: int) -> Decimal:
    """Saldo de salário proporcional aos dias trabalhados.

    Args:
        salario_base: Salário base mensal.
        dias_trabalhados: Dias trabalhados no mês da rescisão.

    Returns:
        Valor do saldo de salário.
    """
    return (salario_base / 30 * dias_trabalhados).quantize(_TWO, ROUND_HALF_UP)


def calcular_rescisao(
    salario_base: Decimal,
    tipo_rescisao: str,
    data_admissao: date,
    data_demissao: date,
    saldo_fgts: Decimal = Decimal("0"),
    ferias_vencidas_dias: int = 0,
    dias_trabalhados_mes: int = 0,
) -> dict:
    """Calcula rescisão completa conforme legislação.

    Args:
        salario_base: Último salário base.
        tipo_rescisao: voluntary, involuntary, just_cause, mutual_agreement.
        data_admissao: Data de admissão.
        data_demissao: Data de demissão.
        saldo_fgts: Saldo total do FGTS acumulado.
        ferias_vencidas_dias: Dias de férias vencidas não gozadas.
        dias_trabalhados_mes: Dias trabalhados no mês da rescisão.

    Returns:
        Dict com detalhamento completo da rescisão.
    """
    # Tempo de serviço (anos completos, para o aviso prévio proporcional).
    delta = data_demissao - data_admissao
    anos_servico = delta.days // 365

    # ------------------------------------------------------------------
    # AVOS — bases DISTINTAS por verba (não usar um único "meses_ano"):
    #  • 13º proporcional  → avos do ANO CIVIL (jan→demissão), Súmula 461 TST.
    #  • Férias proporc.   → avos do PERÍODO AQUISITIVO em curso (desde o
    #    último aniversário de admissão), art. 146 CLT / Súmula 171 TST.
    # É por isso que 13º e férias proporcionais podem (e costumam) diferir.
    # ------------------------------------------------------------------
    avos_13 = _avos_ano_civil(data_demissao)
    avos_ferias = _avos_periodo_aquisitivo(data_admissao, data_demissao)

    valor_dia = salario_base / 30

    # Saldo de salário
    saldo_sal = calcular_saldo_salario(salario_base, dias_trabalhados_mes)

    # Aviso prévio
    aviso_dias = calcular_aviso_previo_dias(anos_servico)
    tem_aviso = tipo_rescisao in ("involuntary", "sem_justa_causa")
    aviso_indenizado = (valor_dia * aviso_dias).quantize(_TWO, ROUND_HALF_UP) if tem_aviso else Decimal("0")

    # Acordo: 50% do aviso
    if tipo_rescisao in ("mutual_agreement", "acordo"):
        aviso_indenizado = (valor_dia * aviso_dias * Decimal("0.5")).quantize(_TWO, ROUND_HALF_UP)

    # Férias vencidas + 1/3
    ferias_venc = (valor_dia * ferias_vencidas_dias).quantize(_TWO, ROUND_HALF_UP)
    terco_venc = (ferias_venc / 3).quantize(_TWO, ROUND_HALF_UP)

    # Férias proporcionais + 1/3 (não paga em justa causa) — base = avos do
    # período aquisitivo.
    ferias_prop = Decimal("0")
    terco_prop = Decimal("0")
    if tipo_rescisao not in ("just_cause", "justa_causa"):
        ferias_prop = (salario_base * avos_ferias / 12).quantize(_TWO, ROUND_HALF_UP)
        terco_prop = (ferias_prop / 3).quantize(_TWO, ROUND_HALF_UP)

    # 13o proporcional (não paga em justa causa) — base = avos do ano civil.
    decimo_terceiro = Decimal("0")
    if tipo_rescisao not in ("just_cause", "justa_causa"):
        decimo_terceiro = calcular_13_proporcional(salario_base, avos_13)

    # Multa FGTS — NÃO é provento/remuneração: é indenização depositada na
    # conta vinculada do FGTS. Fica FORA do "total de proventos" e não sofre
    # INSS/IRRF. É totalizada em separado (total_indenizatorio_fgts).
    multa_fgts = calcular_multa_fgts(saldo_fgts, tipo_rescisao)

    # -------------------------------------------------------------------
    # TOTAL DE PROVENTOS = soma EXATA das verbas de provento listadas.
    # (saldo + aviso + férias venc + 1/3 venc + férias prop + 1/3 prop + 13º)
    # A multa FGTS NÃO entra aqui — por isso o antigo total_bruto (que a
    # incluía) não reconciliava com as linhas exibidas na tela.
    # -------------------------------------------------------------------
    total_proventos = (
        saldo_sal
        + aviso_indenizado
        + ferias_venc
        + terco_venc
        + ferias_prop
        + terco_prop
        + decimo_terceiro
    )

    # Total bruto (proventos + parcela indenizatória do FGTS), mantido por
    # compatibilidade com chamadores que somavam tudo.
    total_bruto = total_proventos + multa_fgts

    # Descontos (INSS + IRRF sobre saldo salário + 13o)
    base_inss = saldo_sal + decimo_terceiro
    inss = calcular_inss(base_inss)
    base_irrf = base_inss - inss
    irrf = calcular_irrf(base_irrf)
    total_descontos = inss + irrf

    # Líquido a receber pelo trabalhador = proventos - descontos + multa FGTS.
    # A multa é indenizatória e não sofre descontos, então entra "cheia".
    total_liquido = total_proventos - total_descontos + multa_fgts

    return {
        "saldo_salario": saldo_sal,
        "aviso_previo_indenizado": aviso_indenizado,
        "aviso_previo_dias": aviso_dias if tem_aviso or tipo_rescisao in ("mutual_agreement", "acordo") else 0,
        "ferias_vencidas": ferias_venc,
        "terco_ferias_vencidas": terco_venc,
        "ferias_proporcionais": ferias_prop,
        "terco_ferias_proporcionais": terco_prop,
        "decimo_terceiro_proporcional": decimo_terceiro,
        "avos_13": avos_13,
        "avos_ferias": avos_ferias,
        "multa_fgts": multa_fgts,
        "total_proventos": total_proventos,
        "total_indenizatorio_fgts": multa_fgts,
        "total_bruto": total_bruto,
        "inss": inss,
        "irrf": irrf,
        "total_descontos": total_descontos,
        "total_liquido": total_liquido,
        "anos_servico": anos_servico,
        "tipo_rescisao": tipo_rescisao,
    }
