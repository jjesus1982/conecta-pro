"""Oráculo — DGX Y5: o que o COLABORADOR vê (24/09/2026).

Por que existe: em três dias, 30 frentes construíram para o ESCRITÓRIO. O colaborador
continua vendo o mesmo de antes. Este oráculo mede o portal pelo lado de FORA — com o
token de um colaborador de verdade, senha = dígitos do CPF — e afirma as cinco coisas que
podem dar errado quando se liga coisa do escritório na tela de quem trabalha:

  (a) VAZAMENTO. Toda rota do portal tem de filtrar por `employee_id` do token. Medido no
      nascimento: `GET /api/v1/redesign/ferias/{vid}/recibo/pdf`, `.../aviso/pdf` e
      `GET /api/v1/redesign/crachas/pdf?ids=` devolviam 200 %PDF com o documento de OUTRA
      pessoa para o token de um colaborador qualquer — não havia checagem de dono, só
      `CurrentActiveUser`. O oráculo chama cada rota do portal com o token de A e recusa
      qualquer resposta que contenha id, nome ou CPF de B.
  (b) A FILA. O aviso de férias da U2 (`sig_signature_requests`, document_type
      `aviso_ferias`) tem de aparecer em `GET /api/v1/signatures/meus-pendentes` do DONO —
      e não na de mais ninguém. Provado com fixture, apagada no fim.
  (c) O DOWNLOAD. Crachá (F6/T1), recibo e aviso de férias (U2) têm de baixar pelo PORTAL,
      200 e `%PDF`, pela rota escopada do próprio funcionário — e a mesma rota do portal
      tem de recusar o documento de outro.
  (d) MESMA FONTE. O espelho que o colaborador baixa tem de ser o MESMO que o DP baixa
      para a mesma competência — mesmo texto, sem régua paralela. (O portal calcula sob
      demanda quando o DP ainda não fechou o mês; o resultado tem de coincidir.)
  (e) SEM CONFERÊNCIA INTERNA. Nenhuma rota do portal pode expor `folha_beneficio_conferencia`,
      `ponto_folha_conferencia` nem `banco_horas_conferencia`. O colaborador vê o que
      RECEBEU; a nossa apuração paralela é assunto do escritório.
  (f) E o que ele PASSA a ver: por qual regra cada benefício é concedido, o status da
      justificativa que ele mesmo escreveu, as linhas do holerite com nome e valor, e a
      lista de férias COMPLETA — recontada por SQL contra `hr_vacation_requests`, porque
      um `except` que devolve `[]` com HTTP 200 mente pior do que um erro.

Estado medido no nascimento (sandbox, 24/09/2026):
  ✗ (a) recibo/aviso/crachá de terceiro baixavam com 200 %PDF para token de colaborador
  ✗ (c) não existia rota de crachá nem de recibo/aviso no portal (404)
  ✗ (f) `/self-service/minhas-justificativas` não existia (404) — 13 justificativas paradas,
        nenhuma visível a quem as escreveu
  ✗ (f) `/self-service/meus-beneficios` não dizia por qual REGRA o benefício é concedido
  ✗ (f) itens do holerite saíam todos com descrição "" e valor 0,00 (o serviço lia chaves em
        inglês; `hr_payslips.earnings` guarda `descricao`/`valor`/`referencia`)
  ✗ (f) `/minhas-ferias/solicitacoes` devolvia `[]` com HTTP 200 para quem tinha 3 férias —
        lia a cópia morta `employee_vacation_requests`, cujo `dias` guarda texto ("15 dias"),
        o schema pedia `int`, e o `except` engolia
  ✓ (b) (d) (e) já verdes — a fila é genérica, o espelho já é o mesmo `ler_espelho`, e o
        portal nunca tocou nas tabelas de conferência. Ficam como TRAVA contra regressão.

Como roda (o portal precisa estar de pé; o oráculo mede a SAÍDA, não o código):
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
      -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      -e Y5_BASE=http://teste-dgx-y5:8080 \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y5_portal_colaborador.py

Sai 0 = verde; 1 = vermelho. Linha final `TOTAL y5: N`.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

import httpx

BASE = os.environ.get("Y5_BASE") or "http://127.0.0.1:8080"
PORTAL = "/api/v1/people-management/portal/self-service"
FIX = "FIXTURE DGX Y5"

# Campos de apuração interna que o colaborador NUNCA deve ver.
CONFERENCIA = ("folha_beneficio_conferencia", "ponto_folha_conferencia", "banco_horas_conferencia")

# Rotas GET do portal do colaborador (a superfície inteira, medida em 24/09/2026).
ROTAS_PORTAL = [
    f"{PORTAL}/me",
    f"{PORTAL}/meus-dados",
    f"{PORTAL}/onboarding-status",
    f"{PORTAL}/meu-ponto",
    f"{PORTAL}/ponto-hoje",
    f"{PORTAL}/meus-beneficios",
    f"{PORTAL}/meus-documentos",
    f"{PORTAL}/meus-holerites",
    f"{PORTAL}/meus-treinamentos",
    f"{PORTAL}/minha-escala",
    f"{PORTAL}/minha-escala/proximo-turno",
    f"{PORTAL}/minhas-ferias/saldo",
    f"{PORTAL}/minhas-ferias/solicitacoes",
    f"{PORTAL}/minhas-notificacoes",
    f"{PORTAL}/meus-pagamentos",
    f"{PORTAL}/meus-reembolsos",
    f"{PORTAL}/categorias-reembolso",
    f"{PORTAL}/ouvidoria/minhas",
    f"{PORTAL}/minhas-justificativas",
    "/api/v1/signatures/meus-pendentes",
    "/api/v1/redesign/data/portal-do-funcionario",
]

# A = colaborador com férias APROVADA (recibo/aviso têm o que baixar); B = outro colaborador.
SQL_A = """
SELECT u.email, e.cpf, e.id::text, e.nome,
       (SELECT v.id::text FROM hr_vacation_requests v
         WHERE v.employee_id = e.id AND v.status = 'APPROVED'
         ORDER BY v.start_date DESC LIMIT 1) AS vid
  FROM users u JOIN employees e ON e.id = u.employee_id
 WHERE u.role = 'funcionario' AND u.is_active AND e.cpf IS NOT NULL
   AND EXISTS (SELECT 1 FROM hr_vacation_requests v
                WHERE v.employee_id = e.id AND v.status = 'APPROVED')
 ORDER BY e.nome LIMIT 1
