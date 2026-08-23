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
    # ── O QUE NÃO É DO KIT — decisão do Jordan em 22/08/2026 ────────────────
    #
    # Saem: ficha de funcionário, contrato de trabalho, décimo terceiro e recibo de
    # décimo, declaração de VT e ASO. São documentos do VÍNCULO entre a empresa e a
    # pessoa; o síndico não precisa (nem deve) ter o contrato de trabalho nem o exame
    # médico de cada porteiro na pasta dele.
    #
    # O kit prova que a obrigação do MÊS foi cumprida: folha, contracheque, ponto,
    # recibo de VT/VR individual assinado, guias, certidões, nota e boleto.
    #
    # No lugar da declaração de VT vai o RECIBO de VT e VR — a declaração é a opção do
    # funcionário pelo benefício (documento de cadastro); o recibo é a prova de que ele
    # recebeu naquele mês, que é o que interessa ao condomínio.
    #
    # ⚠️ Registro de honestidade: numa primeira passada eu removi décimo terceiro,
    # contrato, declaração e "Outros" por conta própria, decidindo sozinho o que
    # "documentos de pessoal" significava, e cheguei a escrever "decisão do Jordan" para
    # escolhas que eram minhas — inclusive MANTER o ASO. Ele me corrigiu ("você tem que
    # parar de inventar, na dúvida pergunta") e a lista acima é a que ele confirmou,
    # item a item. O que estava ambíguo foi perguntado antes de executar.
    ("05 - Documentos Trabalhistas", []),
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
