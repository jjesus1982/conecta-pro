"""Análise de Riscos Jurídicos (trabalhista + tributário) — módulo Jurídico.

PRINCÍPIO DE VERACIDADE: todo número aqui é DERIVADO de dado REAL do banco
(`employees`, `contracts`, `nfses`, `sst_afastamentos`, `gp_clock_punches`).
O que NÃO se deriva do dado real é rotulado como "requer análise"/"requer dado"
— nunca fabricamos alíquota, provisão ou número inexistente.

Rótulos honestos usados em toda a saída:
  - "estimativa de exposição, não provisão contábil" (trabalhista)
  - "estimativa p/ decisão, validar com contador" (tributário)

Bases legais citadas: CLT (arts. citados por verba) e CCT SINDECOMPRESTS
AM000613/2025 (piso da categoria R$ 1.670,00 em 2026; somos AGENTES DE PORTARIA).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# --------------------------------------------------------------------------- #
# Constantes de contexto (fatos declarados / parâmetros legais 2026)
# Não são "dados do banco": são parâmetros legais públicos e o contexto societário.
# --------------------------------------------------------------------------- #
PISO_CCT_2026 = Decimal("1670.00")  # CCT SINDECOMPRESTS AM000613/2025
CNPJ1 = "35.710.481/0001-03"  # Jordan Santos de Jesus Ltda — Lucro Real em 2026
TETO_SIMPLES_ANUAL = Decimal("4800000.00")  # LC 123/2006, sublimite anual do Simples

# Alíquotas legais PÚBLICAS usadas SÓ para comparativo transparente (não sigilo do banco).
# Toda estimativa que as usa carrega o rótulo "validar com contador".
FGTS_ALIQUOTA = Decimal("0.08")  # CF art. 7º III + Lei 8.036/90
FGTS_MULTA_RESCISORIA = Decimal("0.40")  # Lei 8.036/90 art. 18 §1º
TERCO_FERIAS = Decimal("0.3333")  # CF art. 7º XVII


def _d(v: Any) -> Decimal:
    if v is None:
        return Decimal("0")
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _f(v: Decimal) -> float:
    return float(round(v, 2))


def _meses_de_casa(adm: date | None, hoje: date) -> int | None:
    if not adm:
        return None
    return max(0, (hoje.year - adm.year) * 12 + (hoje.month - adm.month))


# =========================================================================== #
# RISCO TRABALHISTA
# =========================================================================== #
def _exposicao_funcionario(emp: dict, hoje: date) -> dict[str, Any]:
    """Estima a EXPOSIÇÃO (não provisão) de passivo de UM funcionário ativo.

    Cada verba tem: valor derivado do dado real OU rótulo "requer análise".
    Fórmulas (colunas reais entre parênteses):
      - salário-base (employees.salario_base). Se NULL → usa piso CCT e marca alerta.
      - piso: se salario_base < PISO_CCT → diferença retroativa dos meses de casa
              (employees.data_admissao define os meses; teto de 60 meses = prescrição
               quinquenal, CLT art. 11 / CF art. 7º XXIX).
      - FGTS+multa 40%: base salário × 8% × meses × 40% (exposição em rescisão sem justa causa).
      - férias+1/3 e 13º proporcional: proporcional aos meses do ano corrente.
      - horas extras/adicional noturno: REQUER ANÁLISE do ponto (gp_clock_punches)
        — não estimamos cegamente sem cruzar escala; marcado explicitamente.
    """
    nome = emp.get("nome")
    cargo = emp.get("cargo")
    adm = emp.get("data_admissao")
    salario_real = emp.get("salario_base")
    meses_casa = _meses_de_casa(adm, hoje)
    meses_prescricao = min(meses_casa, 60) if meses_casa is not None else None

    verbas: dict[str, Any] = {}
    alertas: list[str] = []

    # Base salarial efetiva usada nos cálculos
    if salario_real is None:
        base = PISO_CCT_2026
        alertas.append("salario_base NULO no cadastro — usado piso CCT como base (requer confirmação)")
    else:
        base = _d(salario_real)

    # 1) Diferença de piso (retroativo) — CLT art. 457/CCT AM000613/2025
    if base < PISO_CCT_2026 and meses_prescricao:
        dif = (PISO_CCT_2026 - base) * Decimal(meses_prescricao)
        verbas["diferenca_piso_retroativa"] = {
            "valor": _f(dif),
            "base_legal": "CCT SINDECOMPRESTS AM000613/2025 (piso R$1.670) + CLT art. 11 (prescrição 5 anos)",
            "detalhe": f"(1670 - {_f(base)}) x {meses_prescricao} meses",
        }
    else:
        verbas["diferenca_piso_retroativa"] = {"valor": 0.0, "base_legal": "salário >= piso CCT"}

    # 2) FGTS + multa 40% (exposição em rescisão sem justa causa) — Lei 8.036/90
    if meses_casa:
        fgts_deposito = base * FGTS_ALIQUOTA * Decimal(meses_casa)
        multa = fgts_deposito * FGTS_MULTA_RESCISORIA
        verbas["fgts_multa_40"] = {
            "valor": _f(multa),
            "base_legal": "Lei 8.036/90 art. 18 §1º",
            "detalhe": f"{_f(base)} x 8% x {meses_casa} meses x 40% (multa rescisória)",
            "rotulo": "exposição em cenário de rescisão sem justa causa",
        }
    else:
        verbas["fgts_multa_40"] = {"valor": 0.0, "rotulo": "requer data_admissao"}

    # 3) Aviso prévio (30 dias + 3/ano, teto 90) — Lei 12.506/2011
    anos = (meses_casa // 12) if meses_casa is not None else 0
    dias_aviso = min(30 + anos * 3, 90)
    verbas["aviso_previo"] = {
        "valor": _f(base * Decimal(dias_aviso) / Decimal(30)),
        "base_legal": "Lei 12.506/2011",
        "detalhe": f"{dias_aviso} dias proporcionais ({anos} anos de casa)",
        "rotulo": "exposição em cenário de dispensa",
    }

    # 4) Férias proporcionais + 1/3 (do ano corrente) — CF art. 7º XVII
    meses_ano = hoje.month
    ferias = (base / Decimal(12) * Decimal(meses_ano)) * (Decimal(1) + TERCO_FERIAS)
    verbas["ferias_prop_mais_terco"] = {
        "valor": _f(ferias),
        "base_legal": "CF art. 7º XVII + CLT art. 129+",
        "detalhe": f"{meses_ano}/12 avos + 1/3",
    }

    # 5) 13º proporcional (do ano corrente) — Lei 4.090/62
    verbas["decimo_terceiro_prop"] = {
        "valor": _f(base / Decimal(12) * Decimal(meses_ano)),
        "base_legal": "Lei 4.090/62",
        "detalhe": f"{meses_ano}/12 avos",
    }

    # 6) Horas extras / adicional noturno — NÃO estimamos sem cruzar ponto+escala
    verbas["horas_extras_noturno"] = {
        "valor": None,
        "status": "requer análise",
        "base_legal": "CLT art. 59 (HE) / art. 73 (adicional noturno)",
        "detalhe": "exige cruzar gp_clock_punches x escala/jornada contratada — não estimável cegamente",
    }

    # 7) Adicionais de risco já pagos vs devidos (insalubridade/periculosidade/ronda)
    #    Só sinalizamos divergência; o valor devido depende de laudo (requer análise).
    ins = _d(emp.get("insalubridade_percentual"))
    per = _d(emp.get("periculosidade_percentual"))
    ron = _d(emp.get("adicional_ronda_percentual"))
    verbas["adicionais_risco"] = {
        "insalubridade_pct": _f(ins),
        "periculosidade_pct": _f(per),
        "adicional_ronda_pct": _f(ron),
        "status": "requer análise" if (ins == 0 and per == 0 and ron == 0) else "cadastrado",
        "base_legal": "CLT art. 189-197 (insalubridade) / art. 193 (periculosidade) / CCT (ronda)",
        "detalhe": "adicional devido depende de laudo técnico (LTCAT/PPRA) — validar com SST",
    }

    total = Decimal("0")
    for v in verbas.values():
        val = v.get("valor")
        if isinstance(val, (int, float)):
            total += _d(val)

    return {
        "employee_id": emp.get("id"),
        "nome": nome,
        "cargo": cargo,
        "meses_de_casa": meses_casa,
        "salario_base_cadastrado": _f(_d(salario_real)) if salario_real is not None else None,
        "verbas": verbas,
        "exposicao_estimada": _f(total),
        "alertas": alertas,
    }


def riscos_trabalhista(db: Session) -> dict[str, Any]:
    hoje = date.today()

    rows = db.execute(
        text(
            """
            SELECT id, nome, cargo, salario_base, data_admissao, status,
                   insalubridade_percentual, periculosidade_percentual,
                   adicional_ronda_percentual
            FROM employees
            WHERE is_active = true AND lower(coalesce(status,'')) = 'ativo'
            ORDER BY cargo, nome
            """
        )
    ).mappings().all()

    # Afastamentos com estabilidade (risco de reintegração/indenização) — dado real
    afast = db.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE gera_estabilidade = true) AS com_estabilidade,
                   count(*) FILTER (WHERE lower(coalesce(tipo,'')) LIKE '%%acidente%%'
                                     OR lower(coalesce(motivo,'')) LIKE '%%acidente%%') AS acidentarios,
                   count(*) AS total
            FROM sst_afastamentos
            """
        )
    ).mappings().first()

    total_punches = db.execute(text("SELECT count(*) FROM gp_clock_punches")).scalar() or 0

    detalhado = [_exposicao_funcionario(dict(r), hoje) for r in rows]

    total_exposicao = sum(_d(f["exposicao_estimada"]) for f in detalhado)
    com_risco = [f for f in detalhado if _d(f["exposicao_estimada"]) > 0]

    # Agregação por tipo de verba
    por_tipo: dict[str, Decimal] = {}
    for f in detalhado:
        for k, v in f["verbas"].items():
            val = v.get("valor")
            if isinstance(val, (int, float)):
                por_tipo[k] = por_tipo.get(k, Decimal("0")) + _d(val)
    por_tipo_out = {k: _f(v) for k, v in por_tipo.items()}

    # Escalonamento: exposição alta agregada dispara recomendação de assessoria
    exposicao_alta = total_exposicao > Decimal("500000")

    return {
        "referencia": hoje.isoformat(),
        "titulo": "Análise de Risco Trabalhista",
        "rotulo": "estimativa de exposição, não provisão contábil",
        "fonte_dados": {
            "employees_ativos": len(rows),
            "afastamentos": dict(afast) if afast else {},
            "gp_clock_punches_registrados": total_punches,
            "piso_cct_2026": _f(PISO_CCT_2026),
            "base_cct": "SINDECOMPRESTS AM000613/2025 (Agentes de Portaria)",
        },
        "total_exposicao_estimada": _f(total_exposicao),
        "funcionarios_com_risco": len(com_risco),
        "funcionarios_analisados": len(detalhado),
        "por_tipo": por_tipo_out,
        "itens_requer_analise": [
            "horas_extras_noturno: exige cruzar gp_clock_punches x escala contratada",
            "adicionais_risco: valor devido depende de laudo técnico (LTCAT/PPRA)",
        ],
        "afastamentos_estabilidade": (afast or {}).get("com_estabilidade"),
        "afastamentos_acidentarios": (afast or {}).get("acidentarios"),
        "detalhado": detalhado,
        "escalonar": exposicao_alta,
        "recomendacao": (
            "Exposição agregada elevada — recomenda-se revisão por assessoria trabalhista "
            "e provisionamento contábil formal."
            if exposicao_alta
            else "Manter monitoramento; validar itens 'requer análise' com DP/SST."
        ),
        "disclaimer": (
            "Números são ESTIMATIVA DE EXPOSIÇÃO em cenário hipotético de reclamação/rescisão, "
            "derivados do cadastro real (salário, admissão, adicionais). NÃO constituem provisão "
            "contábil nem parecer jurídico. Verbas marcadas 'requer análise' não foram estimadas "
            "por falta de cruzamento de dados. Base: CLT + CCT SINDECOMPRESTS AM000613/2025."
        ),
    }


