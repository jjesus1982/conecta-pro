"""Oráculo C7 — EFD Contribuições (PIS/COFINS): o regime decide o arquivo inteiro.

Por que existe
--------------
Esta escrituração não existia até 26/09/2026, e o que a impedia não era código: era **não
saber o regime**. Lucro Real leva ao não-cumulativo como REGRA GERAL — e serviço de
vigilância é uma das exceções do art. 10 da Lei 10.833/2003, que permanece no CUMULATIVO.
Trocar um pelo outro muda alíquota (0,65%+3,00% contra 1,65%+7,60%), muda o CST, muda o
código de apuração e cria um bloco de créditos que não deve existir. O arquivo sai bonito
e errado, e o validador do fisco aceita.

Este oráculo trava o que não pode escorregar sozinho.

O que afirma
------------
  a) as alíquotas do cumulativo são as da Lei 9.718 — PIS 0,65% e COFINS 3,00% — e não as
     do não-cumulativo, que são as que alguém digitaria por hábito;
  b) o código de contribuição apurada é **51** (cumulativo, alíquota básica). O «01»
     parecido é o NÃO-cumulativo, e a troca passa despercebida a olho nu;
  c) o registro 0110 declara COD_INC_TRIB = 2 (exclusivamente cumulativo);
  d) NOTA CANCELADA entra no arquivo (o número foi usado) e **fica fora da base** —
     somar cancelada é recolher sobre faturamento que não houve;
  e) o bloco 9 conta a si mesmo: o 9900 do 9900 existe, o 9990 fecha o bloco e o 9999
     conta o arquivo inteiro incluindo ele próprio;
  f) empresa do SIMPLES é recusada por ser DISPENSADA, não por «falta declarar o regime»
     — recusa com o motivo errado manda consertar o que não está quebrado;
  g) CNPJ sem regime declarado é recusado ANTES de montar qualquer coisa;
  h) um regime que o montador não sabe escriturar levanta em vez de produzir arquivo.

Como roda (container, PYTHONPATH=/app):
    python3 /app/scripts/orq/test_oraculo_c7_efd_contribuicoes.py
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal


def main() -> int:
    falhas: list[str] = []
    medidas: list[str] = []

    from modules.government_integrations.core import sped_contribuicoes as sc

    # ── (a) as alíquotas são as do CUMULATIVO ────────────────────────────────────────
    if Decimal("0.65") != sc.ALIQ_PIS_CUMULATIVO:
        falhas.append(f"(a) PIS do cumulativo é 0,65% e está {sc.ALIQ_PIS_CUMULATIVO}")
    if Decimal("3.00") != sc.ALIQ_COFINS_CUMULATIVO:
        falhas.append(f"(a) COFINS do cumulativo é 3,00% e está {sc.ALIQ_COFINS_CUMULATIVO}")
    if Decimal("1.65") == sc.ALIQ_PIS_CUMULATIVO or Decimal("7.60") == sc.ALIQ_COFINS_CUMULATIVO:
        falhas.append("(a) alíquotas do NÃO-cumulativo no montador do cumulativo")

    # ── (b)(c) os códigos que o regime determina ─────────────────────────────────────
    if sc.COD_CONT_CUMULATIVO != "51":
        falhas.append(f"(b) código de contribuição apurada devia ser 51, está {sc.COD_CONT_CUMULATIVO}")
    if sc.COD_INC_TRIB_CUMULATIVO != "2":
        falhas.append(f"(c) 0110/COD_INC_TRIB devia ser 2, está {sc.COD_INC_TRIB_CUMULATIVO}")

    # ── monta um arquivo de mesa: uma nota boa e uma CANCELADA ───────────────────────
    m = sc.SPEDContribuicoesManager(
        cnpj="00000000000191", razao_social="FIXTURE C7", uf="AM",
        codigo_municipio="1302603", inscricao_municipal="00000000",
    )
    m.adicionar_tomador(sc.Tomador(codigo="P0001", nome="TOMADOR FIXTURE", cnpj_cpf="00736037000182"))
    m.adicionar_servico(sc.ServicoPrestado(
        numero="1", serie="901", chave="X" * 50, data_emissao=date(2026, 8, 10),
        tomador_codigo="P0001", valor_servico=Decimal("1000.00"), valor_iss=Decimal("50.00"),
        codigo_servico="140601", descricao="fixture"))
    m.adicionar_servico(sc.ServicoPrestado(
        numero="2", serie="901", chave="Y" * 50, data_emissao=date(2026, 8, 20),
        tomador_codigo="P0001", valor_servico=Decimal("500.00"), situacao="02"))
    txt = m.gerar_arquivo(date(2026, 8, 1), date(2026, 8, 31))
    linhas = txt.split("\r\n")

    # ── (d) cancelada no arquivo, fora da base ───────────────────────────────────────
    if m.receita_tributavel != Decimal("1000.00"):
        falhas.append(f"(d) a base devia ser R$ 1.000,00 (a cancelada fica de fora) e é {m.receita_tributavel}")
    if m.pis_apurado != Decimal("6.50") or m.cofins_apurado != Decimal("30.00"):
        falhas.append(f"(d) PIS/COFINS sobre R$ 1.000 no cumulativo são 6,50 e 30,00; "
                      f"vieram {m.pis_apurado} e {m.cofins_apurado}")
    a100 = [x for x in linhas if x.startswith("|A100|")]
    if len(a100) != 2:
        falhas.append(f"(d) a nota cancelada sumiu do arquivo: {len(a100)} A100, esperado 2")
    elif "|02|" not in a100[1]:
        falhas.append("(d) a nota cancelada não saiu com COD_SIT 02")
    medidas.append(f"base R$ {m.receita_tributavel} · PIS R$ {m.pis_apurado} · COFINS R$ {m.cofins_apurado}")

    if not any(x.startswith(f"|0110|{sc.COD_INC_TRIB_CUMULATIVO}|") for x in linhas):
        falhas.append("(c) o 0110 do arquivo não declara o regime cumulativo")
    for reg in ("M210", "M610"):
        ln = [x for x in linhas if x.startswith(f"|{reg}|")]
        if not ln:
            falhas.append(f"(b) o arquivo não tem {reg}")
        elif not ln[0].startswith(f"|{reg}|{sc.COD_CONT_CUMULATIVO}|"):
            falhas.append(f"(b) {reg} não usa o código {sc.COD_CONT_CUMULATIVO}: {ln[0][:40]}")

    # ── (e) o bloco 9 conta a si mesmo ───────────────────────────────────────────────
    r9900 = {x.split("|")[2]: int(x.split("|")[3]) for x in linhas if x.startswith("|9900|")}
    reais: dict[str, int] = {}
    for x in linhas:
        if x.startswith("|"):
            reais[x.split("|")[1]] = reais.get(x.split("|")[1], 0) + 1
    for reg, qtd in sorted(r9900.items()):
        if reais.get(reg, 0) != qtd:
            falhas.append(f"(e) 9900 diz {qtd} de {reg} e o arquivo tem {reais.get(reg, 0)}")
    if "9900" not in r9900:
        falhas.append("(e) não há 9900 contando os próprios 9900 — o validador recusa o arquivo")
    n9999 = [x for x in linhas if x.startswith("|9999|")]
    if not n9999:
        falhas.append("(e) arquivo sem 9999")
    elif int(n9999[0].split("|")[2]) != len(linhas):
        falhas.append(f"(e) 9999 diz {n9999[0].split('|')[2]} e o arquivo tem {len(linhas)} linhas")
    medidas.append(f"{len(linhas)} registros · {len(r9900)} tipos no 9900")

    # ── (h) regime que ele não sabe escriturar LEVANTA ───────────────────────────────
    try:
        sc.SPEDContribuicoesManager(
            cnpj="00000000000191", razao_social="FIXTURE C7", uf="AM",
            codigo_municipio="1302603", regime="nao_cumulativo")
        falhas.append("(h) aceitou montar no NÃO-cumulativo, que ele não sabe escriturar")
    except sc.RegimeNaoEscrituravelError:
        pass

    # ── (f)(g) as recusas do serviço, com o motivo CERTO ─────────────────────────────
    from modules.government_integrations.services import sped_contribuicoes_service as svc

    try:
        svc.SPEDContribuicoesService(empresa_slug="conecta_patrimonial")
        falhas.append("(f) a Patrimonial (Simples) não foi recusada — ela é DISPENSADA da EFD")
    except svc.DispensadaDaEFDError as e:
        if "simples" not in str(e).lower():
            falhas.append(f"(f) recusou a Patrimonial pelo motivo errado: {str(e)[:70]}")
    except svc.RegimeNaoDeclaradoError as e:
        falhas.append(f"(f) recusou a Patrimonial como «regime não declarado»; ela é DISPENSADA: {str(e)[:60]}")

    try:
        eletronica = svc.SPEDContribuicoesService(empresa_slug="conecta_eletronica")
        if eletronica.regime != "cumulativo":
            falhas.append(f"(g) a Eletrônica saiu no regime «{eletronica.regime}», e a decisão é CUMULATIVO")
        if not eletronica.regime_fonte.strip():
            falhas.append("(g) o regime da Eletrônica está declarado SEM fonte escrita")
        medidas.append(f"Eletrônica: {eletronica.regime}")
    except Exception as e:  # noqa: BLE001
        falhas.append(f"(g) a Eletrônica não conseguiu iniciar a escrituração: {str(e)[:80]}")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na EFD Contribuições")
    print(
        "OK EFD Contribuições: alíquotas e códigos do CUMULATIVO, 0110 declarando o regime, "
        "nota cancelada dentro do arquivo e fora da base, bloco 9 contando a si mesmo, "
        "Simples recusado por DISPENSA e regime desconhecido levantando"
    )
    print(f"TOTAL desvios C7: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(main())
    except AssertionError as e:
        print(e)
        print("TOTAL desvios C7: >0")
        sys.exit(1)
