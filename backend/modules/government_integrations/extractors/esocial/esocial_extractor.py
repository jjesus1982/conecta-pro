"""
Extrator de Eventos do eSocial.

Implementa:
- Consulta de eventos enviados
- Download de recibos
- Atualização de status
"""

import asyncio
import logging
from datetime import datetime, timedelta
from uuid import UUID
from xml.etree.ElementTree import Element  # noqa: S405

from defusedxml import ElementTree as ET  # noqa: N817

from ...core.credentials import TipoCredencial
from ..base_extractor import DocumentoExtraido, ExtratorBase, ResultadoExtracao

logger = logging.getLogger(__name__)


# Namespaces XML eSocial
NS_ESOCIAL = "http://www.esocial.gov.br/schema/lote/eventos/envio/v1_1_1"
NS_ESOCIAL_RET = "http://www.esocial.gov.br/schema/lote/eventos/envio/retornoProcessamento/v1_3_0"
NS_SOAP = "http://www.w3.org/2003/05/soap-envelope"

# Tipos de eventos eSocial
EVENTOS_TABELAS = [
    "S-1000",
    "S-1005",
    "S-1010",
    "S-1020",
    "S-1030",
    "S-1035",
    "S-1040",
    "S-1050",
    "S-1060",
    "S-1070",
    "S-1080",
]
EVENTOS_NAO_PERIODICOS = [
    "S-2190",
    "S-2200",
    "S-2205",
    "S-2206",
    "S-2210",
    "S-2220",
    "S-2230",
    "S-2240",
    "S-2250",
    "S-2260",
    "S-2298",
    "S-2299",
    "S-2300",
    "S-2306",
    "S-2399",
    "S-2400",
    "S-3000",
    "S-5001",
    "S-5002",
    "S-5003",
    "S-5011",
    "S-5012",
    "S-5013",
    "S-8299",
]
EVENTOS_PERIODICOS = [
    "S-1200",
    "S-1202",
    "S-1207",
    "S-1210",
    "S-1260",
    "S-1270",
    "S-1280",
    "S-1298",
    "S-1299",
    "S-1300",
]


