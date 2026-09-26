"""C5 — o calendário mostra a obrigação que o REGIME exige, não só a que já foi cadastrada.

Nasceu em 25/09/2026, do loop de contabilidade, quando o dono decidiu rescindir com a
contabilidade terceirizada.

O calendário do grupo montava assim:

    por_empresa = {slug: reais.get(slug, obs) for slug, obs in cal.por_empresa.items()}

Bastava **uma** obrigação cadastrada no mês para o molde do regime ser descartado inteiro.
Como ECD, ECF, EFD Contribuições, EFD ICMS/IPI, DCTF e PGDAS-D **nunca foram cadastradas**,
elas nunca apareciam — e é exatamente essa a lista que passa a doer quando quem transmitia
sai. `GET /empresas/obrigacoes/calendario/grupo?mes=9&ano=2026` devolvia
`previstos_pelo_regime: 0`.

Medido em 25/09/2026, antes da correção:

    09/2026 Eletrônica   7 cadastradas · 0 do regime   (invisíveis: DCTF, EFD_CONTRIBUICOES,
                                                        EFD_ICMS_IPI, IRPJ_CSLL_ESTIMATIVA)
    06/2026 Eletrônica   7 cadastradas · 0 do regime   (invisível também: a ECD)
    09/2026 Patrimonial  1 cadastrada  · 0 do regime   (invisíveis: FGTS, ISS, PGDAS_D)

E o motivo de o código ter ficado assim é legítimo: as duas fontes chamam a MESMA obrigação
por nomes diferentes — `FGTS` no cadastro contra `FGTS_GUIA` no molde, `INSS`×`INSS_GPS`,
`ISS`×`ISS_AVULSO`. Mesclar sem essa ponte duplicaria tudo no painel, e alarme repetido
ensina a ignorar o painel tão bem quanto alarme falso.

O QUE ELE AFIRMA

 (a) **O molde não é descartado por haver cadastro.** Em mês com obrigação cadastrada, as do
     regime que faltam continuam aparecendo.

 (b) **Nada duplica.** Nenhuma empresa tem o mesmo tipo (normalizado pela ponte de nomes)
     duas vezes no mesmo mês.

 (c) **O que o Lucro Real exige e nunca foi cadastrado aparece:** EFD Contribuições, EFD
     ICMS/IPI e DCTF todo mês; a ECD em junho.

 (d) **O Simples aparece com o que é dele:** PGDAS-D para a empresa do Simples — declarar é
     ato separado de pagar o DAS.

 (e) **A origem é declarada.** Obrigação vinda do molde carrega `fonte` diferente de
     "cadastro", para o painel distinguir «pendente de verdade» de «prevista e nunca
     cadastrada». Sem isso a mescla viraria uma lista de pendências falsas.

VERMELHO ANTES: com o controller anterior, (a), (c), (d) e (e) falham — o calendário de
setembro tinha 7 linhas, todas do cadastro, e `previstos_pelo_regime = 0`.
"""

from __future__ import annotations

import asyncio
import sys

#: Meses conferidos: um com cadastro (setembro), um sem (outubro) e junho, que é quando a
#: ECD vence.
MESES = (9, 10, 6)
ANO = 2026

#: Obrigações do Lucro Real que o cadastro nunca teve e que precisam aparecer todo mês.
MENSAIS_LUCRO_REAL = {"EFD_CONTRIBUICOES", "EFD_ICMS_IPI", "DCTF"}

#: A ponte de nomes entre o cadastro e o molde, REPETIDA aqui de propósito: importá-la do
#: controller faria a régua perguntar ao medido qual é a medida.
_MESMO_TIPO = {"FGTS_GUIA": "FGTS", "INSS_GPS": "INSS", "ISS_AVULSO": "ISS"}


class _Usuario:
    id = "oraculo"


async def main() -> int:
    from core.database import async_session_factory
    from modules.empresas.controllers import obligations_controller as oc

    falhas: list[str] = []
    medidas: list[str] = []

    for mes in MESES:
        try:
            async with async_session_factory() as db:
                r = await oc.calendario_grupo(mes=mes, ano=ANO, db=db, current_user=_Usuario())
        except Exception as e:  # noqa: BLE001 — oráculo ACUSA, não quebra
            falhas.append(f"({mes:02d}) o calendário levantou {type(e).__name__}: {str(e)[:90]}")
            continue
        por = r.get("por_empresa") or {}
        if not por:
            falhas.append(f"({mes:02d}) o calendário voltou sem `por_empresa` — nada foi medido")
            continue

        total_regime = 0
        for slug, obs in por.items():
            tipos_cad = {
                (o.get("tipo") or "").upper() for o in obs if o.get("fonte") == "cadastro"
            }
            tipos_reg = {
                (o.get("tipo") or "").upper() for o in obs if o.get("fonte") != "cadastro"
            }
            total_regime += len(tipos_reg)

            # (a) molde não é descartado por haver cadastro
            if tipos_cad and not tipos_reg:
                falhas.append(
                    f"(a) {slug} em {mes:02d}/{ANO}: {len(tipos_cad)} cadastrada(s) e ZERO do "
                    "regime — o molde foi descartado por existir cadastro"
                )

            # (b) nada duplica, depois da ponte de nomes
            chaves = [_MESMO_TIPO.get((o.get("tipo") or "").upper(),
                                      (o.get("tipo") or "").upper()) for o in obs]
            repetidos = {k for k in chaves if chaves.count(k) > 1}
            if repetidos:
                falhas.append(f"(b) {slug} em {mes:02d}/{ANO}: tipo repetido no mês: {sorted(repetidos)}")

            # (e) a origem é declarada
            sem_fonte = [o.get("tipo") for o in obs if not (o.get("fonte") or "").strip()]
            if sem_fonte:
                falhas.append(f"(e) {slug} em {mes:02d}/{ANO}: {len(sem_fonte)} obrigação(ões) sem `fonte`")

            todos = tipos_cad | tipos_reg

            # (c) o que o Lucro Real exige e nunca foi cadastrado
            if "eletronica" in slug:
                faltam = MENSAIS_LUCRO_REAL - todos
                if faltam:
                    falhas.append(
                        f"(c) {slug} em {mes:02d}/{ANO}: o painel não mostra {sorted(faltam)}"
                    )
                if mes == 6 and "ECD" not in todos:
                    falhas.append(f"(c) {slug}: a ECD não aparece em junho, que é quando vence")

            # (d) o Simples com o que é dele
            if "patrimonial" in slug and "PGDAS_D" not in todos:
                falhas.append(
                    f"(d) {slug} em {mes:02d}/{ANO}: PGDAS-D não aparece — declarar é ato "
                    "separado de pagar o DAS"
                )

        medidas.append(
            f"{mes:02d}/{ANO}: {r['resumo']['total']} obrigação(ões), "
            f"{r['resumo']['previstos_pelo_regime']} pelo regime"
        )
        if not total_regime:
            falhas.append(f"({mes:02d}) nenhuma obrigação do regime em mês nenhum — molde inerte")

    print(" · ".join(medidas))
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no calendário de obrigações")
    print(
        "OK calendário: o cadastro manda no que existe e o molde do regime completa o que "
        "falta, sem duplicar, com a origem declarada — ECD, EFD Contribuições, EFD ICMS/IPI, "
        "DCTF e PGDAS-D visíveis"
    )
    print(f"TOTAL desvios C5: {len(falhas)}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios C5: >0")
        sys.exit(1)
