"""Oráculo — DGX T1, DP/RH (24/09/2026): foto do colaborador, ficha única, certificados vencendo,
turnover mensal, cargo com CBO/exigências, termo disciplinar em PDF, férias × afastamento aberto.

Por que existe: a passagem de teste do DGX (docs/dgx/lacunas/dp_rh.md) achou 7 lacunas de valor
no grupo DP/RH. Cada uma é uma REGRA que pode apodrecer em silêncio: a foto gravada num caminho
que o crachá não resolve; a ficha que mostra 0 dependentes quando o JSON tem 2; a régua de
validade que chama de "Ativo" um certificado vencido; o turnover que conta PJ; férias programadas
para quem está afastado (o DGX recusa: "Já existe um afastamento para este colaborador").

O que afirma:
  0. Fiação: `departamento_pessoal.build` chama `_telas_t1` ANTES de `montar_grupos`; as 9 abas
     estão em `_dp_grupos.GRUPOS`; `rh.py` liga o PDF do termo; `vacation_controller` tem a trava.
  1. Réguas puras: `situacao_validade` (não expira / vencido / ≤30 / ≤60 / ≤90 / ativo) e
     `turnover` (fórmula do DGX: 1 admitido, 0 desligado, 1 no quadro → 0,50).
  2. Foto (fixture): `salvar_foto` grava arquivo que `cracha_pdf.foto_path` RESOLVE e escreve
     `employees.foto_url`; GIF é recusado; ZIP com matrícula + CPF + desconhecido → 2 gravadas,
     1 sem colaborador. Tudo desfeito ao fim (foto_url volta ao valor anterior, arquivos apagados).
  3. Ficha: 15 seções; dependentes == jsonb_array_length; benefícios ativos == count por SQL;
     férias == min(6, count por SQL) — recontados por SQL próprio, não pelo serviço.
  4. Certificados: nº de "Vencido" == recontagem por SQL das três fontes (RH, vigilante, ficha).
  5. Turnover: admitidos/desligados do último mês == SQL próprio (só CLT, sem PJ/candidato).
  6. Termo em PDF: da primeira medida com `document_text`, o PDF começa com %PDF e contém o nome.
  7. Férias × afastamento (fixture): `criar_vacation` recusa (409) com afastamento aberto e aceita
     depois do retorno; a solicitação criada é apagada.
  8. DDL de `cct_cargos` (cbo, tipo_servico, exige_cnh/cnv/porte_arma) aplicada por `_ensure`.

Estado medido no nascimento (sandbox, 24/09/2026 05:20): builder não existia → VERMELHO na fiação
(1 falha, o resto não roda). Verde após o código.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL dgx t1: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import io
import sys
import zipfile
from datetime import date, timedelta

ABAS = {
    "g-admissao": ["colaboradores-fotos", "colaborador-foto", "colaboradores-fotos-lote", "ficha-colaborador", "certificados-vencimento"],
    "g-visao": ["turnover-dashboard"],
    "g-cct": ["cargos-atributos", "cargo-atributos-form"],
}
JPG = b"\xff\xd8\xff\xe0" + bytes(64)  # assinatura JPEG basta para a régua de conteúdo
CLT = "coalesce(status,'') NOT IN ('candidato','pj_ativo','pj_inativo') AND coalesce(is_homologacao,false)=false"


class _User:
    id = None
    email = "oraculo@conectamais.pro"


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    # 0) fiação
    try:
        # departamento_pessoal PRIMEIRO (bloco próprio, fora do alcance do isort): é ele quem importa
        # `_dgx_t1_dp.router`; importar a frente antes dele fecha o ciclo (partially initialized module).
        from modules.operacional.controllers.redesign_builders import departamento_pessoal

        assert departamento_pessoal.build  # separa os blocos de import — mantém a ordem acima
        from modules.operacional.controllers.redesign_builders import _dgx_t1_dp as t1
        from modules.operacional.controllers.redesign_builders import _dp_grupos, rh
        from modules.people_management.hr.controllers import vacation_controller as vc
        from modules.people_management.hr.services import foto_colaborador as fc
        from modules.people_management.hr.services import termo_disciplinar_pdf as tp
        from modules.people_management.hr.services.cracha_pdf import foto_path
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: frente T1 não importa: {e}")
        print("TOTAL dgx t1: 1 falha(s)")
        return 1
    src = inspect.getsource(departamento_pessoal.build)
    if "_telas_t1(db, out)" not in src or src.index("_telas_t1(db, out)") > src.index("montar_grupos(out)"):
        falhas.append("build() não chama _telas_t1 antes de montar_grupos")
    grupos = {g[0]: [x[0] for x in g[3]] for g in _dp_grupos.GRUPOS}
    for g, ids in ABAS.items():
        for i in ids:
            if i not in grupos.get(g, []):
                falhas.append(f"aba {i} não está em {g}")
    if "/redesign/disciplina/" not in inspect.getsource(rh):
        falhas.append("rh.py não liga o PDF do termo em disc-medidas")
    if "sst_afastamentos" not in inspect.getsource(vc.criar_vacation):
        falhas.append("criar_vacation sem a trava de afastamento aberto")

    # 1) réguas puras
    hoje = date(2026, 9, 24)
    casos = [(None, "Não expira"), (hoje - timedelta(days=1), "Vencido há 1 d"), (hoje + timedelta(days=30), "Vence em 30 d"), (hoje + timedelta(days=60), "Vence em 60 d"), (hoje + timedelta(days=90), "Vence em 90 d"), (hoje + timedelta(days=91), "Ativo")]
    for v, esperado in casos:
        got = t1.situacao_validade(v, hoje)[0]
        if got != esperado:
            falhas.append(f"situacao_validade({v}) = {got!r}, esperado {esperado!r}")
    if t1.turnover(1, 0, 1) != 0.5 or t1.turnover(0, 0, 0) != 0.0 or t1.turnover(4, 2, 60) != 0.05:
        falhas.append("fórmula de turnover não é a do DGX ((adm+desl)/2/quadro)")
    try:
        fc.demo()
        tp.demo()
    except AssertionError as e:
        falhas.append(f"demo dos serviços: {e}")

    async with async_session_factory() as db:
        await t1._ensure(db)
        # 8) DDL
        cols = {
            r[0]
            for r in (await db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='cct_cargos'"))).fetchall()
        }
        for c in ("cbo", "tipo_servico", "exige_cnh", "exige_cnv", "exige_porte_arma"):
            if c not in cols:
                falhas.append(f"cct_cargos sem coluna {c}")

        pessoas = (
            await db.execute(
                text(
                    f"SELECT id::text, nome, coalesce(matricula,''), regexp_replace(coalesce(cpf,''),'\\D','','g'), foto_url FROM employees "
                    f"WHERE status='ativo' AND matricula IS NOT NULL AND cpf IS NOT NULL AND {CLT} ORDER BY nome LIMIT 2"
                )
            )
        ).fetchall()
        if len(pessoas) < 2:
            falhas.append("banco sem 2 ativos com matrícula e CPF para a fixture")
            pessoas = pessoas + pessoas
        (e1, n1, m1, _c1, f1), (e2, n2, _m2, c2, f2) = pessoas[0], pessoas[1]

        # 2) foto — fixture
        try:
            url = await fc.salvar_foto(db, e1, JPG, "image/jpeg", "f.jpg")
            gravado = (await db.execute(text("SELECT foto_url FROM employees WHERE id::text=:e"), {"e": e1})).scalar()
            if gravado != url:
                falhas.append(f"foto_url gravada {gravado!r} ≠ {url!r}")
            if not foto_path(url):
                falhas.append(f"cracha_pdf.foto_path não resolve {url!r} — o crachá continuaria sem foto")
            try:
                await fc.salvar_foto(db, e1, b"GIF89a" + bytes(20), "image/gif", "f.gif")
                falhas.append("GIF aceito como foto")
            except ValueError:
                pass
            zb = io.BytesIO()
            with zipfile.ZipFile(zb, "w") as z:
                z.writestr(f"{m1}.jpg", JPG)
                z.writestr(f"x/{c2}.jpg", JPG)
                z.writestr("999999999.jpg", JPG)
                z.writestr("leia.txt", b"x")
            r = await fc.importar_zip(db, zb.getvalue())
            if len(r["ok"]) != 2 or r["nao_encontrados"] != ["999999999.jpg"] or r["ignorados"] != ["leia.txt"]:
                falhas.append(f"lote ZIP: {r}")
            n_com = (await db.execute(text("SELECT count(*) FROM employees WHERE foto_url LIKE 'employees/%'"))).scalar()
            if n_com != 2:
                falhas.append(f"após o lote, {n_com} com foto (esperado 2)")
        finally:
            for eid, antes in ((e1, f1), (e2, f2)):
                await db.execute(text("UPDATE employees SET foto_url=:f WHERE id::text=:e"), {"f": antes, "e": eid})
                for p in fc.fotos_dir().glob(f"{eid}.*"):
                    p.unlink(missing_ok=True)
            await db.commit()

        # 3) ficha
        sec = await t1.ficha(db, e1)
        esperadas = {"dados_gerais", "contrato", "documentos", "endereco_e_contato", "banco_e_pix", "alocacao", "dependentes", "beneficios", "descontos_e_vales", "aso", "cursos_e_certificados", "disciplina", "afastamentos", "ferias", "uniforme_epi_e_equipamentos"}
        if set(sec) != esperadas:
            falhas.append(f"ficha com seções {sorted(set(sec) ^ esperadas)} a mais/menos")
        n_dep = (await db.execute(text("SELECT coalesce(jsonb_array_length(CASE WHEN jsonb_typeof(dependentes)='array' THEN dependentes END),0) FROM employees WHERE id::text=:e"), {"e": e1})).scalar()
        n_ben = (await db.execute(text("SELECT count(*) FROM employee_benefits WHERE employee_id::text=:e AND coalesce(status,'active')='active'"), {"e": e1})).scalar()
        n_fer = (await db.execute(text("SELECT count(*) FROM hr_vacation_requests WHERE employee_id::text=:e"), {"e": e1})).scalar()
        if len(sec.get("dependentes", [])) != n_dep or len(sec.get("beneficios", [])) != n_ben or len(sec.get("ferias", [])) != min(6, n_fer):
            falhas.append(f"ficha de {n1}: dependentes {len(sec.get('dependentes', []))}/{n_dep} · benefícios {len(sec.get('beneficios', []))}/{n_ben} · férias {len(sec.get('ferias', []))}/{min(6, n_fer)}")
        if sec["dados_gerais"].get("nome") != n1:
            falhas.append("ficha não é da pessoa pedida")

        # 4) certificados
        itens = await t1.certificados(db)
        venc_sql = (
            await db.execute(
                text(
                    "SELECT count(*) FROM (SELECT tc.expires_at::date AS v FROM training_certificates tc WHERE coalesce(tc.status::text,'')<>'revoked' "
                    "UNION ALL SELECT vence_em FROM vigilante_cursos "
                    f"UNION ALL SELECT x FROM employees e, unnest(ARRAY[e.cnv_validade, e.curso_vigilante_validade, e.cnh_validade, e.porte_arma_validade]) AS x WHERE e.status='ativo' AND {CLT}) u "
                    "WHERE v IS NOT NULL AND v < CURRENT_DATE"
                )
            )
        ).scalar()
        venc = sum(1 for i in itens if i["situacao"].startswith("Vencido"))
        if venc != venc_sql:
            falhas.append(f"certificados vencidos: tela {venc} × SQL {venc_sql}")

        # 5) turnover — último mês
        serie = await t1.serie_turnover(db, 3)
        ult = serie[-1]
        ini = ult["mes"]
        fim = (ini.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        r = (
            await db.execute(
                text(
                    f"SELECT count(*) FILTER (WHERE data_admissao BETWEEN :i AND :f), count(*) FILTER (WHERE coalesce(data_demissao,data_desligamento) BETWEEN :i AND :f) "
                    f"FROM employees WHERE {CLT} AND data_admissao IS NOT NULL"
                ),
                {"i": ini, "f": fim},
            )
        ).first()
        if (ult["admitidos"], ult["desligados"]) != (int(r[0]), int(r[1])):
            falhas.append(f"turnover {ini:%m/%Y}: série {ult['admitidos']}/{ult['desligados']} × SQL {r[0]}/{r[1]}")
        if ult["turnover"] != t1.turnover(ult["admitidos"], ult["desligados"], ult["quadro"] + ult["desligados"]):
            falhas.append("turnover do mês não segue a fórmula")

        # 6) termo PDF
        a = (await db.execute(text("SELECT * FROM disciplinary_actions WHERE document_text IS NOT NULL ORDER BY created_at DESC LIMIT 1"))).mappings().first()
        if a:
            pdf = tp.montar_termo(dict(a))
            if not pdf.startswith(b"%PDF"):
                falhas.append("termo não é PDF")
            try:
                from PyPDF2 import PdfReader

                txt = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)
                if (a["employee_name"] or "").split()[0] not in txt:
                    falhas.append("PDF do termo não traz o nome do empregado")
            except ImportError:
                pass
        else:
            print("aviso: nenhuma medida com document_text — bloco 6 sem caso de banco")

        # 7) férias × afastamento — fixture
        from fastapi import HTTPException

        await db.execute(
            text(
                "INSERT INTO sst_afastamentos (id, employee_id, employee_nome, tipo, data_inicio, status, observacoes, created_at, updated_at) "
                "VALUES (gen_random_uuid(), CAST(:e AS uuid), :n, 'doenca', CURRENT_DATE - 10, 'ativo', 'FIXTURE DGX T1', now(), now())"
            ),
            {"e": e2, "n": n2},
        )
        await db.commit()
        pedido = {"employee_id": e2, "start_date": "2027-03-01", "end_date": "2027-03-30", "vacation_type": "full"}
        try:
            try:
                await vc.criar_vacation(dict(pedido), _User(), db)
                falhas.append("férias aceitas com afastamento aberto")
            except HTTPException as ex:
                if ex.status_code != 409:
                    falhas.append(f"férias com afastamento aberto: HTTP {ex.status_code}, esperado 409")
            await db.rollback()
            await db.execute(text("UPDATE sst_afastamentos SET data_retorno = CURRENT_DATE - 1, status='encerrado' WHERE observacoes='FIXTURE DGX T1'"))
            await db.commit()
            try:
                await vc.criar_vacation(dict(pedido), _User(), db)
            except HTTPException as ex:
                if ex.status_code == 409 and "afastamento" in str(ex.detail):
                    falhas.append("férias ainda recusadas por afastamento depois do retorno")
        finally:
            await db.rollback()
            await db.execute(text("DELETE FROM hr_vacation_requests WHERE employee_id::text=:e AND start_date='2027-03-01'"), {"e": e2})
            await db.execute(text("DELETE FROM sst_afastamentos WHERE observacoes='FIXTURE DGX T1'"))
            await db.commit()

        # telas montam
        out: dict = {}
        await t1.telas(db, out)
        faltam = [i for ids in ABAS.values() for i in ids if i not in out]
        if faltam:
            falhas.append(f"telas() não montou {faltam}")
        n_at = (await db.execute(text(f"SELECT count(*) FROM employees WHERE status='ativo' AND {CLT}"))).scalar()
        if len((out.get("colaboradores-fotos") or {}).get("rows") or []) != n_at:
            falhas.append("tela de fotos não lista todos os ativos CLT")

    print(f"ativos CLT: {n_at} · certificados: {len(itens)} ({venc} vencidos) · turnover {ini:%m/%Y}: +{ult['admitidos']} −{ult['desligados']} quadro {ult['quadro']} → {ult['turnover']:.2f}")
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL dgx t1: {len(falhas)} falha(s)")
    if falhas:
        return 1
    print("OK dgx t1: foto resolve no crachá, ficha bate com o SQL, régua de validade, turnover DGX, termo em PDF, férias travadas por afastamento aberto")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
