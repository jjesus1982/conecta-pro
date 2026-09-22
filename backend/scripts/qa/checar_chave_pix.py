#!/usr/bin/env python3
"""Chave PIX que não leva o dinheiro até a pessoa — pega ANTES do pagamento.

Origem: 22/09/2026. No pagamento do VT+VR alguns funcionários reclamaram que a chave CPF
apontava para banco que eles não usam; a da Graciene caía em conta negativa. O Jordan mandou
revisar tudo antes do adiantamento de setembro, e a varredura achou sete defeitos — dois deles
em gente que ia receber naquele dia: Bianca e Kelly tinham telefone gravado com `pix_key_type`
CPF. Nenhum apitou nunca, porque **ninguém nunca tinha perguntado**.

O pior achado não era de formato: `José Rodrigo Oliveira` (PJ ativo) tinha
`pix_key = 92984009843`, que é o TELEFONE dele sem o +55, etiquetado como CPF. Como CPF ele
nem passa no dígito verificador — o pagamento nunca chegaria. A prova de que era o telefone
veio de dentro de casa: a mesma pessoa em `diaria_diaristas` tem `+5592984009843`.

Daí as duas perguntas que este caçador faz, e a ordem importa:

1. **A chave é coerente consigo mesma?** tipo × valor, dígito verificador do CPF, telefone com
   +55 e nono dígito, e-mail que é e-mail, EVP que é UUID, chave repetida em duas pessoas
   (dinheiro de um caindo para outro), chave CPF que não é o CPF do próprio dono.
2. **A mesma pessoa tem chave DIFERENTE em outra tabela?** `employees.pix_key` paga a folha;
   `diaria_diaristas.pix` paga o VT/VR e a diária. Divergir não é defeito por si só — 7 das 8
   divergências medidas no primeiro dia eram gente com duas chaves suas, as duas boas. Vira
   defeito quando a chave da FOLHA nunca foi provada pelo banco e a outra já foi.

⚠️ O que este caçador NÃO consegue fazer, e por que: perguntar ao DICT quem é o dono da chave.
A API do Inter não expõe consulta de chave — `/pix/v2/dict/key` devolve 404 (medido em
22/09/2026, e mais cinco variantes de caminho). O `InterAdapter.validate_pix_key()` chama esse
caminho e engole o erro no `except`, então ele responde `None` para TODA chave: uma função que
parece validar e sempre diz "não". Não confie nela.

A prova real de que a chave leva à pessoa certa só existe DEPOIS de pagar: o Inter devolve
`recebedor.nome`, e `conferencia_pix.conferir()` grava `recebedor confere` ou
`⚠ RECEBEDOR DIVERGE` na linha do pagamento. Por isso a segunda pergunta usa esse histórico
como lastro — é o único oráculo externo que esta casa tem para chave PIX.

    python3 backend/scripts/qa/checar_chave_pix.py

Linha canônica: `TOTAL chaves PIX com defeito: N` (binária: N = 0). Exit 1 quando há achado.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

PG = os.environ.get("QA_PG_CONTAINER", "conecta-pro-postgres")
DOCKER = os.environ.get("QA_DOCKER", "/usr/bin/docker")

#: Só quem pode receber dinheiro hoje. Demitido com chave torta não é defeito — é história.
_VIVOS = "e.status IN ('ativo','pj_ativo','afastado_inss') AND coalesce(e.is_homologacao,false)=false"


def _sql(q: str) -> list[list[str]]:
    r = subprocess.run(  # noqa: S603
        [DOCKER, "exec", PG, "psql", "-U", "postgres", "-d", "conecta_pro", "-t", "-A", "-F\t", "-c", q],
        capture_output=True,
        timeout=120,
        check=False,
    )
    if r.returncode != 0:
        print("NÃO MEDIDO — psql falhou:", r.stderr.decode("utf8", "ignore")[:200], file=sys.stderr)
        raise SystemExit(0)  # banco fora do ar não é vermelho: trava que grita à toa ninguém lê
    saida = r.stdout.decode("utf8", "ignore").strip()
    return [ln.split("\t") for ln in saida.splitlines() if ln.strip()]


def _dig(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _cpf_ok(c: str) -> bool:
    """Dígito verificador. Chave CPF que não passa aqui NUNCA vai chegar em ninguém."""
    c = _dig(c)
    if len(c) != 11 or c == c[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(c[i]) * ((n + 1) - i) for i in range(n))
        if (soma * 10) % 11 % 10 != int(c[n]):
            return False
    return True


def _tipo_real(k: str) -> str:
    """O que a chave É, lida pelo valor — não pelo que alguém digitou na etiqueta."""
    k = (k or "").strip()
    if "@" in k:
        return "EMAIL"
    if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", k):
        return "EVP"
    d = _dig(k)
    if k.startswith("+") or len(d) in (12, 13):
        return "PHONE"
    if len(d) == 14:
        return "CNPJ"
    if len(d) == 11:
        return "CPF"
    return "?"


def main() -> int:  # noqa: C901, PLR0912
    achados: dict[str, list[str]] = {}

    def anota(cat: str, linha: str) -> None:
        achados.setdefault(cat, []).append(linha)

    pessoas = _sql(
        "SELECT e.nome, coalesce(e.cpf,''), btrim(coalesce(e.pix_key,'')), "
        "       upper(coalesce(e.pix_key_type,'')), e.status "
        f"  FROM employees e WHERE {_VIVOS} ORDER BY e.nome;"
    )
    por_chave: dict[str, list[str]] = {}

    for nome, cpf, chave, etiqueta, status in pessoas:
        if not chave:
            anota("SEM CHAVE (recebe dinheiro e não tem como)", f"{nome} [{status}]")
            continue
        por_chave.setdefault(chave.lower(), []).append(f"{nome} [{status}]")
        real = _tipo_real(chave)
        if real != etiqueta:
            anota("TIPO ≠ VALOR", f"{nome}: {chave} etiquetado {etiqueta or '(vazio)'}, é {real}")
        if real == "CPF":
            if not _cpf_ok(chave):
                anota("CPF INVÁLIDO (nem chega)", f"{nome}: {chave}")
            elif _dig(cpf) and _dig(chave) != _dig(cpf):
                anota("CHAVE CPF ≠ CPF DA PESSOA", f"{nome}: chave {_dig(chave)} × cadastro {_dig(cpf)}")
            elif not _dig(cpf):
                anota("CHAVE CPF SEM CPF NO CADASTRO (não dá para conferir)", f"{nome}: {chave}")
        elif real == "PHONE":
            d = _dig(chave)
            if not chave.startswith("+55"):
                anota("TELEFONE sem +55", f"{nome}: {chave}")
            elif len(d) != 13:
                anota("TELEFONE com dígitos a mais/menos", f"{nome}: {chave} ({len(d)} díg.)")
            elif d[4] != "9":
                anota("TELEFONE sem o nono dígito", f"{nome}: {chave}")
        elif real == "EMAIL" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}", chave):
            anota("E-MAIL mal formado", f"{nome}: {chave}")
        elif real == "?":
            anota("CHAVE que não é nenhum tipo válido", f"{nome}: {chave!r}")

    for chave, donos in por_chave.items():
        if len(donos) > 1:
            anota("CHAVE REPETIDA em mais de uma pessoa", f"{chave} → " + " | ".join(donos))

    # Pergunta 2: a folha paga uma chave e o VT/VR paga outra — e a da folha nunca foi provada?
    divergentes = _sql(
        "WITH div AS ("
        "  SELECT e.nome, btrim(e.pix_key) folha, btrim(d.pix) outra"
        "    FROM employees e JOIN diaria_diaristas d"
        r"      ON regexp_replace(coalesce(e.cpf,'x'),'\D','','g') = regexp_replace(coalesce(d.cpf,'y'),'\D','','g')"
        f"   WHERE {_VIVOS} AND coalesce(e.pix_key,'')<>'' AND coalesce(d.pix,'')<>''"
        "     AND lower(btrim(e.pix_key)) <> lower(btrim(d.pix))"
        r"     AND regexp_replace(e.pix_key,'\D','','g') <> regexp_replace(d.pix,'\D','','g'))"
        "SELECT div.nome, div.folha, div.outra,"
        "  (SELECT count(*) FROM financial_pagamentos_diaristas p"
        "    WHERE upper(btrim(p.beneficiario))=upper(btrim(div.nome))"
        "      AND btrim(p.pix_key)=div.folha AND p.descricao ~* 'recebedor confere'),"
        "  (SELECT count(*) FROM financial_pagamentos_diaristas p"
        "    WHERE upper(btrim(p.beneficiario))=upper(btrim(div.nome))"
        "      AND btrim(p.pix_key)=div.outra AND p.descricao ~* 'recebedor confere')"
        " FROM div ORDER BY div.nome;"
    )
    benignas = 0
    for nome, folha, outra, prov_folha, prov_outra in divergentes:
        if int(prov_folha or 0) > 0:
            benignas += 1  # as duas são dela; o banco já confirmou a da folha
        elif int(prov_outra or 0) > 0:
            anota(
                "FOLHA PAGA CHAVE NÃO PROVADA, e a OUTRA já foi provada pelo banco",
                f"{nome}: folha={folha} (0 provas) × VT/VR={outra} ({prov_outra} prova(s))",
            )

    ordem = [
        "CPF INVÁLIDO (nem chega)",
        "CHAVE REPETIDA em mais de uma pessoa",
        "CHAVE CPF ≠ CPF DA PESSOA",
        "FOLHA PAGA CHAVE NÃO PROVADA, e a OUTRA já foi provada pelo banco",
        "TIPO ≠ VALOR",
        "TELEFONE sem +55",
        "TELEFONE com dígitos a mais/menos",
        "TELEFONE sem o nono dígito",
        "E-MAIL mal formado",
        "CHAVE que não é nenhum tipo válido",
        "SEM CHAVE (recebe dinheiro e não tem como)",
        "CHAVE CPF SEM CPF NO CADASTRO (não dá para conferir)",
    ]
    #: Não conta para o total binário: é falta de CPF no cadastro, não chave errada.
    _so_aviso = {"CHAVE CPF SEM CPF NO CADASTRO (não dá para conferir)"}

    total = 0
    for cat in ordem:
        if achados.get(cat):
            print(f"  {'(aviso) ' if cat in _so_aviso else ''}{cat}: {len(achados[cat])}")
            for linha in achados[cat]:
                print(f"       {linha}")
            if cat not in _so_aviso:
                total += len(achados[cat])

    print(f"  divergências benignas (chave da folha já provada pelo banco): {benignas}")
    print(f"TOTAL chaves PIX com defeito: {total}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