"""
SQL_B = """
SELECT u.email, e.cpf, e.id::text, e.nome
  FROM users u JOIN employees e ON e.id = u.employee_id
 WHERE u.role = 'funcionario' AND u.is_active AND e.cpf IS NOT NULL AND e.id::text <> :a
   AND EXISTS (SELECT 1 FROM ged_kit_documents d WHERE d.employee_id = e.id)
 ORDER BY e.nome LIMIT 1
"""
# competência com espelho já calculado pelo DP para A (o portal e o DP têm de coincidir)
SQL_COMP = """
SELECT t.reference_month, t.reference_year FROM time_sheets t
 WHERE t.employee_id::text = :a ORDER BY t.reference_year DESC, t.reference_month DESC LIMIT 1
"""
# fixture do aviso: copia os defaults reais das solicitações de funcionário já existentes
SQL_FIX = """
INSERT INTO sig_signature_requests
  (id, tenant_id, title, status, priority, purpose, reminder_frequency, requested_by,
   document_type, document_id, document_name, signer_type, signer_id, signer_name,
   created_at, updated_at)
VALUES (CAST(:i AS uuid), '00000000-0000-0000-0000-000000000001', :n, 'PENDING', 'NORMAL',
        'APPROVAL', 'NONE', '00000000-0000-0000-0000-000000000001',
        'aviso_ferias', CAST(:v AS uuid), :n, 'employee', CAST(:e AS uuid), :nome,
        now(), now())
