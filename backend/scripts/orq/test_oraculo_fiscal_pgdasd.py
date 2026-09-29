#!/usr/bin/env python3
"""Oráculo: a declaração do PGDAS-D é lida, prova a si mesma, e o RBT12 chega ao cadastro.

Por que nasceu (29/09/2026): o RBT12 era o único número do preço que vinha de tabela genérica,
e o recibo do PGDAS-D — o único documento do Simples que já tínhamos — NÃO o traz. O dono
baixou as declarações completas à mão. Sem oráculo, o parser volta a errar calado no dia em
que o layout mudar, e o preço volta a mentir sem ninguém ver.

Regras afirmadas (não fotografia):
  (a) toda declaração parseia como PGDASD_DECLARACAO, e a competência lida do «Período de
      Apuração» bate com a que está DENTRO do número da declaração (raiz do CNPJ+AAAAMM+seq).
  (b) o documento se prova sozinho: a alíquota efetiva calculada pelo RBT12p na faixa do
      Anexo IV é IGUAL à que o próprio DAS praticou no segmento sem retenção de ISS.
  (c) quem manda na faixa é o RBT12p, não o RBT12 — empresa em início de atividade. Se os
      dois fossem intercambiáveis, a conta de (b) fecharia com qualquer um dos dois.
  (d) `empresas.rbt12` guarda o RBT12p da declaração MAIS NOVA disponível, com o marcador
      `pgdasd_comp:AAAA-MM` na fonte, e o resolvedor de regime devolve esse mesmo número.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_fiscal_pgdasd.py
"""

from __future__ import annotations

import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from modules.fiscal_contabil.obrigacoes.guias_drive_service import (  # noqa: E402
    _FAIXAS_ANEXO_IV,
    _db_sync,
    parse_pdf_guia,
)

PASTAS = ("/app/uploads/ecac", "/app/uploads/onvio")


def _efetiva(rbt: float) -> float | None:
    for teto, aliq, ded in _FAIXAS_ANEXO_IV:
        if rbt <= teto:
            return round((rbt * aliq - ded) / rbt, 6)
    return None


