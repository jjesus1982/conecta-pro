"""ORÁCULO — espelho de ponto impresso na janela 26/x → 25/y (folha de ponto do DP).

Afirma REGRA, nunca fotografia: nenhum id, nome, data ou total está escrito aqui. O sujeito
(colaborador + competência) é DESCOBERTO no banco — a última competência com espelho calculado e
o colaborador com mais dias apurados nela. Se o mês virar, o oráculo troca de sujeito sozinho.

As 4 regras sob prova:

  R1 — JANELA CORRIDA: `dias_corridos(ini..fim)` devolve TODOS os dias do intervalo, uma linha por
       dia de calendário, começando em `ini` e terminando em `fim`, sem furo e sem repetição; dia
       sem batida nenhuma aparece declarado ("Folga / sem registro"), nunca omitido.

  R2 — TOTAL NÃO MENTE A JANELA: os totais de `ler_espelho` são SEMPRE do mês civil
       (`time_sheets` filtrado por reference_month/year). Logo, quando a tabela de dias é de OUTRA
       janela (`periodo_kit` presente), o PDF não pode rotular a caixa de somas como "TOTAIS DO
       PERÍODO" — tem que nomear o mês civil de onde os números vieram. Dias de um período com
       somas de outro sob rótulo ambíguo é o defeito que este oráculo existe para pegar.

  R3 — CONTROLE (irmã de caminho feliz da R2): sem troca de janela, o rótulo continua
       "TOTAIS DO PERÍODO". Uma regra que rotula tudo o tempo todo não prova nada.

  R4 — FOLHA 26→25 NÃO HOMOLOGA: a homologação carimba o hash DESTE pdf; assinar o hash da folha
       26→25 registraria assinatura sobre documento diferente do legal. `janela=26a25` não chama
       `garantir_homologacao_espelho`; `janela=mes` chama (espião, ida e volta).

Read-only: só SELECT e geração de PDF em memória. R4 substitui a homologação por um espião, então
nada é gravado nem no caminho feliz.

Rodar:  docker exec conecta-pro-backend python /app/scripts/orq/test_oraculo_espelho_janela_26a25.py
"""

from __future__ import annotations

import sys
from datetime import timedelta

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

falhas: list[str] = []