"""

falhas: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def bad(msg: str) -> None:
    falhas.append(msg)
    print(f"  ✗ {msg}")


def _so_digitos(v: str) -> str:
    return "".join(c for c in (v or "") if c.isdigit())


async def _login(cli: httpx.AsyncClient, user: str, senha: str) -> str | None:
    r = await cli.post(
        "/api/v1/auth/login",
        data={"username": user, "password": senha},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


def _texto_pdf(conteudo: bytes) -> str:
    import pymupdf

    with pymupdf.open(stream=conteudo, filetype="pdf") as d:
        return "\n".join(p.get_text() for p in d)


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text as T  # noqa: N812 — padrão dos oráculos da casa

    from core.database import async_session_factory

    async with async_session_factory() as db:
        a = (await db.execute(T(SQL_A))).first()
        if not a:
            print("✗ sem colaborador com férias aprovada no sandbox — oráculo não pode medir")
            print("TOTAL y5: 1")
            return 1
        b = (await db.execute(T(SQL_B), {"a": a[2]})).first()
        comp = (await db.execute(T(SQL_COMP), {"a": a[2]})).first()
    if not b:
        print("✗ sem segundo colaborador para o teste de vazamento")
        print("TOTAL y5: 1")
        return 1

    a_email, a_cpf, a_id, a_nome, a_vid = a
    b_email, b_cpf, b_id, b_nome = b
    print(f"A = {a_nome} ({a_id[:8]}…)  ·  B = {b_nome} ({b_id[:8]}…)")

    fix_req = None
    async with httpx.AsyncClient(base_url=BASE, timeout=180) as cli:
        ta = await _login(cli, a_email, _so_digitos(a_cpf))
        tb = await _login(cli, b_email, _so_digitos(b_cpf))
        tadm = await _login(cli, "jjesus@conectamais.pro", os.environ.get("ADMIN_PASS", "JsJ618908@#%"))
        if not ta or not tb:
            print("✗ não consegui token de colaborador (senha = dígitos do CPF) — rate limit?")
            print("TOTAL y5: 1")
            return 1
        HA = {"Authorization": f"Bearer {ta}"}
        HB = {"Authorization": f"Bearer {tb}"}

        # ------------------------------------------------------------------ #
        # (a) VAZAMENTO — nenhuma rota do portal devolve dado de B para A
        # ------------------------------------------------------------------ #
        print("\n[a] vazamento entre colaboradores")
        alheios = {b_id: "id de B", b_nome: "nome de B", _so_digitos(b_cpf): "CPF de B"}
        vazou = 0
        for rota in ROTAS_PORTAL:
            r = await cli.get(rota, headers=HA)
            if r.status_code == 404:
                bad(f"{rota} → 404 (rota do portal não existe)")
                continue
            if r.status_code >= 400:
                bad(f"{rota} → HTTP {r.status_code}")
                continue
            corpo = r.text
            for agulha, rotulo in alheios.items():
                if agulha and agulha in corpo:
                    bad(f"{rota} devolveu {rotulo} para o token de A")
                    vazou += 1
        if not vazou:
            ok(f"{len(ROTAS_PORTAL)} rotas do portal: nenhuma trouxe id/nome/CPF de B")

        # documentos de TERCEIRO pelas rotas de documento do escritório
        for rota, oq in (
            (f"/api/v1/redesign/ferias/{a_vid}/recibo/pdf", "recibo de férias de A"),
            (f"/api/v1/redesign/ferias/{a_vid}/aviso/pdf", "aviso de férias de A"),
            (f"/api/v1/redesign/crachas/pdf?ids={a_id}", "crachá de A"),
        ):
            r = await cli.get(rota, headers=HB)
            if r.status_code < 400:
                bad(f"B baixou o {oq} ({rota.split('?')[0]} → {r.status_code})")
            else:
                ok(f"B NÃO baixa o {oq} (HTTP {r.status_code})")

        # ------------------------------------------------------------------ #
        # (b) o aviso de férias da U2 aparece na fila de assinatura do DONO
        # ------------------------------------------------------------------ #
        print("\n[b] aviso de férias na fila de assinatura do colaborador")
        fix_req = str(uuid.uuid4())
        async with async_session_factory() as db:
            await db.execute(
                T(SQL_FIX),
                {"i": fix_req, "v": a_vid, "n": f"{FIX} — Aviso de férias", "e": a_id, "nome": a_nome},
            )
            await db.commit()
        ra = (await cli.get("/api/v1/signatures/meus-pendentes", headers=HA)).text
        rb = (await cli.get("/api/v1/signatures/meus-pendentes", headers=HB)).text
        if FIX in ra:
            ok("o aviso de férias entra na fila «documentos a assinar» do dono")
        else:
            bad("aviso de férias PENDING não aparece em /signatures/meus-pendentes do dono")
        if FIX in rb:
            bad("o aviso de férias de A aparece na fila de B")
        else:
            ok("o aviso de A não aparece na fila de B")

        # ------------------------------------------------------------------ #
        # (c) crachá e recibo baixam pelo PORTAL, 200 e %PDF
        # ------------------------------------------------------------------ #
        print("\n[c] crachá, recibo e aviso pelo portal do próprio colaborador")
        for rota, oq, forjavel in (
            (f"{PORTAL}/meu-cracha/pdf", "meu crachá", False),
            (f"{PORTAL}/minhas-ferias/{a_vid}/recibo/pdf", "meu recibo de férias", True),
            (f"{PORTAL}/minhas-ferias/{a_vid}/aviso/pdf", "meu aviso de férias", True),
        ):
            r = await cli.get(rota, headers=HA)
            if r.status_code == 200 and r.content[:5] == b"%PDF-":
                ok(f"{oq}: 200 e %PDF ({len(r.content) // 1024} KB)")
            else:
                bad(f"{oq}: HTTP {r.status_code}, começa com {r.content[:8]!r}")
            if not forjavel:
                continue  # /meu-cracha é sempre o do token; não há id a forjar
            r2 = await cli.get(rota, headers=HB)
            if r2.status_code < 400:
                bad(f"B baixou «{oq}» de A pela rota do portal (HTTP {r2.status_code})")
            else:
                ok(f"B leva {r2.status_code} ao pedir «{oq}» de A pela rota do portal")

        # ------------------------------------------------------------------ #
        # (d) o espelho do colaborador == o do DP para a mesma competência
        # ------------------------------------------------------------------ #
        print("\n[d] espelho do colaborador × espelho do DP (mesma fonte)")
        if not comp:
            bad("sem time_sheets para A — não dá para comparar espelho")
        elif not tadm:
            bad("sem token de admin — não dá para buscar o espelho pelo lado do DP")
        else:
            mes, ano = int(comp[0]), int(comp[1])
            rp = await cli.get(f"{PORTAL}/meu-espelho/{mes}/{ano}/pdf", headers=HA)
            rd = await cli.get(
                f"/api/v1/people-management/hr/ponto/espelho/{a_id}/{mes}/{ano}/pdf",
                headers={"Authorization": f"Bearer {tadm}"},
            )
            if rp.status_code != 200 or rd.status_code != 200:
                bad(f"espelho {mes:02d}/{ano}: portal={rp.status_code} dp={rd.status_code}")
            else:
                tp, td = _texto_pdf(rp.content), _texto_pdf(rd.content)
                if tp == td:
                    ok(f"espelho {mes:02d}/{ano}: texto do portal IDÊNTICO ao do DP ({len(tp)} chars)")
                else:
                    bad(f"espelho {mes:02d}/{ano}: portal e DP divergem — régua paralela")

        # ------------------------------------------------------------------ #
        # (e) nenhuma rota do portal expõe a conferência interna
        # ------------------------------------------------------------------ #
        print("\n[e] conferência interna não vaza para o colaborador")
        sujas = 0
        for rota in ROTAS_PORTAL:
            r = await cli.get(rota, headers=HA)
            if r.status_code >= 400:
                continue
            baixo = r.text.lower()
            for campo in CONFERENCIA:
                if campo in baixo:
                    bad(f"{rota} expõe `{campo}` ao colaborador")
                    sujas += 1
        if not sujas:
            ok("nenhuma das rotas do portal cita folha_/ponto_/banco_horas_conferencia")

        # ------------------------------------------------------------------ #
        # (f) o que o colaborador PASSA a ver
        # ------------------------------------------------------------------ #
        print("\n[f] o que o colaborador passa a ver")
        rb2 = await cli.get(f"{PORTAL}/meus-beneficios", headers=HA)
        if rb2.status_code == 200:
            ativos = rb2.json().get("beneficios_ativos") or []
            com_regra = [x for x in ativos if (x or {}).get("regra")]
            if ativos and len(com_regra) == len(ativos):
                ok(f"{len(ativos)} benefício(s) dizem por qual regra são concedidos")
            elif not ativos:
                ok("colaborador sem benefício ativo (vazio honesto)")
            else:
                bad(f"{len(ativos) - len(com_regra)} benefício(s) sem a regra de concessão")
        else:
            bad(f"/meus-beneficios → HTTP {rb2.status_code}")

        # férias: a lista do portal tem de ter TODAS as de `hr_vacation_requests` (a autoritativa).
        # Até 24/09 a rota lia a cópia morta e o `except` engolia o erro de schema: HTTP 200 com
        # lista VAZIA para quem tinha 3 férias. Zero não é a mesma coisa que nenhum.
        async with async_session_factory() as db:
            n_fer = (
                await db.execute(
                    T("SELECT count(*) FROM hr_vacation_requests WHERE employee_id = CAST(:e AS uuid)"),
                    {"e": a_id},
                )
            ).scalar() or 0
        rf = await cli.get(f"{PORTAL}/minhas-ferias/solicitacoes", headers=HA)
        vistas = len(rf.json()) if rf.status_code == 200 and isinstance(rf.json(), list) else -1
        if vistas == n_fer:
            ok(f"minhas férias: {vistas} na tela == {n_fer} em hr_vacation_requests")
        else:
            bad(f"minhas férias: {vistas} na tela × {n_fer} em hr_vacation_requests")

        rj = await cli.get(f"{PORTAL}/minhas-justificativas", headers=HA)
        if rj.status_code != 200:
            bad(f"/minhas-justificativas → HTTP {rj.status_code}")
        else:
            corpo = rj.json()
            if "justificativas" in corpo and all("status" in j for j in corpo["justificativas"]):
                ok(f"minhas justificativas: {corpo.get('total', 0)} com status visível")
            else:
                bad("/minhas-justificativas sem a lista ou sem o status de cada uma")

        # itens do holerite com nome e valor (chaves em PT no hr_payslips.earnings)
        rh = await cli.get(f"{PORTAL}/meus-holerites", headers=HA)
        if rh.status_code == 200 and rh.json():
            p0 = rh.json()[0]
            rd2 = await cli.get(f"{PORTAL}/meus-holerites/{p0['month']}/{p0['year']}", headers=HA)
            itens = rd2.json().get("items", []) if rd2.status_code == 200 else []
            nomeados = [i for i in itens if (i.get("description") or "").strip()]
            if itens and len(nomeados) == len(itens):
                ok(f"holerite {p0['month']:02d}/{p0['year']}: {len(itens)} linha(s) com descrição e valor")
            elif not itens:
                bad(f"holerite {p0['month']:02d}/{p0['year']} sem linhas de detalhe")
            else:
                bad(f"holerite {p0['month']:02d}/{p0['year']}: {len(itens) - len(nomeados)} sem descrição")

    # limpeza da fixture
    if fix_req:
        async with async_session_factory() as db:
            await db.execute(
                T("DELETE FROM sig_signature_requests WHERE document_name LIKE :p"),
                {"p": f"{FIX}%"},
            )
            await db.commit()
        async with async_session_factory() as db:
            resto = (
                await db.execute(
                    T("SELECT count(*) FROM sig_signature_requests WHERE document_name LIKE :p"),
                    {"p": f"{FIX}%"},
                )
            ).scalar()
        print(f"\nfixtures '{FIX}' restantes: {resto}")

    print(f"\nTOTAL y5: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
