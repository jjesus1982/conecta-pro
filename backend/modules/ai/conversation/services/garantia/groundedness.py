"""Fase 5.2a.3 — Camada de Garantia: GROUNDEDNESS (âncora anti-alucinação).

Princípio inegociável do Conecta PRO: "nunca fabricar dado" — o que um agente
afirma tem que ter lastro numa FONTE real (panorama, tool-result). Este módulo
não impede a IA de falar; ele MARCA o que ela falou sem lastro, pra a Fase
5.2a.4 decidir o que fazer (avisar o gestor, reprovar, exigir revisão).

`verificar(resposta, fonte)` é o núcleo: extrai números de ambos os lados,
compara de forma tolerante a formatação (BR "9.125,56" vs "9125,56" vs float
9125.56 vs "R$ 9.125,56") e reporta os números da resposta SEM lastro na fonte.

Conservador por padrão: um número que aparece afirmado no texto e não tem
nenhuma correspondência (mesmo após normalizar pontuação de milhar/decimal) na
fonte é considerado suspeito. Anos (ex. "2026") e percentuais (ex. "12%")
plain-int são ignorados por padrão — são raramente "o fato que se fabrica" e
geram ruído (datas, CCTs, etc.).
"""
from __future__ import annotations

import re

# Ordem importa: alternativas mais específicas primeiro, senão o fallback
# "\d+" comeria pedaços de números com milhar/decimal antes de tentar as
# formas mais longas na mesma posição.
_RE_NUM = re.compile(
    r"R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?"  # R$ 9.125,56 / R$ 100.000 / R$ 50
    r"|\d{1,3}(?:\.\d{3})+(?:,\d+)?"  # 100.000 / 9.125,56 (sem R$)
    r"|\d+,\d+"  # 56,78 (decimal sem milhar)
    r"|\d+x\d+"  # 12x36 (escala de trabalho)
    r"|\d+"  # inteiro simples: 3, 7, 100
)

_RE_ANO = re.compile(r"^(19|20)\d{2}$")


def _limpar(bruto: str) -> str:
    """Remove o prefixo 'R$' e espaços — mantém a pontuação numérica como
    apareceu no texto (é o que vira suspeito reportável ao humano)."""
    t = bruto.strip()
    if t.upper().startswith("R$"):
        t = t[2:].strip()
    return t


def _canon(bruto: str) -> str:
    """Forma canônica SÓ para comparação (nunca exibida): tira pontuação de
    milhar e vira decimal com ponto. '9.125,56' -> '9125.56'; '100.000' ->
    '100000'; '7' -> '7'; '12x36' fica como está (não é valor monetário)."""
    t = _limpar(bruto)
    if re.fullmatch(r"\d+x\d+", t, re.IGNORECASE):
        return t.lower()
    t = t.replace(".", "")
    t = t.replace(",", ".")
    # ZERO À ESQUERDA é formatação, não valor: a resposta escreve "22/08" e a fonte guarda
    # mes=8, então "08" ficava sem lastro e colava um "confira" numa resposta correta. Aviso
    # que dispara sempre é aviso que se aprende a ignorar — e aí ele deixa de valer quando o
    # número for mesmo fabricado. Medido em 24/08/2026 sobre a resposta de horas do porteiro:
    # os suspeitos eram '08' e '22', ambos de uma data, nenhum de hora.
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        inteiro, ponto, decimal = t.partition(".")
        t = (inteiro.lstrip("0") or "0") + (ponto + decimal if ponto else "")
    return t


def extrair_numeros(
    texto: str, *, ignorar_anos: bool = True, ignorar_percentuais: bool = True
) -> set[str]:
    """Extrai valores monetários/numéricos do texto, na forma como aparecem
    (sem o prefixo 'R$'). Ex.: 'R$ 9.125,56' -> '9.125,56'; 'saldo R$ 100.000'
    -> '100.000'; '3 porteiros' -> '3'; 'escala 12x36' -> '12x36'."""
    if not texto:
        return set()
    achados: set[str] = set()
    for m in _RE_NUM.finditer(texto):
        bruto = m.group(0)
        fim = m.end()
        if ignorar_percentuais and texto[fim : fim + 1] == "%":
            continue
        limpo = _limpar(bruto)
        if ignorar_anos and not bruto.upper().startswith("R$") and _RE_ANO.match(limpo):
            continue
        achados.add(limpo)
    return achados


