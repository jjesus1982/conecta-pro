"""DRY-RUN Missão 1 — prova que o ValueError honesto sumiu e o XML parseia.

NÃO transmite NADA: usa montar_xml_evento_sst (geração pura + enriquecimento
sst_pcmso/PGR/LTCAT) contra o banco REAL.

Prova em 3 atos:
  1. ANTES (código baked antigo): gerar_s2220/gerar_s2240 com o dado cru
     => ValueError descritivo (honesto).
  2. DEPOIS (código novo): montar_xml_evento_sst('S-2220', <aso realizado>)
     => XML parseia; respMonit = médico REAL do PCMSO (Pojucan/CRM 467/AM).
  3. DEPOIS: montar_xml_evento_sst('S-2240', <jardineiro GEILSON>)
     => XML parseia; agentes 02.01.001 (ruído 89 dB) e 02.01.002 (VMB 3,85 m/s²);
     e para um AGP => agente único 09.01.001 (ausência, conclusão do LTCAT).

Execução (host):
  docker cp backend/modules/people_management/hr/services/esocial_service.py \
      conecta-pro-backend:/tmp/esocial_service_novo.py
  docker cp backend/migrations_sst_esocial/dryrun_missao1_s2220_s2240.py \
      conecta-pro-backend:/tmp/dryrun_missao1.py
  docker exec conecta-pro-backend python /tmp/dryrun_missao1.py
"""

import asyncio
import importlib.util
import os
import sys
from xml.etree.ElementTree import fromstring

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

NOVO = "/tmp/esocial_service_novo.py"
ANTIGO = "/app/modules/people_management/hr/services/esocial_service.py"

ASO_REALIZADO = "4fc65216-a2cb-4c8c-bb02-be3ac7486203"  # admissional 2026-02-23, real
JARDINEIRO_ID = "0137ab13-5153-4b89-aaae-187264c73716"  # GEILSON RODRIGUES DE ANDRADE


def _load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tag(el):
    return el.tag.split("}")[-1]


def _achar(root, tag):
    for el in root.iter():
        if _tag(el) == tag:
            return el
    return None


def _achar_todos(root, tag):
    return [el for el in root.iter() if _tag(el) == tag]


