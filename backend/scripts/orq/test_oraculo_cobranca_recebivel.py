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

    def nota(db, empresa, doc, comp, valor=5.0, cancelada=False):
        chave = f"{MARCA}-{uuid.uuid4().hex[:20]}"
        db.execute(text(
            "INSERT INTO nfse_emitidas_nacional (chave_acesso, numero, competencia, data_emissao, tomador_cnpj, tomador_nome, "
            " valor_servicos, empresa_id, cancelada, fonte, created_at) VALUES (:ch, '999999', :comp, now(), :doc, :nome, :v, "
            " CAST(:emp AS uuid), :canc, 'oraculo', now())"),
            {"ch": chave, "comp": comp, "doc": doc, "nome": f"CLIENTE {MARCA}", "v": valor, "emp": empresa, "canc": cancelada})
        db.commit()
        return chave

    def cria(db, empresa, doc, valor=5.0, dias=3, status="pendente", boleto_id=None, ref=None):
        rid = str(uuid.uuid4())
        db.execute(text(
            "INSERT INTO receivable_accounts (id, condominio_id, empresa_id, code, customer_name, customer_document, description, "
            " gross_value, net_value, issue_date, due_date, competence_date, status, origem, boleto_id, reference_month, created_at, updated_at) "
            "VALUES (CAST(:id AS uuid), CAST(:cond AS uuid), CAST(:emp AS uuid), :code, :nome, :doc, :desc, :v, :v, current_date, "
            " current_date + CAST(:dias AS int), current_date, :st, 'contrato', :bid, :ref, now(), now())"),
            {"id": rid, "cond": COND, "emp": empresa, "code": f"{MARCA}-{rid[:4]}", "nome": f"CLIENTE {MARCA}", "doc": doc,
             "desc": f"Serviços {MARCA}", "v": valor, "dias": dias, "st": status, "bid": boleto_id, "ref": ref})
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

            a = emitir(r_patr, preview=True); assert a["ok"] and a["banco"] == "cora" and a["situacao"] == "preview", a
            b = emitir(r_elet, preview=True); assert b["ok"] and b["banco"] == "inter" and b["situacao"] == "preview", b
            print("OK roteamento: Patrimonial → Cora, Eletrônica → Inter (preview, sem chamar banco)")
            for rid, nome, trecho in ((r_paga, "paga", "status"), (r_venc, "vencida", "vencimento"), (r_semd, "sem documento", "CPF/CNPJ"), (r_baixo, "abaixo de R$ 5", "mínimo")):
                r = emitir(rid, preview=True)
                assert r.get("erro") and trecho in r["erro"], (nome, r)
            print("OK recusas: paga, vencida, sem documento e abaixo de R$ 5 não emitem")
            j = emitir(r_ja, preview=True); assert j["ok"] and j["situacao"] == "ja_emitida" and j["boleto_id"] == "inv_ORACULO", j
            print("OK idempotência: conta já emitida não reemite")

            # Fluxo natural nota → boleto: a nota acha a conta em aberto da mesma empresa/tomador/competência
            comp = date.today().strftime("%Y-%m"); ref = date.today().strftime("%m/%Y")
            r_nota = cria(db, PATR, "11.222.333/0001-81", ref=ref)
            n_ok = nota(db, PATR, "11222333000181", comp)
            n_sem = nota(db, PATR, "99.888.777/0001-66", comp)
            n_canc = nota(db, PATR, "11222333000181", comp, cancelada=True)
            n_outra = nota(db, ELET, "11222333000181", comp)  # mesma pessoa, outra empresa credora → não casa
            x = emitir_por_nota(n_ok, preview=True)
            assert x["ok"] and x["id"] == r_nota and x["banco"] == "cora" and x["situacao"] == "preview" and x["nota"] == "999999", x
            for ch, trecho in ((n_sem, "nenhuma conta"), (n_canc, "cancelada"), (n_outra, "nenhuma conta")):
                r = emitir_por_nota(ch, preview=True); assert r.get("erro") and trecho in r["erro"], (ch, r)
            assert "não encontrada" in emitir_por_nota("nao-existe", preview=True)["erro"]
            print("OK nota → boleto: casa por empresa+tomador+competência; sem conta, cancelada e outra empresa recusam")
        finally:
            db.execute(text("DELETE FROM receivable_accounts WHERE code LIKE :m"), {"m": f"{MARCA}%"})
            db.execute(text("DELETE FROM nfse_emitidas_nacional WHERE chave_acesso LIKE :m"), {"m": f"{MARCA}%"}); db.commit()
            sobras = db.execute(text("SELECT count(*) FROM receivable_accounts WHERE code LIKE :m"), {"m": f"{MARCA}%"}).scalar()
            print(f"LIMPEZA OK — {sobras} remanescente(s)"); assert sobras == 0
    print("TEST oraculo_cobranca_recebivel PASS")


if __name__ == "__main__":
    main()
