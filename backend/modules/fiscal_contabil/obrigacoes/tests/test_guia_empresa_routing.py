from modules.fiscal_contabil.obrigacoes.guias_drive_service import _empresa_por_cnpj

ELET = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
PATR = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"


def test_reconhece_patrimonial_formatado():
    assert _empresa_por_cnpj("... CNPJ 66.014.833/0001-10 ...") == PATR


def test_reconhece_patrimonial_so_digitos():
    assert _empresa_por_cnpj("inscricao 66014833000110 competencia") == PATR


def test_reconhece_eletronica():
    assert _empresa_por_cnpj("CNPJ: 35.710.481/0001-03") == ELET


def test_default_eletronica_quando_ausente():
    assert _empresa_por_cnpj("nenhum cnpj aqui") == ELET
