#!/usr/bin/env python3
"""O anexo do Simples que ESTÁ no cadastro contra o que a GUIA PAGA mostra.

`empresas.anexo_simples` é lido por duas coisas que decidem dinheiro:
`encargos.encargo_pct_da_empresa()` (32,44% no Anexo III × 55,44% no IV — 23 pontos de
diferença no custo de mão de obra) e `crm.regime_tributario.aliquota_efetiva()` (a faixa
do DAS). Errar esse campo erra os dois, em direções opostas, e o preço parece plausível.

A régua não é opinião nem fonte da internet: é o código de receita 1006 dentro da própria
guia que a empresa pagou. A CPP patronal está DENTRO do DAS no Anexo III e FORA dele no
Anexo IV — essa é a definição dos dois anexos, não uma consequência. Então:

    guia tem 1006 material  ->  III
    guia não tem            ->  IV

"Material" importa: em 27/09/2026 a guia 07/2026 da Patrimonial trazia INSS de R$ 171,06
com 52 funcionários na folha. CPP de 20% sobre aquela folha seria ~R$ 30 mil. R$ 171 é
resíduo, não CPP — tratar qualquer valor > 0 como "tem 1006" faria a trava dizer III para
uma empresa que é IV. O piso compara com a folha, que é o denominador certo.

Achado que originou: cadastro dizia III; o DAS de 08/2026 não tem 1006 nenhum.
"""

import os
import re
import sys

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text  # noqa: E402

# Abaixo disto, a linha de INSS na guia não pode ser CPP patronal: 20% da folha é o piso
# teórico, e mesmo com toda a folha isenta a CPP nunca seria uma fração de porcento dela.
FRACAO_MINIMA_DA_FOLHA = 0.05


def _url() -> str:
    u = os.environ.get("DATABASE_URL") or ""
    if not u:
        from core.config.settings import settings

        u = str(settings.database_url)
    return u.replace("+asyncpg", "")


def main() -> int:
    eng = create_engine(_url())
    achados: list[str] = []
    with eng.connect() as c:
        empresas = (
            c.execute(
                text(
                    "SELECT id::text id, razao_social, cnpj, regime_tributario, anexo_simples "
                    "  FROM empresas WHERE coalesce(regime_tributario,'') = 'simples_nacional'"
                )
            )
            .mappings()
            .all()
        )

        if not empresas:
            print("nenhuma empresa no Simples — nada a comparar")
            print("TOTAL: 0 empresa(s) com anexo do cadastro diferente da guia")
            return 0

        for e in empresas:
            guias = (
                c.execute(
                    text(
                        "SELECT nome_arquivo, detalhes_json->'composicao' comp "
                        "  FROM onvio_documents "
                        " WHERE empresa_id = :eid AND detalhes_json ? 'composicao' "
                        # Parcelamento rateia a parcela entre os tributos ORIGINais da dívida —
                        # pode trazer 1006 de um período em que a empresa era de outro anexo, e
                        # até ICMS. Não serve de régua para o anexo de hoje.
                        "   AND nome_arquivo !~* 'parc' "
                        " ORDER BY nome_arquivo DESC LIMIT 6"
                    ),
                    {"eid": e["id"]},
                )
                .mappings()
                .all()
            )

            if not guias:
                achados.append(
                    f"   ? SEM GUIA   {e['razao_social']}: cadastro diz "
                    f"{e['anexo_simples'] or 'NADA'} e não há DAS extraído para conferir"
                )
                continue

            for g in guias:
                comp = g["comp"] or {}
                inss = float(comp.get("INSS") or 0)
                # A folha da competência da guia, para dizer se aquele INSS é CPP ou resíduo.
                mes = re.search(r"(\d{2})[ _/-](\d{4})", g["nome_arquivo"] or "")
                folha = 0.0
                if mes:
                    folha = float(
                        c.execute(
                            text(
                                "SELECT coalesce(sum(total_earnings),0) FROM hr_payslips "
                                " WHERE reference_year = :a AND reference_month = :m"
                            ),
                            {"a": int(mes.group(2)), "m": int(mes.group(1))},
                        ).scalar()
                        or 0
                    )

                piso = folha * FRACAO_MINIMA_DA_FOLHA
                tem_cpp = inss > piso and inss > 0
                da_guia = "III" if tem_cpp else "IV"
                cadastro = (e["anexo_simples"] or "").upper().strip()

                if cadastro and cadastro != da_guia:
                    achados.append(
                        f"   x {e['razao_social']}: cadastro {cadastro} × guia {da_guia}  "
                        f"({g['nome_arquivo']}: INSS R$ {inss:,.2f}, folha R$ {folha:,.2f})"
                    )
                elif not cadastro:
                    achados.append(
                        f"   x {e['razao_social']}: cadastro SEM ANEXO × guia {da_guia}  ({g['nome_arquivo']})"
                    )
                break  # a guia mais recente manda; as outras são histórico

    for a in achados:
        print(a)
    print(f"TOTAL: {len(achados)} empresa(s) com anexo do cadastro diferente da guia")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