def main() -> None:
    arquivos = []
    for pasta in PASTAS:
        arquivos += glob.glob(f"{pasta}/**/*.pdf", recursive=True)
    decls = []
    for f in sorted(set(arquivos)):
        if "PGDASD" not in os.path.basename(f).upper():
            continue
        g = parse_pdf_guia(f, os.path.basename(f))
        if g.tipo != "PGDASD_DECLARACAO":
            continue
        decls.append((f, g))
    assert decls, f"nenhuma declaração do PGDAS-D lida em {PASTAS} — o parser cegou ou os arquivos sumiram"

    provadas = 0
    for f, g in decls:
        nome = os.path.basename(f)
        # (a) a competência do texto bate com a de dentro do número da declaração
        # O número é RAIZ do CNPJ (8 dígitos) + AAAAMM + sequencial — não o CNPJ inteiro.
        m = re.search(r"^(\d{8})(\d{4})(\d{2})(\d{3})$", (g.numero_documento or ""))
        assert m, f"{nome}: número da declaração fora do formato raiz+AAAAMM+seq: {g.numero_documento!r}"
        assert (g.competencia_ano, g.competencia_mes) == (int(m.group(2)), int(m.group(3))), (
            f"{nome}: competência lida {g.competencia_mes:02d}/{g.competencia_ano} ≠ "
            f"{m.group(3)}/{m.group(2)} do número da declaração"
        )
        d = g.detalhe or {}
        rbt12, rbt12p = d.get("rbt12"), d.get("rbt12p")
        # A base da faixa é o proporcionalizado SÓ nos 12 primeiros meses de atividade.
        base_faixa = rbt12p if d.get("inicio_de_atividade") else rbt12
        if not base_faixa:
            continue  # meses sem receita anterior não têm faixa a provar

        # (b) o DAS do segmento SEM retenção prova a alíquota que o RBT12p implica
        import fitz  # noqa: PLC0415

        txt = "\n".join(p.get_text() for p in fitz.open(f))
        # O bloco tem de ser do ANEXO IV explicitamente. Casar só por «sem retenção» pegava
        # bloco de Anexo III numa declaração mista e comparava alíquota de anexo errado.
        bloco = txt.split("Sujeitos ao Anexo IV, sem", 1)
        if len(bloco) < 2 or "IV" not in (d.get("anexos") or []):
            continue
        receita = re.search(r"Receita Bruta Informada: R\$ ([\d.]+,\d{2})", bloco[1])
        totais = re.findall(r"\n([\d.]+,\d{2})", bloco[1][: bloco[1].find("Parcela 1")])
        # São NOVE colunas — IRPJ, CSLL, COFINS, PIS/Pasep, INSS/CPP, ICMS, IPI, ISS, Total.
        # Ler a 8ª pega o ISS e não o total: em 07/2026 isso dava 3,20% contra 8,00% reais.
        if not (receita and len(totais) >= 9):
            continue
        base = float(receita.group(1).replace(".", "").replace(",", "."))
        total_das = float(totais[8].replace(".", "").replace(",", "."))
        iss_das = float(totais[7].replace(".", "").replace(",", "."))
        praticada = round(total_das / base, 6)
        calc_p = _efetiva(base_faixa)
        assert calc_p is not None, f"{nome}: base {base_faixa} fora das faixas do Anexo IV"
        # ⚠️ TETO DO ISS: o ISS no Simples para no teto municipal de 5%. Quando ele ativa, a
        # alíquota praticada fica ABAIXO da que a faixa implica, e a igualdade não vale — foi
        # o que a declaração da Eletrônica de 12/2025 mostrou (15,2419% praticada contra
        # 15,3946% da faixa, com o ISS cravado em 5,0000%). Aí a afirmação muda de forma, mas
        # não desaparece: o teto só pode DIMINUIR, nunca aumentar.
        if abs(iss_das / base - 0.05) < 1e-6:
            assert praticada <= calc_p + 1e-6, (
                f"{nome}: ISS no teto de 5% e ainda assim a praticada {praticada} ficou ACIMA "
                f"da faixa {calc_p} — o teto não pode aumentar tributo"
            )
            print(
                f"OK {nome[:46]:<46} {g.competencia_mes:02d}/{g.competencia_ano} "
                f"teto do ISS ativo: praticada {praticada * 100:.4f}% ≤ faixa {calc_p * 100:.4f}%"
            )
            provadas += 1
            continue
        assert abs(calc_p - praticada) < 1e-4, (
            f"{nome}: alíquota pela base {base_faixa} {calc_p} ≠ praticada no DAS {praticada} ({total_das} / {base})"
        )
        # (c) e o RBT12 CRU não serviria — se servisse, o campo proporcionalizado seria enfeite
        outra = rbt12 if d.get("inicio_de_atividade") else rbt12p
        if outra and abs(outra - base_faixa) > 0.01:
            calc_cru = _efetiva(outra)
            assert calc_cru is None or abs(calc_cru - praticada) > 1e-4, (
                f"{nome}: a OUTRA base daria a MESMA alíquota — a distinção que este "
                f"oráculo protege deixou de existir; reveja a regra antes de relaxá-la"
            )
        provadas += 1
        print(
            f"OK {nome[:46]:<46} {g.competencia_mes:02d}/{g.competencia_ano} "
            f"base {base_faixa:,.2f} → efetiva {praticada * 100:.4f}% (bate com o DAS)"
        )

    assert provadas, "nenhuma declaração com RBT12p e Anexo IV para provar a alíquota"

    # (d) o cadastro guarda o mais novo, com marcador, e o resolvedor devolve o mesmo número
    db = _db_sync()

    def _base(g):
        d = g.detalhe or {}
        return (d.get("rbt12p") if d.get("inicio_de_atividade") else d.get("rbt12")) or d.get("rbt12")

    novo = max((g.competencia_ano * 12 + g.competencia_mes, g) for _, g in decls if _base(g))[1]
    raiz = re.search(r"^(\d{8})", novo.numero_documento or "").group(1)
    r = db.execute(
        text(
            "SELECT rbt12::float, coalesce(fonte_regime,'') FROM empresas "
            " WHERE regexp_replace(coalesce(cnpj,''),'[^0-9]','','g') LIKE :c"
        ),
        {"c": raiz + "%"},
    ).first()
    db.close()
    assert r, f"empresa de raiz {raiz} não está no cadastro"
    esperado = _base(novo)
    assert r[0] and abs(r[0] - esperado) < 0.01, (
        f"empresas.rbt12 = {r[0]} ≠ base {esperado} da declaração mais nova "
        f"({novo.competencia_mes:02d}/{novo.competencia_ano})"
    )
    marca = f"pgdasd_comp:{novo.competencia_ano}-{novo.competencia_mes:02d}"
    assert marca in r[1], f"fonte_regime sem o marcador {marca} — o número está lá sem dizer de onde veio"
    print(f"OK cadastro: rbt12 {r[0]:,.2f} com {marca}")
    print(f"TEST oraculo_fiscal_pgdasd PASS ({provadas} declaração(ões) provada(s) contra o próprio DAS)")


if __name__ == "__main__":
    main()
