"""VERDADES DE DOMÍNIO — a tabela que um humano cura, e que o `checar_dominio` confere.

Erro de domínio não tem trava por definição: alíquota errada com fonte certa passa em tudo,
"ali só quem entende do assunto olhando". O que dá para mecanizar é o passo seguinte: quem
entende olha UMA vez, escreve aqui o valor, a fonte e até quando vale — e a trava confere
todo dia que (1) o código diz o mesmo, (2) a mesma verdade não aparece com dois valores em
dois arquivos, e (3) a vigência não venceu.

O caso que motivou (06/09/2026): `FAIXAS_INSS_2026` existe em `people_management/folha/
services/calculo_service.py` com a tabela de 2026 (1.621 · 2.902,84 · 4.354,27 · 8.475,55) e
em `government_integrations/services/fgts_inss_service.py` com a de 2024 (1.412 · 2.666,68 ·
4.000,03 · 7.786,02) — mesmo nome, ano diferente, ninguém viu.

Cada verdade: chave · valores (na ordem em que aparecem no código) · fonte · vigente_ate ·
medido_em · onde = [(arquivo relativo a backend/, NOME_DA_CONSTANTE)] · opcionalmente
`banco` = SQL cujo escalar tem que bater com o primeiro valor (verdade ancorada no banco).

⚠️ Este arquivo é CURADO. Mudar um valor aqui é afirmar que a lei mudou — cite a fonte.
"""
from __future__ import annotations

VERDADES: list[dict] = [
    {
        "chave": "salario_minimo_2026",
        "valores": ["1621.00"],
        "fonte": "Portaria Interministerial MPS/MF nº 13/2026 (citada no código)",
        "vigente_ate": "2026-12-31", "medido_em": "2026-09-06",
        "onde": [("modules/people_management/common/utils/clt_calculator.py", "SALARIO_MINIMO")],
    },
    {
        "chave": "teto_salario_contribuicao_inss_2026",
        "valores": ["8475.55"],
        "fonte": "Portaria Interministerial MPS/MF nº 13/2026",
        "vigente_ate": "2026-12-31", "medido_em": "2026-09-06",
        "onde": [("modules/people_management/common/utils/clt_calculator.py", "TETO_INSS")],
    },
    {
        "chave": "faixas_inss_2026",
        "valores": ["1621.00", "0.075", "2902.84", "0.09", "4354.27", "0.12", "8475.55", "0.14"],
        "fonte": "Portaria Interministerial MPS/MF nº 13/2026",
        "vigente_ate": "2026-12-31", "medido_em": "2026-09-06",
        "onde": [
            ("modules/people_management/folha/services/calculo_service.py", "FAIXAS_INSS_2026"),
            # government_integrations/services/fgts_inss_service.py tinha a tabela de 2024 sob
            # este nome (achado de 06/09/2026); passou a DERIVAR da folha — uma fonte só.
        ],
    },
    {
        "chave": "faixas_irrf_2026",
        "valores": ["2428.80", "0", "0", "2826.65", "0.075", "182.16", "3751.05", "0.15", "394.16",
                    "4664.68", "0.225", "675.49", "99999999", "0.275", "908.73"],
        "fonte": "Lei 15.191/2025 (tabela progressiva mensal; citada no código, IRRF_CERTIFICADA=False)",
        "vigente_ate": "2026-12-31", "medido_em": "2026-09-06",
        "onde": [("modules/people_management/folha/services/calculo_service.py", "FAIXAS_IRRF_2026")],
    },
    {
        "chave": "aliquota_fgts",
        "valores": ["0.08"],
        "fonte": "Lei 8.036/1990, art. 15",
        "vigente_ate": "2027-12-31", "medido_em": "2026-09-06",
        "onde": [
            ("modules/government_integrations/core/fgts_digital.py", "ALIQUOTA_FGTS"),
            ("modules/government_integrations/services/fgts_inss_service.py", "ALIQUOTA_FGTS"),
        ],
    },
    {
        "chave": "piso_cct_menor_cargo",
        "valores": ["1670.00"],
        "fonte": "cct_cargos (CCT SINDECOMPRESTS AM000613/2025) — ancorado no banco",
        "vigente_ate": "2026-12-31", "medido_em": "2026-09-06",
        "banco": "SELECT min(piso_salarial) FROM cct_cargos WHERE is_active",
        "onde": [
            ("modules/financial/controllers/custeio_controller.py", "PISO_CATEGORIA"),
            ("modules/financial/controllers/precificacao_controller.py", "PISO_CATEGORIA"),
        ],
    },
]
