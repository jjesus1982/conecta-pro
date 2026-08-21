"""O decodificador de boleto decide se algo vira DÍVIDA. Se ele aceitar lixo, o sistema
inventa obrigação; se recusar boleto bom, o radar fica cego.

Os casos são REAIS: boletos da Full Telecom pagos em 19/08/2026, cujos valores e
vencimentos foram confirmados contra a API do Inter.
"""
import pathlib
import sys
from datetime import date

sys.path[0] = str(pathlib.Path(__file__).resolve().parents[1])

from modules.financial.services.boleto_codigo import (  # noqa: E402
    achar_boletos,
    decodificar,
)

HOJE = date(2026, 8, 19)


def test_boletos_reais_full_telecom():
    # Código de barras (44) — os três títulos distintos confirmados no Inter.
    casos = [
        ("03393154400000149009039976000000006599080101", 149.00, date(2026, 8, 20)),
        ("03395151300000149009039976000000006575140101", 149.00, date(2026, 7, 20)),
        ("03391154400000149009039976000000006599670101", 149.00, date(2026, 8, 20)),
    ]
    for barras, valor, venc in casos:
        r = decodificar(barras, HOJE)
        assert r, f"recusou boleto real: {barras}"
        assert r["valor"] == valor, f"{barras}: valor {r['valor']} != {valor}"
        assert r["vencimento"] == venc, f"{barras}: venc {r['vencimento']} != {venc}"
        assert r["banco"] == "033"       # Santander, o emissor da Full

    # Linha digitável (47) do boleto de julho — tem de dar no MESMO código de barras.
    linha = "03399039997600000000065751401012515130000014900"
    r = decodificar(linha, HOJE)
    assert r, "recusou a linha digitável real"
    assert r["valor"] == 149.00
    assert r["vencimento"] == date(2026, 7, 20)
    assert r["barras"] == "03395151300000149009039976000000006575140101"


def test_recusa_o_que_nao_e_boleto():
    """O caso que motiva o validador: PDF é cheio de número longo."""
    nao_sao = [
        "35240612345678000199550010000012341234567890",   # chave de NFS-e (44 dígitos)
        "1" * 47,                                          # sequência inventada
        "66014833000110",                                  # CNPJ
        "03399039997600000000065751401012515130000014901",  # linha real com 1 dígito trocado
    ]
    for x in nao_sao:
        assert decodificar(x, HOJE) is None, f"aceitou o que não é boleto: {x[:20]}"


def test_acha_no_meio_do_texto():
    """Como vem num PDF de verdade: rótulo, espaços e outros números em volta."""
    texto = (
        "FULL TELECOM LTDA  CNPJ 28.042.482/0001-61\n"
        "Contrato 00360305   Nosso numero 6575140\n"
        "Linha digitavel: 03399.03999 76000.000000 65751.401012 5 15130000014900\n"
        "Valor: R$ 149,00\n"
    )
    achados = achar_boletos(texto, HOJE)
    assert len(achados) == 1, f"esperado 1 boleto, veio {len(achados)}"
    assert achados[0]["valor"] == 149.00
    assert achados[0]["vencimento"] == date(2026, 7, 20)


if __name__ == "__main__":
    test_boletos_reais_full_telecom()
    test_recusa_o_que_nao_e_boleto()
    test_acha_no_meio_do_texto()
    print("ok")
