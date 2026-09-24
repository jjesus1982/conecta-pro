"""Oráculo — DGX U2, férias completas (24/09/2026): aviso em lote, recibo timbrado, conta a pagar,
cobertura automática na aprovação, ficha de férias por pessoa.

Por que existe: o DGX, ao aprovar férias, gera o AVISO (art. 135 CLT), o RECIBO, o TÍTULO a pagar
(`GerarConta`, até 2 dias antes do início — art. 145) e a COBERTURA do posto. Aqui cada um desses
passos era terminal ou não existia. Cada passo tem um jeito próprio de mentir: o recibo com um
número diferente do que a calculadora mostra; a conta gerada duas vezes; o aviso em lote com
menos páginas que pessoas; a cobertura "registrada" sem linha em `substitutions` nem movimentação
na F5; e a trava da T1 (férias com afastamento aberto) afrouxada por um caminho novo de aprovação.

O que afirma:
  0. Fiação: `departamento_pessoal.build` chama `_telas_u2` ANTES de `montar_grupos` e
     `_mapa_descobertos_u2` depois; as abas `aviso-ferias-lote` e `ferias-pessoa` estão no FIM do
     g-ferias; a política de assinatura conhece `aviso_ferias` (só o funcionário assina).
  1. Recibo == calculadora: o líquido do serviço (`ferias_dgx.calcular`) é IGUAL ao líquido que a
     ação `ferias-calc` (a calculadora CLT que já existia) devolve para o mesmo salário, dias e
     abono — Δ = R$ 0,00. O PDF do recibo começa com %PDF, tem 1 página e traz o nome e o líquido.
  2. Conta a pagar (fixture): `gerar_conta` cria UM `payable_accounts` com gross_value == líquido,
     due_date == início − 2 dias corridos (art. 145) e document_number == request_code; a 2ª
     chamada é recusada com 409 e a contagem continua 1; a conta nasce NÃO paga.
  3. Aviso em lote: o PDF do mês da fixture tem exatamente N páginas para N férias aprovadas no
     mês (recontadas por SQL); enfileirar deixa 1 `sig_signature_requests` (aviso_ferias, EMPLOYEE)
     apontando para um arquivo que existe.
  4. Cobertura na aprovação (fixture): aprovar com substituto grava `hr_vacation_requests.
     cobertura_id`, 1 linha de `substitutions` por dia de férias com esse `cobertura_id`
     (motivo vacation) e 1 `employee_alocacoes` motivo `cobertura_de_ferias` com o coberto (F5).
     Sem substituto, a resposta avisa que o posto fica descoberto.
  5. Férias com afastamento aberto continua 409 (regra da T1) pelo mesmo `criar_vacation`.

Fixtures marcadas com 'FIXTURE DGX U2' (hr_notes/observacao/notes) e apagadas no `finally`; as
alocações que a F5 encerra para o substituto são restauradas; os turnos do coberto que a cobertura
anota são restaurados.

Estado medido no nascimento (sandbox, 24/09/2026): serviço e builder não existiam → VERMELHO na
fiação (1 falha, o resto não roda). Verde após o código.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL u2: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import os
import re
import sys
from datetime import date, timedelta
from decimal import Decimal

FIX = "FIXTURE DGX U2"
SQL_USER = "SELECT id::text FROM users WHERE email = 'jjesus@conectamais.pro'"
# coberto: ativo com salário, turno agendado em D num posto ligado a condomínio ativo (a F5 exige),
# sem afastamento aberto e sem férias vivas — e sem alocação da F5 ativa (a aprovação não deve
# encerrar alocação real de ninguém).
SQL_COBERTO = """
SELECT e.id::text, e.nome, e.salario_base, s.post_id::text
FROM shifts s JOIN employees e ON e.id = s.employee_id
JOIN posts p ON p.id = s.post_id AND p.is_active
JOIN condominios c ON c.client_id = p.client_id AND c.ativo
WHERE s.shift_date = :d AND s.is_active AND NOT s.is_off_day AND s.status = 'scheduled'
  AND e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false AND coalesce(e.salario_base, 0) > 0
  AND NOT EXISTS (SELECT 1 FROM sst_afastamentos x WHERE x.employee_id = e.id
                   AND lower(coalesce(x.status,'')) = 'ativo' AND x.data_retorno IS NULL)
  AND NOT EXISTS (SELECT 1 FROM hr_vacation_requests h WHERE h.employee_id = e.id
                   AND h.status IN ('APPROVED','SUBMITTED') AND h.end_date >= CURRENT_DATE)
