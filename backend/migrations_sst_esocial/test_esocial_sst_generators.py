"""Teste unitário LEVE dos geradores XML eSocial SST (S-2210/S-2220/S-2230/S-2240).

- Usa dado REAL do banco (read-only, via psql no container postgres).
- NÃO transmite nada — apenas geração de XML.
- Prova 2 coisas por evento:
  1. Com o dado real INCOMPLETO de hoje => ValueError descritivo (honesto).
  2. Com o dado real + complementos mínimos => XML parseia e contém os
     campos obrigatórios do leiaute.

Execução (host): python3 migrations_sst_esocial/test_esocial_sst_generators.py
"""

import importlib.util
import json
import subprocess
import sys
from xml.etree.ElementTree import fromstring

SERVICE_PATH = "/opt/conecta-pro/backend/modules/people_management/hr/services/esocial_service.py"

spec = importlib.util.spec_from_file_location("esocial_service_sst", SERVICE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
Svc = mod.ESocialEventService

PSQL = [
    "docker", "exec", "conecta-pro-postgres",
    "psql", "-U", "postgres", "-d", "conecta_pro", "-t", "-A",
]


def q(sql: str):
    out = subprocess.run(
        PSQL + ["-c", f"SELECT COALESCE(json_agg(t), '[]'::json) FROM ({sql}) t"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return json.loads(out)


falhas = []
ok = []


def check(nome, fn):
    try:
        fn()
        ok.append(nome)
        print(f"  PASS  {nome}")
    except AssertionError as e:
        falhas.append(f"{nome}: {e}")
        print(f"  FAIL  {nome}: {e}")


def tag(xml, nome):
    """Encontra tag ignorando namespace."""
    root = fromstring(xml)
    for el in root.iter():
        if el.tag.split("}")[-1] == nome:
            return el
    return None


EMPREGADOR = q("SELECT cnpj, razao_social FROM empresas WHERE cnpj IS NOT NULL AND btrim(cnpj)<>'' LIMIT 1")[0]
CNPJ = EMPREGADOR["cnpj"]

# ---------------------------------------------------------------- S-2210 (CAT)
cats = q(
    "SELECT c.*, e.cpf, e.matricula, e.nome AS emp_nome FROM gp_cats c "
    "JOIN employees e ON e.id::text = c.employee_id LIMIT 1"
)
assert cats, "sem CAT real no banco"
cat = cats[0]
employee = {"id": cat["employee_id"], "cpf": cat["cpf"], "matricula": cat["matricula"]}


def t_s2210_incompleto():
    try:
        Svc.gerar_s2210(cat, employee, {"cnpj": CNPJ})
        raise AssertionError("deveria lançar ValueError (CAT real está incompleta)")
    except ValueError as e:
        msg = str(e)
        # (2026-07-08: hora_acidente já existe na CAT real — só as faltas restantes)
        assert "cod_sit_geradora" in msg, f"faltas não listadas: {msg}"


def t_s2210_completo():
    completo = dict(cat)
    completo.update(
        hora_acidente="14:30", hrs_trab_antes_acid="0630", ind_comun_policia="N",
        cod_sit_geradora="200004900", tp_local="3", numero_logradouro="100",
        cod_municipio="1302603", uf="AM", cod_parte_atingida="753510000",
        lateralidade="0", cod_agente_causador="303010200",
    )
    xml = Svc.gerar_s2210(completo, employee, {"cnpj": CNPJ})
    fromstring(xml)  # parseia
    for t in ("evtCAT", "ideEvento", "ideEmpregador", "ideVinculo", "dtAcid", "tpAcid",
              "codSitGeradora", "localAcidente", "parteAtingida", "agenteCausador"):
        assert tag(xml, t) is not None, f"tag obrigatória ausente: {t}"
    assert tag(xml, "dtAcid").text == str(cat["data_acidente"]), "dtAcid != dado real do banco"
    assert 'Id="ID1' in xml, "evento sem Id assinável"


check("S-2210 dado real incompleto => ValueError descritivo", t_s2210_incompleto)
check("S-2210 dado real + complementos => XML válido", t_s2210_completo)

# ---------------------------------------------------------------- S-2220 (ASO)
asos = q(
    "SELECT a.*, e.cpf, e.matricula FROM gp_asos a "
    "JOIN employees e ON e.id = a.employee_id "
    "WHERE a.data_realizacao IS NOT NULL AND a.apto IS NOT NULL LIMIT 1"
)
assert asos, "sem ASO realizado real no banco"
aso = asos[0]
emp_aso = {"id": str(aso["employee_id"]), "cpf": aso["cpf"], "matricula": aso["matricula"]}


def t_s2220_incompleto():
    # 2026-07-08 (Missão 1): gp_asos.exames foi populado (Tabela 27, 0295) —
    # a única falta do registro CRU é o respMonit, que o montador resolve via
    # sst_pcmso (médico REAL do PCMSO). Aqui provamos que SEM o montador o
    # gerador segue honesto.
    try:
        Svc.gerar_s2220(aso, emp_aso, CNPJ)
        raise AssertionError("deveria lançar ValueError (registro cru sem respMonit)")
    except ValueError as e:
        assert "resp_monit_nome" in str(e), f"faltas não listadas: {e}"


def t_s2220_completo():
    completo = dict(aso)
    completo.update(
        exames=[{"dt_exame": aso["data_realizacao"], "cod_procedimento": "0101"}],
        resp_monit_nome=aso["medico"], resp_monit_crm="4521", resp_monit_uf_crm="AM",
    )
    xml = Svc.gerar_s2220(completo, emp_aso, CNPJ)
    fromstring(xml)
    for t in ("evtMonit", "exMedOcup", "tpExameOcup", "aso", "dtAso", "resAso",
              "exame", "procRealizado", "medico", "nrCRM", "respMonit"):
        assert tag(xml, t) is not None, f"tag obrigatória ausente: {t}"
    assert tag(xml, "dtAso").text == str(aso["data_realizacao"]), "dtAso != dado real"
    assert tag(xml, "nrCRM").text == "4521", f"CRM real não parseado: {tag(xml,'nrCRM').text}"


check("S-2220 dado real incompleto => ValueError descritivo", t_s2220_incompleto)
check("S-2220 dado real + complementos => XML válido", t_s2220_completo)

# ------------------------------------------------------------ S-2230 (Afastamento)
afs = q(
    "SELECT a.*, e.cpf, e.matricula FROM sst_afastamentos a "
    "JOIN employees e ON e.id = a.employee_id WHERE a.tipo = 'doenca' LIMIT 1"
)
assert afs, "sem afastamento 'doenca' real no banco"
af = afs[0]
emp_af = {"id": str(af["employee_id"]), "cpf": af["cpf"], "matricula": af["matricula"]}


def t_s2230_real():
    xml = Svc.gerar_s2230(af, emp_af, CNPJ)
    fromstring(xml)
    for t in ("evtAfastTemp", "infoAfastamento", "iniAfastamento", "dtIniAfast", "codMotAfast"):
        assert tag(xml, t) is not None, f"tag obrigatória ausente: {t}"
    assert tag(xml, "dtIniAfast").text == str(af["data_inicio"]), "dtIniAfast != dado real"
    assert tag(xml, "codMotAfast").text == "03", "doenca deve mapear p/ Tabela 18 = 03"


def t_s2230_tipo_sem_mapa():
    ruim = dict(af)
    ruim["tipo"] = "suspensao_contratual"
    try:
        Svc.gerar_s2230(ruim, emp_af, CNPJ)
        raise AssertionError("tipo sem mapeamento deveria lançar ValueError")
    except ValueError as e:
        assert "Tabela 18" in str(e)


check("S-2230 dado real (doenca) => XML válido direto do banco", t_s2230_real)
check("S-2230 tipo sem código eSocial => ValueError honesto", t_s2230_tipo_sem_mapa)

# ------------------------------------------------------------ S-2240 (Riscos)
riscos = q("SELECT * FROM gp_risks WHERE status <> 'encerrado'")
emp_full = q(
    "SELECT id::text AS id, nome, cpf, matricula, data_admissao, cargo, setor "
    "FROM employees WHERE cpf IS NOT NULL AND matricula IS NOT NULL "
    "AND data_admissao IS NOT NULL AND cargo IS NOT NULL LIMIT 1"
)[0]


def t_s2240_incompleto():
    try:
        Svc.gerar_s2240(emp_full, riscos, CNPJ, dados={"local_amb": "1", "nr_insc_local": CNPJ, "dsc_setor": "Portaria"})
        raise AssertionError("deveria lançar ValueError (gp_risks sem cod Tabela 24)")
    except ValueError as e:
        assert "cod_agente_nocivo" in str(e), f"faltas não listadas: {e}"


def t_s2240_completo():
    riscos_ok = [dict(r, cod_agente_nocivo="02.01.014", utiliz_epc="2", utiliz_epi="2") for r in riscos[:2]]
    xml = Svc.gerar_s2240(
        emp_full, riscos_ok, CNPJ,
        dados={"local_amb": "1", "nr_insc_local": CNPJ, "dsc_setor": "Portaria"},
    )
    fromstring(xml)
    for t in ("evtExpRisco", "infoExpRisco", "dtIniCondicao", "infoAmb", "localAmb",
              "infoAtiv", "dscAtivDes", "agNoc", "codAgNoc", "epcEpi"):
        assert tag(xml, t) is not None, f"tag obrigatória ausente: {t}"
    assert tag(xml, "dtIniCondicao").text == str(emp_full["data_admissao"]), "dtIniCondicao != data_admissao real"


check("S-2240 riscos reais sem Tabela 24 => ValueError descritivo", t_s2240_incompleto)
check("S-2240 riscos reais + códigos => XML válido", t_s2240_completo)

print()
print(f"RESULTADO: {len(ok)} PASS / {len(falhas)} FAIL")
sys.exit(1 if falhas else 0)
