"""
Service para integrações com eSocial.

TRANSMISSÃO REAL: enviar_evento() assina com certificado A1 e transmite via
SOAP+mTLS ao webservice do governo (ESocialTransmitter). NUNCA fabrica
protocolo: sem resposta real do eSocial => exceção honesta.

Ambiente: decidido por env ESOCIAL_AMBIENTE (default SEGURO: producaorestrita,
o ambiente de testes do governo com dados reais). A virada para produção real
é explícita: ESOCIAL_AMBIENTE=producao.
"""

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class ESocialService:
    """Service para operações com eSocial."""

    # Eventos suportados
    EVENTOS_SUPORTADOS: list[dict[str, str]] = [
        {
            "codigo": "S-2200",
            "nome": "Cadastramento Inicial do Vinculo e Admissao",
            "descricao": "Evento de admissao de funcionario",
        },
        {
            "codigo": "S-2205",
            "nome": "Alteracao de Dados Cadastrais",
            "descricao": "Alteracao de dados do funcionario",
        },
        {
            "codigo": "S-2206",
            "nome": "Alteracao de Contrato de Trabalho",
            "descricao": "Alteracao de condicoes contratuais",
        },
        {
            "codigo": "S-2210",
            "nome": "Comunicacao de Acidente de Trabalho",
            "descricao": "CAT - Comunicacao de Acidente",
        },
        {
            "codigo": "S-2220",
            "nome": "Monitoramento da Saude do Trabalhador",
            "descricao": "ASO - Atestado de Saude Ocupacional",
        },
        {
            "codigo": "S-2230",
            "nome": "Afastamento Temporario",
            "descricao": "Afastamentos (ferias, licencas, etc)",
        },
        {
            "codigo": "S-2240",
            "nome": "Condicoes Ambientais do Trabalho",
            "descricao": "Fatores de risco e EPIs",
        },
        {
            "codigo": "S-2299",
            "nome": "Desligamento",
            "descricao": "Evento de demissao/desligamento",
        },
    ]

    @staticmethod
    async def enviar_evento(
        tipo_evento: str,
        funcionario_id: str,
        dados: dict[str, Any],
        ambiente: str | None = None,
    ) -> dict[str, Any]:
        """
        Envia evento para o eSocial — TRANSMISSÃO REAL (assinatura A1 + SOAP mTLS).

        Args:
            tipo_evento: Tipo do evento eSocial (ex.: "S-2210").
            funcionario_id: ID do funcionário (referência interna).
            dados: Dados do evento. Deve conter "employer_cnpj" (ou "cnpj").
                Se contiver "xml" (ou "xml_content"), o XML pré-construído
                (com atributo Id) é assinado e transmitido como está — caminho
                usado pelos geradores SST de people_management. Caso contrário,
                o XMLBuilder interno do transmitter constrói o XML (tipos
                suportados: S-1000, S-2200, S-2299, S-2220).
            ambiente: "producao" | "producaorestrita"/"homologacao". Se None,
                resolve por env ESOCIAL_AMBIENTE (default producaorestrita).

        Returns:
            Dict com protocolo REAL retornado pelo governo.

        Raises:
            ValueError: Se dados obrigatórios ausentes.
            RuntimeError: Se o governo rejeitar ou a transmissão falhar —
                NUNCA retorna protocolo fabricado.
        """
        from modules.government_integrations.core.esocial_transmitter import (
            ESocialTransmitter,
            EventType,
            TransmissionStatus,
            resolve_environment,
        )

        try:
            event_type = EventType(tipo_evento)
        except ValueError:
            raise ValueError(f"Tipo de evento eSocial inválido/não suportado: {tipo_evento}")

        employer_cnpj = dados.get("employer_cnpj") or dados.get("cnpj")
        if not employer_cnpj:
            raise ValueError(
                "enviar_evento: 'employer_cnpj' (ou 'cnpj') obrigatório em dados — "
                "sem CNPJ do empregador não há transmissão."
            )

        env = resolve_environment(ambiente)
        cert_path = os.environ.get(
            "CERTIFICATE_PATH", "/opt/conecta-pro/credentials/certificates/certificado.pfx"
        )
        cert_password = os.environ.get("CERTIFICATE_PASSWORD", "")

        transmitter = ESocialTransmitter(
            environment=env,
            certificate_path=cert_path,
            certificate_password=cert_password,
        )
        await transmitter.load_certificate()

        xml_prebuilt = dados.get("xml") or dados.get("xml_content")
        if xml_prebuilt:
            event = await transmitter.create_event_from_xml(
                event_type=event_type,
                employer_cnpj=str(employer_cnpj),
                xml_content=xml_prebuilt,
                employee_cpf=dados.get("cpf"),
                reference_id=str(funcionario_id),
            )
        else:
            event = await transmitter.create_event(
                event_type=event_type,
                employer_cnpj=str(employer_cnpj),
                data=dados,
                employee_cpf=dados.get("cpf"),
                reference_id=str(funcionario_id),
            )

        event = await transmitter.transmit(event.id)

        if not event.protocol:
            erros = event.errors or [{"code": "SEM_PROTOCOLO", "message": "Resposta sem protocolo"}]
            if event.status == TransmissionStatus.REJECTED:
                raise RuntimeError(f"eSocial rejeitou o evento {tipo_evento}: {erros}")
            raise RuntimeError(f"Falha na transmissão do {tipo_evento} ao eSocial: {erros}")

        logger.info(
            "Evento eSocial transmitido de VERDADE: tipo=%s, funcionario=%s, protocolo=%s, ambiente=%s",
            tipo_evento,
            funcionario_id,
            event.protocol,
            env.name,
        )

        return {
            "protocolo": event.protocol,
            "tipo_evento": tipo_evento,
            "funcionario_id": funcionario_id,
            "ambiente": env.name.lower(),
            "status": event.status.value,
            "data_transmissao": event.transmitted_at.isoformat() if event.transmitted_at else None,
        }

    @staticmethod
    def consultar_status(protocolo: str) -> dict[str, Any]:
        """
        Consulta status de evento eSocial pelo protocolo (cache local).

        Honesto: sem consulta SOAP ao lote (exige o contexto do evento em
        memória do transmitter), retorna status 'desconhecido' — nunca um
        status fabricado como 'processado'.
        """
        return {
            "protocolo": protocolo,
            "status": "desconhecido",
            "recibo": None,
            "erros": [],
            "data_processamento": None,
            "detalhe": (
                "Consulta de lote por protocolo avulso ainda não implementada — "
                "o recibo é capturado na própria transmissão (transmitir_evento_sst)."
            ),
        }

    @classmethod
    def listar_eventos_suportados(cls) -> dict[str, Any]:
        """
        Lista eventos eSocial suportados.

        Returns:
            Dict com lista de eventos.
        """
        return {
            "eventos": cls.EVENTOS_SUPORTADOS,
            "ambiente_producao": "Requer certificado digital A1/A3",
            "ambiente_homologacao": "Disponivel para testes",
        }
