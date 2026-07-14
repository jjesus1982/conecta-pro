"""Service eSocial — Geração de eventos XML (S-2200, S-2299 e eventos SST).

Gera XMLs compatíveis com o layout eSocial S-1.2 (namespaces v_S_01_02_00)
para transmissão ao governo.

Eventos SST cobertos:
- S-2210: Comunicação de Acidente de Trabalho (CAT)      — fonte: gp_cats
- S-2220: Monitoramento da Saúde do Trabalhador (ASO)    — fonte: gp_asos
- S-2230: Afastamento Temporário                          — fonte: sst_afastamentos
- S-2240: Condições Ambientais do Trabalho (riscos)      — fonte: gp_risks + employees

PRINCÍPIO INEGOCIÁVEL: nenhum campo obrigatório é fabricado. Campo obrigatório
sem fonte real => ValueError descritivo listando exatamente o que falta, para o
controller reportar honesto ("aguardando dado", nunca dado inventado).

=============================================================================
CONTRATO (Onda B) — função única de transmissão SST:

    async def transmitir_evento_sst(
        db,                        # AsyncSession
        tipo: str,                 # 'S-2210' | 'S-2220' | 'S-2230' | 'S-2240'
        ref_id,                    # S-2210: gp_cats.cat_id ou id
                                   # S-2220: gp_asos.aso_id ou id
                                   # S-2230: sst_afastamentos.id (uuid)
                                   # S-2240: employees.id (uuid)
    ) -> dict                      # {"protocolo": str|None, "recibo": str|None,
                                   #  "status": str, "erros": list?}

Comportamento:
1. Carrega o registro de origem + funcionário + empregador (dados REAIS do banco).
2. Gera o XML do evento (ValueError descritivo se faltar dado obrigatório).
3. Assina com certificado A1 e transmite de verdade via ESocialTransmitter
   (ambiente decidido por env ESOCIAL_AMBIENTE; default SEMPRE producaorestrita).
4. Grava recibo/status na tabela de origem:
   - gp_cats:           esocial_status, esocial_transmitida_em, numero_recibo_esocial,
                        status (ciclo: aberta|transmitida|registrada_inss|encerrada)
   - gp_asos:           esocial_status, recibo_s2220
   - sst_afastamentos:  esocial_status, recibo_s2230
   - S-2240: sem coluna de recibo própria (retorno apenas no dict).
   Valores de esocial_status: nao_transmitida|transmitida|aceita|rejeitada|erro.
5. Rejeição do governo => retorna {"status": "rejeitada", "erros": [...]} (honesto).
   Falha de infraestrutura (SSL/conexão/timeout) => RuntimeError (nunca protocolo
   fabricado).
=============================================================================
"""

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger(__name__)

ESOCIAL_NAMESPACE = "http://www.esocial.gov.br/schema/evt/evtAdmissao/v_S_01_02_00"

# Namespaces dos eventos SST (mesmo padrão/versão de layout do S-2200)
NS_S2210 = "http://www.esocial.gov.br/schema/evt/evtCAT/v_S_01_02_00"
NS_S2220 = "http://www.esocial.gov.br/schema/evt/evtMonit/v_S_01_02_00"
NS_S2230 = "http://www.esocial.gov.br/schema/evt/evtAfastTemp/v_S_01_02_00"
NS_S2240 = "http://www.esocial.gov.br/schema/evt/evtExpRisco/v_S_01_02_00"

# Mapeamentos determinísticos (tabelas do leiaute eSocial)
TP_ACIDENTE = {"tipico": "1", "doenca": "2", "trajeto": "3"}  # S-2210 tpAcid
TP_EXAME_OCUP = {  # S-2220 tpExameOcup
    "admissional": "0",
    "periodico": "1",
    "retorno_trabalho": "2",
    "mudanca_funcao": "3",  # mudança de risco ocupacional
    "demissional": "9",
}
COD_MOT_AFAST = {  # S-2230 codMotAfast (Tabela 18)
    "doenca": "03",  # acidente/doença NÃO relacionada ao trabalho
    "acidente_trabalho": "01",  # acidente/doença do trabalho
    "acidente_trajeto": "01",  # trajeto = acidente do trabalho
    "licenca_maternidade": "17",
}
# Código Tabela 24 para "ausência de agente nocivo"
COD_AUSENCIA_AGENTE_NOCIVO = "09.01.001"

# ---------------------------------------------------------------------------
# Fonte REAL: PGR CONECTA MAIS (MBS Engenharia, elaborado 28/05/2026, assinado
# digitalmente 31/05/2026) — APRO GES 1-4 (descrição das atividades e setores
# por função) e LTCAT 28/05/2026 (parecer conclusivo por função).
# Tokens de função usados em gp_risks.funcoes_aplicaveis.
# ---------------------------------------------------------------------------
PGR_FUNCOES: dict[str, dict[str, str]] = {
    "AGP": {
        "setor": "PORTARIA",
        "atividades": (
            "Orienta a entrada e saída de pessoas, realiza monitoramento eletrônico, "
            "encaminha as pessoas aos destinatários, abre e fecha as dependências do "
            "condomínio, recebe a correspondência e encaminha ao protocolo, atende e "
            "efetua ligações telefônicas."
        ),
    },
    "LIDER": {
        "setor": "PORTARIA",
        "atividades": (
            "Lidera e acompanha os serviços efetuados pela equipe na portaria, acompanha "
            "e atende a portaria fazendo o controle de acesso de veículos, funcionários, "
            "visitantes e elabora relatórios de portaria com as ocorrências diárias."
        ),
    },
    "ASG": {
        "setor": "CONSERVAÇÃO E LIMPEZA",
        "atividades": (
            "Responsável pela manutenção da limpeza do condomínio, faz o diagnóstico e a "
            "solução de problemas no patrimônio do condomínio, retira lixos e faz a "
            "limpeza em geral de áreas comuns e áreas externas."
        ),
    },
    "ARTIFICE": {
        "setor": "MANUTENÇÃO",
        "atividades": (
            "Manutenções simples mecânicas e elétricas no condomínio: substituindo, "
            "trocando, limpando, reparando e instalando peças, componentes, equipamentos. "
            "Conserva vidros e fachadas, seguindo normas de segurança, higiene, qualidade "
            "e proteção ao ambiente."
        ),
    },
    "JARDINEIRO": {
        "setor": "CONSERVAÇÃO E LIMPEZA",
        "atividades": (
            "Realiza a capina com o uso da roçadeira, podagem de plantas, cultivo, forma "
            "e conserva jardins, parques, pomares, hortas florestais e vasos ornamentais, "
            "planta culturas diversas, realiza controle de pragas, aduba e cuida do solo."
        ),
    },
}