async def main() -> int:
    url = os.environ["DATABASE_URL"]
    if "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    engine = create_async_engine(url)
    falhas = []

    antigo = _load(ANTIGO, "esocial_antigo")
    novo = _load(NOVO, "esocial_novo")

    async with AsyncSession(engine) as db:
        from sqlalchemy import text

        # ---------- ATO 1: ANTES — ValueError honesto ----------
        aso_cru = dict(
            (await db.execute(
                text("SELECT * FROM gp_asos WHERE aso_id = :r"), {"r": ASO_REALIZADO}
            )).mappings().first()
        )
        aso_sem_enriquecimento = {
            k: v for k, v in aso_cru.items()
            if k not in ("exames",)  # estado pré-migration: sem coluna exames
        }
        emp_aso = dict(
            (await db.execute(
                text("SELECT id::text AS id, nome, cpf, matricula, cargo, setor, "
                     "data_admissao FROM employees WHERE id = :e"),
                {"e": str(aso_cru["employee_id"])},
            )).mappings().first()
        )
        try:
            antigo.ESocialEventService.gerar_s2220(aso_sem_enriquecimento, emp_aso, "35710481000103")
            falhas.append("ATO1a: gerar_s2220 ANTIGO deveria ter lançado ValueError")
        except ValueError as e:
            print(f"[ATO 1a] OK — S-2220 antigo, ValueError honesto:\n         {e}\n")

        jard = dict(
            (await db.execute(
                text("SELECT id::text AS id, nome, cpf, matricula, cargo, setor, "
                     "data_admissao FROM employees WHERE id = :e"),
                {"e": JARDINEIRO_ID},
            )).mappings().first()
        )
        riscos_crus = [
            {k: v for k, v in dict(r).items()
             if k not in ("cod_agente_nocivo", "utiliz_epc", "utiliz_epi", "medicao",
                          "funcoes_aplicaveis")}
            for r in (await db.execute(
                text("SELECT * FROM gp_risks WHERE COALESCE(status,'')<>'encerrado' LIMIT 5")
            )).mappings().all()
        ]
        try:
            antigo.ESocialEventService.gerar_s2240(jard, riscos_crus, "35710481000103")
            falhas.append("ATO1b: gerar_s2240 ANTIGO deveria ter lançado ValueError")
        except ValueError as e:
            print(f"[ATO 1b] OK — S-2240 antigo, ValueError honesto:\n         {e}\n")

        # ---------- ATO 2: DEPOIS — S-2220 com PCMSO real ----------
        try:
            m = await novo.montar_xml_evento_sst(db, "S-2220", ASO_REALIZADO)
            root = fromstring(m["xml"])  # parseia ou explode
            resp = _achar(root, "respMonit")
            nm = _achar(resp, "nmResp").text
            crm = _achar(resp, "nrCRM").text
            uf = _achar(resp, "ufCRM").text
            proc = _achar(root, "procRealizado").text
            assert "POJUCAN" in nm.upper(), f"respMonit inesperado: {nm}"
            assert crm == "467" and uf == "AM", f"CRM/UF inesperados: {crm}/{uf}"
            assert proc == "0295", f"procRealizado inesperado: {proc}"
            print("[ATO 2 ] OK — S-2220 gerado e parseado (SEM transmitir):")
            print(f"         ASO {ASO_REALIZADO} ({emp_aso['nome']})")
            print(f"         respMonit: {nm} / CRM {crm}-{uf} (fonte: sst_pcmso)")
            print(f"         procRealizado (Tabela 27): {proc}\n")
        except Exception as e:  # noqa: BLE001
            falhas.append(f"ATO2: S-2220 novo falhou: {type(e).__name__}: {e}")

        # ---------- ATO 3: DEPOIS — S-2240 jardineiro + AGP ----------
        try:
            m = await novo.montar_xml_evento_sst(db, "S-2240", JARDINEIRO_ID)
            root = fromstring(m["xml"])
            cods = [_achar(ag, "codAgNoc").text for ag in _achar_todos(root, "agNoc")]
            setor = _achar(root, "dscSetor").text
            nr_insc = _achar_todos(root, "nrInsc")[-1].text
            assert sorted(cods) == ["02.01.001", "02.01.002"], f"agentes: {cods}"
            assert nr_insc == "23147782000191", f"nrInsc local: {nr_insc}"
            epcs = [e.text for e in _achar_todos(root, "utilizEPC")]
            epis = [e.text for e in _achar_todos(root, "utilizEPI")]
            print("[ATO 3a] OK — S-2240 JARDINEIRO (GEILSON) gerado e parseado:")
            print(f"         agentes Tabela 24: {cods} | setor: {setor}")
            print(f"         local: condomínio CNPJ {nr_insc} (Ideal Flores da Cidade)")
            print(f"         utilizEPC={epcs} utilizEPI={epis}\n")
        except Exception as e:  # noqa: BLE001
            falhas.append(f"ATO3a: S-2240 jardineiro falhou: {type(e).__name__}: {e}")

        agp = (await db.execute(text(
            "SELECT e.id::text AS id FROM employees e "
            "JOIN allocations a ON a.employee_id = e.id AND a.status='active' "
            "JOIN posts p ON p.id = a.post_id "
            "JOIN clients c ON upper(unaccent(c.name)) = upper(unaccent(p.name)) "
            "WHERE e.cargo = 'AGENTE DE PORTARIA' AND e.status='ativo' "
            "  AND length(regexp_replace(c.document_number,'\\D','','g')) = 14 "
            "  AND c.document_number <> '00000000000000' LIMIT 1"
        ))).scalar()
        if agp:
            try:
                m = await novo.montar_xml_evento_sst(db, "S-2240", agp)
                root = fromstring(m["xml"])
                cods = [_achar(ag, "codAgNoc").text for ag in _achar_todos(root, "agNoc")]
                assert cods == ["09.01.001"], f"AGP deveria declarar só 09.01.001: {cods}"
                print("[ATO 3b] OK — S-2240 AGENTE DE PORTARIA gerado e parseado:")
                print(f"         agente único: {cods[0]} (ausência — conclusão do LTCAT pág. 35)\n")
            except Exception as e:  # noqa: BLE001
                falhas.append(f"ATO3b: S-2240 AGP falhou: {type(e).__name__}: {e}")
        else:
            print("[ATO 3b] AGP com alocação ativa + CNPJ de condomínio não encontrado — pulado (honesto)\n")

    await engine.dispose()

    if falhas:
        print("FALHAS:")
        for f in falhas:
            print(" -", f)
        return 1
    print("DRY-RUN 100% OK — nada foi transmitido.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
