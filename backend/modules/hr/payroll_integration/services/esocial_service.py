"""Service para integração com eSocial."""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.payroll_integration.models import ExportFormat, PayrollExport, PayrollIntegration
from modules.hr.payroll_integration.repositories import (
    PayrollEventRepository,
    PayrollExportRepository,
    PayrollIntegrationRepository,
    PayrollPeriodRepository,
)
from modules.hr.payroll_integration.schemas import ESocialExportRequest, ESocialTransmissionResponse

logger = logging.getLogger(__name__)


#: Eventos eSocial e o que o sistema REALMENTE faz com cada um.
#:
#: Este dicionário se chamava «eventos suportados» e é devolvido por
#: `get_supported_events()`, que tem rota. Em 26/09/2026, montando a conta do que falta
#: para sair da Portte, ele declarava SETE eventos periódicos como suportados. A medida:
#:
#:   · S-1200, S-1210 e S-1299 têm gerador, e os três são ESQUELETO — o S-1200 sai sem
#:     `ideTrabalhador` (ou seja, sem o CPF de quem recebeu), com Id fora do formato de
#:     36 caracteres do eSocial e sem `perApur`; o S-1210 e o S-1299 dizem «implementação
#:     simplificada» no próprio código e emitem bloco vazio;
#:   · S-1260, S-1270, S-1280 e S-1298 não têm gerador nenhum — o `_generate_esocial_xml`
#:     não os despacha.
#:
#: Declarar capacidade que não existe é o mesmo defeito do gerador da EFD ICMS/IPI, que
#: declarava nota de SERVIÇO como mercadoria «para não gerar arquivo oco». O campo
#: `gerador` passa a dizer a verdade, e quem consome escolhe o que fazer com ela.
#:
#:   completo       → produz XML que se pode transmitir
#:   outro_servico  → quem produz é `people_management.hr.services.esocial_service`;
#:                    ESTE serviço não o despacha, e dizer «suportado» aqui esconde isso
#:   esqueleto      → produz XML INCOMPLETO; o governo recusa e, pior, PARECE capacidade
#:   nenhum         → não há gerador em lugar nenhum
ESOCIAL_EVENTS = {
    "S-1200": {
        "name": "Remuneração do Trabalhador vinculado ao RGPS",
        "description": "Informações da remuneração de cada trabalhador no mês",
        "periodic": True,
        "gerador": "esqueleto",
        "gerador_nota": "sem ideTrabalhador (sem CPF), Id fora do formato de 36 caracteres e sem perApur",
    },
    "S-1210": {
        "name": "Pagamentos de Rendimentos do Trabalho",
        "description": "Informações dos pagamentos efetuados",
        "periodic": True,
        "gerador": "esqueleto",
        "gerador_nota": "«implementação simplificada» no código: evtPgtos vazio, sem nenhum pagamento",
    },
    "S-1260": {
        "name": "Comercialização da Produção Rural PF",
        "description": "Comercialização de produção rural por pessoa física",
        "periodic": True,
        "gerador": "nenhum",
        "gerador_nota": "não despachado por _generate_esocial_xml",
    },
    "S-1270": {
        "name": "Contratação de Trabalhadores Avulsos",
        "description": "Informações de trabalhadores avulsos",
        "periodic": True,
        "gerador": "nenhum",
        "gerador_nota": "não despachado por _generate_esocial_xml",
    },
    "S-1280": {
        "name": "Informações Complementares aos Eventos Periódicos",
        "description": "Informações complementares",
        "periodic": True,
        "gerador": "nenhum",
        "gerador_nota": "não despachado por _generate_esocial_xml",
    },
    "S-1298": {
        "name": "Reabertura dos Eventos Periódicos",
        "description": "Reabre eventos periódicos já fechados",
        "periodic": False,
        "gerador": "nenhum",
        "gerador_nota": "não despachado por _generate_esocial_xml",
    },
    "S-1299": {
        "name": "Fechamento dos Eventos Periódicos",
        "description": "Informa o fechamento da folha",
        "periodic": True,
        "gerador": "esqueleto",
        "gerador_nota": "«implementação simplificada» no código: evtFechaEvPer sem os totalizadores",
    },
    "S-2200": {
        "name": "Cadastramento Inicial do Vínculo e Admissão",
        "description": "Informações de admissão de trabalhador",
        "periodic": False,
        "gerador": "outro_servico",
        "gerador_nota": "gerado por `people_management.hr.services.esocial_service.ESocialEventService.gerar_s2200`, com rota POST /people-management/hr/esocial/s2200/gerar — este serviço aqui NÃO o despacha",
    },
    "S-2299": {
        "name": "Desligamento",
        "description": "Informações de desligamento de trabalhador",
        "periodic": False,
        "gerador": "outro_servico",
        "gerador_nota": "gerado por `ESocialEventService.gerar_s2299`, com rota POST /people-management/hr/esocial/s2299/gerar — este serviço aqui NÃO o despacha",
    },
    "S-2300": {
        "name": "Trabalhador Sem Vínculo de Emprego",
        "description": "Cadastro de TSVE",
        "periodic": False,
        "gerador": "nenhum",
        "gerador_nota": "não despachado aqui e sem gerador em ESocialEventService",
    },
    "S-2399": {
        "name": "Término de TSVE",
        "description": "Término de trabalhador sem vínculo",
        "periodic": False,
        "gerador": "nenhum",
        "gerador_nota": "não despachado aqui e sem gerador em ESocialEventService",
    },
}