class ExtratoreSocial(ExtratorBase):
    """
    Extrator de eventos do eSocial.

    Serviços utilizados:
    - ConsultarLoteEventos: Consultar lote de eventos
    - DownloadEventos: Baixar eventos processados
    """

    # URLs dos webservices
    URLS = {
        # PRODUÇÃO REAL: hosts oficiais distintos por serviço (envio/consulta/download).
        "producao": {
            "envio": "https://webservices.envio.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc",
            "consulta": "https://webservices.consulta.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc",
            "download": "https://webservices.download.esocial.gov.br/servicos/empregador/downloadEventos/WsDownloadEventos.svc",
        },
        "homologacao": {
            "envio": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/enviarloteeventos/WsEnviarLoteEventos.svc",
            "consulta": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/consultarloteeventos/WsConsultarLoteEventos.svc",
            "download": "https://webservices.producaorestrita.esocial.gov.br/servicos/empregador/downloadEventos/WsDownloadEventos.svc",
        },
    }

    @property
    def tipo_servico(self) -> str:
        return "esocial"

    @property
    def tipo_credencial(self) -> TipoCredencial:
        return TipoCredencial.ESOCIAL

    async def extrair(
        self,
        tenant_id: UUID,
        data_inicio: datetime | None = None,
        data_fim: datetime | None = None,
        cnpjs: list[str] | None = None,
        ufs: list[str] | None = None,
        incremental: bool = True,
    ) -> ResultadoExtracao:
        """
        Extrai eventos do eSocial.

        Args:
            tenant_id: ID do tenant
            data_inicio: Data inicial (para filtrar eventos)
            data_fim: Data final
            cnpjs: CNPJs a consultar
            ufs: Não usado para eSocial
            incremental: Se True, busca apenas novos eventos

        Returns:
            ResultadoExtracao
        """
        resultado = ResultadoExtracao(
            servico=self.tipo_servico,
            inicio=datetime.utcnow(),
        )

        # Defaults
        if data_fim is None:
            data_fim = datetime.utcnow()
        if data_inicio is None:
            data_inicio = data_fim - timedelta(days=30)

        logger.info(f"Iniciando extração eSocial: {tenant_id} - Período: {data_inicio.date()} a {data_fim.date()}")

        try:
            # Obter credenciais
            credencial = await self.credentials.obter_credencial(tenant_id, self.tipo_credencial)

            if not credencial.valida:
                resultado.status = "falha"
                resultado.erros.append(f"Credencial inválida: {credencial.erro}")
                return resultado

            # Extrair para cada CNPJ
            cnpjs = cnpjs or [credencial.certificado_info.cnpj_cpf]

            for cnpj in cnpjs:
                logger.info(f"Extraindo eSocial para CNPJ: {cnpj}")

                # Consultar eventos por período
                docs = await self._consultar_eventos(tenant_id, cnpj, data_inicio, data_fim)

                for doc in docs:
                    resultado.documentos.append(doc)

                    if doc.erro:
                        resultado.documentos_erro += 1
                        resultado.erros.append(doc.erro)
                    else:
                        resultado.documentos_novos += 1

                    resultado.documentos_processados += 1

            resultado.status = "concluida" if not resultado.erros else "concluida_parcial"

        except Exception as e:
            logger.error(f"Erro na extração eSocial: {e}")
            resultado.status = "falha"
            resultado.erros.append(str(e))

        finally:
            resultado.fim = datetime.utcnow()
            await self.close()

        return resultado

    async def _consultar_eventos(
        self,
        tenant_id: UUID,
        cnpj: str,
        data_inicio: datetime,
        data_fim: datetime,
    ) -> list[DocumentoExtraido]:
        """Consulta eventos do eSocial para um CNPJ."""
        documentos = []

        try:
            # Consultar por tipo de evento
            for tipo_evento in EVENTOS_PERIODICOS + EVENTOS_NAO_PERIODICOS:
                docs = await self._consultar_tipo_evento(tenant_id, cnpj, tipo_evento, data_inicio, data_fim)
                documentos.extend(docs)

                # Rate limiting
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Erro ao consultar eventos: {e}")

        return documentos

    async def _consultar_tipo_evento(
        self,
        tenant_id: UUID,
        cnpj: str,
        tipo_evento: str,
        data_inicio: datetime,
        data_fim: datetime,
    ) -> list[DocumentoExtraido]:
        """Consulta eventos de um tipo específico."""
        documentos = []

        try:
            # Montar envelope de consulta
            envelope = self._montar_envelope_consulta(cnpj, tipo_evento, data_inicio, data_fim)

            # Fazer requisição
            url = self.URLS["producao"]["consulta"]
            resposta = await self._fazer_requisicao(tenant_id, url, data=envelope)

            if resposta:
                docs = self._processar_resposta_consulta(resposta, tipo_evento)
                documentos.extend(docs)

        except Exception as e:
            logger.error(f"Erro ao consultar {tipo_evento}: {e}")

        return documentos

    def _montar_envelope_consulta(
        self,
        cnpj: str,
        tipo_evento: str,
        data_inicio: datetime,
        data_fim: datetime,
    ) -> str:
        """Monta envelope SOAP para consulta de eventos."""
        # Formato de período: AAAA-MM
        per_apur_ini = data_inicio.strftime("%Y-%m")
        per_apur_fim = data_fim.strftime("%Y-%m")

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
    <soap:Header/>
    <soap:Body>
        <ConsultarLoteEventos xmlns="http://www.esocial.gov.br/servicos/empregador/lote/eventos/envio/consulta/v1_1_0">
            <consulta>
                <eSocial xmlns="http://www.esocial.gov.br/schema/consulta/v1_0_0">
                    <consultaLoteEventos>
                        <tpInsc>1</tpInsc>
                        <nrInsc>{cnpj[:8]}</nrInsc>
                        <perApuracao>
                            <ini>{per_apur_ini}</ini>
                            <fim>{per_apur_fim}</fim>
                        </perApuracao>
                        <tpEvento>{tipo_evento}</tpEvento>
                    </consultaLoteEventos>
                </eSocial>
            </consulta>
        </ConsultarLoteEventos>
    </soap:Body>
