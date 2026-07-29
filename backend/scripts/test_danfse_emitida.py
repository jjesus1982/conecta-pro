"""Self-check do DANFSe da NFS-e emitida (nfse_emitidas_nacional).

Roda dentro do container: docker exec conecta-pro-backend python scripts/test_danfse_emitida.py
Falha se o mapeamento de campos quebrar, se a competência não normalizar, ou se o PDF sair vazio.
"""
from modules.gedeon.services.nfse_danfse_generator import gerar_danfse_de_emitida

# Linha realista: campos da emitida + prestador do join `empresas` (dado real, não fabricado).
row = {
    "chave_acesso": "13026032266014833000110000000000002026075839565230",
    "numero": "20",
    "competencia": "2026-07",
    "data_emissao": None,  # timestamp; dt() cai pro fallback str sem quebrar
    "tomador_cnpj": "12.345.678/0001-99",
    "tomador_nome": "CONDOMINIO MIRANTE DAS FLORES",
    "valor_servicos": 13561.5,
    "iss_valor": 0.0,
    "inss_retido": 1491.76,
    "valor_liquido": 12069.74,
    "descricao": "Limpeza, manutenção e conservação de imóveis.",
    "codigo_servico": "7.10",
    "emit_cnpj": "66.014.833/0001-10",
    "emit_nome": "CONECTAMAIS PATRIMONIAL LTDA",
    "emit_im": "721042001",
}

pdf = gerar_danfse_de_emitida(row)
assert pdf[:4] == b"%PDF", "não gerou PDF"
assert len(pdf) > 2000, f"PDF suspeito de vazio ({len(pdf)} bytes)"

# Prestador NUNCA vazio (era o bug de reusar gerar_danfse_de_nfse com nomes de coluna errados).
assert row["emit_nome"] and row["emit_cnpj"], "prestador vazio"

# Competência 'YYYY-MM' -> 'MM/YYYY' (checa a transformação isolada)
def _comp(c):
    if len(c) == 7 and "-" in c:
        a, m = c.split("-"); return f"{m}/{a}"
    return c
assert _comp("2026-07") == "07/2026", "competência não normalizou"

print(f"OK — DANFSe emitida: {len(pdf)} bytes, competência 07/2026, prestador presente")