class ESocialService:
    """Service para operações do eSocial."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.period_repo = PayrollPeriodRepository(db)
        self.event_repo = PayrollEventRepository(db)
        self.export_repo = PayrollExportRepository(db)
        self.integration_repo = PayrollIntegrationRepository(db)

    async def get_integration(
        self,
        condominio_id: UUID,
    ) -> PayrollIntegration | None:
        """Obtém integração eSocial configurada."""
        return await self.integration_repo.get_esocial_integration(condominio_id)

    async def validate_integration(
        self,
        condominio_id: UUID,
    ) -> dict[str, Any]:
        """Valida configuração do eSocial."""
        integration = await self.get_integration(condominio_id)

        result = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        if not integration:
            result["valid"] = False
            result["errors"].append("Integração eSocial não configurada")
            return result

        # Validar configuração
        config = integration.esocial_config or {}

        if not config.get("nr_inscricao"):
            result["valid"] = False
            result["errors"].append("CNPJ/CPF não configurado")

        if not config.get("certificado_tipo"):
            result["valid"] = False
            result["errors"].append("Tipo de certificado não configurado")

        if config.get("ambiente") not in ["producao", "producao_restrita"]:
            result["warnings"].append("Ambiente não definido, usando produção restrita")

        # Verificar mapeamento de rubricas
        rubrica_mapping = integration.rubrica_mapping or {}
        if len(rubrica_mapping) < 5:
            result["warnings"].append(
                f"Apenas {len(rubrica_mapping)} rubricas mapeadas. Recomenda-se mapear todas as rubricas utilizadas."
            )

        return result

    async def generate_event(
        self,
        request: ESocialExportRequest,
        condominio_id: UUID,
        *,
        user_id: UUID = None,
    ) -> PayrollExport:
        """Gera evento eSocial."""
        # Validar integração
        validation = await self.validate_integration(condominio_id)
        if not validation["valid"]:
            raise ValueError(f"Integração inválida: {validation['errors']}")

        # Validar tipo de evento
        if request.event_type not in ESOCIAL_EVENTS:
            raise ValueError(f"Tipo de evento inválido: {request.event_type}")

        # Buscar período
        period = await self.period_repo.get_by_id(request.period_id)
        if not period:
            raise ValueError("Período não encontrado")

        # Criar exportacao
        # pylint: disable=import-outside-toplevel
        from modules.hr.payroll_integration.schemas import PayrollExportCreate

        export_data = PayrollExportCreate(
            name=f"eSocial {request.event_type} - {period.code}",
            description=ESOCIAL_EVENTS[request.event_type]["description"],
            export_format=ExportFormat.ESOCIAL_XML,
            export_type=request.event_type,
            period_id=request.period_id,
        )

        export = await self.export_repo.create(
            export_data,
            condominio_id,
            created_by=user_id,
        )

        # Processar exportação
        await self._process_esocial_export(export, request, condominio_id)

        return await self.export_repo.get_by_id(export.id)

    async def _process_esocial_export(
        self,
        export: PayrollExport,
        request: ESocialExportRequest,
        condominio_id: UUID,
    ) -> None:
        """Processa exportação eSocial."""
        await self.export_repo.start_processing(export.id)

        try:
            # Buscar dados
            events, _ = await self.event_repo.list_by_period(
                request.period_id,
                page_size=10000,
            )

            # Filtrar por funcionários se especificado
            if request.employees:
                events = [e for e in events if e.employee_id in request.employees]

            # Gerar XML
            xml_content = await self._generate_esocial_xml(
                event_type=request.event_type,
                events=events,
                condominio_id=condominio_id,
                test_mode=request.test_mode,
            )

            # Salvar
            file_name = f"{export.export_code}_{request.event_type}.xml"
            file_path = f"/esocial/{condominio_id}/{file_name}"

            await self.export_repo.complete(
                export.id,
                file_path=file_path,
                file_name=file_name,
                file_size=len(xml_content),
                total_records=len(events),
                success_records=len(events),
            )

        except Exception as e:
            logger.error("Erro ao processar eSocial %s: %s", export.id, e)
            await self.export_repo.fail(export.id, str(e))
            raise

    async def _generate_esocial_xml(
        self,
        event_type: str,
        events: list,
        condominio_id: UUID,
        test_mode: bool = False,
    ) -> bytes:
        """Gera XML do evento eSocial."""
        integration = await self.get_integration(condominio_id)
        config = integration.esocial_config or {}

        ambiente = "2" if test_mode or config.get("ambiente") == "producao_restrita" else "1"
        nr_inscricao = config.get("nr_inscricao", "00000000000000")

        # XML simplificado - em producao usaria biblioteca especializada
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<eSocial xmlns="http://www.esocial.gov.br/schema/lote/eventos/envio/v1_1_1">',
            "  <envioLoteEventos>",
            "    <ideEmpregador>",
            "      <tpInsc>1</tpInsc>",
            f"      <nrInsc>{nr_inscricao[:8]}</nrInsc>",
            "    </ideEmpregador>",
            "    <ideTransmissor>",
            "      <tpInsc>1</tpInsc>",
            f"      <nrInsc>{nr_inscricao}</nrInsc>",
            "    </ideTransmissor>",
            "    <eventos>",
        ]

        # Gerar eventos baseado no tipo
        if event_type == "S-1200":
            xml_lines.extend(self._generate_s1200_events(events, config, ambiente))
        elif event_type == "S-1210":
            xml_lines.extend(self._generate_s1210_events(events, config, ambiente))
        elif event_type == "S-1299":
            xml_lines.extend(self._generate_s1299_event(events, config, ambiente))

        xml_lines.extend(
            [
                "    </eventos>",
                "  </envioLoteEventos>",
                "</eSocial>",
            ]
        )

        return "\n".join(xml_lines).encode("utf-8")

    def _generate_s1200_events(
        self,
        events: list,
        config: dict,
        ambiente: str,
    ) -> list[str]:
        """Gera eventos S-1200."""
        lines = []

        # Agrupar por funcionário
        by_employee: dict[str, list] = {}
        for event in events:
            emp_id = str(event.employee_id)
            if emp_id not in by_employee:
                by_employee[emp_id] = []
            by_employee[emp_id].append(event)

        for emp_id, emp_events in by_employee.items():
            lines.append(f'      <evento Id="ID{emp_id[:30]}">')
            lines.append("        <evtRemun>")
            lines.append("          <ideEvento>")
            lines.append("            <indRetif>1</indRetif>")
            lines.append(f"            <tpAmb>{ambiente}</tpAmb>")
            lines.append("            <procEmi>1</procEmi>")
            lines.append("            <verProc>1.0</verProc>")
            lines.append("          </ideEvento>")
            lines.append("          <dmDev>")

            for event in emp_events:
                esocial_code = event.esocial_code or event.event_code
                valor = int(float(event.value) * 100)  # Em centavos

                lines.append("            <ideEstabLot>")
                lines.append("              <tpInsc>1</tpInsc>")
                lines.append(f"              <nrInsc>{config.get('nr_inscricao', '')}</nrInsc>")
                lines.append("              <remunPerApur>")
                lines.append("                <itensRemun>")
                lines.append(f"                  <codRubr>{esocial_code}</codRubr>")
                lines.append(f"                  <vrRubr>{valor}</vrRubr>")
                lines.append("                </itensRemun>")
                lines.append("              </remunPerApur>")
                lines.append("            </ideEstabLot>")

            lines.append("          </dmDev>")
            lines.append("        </evtRemun>")
            lines.append("      </evento>")

        return lines

    def _generate_s1210_events(
        self,
        events: list,  # pylint: disable=unused-argument
        config: dict,  # pylint: disable=unused-argument
        ambiente: str,
    ) -> list[str]:
        """Gera eventos S-1210."""
        lines = []
        # Implementacao simplificada
        lines.append('      <evento Id="ID_S1210">')
        lines.append("        <evtPgtos>")
        lines.append("          <ideEvento>")
        lines.append("            <indRetif>1</indRetif>")
        lines.append(f"            <tpAmb>{ambiente}</tpAmb>")
        lines.append("            <procEmi>1</procEmi>")
        lines.append("            <verProc>1.0</verProc>")
        lines.append("          </ideEvento>")
        lines.append("        </evtPgtos>")
        lines.append("      </evento>")
        return lines

    def _generate_s1299_event(
        self,
        events: list,  # pylint: disable=unused-argument
        config: dict,  # pylint: disable=unused-argument
        ambiente: str,
    ) -> list[str]:
        """Gera evento S-1299 (fechamento)."""
        lines = []
        lines.append('      <evento Id="ID_S1299">')
        lines.append("        <evtFechaEvPer>")
        lines.append("          <ideEvento>")
        lines.append("            <indRetif>1</indRetif>")
        lines.append(f"            <tpAmb>{ambiente}</tpAmb>")
        lines.append("            <procEmi>1</procEmi>")
        lines.append("            <verProc>1.0</verProc>")
        lines.append("          </ideEvento>")
        lines.append("          <ideRespInf>")
        lines.append("            <nmResp>Responsavel</nmResp>")
        lines.append("            <cpfResp>00000000000</cpfResp>")
        lines.append("            <telefone>0000000000</telefone>")
        lines.append("            <email>resp@email.com</email>")
        lines.append("          </ideRespInf>")
        lines.append("          <infoFech>")
        lines.append("            <evtRemun>S</evtRemun>")
        lines.append("            <evtPgtos>S</evtPgtos>")
        lines.append("            <evtAqProd>N</evtAqProd>")
        lines.append("            <evtComProd>N</evtComProd>")
        lines.append("            <evtContratAvNP>N</evtContratAvNP>")
        lines.append("            <evtInfoComplPer>N</evtInfoComplPer>")
        lines.append("          </infoFech>")
        lines.append("        </evtFechaEvPer>")
        lines.append("      </evento>")
        return lines

    async def transmit(
        self,
        export_id: UUID,
        condominio_id: UUID,
    ) -> ESocialTransmissionResponse:
        """Transmite evento ao eSocial."""
        export = await self.export_repo.get_by_id(export_id)
        if not export:
            raise ValueError("Exportação não encontrada")
        if not export.is_completed:
            raise ValueError("Exportação não concluída")

        integration = await self.get_integration(condominio_id)
        if not integration:
            raise ValueError("Integração eSocial não configurada")

        # Simular transmissão
        # Em produção, usaria biblioteca de assinatura digital e webservice

        transmission_id = f"PROTO-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        receipt = f"REC-{transmission_id}"

        await self.export_repo.record_transmission(
            export_id,
            transmission_id=transmission_id,
            receipt_number=receipt,
        )

        await self.integration_repo.record_sync(
            integration.id,
            success=True,
            records=export.total_records,
            message=f"Transmitido com sucesso: {receipt}",
        )

        return ESocialTransmissionResponse(
            export_id=export_id,
            protocol=transmission_id,
            receipt=receipt,
            status="accepted",
            transmitted_at=datetime.utcnow(),
            events_count=export.total_records,
            accepted_count=export.total_records,
            rejected_count=0,
            pending_count=0,
            rejections=None,
        )

    async def check_receipt(
        self,
        export_id: UUID,
        condominio_id: UUID,  # pylint: disable=unused-argument
    ) -> dict[str, Any]:
        """Consulta recibo de transmissão."""
        export = await self.export_repo.get_by_id(export_id)
        if not export:
            raise ValueError("Exportação não encontrada")

        if not export.transmission_id:
            raise ValueError("Exportação não foi transmitida")

        # Simular consulta
        return {
            "protocol": export.transmission_id,
            "receipt": export.receipt_number,
            "status": "processed",
            "processed_at": datetime.utcnow().isoformat(),
            "events": {
                "total": export.total_records,
                "accepted": export.success_records,
                "rejected": export.error_records,
            },
        }

    def get_supported_events(self) -> dict[str, dict[str, Any]]:
        """Os eventos e o que o sistema REALMENTE faz com cada um.

        Não se chama mais «suportados» na prática: cada entrada carrega `gerador`
        (`completo` · `esqueleto` · `nenhum`) e, quando não é completo, a razão. Antes
        devolvia sete periódicos como se todos estivessem prontos — três eram esqueleto e
        quatro não tinham gerador. Capacidade declarada e inexistente é o mesmo defeito
        que fez a EFD ICMS/IPI declarar nota de serviço como mercadoria.
        """
        return {k: dict(v) for k, v in ESOCIAL_EVENTS.items()}

    def eventos_por_maturidade(self) -> dict[str, list[str]]:
        """Resumo honesto: quais eventos estão completos, quais são casca, quais faltam."""
        fora: dict[str, list[str]] = {"completo": [], "esqueleto": [], "nenhum": []}
        for cod, info in ESOCIAL_EVENTS.items():
            fora.setdefault(info.get("gerador", "completo"), []).append(cod)
        return fora
