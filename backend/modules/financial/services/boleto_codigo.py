"""Decodifica e VALIDA linha digitável / código de barras de boleto.

Existe porque o radar por e-mail lê PDF de fornecedor, e um PDF é cheio de números
longos: CNPJ colado, número de contrato, chave de acesso de NFS-e. Sem validar, qualquer
sequência de 47 dígitos viraria uma dívida que ninguém emitiu — o oposto da regra da casa.

O boleto se descreve: valor e vencimento estão DENTRO do código, com dígitos
verificadores. Se os DVs batem, não é coincidência — é boleto de verdade.

Dois formatos:
  • **Bancário** (47 dígitos digitáveis → 44 de barras): valor e fator de vencimento no
    próprio código; três campos com DV módulo 10 e um DV geral módulo 11.
  • **Convênio/arrecadação** (48 dígitos, começa com 8): água, luz, telefone, tributo.
    Tem valor, mas **não tem vencimento no código** — e é por isso que devolvemos
    `vencimento=None` em vez de inventar uma data.

⚠️ Vencimento vem do FATOR (dias desde 07/10/1997, Febraban). O fator reseta ao chegar
em 9999; corrigimos somando ciclos de 9000 até a data ficar coerente com hoje. Sem isso,
boleto emitido depois do reset apontaria para 2001.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

#: Época do fator de vencimento (Febraban).
_EPOCA = date(1997, 10, 7)


def _so_digitos(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


def _dv_mod10(campo: str) -> int:
    """DV módulo 10 — pesos 2,1 alternados da direita para a esquerda, somando os
    algarismos do produto (12 vira 1+2)."""
    soma, peso = 0, 2
    for c in reversed(campo):
        p = int(c) * peso
        soma += p if p < 10 else p - 9
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def _dv_mod11_barras(barras_sem_dv: str) -> int:
    """DV geral do código de barras — módulo 11, pesos 2..9 cíclicos.

    Resultado 0, 1 ou 10 vira 1: é a regra da Febraban, não um arredondamento nosso.
    """
    soma, peso = 0, 2
    for c in reversed(barras_sem_dv):
        soma += int(c) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    dv = 11 - resto
    return 1 if dv in (0, 1, 10, 11) else dv


def _dv_convenio(campo: str, modulo: int) -> int:
    """DV de bloco de convênio. O 4º dígito do código diz se é módulo 10 ou 11."""
    if modulo == 10:
        return _dv_mod10(campo)
    soma, peso = 0, 2
    for c in reversed(campo):
        soma += int(c) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    if resto == 0:
        return 0
    if resto == 1:
        return 0        # regra da arrecadação: resto 1 → DV 0
    return 11 - resto


def _data_do_fator(fator: int, hoje: date | None = None) -> date | None:
    if fator <= 0:
        return None
    hoje = hoje or date.today()
    venc = _EPOCA + timedelta(days=fator)
    # Ciclo de 9000: o fator reseta em 9999 e recomeça em 1000. NO MÁXIMO duas voltas —
    # empurrar sem limite transformava lixo em "vencimento em 2048" em vez de recusar.
    voltas = 0
    while venc < hoje - timedelta(days=365) and voltas < 2:
        venc += timedelta(days=9000)
        voltas += 1
    return venc


def decodificar(codigo: str, hoje: date | None = None) -> dict | None:
    """Devolve {tipo, barras, valor, vencimento} se for boleto VÁLIDO; senão `None`.

    `None` significa "isto não é um boleto" — e é a resposta certa para o CNPJ, o número
    do contrato e a chave da NFS-e que também aparecem no PDF.
    """
    d = _so_digitos(codigo)

    if len(d) == 48 and d[0] == "8":
        return _convenio(d)
    if len(d) == 47:
        return _bancario_47(d, hoje)
    if len(d) == 44 and d[0] != "8":
        return _bancario_44(d, hoje)
    return None


def _bancario_47(d: str, hoje: date | None) -> dict | None:
    # Campos 1..3 têm DV módulo 10 na última posição de cada um.
    if _dv_mod10(d[0:9]) != int(d[9]):
        return None
    if _dv_mod10(d[10:20]) != int(d[20]):
        return None
    if _dv_mod10(d[21:31]) != int(d[31]):
        return None

    # Linha digitável → código de barras (a ordem dos pedaços é fixa pela Febraban).
    barras = d[0:4] + d[32] + d[33:47] + d[4:9] + d[10:20] + d[21:31]
    return _bancario_44(barras, hoje)


#: Janela plausível de vencimento. Boleto com data fora disso não é boleto — é uma
#: sequência qualquer que passou no DV por acaso. Medido em 21/08/2026: a varredura da
#: caixa devolveu "NFS-e da Sólides" vencendo em 2047 e 2048, valores de R$30 milhões.
ANOS_PARA_TRAS = 3
ANOS_PARA_FRENTE = 3


def _bancario_44(barras: str, hoje: date | None) -> dict | None:
    if len(barras) != 44:
        return None
    # ⚠️ O código de barras tem UM só dígito verificador (módulo 11) — uma sequência
    # qualquer passa por acaso ~1 vez em 11. A linha digitável de 47 tem QUATRO e por
    # isso é confiável. Como o extrator desliza uma janela sobre números longos de PDF,
    # 9% de falso positivo vira dívida inventada. Daí as duas travas abaixo.
    if barras[3] != "9":
        return None          # posição 4 = código da moeda; 9 = Real. Chave de NFS-e cai aqui.
    if _dv_mod11_barras(barras[:4] + barras[5:]) != int(barras[4]):
        return None

    fator = int(barras[5:9])
    valor = int(barras[9:19]) / 100
    if valor <= 0:
        return None          # boleto sem valor: não vira obrigação, é para consulta

    venc = _data_do_fator(fator, hoje)
    if venc:
        ref = hoje or date.today()
        if not (ref - timedelta(days=365 * ANOS_PARA_TRAS) <= venc
                <= ref + timedelta(days=365 * ANOS_PARA_FRENTE)):
            return None      # data implausível: não era boleto
    return {
        "tipo": "bancario",
        "barras": barras,
        "banco": barras[0:3],
        "valor": round(valor, 2),
        "vencimento": venc,
    }


def _convenio(d: str) -> dict | None:
    """Arrecadação/convênio: 48 dígitos em 4 blocos de 12, cada um com DV no fim."""
    modulo = 10 if d[2] in ("6", "7") else 11
    for i in range(4):
        bloco = d[i * 12:(i + 1) * 12]
        if _dv_convenio(bloco[:11], modulo) != int(bloco[11]):
            return None

    barras = "".join(d[i * 12:(i * 12) + 11] for i in range(4))
    valor = int(barras[4:15]) / 100
    if valor <= 0:
        return None
    return {
        "tipo": "convenio",
        "barras": barras,
        "banco": None,
        "valor": round(valor, 2),
        # Convênio NÃO carrega vencimento no código. `None` em vez de data inventada —
        # quem consome decide (pedir ao humano, ou usar o prazo do e-mail).
        "vencimento": None,
    }


#: Sequências de 44 a 48 dígitos, tolerando espaços e pontos como os PDFs trazem.
_PADRAO = re.compile(r"(?:\d[\s.]?){43,60}\d")


def achar_boletos(texto: str, hoje: date | None = None) -> list[dict]:
    """Todos os boletos VÁLIDOS num texto. Deduplicado por código de barras."""
    achados: dict[str, dict] = {}
    for m in _PADRAO.finditer(texto or ""):
        bruto = _so_digitos(m.group())
        # A janela pode capturar dígitos vizinhos; testa os tamanhos possíveis a partir
        # de cada início plausível em vez de exigir corte exato.
        for ini in range(0, max(1, len(bruto) - 43)):
            for tam in (47, 48, 44):
                r = decodificar(bruto[ini:ini + tam], hoje)
                if r:
                    achados[r["barras"]] = r
                    break
    return list(achados.values())
