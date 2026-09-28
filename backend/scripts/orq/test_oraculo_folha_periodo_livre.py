"""ORÁCULO — folha de ponto por PERÍODO LIVRE (data de início e fim), individual e em LOTE.

Pyetra, 28/09/2026: «Não consigo colocar data de início e fim das folhas de ponto quando vou
verificar os pontos ou emitir elas todas». A janela dela é 26/07 a 25/08 — não é mês civil nenhum.

Afirma REGRA, nunca fotografia: nenhum id, nome, data ou total está escrito aqui. O sujeito
(colaborador + duas competências consecutivas calculadas) é DESCOBERTO no banco, e a janela é
derivada dele com `janela_26a25`. Se o mês virar, o oráculo troca de sujeito sozinho.

Irmão de `test_oraculo_espelho_janela_26a25.py`, que prova a janela 26→25 do espelho individual.
Este prova o PERÍODO LIVRE (qualquer ini..fim) e o caminho do LOTE, que não tinham cobertura.

As 5 regras sob prova:

  R1 — PERÍODO PEDIDO É O PERÍODO IMPRESSO: `espelho_do_periodo(ini, fim)` devolve exatamente os
       dias de `ini` a `fim`, um por dia de calendário, e o PDF imprime essas datas. Qualquer
       recorte, não só 26→25 — inclusive um que não começa em 26 nem termina em 25.

  R2 — TOTAL NÃO MENTE A JANELA: os totais são SEMPRE do mês civil de `fim` (`ler_espelho` filtra
       `time_sheets` por reference_month/year). Logo o PDF do período NÃO pode rotular a caixa de
       somas como "TOTAIS DO PERÍODO": tem que nomear a competência. Prova dupla — o rótulo diz o
       mês E os números batem, campo por campo, com `ler_espelho` desse mês (se divergissem,
       alguém teria criado a quarta régua de apuração desta casa).
       Idem a nota de anomalias, que também conta o mês civil.

  R3 — CONTROLE (irmã de caminho feliz da R2): sem período, o PDF do mês civil continua
       "TOTAIS DO PERÍODO" e não imprime período nenhum no cabeçalho. Uma regra que rotula tudo o
       tempo todo não prova nada.

  R4 — HOMOLOGAÇÃO É DO DOCUMENTO LEGAL: `document_hash` é o hash DO PDF gerado; mandar o
       colaborador assinar o hash de uma folha de período registraria assinatura sobre documento
       diferente do legal. `de`/`ate` NÃO homologam (e a guarda tem de observar o DOCUMENTO — o
       `janela` default é "mes" mesmo quando há período, então quem observa o PEDIDO passa batido).
       O mês civil AINDA homologa (espião, ida e volta).

  R5 — LOTE FALHA FECHADO E RESPEITA O PERÍODO: uma data só (sem a outra) é recusada em vez de o
       sistema inventar a metade que falta; período invertido é recusado; e com as duas datas o
       lote deriva a competência dos totais do mês do FIM — nunca do campo de competência, senão
       sairiam dias de agosto sob somas de julho. O PDF do lote sai com o período em cada página.

Read-only: só SELECT e PDF em memória. R4 troca a homologação por um espião, então nada é gravado
nem no caminho feliz.

Rodar:  docker exec conecta-pro-backend python /app/scripts/orq/test_oraculo_folha_periodo_livre.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

falhas: list[str] = []


def ok(nome: str, cond: bool, detalhe: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {nome}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        falhas.append(nome)


def _texto_pdf(pdf: bytes) -> str:
    import pymupdf

    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return "\n".join(p.get_text() for p in doc)


def _rotulo_totais(txt: str) -> str:
    return next((ln for ln in txt.splitlines() if ln.startswith("TOTAIS")), "<sem bloco de totais>")


def _sujeito(db):
    """Colaborador com DUAS competências consecutivas calculadas — é o que a janela 26→25 exige.

    Descoberto no banco: sem os dois meses, os dias 26→31 cairiam no fallback de batida crua e a
    R1 mediria o fallback em vez do motor.
    """
    r = db.execute(
        text(
            "SELECT a.employee_id::text, a.reference_month, a.reference_year "
            "FROM time_sheets a JOIN time_sheets b "
            "  ON b.employee_id = a.employee_id AND COALESCE(b.is_deleted,false)=false "
            " AND b.daily_summary IS NOT NULL "
            " AND ((a.reference_month > 1 AND b.reference_month = a.reference_month - 1 AND b.reference_year = a.reference_year) "
            "   OR (a.reference_month = 1 AND b.reference_month = 12 AND b.reference_year = a.reference_year - 1)) "
            "WHERE COALESCE(a.is_deleted,false)=false AND a.daily_summary IS NOT NULL "
            "ORDER BY a.reference_year DESC, a.reference_month DESC, "
            "  jsonb_array_length(a.daily_summary::jsonb) DESC LIMIT 1"
        )
    ).first()
    if not r:
        print("SEM DUAS COMPETÊNCIAS CONSECUTIVAS calculadas — oráculo não aplicável (aguardando dado).")
        sys.exit(0)
    return r[0], int(r[1]), int(r[2])


def main() -> int:  # noqa: C901
    from modules.people_management.hr.controllers import espelho_ponto_controller as ctrl
    from modules.people_management.hr.services import espelho_ponto_service as svc
    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.ponto.dias_corridos import espelho_do_periodo, janela_26a25

    with get_sync_db() as db:
        eid, mes, ano = _sujeito(db)
        ini, fim = janela_26a25(mes, ano)
        print(f"sujeito descoberto no banco: employee={eid} competência={mes:02d}/{ano} período={ini}..{fim}")

        esp_mes = svc.ler_espelho(db, eid, mes, ano) or {}

        # ── R1 — o período pedido é o período impresso ─────────────────────────────────────────
        print("\nR1 — o período PEDIDO é o período IMPRESSO (qualquer recorte, não só 26→25)")
        esp_per = None
        try:
            esp_per = espelho_do_periodo(db, eid, ini, fim)
            dias = [str(d.get("date") or d.get("data"))[:10] for d in (esp_per or {}).get("dias") or []]
            esperado = [(ini + timedelta(days=i)).isoformat() for i in range((fim - ini).days + 1)]
            ok("devolve espelho para o período", bool(esp_per))
            ok("uma linha por dia, sequência exata de ini a fim", dias == esperado,
               f"{len(dias)} linhas de {dias[0] if dias else '—'} a {dias[-1] if dias else '—'}")
            ok("cabeçalho carrega o período pedido",
               (esp_per or {}).get("periodo_kit") == f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}",
               str((esp_per or {}).get("periodo_kit")))
            # RECORTE ARBITRÁRIO: o que prova que é período LIVRE e não outro atalho 26→25.
            i2, f2 = ini + timedelta(days=3), fim - timedelta(days=7)
            d2 = [str(x.get("date") or x.get("data"))[:10] for x in (espelho_do_periodo(db, eid, i2, f2) or {}).get("dias") or []]
            ok("recorte arbitrário (não começa em 26 nem termina em 25) é respeitado",
               d2 == [(i2 + timedelta(days=i)).isoformat() for i in range((f2 - i2).days + 1)],
               f"pedido {i2}..{f2} → {len(d2)} linhas")
            txt_p = _texto_pdf(montar_espelho_ponto_pdf(dict(esp_per)))
            ok("o PDF imprime as datas do período", f"{ini:%d/%m/%Y}" in txt_p.replace("\n", " "))
        except Exception as e:  # noqa: BLE001
            ok("R1 executou", False, f"{type(e).__name__}: {e}")
            txt_p = ""

        # ── R2 — os totais não mentem a janela ────────────────────────────────────────────────
        print("\nR2 — totais são do mês civil de `fim`; o PDF do período tem que dizer isso")
        try:
            ok("NÃO rotula as somas como 'do período'", "TOTAIS DO PERÍODO" not in txt_p,
               "senão são dias de outra janela somados como mês civil, sem aviso")
            ok("o rótulo nomeia a competência dos totais",
               f"{mes:02d}/{ano}" in _rotulo_totais(txt_p) and "MÊS CIVIL" in _rotulo_totais(txt_p),
               _rotulo_totais(txt_p))
            # Prova que os números NÃO foram recalculados: bate campo por campo com o mês civil.
            # Uma soma própria aqui seria a quarta régua de apuração da casa.
            campos = ("horas_trabalhadas", "horas_previstas", "saldo_banco", "extras_50", "extras_100",
                      "adicional_noturno", "atrasos", "faltas_dias", "dsr_dias", "dsr_perdidos")
            iguais = [c for c in campos if (esp_per or {}).get(c) == esp_mes.get(c)]
            ok("nenhum total foi recalculado (idênticos ao mês civil, campo por campo)",
               len(iguais) == len(campos), f"{len(iguais)}/{len(campos)} idênticos")
            if int(esp_mes.get("anomaly_count") or 0):
                ok("a nota de anomalias também nomeia a competência (conta o mês civil)",
                   "Este período possui" not in txt_p, f"anomalias={esp_mes.get('anomaly_count')}")
            else:
                ok("a nota de anomalias também nomeia a competência (conta o mês civil)", True,
                   "sujeito sem anomalia no mês — não aplicável")
        except Exception as e:  # noqa: BLE001
            ok("R2 executou", False, f"{type(e).__name__}: {e}")

        # ── R3 — controle: sem período nada muda ──────────────────────────────────────────────
        print("\nR3 — controle: sem período, o mês civil continua exatamente como era")
        try:
            txt_m = _texto_pdf(montar_espelho_ponto_pdf(dict(esp_mes)))
            ok("mês civil mantém 'TOTAIS DO PERÍODO'", "TOTAIS DO PERÍODO" in txt_m, _rotulo_totais(txt_m))
            ok("mês civil não imprime período de outra janela", "· período " not in txt_m.replace("\n", " "))
        except Exception as e:  # noqa: BLE001
            ok("R3 executou", False, f"{type(e).__name__}: {e}")

        # ── R4 — homologação só do documento legal ────────────────────────────────────────────
        print("\nR4 — homologação é do mês civil; a folha por período NÃO homologa")
        chamadas: list[str] = []
        original = svc.garantir_homologacao_espelho
        svc.garantir_homologacao_espelho = lambda db_, *, esp, pdf_bytes=None: chamadas.append(  # type: ignore[assignment]
            str(esp.get("periodo_kit") or "mes")
        )
        try:
            # `janela="mes"` vai EXPLÍCITO junto com de/ate, e é o que torna esta regra afiada:
            # é o caso REAL (a tela não manda `janela`, o FastAPI preenche o default "mes") e é
            # exatamente onde uma guarda que observa o PEDIDO — `if janela == "mes"` — homologaria o
            # documento do período. ⚠️ Não deixar no default do Python: chamada direta não passa
            # pelo FastAPI, `janela` chegaria como o objeto Query e o `== "mes"` daria False por
            # acidente. Verde por motivo errado é oráculo cúmplice — medido: com a guarda antiga
            # montada, este teste passava sem `janela="mes"` e só ficou vermelho com ele.
            ctrl.baixar_espelho_pdf(eid, mes, ano, janela="mes", de=ini.isoformat(), ate=fim.isoformat(),
                                    current_user=None, db=db)
            ok("período livre NÃO homologa, mesmo com janela='mes' explícito", chamadas == [], f"chamadas={chamadas}")
            # `de`/`ate` OMITIDOS de propósito nas duas chamadas abaixo (não `de=None`): chamada
            # direta não passa pelo FastAPI, então os defaults chegam como o objeto `Query`, que é
            # TRUTHY. Passar None explícito esconderia o defeito — foi assim que ele escapou e
            # quebrou o oráculo irmão com "fromisoformat: argument must be str".
            ctrl.baixar_espelho_pdf(eid, mes, ano, janela="26a25", current_user=None, db=db)
            ok("janela 26→25 NÃO homologa (chamada direta, de/ate omitidos)", chamadas == [], f"chamadas={chamadas}")
            ctrl.baixar_espelho_pdf(eid, mes, ano, janela="mes", current_user=None, db=db)
            ok("mês civil AINDA homologa (caminho feliz, de/ate omitidos)", chamadas == ["mes"], f"chamadas={chamadas}")
        except Exception as e:  # noqa: BLE001
            ok("R4 executou", False, f"{type(e).__name__}: {e}")
        finally:
            svc.garantir_homologacao_espelho = original  # type: ignore[assignment]

        # ── R5 — o LOTE: falha fechado e deriva a competência do FIM ──────────────────────────
        print("\nR5 — lote: meia data é recusada, e a competência dos totais vem do mês do FIM")
        try:
            from fastapi import HTTPException

            from modules.operacional.controllers.redesign_builders import _dgx_f7_ponto as f7

            def _recusa(payload: dict) -> str | None:
                try:
                    f7._filtros_lote(payload)
                    return None
                except HTTPException as h:
                    return str(h.detail)

            base = {"competencia": f"{mes:02d}/{ano}"}
            ok("só data de início → recusa (não inventa o fim)",
               bool(_recusa({**base, "de": ini.isoformat()})), _recusa({**base, "de": ini.isoformat()}) or "ACEITOU")
            ok("só data final → recusa (não inventa o início)",
               bool(_recusa({**base, "ate": fim.isoformat()})), _recusa({**base, "ate": fim.isoformat()}) or "ACEITOU")
            ok("período invertido → recusa",
               bool(_recusa({**base, "de": fim.isoformat(), "ate": ini.isoformat()})))
            ok("as duas datas → aceita", _recusa({**base, "de": ini.isoformat(), "ate": fim.isoformat()}) is None)
            # A competência dos totais é DERIVADA do fim, nunca lida do campo: competência errada
            # no formulário não pode fazer o PDF somar um mês debaixo dos dias de outro.
            errada = date(ini.year, ini.month, 1)
            f = f7._filtros_lote({"competencia": f"{errada.month:02d}/{errada.year}",
                                  "de": ini.isoformat(), "ate": fim.isoformat()})
            ok("competência derivada do mês do FIM, ignorando o campo",
               (f["mes"], f["ano"]) == (fim.month, fim.year),
               f"campo dizia {errada.month:02d}/{errada.year}, valeu {f['mes']:02d}/{f['ano']}")
            ok("o período viaja nos filtros do lote", (f["de"], f["ate"]) == (ini, fim))
            # E o PDF do lote sai com o período impresso (uma página, o sujeito descoberto).
            from modules.people_management.ponto import cartao_lote

            pdf_lote, relato = cartao_lote.montar_cartao_lote(db, fim.month, fim.year, [eid], de=ini, ate=fim)
            txt_l = _texto_pdf(pdf_lote) if pdf_lote else ""
            ok("lote gera página para quem tem espelho", bool(pdf_lote) and any("paginas" in r for r in relato),
               f"relato={relato}")
            ok("a página do lote traz o período, não o mês civil",
               f"{ini:%d/%m/%Y}" in txt_l.replace("\n", " ") and "TOTAIS DO PERÍODO" not in txt_l,
               _rotulo_totais(txt_l))
        except Exception as e:  # noqa: BLE001
            ok("R5 executou", False, f"{type(e).__name__}: {e}")

    print("\n" + ("TODOS VERDES" if not falhas else f"{len(falhas)} FALHA(S): " + "; ".join(falhas)))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