def _achatar(obj):
    """Percorre recursivamente dict/list/tuple/set, produzindo os valores-folha."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _achatar(v)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            yield from _achatar(v)
    else:
        yield obj


def numeros_da_fonte(fonte: dict) -> set[str]:
    """Achata um dict de panorama/tool-result e extrai os números presentes
    nos valores (na mesma forma que `extrair_numeros` produziria, pra dar pra
    comparar). Booleanos são ignorados (não são "número afirmado")."""
    achados: set[str] = set()
    for folha in _achatar(fonte or {}):
        if folha is None or isinstance(folha, bool):
            continue
        if isinstance(folha, int):
            achados.add(str(folha))
        elif isinstance(folha, float):
            # forma BR (vírgula decimal) pra passar pelo MESMO _canon do texto,
            # e a forma inteira arredondada (cobre "R$ 9.125" sem centavos).
            achados.add(f"{folha:.2f}".replace(".", ","))
            achados.add(str(int(round(folha))))
        elif isinstance(folha, str):
            achados |= extrair_numeros(folha, ignorar_anos=False, ignorar_percentuais=False)
        else:
            achados |= extrair_numeros(str(folha), ignorar_anos=False, ignorar_percentuais=False)
    return achados


def verificar(resposta: str, fonte: dict) -> dict:
    """Verifica se os números afirmados em `resposta` têm lastro em `fonte`.

    Retorna `{"ok": bool, "suspeitos": [...]}`. `suspeitos` guarda os números
    NA FORMA COMO APARECERAM no texto (legível por humano) — a comparação
    internamente é tolerante a formatação (milhar/decimal/R$)."""
    nums_resposta = extrair_numeros(resposta)
    if not nums_resposta:
        return {"ok": True, "suspeitos": []}
    fonte_canon = {_canon(n) for n in numeros_da_fonte(fonte)}
    suspeitos = sorted(bruto for bruto in nums_resposta if _canon(bruto) not in fonte_canon)
    return {"ok": not suspeitos, "suspeitos": suspeitos}


# ─────────────────────────────────────────────────────────────────────────────
# TESTE-ÂNCORA (padrão 5.1: sem pytest, `python groundedness.py`, só asserts)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    fonte = {"saldo": "R$ 9.125,56", "postos": 7}

    # 1) resposta só com números da fonte -> ok=True, sem suspeitos
    resposta_ok = "O saldo atual é R$ 9.125,56 e temos 7 postos ativos."
    r1 = verificar(resposta_ok, fonte)
    assert r1["ok"] is True, f"esperado ok=True, veio {r1}"
    assert r1["suspeitos"] == [], f"esperado sem suspeitos, veio {r1}"
    print("TESTE 1 (só números da fonte) PASS:", r1)

    # 2) resposta que FABRICA um saldo -> ok=False, número fabricado em suspeitos
    resposta_fabrica = "O saldo atual é de R$ 50.000,00, bem confortável."
    r2 = verificar(resposta_fabrica, fonte)
    assert r2["ok"] is False, f"esperado ok=False, veio {r2}"
    assert "50.000,00" in r2["suspeitos"], f"esperado '50.000,00' em suspeitos, veio {r2}"
    print("TESTE 2 (número fabricado) PASS:", r2)

    # 3) tolerância a formatação: fonte com float puro, resposta em BR
    fonte_float = {"mrr": 272456.78, "clientes": 11}
    resposta_float_ok = "O MRR é R$ 272.456,78 com 11 clientes ativos."
    r3 = verificar(resposta_float_ok, fonte_float)
    assert r3["ok"] is True, f"esperado ok=True (tolerância formatação), veio {r3}"
    print("TESTE 3 (float vs BR-string) PASS:", r3)

    # 4) escala de trabalho (12x36) tratada como número válido, e ano ignorado
    fonte_escala = {"escala": "12x36", "cct": "AM000613/2025"}
    resposta_escala = "A escala é 12x36, conforme a CCT vigente em 2026."
    r4 = verificar(resposta_escala, fonte_escala)
    assert r4["ok"] is True, f"esperado ok=True (ano ignorado + escala com lastro), veio {r4}"
    print("TESTE 4 (escala + ano ignorado) PASS:", r4)

    # 5) resposta sem nenhum número -> ok=True trivialmente
    r5 = verificar("Tudo certo por aqui, sem números pra reportar.", fonte)
    assert r5 == {"ok": True, "suspeitos": []}, f"veio {r5}"
    print("TESTE 5 (sem números) PASS:", r5)

    # ── 6) FORMATO não é divergência (24/08/2026) ────────────────────────────
    # O Bartolo acertou as horas do porteiro e colava "confira" na própria resposta certa.
    # Medido: os suspeitos eram '08' e '22' — de uma DATA, por zero à esquerda. A hipótese
    # de que "83h55" × "83:55" era a causa foi VERIFICADA E DESCARTADA: o extrator separa os
    # dois do mesmo jeito (83 e 55). O teste trava as duas coisas assim mesmo.
    fonte_horas = {"horas_trabalhadas": "83:55", "mes": 8, "faltas_dias": 1}
    r6 = verificar("Você fez 83h55 no mês (referência 08), com 1 falta.", fonte_horas)
    assert r6["ok"] is True, f"formato (h × : e zero à esquerda) não pode virar suspeito: {r6}"
    print("TESTE 6 (formato não é divergência) PASS:", r6)

    # ── 7) …e o inverso: VALOR diferente continua reprovando ─────────────────
    # Sem esta metade o conserto vira carimbo: um verificador que aprova tudo é pior que
    # nenhum, porque parece que alguém está olhando.
    r7 = verificar("Você fez 84h55 no mês.", fonte_horas)
    assert r7["ok"] is False, f"84h55 não tem lastro em 83:55 — tinha de reprovar: {r7}"
    assert "84" in r7["suspeitos"], f"o número divergente tem de aparecer: {r7}"
    print("TESTE 7 (valor divergente ainda reprova) PASS:", r7)

    # ── 8) zero à esquerda não apaga diferença de ordem de grandeza ──────────
    r8 = verificar("O saldo é R$ 100.000,00.", {"saldo": 10000.0})
    assert r8["ok"] is False, f"100.000 não é 10.000 — normalizar zero não pode achatar isso: {r8}"
    print("TESTE 8 (ordem de grandeza preservada) PASS:", r8)

    print("\nTODOS OS TESTES DE groundedness.py PASSARAM")
