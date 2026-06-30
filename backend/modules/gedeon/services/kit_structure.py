"""
GEDEON — Estrutura canônica do kit documental no Google Drive.

Define as subpastas (categorias) de cada kit de condomínio/mês e quais tipos de
documento (slug de kit_documental_templates) pertencem a cada uma. GEDEON cria
sempre esta mesma estrutura organizada e arquiva cada documento na subpasta certa.
"""

from __future__ import annotations

# Ordem = ordem das subpastas no Drive. (rótulo_pasta, [slugs])
KIT_CATEGORIAS: list[tuple[str, list[str]]] = [
    ("01 - Faturamento", ["nfse", "boleto"]),
    ("02 - Folha de Pagamento", ["folha_pagamento", "contracheque", "comp_salario_individual"]),
    (
        "03 - Benefícios (VA/VT)",
        ["comp_va_solides", "comp_vt_individual", "comp_vt_va_combinado", "recibo_vt_va", "relatorio_pedido_va"],
    ),
    ("04 - Ponto", ["folhas_ponto"]),
    ("05 - Documentos Trabalhistas", ["contrato_trabalho", "ficha_empregado", "aso"]),
    (
        "06 - Tributário (FGTS/INSS/DCTFWeb)",
        [
            "gfd_fgts_mensal",
            "relatorio_gfd_fgts",
            "comp_pag_fgts",
            "dctfweb_declaracao",
            "dctfweb_extrato",
            "dctfweb_recibo",
            "inss_mensal",
        ],
    ),
    ("07 - Certidões (CNDs)", ["cnd_sefaz", "cnd_caixa", "cnd_trabalhista", "cnd_prefeitura", "cnd_rfb"]),
    (
        "08 - Rescisões e Férias",
        [
            "rescisao_contrato",
            "comp_rescisao",
            "comp_fgts_rescisao",
            "gfd_fgts_rescisao",
            "relatorio_gfd_rescisao",
            "aviso_previo_ferias",
            "recibo_ferias",
        ],
    ),
]

# slug -> rótulo da subpasta (pra arquivar cada doc na pasta certa)
SLUG_PARA_CATEGORIA: dict[str, str] = {slug: label for label, slugs in KIT_CATEGORIAS for slug in slugs}


def categoria_de(slug: str) -> str:
    """Rótulo da subpasta onde o documento daquele slug deve ser arquivado."""
    return SLUG_PARA_CATEGORIA.get(slug, "09 - Outros / A Classificar")
