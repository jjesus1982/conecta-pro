"""Um centavo nunca é adiantamento de salário.

🔴 MEDIDO EM 28/09/2026, achado pela PYETRA. Ela recebeu do sistema um documento assim:

    RECIBO DE PAGAMENTO · nº AD-202609-215 · 17/09/2026
    **R$ 0,01**
    «Recebi de CONECTAMAIS PATRIMONIAL LTDA, inscrita no CNPJ 66.014.833/0001-10, a importância
     de R$ 0,01, referente a adiantamento salarial de 40% da competência 09/2026, pago via PIX,
     **dando plena e geral quitação** quanto ao valor recebido.»

O valor certo, conferido no contracheque da própria pessoa: **R$ 668,00** — 40% de R$ 1.670,00.

Palavras dela: *"Comprovantes de pagamento de 40% — apenas o Ruan está com o valor, o resto são
os comprovantes de R$ 0,01."* Medido: **170 recibos e 170 comprovantes para 67 pessoas.**

## De onde veio o centavo

O extrato de setembro tem **104 lançamentos de R$ 0,01 entre 16 e 22/09** — os testes de chave
PIX da campanha das 66 pessoas — e **43 de R$ 668,00 em 22/09**, que são os adiantamentos reais.

`classificar_pagamento` decidia assim:

    if data_pg.month == ref.month and 14 <= data_pg.day <= 26:
        return "comprovante_pagamento", "Adiantamento 40%"

⭐ **Olhava DATA e TEXTO e nunca o VALOR** — num documento cujo propósito inteiro é o valor.
Todo centavo que caísse entre os dias 14 e 26 virava adiantamento de 40%. É a família de defeito
mais cara desta casa: a lógica estava certa e a OBSERVAÇÃO estava errada.

## O que este oráculo trava

1. **Centavo não vira remuneração** — nem adiantamento, nem folha, nem saldo.
2. **Valor real continua virando** — conserto que cala o verdadeiro junto com o falso é pior que
   o defeito. Afirma os dois lados.
3. **Sem valor, falha FECHADO** — o parâmetro é opcional para não quebrar chamador antigo, e
   esse opcional é a porta pela qual o defeito voltaria em silêncio.
4. **Os chamadores passam o valor.** Régua boa que ninguém alimenta é régua desligada — foi
   assim que 909 fotos ficaram invisíveis nesta casa.

⚠️ Afirma a REGRA: nenhum nome, id, data ou CNPJ. O piso vem da constante do próprio módulo,
então mexer nela sem pensar deixa o oráculo vermelho.
"""

import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from modules.people_management.ged.services import kit_eventos as ke  # noqa: E402

REF = date(2026, 9, 1)
#: Dia dentro da janela 14–26 que a régua antiga usava para chamar de "Adiantamento 40%".
DIA_NA_JANELA = date(2026, 9, 17)


def main() -> None:
    piso = float(ke.VALOR_MINIMO_REMUNERACAO)

    # 1 — abaixo do piso NUNCA é remuneração, mesmo caindo na janela do adiantamento
    for centavos in (0.01, 0.10, 1.00, piso - 0.01):
        _, rotulo = ke.classificar_pagamento(DIA_NA_JANELA, REF, "PIX ENVIADO", valor=centavos)
        assert "Adiantamento" not in rotulo and "Folha" not in rotulo and "Saldo" not in rotulo, (
            f"R$ {centavos:.2f} voltou a ser tratado como remuneração («{rotulo}») — "
            f"foi assim que 170 recibos de R$ 0,01 saíram com texto de quitação legal")

    # 2 — e o valor REAL continua sendo classificado. Conserto que cala o verdadeiro junto com
    #     o falso troca um defeito por outro.
    _, rotulo_real = ke.classificar_pagamento(DIA_NA_JANELA, REF, "PIX ENVIADO", valor=668.00)
    assert rotulo_real == "Adiantamento 40%", (
        f"o adiantamento real deixou de ser reconhecido («{rotulo_real}»)")

    # 3 — sem valor, falha FECHADO
    _, sem_valor = ke.classificar_pagamento(DIA_NA_JANELA, REF, "PIX ENVIADO", valor=None)
    assert "Adiantamento" not in sem_valor, (
        "sem valor informado a régua voltou a afirmar «Adiantamento 40%» — o desconhecido tem "
        "de falhar fechado, senão o opcional vira a porta de volta do defeito")

    # 4 — o texto ainda manda quando é VT/VR (benefício de valor baixo é legítimo)
    _, vt = ke.classificar_pagamento(DIA_NA_JANELA, REF, "VALE TRANSPORTE", valor=0.01)
    assert vt == "VT", f"a régua de texto (VT/VR) foi perdida: «{vt}»"

    # 5 — TODO chamador passa o valor. Régua que ninguém alimenta é régua desligada.
    fonte = ke.__file__.replace(".pyc", ".py")
    if os.path.exists(fonte):
        with open(fonte, encoding="utf-8") as fh:
            corpo = fh.read()
        chamadas = re.findall(r"classificar_pagamento\((?!\s*\n?\s*data_pg)[^)]*\)", corpo)
        sem_valor_ = [c for c in chamadas if "valor" not in c]
        assert not sem_valor_, (
            f"{len(sem_valor_)} chamada(s) de classificar_pagamento sem passar o valor: "
            f"{sem_valor_[0][:90]}")
        print(f"OK {len(chamadas)} chamada(s) no módulo, todas passando o valor")

    print(f"OK piso R$ {piso:.2f} · centavo não vira remuneração · "
          f"adiantamento real preservado · sem valor falha fechado · VT/VR pelo texto")
    print("TEST oraculo_recibo_nao_e_centavo PASS")


if __name__ == "__main__":
    main()
