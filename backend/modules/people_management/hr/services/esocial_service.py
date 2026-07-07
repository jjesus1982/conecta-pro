"""Service eSocial — Geração de eventos XML S-2200 e S-2299.

Gera XMLs compatíveis com o layout eSocial S-1.2 para transmissão ao governo.
"""

import logging
import os
from datetime import date
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

logger = logging.getLogger(__name__)

ESOCIAL_NAMESPACE = "http://www.esocial.gov.br/schema/evt/evtAdmissao/v_S_01_02_00"


def _tp_amb() -> str:
    """Resolve o tpAmb do eSocial a partir da configuração/ambiente.

    Regra: 1=produção, 2=homologação (dados reais em ambiente de testes).
    Fonte de verdade: variável de ambiente ESOCIAL_TP_AMB quando definida;
    caso contrário deriva de settings.environment ('production' => '1').
    NUNCA hardcoded — evitar transmitir produção como homologação e vice-versa.
    """
    explicit = os.getenv("ESOCIAL_TP_AMB")
    if explicit and explicit.strip() in ("1", "2"):
        return explicit.strip()
    try:
        from core.config import settings

        env = (getattr(settings, "environment", "") or "").lower()
    except Exception:  # pragma: no cover - fallback defensivo
        env = os.getenv("ENVIRONMENT", "").lower()
    return "1" if env in ("production", "prod") else "2"


class ESocialEventService:
    """Serviço de geração de eventos eSocial (S-2200, S-2299)."""

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
        SubElement(ide, "tpAmb").text = _tp_amb()  # 1=produção, 2=homologação (config)
        SubElement(ide, "procEmi").text = "1"
        SubElement(ide, "verProc").text = "ConectaPRO_2.0"

        # ideEmpregador
        emp = SubElement(evt, "ideEmpregador")
        SubElement(emp, "tpInsc").text = "1"
        SubElement(emp, "nrInsc").text = empregador_cnpj

        # trabalhador
        trab = SubElement(evt, "trabalhador")
        SubElement(trab, "cpfTrab").text = trabalhador.get("cpf", "")
        SubElement(trab, "nmTrab").text = trabalhador.get("nome", "")
        SubElement(trab, "sexo").text = trabalhador.get("sexo", "M")
        if trabalhador.get("data_nascimento"):
            SubElement(trab, "dtNascto").text = trabalhador["data_nascimento"]

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
        SubElement(ide, "tpAmb").text = _tp_amb()  # 1=produção, 2=homologação (config)
        SubElement(ide, "procEmi").text = "1"
        SubElement(ide, "verProc").text = "ConectaPRO_2.0"

        # ideEmpregador
        emp = SubElement(evt, "ideEmpregador")
        SubElement(emp, "tpInsc").text = "1"
        SubElement(emp, "nrInsc").text = empregador_cnpj

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