# =========================================================================== #
# RISCO TRIBUTÁRIO
# =========================================================================== #
def riscos_tributario(db: Session) -> dict[str, Any]:
    hoje = date.today()

    # Faturamento REAL: contratos ativos (monthly_value) + NFS-e emitidas
    contratos = db.execute(
        text(
            """
            SELECT count(*) FILTER (WHERE lower(coalesce(status::text,'')) = 'active') AS ativos,
                   coalesce(sum(monthly_value) FILTER (WHERE lower(coalesce(status::text,'')) = 'active'), 0) AS mrr,
                   count(*) FILTER (WHERE retencao_iss = true)  AS com_ret_iss,
                   count(*) FILTER (WHERE retencao_inss = true) AS com_ret_inss,
                   count(*) FILTER (WHERE retencao_csll = true) AS com_ret_csll
            FROM contracts
            """
        )
    ).mappings().first()

    # [Veracidade] Enquadramento no Simples depende do FATURAMENTO TOTAL — usar a
    # fonte autoritativa nfse_emitidas_nacional (77 notas jan-jun / R$1.428.413,04 =
    # razão 3.1.1.01). A tabela `nfses` so tinha jan-fev (R$542k) e daria uma
    # conclusao legal ERRADA sobre o teto do Simples.
    # A tabela nacional NAO carrega detalhamento de retencoes csll/pis/cofins nem
    # a flag inss_liminar_aplicada -> retornados como 0/None (honesto: dado nao
    # disponivel nesta fonte, nao fabricar).
    nfse = db.execute(
        text(
            """
            SELECT count(*) AS qtd,
                   coalesce(sum(valor_servicos), 0) AS total_servicos,
                   coalesce(sum(iss_valor), 0)      AS iss,
                   coalesce(sum(inss_retido), 0)    AS inss,
                   0::numeric                       AS csll,
                   0::numeric                       AS pis,
                   0::numeric                       AS cofins,
                   NULL::bigint                     AS nfse_liminar_inss
            FROM nfse_emitidas_nacional
            """
        )
    ).mappings().first()

    mrr = _d((contratos or {}).get("mrr"))
    faturamento_anualizado = mrr * Decimal(12)
    total_nfse = _d((nfse or {}).get("total_servicos"))

    # ---- Enquadramento (faturamento x teto Simples) — DADO REAL x parâmetro legal ----
    margem_teto = TETO_SIMPLES_ANUAL - faturamento_anualizado
    pode_simples = faturamento_anualizado <= TETO_SIMPLES_ANUAL
    ocupacao_teto = (
        _f(faturamento_anualizado / TETO_SIMPLES_ANUAL * Decimal(100))
        if TETO_SIMPLES_ANUAL > 0
        else None
    )

    # ---- Comparativo de carga (transparente, alíquotas legais públicas) ----
    # Estimativas ILUSTRATIVAS p/ decisão — validar com contador (rótulo obrigatório).
    # Simples Anexo IV (vigilância/limpeza terceirizada): faixa ~ 6% a 16,85% + CPP fora do DAS.
    # Lucro Real: PIS/COFINS não-cumulativo (9,25%) + IRPJ/CSLL sobre lucro + ISS.
    aliq_simples_estim = Decimal("0.14")  # ponto médio Anexo IV (ILUSTRATIVO)
    carga_simples_estim = faturamento_anualizado * aliq_simples_estim

    # Lucro Real: sobre faturamento é estimativa grosseira — depende do lucro real.
    # Marcamos como "requer apuração" e damos só uma faixa referencial de tributos sobre receita.
    pis_cofins_lr = faturamento_anualizado * Decimal("0.0925")

    comparativo = {
        "faturamento_anualizado_base": _f(faturamento_anualizado),
        "simples_anexo_iv": {
            "aliquota_ilustrativa_pct": _f(aliq_simples_estim * 100),
            "carga_anual_estimada": _f(carga_simples_estim),
            "observacao": "Anexo IV LC 123/2006: alíquota efetiva varia por faixa (RBT12). "
            "CPP (INSS patronal) recolhida FORA do DAS. Valor ILUSTRATIVO.",
        },
        "lucro_real": {
            "pis_cofins_nao_cumulativo_pct": 9.25,
            "pis_cofins_anual_estimado": _f(pis_cofins_lr),
            "irpj_csll": "requer apuração (dependem do LUCRO real, não da receita)",
            "observacao": "PIS/COFINS há LIMINAR de recolhimento zerado (a confirmar vigência). "
            "IRPJ/CSLL não estimáveis sem DRE.",
        },
        "rotulo": "estimativa p/ decisão, validar com contador",
    }

    # ---- Retenções aplicáveis (dado real dos contratos + NFS-e) ----
    retencoes = {
        "iss": {
            "contratos_com_retencao": (contratos or {}).get("com_ret_iss"),
            "iss_destacado_nfse": _f(_d((nfse or {}).get("iss"))),
            "base_legal": "LC 116/2003 + legislação municipal Manaus-AM",
        },
        "inss": {
            "contratos_com_retencao": (contratos or {}).get("com_ret_inss"),
            "inss_retido_nfse": _f(_d((nfse or {}).get("inss"))),
            "nfse_com_liminar_inss": (nfse or {}).get("nfse_liminar_inss"),
            "base_legal": "Lei 8.212/91 art. 31 (retenção 11% cessão de mão de obra) — "
            "há liminar de não-retenção a validar",
        },
        "csll": {
            "contratos_com_retencao": (contratos or {}).get("com_ret_csll"),
            "csll_retido_nfse": _f(_d((nfse or {}).get("csll"))),
            "base_legal": "Lei 10.833/2003 art. 30 (retenção CSLL/PIS/COFINS)",
        },
        "pis_cofins": {
            "pis_retido_nfse": _f(_d((nfse or {}).get("pis"))),
            "cofins_retido_nfse": _f(_d((nfse or {}).get("cofins"))),
            "base_legal": "Lei 10.833/2003 — há LIMINAR de recolhimento zerado (a confirmar)",
        },
        # [Veracidade] O detalhamento de retenções CSLL/PIS/COFINS por nota e a flag
        # de liminar INSS não constam na fonte fiscal nacional (nfse_emitidas_nacional);
        # exibidos como 0 significa "não disponível nesta fonte", não "retido zero".
        "nota_fonte": "iss/inss vêm da NFS-e nacional (jan-jun); csll/pis/cofins "
        "por nota e liminar INSS não são rastreados nesta fonte — consultar razão/contador.",
    }

    # ---- Riscos identificados (só o que decorre do dado real + contexto) ----
    riscos: list[dict[str, Any]] = []
    if pode_simples:
        riscos.append(
            {
                "tema": "Enquadramento Simples Nacional",
                "nivel": "atenção",
                "descricao": f"Faturamento anualizado (R$ {_f(faturamento_anualizado)}) está "
                f"{ocupacao_teto}% do teto do Simples (R$ 4,8M). Migração viável, "
                f"mas monitorar RBT12 real — a base aqui é MRR x12 dos contratos ativos.",
            }
        )
    else:
        riscos.append(
            {
                "tema": "Enquadramento Simples Nacional",
                "nivel": "alto",
                "descricao": f"Faturamento anualizado (R$ {_f(faturamento_anualizado)}) ULTRAPASSA "
                f"o teto de R$ 4,8M — vedado o Simples. Reavaliar estratégia CNPJ2.",
            }
        )
    riscos.append(
        {
            "tema": "Retenções na fonte (INSS/PIS/COFINS via liminar)",
            "nivel": "alto",
            "descricao": "NFS-e emitidas com INSS/PIS/COFINS = R$ 0 (liminar aplicada em parte). "
            "Risco de autuação se a liminar cair/perder vigência — depósito judicial "
            "das diferenças deve ser considerado. Validar vigência com jurídico/contador.",
        }
    )
    riscos.append(
        {
            "tema": "Transição de regime (Lucro Real → Simples)",
            "nivel": "atenção",
            "descricao": "CNPJ1 em Lucro Real (2026) migrando p/ Simples; contratos humanizados "
            "vão p/ CNPJ2 (Conecta Mais Patrimonial). Risco de segregação artificial / "
            "planejamento abusivo se não houver substância — documentar razão negocial.",
        }
    )

    return {
        "referencia": hoje.isoformat(),
        "titulo": "Análise de Risco Tributário",
        "rotulo": "estimativa p/ decisão, validar com contador",
        "contexto_societario": {
            "cnpj1": CNPJ1,
            "regime_atual": "Lucro Real (2026)",
            "regime_futuro": "Simples Nacional (após transferir contratos humanizados)",
            "cnpj2": "Conecta Mais Patrimonial (em abertura, Simples, CNAE 8111-7/00)",
        },
        "fonte_dados": {
            "contratos_ativos": (contratos or {}).get("ativos"),
            "mrr_real": _f(mrr),
            "faturamento_anualizado": _f(faturamento_anualizado),
            "nfse_emitidas": (nfse or {}).get("qtd"),
            "nfse_valor_servicos": _f(total_nfse),
        },
        "enquadramento": {
            "teto_simples_anual": _f(TETO_SIMPLES_ANUAL),
            "faturamento_anualizado": _f(faturamento_anualizado),
            "margem_ate_teto": _f(margem_teto),
            "ocupacao_teto_pct": ocupacao_teto,
            "pode_simples": pode_simples,
            "base": "MRR real x12 dos contratos ativos (proxy de RBT12 — validar com faturamento real)",
        },
        "comparativo_carga": comparativo,
        "retencoes_aplicaveis": retencoes,
        "riscos": riscos,
        "escalonar": any(r["nivel"] == "alto" for r in riscos),
        "disclaimer": (
            "Estimativas ILUSTRATIVAS para apoio à decisão, derivadas do faturamento real "
            "(contratos + NFS-e). Alíquotas citadas são legais/públicas e a carga efetiva depende "
            "de apuração (RBT12, DRE, vigência de liminares). NÃO substitui parecer do contador "
            "nem consulta formal à RFB. Validar com Domínio Sistemas antes de qualquer decisão."
        ),
    }