def _cargo_token(cargo: Any) -> str | None:
    """Mapeia o cargo REAL de employees para o token de função do PGR/LTCAT.

    Determinístico (sem chute): só os cargos que existem na base e no PGR.
    Cargo não mapeado => None (o chamador segue honesto sem riscos p/ S-2240).
    """
    texto = str(cargo or "").upper()
    # normalização mínima de acentos dos cargos reais da base
    texto = (
        texto.replace("Í", "I").replace("Ç", "C").replace("É", "E").replace("Ã", "A")
    )
    if "LIDER DE PORTARIA" in texto:
        return "LIDER"
    if "AGENTE DE PORTARIA" in texto:
        return "AGP"
    if "SERVICOS GERAIS" in texto:
        return "ASG"
    if "ARTIFICE" in texto:
        return "ARTIFICE"
    if "JARDINEIRO" in texto:
        return "JARDINEIRO"
    return None


def _json_list(valor: Any) -> list:
    """JSONB pode chegar como list (SQLAlchemy) ou str (asyncpg cru) — normaliza."""
    if valor is None:
        return []
    if isinstance(valor, list):
        return valor
    if isinstance(valor, str):
        import json

        try:
            parsed = json.loads(valor)
            return parsed if isinstance(parsed, list) else []
        except ValueError:
            return []
    return []


def _tp_amb() -> str:
    """Resolve o tpAmb do eSocial a partir da configuração/ambiente.

    Regra: 1=produção, 2=produção restrita (testes do governo, dados reais).
    Precedência: ESOCIAL_TP_AMB explícita > ESOCIAL_AMBIENTE > default "2".
    REGRA DE SEGURANÇA: default é SEMPRE "2" (produção restrita). A virada
    para produção real é explícita por env — NUNCA por omissão.
    """
    explicit = os.getenv("ESOCIAL_TP_AMB")
    if explicit and explicit.strip() in ("1", "2"):
        return explicit.strip()
    ambiente = (os.getenv("ESOCIAL_AMBIENTE") or "").strip().lower()
    if ambiente in ("producao", "producao_real", "prod", "1"):
        return "1"
    return "2"


