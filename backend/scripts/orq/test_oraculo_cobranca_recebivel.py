#!/usr/bin/env python3
"""Cobrança bancária da conta a receber: roteia pela empresa credora e recusa o que não pode.

Regra do dono (07/09/2026): boleto/PIX nasce no Conecta PRO — Eletrônica → Inter, Patrimonial →
Cora. Este oráculo NÃO chama banco: usa preview=True em contas de TESTE (marcadas ORACULO,
pagador = o CNPJ da própria empresa) e afirma a regra: roteamento pela `empresa_id` da conta,
conta paga/vencida/sem documento/abaixo de R$ 5 é recusada, conta já emitida não reemite.
Apaga tudo o que criou.

Telas que este oráculo vigia (mesmo serviço por trás dos botões): "contas-receber" (Emitir
cobrança por linha), "recorrencia" (prévia do mês), "gerar-cobrancas" (emissão do mês) e
"nfse-emitidas" (Gerar boleto na nota → emitir_por_nota).

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_cobranca_recebivel.py
"""

import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")
import main_production  # noqa: E402,F401

MARCA = f"ORACULO-COB-{uuid.uuid4().hex[:8]}"
COND = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
ELET, PATR = "619a3df1-8bce-49ce-b77a-04f80a0e8491", "7d79ed12-d480-4906-b2e0-2b2c4d299bab"