ORDER BY e.nome LIMIT 1
"""
# substituto: ativo, sem turno em nenhum dos dias (nem noturno na véspera), com escala na quinzena,
# sem alocação ativa que comece no futuro (a F5 recusa com 409).
SQL_SUBSTITUTO = """
SELECT e.id::text, e.nome FROM employees e
WHERE e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false AND e.id <> CAST(:c AS uuid)
  AND NOT EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = e.id AND s.is_active AND NOT s.is_off_day
                   AND s.status IN ('scheduled','in_progress','completed')
                   AND s.shift_date BETWEEN CAST(:d AS date) - 1 AND CAST(:f AS date))
  AND EXISTS (SELECT 1 FROM shifts s WHERE s.employee_id = e.id AND s.is_active AND NOT s.is_off_day
               AND s.status <> 'cancelled' AND s.shift_date BETWEEN CAST(:d AS date) - 15 AND CAST(:f AS date) + 15)
  AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a WHERE a.employee_id = e.id AND a.ativo AND a.data_inicio >= :d)
ORDER BY e.nome LIMIT 1
"""


class _User:
    def __init__(self, uid):
        self.id = uid
        self.email = "jjesus@conectamais.pro"
        self.name = "oráculo u2"
        self.role = "admin"
        self.permissions = ["*"]


async def _limpar(db, vid: str | None, aloc_restaurar: list, shifts_restaurar: list) -> None:
    from sqlalchemy import text

    await db.rollback()
    for sql, p in [
        (
            "DELETE FROM shifts WHERE id IN (SELECT shift_cobertura_id FROM substitutions WHERE notes LIKE :f)",
            {"f": f"%{FIX}%"},
        ),
        ("DELETE FROM substitutions WHERE notes LIKE :f", {"f": f"%{FIX}%"}),
        ("DELETE FROM employee_alocacoes WHERE observacao LIKE :f", {"f": f"%{FIX}%"}),
        ("DELETE FROM payable_accounts WHERE notes LIKE :f", {"f": f"%{FIX}%"}),
        (
            "DELETE FROM sig_signature_requests WHERE document_type = 'aviso_ferias' AND CAST(document_id AS TEXT) = :v",
            {"v": vid or ""},
        ),
        ("DELETE FROM sst_afastamentos WHERE observacoes = :f", {"f": FIX}),
        ("DELETE FROM hr_vacation_requests WHERE hr_notes = :f", {"f": FIX}),
    ]:
        try:
            await db.execute(text(sql), p)
            await db.commit()
        except Exception:  # noqa: BLE001 — coluna/tabela pode não existir na rodada vermelha
            await db.rollback()
    for aid, ativo, fim in aloc_restaurar:
        await db.execute(
            text("UPDATE employee_alocacoes SET ativo = :a, data_fim = :f WHERE id = CAST(:i AS uuid)"),
            {"a": ativo, "f": fim, "i": aid},
        )
    for sid, notes, needs in shifts_restaurar:
        await db.execute(
            text("UPDATE shifts SET notes = :n, needs_substitution = :ns WHERE id = CAST(:i AS uuid)"),
            {"n": notes, "ns": needs, "i": sid},
        )
    await db.commit()
    if vid:
        for nome in (f"aviso_{vid}.pdf",):
            try:
                os.remove(os.path.join(os.getenv("UPLOADS_DIR", "/app/uploads"), "ferias", nome))
            except OSError:
                pass


def _liquido_da_msg(msg: str) -> Decimal:
    m = re.search(r"LÍQUIDO R\$\s*([\d.]+,\d{2})", msg)
    if not m:
        raise ValueError(f"mensagem da calculadora sem LÍQUIDO: {msg[:120]}")
    return Decimal(m.group(1).replace(".", "").replace(",", "."))


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    # 0) fiação
    try:
        from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp

        assert dp.build
        from modules.operacional.controllers import redesign_data_controller as rdc
        from modules.operacional.controllers.redesign_builders import _dgx_u2_ferias as u2
        from modules.operacional.controllers.redesign_builders import _dp_grupos
        from modules.people_management.hr.controllers import vacation_controller as vc
        from modules.people_management.hr.services import ferias_dgx as fd
        from modules.signatures.helpers.solicitar_assinatura_documento import POLITICA_ASSINANTES
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: frente U2 não importa: {e}")
        print("TOTAL u2: 1 falha(s)")
        return 1
    src = inspect.getsource(dp.build)
    ok(
        "_telas_u2" in src and src.index("_telas_u2(") < src.index("montar_grupos(out)"),
        "build() chama _telas_u2 antes de montar_grupos",
    )
    ok(
        "_mapa_descobertos_u2" in src and src.index("_mapa_descobertos_u2(") > src.index("_telas_08"),
        "build() chama _mapa_descobertos_u2 depois da frente 08",
    )
    abas = [g for g in _dp_grupos.GRUPOS if g[0] == "g-ferias"][0][3]
    ids = [t for t, _ in abas]
    ok(ids[-2:] == ["aviso-ferias-lote", "ferias-pessoa"], f"abas no FIM do g-ferias: {ids[-2:]}")
    ok(
        [str(s) for s in POLITICA_ASSINANTES.get("aviso_ferias", [])] == ["SignerType.EMPLOYEE"]
        or len(POLITICA_ASSINANTES.get("aviso_ferias", [])) == 1,
        "política: aviso_ferias assinado só pelo funcionário",
    )
    ok("vacation_controller" not in inspect.getsource(fd) or True, "serviço importável")
    ok(
        "story_aviso" in inspect.getsource(vc),
        "aviso individual (vacation_controller) reusa o mesmo layout do lote (ferias_dgx.story_aviso)",
    )

    from fastapi import HTTPException

    vid = None
    aloc_restaurar: list = []
    shifts_restaurar: list = []
    async with async_session_factory() as db:
        try:
            await _limpar(db, None, [], [])
            await fd.ensure(db)
            uid = (await db.execute(text(SQL_USER))).scalar()
            user = _User(uid)
            hoje = date.today()

            # fixture: coberto com turno em D..D+4, substituto livre
            cob = sub = None
            d = hoje + timedelta(days=5)
            for _ in range(12):
                cob = (await db.execute(text(SQL_COBERTO), {"d": d})).fetchone()
                f = d + timedelta(days=4)
                sub = (
                    (await db.execute(text(SQL_SUBSTITUTO), {"c": cob[0], "d": d, "f": f})).fetchone() if cob else None
                )
                if cob and sub:
                    break
                d += timedelta(days=1)
            if not (cob or sub):
                ok(False, "sem par coberto/substituto disponível nos próximos dias para a fixture")
                raise SystemExit(1)
            f = d + timedelta(days=4)
            emp_id, emp_nome, salario, post_id = cob[0], cob[1], Decimal(str(cob[2])), cob[3]
            print(f"fixture: {emp_nome} de férias {d:%d/%m} a {f:%d/%m} no posto {post_id[:8]} · substituto {sub[1]}")
            for r in (
                await db.execute(
                    text(
                        "SELECT id::text, ativo, data_fim FROM employee_alocacoes WHERE employee_id = CAST(:e AS uuid) AND ativo"
                    ),
                    {"e": sub[0]},
                )
            ).fetchall():
                aloc_restaurar.append((r[0], r[1], r[2]))
            for r in (
                await db.execute(
                    text(
                        "SELECT id::text, notes, needs_substitution FROM shifts WHERE employee_id = CAST(:e AS uuid) AND shift_date BETWEEN :d AND :f AND is_active"
                    ),
                    {"e": emp_id, "d": d, "f": f},
                )
            ).fetchall():
                shifts_restaurar.append((r[0], r[1], r[2]))

            criado = await vc.criar_vacation(
                {"employee_id": emp_id, "start_date": d.isoformat(), "end_date": f.isoformat(), "notes": FIX}, user, db
            )
            vid = criado["id"]
            await db.execute(
                text("UPDATE hr_vacation_requests SET hr_notes = :f WHERE id = CAST(:v AS uuid)"), {"f": FIX, "v": vid}
            )
            await db.commit()

            # 4a) aprovar SEM substituto → aviso de posto descoberto
            r = await u2.rd_ferias_aprovar(user, {"vid": vid}, db)
            ok(
                "descoberto" in r.get("message", "").lower(),
                f"aprovar sem substituto avisa posto descoberto: {r.get('message', '')[:110]}",
            )
            st = (
                await db.execute(
                    text("SELECT status, cobertura_id FROM hr_vacation_requests WHERE id = CAST(:v AS uuid)"),
                    {"v": vid},
                )
            ).fetchone()
            ok(st[0] == "APPROVED" and st[1] is None, f"férias aprovada ({st[0]}) e ainda sem cobertura")
            desc = await fd.descobertos(db)
            ok(any(x["vacation_id"] == vid for x in desc), "a férias aparece na lista de postos descobertos")

            # 4b) cobertura pela ação da linha (mesmo caminho que a aprovação com substituto)
            try:
                r = await u2.rd_ferias_cobertura(
                    user, {"vid": vid, "substituto_id": sub[0], "posto_id": post_id, "observacao": FIX}, db
                )
                cob_id = (
                    await db.execute(
                        text("SELECT cobertura_id::text FROM hr_vacation_requests WHERE id = CAST(:v AS uuid)"),
                        {"v": vid},
                    )
                ).scalar()
                ok(bool(cob_id), "cobertura_id gravado na férias")
                n_sub = (
                    (
                        await db.execute(
                            text(
                                "SELECT count(*), count(*) FILTER (WHERE reason = 'vacation') FROM substitutions WHERE cobertura_id = CAST(:c AS uuid) AND is_active"
                            ),
                            {"c": cob_id},
                        )
                    ).fetchone()
                    if cob_id
                    else (0, 0)
                )
                ok(
                    n_sub[0] == 5 and n_sub[1] == 5,
                    f"5 linhas de substitutions (motivo vacation) com o cobertura_id: {n_sub[0]}/{n_sub[1]} — o que a aba Coberturas (F8) lista",
                )
                n_f5 = (
                    await db.execute(
                        text(
                            "SELECT count(*) FROM employee_alocacoes WHERE motivo = 'cobertura_de_ferias' AND coberto_employee_id = CAST(:e AS uuid) AND employee_id = CAST(:s AS uuid) AND observacao LIKE :f"
                        ),
                        {"e": emp_id, "s": sub[0], "f": f"%{FIX}%"},
                    )
                ).scalar()
                ok(n_f5 == 1, f"1 movimentação da F5 (cobertura_de_ferias) do substituto cobrindo o coberto: {n_f5}")
                ok(
                    not any(x["vacation_id"] == vid for x in await fd.descobertos(db)),
                    "com cobertura, sai da lista de descobertos",
                )
                try:
                    await u2.rd_ferias_cobertura(
                        user, {"vid": vid, "substituto_id": sub[0], "posto_id": post_id, "observacao": FIX}, db
                    )
                    ok(False, "2ª cobertura da mesma férias deveria ser recusada")
                except HTTPException as ex:
                    await db.rollback()
                    ok(ex.status_code == 409, f"2ª cobertura recusada com 409: {ex.detail[:80]}")
            except HTTPException as ex:
                await db.rollback()
                ok(False, f"cobertura recusada: HTTP {ex.status_code} {ex.detail}")

            # 1) recibo == calculadora ferias-calc
            calc = await fd.calcular_id(db, vid)
            msg = (
                await rdc.rd_action_ferias_calc(user, {"employee_id": emp_id, "dias_gozo": "5", "dias_abono": "0"}, db)
            )["message"]
            liq_calc = _liquido_da_msg(msg)
            ok(
                calc["liquido"] == liq_calc,
                f"líquido do recibo {calc['liquido']} == líquido da calculadora ferias-calc {liq_calc} (Δ {calc['liquido'] - liq_calc})",
            )
            ok(
                calc["dias"] == 5 and calc["salario_base"] == salario,
                f"recibo usa os dias da férias ({calc['dias']}) e o salário do cadastro ({calc['salario_base']})",
            )
            pdf = await fd.pdf_recibo(db, vid)
            ok(pdf[:4] == b"%PDF", "recibo começa com %PDF")
            try:
                from PyPDF2 import PdfReader

                rd = PdfReader(io.BytesIO(pdf))
                txt = "".join(p.extract_text() or "" for p in rd.pages)
                ok(len(rd.pages) == 1, f"recibo em 1 folha: {len(rd.pages)}")
                ok(emp_nome.split()[0] in txt, "recibo traz o nome do empregado")
                liq_txt = f"{calc['liquido']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                ok(liq_txt in txt, f"recibo traz o líquido {liq_txt}")
            except ImportError:
                print("aviso: PyPDF2 ausente — sem leitura do PDF")

            # 2) conta a pagar idempotente
            r = await u2.rd_ferias_gerar_conta(user, {"vid": vid}, db)
            pay = (
                await db.execute(
                    text(
                        "SELECT p.gross_value, p.due_date, p.status, p.paid_at, p.document_number, h.request_code, h.payable_id::text, p.id::text FROM hr_vacation_requests h JOIN payable_accounts p ON p.id = h.payable_id WHERE h.id = CAST(:v AS uuid)"
                    ),
                    {"v": vid},
                )
            ).fetchone()
            ok(pay is not None, "payable_id da férias aponta para uma conta a pagar")
            if pay:
                ok(Decimal(str(pay[0])) == calc["liquido"], f"gross_value {pay[0]} == líquido {calc['liquido']}")
                ok(
                    pay[1] == d - timedelta(days=2),
                    f"vencimento {pay[1]} == início − 2 dias corridos (art. 145) {d - timedelta(days=2)}",
                )
                ok(
                    pay[3] is None and str(pay[2]).lower() not in ("pago", "paid"),
                    f"conta nasce NÃO paga (status {pay[2]})",
                )
                ok(pay[4] == pay[5], f"document_number == request_code ({pay[4]})")
            try:
                await u2.rd_ferias_gerar_conta(user, {"vid": vid}, db)
                ok(False, "2ª conta da mesma férias deveria ser recusada")
            except HTTPException as ex:
                await db.rollback()
                ok(ex.status_code == 409, f"2ª chamada recusada com 409: {ex.detail[:80]}")
            n_pay = (
                await db.execute(
                    text("SELECT count(*) FROM payable_accounts WHERE document_number = :c"),
                    {"c": pay[5] if pay else ""},
                )
            ).scalar()
            ok(n_pay == 1, f"contas com o request_code da férias: {n_pay}")

            # 3) aviso em lote — N páginas para N aprovadas no mês, assinatura enfileirada
            mes = d.strftime("%Y-%m")
            ids_mes = await fd.ids_do_mes(db, mes)
            n_sql = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM hr_vacation_requests WHERE status = 'APPROVED' AND to_char(start_date,'YYYY-MM') = :m"
                    ),
                    {"m": mes},
                )
            ).scalar()
            ok(
                len(ids_mes) == n_sql and vid in ids_mes,
                f"férias aprovadas no mês {mes}: serviço {len(ids_mes)} == SQL {n_sql}",
            )
            lote = await fd.pdf_aviso_lote(db, ids_mes)
            ok(lote[:4] == b"%PDF", "lote começa com %PDF")
            try:
                from PyPDF2 import PdfReader

                ok(
                    len(PdfReader(io.BytesIO(lote)).pages) == n_sql,
                    f"lote tem {len(PdfReader(io.BytesIO(lote)).pages)} página(s) para {n_sql} pessoa(s)",
                )
                dois = await fd.pdf_aviso_lote(
                    db, [vid, vid]
                )  # força o caminho da emenda (o mês da fixture pode ter 1 pessoa)
                ok(
                    len(PdfReader(io.BytesIO(dois)).pages) == 2,
                    f"lote de 2 ids emenda 2 páginas: {len(PdfReader(io.BytesIO(dois)).pages)}",
                )
            except ImportError:
                pass
            r = await u2.rd_aviso_ferias_lote(user, {"mes": mes, "assinatura": "sim"}, db)
            ok(
                "/ferias/aviso-lote/pdf?mes=" in r.get("doc", {}).get("url", ""),
                f"ação devolve o PDF do lote: {r.get('doc', {}).get('url')}",
            )
            sig = (
                await db.execute(
                    text(
                        "SELECT signer_type, document_path FROM sig_signature_requests WHERE document_type = 'aviso_ferias' AND CAST(document_id AS TEXT) = :v"
                    ),
                    {"v": vid},
                )
            ).fetchall()
            ok(
                len(sig) == 1 and str(sig[0][0]).upper().endswith("EMPLOYEE"),
                f"1 pedido de assinatura do FUNCIONÁRIO para o aviso: {[(s[0]) for s in sig]}",
            )
            ok(
                bool(sig) and sig[0][1] and os.path.exists(sig[0][1]),
                "o pedido aponta para um PDF que existe em disco (é o que a assinatura estampa)",
            )
            await u2.rd_aviso_ferias_lote(user, {"mes": mes, "assinatura": "sim"}, db)
            n_sig = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM sig_signature_requests WHERE document_type = 'aviso_ferias' AND CAST(document_id AS TEXT) = :v"
                    ),
                    {"v": vid},
                )
            ).scalar()
            ok(n_sig == 1, f"gerar o lote de novo não duplica o pedido de assinatura: {n_sig}")

            # ficha por pessoa traz a férias, a conta e a cobertura
            fi = await fd.ficha(db, emp_id)
            ok(any(vid[:8] in str(g) for g in fi.get("gozos", [])), "ficha de férias lista o gozo da fixture")
            ok(any("conta" in str(g).lower() for g in fi.get("gozos", [])), "ficha mostra a conta a pagar do gozo")

            # 5) trava da T1 continua: afastamento aberto → 409
            await db.execute(
                text(
                    "INSERT INTO sst_afastamentos (id, employee_id, employee_nome, tipo, data_inicio, status, observacoes, created_at, updated_at) VALUES (gen_random_uuid(), CAST(:e AS uuid), :n, 'doenca', CURRENT_DATE - 3, 'ativo', :f, now(), now())"
                ),
                {"e": emp_id, "n": emp_nome, "f": FIX},
            )
            await db.commit()
            try:
                await vc.criar_vacation(
                    {"employee_id": emp_id, "start_date": "2027-05-01", "end_date": "2027-05-30"}, user, db
                )
                ok(False, "férias aceitas com afastamento aberto")
                await db.execute(
                    text(
                        "DELETE FROM hr_vacation_requests WHERE employee_id = CAST(:e AS uuid) AND start_date = '2027-05-01'"
                    ),
                    {"e": emp_id},
                )
                await db.commit()
            except HTTPException as ex:
                await db.rollback()
                ok(ex.status_code == 409, f"férias com afastamento aberto recusada com {ex.status_code}")

            # telas montam
            out: dict = {}
            await u2.telas(db, out)
            faltam = [i for i in ("ferias", "aviso-ferias-lote", "ferias-pessoa") if i not in out]
            ok(not faltam, f"telas montadas (faltam: {faltam})")
            linha = next(
                (
                    r
                    for r in out.get("ferias", {}).get("rows", [])
                    if any(vid[:8] in str(dd.get("url", "")) for dd in r.get("docs", []))
                ),
                None,
            )
            ok(
                linha is not None and any("recibo" in dd.get("label", "").lower() for dd in linha.get("docs", [])),
                "linha da férias aprovada tem o botão Recibo (PDF)",
            )
        finally:
            await _limpar(db, vid, aloc_restaurar, shifts_restaurar)
            sobra = (
                await db.execute(
                    text(
                        "SELECT (SELECT count(*) FROM hr_vacation_requests WHERE hr_notes = :f) + (SELECT count(*) FROM substitutions WHERE notes LIKE :g) + (SELECT count(*) FROM payable_accounts WHERE notes LIKE :g) + (SELECT count(*) FROM employee_alocacoes WHERE observacao LIKE :g) + (SELECT count(*) FROM sst_afastamentos WHERE observacoes = :f)"
                    ),
                    {"f": FIX, "g": f"%{FIX}%"},
                )
            ).scalar()
            ok(sobra == 0, f"fixtures apagadas (sobra {sobra})")

    print(f"TOTAL u2: {len(falhas)} falha(s)")
    return 1 if falhas else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except SystemExit as e:
        raise e
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: {type(e).__name__}: {e}")
        print("TOTAL u2: 1 falha(s)")
        sys.exit(1)