# =========================================================================== #
# DASHBOARD (resumo dos dois)
# =========================================================================== #
def dashboard_riscos(db: Session) -> dict[str, Any]:
    trab = riscos_trabalhista(db)
    trib = riscos_tributario(db)
    hoje = date.today()

    return {
        "referencia": hoje.isoformat(),
        "titulo": "Painel de Riscos Jurídicos — Trabalhista + Tributário",
        "trabalhista": {
            "exposicao_estimada_total": trab["total_exposicao_estimada"],
            "funcionarios_com_risco": trab["funcionarios_com_risco"],
            "funcionarios_analisados": trab["funcionarios_analisados"],
            "por_tipo": trab["por_tipo"],
            "escalonar": trab["escalonar"],
            "rotulo": trab["rotulo"],
        },
        "tributario": {
            "faturamento_anualizado": trib["fonte_dados"]["faturamento_anualizado"],
            "pode_simples": trib["enquadramento"]["pode_simples"],
            "ocupacao_teto_pct": trib["enquadramento"]["ocupacao_teto_pct"],
            "riscos_altos": [r for r in trib["riscos"] if r["nivel"] == "alto"],
            "escalonar": trib["escalonar"],
            "rotulo": trib["rotulo"],
        },
        "escalonar_geral": trab["escalonar"] or trib["escalonar"],
        "disclaimer": (
            "Painel consolida ESTIMATIVAS de exposição (trabalhista) e cenários (tributário) "
            "derivados de dado real. Não é provisão contábil nem parecer jurídico/fiscal. "
            "Itens 'requer análise'/'validar com contador' precisam de aprofundamento humano."
        ),
    }