</soap:Envelope>"""

    def _processar_resposta_consulta(self, xml_resposta: str, tipo_evento: str) -> list[DocumentoExtraido]:
        """Processa resposta da consulta de eventos."""
        documentos = []

        try:
            root = ET.fromstring(xml_resposta.encode())

            # Buscar retorno de eventos
            eventos = root.findall(
                ".//{http://www.esocial.gov.br/schema/lote/eventos/envio/retornoProcessamento/v1_3_0}evento"
            )

            for evento in eventos:
                doc = self._extrair_evento(evento, tipo_evento)
                if doc:
                    documentos.append(doc)

        except ET.ParseError as e:
            logger.error(f"Erro ao parsear resposta eSocial: {e}")

        return documentos

    def _extrair_evento(self, elemento: Element, tipo_evento: str) -> DocumentoExtraido | None:
        """Extrai dados de um evento eSocial."""
        try:
            # Buscar ID do evento
            id_evento = elemento.get("Id", "")

            # Buscar recibo
            recibo = elemento.findtext(".//{*}nrRecibo") or ""

            # Status de processamento
            cd_resposta = elemento.findtext(".//{*}cdResposta") or ""
            desc_resposta = elemento.findtext(".//{*}descResposta") or ""

            dados = {
                "id_evento": id_evento,
                "tipo_evento": tipo_evento,
                "numero_recibo": recibo,
                "codigo_resposta": cd_resposta,
                "descricao_resposta": desc_resposta,
                "status": self._mapear_status(cd_resposta),
            }

            # Tentar extrair dados específicos do evento
            self._extrair_dados_especificos(elemento, tipo_evento, dados)

            return DocumentoExtraido(
                id=id_evento or recibo,
                tipo=f"esocial_{tipo_evento.lower().replace('-', '_')}",
                dados=dados,
                xml_original=ET.tostring(elemento, encoding="unicode"),
            )

        except Exception as e:
            logger.error(f"Erro ao extrair evento: {e}")
            return None

    def _extrair_dados_especificos(self, elemento: Element, tipo_evento: str, dados: dict):
        """Extrai dados específicos por tipo de evento."""
        if tipo_evento == "S-1200":
            # Remuneração
            dados["competencia"] = elemento.findtext(".//{*}perApur") or ""
            dados["cpf_trabalhador"] = elemento.findtext(".//{*}cpfTrab") or ""
            dados["valor_bruto"] = elemento.findtext(".//{*}vrBruto") or "0"

        elif tipo_evento == "S-2200":
            # Cadastramento inicial / Admissão
            dados["cpf_trabalhador"] = elemento.findtext(".//{*}cpfTrab") or ""
            dados["nome_trabalhador"] = elemento.findtext(".//{*}nmTrab") or ""
            dados["data_admissao"] = elemento.findtext(".//{*}dtAdm") or ""
            dados["matricula"] = elemento.findtext(".//{*}matricula") or ""

        elif tipo_evento == "S-2299":
            # Desligamento
            dados["cpf_trabalhador"] = elemento.findtext(".//{*}cpfTrab") or ""
            dados["data_desligamento"] = elemento.findtext(".//{*}dtDeslig") or ""
            dados["motivo_desligamento"] = elemento.findtext(".//{*}mtvDeslig") or ""

        elif tipo_evento in ["S-1298", "S-1299"]:
            # Reabertura / Fechamento
            dados["competencia"] = elemento.findtext(".//{*}perApur") or ""

    def _mapear_status(self, codigo: str) -> str:
        """Mapeia código de resposta para status."""
        mapeamento = {
            "201": "processado",
            "202": "processado_com_advertencia",
            "301": "rejeitado",
            "401": "erro_validacao",
            "402": "erro_schema",
        }
        return mapeamento.get(codigo, "desconhecido")

    async def consultar_recibo(self, tenant_id: UUID, cnpj: str, numero_recibo: str) -> DocumentoExtraido | None:
        """
        Consulta um recibo específico.

        Args:
            tenant_id: ID do tenant
            cnpj: CNPJ do empregador
            numero_recibo: Número do recibo

        Returns:
            Documento com dados do recibo
        """
        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
    <soap:Body>
        <DownloadEventos xmlns="http://www.esocial.gov.br/servicos/empregador/download/v1_0_0">
            <download>
                <eSocial xmlns="http://www.esocial.gov.br/schema/download/v1_0_0">
                    <downloadEventos>
                        <tpInsc>1</tpInsc>
                        <nrInsc>{cnpj[:8]}</nrInsc>
                        <nrRec>{numero_recibo}</nrRec>
                    </downloadEventos>
                </eSocial>
            </download>
        </DownloadEventos>
    </soap:Body>
</soap:Envelope>"""

        url = self.URLS["producao"]["download"]
        resposta = await self._fazer_requisicao(tenant_id, url, data=envelope)

        if resposta:
            return self._processar_download(resposta, numero_recibo)

        return None

    def _processar_download(self, xml_resposta: str, numero_recibo: str) -> DocumentoExtraido | None:
        """Processa resposta do download de evento."""
        try:
            root = ET.fromstring(xml_resposta.encode())

            # Buscar evento
            evento = root.find(".//{*}evento")

            if evento is not None:
                return DocumentoExtraido(
                    id=numero_recibo,
                    tipo="esocial_download",
                    dados={
                        "numero_recibo": numero_recibo,
                        "status": "baixado",
                    },
                    xml_original=ET.tostring(evento, encoding="unicode"),
                    processado=True,
                )

        except Exception as e:
            logger.error(f"Erro ao processar download: {e}")

        return None

    async def listar_eventos_pendentes(
        self,
        tenant_id: UUID,
        cnpj: str,
    ) -> list[dict]:
        """Lista eventos pendentes de processamento."""
        # Esta é uma consulta simplificada
        # Em produção, manter cache de eventos enviados
        pendentes = []

        # Consultar eventos recentes
        data_fim = datetime.utcnow()
        data_inicio = data_fim - timedelta(days=7)

        resultado = await self.extrair(
            tenant_id=tenant_id,
            data_inicio=data_inicio,
            data_fim=data_fim,
            cnpjs=[cnpj],
            incremental=True,
        )

        for doc in resultado.documentos:
            if doc.dados.get("status") == "desconhecido":
                pendentes.append(doc.dados)

        return pendentes
