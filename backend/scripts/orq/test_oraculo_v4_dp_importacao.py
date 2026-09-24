"""Oráculo — DGX V4: fila de falhas de importação, export/impressão de colaboradores com
contadores por status, e importação de apontamentos da folha em CSV (24/09/2026).

Por que existe: três coisas que só valem se forem verdade juntas.
  1. Um importador do DP que recusa uma linha PRECISA deixar a pendência em algum lugar com dono
     — e rerodar a mesma importação não pode transformar a fila num diário de linhas iguais.
  2. O número que a tela `funcionarios` mostra no cabeçalho precisa bater com o banco. Contador
     de status é o tipo de número que ninguém reconfere e todo mundo repete em reunião.
  3. O CSV de apontamentos é caminho de FOLHA: precisa recusar competência publicada (409) e,
     no que aceita, escrever pelo mesmo caminho de «Apontar» — sem tocar em valor calculado.

O que afirma (fixtures 'FIXTURE DGX V4', apagadas ao fim, mesmo em falha):
  a. `import-cadastro` com um CPF que não existe grava 1 falha (origem planilha, não resolvida);
     rodar a MESMA planilha de novo continua com 1 — a chave é (origem, identificador, motivo).
  b. `resolver` liga a falha a um colaborador existente (status resolvido_manual + employee_id),
     e recusa um employee_id que não existe.
  c. `colaboradores_export.linhas()` devolve exatamente tantas linhas quantos os colaboradores
     com vínculo vivo — recontado por SQL PRÓPRIO aqui, não pelo serviço.
  d. o PDF timbrado sai (bytes com assinatura %PDF) e o XLSX sai (assinatura PK) com 1 linha de
     cabeçalho + N; CPF mascarado quando `admin=False`.
  e. cada contador do cabeçalho == o mesmo contador recontado por SQL próprio aqui.
  f. CSV com 2 linhas boas + 1 ruim → 2 apontamentos (em 2 holerites rascunho) e 1 falha na fila;
     «só validar» não escreve NADA — nem apontamento, nem linha na fila (medido por HTTP em 24/09:
     a prévia dizia «nada gravado» e deixava 2 pendências para alguém resolver).
  g. o mesmo CSV numa competência com folha PUBLICADA → HTTP 409, e nada é gravado.

Estado medido no nascimento (staging, 24/09/2026): `dp_importacao_falhas` não existia
(`to_regclass` → NULL) e `colaboradores_export`/`apontamentos_csv` não existiam → ImportError →
VERMELHO. employees: 63 ativo, 20 inativo, 11 demitido, 7 pj_ativo, 1 afastado_inss, 1 candidato,
1 suspenso. hr_payslips: 51 draft em 09/2026, 51 published em 07/2026.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys
from uuid import uuid4

from sqlalchemy import text

FIX = "FIXTURE DGX V4"
#: Competência livre de folha publicada — o CSV bom vai para cá.
ANO_LIVRE, MES_LIVRE = 2030, 12
#: CPF sintético (válido em forma, inexistente no cadastro) para a falha da planilha.
CPF_FANTASMA = "52998224725"


async def _limpar(db) -> None:
    await db.execute(
        text("DELETE FROM dp_importacao_falhas WHERE identificador_origem LIKE :p OR cpf = :c"),
        {"p": f"{FIX}%", "c": CPF_FANTASMA},
    )
    await db.execute(text("DELETE FROM hr_payslips WHERE payslip_code LIKE :p"), {"p": f"{FIX}%"})
    await db.execute(text("DELETE FROM employees WHERE nome LIKE :p"), {"p": f"{FIX}%"})
    await db.commit()


async def _fixtures(db) -> list[tuple[str, str]]:
    """2 colaboradores ativos com matrícula + 1 holerite RASCUNHO cada, na competência livre."""
    cond = (await db.execute(text("SELECT CAST(id AS text) FROM condominios LIMIT 1"))).scalar()
    if not cond:
        raise RuntimeError("sem condominios no banco — não dá para criar holerite de fixture")
    pessoas = []
    for i, suf in enumerate(("A", "B"), start=1):
        eid = str(uuid4())
        mat = f"FIXV4{suf}"
        await db.execute(
            text(
                "INSERT INTO employees (id, nome, matricula, cpf, status, cargo, data_admissao, created_at, updated_at) "
                "VALUES (CAST(:i AS uuid), :n, :m, :c, 'ativo', 'TESTE', CURRENT_DATE, now(), now())"
            ),
            {"i": eid, "n": f"{FIX} {suf}", "m": mat, "c": f"9999999990{i}"},
        )
        await db.execute(
            text(
                "INSERT INTO hr_payslips (id, condominio_id, employee_id, payslip_code, payslip_type, status, "
                "reference_year, reference_month, reference_period, created_at, updated_at) "
                "VALUES (gen_random_uuid(), CAST(:cond AS uuid), CAST(:e AS uuid), :code, 'monthly', 'draft', "
                ":a, :m, :per, now(), now())"
            ),
            {
                "cond": cond,
                "e": eid,
                "code": f"{FIX}-{suf}",
                "a": ANO_LIVRE,
                "m": MES_LIVRE,
                "per": f"{MES_LIVRE:02d}/{ANO_LIVRE}",
            },
        )
        pessoas.append((eid, mat))
    await db.commit()
    return pessoas


class _Autor:
    """Quem assina o apontamento. `rd_action_folha_apontamento` grava `[autor] motivo` —
    o oráculo passa o mesmo tipo de objeto que o endpoint recebe do `CurrentActiveUser`."""

    name = FIX
    email = None
    id = FIX


def _csv(mat_a: str, mat_b: str, rubrica: str, comp: str) -> str:
    return (
        "matricula;rubrica;referencia;valor;competencia\n"
        f"{mat_a};{rubrica};30;123,45;{comp}\n"
        f"{mat_b};{rubrica};30;67,89;{comp}\n"
        f"FIXV4NAOEXISTE;{rubrica};30;10,00;{comp}\n"
    )


async def main() -> int:  # noqa: PLR0912, PLR0915 — um oráculo é uma lista de afirmações
    from fastapi import HTTPException

    from core.database import async_session_factory
    from core.database.session import SyncSessionLocal
    from modules.integrations.connectors.whatsapp.identidade import SEM_VINCULO
    from modules.people_management.folha.services import apontamentos_csv
    from modules.people_management.hr.services import colaboradores_export as expo
    from modules.people_management.hr.services import importacao_falhas as falhas
    from modules.people_management.hr.services.cadastro_import_service import CadastroImportService

    falhas_medidas: list[str] = []
    mat_a = mat_b = rubrica = None
    async with async_session_factory() as db:
        await falhas._ensure(db)
        await _limpar(db)
        try:
            pessoas = await _fixtures(db)
            (eid_a, mat_a), (_eid_b, mat_b) = pessoas

            # ── a) importador com linha inválida grava 1 falha; rerodar não duplica ───────────
            # «rg» porque `HEADER_MAP` precisa de ao menos UMA coluna de cadastro além do CPF.
            planilha = f"cpf;rg\n{CPF_FANTASMA};9999999\n".encode()
            for _ in range(2):
                await CadastroImportService(db).import_csv(planilha)
            n = (
                await db.execute(
                    text("SELECT count(*) FROM dp_importacao_falhas WHERE origem='planilha' AND cpf = :c"),
                    {"c": CPF_FANTASMA},
                )
            ).scalar()
            if n != 1:
                falhas_medidas.append(f"a) CPF sem cadastro importado 2x deixou {n} falha(s); esperado 1")
            st = (
                await db.execute(
                    text("SELECT status FROM dp_importacao_falhas WHERE cpf = :c LIMIT 1"), {"c": CPF_FANTASMA}
                )
            ).scalar()
            if st != "nao_resolvido":
                falhas_medidas.append(f"a) falha nasceu com status {st!r}; esperado 'nao_resolvido'")

            # ── b) resolver liga ao colaborador (e recusa id inventado) ──────────────────────
            fid = (
                await db.execute(
                    text("SELECT id FROM dp_importacao_falhas WHERE cpf = :c LIMIT 1"), {"c": CPF_FANTASMA}
                )
            ).scalar()
            try:
                await falhas.resolver(db, fid, FIX, employee_id=str(uuid4()))
                falhas_medidas.append("b) resolver aceitou employee_id inexistente")
            except ValueError:
                await db.rollback()
            await falhas.resolver(db, fid, FIX, employee_id=eid_a)
            r = (
                await db.execute(
                    text(
                        "SELECT status, CAST(employee_id AS text), resolvido_por FROM dp_importacao_falhas WHERE id = :i"
                    ),
                    {"i": fid},
                )
            ).first()
            if not r or r[0] != "resolvido_manual" or r[1] != eid_a or r[2] != FIX:
                falhas_medidas.append(
                    f"b) depois de resolver a falha ficou {r!r}; esperado (resolvido_manual, {eid_a}, {FIX})"
                )

            # ── c) export tem N linhas == régua de ativos recontada por SQL próprio ──────────
            esperado = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM employees e WHERE lower(coalesce(e.status,'')) <> ALL(:sem) "
                        "AND lower(coalesce(e.status,'')) <> 'demitido' AND coalesce(e.is_homologacao,false) = false"
                    ),
                    {"sem": list(SEM_VINCULO)},
                )
            ).scalar()
            linhas = await expo.linhas(db)
            if len(linhas) != esperado:
                falhas_medidas.append(f"c) export trouxe {len(linhas)} linha(s); a régua conta {esperado}")
            if linhas and "*" not in linhas[0]["cpf"] and len(linhas[0]["cpf"].replace(".", "").replace("-", "")) == 11:
                falhas_medidas.append("c) CPF saiu completo com admin=False (LGPD)")
            linhas_admin = await expo.linhas(db, admin=True)
            if len(linhas_admin) != esperado:
                falhas_medidas.append(f"c) export admin trouxe {len(linhas_admin)}; esperado {esperado}")

            # ── d) PDF e XLSX saem de verdade ────────────────────────────────────────────────
            cont = await expo.contadores(db)
            pdf = expo.para_pdf(linhas, subtitulo=f"oráculo {FIX}", resumo=cont)
            if not pdf.startswith(b"%PDF"):
                falhas_medidas.append("d) PDF da relação de colaboradores não começa com %PDF")
            xlsx = expo.para_xlsx(linhas)
            if not xlsx.startswith(b"PK"):
                falhas_medidas.append("d) XLSX não começa com PK (não é zip/xlsx)")
            csv_bytes = expo.para_csv(linhas)
            n_csv = csv_bytes.count(b"\r\n")
            if n_csv != len(linhas) + 1:
                falhas_medidas.append(f"d) CSV tem {n_csv} linha(s); esperado {len(linhas) + 1} (cabeçalho + dados)")

            # ── e) contadores da tela == recontados por SQL próprio ─────────────────────────
            from modules.people_management.ponto.coorte_ponto import SQL_NAO_AUSENTE_HOJE

            recontagem = {
                "Ativo": "lower(coalesce(e.status,'')) <> ALL(:sem) AND lower(coalesce(e.status,'')) <> 'demitido' "
                "AND coalesce(e.is_homologacao,false) = false",
                "Inativo": "lower(coalesce(e.status,'')) = ANY(:sem)",
                "Demitido": "lower(coalesce(e.status,'')) = 'demitido'",
                "Suspenso": "lower(coalesce(e.status,'')) = 'suspenso'",
                "Afastado": "lower(coalesce(e.status,'')) <> ALL(:sem) AND lower(coalesce(e.status,'')) <> 'demitido' "
                "AND coalesce(e.is_homologacao,false) = false AND EXISTS (SELECT 1 FROM sst_afastamentos a "
                "WHERE a.employee_id = e.id AND lower(coalesce(a.status,'')) IN ('em_andamento','ativo') "
                "AND a.data_retorno IS NULL)",
                "Férias": "lower(coalesce(e.status,'')) <> ALL(:sem) AND lower(coalesce(e.status,'')) <> 'demitido' "
                "AND coalesce(e.is_homologacao,false) = false AND EXISTS (SELECT 1 FROM hr_vacation_requests v "
                "WHERE v.employee_id = e.id AND upper(coalesce(v.status,'')) = 'APPROVED' "
                "AND (now() AT TIME ZONE 'America/Manaus')::date BETWEEN v.start_date AND v.end_date)",
                "Ausente hoje": "lower(coalesce(e.status,'')) = 'ativo' AND coalesce(e.is_homologacao,false) = false "
                f"AND NOT (TRUE {SQL_NAO_AUSENTE_HOJE})",
            }
            # Snapshot ÚNICO: o sandbox é compartilhado com as outras frentes da onda, e entre a
            # leitura do serviço e a recontagem duas pessoas já mudaram de status no meio (medido
            # em 24/09: «Inativo = 21; recontado = 23»). REPEATABLE READ faz as duas lerem o mesmo
            # instante — sem isso o oráculo pisca vermelho por concorrência, que é pior que não ter.
            await db.rollback()
            await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            cont_snap = await expo.contadores(db)
            por_label = {c["label"]: c["valor"] for c in cont_snap}
            if set(por_label) != set(recontagem):
                falhas_medidas.append(f"e) contadores da tela: {sorted(por_label)}; esperados {sorted(recontagem)}")
            for label, pred in recontagem.items():
                alvo = (
                    await db.execute(
                        text(f"SELECT count(*) FROM employees e WHERE {pred}"),  # noqa: S608 — predicado fixo
                        {"sem": list(SEM_VINCULO)},
                    )
                ).scalar()
                if por_label.get(label) != alvo:
                    falhas_medidas.append(f"e) contador «{label}» = {por_label.get(label)}; recontado = {alvo}")

            rubrica = (
                await db.execute(text("SELECT codigo FROM rubricas_folha WHERE ativo ORDER BY codigo LIMIT 1"))
            ).scalar()
            if not rubrica:
                raise RuntimeError("sem rubrica ativa em rubricas_folha — o CSV não tem como ser válido")
        except RuntimeError as exc:
            falhas_medidas.append(f"pré-condição: {exc}")
        finally:
            await db.rollback()

    # ── f/g) o CSV de apontamentos roda em sessão SÍNCRONA (mesmo caminho de «Apontar») ─────
    if rubrica and mat_a and mat_b:
        sdb = SyncSessionLocal()
        try:
            comp_livre = f"{MES_LIVRE:02d}/{ANO_LIVRE}"
            conteudo = _csv(mat_a, mat_b, rubrica, comp_livre)

            previa = await apontamentos_csv.importar(
                sdb, conteudo, FIX, arquivo=FIX, simular=True, current_user=_Autor()
            )
            if previa["apontamentos"] != 0:
                falhas_medidas.append(f"f) «só validar» gravou {previa['apontamentos']} apontamento(s)")
            if previa["validas"] != 2 or previa["recusadas"] != 1:
                falhas_medidas.append(
                    f"f) prévia: {previa['validas']} válida(s)/{previa['recusadas']} recusada(s); esperado 2/1"
                )
            nf_previa = sdb.execute(
                text("SELECT count(*) FROM dp_importacao_falhas WHERE identificador_origem LIKE :p"),
                {"p": f"{FIX}:%"},
            ).scalar()
            if nf_previa:
                falhas_medidas.append(
                    f"f) «só validar» disse «nada gravado» e deixou {nf_previa} falha(s) na fila — verde cego"
                )

            r = await apontamentos_csv.importar(sdb, conteudo, FIX, arquivo=FIX, simular=False, current_user=_Autor())
            if r["apontamentos"] != 2:
                falhas_medidas.append(f"f) gravou {r['apontamentos']} apontamento(s); esperado 2 — {r}")
            apontados = sdb.execute(
                text(
                    "SELECT count(*) FROM hr_payslips WHERE payslip_code LIKE :p AND contest_reason IS NOT NULL "
                    "AND contested_at IS NOT NULL"
                ),
                {"p": f"{FIX}%"},
            ).scalar()
            if apontados != 2:
                falhas_medidas.append(f"f) {apontados} holerite(s) com contest_reason; esperado 2")
            nf = sdb.execute(
                text(
                    "SELECT count(*) FROM dp_importacao_falhas WHERE origem='planilha' AND identificador_origem LIKE :p"
                ),
                {"p": f"{FIX}:%"},
            ).scalar()
            if nf != 1:
                falhas_medidas.append(f"f) a linha ruim deixou {nf} falha(s) na fila; esperado 1")
            # rerodar o MESMO arquivo: a falha continua única (chave origem+identificador+motivo)
            await apontamentos_csv.importar(sdb, conteudo, FIX, arquivo=FIX, simular=False, current_user=_Autor())
            nf2 = sdb.execute(
                text(
                    "SELECT count(*) FROM dp_importacao_falhas WHERE origem='planilha' AND identificador_origem LIKE :p"
                ),
                {"p": f"{FIX}:%"},
            ).scalar()
            if nf2 != 3:
                # 1 da linha ruim + 2 «já tem apontamento de outra origem» (as duas boas, na 2ª rodada)
                falhas_medidas.append(f"f) reimportar deixou {nf2} falha(s); esperado 3 (1 ruim + 2 já apontadas)")

            # ── g) competência com folha PUBLICADA → 409, nada gravado ──────────────────────
            pub = sdb.execute(
                text(
                    "SELECT reference_month, reference_year FROM hr_payslips WHERE status::text='published' "
                    "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
                )
            ).first()
            if not pub:
                falhas_medidas.append("g) não há folha publicada no banco — o 409 não pôde ser exercido")
            else:
                antes = sdb.execute(text("SELECT count(*) FROM dp_importacao_falhas")).scalar()
                try:
                    await apontamentos_csv.importar(
                        sdb,
                        _csv(mat_a, mat_b, rubrica, f"{pub[0]:02d}/{pub[1]}"),
                        FIX,
                        arquivo=FIX,
                        simular=False,
                        current_user=_Autor(),
                    )
                    falhas_medidas.append(f"g) competência {pub[0]:02d}/{pub[1]} PUBLICADA foi aceita; esperado 409")
                except HTTPException as exc:
                    if exc.status_code != 409:
                        falhas_medidas.append(f"g) competência publicada devolveu {exc.status_code}; esperado 409")
                depois = sdb.execute(text("SELECT count(*) FROM dp_importacao_falhas")).scalar()
                if depois != antes:
                    falhas_medidas.append(
                        f"g) o 409 ainda gravou {depois - antes} falha(s) — deveria recusar antes de tudo"
                    )
        finally:
            sdb.rollback()
            sdb.close()

    async with async_session_factory() as db:
        await _limpar(db)

    for f in falhas_medidas:
        print("DESVIO:", f)
    print(f"TOTAL desvios: {len(falhas_medidas)}")
    if falhas_medidas:
        return 1
    print(
        "OK V4: fila de falhas idempotente e resolvível · export/PDF com a régua de vínculo e CPF mascarado · "
        "contadores recontados · CSV de apontamentos pelo caminho de «Apontar», 409 em competência publicada"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