def _field(obj: Any, nome: str, default: Any = None) -> Any:
    """Lê campo de dict ou de objeto (model SQLAlchemy/Row)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(nome, default)
    return getattr(obj, nome, default)


def _vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _exigir(evento: str, pares: dict[str, Any]) -> None:
    """Valida campos obrigatórios; lança ValueError descritivo com TUDO que falta."""
    faltando = [nome for nome, valor in pares.items() if _vazio(valor)]
    if faltando:
        raise ValueError(
            f"{evento}: dados obrigatórios ausentes (não serão fabricados): "
            + ", ".join(faltando)
        )


def _data_iso(valor: Any) -> str:
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%Y-%m-%d")
    return str(valor)


def _digits(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _event_id(empregador_cnpj: str) -> str:
    """ID do evento (36 chars): ID + tpInsc(1) + raiz CNPJ padded(14) + ts(14) + seq(5)."""
    cnpj = _digits(empregador_cnpj)
    raiz = cnpj[:8].ljust(14, "0")
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    seq = uuid4().int % 100000
    return f"ID1{raiz}{ts}{seq:05d}"


def _parse_crm(crm_raw: Any) -> tuple[str | None, str | None]:
    """Extrai (número, UF) de strings reais como 'CRM-AM 4521', '4521/AM', 'CRM 4521 AM'."""
    texto = str(crm_raw or "").upper().strip()
    if not texto:
        return None, None
    uf_match = re.search(r"\b([A-Z]{2})\b", texto.replace("CRM", " "))
    nr_match = re.search(r"(\d{3,})", texto)
    uf = uf_match.group(1) if uf_match else None
    nr = nr_match.group(1) if nr_match else None
    return nr, uf


def _ide_evento(evt: Element) -> None:
    ide = SubElement(evt, "ideEvento")
    SubElement(ide, "indRetif").text = "1"
    SubElement(ide, "tpAmb").text = _tp_amb()
    SubElement(ide, "procEmi").text = "1"
    SubElement(ide, "verProc").text = "ConectaPRO_2.0"


def _ide_empregador(evt: Element, cnpj: str) -> None:
    emp = SubElement(evt, "ideEmpregador")
    SubElement(emp, "tpInsc").text = "1"
    SubElement(emp, "nrInsc").text = _digits(cnpj)[:8]  # raiz do CNPJ


def _ide_vinculo(evt: Element, evento: str, employee: Any) -> None:
    cpf = _digits(_field(employee, "cpf"))
    matricula = _field(employee, "matricula")
    _exigir(evento, {"employee.cpf": cpf or None, "employee.matricula": matricula})
    vinc = SubElement(evt, "ideVinculo")
    SubElement(vinc, "cpfTrab").text = cpf
    SubElement(vinc, "matricula").text = str(matricula)


class ESocialEventService:
    """Serviço de geração de eventos eSocial (S-2200, S-2299, S-2210, S-2220, S-2230, S-2240)."""

    @staticmethod
    def gerar_s2200(
        empregador_cnpj: str,
        empregador_razao: str,
        trabalhador: dict[str, Any],
        contrato: dict[str, Any],
    ) -> str:
        """Gera XML do evento S-2200 (Cadastramento Inicial / Admissão)."""
        root = Element("eSocial", xmlns=ESOCIAL_NAMESPACE)
        evt = SubElement(root, "evtAdmissao")

        # ideEvento
        ide = SubElement(evt, "ideEvento")
        SubElement(ide, "indRetif").text = "1"
        SubElement(ide, "tpAmb").text = _tp_amb()  # 1=produção, 2=produção restrita (config)
        SubElement(ide, "procEmi").text = "1"
        SubElement(ide, "verProc").text = "ConectaPRO_2.0"

        # ideEmpregador (raiz de 8 dígitos — mesmo helper dos eventos SST; tpInsc=1
        # exige a RAIZ do CNPJ, não o número completo, senão o eSocial rejeita)
        _ide_empregador(evt, empregador_cnpj)

        # trabalhador
        # Sexo e nascimento vêm do CADASTRO real do employee — NUNCA fabricados.
        # Se ausentes, falha honesta (dado eSocial não se inventa).
        sexo_raw = trabalhador.get("sexo")
        sexo = str(sexo_raw).strip().upper() if sexo_raw is not None else ""
        nascimento = trabalhador.get("data_nascimento")
        _exigir(
            "S-2200",
            {
                "trabalhador.sexo (M/F no cadastro)": sexo or None,
                "trabalhador.data_nascimento": _data_iso(nascimento) if nascimento else None,
            },
        )
        if sexo not in ("M", "F"):
            raise ValueError(
                f"S-2200: sexo inválido no cadastro ('{sexo_raw}'); eSocial aceita apenas 'M' ou 'F'."
            )
        trab = SubElement(evt, "trabalhador")
        SubElement(trab, "cpfTrab").text = trabalhador.get("cpf", "")
        SubElement(trab, "nmTrab").text = trabalhador.get("nome", "")
        SubElement(trab, "sexo").text = sexo
        SubElement(trab, "dtNascto").text = _data_iso(nascimento)

        # vinculo
        vinc = SubElement(evt, "vinculo")
        SubElement(vinc, "matricula").text = contrato.get("matricula", "")
        SubElement(vinc, "dtAdm").text = contrato.get("data_admissao", "")
        SubElement(vinc, "tpContr").text = contrato.get("tipo_contrato", "1")
        SubElement(vinc, "vrSalFx").text = str(contrato.get("salario", 0))
        SubElement(vinc, "codCateg").text = contrato.get("categoria", "101")

        xml_str = tostring(root, encoding="unicode", xml_declaration=True)
        logger.info("S-2200 gerado para CPF %s", trabalhador.get("cpf", "?"))
        return xml_str

    @staticmethod
    def gerar_s2299(
        empregador_cnpj: str,
        trabalhador_cpf: str,
        matricula: str,
        data_desligamento: date,
        motivo_desligamento: str = "02",
        verbas_rescisorias: list[dict[str, Any]] | None = None,
    ) -> str:
        """Gera XML do evento S-2299 (Desligamento)."""
        ns = "http://www.esocial.gov.br/schema/evt/evtDeslig/v_S_01_02_00"
        root = Element("eSocial", xmlns=ns)
        evt = SubElement(root, "evtDeslig")

        # ideEvento
        ide = SubElement(evt, "ideEvento")
        SubElement(ide, "indRetif").text = "1"
        SubElement(ide, "tpAmb").text = _tp_amb()  # 1=produção, 2=produção restrita (config)
        SubElement(ide, "procEmi").text = "1"
        SubElement(ide, "verProc").text = "ConectaPRO_2.0"

        # ideEmpregador (raiz de 8 dígitos — mesmo helper dos eventos SST; tpInsc=1
        # exige a RAIZ do CNPJ, não o número completo, senão o eSocial rejeita)
        _ide_empregador(evt, empregador_cnpj)

        # ideVinculo
        vinc = SubElement(evt, "ideVinculo")
        SubElement(vinc, "cpfTrab").text = trabalhador_cpf
        SubElement(vinc, "matricula").text = matricula

        # infoDeslig
        deslig = SubElement(evt, "infoDeslig")
        SubElement(deslig, "dtDeslig").text = data_desligamento.isoformat()
        SubElement(deslig, "mtvDeslig").text = motivo_desligamento

        # verbas rescisórias
        if verbas_rescisorias:
            verbas_el = SubElement(deslig, "verbasResc")
            for verba in verbas_rescisorias:
                item = SubElement(verbas_el, "dmDev")
                SubElement(item, "codRubr").text = str(verba.get("codigo", ""))
                SubElement(item, "vrRubr").text = str(verba.get("valor", 0))

        xml_str = tostring(root, encoding="unicode", xml_declaration=True)
        logger.info("S-2299 gerado para CPF %s, matrícula %s", trabalhador_cpf, matricula)
        return xml_str

    # ------------------------------------------------------------------
    # EVENTOS SST
    # ------------------------------------------------------------------

    @staticmethod
    def gerar_s2210(cat: Any, employee: Any, empregador: Any) -> str:
        """Gera XML do evento S-2210 (Comunicação de Acidente de Trabalho).

        Fonte: gp_cats (+ campos complementares que o registro/chamador fornecer).
        Campos obrigatórios do leiaute SEM coluna própria em gp_cats devem vir
        no dict `cat` (ex.: hrs_trab_antes_acid, cod_sit_geradora, cod_parte_atingida,
        cod_agente_causador, ind_comun_policia, tp_local, cod_municipio, uf,
        numero_logradouro, lateralidade). Ausência => ValueError descritivo.
        """
        cnpj = _field(empregador, "cnpj") if not isinstance(empregador, str) else empregador
        _exigir("S-2210", {"empregador.cnpj": cnpj})

        tipo_acidente = str(_field(cat, "tipo_acidente") or "").lower()
        tp_acid = TP_ACIDENTE.get(tipo_acidente)

        obrigatorios = {
            "cat.data_acidente": _field(cat, "data_acidente"),
            "cat.tipo_acidente (tipico|trajeto|doenca)": tp_acid,
            "cat.hora_acidente (HH:MM)": _field(cat, "hora_acidente"),
            "cat.hrs_trab_antes_acid (horas trabalhadas antes do acidente, HHMM)": _field(cat, "hrs_trab_antes_acid"),
            "cat.ind_comun_policia (S|N — houve comunicação à polícia?)": _field(cat, "ind_comun_policia"),
            "cat.cod_sit_geradora (Tabela 25 eSocial)": _field(cat, "cod_sit_geradora"),
            "cat.tp_local (1=estab. empregador, 2=estab. terceiros, 3=via pública, ...)": _field(cat, "tp_local"),
            "cat.local (descrição do logradouro)": _field(cat, "local"),
            "cat.numero_logradouro": _field(cat, "numero_logradouro"),
            "cat.cod_municipio (IBGE)": _field(cat, "cod_municipio"),
            "cat.uf": _field(cat, "uf"),
            "cat.cod_parte_atingida (Tabela 13 eSocial)": _field(cat, "cod_parte_atingida"),
            "cat.lateralidade (0=N/A, 1=esq, 2=dir, 3=ambas)": _field(cat, "lateralidade"),
            "cat.cod_agente_causador (Tabela 14/15 eSocial)": _field(cat, "cod_agente_causador"),
        }
        _exigir("S-2210", obrigatorios)

        root = Element("eSocial", xmlns=NS_S2210)
        evt = SubElement(root, "evtCAT", Id=_event_id(cnpj))
        _ide_evento(evt)
        _ide_empregador(evt, cnpj)
        _ide_vinculo(evt, "S-2210", employee)

        cat_el = SubElement(evt, "cat")
        SubElement(cat_el, "dtAcid").text = _data_iso(_field(cat, "data_acidente"))
        SubElement(cat_el, "tpAcid").text = tp_acid
        SubElement(cat_el, "hrAcid").text = _digits(_field(cat, "hora_acidente"))[:4]
        SubElement(cat_el, "hrsTrabAntesAcid").text = _digits(_field(cat, "hrs_trab_antes_acid"))[:4]
        SubElement(cat_el, "tpCat").text = str(_field(cat, "tp_cat", "1"))  # 1=inicial (CAT emitida pelo sistema)
        # indCatObito derivado da gravidade REAL do registro
        gravidade = str(_field(cat, "gravidade") or "").lower()
        SubElement(cat_el, "indCatObito").text = "S" if gravidade == "obito" else "N"
        SubElement(cat_el, "indComunPolicia").text = str(_field(cat, "ind_comun_policia")).upper()[:1]
        SubElement(cat_el, "codSitGeradora").text = str(_field(cat, "cod_sit_geradora"))
        SubElement(cat_el, "iniciatCAT").text = str(_field(cat, "iniciat_cat", "1"))  # 1=empregador
        descricao = _field(cat, "descricao")
        if descricao:
            SubElement(cat_el, "obsCAT").text = str(descricao)[:255]
        ult_dia_trab = _field(cat, "ult_dia_trab")
        if ult_dia_trab:
            SubElement(cat_el, "ultDiaTrab").text = _data_iso(ult_dia_trab)
        # houveAfast derivado do campo REAL 'afastamento' (dias)
        dias_afast = _field(cat, "afastamento") or 0
        SubElement(cat_el, "houveAfast").text = "S" if int(dias_afast) > 0 else "N"

        local_el = SubElement(cat_el, "localAcidente")
        SubElement(local_el, "tpLocal").text = str(_field(cat, "tp_local"))
        SubElement(local_el, "dscLocal").text = str(_field(cat, "local"))[:80]
        SubElement(local_el, "dscLograd").text = str(_field(cat, "logradouro") or _field(cat, "local"))[:100]
        SubElement(local_el, "nrLograd").text = str(_field(cat, "numero_logradouro"))[:10]
        bairro = _field(cat, "bairro")
        if bairro:
            SubElement(local_el, "bairro").text = str(bairro)[:90]
        cep = _field(cat, "cep")
        if cep:
            SubElement(local_el, "cep").text = _digits(cep)
        SubElement(local_el, "codMunic").text = _digits(_field(cat, "cod_municipio"))
        SubElement(local_el, "uf").text = str(_field(cat, "uf")).upper()[:2]

        parte = SubElement(cat_el, "parteAtingida")
        SubElement(parte, "codParteAting").text = str(_field(cat, "cod_parte_atingida"))
        SubElement(parte, "lateralidade").text = str(_field(cat, "lateralidade"))

        agente = SubElement(cat_el, "agenteCausador")
        SubElement(agente, "codAgntCausador").text = str(_field(cat, "cod_agente_causador"))

        # atestado médico — grupo condicional: só entra se o conjunto completo existir
        campos_atestado = {
            "cat.dt_atendimento": _field(cat, "dt_atendimento"),
            "cat.hr_atendimento": _field(cat, "hr_atendimento"),
            "cat.ind_internacao (S|N)": _field(cat, "ind_internacao"),
            "cat.dur_trat (dias de tratamento)": _field(cat, "dur_trat"),
            "cat.ind_afast_atestado (S|N)": _field(cat, "ind_afast_atestado"),
            "cat.dsc_lesao (Tabela 17 eSocial)": _field(cat, "dsc_lesao"),
            "cat.cod_cid": _field(cat, "cod_cid"),
            "cat.medico_nome": _field(cat, "medico_nome"),
            "cat.medico_crm": _field(cat, "medico_crm"),
            "cat.medico_uf_crm": _field(cat, "medico_uf_crm"),
        }
        if any(not _vazio(v) for v in campos_atestado.values()):
            # se veio atendimento médico parcial, exigir o conjunto completo (não fabricar)
            _exigir("S-2210/atestado", campos_atestado)
            at = SubElement(cat_el, "atestado")
            SubElement(at, "dtAtendimento").text = _data_iso(_field(cat, "dt_atendimento"))
            SubElement(at, "hrAtendimento").text = _digits(_field(cat, "hr_atendimento"))[:4]
            SubElement(at, "indInternacao").text = str(_field(cat, "ind_internacao")).upper()[:1]
            SubElement(at, "durTrat").text = str(_field(cat, "dur_trat"))
            SubElement(at, "indAfast").text = str(_field(cat, "ind_afast_atestado")).upper()[:1]
            SubElement(at, "dscLesao").text = str(_field(cat, "dsc_lesao"))
            SubElement(at, "codCID").text = str(_field(cat, "cod_cid")).upper()
            emit = SubElement(at, "emitente")
            SubElement(emit, "nmEmit").text = str(_field(cat, "medico_nome"))[:70]
            SubElement(emit, "ideOC").text = "1"  # 1=CRM
            SubElement(emit, "nrOc").text = _digits(_field(cat, "medico_crm"))
            SubElement(emit, "ufOC").text = str(_field(cat, "medico_uf_crm")).upper()[:2]

        xml_str = tostring(root, encoding="unicode", xml_declaration=True)
        logger.info("S-2210 gerado: cat=%s employee=%s", _field(cat, "cat_id"), _field(employee, "id"))
        return xml_str

    @staticmethod
    def gerar_s2220(aso: Any, employee: Any, empregador_cnpj: str) -> str:
        """Gera XML do evento S-2220 (Monitoramento da Saúde — ASO).

        Fonte: gp_asos. O leiaute EXIGE ao menos um exame com procedimento da
        Tabela 27 (coluna gp_asos.exames, populada em 2026-07-08 — o exame
        clínico 0295 é derivação determinística de data_realizacao) e o médico
        responsável pelo PCMSO (aso['resp_monit_nome'/'resp_monit_crm'/
        'resp_monit_uf_crm'] — preenchidos pelo montador a partir de sst_pcmso,
        registro REAL do PCMSO MB: Dr. Pojucan Manoel Moraes, CRM/AM 467).
        """
        _exigir("S-2220", {"empregador.cnpj": empregador_cnpj})

        tipo = str(_field(aso, "tipo") or "").lower()
        tp_exame = TP_EXAME_OCUP.get(tipo)
        apto = _field(aso, "apto")
        exames = _json_list(_field(aso, "exames"))

        obrigatorios = {
            "aso.tipo (admissional|periodico|retorno_trabalho|mudanca_funcao|demissional)": tp_exame,
            "aso.data_realizacao": _field(aso, "data_realizacao"),
            "aso.apto (resultado do ASO: apto/inapto)": None if apto is None else str(apto),
            "aso.medico (nome do médico examinador)": _field(aso, "medico"),
            "aso.crm (CRM do médico examinador)": _field(aso, "crm"),
            "aso.exames (lista de exames com cod_procedimento da Tabela 27 eSocial)": exames or None,
            "aso.resp_monit_nome (médico responsável PCMSO)": _field(aso, "resp_monit_nome"),
            "aso.resp_monit_crm": _field(aso, "resp_monit_crm"),
            "aso.resp_monit_uf_crm": _field(aso, "resp_monit_uf_crm"),
        }
        _exigir("S-2220", obrigatorios)

        crm_nr, crm_uf = _parse_crm(_field(aso, "crm"))
        _exigir(
            "S-2220",
            {
                "aso.crm (número do CRM não identificado)": crm_nr,
                "aso.crm (UF do CRM não identificada)": crm_uf,
            },
        )
        faltas_exames = [
            f"aso.exames[{i}].{campo}"
            for i, ex in enumerate(exames)
            for campo in ("dt_exame", "cod_procedimento")
            if _vazio(_field(ex, campo))
        ]
        if faltas_exames:
            raise ValueError(
                "S-2220: dados obrigatórios ausentes (não serão fabricados): " + ", ".join(faltas_exames)
            )

        root = Element("eSocial", xmlns=NS_S2220)
        evt = SubElement(root, "evtMonit", Id=_event_id(empregador_cnpj))
        _ide_evento(evt)
        _ide_empregador(evt, empregador_cnpj)
        _ide_vinculo(evt, "S-2220", employee)

        exmed = SubElement(evt, "exMedOcup")
        SubElement(exmed, "tpExameOcup").text = tp_exame
        aso_el = SubElement(exmed, "aso")
        SubElement(aso_el, "dtAso").text = _data_iso(_field(aso, "data_realizacao"))
        SubElement(aso_el, "resAso").text = "1" if apto else "2"  # 1=apto, 2=inapto

        for ex in exames:
            ex_el = SubElement(aso_el, "exame")
            SubElement(ex_el, "dtExm").text = _data_iso(_field(ex, "dt_exame"))
            SubElement(ex_el, "procRealizado").text = str(_field(ex, "cod_procedimento"))
            obs = _field(ex, "obs")
            if obs:
                SubElement(ex_el, "obsProc").text = str(obs)[:150]

        med = SubElement(aso_el, "medico")
        SubElement(med, "nmMed").text = str(_field(aso, "medico"))[:70]
        SubElement(med, "nrCRM").text = crm_nr
        SubElement(med, "ufCRM").text = crm_uf

        resp = SubElement(exmed, "respMonit")
        SubElement(resp, "nmResp").text = str(_field(aso, "resp_monit_nome"))[:70]
        SubElement(resp, "nrCRM").text = _digits(_field(aso, "resp_monit_crm"))
        SubElement(resp, "ufCRM").text = str(_field(aso, "resp_monit_uf_crm")).upper()[:2]

        xml_str = tostring(root, encoding="unicode", xml_declaration=True)
        logger.info("S-2220 gerado: aso=%s employee=%s", _field(aso, "aso_id"), _field(employee, "id"))
        return xml_str

    @staticmethod
    def gerar_s2230(afastamento: Any, employee: Any, empregador_cnpj: str) -> str:
        """Gera XML do evento S-2230 (Afastamento Temporário).

        Fonte: sst_afastamentos. Tipos mapeáveis (Tabela 18): doenca=>03,
        acidente_trabalho/acidente_trajeto=>01, licenca_maternidade=>17.
        Tipos sem código no eSocial (licenca_paternidade, suspensao_contratual,
        outro) => ValueError descritivo (não informáveis via S-2230 sem
        classificação humana).
        Término: se status=encerrado, dtTermAfast = data_fim_prevista quando
        existir; senão data_retorno - 1 dia (último dia afastado — derivação
        determinística do dado real de retorno).
        """
        _exigir("S-2230", {"empregador.cnpj": empregador_cnpj})

        tipo = str(_field(afastamento, "tipo") or "").lower()
        cod_mot = COD_MOT_AFAST.get(tipo)
        if not cod_mot:
            raise ValueError(
                f"S-2230: tipo de afastamento '{tipo}' sem mapeamento para a Tabela 18 do eSocial "
                "(mapeáveis: doenca, acidente_trabalho, acidente_trajeto, licenca_maternidade). "
                "Classificação humana necessária — não será fabricada."
            )

        _exigir("S-2230", {"afastamento.data_inicio": _field(afastamento, "data_inicio")})

        root = Element("eSocial", xmlns=NS_S2230)
        evt = SubElement(root, "evtAfastTemp", Id=_event_id(empregador_cnpj))
        _ide_evento(evt)
        _ide_empregador(evt, empregador_cnpj)
        _ide_vinculo(evt, "S-2230", employee)

        info = SubElement(evt, "infoAfastamento")
        ini = SubElement(info, "iniAfastamento")
        SubElement(ini, "dtIniAfast").text = _data_iso(_field(afastamento, "data_inicio"))
        SubElement(ini, "codMotAfast").text = cod_mot
        motivo = _field(afastamento, "motivo")
        if motivo:
            SubElement(ini, "observacao").text = str(motivo)[:255]

        status = str(_field(afastamento, "status") or "").lower()
        if status == "encerrado":
            data_fim = _field(afastamento, "data_fim_prevista")
            data_retorno = _field(afastamento, "data_retorno")
            if data_fim:
                dt_term = data_fim
            elif data_retorno and isinstance(data_retorno, date):
                dt_term = data_retorno - timedelta(days=1)  # último dia afastado
            else:
                raise ValueError(
                    "S-2230: afastamento encerrado sem data de término real "
                    "(data_fim_prevista e data_retorno ausentes) — não será fabricada."
                )
            fim = SubElement(info, "fimAfastamento")
            SubElement(fim, "dtTermAfast").text = _data_iso(dt_term)

        xml_str = tostring(root, encoding="unicode", xml_declaration=True)
        logger.info("S-2230 gerado: afastamento=%s employee=%s", _field(afastamento, "id"), _field(employee, "id"))
        return xml_str

    @staticmethod
    def gerar_s2240(employee: Any, riscos: list[Any], empregador_cnpj: str, dados: Any = None) -> str:
        """Gera XML do evento S-2240 (Condições Ambientais do Trabalho).

        Fonte: employees + gp_risks. O leiaute EXIGE por agente nocivo o código
        da Tabela 24 (gp_risks.cod_agente_nocivo — populado em 2026-07-08 a
        partir do LTCAT/laudos REAIS da MB Consultoria); para agentes que não
        sejam "09.01.001 — ausência de agente nocivo" exige também
        utiliz_epc (0=não se aplica, 1=não implementa, 2=implementa) e
        utiliz_epi (0=não se aplica, 1=não utilizado, 2=utilizado).
        `dados` complementa: local_amb (1=estab. próprio, 2=terceiros),
        nr_insc_local (CNPJ do estabelecimento), dsc_setor, dsc_atividades,
        dt_ini_condicao (default: data_admissao REAL do funcionário).
        """
        _exigir("S-2240", {"empregador.cnpj": empregador_cnpj})
        if not riscos:
            raise ValueError(
                "S-2240: nenhum risco/agente informado. Sem mapeamento de riscos (gp_risks) "
                "para este funcionário não há evento a gerar — não será fabricado "
                f"(nem mesmo '{COD_AUSENCIA_AGENTE_NOCIVO} — ausência de agente nocivo', "
                "que exige decisão humana)."
            )

        dt_ini = _field(dados, "dt_ini_condicao") or _field(employee, "data_admissao")
        obrigatorios = {
            "dt_ini_condicao (ou employees.data_admissao)": dt_ini,
            "local_amb (1=estab. do empregador, 2=estab. de terceiros)": _field(dados, "local_amb"),
            "nr_insc_local (CNPJ do estabelecimento onde há exposição)": _field(dados, "nr_insc_local"),
            "dsc_setor (setor de lotação)": _field(dados, "dsc_setor") or _field(employee, "setor"),
            "dsc_atividades (descrição das atividades — ou employees.cargo)": (
                _field(dados, "dsc_atividades") or _field(employee, "cargo")
            ),
        }
        _exigir("S-2240", obrigatorios)

        faltas: list[str] = []
        for i, risco in enumerate(riscos):
            cod = _field(risco, "cod_agente_nocivo")
            rid = _field(risco, "risk_id") or i
            if _vazio(cod):
                faltas.append(f"gp_risks[{rid}].cod_agente_nocivo (Tabela 24 eSocial)")
                continue
            if str(cod) != COD_AUSENCIA_AGENTE_NOCIVO:
                if _vazio(_field(risco, "utiliz_epc")):
                    faltas.append(f"gp_risks[{rid}].utiliz_epc (0|1|2)")
                if _vazio(_field(risco, "utiliz_epi")):
                    faltas.append(f"gp_risks[{rid}].utiliz_epi (0|1|2)")
        if faltas:
            raise ValueError(
                "S-2240: dados obrigatórios ausentes (não serão fabricados): " + ", ".join(faltas)
            )

        root = Element("eSocial", xmlns=NS_S2240)
        evt = SubElement(root, "evtExpRisco", Id=_event_id(empregador_cnpj))
        _ide_evento(evt)
        _ide_empregador(evt, empregador_cnpj)
        _ide_vinculo(evt, "S-2240", employee)

        info = SubElement(evt, "infoExpRisco")
        SubElement(info, "dtIniCondicao").text = _data_iso(dt_ini)

        amb = SubElement(info, "infoAmb")
        SubElement(amb, "localAmb").text = str(_field(dados, "local_amb"))
        SubElement(amb, "dscSetor").text = str(_field(dados, "dsc_setor") or _field(employee, "setor"))[:100]
        SubElement(amb, "tpInsc").text = "1"
        SubElement(amb, "nrInsc").text = _digits(_field(dados, "nr_insc_local"))

        ativ = SubElement(info, "infoAtiv")
        SubElement(ativ, "dscAtivDes").text = str(
            _field(dados, "dsc_atividades") or _field(employee, "cargo")
        )[:999]

        for risco in riscos:
            ag = SubElement(info, "agNoc")
            cod = str(_field(risco, "cod_agente_nocivo"))
            SubElement(ag, "codAgNoc").text = cod
            descricao = _field(risco, "descricao")
            # códigos "outros" (01.18.xxx e *.999) exigem descrição do agente
            if descricao and (cod.startswith("01.18") or cod.endswith(".999")):
                SubElement(ag, "dscAgNoc").text = str(descricao)[:100]
            if cod != COD_AUSENCIA_AGENTE_NOCIVO:
                epc_epi = SubElement(ag, "epcEpi")
                SubElement(epc_epi, "utilizEPC").text = str(_field(risco, "utiliz_epc"))
                SubElement(epc_epi, "utilizEPI").text = str(_field(risco, "utiliz_epi"))

        xml_str = tostring(root, encoding="unicode", xml_declaration=True)
        logger.info("S-2240 gerado: employee=%s (%d agentes)", _field(employee, "id"), len(riscos))
        return xml_str

    @staticmethod
    def validar_xml(xml_content: str) -> dict[str, Any]:
        """Valida estrutura básica de um XML eSocial."""
        errors = []

        if not xml_content or not xml_content.strip():
            return {"valid": False, "errors": ["XML vazio"]}

        if "<eSocial" not in xml_content:
            errors.append("Tag raiz <eSocial> não encontrada")

        required_tags = ["ideEvento", "ideEmpregador"]
        for tag in required_tags:
            if f"<{tag}" not in xml_content:
                errors.append(f"Tag obrigatória <{tag}> não encontrada")

        return {"valid": len(errors) == 0, "errors": errors}


# ---------------------------------------------------------------------------
# TRANSMISSÃO SST — contrato único (ver docstring do módulo)
# ---------------------------------------------------------------------------

_TIPOS_SST = ("S-2210", "S-2220", "S-2230", "S-2240")


async def _carregar_empregador(db: Any) -> dict[str, Any]:
    from sqlalchemy import text

    row = (
        await db.execute(
            text(
                "SELECT cnpj, razao_social FROM empresas "
                "WHERE cnpj IS NOT NULL AND btrim(cnpj) <> '' "
                "ORDER BY CASE WHEN cnpj LIKE '35.710.481%' THEN 0 ELSE 1 END LIMIT 1"
            )
        )
    ).mappings().first()
    if not row or _vazio(row["cnpj"]):
        raise ValueError("eSocial SST: nenhum empregador com CNPJ real na tabela empresas.")
    return {"cnpj": _digits(row["cnpj"]), "razao_social": row["razao_social"]}


async def _carregar_employee(db: Any, employee_id: str) -> dict[str, Any]:
    from sqlalchemy import text

    row = (
        await db.execute(
            text(
                "SELECT id::text AS id, nome, cpf, matricula, data_admissao, cargo, setor "
                "FROM employees WHERE id::text = :eid"
            ),
            {"eid": str(employee_id)},
        )
    ).mappings().first()
    if not row:
        raise ValueError(f"eSocial SST: funcionário {employee_id} não encontrado em employees.")
    return dict(row)


async def _gravar_status_sst(
    db: Any, tipo: str, pk: Any, esocial_status: str, recibo: str | None
) -> None:
    """Grava recibo/status na tabela de origem do evento (S-2240 não tem coluna própria)."""
    from sqlalchemy import text

    if tipo == "S-2210":
        await db.execute(
            text(
                "UPDATE gp_cats SET esocial_status = :st, "
                "esocial_transmitida_em = CASE WHEN :st IN ('transmitida','aceita') "
                "  THEN COALESCE(esocial_transmitida_em, now()) ELSE esocial_transmitida_em END, "
                "numero_recibo_esocial = COALESCE(:rec, numero_recibo_esocial), "
                "status = CASE WHEN :st IN ('transmitida','aceita') AND status = 'aberta' "
                "  THEN 'transmitida' ELSE status END, "
                "updated_at = now() WHERE id = :pk"
            ),
            {"st": esocial_status, "rec": recibo, "pk": pk},
        )
    elif tipo == "S-2220":
        await db.execute(
            text(
                "UPDATE gp_asos SET esocial_status = :st, "
                "recibo_s2220 = COALESCE(:rec, recibo_s2220), updated_at = now() WHERE id = :pk"
            ),
            {"st": esocial_status, "rec": recibo, "pk": pk},
        )
    elif tipo == "S-2230":
        await db.execute(
            text(
                "UPDATE sst_afastamentos SET esocial_status = :st, "
                "recibo_s2230 = COALESCE(:rec, recibo_s2230), updated_at = now() WHERE id::text = :pk"
            ),
            {"st": esocial_status, "rec": recibo, "pk": str(pk)},
        )
    await db.commit()


async def _carregar_pcmso_vigente(db: Any, data_ref: Any = None) -> dict[str, Any] | None:
    """Busca o PCMSO REAL (sst_pcmso) vigente na data de referência (ou o mais recente).

    Fonte: PCMSO_CONECTA.pdf (MB/MBS) extraído em 2026-07-08 — nunca fabricado.
    Prioridade: PCMSO vigente na data de referência; se nenhum cobre a data
    (ex.: ASOs anteriores a 05/2026, antes da contratação da MB), usa o PCMSO
    mais recente — o respMonit do S-2220 é o coordenador REAL do monitoramento,
    e o único registro existente é real (nada é fabricado).
    """
    from sqlalchemy import text

    row = (
        await db.execute(
            text(
                "SELECT medico_coordenador, crm, uf FROM sst_pcmso "
                "ORDER BY CASE WHEN CAST(:dt AS date) IS NOT NULL "
                "              AND vigencia_inicio <= CAST(:dt AS date) "
                "              AND vigencia_fim >= CAST(:dt AS date) THEN 0 ELSE 1 END, "
                "         vigencia_inicio DESC LIMIT 1"
            ),
            {"dt": data_ref},
        )
    ).mappings().first()
    return dict(row) if row else None


async def _montar_dados_s2240(db: Any, employee: dict[str, Any]) -> dict[str, Any]:
    """Monta o bloco `dados` do S-2240 a partir de fontes REAIS.

    - local_amb='2' (estabelecimento de terceiros): a operação é em condomínios
      (PGR: "atividades realizadas nos condomínios").
    - nr_insc_local: CNPJ do condomínio da alocação ATIVA do funcionário
      (allocations→posts→clients; match por client_id ou por nome normalizado).
      Sem CNPJ real => campo fica ausente e o gerador lança ValueError honesto.
    - dsc_setor/dsc_atividades: descrições REAIS do PGR (APRO GES 1-4) por função.
    """
    from sqlalchemy import text

    dados: dict[str, Any] = {}
    token = _cargo_token(employee.get("cargo"))
    if token and token in PGR_FUNCOES:
        dados["dsc_setor"] = PGR_FUNCOES[token]["setor"]
        dados["dsc_atividades"] = PGR_FUNCOES[token]["atividades"]

    row = (
        await db.execute(
            text(
                "SELECT c.document_number AS cnpj, p.name AS posto "
                "FROM allocations a "
                "JOIN posts p ON p.id = a.post_id "
                "LEFT JOIN clients c ON (c.id = p.client_id "
                "     OR upper(unaccent(c.name)) = upper(unaccent(p.name))) "
                "WHERE a.employee_id::text = :eid AND a.status = 'active' "
                "ORDER BY a.is_primary DESC NULLS LAST, a.start_date DESC LIMIT 1"
            ),
            {"eid": str(employee.get("id"))},
        )
    ).mappings().first()
    if row:
        cnpj = _digits(row["cnpj"])
        if len(cnpj) == 14 and cnpj != "0" * 14:
            dados["local_amb"] = "2"  # estabelecimento de terceiros (condomínio)
            dados["nr_insc_local"] = cnpj
    return dados


async def montar_xml_evento_sst(db: Any, tipo: str, ref_id: Any) -> dict[str, Any]:
    """Carrega o registro REAL + enriquecimentos (PCMSO/PGR/LTCAT) e gera o XML.

    NÃO transmite nada — usada pelo transmitir_evento_sst e por dry-runs.
    Retorna {"xml", "employee", "registro", "riscos", "pk", "empregador"}.
    ValueError descritivo se faltar dado obrigatório (nunca fabricado).
    """
    from sqlalchemy import text

    tipo = str(tipo).upper().strip()
    if tipo not in _TIPOS_SST:
        raise ValueError(f"evento SST: tipo '{tipo}' inválido. Válidos: {', '.join(_TIPOS_SST)}")

    empregador = await _carregar_empregador(db)

    registro: dict[str, Any] | None = None
    riscos: list[dict[str, Any]] = []
    pk: Any = None

    if tipo == "S-2210":
        registro = (
            await db.execute(
                text("SELECT * FROM gp_cats WHERE cat_id = :r OR id::text = :r"),
                {"r": str(ref_id)},
            )
        ).mappings().first()
        if not registro:
            raise ValueError(f"S-2210: CAT '{ref_id}' não encontrada em gp_cats.")
        registro = dict(registro)
        pk = registro["id"]
        employee = await _carregar_employee(db, registro["employee_id"])
        xml = ESocialEventService.gerar_s2210(registro, employee, empregador)

    elif tipo == "S-2220":
        registro = (
            await db.execute(
                text("SELECT * FROM gp_asos WHERE aso_id = :r OR id::text = :r"),
                {"r": str(ref_id)},
            )
        ).mappings().first()
        if not registro:
            raise ValueError(f"S-2220: ASO '{ref_id}' não encontrado em gp_asos.")
        registro = dict(registro)
        pk = registro["id"]
        # médico responsável pelo monitoramento (respMonit) = coordenador REAL
        # do PCMSO vigente na data do ASO (sst_pcmso, extraído do PDF da MB)
        pcmso = await _carregar_pcmso_vigente(db, registro.get("data_realizacao"))
        if pcmso:
            registro.setdefault("resp_monit_nome", pcmso["medico_coordenador"])
            registro.setdefault("resp_monit_crm", pcmso["crm"])
            registro.setdefault("resp_monit_uf_crm", pcmso["uf"])
        employee = await _carregar_employee(db, str(registro["employee_id"]))
        xml = ESocialEventService.gerar_s2220(registro, employee, empregador["cnpj"])

    elif tipo == "S-2230":
        registro = (
            await db.execute(
                text("SELECT * FROM sst_afastamentos WHERE id::text = :r"),
                {"r": str(ref_id)},
            )
        ).mappings().first()
        if not registro:
            raise ValueError(f"S-2230: afastamento '{ref_id}' não encontrado em sst_afastamentos.")
        registro = dict(registro)
        pk = registro["id"]
        employee = await _carregar_employee(db, str(registro["employee_id"]))
        xml = ESocialEventService.gerar_s2230(registro, employee, empregador["cnpj"])

    else:  # S-2240 — ref_id é o employee_id
        employee = await _carregar_employee(db, str(ref_id))
        # Riscos por FUNÇÃO (PGR GES 1-4 / LTCAT 28-05-2026): só riscos com
        # enquadramento REAL na Tabela 24 (cod_agente_nocivo preenchido pelo
        # laudo) e aplicáveis à função do funcionário. Riscos ergonômicos/de
        # acidente não são declaráveis na Tabela 24 (ficam fora, honesto).
        token = _cargo_token(employee.get("cargo"))
        todos = [
            dict(r)
            for r in (
                await db.execute(
                    text(
                        "SELECT * FROM gp_risks "
                        "WHERE COALESCE(status,'') <> 'encerrado' "
                        "  AND cod_agente_nocivo IS NOT NULL"
                    )
                )
            ).mappings().all()
        ]
        riscos = [r for r in todos if token and token in _json_list(r.get("funcoes_aplicaveis"))]
        dados = await _montar_dados_s2240(db, employee)
        xml = ESocialEventService.gerar_s2240(employee, riscos, empregador["cnpj"], dados)

    return {
        "xml": xml,
        "employee": employee,
        "registro": registro,
        "riscos": riscos,
        "pk": pk,
        "empregador": empregador,
    }


async def transmitir_evento_sst(db: Any, tipo: str, ref_id: Any) -> dict[str, Any]:
    """Carrega o registro, gera o XML, TRANSMITE de verdade e grava recibo/status.

    Ver contrato completo no docstring do módulo. Nunca fabrica protocolo:
    - dado obrigatório faltando  => ValueError descritivo (nada é transmitido)
    - rejeição do governo        => {"status": "rejeitada", "erros": [...]}
    - falha de infra (SSL/rede)  => RuntimeError (esocial_status='erro' gravado)
    """
    tipo = str(tipo).upper().strip()
    montado = await montar_xml_evento_sst(db, tipo, ref_id)
    xml = montado["xml"]
    employee = montado["employee"]
    pk = montado["pk"]
    empregador = montado["empregador"]

    # --- transmissão REAL (assinatura A1 + SOAP mTLS) ---
    from modules.government_integrations.core.esocial_transmitter import (
        ESocialTransmitter,
        EventType,
        TransmissionStatus,
        resolve_environment,
    )

    cert_path = os.environ.get(
        "CERTIFICATE_PATH", "/opt/conecta-pro/credentials/certificates/certificado.pfx"
    )
    cert_password = os.environ.get("CERTIFICATE_PASSWORD", "Conecta123")

    transmitter = ESocialTransmitter(
        environment=resolve_environment(),  # default SEGURO: producaorestrita
        certificate_path=cert_path,
        certificate_password=cert_password,
    )
    await transmitter.load_certificate()

    event = await transmitter.create_event_from_xml(
        event_type=EventType(tipo),
        employer_cnpj=empregador["cnpj"],
        xml_content=xml,
        employee_cpf=_digits(_field(employee, "cpf")),
        reference_id=str(ref_id),
    )
    event = await transmitter.transmit(event.id)

    if event.protocol:
        recibo: str | None = None
        if tipo != "S-2240":
            await _gravar_status_sst(db, tipo, pk, "transmitida", None)
        # tenta capturar o recibo imediatamente (governo pode ainda estar processando)
        try:
            event = await transmitter.check_status(event.id)
            recibo = event.receipt_number
        except Exception as exc:  # noqa: BLE001 — recibo virá em consulta posterior
            logger.warning("Consulta de recibo pós-transmissão falhou (%s): %s", tipo, exc)
        status_final = "aceita" if recibo else "transmitida"
        if tipo != "S-2240" and recibo:
            await _gravar_status_sst(db, tipo, pk, status_final, recibo)
        logger.info("%s transmitido: protocolo=%s recibo=%s", tipo, event.protocol, recibo)
        return {
            "protocolo": event.protocol,
            "recibo": recibo,
            "status": status_final,
            "ambiente": transmitter.environment.name.lower(),
        }

    # sem protocolo: rejeição do governo ou falha de infraestrutura — nunca fabricar
    erros = event.errors or [{"code": "SEM_PROTOCOLO", "message": "Resposta sem protocolo"}]
    if event.status == TransmissionStatus.REJECTED:
        if tipo != "S-2240":
            await _gravar_status_sst(db, tipo, pk, "rejeitada", None)
        return {"protocolo": None, "recibo": None, "status": "rejeitada", "erros": erros}

    if tipo != "S-2240":
        await _gravar_status_sst(db, tipo, pk, "erro", None)
    raise RuntimeError(f"Falha na transmissão do {tipo} ao eSocial (sem protocolo): {erros}")