def main() -> None:
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.financial.services.cobranca_recebivel_service import emitir, emitir_por_nota

    def nota(db, empresa, doc, comp, valor=5.0, cancelada=False, numero=None):
        chave = f"{MARCA}-{uuid.uuid4().hex[:20]}"
        db.execute(
            text(
                "INSERT INTO nfse_emitidas_nacional (chave_acesso, numero, competencia, data_emissao, tomador_cnpj, tomador_nome, "
                " valor_servicos, empresa_id, cancelada, fonte, created_at) VALUES (:ch, :num, :comp, now(), :doc, :nome, :v, "
                " CAST(:emp AS uuid), :canc, 'oraculo', now())"
            ),
            # Número PRÓPRIO por nota: `document_number` é UNIQUE por condomínio, e todas as
            # notas com '999999' colidiam entre si — foi assim que este oráculo achou, antes
            # da produção, que gravar o número puro estoura com a numeração por empresa.
            {
                "ch": chave,
                "num": numero or "999999",
                "comp": comp,
                "doc": doc,
                "nome": f"CLIENTE {MARCA}",
                "v": valor,
                "emp": empresa,
                "canc": cancelada,
            },
        )
        db.commit()
        return chave

    def cria(db, empresa, doc, valor=5.0, dias=3, status="pendente", boleto_id=None, ref=None):
        rid = str(uuid.uuid4())
        db.execute(
            text(
                "INSERT INTO receivable_accounts (id, condominio_id, empresa_id, code, customer_name, customer_document, description, "
                " gross_value, net_value, issue_date, due_date, competence_date, status, origem, boleto_id, reference_month, created_at, updated_at) "
                "VALUES (CAST(:id AS uuid), CAST(:cond AS uuid), CAST(:emp AS uuid), :code, :nome, :doc, :desc, :v, :v, current_date, "
                " current_date + CAST(:dias AS int), current_date, :st, 'contrato', :bid, :ref, now(), now())"
            ),
            {
                "id": rid,
                "cond": COND,
                "emp": empresa,
                "code": f"{MARCA}-{rid[:4]}",
                "nome": f"CLIENTE {MARCA}",
                "doc": doc,
                "desc": f"Serviços {MARCA}",
                "v": valor,
                "dias": dias,
                "st": status,
                "bid": boleto_id,
                "ref": ref,
            },
        )
        db.commit()
        return rid

    with SyncSessionLocal() as db:
        try:
            r_patr = cria(db, PATR, "66.014.833/0001-10")
            r_elet = cria(db, ELET, "35.710.481/0001-03")
            r_paga = cria(db, PATR, "66014833000110", status="paga")
            r_venc = cria(db, PATR, "66014833000110", dias=-2)
            r_semd = cria(db, PATR, "")
            r_baixo = cria(db, PATR, "66014833000110", valor=4.99)
            r_ja = cria(db, PATR, "66014833000110", boleto_id="inv_ORACULO")

            a = emitir(r_patr, preview=True)
            assert a["ok"] and a["banco"] == "cora" and a["situacao"] == "preview", a
            b = emitir(r_elet, preview=True)
            assert b["ok"] and b["banco"] == "inter" and b["situacao"] == "preview", b
            print("OK roteamento: Patrimonial → Cora, Eletrônica → Inter (preview, sem chamar banco)")
            for rid, nome, trecho in (
                (r_paga, "paga", "status"),
                (r_venc, "vencida", "vencimento"),
                (r_semd, "sem documento", "CPF/CNPJ"),
                (r_baixo, "abaixo de R$ 5", "mínimo"),
            ):
                r = emitir(rid, preview=True)
                assert r.get("erro") and trecho in r["erro"], (nome, r)
            print("OK recusas: paga, vencida, sem documento e abaixo de R$ 5 não emitem")
            j = emitir(r_ja, preview=True)
            assert j["ok"] and j["situacao"] == "ja_emitida" and j["boleto_id"] == "inv_ORACULO", j
            print("OK idempotência: conta já emitida não reemite")

            # Fluxo natural nota → boleto: a nota acha a conta em aberto da mesma empresa/tomador/competência
            comp = date.today().strftime("%Y-%m")
            ref = date.today().strftime("%m/%Y")
            r_nota = cria(db, PATR, "11.222.333/0001-81", ref=ref)
            n_ok = nota(db, PATR, "11222333000181", comp)
            n_sem = nota(db, PATR, "99.888.777/0001-66", comp)
            n_canc = nota(db, PATR, "11222333000181", comp, cancelada=True)
            n_outra = nota(db, ELET, "11222333000181", comp)  # mesma pessoa, outra empresa credora → não casa
            x = emitir_por_nota(n_ok, preview=True)
            assert (
                x["ok"]
                and x["id"] == r_nota
                and x["banco"] == "cora"
                and x["situacao"] == "preview"
                and x["nota"] == "999999"
            ), x
            for ch, trecho in ((n_sem, "nenhuma conta"), (n_canc, "cancelada"), (n_outra, "nenhuma conta")):
                r = emitir_por_nota(ch, preview=True)
                assert r.get("erro") and trecho in r["erro"], (ch, r)
            assert "não encontrada" in emitir_por_nota("nao-existe", preview=True)["erro"]
            print(
                "OK nota → boleto: casa por empresa+tomador+competência; sem conta, cancelada e outra empresa recusam"
            )

            # ── O VÍNCULO GRAVADO (18/09/2026) ──────────────────────────────────────
            # O palpite por competência resolvia 14 de 14 notas de ago/set, e não alcança
            # contrato de VALOR ÚNICO: aquelas parcelas nascem sem `reference_month` porque
            # vencem em DATAS, não em meses. Pior: ele é recalculado a cada consulta e não
            # deixa rastro — ninguém, olhando a conta, sabe qual nota a cobre.
            #
            # A parede que mais importa aqui é a RECUSA POR AMBIGUIDADE. Um contrato de valor
            # único tem várias parcelas em aberto do mesmo tomador ao mesmo tempo (o
            # CTR-2026-00022 tem três). Escolher "a de valor mais próximo" ali seria pendurar
            # a nota na parcela errada em silêncio — o dinheiro some do lugar certo e aparece
            # no errado, e nada acusa.
            from modules.financial.services.cobranca_recebivel_service import vincular_nota

            # sem reference_month de propósito: é a forma das parcelas de valor único
            r_u1 = cria(db, PATR, "44555666000177", valor=100.0)
            n_u = nota(db, PATR, "44555666000177", comp, valor=100.0, numero="900001")

            v = vincular_nota(n_u, preview=True)
            assert v["ok"] and v["situacao"] == "preview", v
            v = vincular_nota(n_u)
            assert v["ok"] and v["situacao"] == "vinculada" and v["receivable_id"] == r_u1, v

            grav = db.execute(
                text("SELECT document_number, metadata->>'nfse_chave' FROM receivable_accounts WHERE id::text = :i"),
                {"i": r_u1},
            ).first()
            assert grav[0] == "900001-PATR" and grav[1] == n_u, grav

            # 1 · o vínculo gravado é lido pelo caminho nota → boleto, SEM competência casar
            x = emitir_por_nota(n_u, preview=True)
            assert x["ok"] and x["id"] == r_u1, ("vínculo gravado não foi lido", x)

            # 2 · idempotente: de novo não escreve, diz que já está
            v2 = vincular_nota(n_u)
            assert v2["ok"] and v2["situacao"] == "ja_vinculada", v2

            # 3 · AMBIGUIDADE É RECUSADA, não adivinhada — duas parcelas em aberto do mesmo
            #     tomador, como num contrato de valor único
            r_u2 = cria(db, PATR, "77888999000144", valor=100.0)
            r_u3 = cria(db, PATR, "77888999000144", valor=250.0)
            n_amb = nota(db, PATR, "77888999000144", comp, valor=100.0, numero="900002")
            amb = vincular_nota(n_amb)
            assert not amb["ok"] and amb.get("situacao") == "ambiguo", amb
            assert len(amb["candidatas"]) == 2, amb
            assert (
                db.execute(
                    text(
                        "SELECT count(*) FROM receivable_accounts WHERE id::text IN (:a, :b) "
                        "AND coalesce(metadata->>'nfse_chave','') <> ''"
                    ),
                    {"a": r_u2, "b": r_u3},
                ).scalar()
                == 0
            ), "recusou e ESCREVEU mesmo assim"

            # 4 · com a conta dita na mão, vincula a essa e não a outra
            v3 = vincular_nota(n_amb, receivable_id=r_u3)
            assert v3["ok"] and v3["receivable_id"] == r_u3, v3

            # 5 · a mesma nota não serve duas contas, e a conta com nota não é roubada
            assert "já está vinculada à conta" in (vincular_nota(n_amb, receivable_id=r_u2).get("erro") or ""), (
                "a mesma nota foi pendurada em duas contas"
            )
            n_outra2 = nota(db, PATR, "77888999000144", comp, valor=250.0, numero="900003")
            assert "já está vinculada a OUTRA nota" in (
                vincular_nota(n_outra2, receivable_id=r_u3).get("erro") or ""
            ), "a conta aceitou uma segunda nota"

            # 6 · conta já vinculada sai do palpite: a nota nova não a rouba por semelhança
            y = emitir_por_nota(n_outra2, preview=True)
            assert y.get("erro"), ("o palpite roubou uma conta que já tem nota", y)

            # 7 · competência incompatível não é escolhida sozinha: uma nota de julho não
            #     gruda na conta de setembro que estiver aberta. Conta de valor único (sem
            #     competência) continua passando — é o caso que o vínculo resolve.
            r_set = cria(db, PATR, "12121212000199", valor=300.0, ref="09/2026")
            n_jul = nota(db, PATR, "12121212000199", "2026-07", valor=300.0, numero="900004")
            inc = vincular_nota(n_jul)
            assert not inc["ok"] and "outra competência" in (inc.get("erro") or ""), inc
            assert (
                db.execute(
                    text("SELECT coalesce(metadata->>'nfse_chave','') FROM receivable_accounts WHERE id::text = :i"),
                    {"i": r_set},
                ).scalar()
                == ""
            ), "recusou por competência e escreveu mesmo assim"
            assert vincular_nota(n_jul, receivable_id=r_set)["ok"], "com a conta na mão devia deixar"

            assert "cancelada" in (vincular_nota(n_canc).get("erro") or ""), "vinculou nota cancelada"
            assert "não encontrada" in (vincular_nota("nao-existe").get("erro") or "")
            print("OK vínculo nota↔conta: gravado, idempotente, recusa ambiguidade e nota/conta já usadas")
        finally:
            db.execute(text("DELETE FROM receivable_accounts WHERE code LIKE :m"), {"m": f"{MARCA}%"})
            db.execute(text("DELETE FROM nfse_emitidas_nacional WHERE chave_acesso LIKE :m"), {"m": f"{MARCA}%"})
            db.commit()
            sobras = db.execute(
                text("SELECT count(*) FROM receivable_accounts WHERE code LIKE :m"), {"m": f"{MARCA}%"}
            ).scalar()
            print(f"LIMPEZA OK — {sobras} remanescente(s)")
            assert sobras == 0
    print("TEST oraculo_cobranca_recebivel PASS")


if __name__ == "__main__":
    main()
