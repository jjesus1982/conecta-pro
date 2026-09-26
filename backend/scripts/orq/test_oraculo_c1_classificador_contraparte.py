"""C1 — quem recebeu o dinheiro é a coluna da contraparte, não o CNPJ do banco na descrição.

Nasceu em 25/09/2026, do loop de contabilidade, rastreando R$ 74.544,49 parados em
«2.1.2.09 Tributos a Recolher - a identificar» — um passivo com 180 baixas e ZERO provisões.

O DEFEITO QUE ELE TRANCA

O extrato do Banco Inter descreve um PIX como `Pix enviado: "Cp :00360305-Fulano de Tal"`.
O `00360305` **não é o CNPJ de quem recebeu** — é o da Caixa Econômica Federal, o banco
DESTINO. O classificador lia esse fragmento como se fosse a contraparte e casava com a regra
`("00360305", "imposto", "Recolhimento FGTS — Caixa Econômica Federal")`. Resultado: **todo
funcionário com conta na Caixa teve o salário carimbado como recolhimento de FGTS**, e o
escriturador baixou esse "tributo" contra uma conta que nunca foi provisionada.

Medido em produção em 25/09/2026, sobre as 3.954 transações que trazem o padrão `Cp :`:
o fragmento coincide com o CNPJ da contraparte em **32**. Das 180 transações que formaram o
saldo de 2.1.2.09, **125 têm CPF de funcionário do cadastro** (R$ 43.176,57).

O QUE ELE AFIRMA

 (a) **CPF não recolhe tributo.** Nenhuma transação cuja contraparte é pessoa física pode
     sair classificada como `imposto`. O fisco não recebe por CPF. Esta é a guarda que
     impede o defeito de voltar por qualquer caminho — regra de CNPJ ou regex na descrição.

 (b) **O `Cp :` da descrição não decide nada.** Trocar o fragmento do banco na descrição, sem
     mexer na contraparte, não pode mudar a classificação. Provado por sabotagem: se mudar,
     o classificador voltou a ler o banco como se fosse a pessoa.

 (c) **A contraparte manda.** Duas transações com a MESMA descrição e contrapartes diferentes
     (uma CNPJ da Caixa, outra CPF) têm de sair em categorias diferentes. Se saírem iguais,
     a coluna `counterparty_document` está sendo ignorada.

 (d) **O CNPJ vem da coluna, e casa pela raiz.** Pagamento cuja contraparte é de fato a Caixa
     (CNPJ 00.360.305/…) continua sendo `imposto` — a correção não pode cegar o acerto.

 (e) **O razão de produção não contradiz (a).** Recontando as transações que hoje sustentam
     2.1.2.09 com o classificador vigente, nenhuma pessoa física sai como tributo.

VERMELHO ANTES: com o classificador de até 25/09/2026 — que fazia
`re.search(r"Cp\\s*:(\\d{8})", desc)` — (a), (b), (c) e (e) falham. (e) acusava 158 pessoas
físicas classificadas como tributo.
"""

from __future__ import annotations

import os
import sys

import psycopg2
import psycopg2.extras

#: CNPJ da Caixa Econômica Federal — contraparte legítima de recolhimento de FGTS.
CNPJ_CAIXA = "00360305000104"
#: CPF sintético, fora do cadastro: exercita a guarda sem depender de quem está contratado.
CPF_QUALQUER = "12345678909"
#: A descrição exata que o Inter escreve, com o CNPJ do banco destino embutido.
DESC_INTER = 'Pix enviado: "Cp :00360305-Fulano de Tal" — FGTS'


def main() -> int:
    from modules.financial.services.lucro_real_justificativa_service import (
        _classificar_tx,
        _cpfs_de_funcionarios,
        _so_digitos,
    )

    falhas: list[str] = []
    medidas: list[str] = []

    # (a) CPF nunca é imposto — varrendo toda descrição que o fisco reconheceria
    tributarias = [
        'Pix enviado: "Cp :00360305-Fulano" — FGTS',
        "DARF pago",
        "INSS competencia 08",
        "Recolhimento GPS ",
        "simples nacional",
        "receita federal",
    ]
    vazou = [d for d in tributarias if _classificar_tx(d, CPF_QUALQUER)[0] == "imposto"]
    if vazou:
        falhas.append(f"(a) contraparte CPF saiu como imposto em {len(vazou)} descrição(ões): {vazou[:2]}")
    medidas.append(f"descrições tributárias testadas contra CPF: {len(tributarias)}")

    # (b) o fragmento "Cp :" na descrição não pode mover a classificação
    base = _classificar_tx(DESC_INTER, CPF_QUALQUER)[0]
    sabotado = _classificar_tx(DESC_INTER.replace("00360305", "99999999"), CPF_QUALQUER)[0]
    if base != sabotado:
        falhas.append(f"(b) trocar o CNPJ do banco na descrição mudou a classificação: {base} → {sabotado}")

    # (c) a contraparte decide: mesma descrição, documentos diferentes, categorias diferentes
    como_pf = _classificar_tx(DESC_INTER, CPF_QUALQUER)[0]
    como_caixa = _classificar_tx(DESC_INTER, CNPJ_CAIXA)[0]
    if como_pf == como_caixa:
        falhas.append(
            f"(c) mesma descrição e contrapartes opostas deram a mesma categoria ({como_pf}) — "
            "counterparty_document está sendo ignorado"
        )
    medidas.append(f"mesma descrição: CPF→{como_pf} · Caixa→{como_caixa}")

    # (d) pagamento de verdade PARA a Caixa continua sendo tributo
    if como_caixa != "imposto":
        falhas.append(f"(d) contraparte é a própria Caixa e não saiu imposto: {como_caixa}")

    # (e) o razão de produção, recontado pela régua vigente
    dsn = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    if not dsn:
        falhas.append("(e) DATABASE_URL ausente — o razão NÃO foi medido; isto não é um verde")
    else:
        conn = psycopg2.connect(dsn)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(
                """
                SELECT bt.description d, bt.counterparty_document doc, bt.amount v
                  FROM accounting_entries ae
                  JOIN bank_transactions bt ON bt.id = ae.bank_transaction_id
                 WHERE ae.conta_debito = '2.1.2.09'
                """
            )
            rows = cur.fetchall()
            if not rows:
                medidas.append("2.1.2.09 sem lançamentos — nada a recontar")
            else:
                cpfs = _cpfs_de_funcionarios(conn)
                pf_como_tributo = [
                    r
                    for r in rows
                    if len(_so_digitos(r["doc"])) == 11 and _classificar_tx(r["d"], r["doc"], cpfs)[0] == "imposto"
                ]
                if pf_como_tributo:
                    total = sum(abs(float(r["v"] or 0)) for r in pf_como_tributo)
                    falhas.append(
                        f"(e) {len(pf_como_tributo)} pessoa(s) física(s) ainda saem como tributo "
                        f"no razão (R$ {total:,.2f})"
                    )
                func = sum(1 for r in rows if _so_digitos(r["doc"]) in cpfs)
                medidas.append(f"2.1.2.09: {len(rows)} transações, {func} com CPF de funcionário")
        finally:
            conn.close()

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no classificador de contraparte")
    print(
        "OK contraparte: CPF nunca é tributo, o CNPJ do banco na descrição não decide, "
        "a coluna da contraparte manda, e pagamento à Caixa continua imposto"
    )
    print(f"TOTAL desvios C1: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(main())
    except AssertionError as e:
        print(e)
        print("TOTAL desvios C1: >0")
        sys.exit(1)
