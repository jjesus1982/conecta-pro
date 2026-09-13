"""Oráculo — o arquivo do operador vai e volta pelo NOSSO parser (frente 03, 12/09/2026).

Por que existe: o pré-mortem (frente 3, item 2) diz que o arquivo do operador vai ser gerado
errado e ninguém vai perceber até o cartão não carregar — o aceite do portal não é prova. A
prova que temos em casa é o parser que já lê os relatórios do Sólides e do SINETRAM
(`beneficios_importer.ler_solides/ler_sinetram`): se o arquivo que geramos, relido por ele,
reproduz linha a linha o que entrou, então nenhum campo deslocou.

O que afirma:
  1. `montar_arquivo_operador` existe e produz texto para 'solides' e 'sinetram'.
  2. IDA E VOLTA sintética (a REGRA, não a fotografia): linhas com valor em centavos, milhar,
     mobilidade zero, nome com preposição e cartão do SINETRAM → gerar → reler = igual, CPF a CPF,
     centavo a centavo, cartão a cartão; o total do cabeçalho é a soma das linhas; o nº de
     colaboradores é o nº de linhas.
  3. IDA E VOLTA real: cada PDF de portal encontrado é lido, regenerado como arquivo do operador
     e relido — mesmos CPFs, mesmos valores, mesmos cartões. (Sem PDF, o item 2 continua valendo.)

Estado medido no nascimento (12/09/2026): não existia gerador — só leitor.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import glob
import os
import sys
from decimal import Decimal

PDF_DIRS = [os.environ.get("BENEFICIO_PDF_DIR", ""), "/app/uploads/referencia_kits", "/app/uploads/kits"]


def _pdfs() -> list[str]:
    out: list[str] = []
    for d in PDF_DIRS:
        if d and os.path.isdir(d):
            out += glob.glob(os.path.join(d, "**", "*.pdf"), recursive=True)
    return sorted(set(out))


def _ida_e_volta(origem: str, linhas, rotulo: str, falhas: list[str]) -> None:
    from modules.people_management.folha.services.beneficio_ponto import montar_arquivo_operador
    from modules.people_management.folha.services.beneficios_importer import parse_sinetram_texto, parse_solides_texto

    texto = montar_arquivo_operador(origem, linhas, competencia="2026-08", gerado_por="oráculo")
    relido = parse_solides_texto(texto) if origem == "solides" else parse_sinetram_texto(texto)
    if len(relido.linhas) != len(linhas):
        falhas.append(f"{rotulo}: gerei {len(linhas)} linha(s) e reli {len(relido.linhas)}")
        return
    soma = Decimal(0)
    for a, b in zip(linhas, relido.linhas, strict=True):
        soma += a.alimentacao + a.mobilidade
        if a.cpf != b.cpf:
            falhas.append(f"{rotulo}: CPF …{a.cpf[-4:]} voltou como …{b.cpf[-4:]}")
        if a.alimentacao != b.alimentacao or a.mobilidade != b.mobilidade:
            falhas.append(f"{rotulo} CPF …{a.cpf[-4:]}: valores {a.alimentacao}/{a.mobilidade} voltaram {b.alimentacao}/{b.mobilidade}")
        if origem == "sinetram" and a.cartao != b.cartao:
            falhas.append(f"{rotulo} CPF …{a.cpf[-4:]}: cartão {a.cartao!r} voltou {b.cartao!r}")
        if not b.nome.upper().startswith(a.nome.upper()[:12]):
            falhas.append(f"{rotulo} CPF …{a.cpf[-4:]}: nome {a.nome!r} voltou {b.nome!r}")
    if relido.total != soma:
        falhas.append(f"{rotulo}: total do cabeçalho {relido.total} ≠ soma das linhas {soma}")
    if f"Colaboradores: {len(linhas)}" not in texto:
        falhas.append(f"{rotulo}: cabeçalho não diz 'Colaboradores: {len(linhas)}'")


def main() -> int:
    falhas: list[str] = []
    try:
        from modules.people_management.folha.services.beneficio_ponto import montar_arquivo_operador  # noqa: F401
        from modules.people_management.folha.services.beneficios_importer import (
            LinhaBeneficio,
            ler_pedidos_em,
            parse_sinetram_texto,  # noqa: F401
            parse_solides_texto,  # noqa: F401
        )
    except ImportError as e:
        print(f"FALHOU: gerador/parser de texto não existe ({e})")
        raise AssertionError("1 desvio: sem gerador")

    # 2) regra, com os casos que costumam deslocar campo
    sint = [
        LinhaBeneficio(cpf="12345678901", nome="MARIA DE SOUZA E SILVA", alimentacao=Decimal("1234.56"), mobilidade=Decimal("0")),
        LinhaBeneficio(cpf="00000000191", nome="Antônio Walcicley Pereira da Silva", alimentacao=Decimal("352.00"), mobilidade=Decimal("160.00")),
        LinhaBeneficio(cpf="98765432100", nome="JOSE", alimentacao=Decimal("0.01"), mobilidade=Decimal("10000.00")),
    ]
    _ida_e_volta("solides", sint, "sintético Sólides", falhas)
    sint_vt = [
        LinhaBeneficio(cpf="84618477253", nome="CELIANE GARCIA DE SOUSA", mobilidade=Decimal("270.00"), cartao="58.04.06504388-1"),
        LinhaBeneficio(cpf="00000000191", nome="JOAO DA SILVA", mobilidade=Decimal("1234.50"), cartao="01.02.00000001-9"),
    ]
    _ida_e_volta("sinetram", sint_vt, "sintético SINETRAM", falhas)
    try:
        montar_arquivo_operador("sinetram", [LinhaBeneficio(cpf="1", nome="X", mobilidade=Decimal("1"))], competencia="2026-08", gerado_por="o")
        falhas.append("SINETRAM sem nº de cartão foi gerado — linha sem cartão vira crédito no cartão de ninguém")
    except ValueError:
        pass

    # 3) real
    pdfs = _pdfs()
    pedidos = ler_pedidos_em(pdfs)
    for p in pedidos:
        _ida_e_volta(p.origem, p.linhas, f"{p.origem} pedido {p.numero or '?'} ({p.competencia or 'sem competência'})", falhas)

    print(f"casos sintéticos: 2 · PDFs de portal relidos: {len(pedidos)} (de {len(pdfs)} pdf) · desvios: {len(falhas)}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na ida e volta do arquivo do operador")
    print("OK arquivo do operador: o que geramos, relido pelo nosso parser, reproduz linha a linha")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as e:
        print(e)
        sys.exit(1)
