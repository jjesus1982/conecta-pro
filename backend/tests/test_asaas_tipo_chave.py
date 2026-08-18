"""O tipo da chave PIX decide quem recebe. Uma chave de telefone com 11 dígitos
"parece" um CPF; se a Asaas adivinhar errado, o dinheiro vai para outra pessoa.

Este teste existe porque a primeira versão do adapter nem mandava o campo.
"""
import pathlib
import sys

# `tests/modules/` TEM `__init__.py` (pacote regular) e `modules/` não (namespace).
# Pacote regular sempre vence o namespace, em qualquer ordem de `sys.path` — então
# adiantar a raiz não resolve: é preciso TIRAR `tests/` do caminho. Ao rodar o arquivo
# direto, `sys.path[0]` é a pasta dele; trocamos por a raiz do backend.
sys.path[0] = str(pathlib.Path(__file__).resolve().parents[1])

from modules.integrations.banking.adapters.asaas import AsaasAdapter as A  # noqa: E402


def test_tipo_de_chave():
    casos = [
        # chaves reais de diaristas nossos (formato, não os valores de produção)
        ("+5592985847540", "PHONE"),   # MAIARA — telefone com +55
        ("5592992717319", "PHONE"),    # telefone sem o +, 13 dígitos
        ("78282705268", "CPF"),        # ANDREA — CPF puro
        ("035.275.542-38", "CPF"),     # CPF pontuado
        ("66014833000110", "CNPJ"),    # Patrimonial
        ("mauricio@gmail.com", "EMAIL"),
        ("a1b2c3d4-e5f6-7890-abcd-ef1234567890", "EVP"),  # aleatória
    ]
    for chave, esperado in casos:
        assert A.tipo_de_chave(chave) == esperado, f"{chave} -> {A.tipo_de_chave(chave)}"

    # o caso que motiva o teste: 11 dígitos é CPF, 13 é telefone.
    assert A.tipo_de_chave("92992717319") == "CPF"      # 11 -> CPF
    assert A.tipo_de_chave("5592992717319") == "PHONE"  # 13 -> telefone


if __name__ == "__main__":
    test_tipo_de_chave()
    print("ok")