def ok(nome: str, cond: bool, detalhe: str = "") -> None:
    print(f"  {'✅' if cond else '❌'} {nome}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        falhas.append(nome)


def _texto_pdf(pdf: bytes) -> str:
    import fitz

    with fitz.open(stream=pdf, filetype="pdf") as doc:
        return "\n".join(p.get_text() for p in doc)


def _sujeito(db):
    """Descobre sujeito no banco: última competência calculada + quem tem mais dias nela."""
    r = db.execute(
        text(
            "SELECT employee_id::text, reference_month, reference_year "
            "FROM time_sheets WHERE COALESCE(is_deleted,false)=false AND daily_summary IS NOT NULL "
            "ORDER BY reference_year DESC, reference_month DESC, "
            "jsonb_array_length(daily_summary::jsonb) DESC LIMIT 1"
        )
    ).first()
    if not r:
        print("SEM ESPELHO CALCULADO EM time_sheets — oráculo não aplicável (aguardando dado).")
        sys.exit(0)
    return r[0], int(r[1]), int(r[2])


def main() -> int:
    from modules.people_management.hr.controllers import espelho_ponto_controller as ctrl
    from modules.people_management.hr.services import espelho_ponto_service as svc
    from modules.people_management.hr.services.espelho_ponto_pdf import montar_espelho_ponto_pdf
    from modules.people_management.ponto.dias_corridos import dias_corridos, janela_26a25

    with get_sync_db() as db:
        eid, mes, ano = _sujeito(db)
        ini, fim = janela_26a25(mes, ano)
        print(f"sujeito descoberto no banco: employee={eid} competência={mes:02d}/{ano} janela={ini}..{fim}")

        # ── R1 — janela corrida ────────────────────────────────────────────────────────────────
        print("\nR1 — janela corrida (todos os dias do intervalo, nenhum furo)")
        try:
            esp_mes = svc.ler_espelho(db, eid, mes, ano) or {}
            ant = svc.ler_espelho(db, eid, ini.month, ini.year) or {}
            dias = dias_corridos(db, eid, ini, fim, (ant.get("dias") or []) + (esp_mes.get("dias") or []))
            esperado = (fim - ini).days + 1
            datas = [str(d.get("date") or d.get("data"))[:10] for d in dias]
            seq = [(ini + timedelta(days=i)).isoformat() for i in range(esperado)]
            ok("uma linha por dia de calendário", len(dias) == esperado, f"{len(dias)} linhas, esperado {esperado}")
            ok("sequência exata (sem furo, sem repetição, 26→25)", datas == seq,
               f"começa {datas[0] if datas else '—'} termina {datas[-1] if datas else '—'}")
            ok("dia sem batida é declarado, não omitido",
               esperado == len(dias) and all(str(d.get("ocorrencia") or d.get("observacao") or d.get("status") or "") != "" or d.get("entrada") for d in dias),
               "toda linha carrega ocorrência ou horário")
            ok("janela_26a25 fecha em 25 e abre em 26", (ini.day, fim.day) == (26, 25))
            # PRECEDÊNCIA: é disto que depende juntar o espelho do mês anterior (os dias 26→31).
            # Se a batida crua (min/max do dia, que não junta noturno) vencesse o dia apurado, a
            # folha teria duas réguas de jornada na mesma tabela.
            alvo = next((str(d.get("date"))[:10] for d in dias if d.get("ocorrencia") in ("Registro de ponto", "Batida única")), None)
            if alvo:
                marcado = {"date": alvo, "entrada": "01:01", "saida": "02:02", "ocorrencia": "APURADO PELO MOTOR"}
                linha = next(x for x in dias_corridos(db, eid, ini, fim, [marcado]) if str(x.get("date"))[:10] == alvo)
                ok("dia apurado pelo motor vence a batida crua", linha is marcado, f"data {alvo}")
            else:
                ok("dia apurado pelo motor vence a batida crua", True, "sem dia de batida crua na janela — não aplicável")
        except Exception as e:  # noqa: BLE001
            ok("R1 executou", False, f"{type(e).__name__}: {e}")
            dias, esp_mes = [], {}

        # ── R2 — o rótulo dos totais não pode mentir a janela ──────────────────────────────────
        print("\nR2 — totais são do mês civil; com dias de outra janela o rótulo tem que dizer isso")
        try:
            esp_janela = dict(esp_mes)
            esp_janela["dias"] = dias
            esp_janela["periodo_kit"] = f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}"
            txt_j = _texto_pdf(montar_espelho_ponto_pdf(esp_janela))
            ok("o período impresso é o pedido", f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}" in txt_j.replace("\n", " "))
            ok("NÃO rotula as somas como 'do período'", "TOTAIS DO PERÍODO" not in txt_j,
               "senão são dias de 26→25 somados como mês civil, sem aviso")
            ok("nomeia o mês civil dos totais (ou omite o bloco)",
               (f"{mes:02d}/{ano}" in txt_j.split("TOTAIS")[-1] if "TOTAIS" in txt_j else True)
               and ("Horas trabalhadas" not in txt_j or "TOTAIS" in txt_j),
               "rótulo encontrado: " + next((ln for ln in txt_j.splitlines() if ln.startswith("TOTAIS")), "<bloco ausente>"))
        except Exception as e:  # noqa: BLE001
            ok("R2 executou", False, f"{type(e).__name__}: {e}")

        # ── R3 — controle: mês civil continua "do período" ─────────────────────────────────────
        print("\nR3 — controle: sem troca de janela o rótulo NÃO muda")
        try:
            txt_m = _texto_pdf(montar_espelho_ponto_pdf(dict(esp_mes)))
            ok("mês civil mantém 'TOTAIS DO PERÍODO'", "TOTAIS DO PERÍODO" in txt_m)
            ok("mês civil não imprime período de outra janela", "período 26/" not in txt_m.replace("\n", " "))
        except Exception as e:  # noqa: BLE001
            ok("R3 executou", False, f"{type(e).__name__}: {e}")

        # ── R4 — folha 26→25 não entra na homologação ─────────────────────────────────────────
        print("\nR4 — homologação é do documento legal (mês civil), não da folha 26→25")
        chamadas: list[str] = []
        original = svc.garantir_homologacao_espelho
        svc.garantir_homologacao_espelho = lambda db_, *, esp, pdf_bytes=None: chamadas.append(  # type: ignore[assignment]
            str(esp.get("periodo_kit") or "mes")
        )
        try:
            ctrl.baixar_espelho_pdf(eid, mes, ano, janela="26a25", current_user=None, db=db)
            ok("janela 26→25 NÃO homologa", chamadas == [], f"chamadas={chamadas}")
            ctrl.baixar_espelho_pdf(eid, mes, ano, janela="mes", current_user=None, db=db)
            ok("mês civil AINDA homologa (caminho feliz)", chamadas == ["mes"], f"chamadas={chamadas}")
        except Exception as e:  # noqa: BLE001
            ok("R4 executou", False, f"{type(e).__name__}: {e}")
        finally:
            svc.garantir_homologacao_espelho = original  # type: ignore[assignment]

    print("\n" + ("TODOS VERDES" if not falhas else f"{len(falhas)} FALHA(S): " + "; ".join(falhas)))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
