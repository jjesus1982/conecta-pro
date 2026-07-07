"""
Serviço Fiscal para Diaristas.

Fornece funcionalidades para:
- Cálculo de retenções (INSS, ISS, IRRF)
- Geração de RPA
- Integração com e-Social (criação de eventos PENDENTES — transmissão real NÃO implementada)
- Relatórios fiscais

REGRAS DE HONESTIDADE FISCAL:
- Tabelas INSS/IRRF vêm SEMPRE do banco (tabela_inss / tabela_irrf).
  Sem vigência cadastrada => HTTP 422 honesto, nunca valor chumbado silencioso.
- CNPJ do tomador vem SEMPRE do cadastro real (tabela empresas) ou do request.
  Nunca placeholder em documento fiscal.
"""

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.diaristas.models import Diarist, DiaristPayment
from modules.operacional.diaristas.models.documento_fiscal import (
    DocumentoFiscal,
    EventoESocial,
    RetencaoFiscal,
    StatusDocumentoFiscal,
    StatusEventoESocial,
    TabelaINSS,
    TabelaIRRF,
    TipoDocumentoFiscal,
    TipoEventoESocial,
    TipoRetencao,
)

logger = logging.getLogger(__name__)


# ISS varia por município. Padrão usado quando não informado: 5% (teto legal
# da LC 116/2003; alíquota aplicada em Manaus para serviços de limpeza).
ALIQUOTA_ISS_PADRAO = Decimal("5.00")


def _dec(valor: Any) -> Decimal:
    """Converte valor de JSONB (float/int/str) para Decimal com segurança."""
    if isinstance(valor, Decimal):
        return valor
    return Decimal(str(valor))


class FiscalService:
    """Serviço de cálculos e documentos fiscais para diaristas."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # CÁLCULOS DE RETENÇÕES
    # =========================================================================

    async def calcular_inss(
        self,
        valor_bruto: Decimal,
        data_referencia: date | None = None,
    ) -> dict[str, Decimal]:
        """
        Calcula INSS para contribuinte individual (autônomo).

        Para autônomos, a alíquota é a definida na tabela vigente (tabela_inss)
        sobre o valor até o teto.

        Args:
            valor_bruto: Valor bruto do serviço
            data_referencia: Data de referência para tabela

        Returns:
            Dict com base_calculo, aliquota e valor

        Raises:
            HTTPException 422: se não há tabela INSS cadastrada para o período
        """
        tabela = await self._get_tabela_inss(data_referencia)

        # Base é o menor entre valor bruto e teto
        teto = _dec(tabela["teto"])
        base_calculo = min(valor_bruto, teto)

        # Alíquota para contribuinte individual (autônomo) — vem do banco
        aliquota = _dec(tabela["aliquota_autonomo"])

        # Cálculo
        valor_inss = (base_calculo * aliquota / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "base_calculo": base_calculo,
            "aliquota": aliquota,
            "valor": valor_inss,
            "teto_aplicado": base_calculo < valor_bruto,
        }

    async def calcular_irrf(
        self,
        valor_bruto: Decimal,
        inss_retido: Decimal = Decimal("0"),
        dependentes: int = 0,
        data_referencia: date | None = None,
    ) -> dict[str, Decimal]:
        """
        Calcula IRRF sobre rendimentos de trabalho autônomo.

        A base é: Valor Bruto - INSS - (Dependentes * Dedução)

        Args:
            valor_bruto: Valor bruto do serviço
            inss_retido: Valor do INSS retido
            dependentes: Número de dependentes
            data_referencia: Data de referência para tabela

        Returns:
            Dict com base_calculo, aliquota, deducao e valor

        Raises:
            HTTPException 422: se não há tabela IRRF cadastrada para o período
        """
        tabela = await self._get_tabela_irrf(data_referencia)

        # Dedução por dependente — vem do banco
        deducao_dependente = _dec(tabela["deducao_dependente"])

        # Base de cálculo
        base_calculo = valor_bruto - inss_retido - (dependentes * deducao_dependente)
        base_calculo = max(base_calculo, Decimal("0"))

        # Encontrar faixa (JSONB do banco; aceita chave "acima_de" ou "acima")
        faixas = tabela["faixas"]
        aliquota = Decimal("0")
        deducao = Decimal("0")

        for faixa in faixas:
            if "ate" in faixa and base_calculo <= _dec(faixa["ate"]):
                aliquota = _dec(faixa["aliquota"])
                deducao = _dec(faixa.get("deducao", 0))
                break
            limite_acima = faixa.get("acima_de", faixa.get("acima"))
            if limite_acima is not None and base_calculo > _dec(limite_acima):
                aliquota = _dec(faixa["aliquota"])
                deducao = _dec(faixa.get("deducao", 0))

        # Cálculo
        if aliquota > 0:
            valor_irrf = ((base_calculo * aliquota / 100) - deducao).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            valor_irrf = max(valor_irrf, Decimal("0"))
        else:
            valor_irrf = Decimal("0")

        return {
            "base_calculo": base_calculo,
            "aliquota": aliquota,
            "deducao_tabela": deducao,
            "valor": valor_irrf,
            "dependentes": dependentes,
            "deducao_dependentes": dependentes * deducao_dependente,
        }

    def calcular_iss(
        self,
        valor_bruto: Decimal,
        aliquota: Decimal | None = None,
        municipio_codigo: str | None = None,
    ) -> dict[str, Decimal]:
        """
        Calcula ISS sobre serviços prestados.

        A alíquota varia de 2% a 5% dependendo do município e serviço.

        Args:
            valor_bruto: Valor bruto do serviço
            aliquota: Alíquota do ISS (se não informada, usa padrão 5% — Manaus)
            municipio_codigo: Código IBGE do município

        Returns:
            Dict com base_calculo, aliquota e valor
        """
        # TODO: Implementar consulta de alíquota por município
        aliquota_iss = aliquota or ALIQUOTA_ISS_PADRAO

        valor_iss = (valor_bruto * aliquota_iss / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "base_calculo": valor_bruto,
            "aliquota": aliquota_iss,
            "valor": valor_iss,
            "municipio": municipio_codigo,
        }

    async def calcular_todas_retencoes(
        self,
        valor_bruto: Decimal,
        dependentes: int = 0,
        aliquota_iss: Decimal | None = None,
        data_referencia: date | None = None,
    ) -> dict[str, Any]:
        """
        Calcula todas as retenções fiscais de uma vez.

        Args:
            valor_bruto: Valor bruto do serviço
            dependentes: Número de dependentes (para IRRF)
            aliquota_iss: Alíquota do ISS
            data_referencia: Data de referência para tabelas

        Returns:
            Dict com todos os cálculos e valor líquido
        """
        # INSS primeiro (deduz do IRRF)
        inss = await self.calcular_inss(valor_bruto, data_referencia)

        # IRRF (considera INSS)
        irrf = await self.calcular_irrf(valor_bruto, inss["valor"], dependentes, data_referencia)

        # ISS
        iss = self.calcular_iss(valor_bruto, aliquota_iss)

        # Total de retenções
        total_retencoes = inss["valor"] + irrf["valor"] + iss["valor"]

        # Valor líquido
        valor_liquido = valor_bruto - total_retencoes

        return {
            "valor_bruto": valor_bruto,
            "inss": inss,
            "irrf": irrf,
            "iss": iss,
            "total_retencoes": total_retencoes,
            "valor_liquido": valor_liquido,
        }

    # =========================================================================
    # GERAÇÃO DE DOCUMENTOS
    # =========================================================================

    async def gerar_rpa(
        self,
        diarist_id: UUID,
        payment_id: UUID | None = None,
        valor_bruto: Decimal | None = None,
        competencia: str | None = None,
        descricao_servico: str = "Prestação de serviços de limpeza e conservação",
        codigo_servico: str = "7.10",  # Código LC 116/2003 para limpeza
        dependentes: int = 0,
        aliquota_iss: Decimal | None = None,
        tomador_cnpj: str | None = None,
        tomador_razao_social: str | None = None,
    ) -> DocumentoFiscal:
        """
        Gera RPA (Recibo de Pagamento Autônomo) para um diarista.

        Args:
            diarist_id: ID do diarista
            payment_id: ID do pagamento (opcional)
            valor_bruto: Valor bruto do serviço
            competencia: Mês/ano de competência (YYYY-MM)
            descricao_servico: Descrição do serviço
            codigo_servico: Código do serviço (LC 116/2003)
            dependentes: Número de dependentes
            aliquota_iss: Alíquota do ISS
            tomador_cnpj: CNPJ do tomador (se ausente, busca a empresa real no banco)
            tomador_razao_social: Razão social do tomador

        Returns:
            DocumentoFiscal criado
        """
        # Buscar diarista
        result = await self.db.execute(select(Diarist).where(Diarist.id == diarist_id))
        diarista = result.scalar_one_or_none()
        if not diarista:
            raise ValueError(f"Diarista {diarist_id} não encontrado")

        # Se payment_id, buscar valor do pagamento
        payment = None
        if payment_id:
            result = await self.db.execute(select(DiaristPayment).where(DiaristPayment.id == payment_id))
            payment = result.scalar_one_or_none()
            if payment and not valor_bruto:
                valor_bruto = payment.valor_bruto

        if not valor_bruto:
            raise ValueError("Valor bruto é obrigatório")

        # Competência
        if not competencia:
            competencia = date.today().strftime("%Y-%m")

        # Tomador: se não informado, buscar a empresa REAL no banco (nunca placeholder)
        if not tomador_cnpj or not tomador_razao_social:
            empresa = await self._get_empresa_tomadora()
            tomador_cnpj = tomador_cnpj or empresa.cnpj
            tomador_razao_social = tomador_razao_social or empresa.razao_social

        # Calcular retenções
        retencoes = await self.calcular_todas_retencoes(
            valor_bruto=valor_bruto,
            dependentes=dependentes,
            aliquota_iss=aliquota_iss,
        )

        # Gerar número do RPA
        numero = await self._gerar_numero_documento("RPA")

        # Criar documento
        documento = DocumentoFiscal(
            numero=numero,
            tipo=TipoDocumentoFiscal.RPA,
            status=StatusDocumentoFiscal.EMITIDO,
            diarist_id=diarist_id,
            payment_id=payment_id,
            competencia=competencia,
            data_emissao=date.today(),
            # Valores
            valor_bruto=valor_bruto,
            valor_inss=retencoes["inss"]["valor"],
            valor_iss=retencoes["iss"]["valor"],
            valor_irrf=retencoes["irrf"]["valor"],
            valor_liquido=retencoes["valor_liquido"],
            # Prestador (colunas reais do model Diarist — PT-BR)
            prestador_cpf=diarista.cpf,
            prestador_nome=diarista.nome,
            prestador_endereco=diarista.endereco,
            prestador_municipio=diarista.cidade,
            prestador_uf=diarista.estado,
            prestador_pis=None,  # Diarist não possui PIS cadastrado — não inventar
            # Tomador (dados reais — request ou tabela empresas)
            tomador_cnpj=tomador_cnpj,
            tomador_razao_social=tomador_razao_social,
            # Serviço
            descricao_servico=descricao_servico,
            codigo_servico=codigo_servico,
            # Bases de cálculo
            base_calculo_inss=retencoes["inss"]["base_calculo"],
            aliquota_inss=retencoes["inss"]["aliquota"],
            base_calculo_iss=retencoes["iss"]["base_calculo"],
            aliquota_iss=retencoes["iss"]["aliquota"],
            base_calculo_irrf=retencoes["irrf"]["base_calculo"],
            aliquota_irrf=retencoes["irrf"]["aliquota"],
        )

        self.db.add(documento)
        # Flush para materializar documento.id antes de criar as retenções filhas
        await self.db.flush()

        # Criar retenções detalhadas
        if retencoes["inss"]["valor"] > 0:
            retencao_inss = RetencaoFiscal(
                documento_id=documento.id,
                tipo=TipoRetencao.INSS,
                base_calculo=retencoes["inss"]["base_calculo"],
                aliquota=retencoes["inss"]["aliquota"],
                valor=retencoes["inss"]["valor"],
                fundamentacao_legal="Art. 30, I, Lei 8.212/91",
                codigo_receita="1162",
            )
            self.db.add(retencao_inss)

        if retencoes["iss"]["valor"] > 0:
            retencao_iss = RetencaoFiscal(
                documento_id=documento.id,
                tipo=TipoRetencao.ISS,
                base_calculo=retencoes["iss"]["base_calculo"],
                aliquota=retencoes["iss"]["aliquota"],
                valor=retencoes["iss"]["valor"],
                fundamentacao_legal="LC 116/2003",
            )
            self.db.add(retencao_iss)

        if retencoes["irrf"]["valor"] > 0:
            retencao_irrf = RetencaoFiscal(
                documento_id=documento.id,
                tipo=TipoRetencao.IRRF,
                base_calculo=retencoes["irrf"]["base_calculo"],
                aliquota=retencoes["irrf"]["aliquota"],
                valor=retencoes["irrf"]["valor"],
                fundamentacao_legal="Art. 7º, Lei 7.713/88",
                codigo_receita="0588",
            )
            self.db.add(retencao_irrf)

        await self.db.commit()
        await self.db.refresh(documento)

        logger.info(f"RPA {numero} gerado para diarista {diarist_id}")

        return documento

    async def _gerar_numero_documento(self, prefixo: str = "RPA") -> str:
        """Gera número sequencial para documento."""
        ano = date.today().year
        # Buscar último número do ano
        result = await self.db.execute(
            select(func.max(DocumentoFiscal.numero)).where(DocumentoFiscal.numero.like(f"{prefixo}-{ano}-%"))
        )
        ultimo = result.scalar()

        if ultimo:
            seq = int(ultimo.split("-")[-1]) + 1
        else:
            seq = 1

        return f"{prefixo}-{ano}-{seq:06d}"

    # =========================================================================
    # E-SOCIAL
    # =========================================================================
    # IMPORTANTE: estes métodos apenas CRIAM o evento com status PENDENTE no
    # banco. NÃO há transmissão real ao e-Social aqui — nenhum status de
    # "autorizado/transmitido" é fabricado. A transmissão real, quando
    # implementada, deve atualizar status/recibo com o retorno oficial.

    async def criar_evento_s2300(
        self,
        diarist_id: UUID,
        data_inicio: date,
    ) -> EventoESocial:
        """
        Cria evento S-2300 (Trabalhador Sem Vínculo - Início) com status PENDENTE.

        Este evento deve ser enviado quando um autônomo é contratado.
        A transmissão real ao e-Social NÃO é feita aqui.

        Args:
            diarist_id: ID do diarista
            data_inicio: Data de início da prestação de serviço

        Returns:
            EventoESocial criado (PENDENTE)
        """
        result = await self.db.execute(select(Diarist).where(Diarist.id == diarist_id))
        diarista = result.scalar_one_or_none()
        if not diarista:
            raise ValueError(f"Diarista {diarist_id} não encontrado")

        competencia = data_inicio.strftime("%Y-%m")

        # Dados do evento — apenas dados REAIS do cadastro; campos ausentes vão
        # como None (o envio real deve validar/completar antes de transmitir).
        dados_evento = {
            "cpfTrab": diarista.cpf,
            "nmTrab": diarista.nome,
            "dtNascto": diarista.data_nascimento.isoformat() if diarista.data_nascimento else None,
            # Diarist não possui campo de sexo cadastrado — não inventar
            "sexo": None,
            "cadIni": {
                "codCateg": "701",  # Contribuinte individual - Autônomo
                "dtInicio": data_inicio.isoformat(),
            },
            "infoComplementares": {
                "infoTrabAutonomo": {
                    "indAutonomo": "S",
                },
            },
        }

        evento = EventoESocial(
            tipo_evento=TipoEventoESocial.S2300,
            status=StatusEventoESocial.PENDENTE,
            diarist_id=diarist_id,
            competencia=competencia,
            dados_evento=dados_evento,
        )

        self.db.add(evento)
        await self.db.commit()
        await self.db.refresh(evento)

        logger.info(f"Evento S-2300 criado (PENDENTE, sem transmissão) para diarista {diarist_id}")

        return evento

    async def criar_evento_s1200(
        self,
        diarist_id: UUID,
        competencia: str,
        valor_remuneracao: Decimal,
    ) -> EventoESocial:
        """
        Cria evento S-1200 (Remuneração RGPS) com status PENDENTE.

        Este evento informa a remuneração mensal do autônomo.
        A transmissão real ao e-Social NÃO é feita aqui.

        Args:
            diarist_id: ID do diarista
            competencia: Mês/ano (YYYY-MM)
            valor_remuneracao: Valor da remuneração

        Returns:
            EventoESocial criado (PENDENTE)
        """
        result = await self.db.execute(select(Diarist).where(Diarist.id == diarist_id))
        diarista = result.scalar_one_or_none()
        if not diarista:
            raise ValueError(f"Diarista {diarist_id} não encontrado")

        # CNPJ REAL da empresa (nunca placeholder em evento fiscal)
        empresa = await self._get_empresa_tomadora()
        cnpj_digits = "".join(ch for ch in empresa.cnpj if ch.isdigit())

        dados_evento = {
            "cpfTrab": diarista.cpf,
            "perApur": competencia,
            "dmDev": [
                {
                    "ideDmDev": str(uuid4())[:8],
                    "codCateg": "701",
                    "infoPerApur": {
                        "ideEstabLot": [
                            {
                                "tpInsc": "1",  # CNPJ
                                "nrInsc": cnpj_digits,  # CNPJ real (tabela empresas)
                                "detVerbas": [
                                    {
                                        "codRubr": "1000",
                                        "ideTabRubr": "001",
                                        "qtdRubr": 1,
                                        "fatorRubr": 1,
                                        "vrUnit": float(valor_remuneracao),
                                        "vrRubr": float(valor_remuneracao),
                                    }
                                ],
                                "infoAgNocivo": {
                                    "grauExp": "1",
                                },
                            }
                        ],
                    },
                }
            ],
            "infoComplCont": {
                "codCBO": "5142-05",  # Auxiliar de serviços de limpeza
            },
        }

        evento = EventoESocial(
            tipo_evento=TipoEventoESocial.S1200,
            status=StatusEventoESocial.PENDENTE,
            diarist_id=diarist_id,
            competencia=competencia,
            dados_evento=dados_evento,
        )

        self.db.add(evento)
        await self.db.commit()
        await self.db.refresh(evento)

        logger.info(
            f"Evento S-1200 criado (PENDENTE, sem transmissão) para diarista {diarist_id}, competência {competencia}"
        )

        return evento

    # =========================================================================
    # CONSULTAS E RELATÓRIOS
    # =========================================================================

    async def listar_documentos(
        self,
        diarist_id: UUID | None = None,
        tipo: TipoDocumentoFiscal | None = None,
        competencia: str | None = None,
        status: StatusDocumentoFiscal | None = None,
        limit: int = 50,
    ) -> list[DocumentoFiscal]:
        """Lista documentos fiscais com filtros."""
        stmt = select(DocumentoFiscal).where(DocumentoFiscal.is_active)

        if diarist_id:
            stmt = stmt.where(DocumentoFiscal.diarist_id == diarist_id)
        if tipo:
            stmt = stmt.where(DocumentoFiscal.tipo == tipo)
        if competencia:
            stmt = stmt.where(DocumentoFiscal.competencia == competencia)
        if status:
            stmt = stmt.where(DocumentoFiscal.status == status)

        stmt = stmt.order_by(DocumentoFiscal.data_emissao.desc()).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def relatorio_retencoes_periodo(
        self,
        data_inicio: date,
        data_fim: date,
        diarist_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Gera relatório de retenções por período.

        Args:
            data_inicio: Data inicial
            data_fim: Data final
            diarist_id: Filtrar por diarista

        Returns:
            Dict com totais de retenções
        """
        stmt = select(
            func.sum(DocumentoFiscal.valor_bruto).label("total_bruto"),
            func.sum(DocumentoFiscal.valor_inss).label("total_inss"),
            func.sum(DocumentoFiscal.valor_iss).label("total_iss"),
            func.sum(DocumentoFiscal.valor_irrf).label("total_irrf"),
            func.sum(DocumentoFiscal.valor_liquido).label("total_liquido"),
            func.count(DocumentoFiscal.id).label("qtd_documentos"),
        ).where(
            DocumentoFiscal.is_active,
            DocumentoFiscal.status == StatusDocumentoFiscal.EMITIDO,
            DocumentoFiscal.data_emissao >= data_inicio,
            DocumentoFiscal.data_emissao <= data_fim,
        )

        if diarist_id:
            stmt = stmt.where(DocumentoFiscal.diarist_id == diarist_id)

        result = await self.db.execute(stmt)
        resultado = result.first()

        return {
            "periodo": {
                "inicio": data_inicio.isoformat(),
                "fim": data_fim.isoformat(),
            },
            "totais": {
                "bruto": float(resultado.total_bruto or 0),
                "inss": float(resultado.total_inss or 0),
                "iss": float(resultado.total_iss or 0),
                "irrf": float(resultado.total_irrf or 0),
                "total_retencoes": float(
                    (resultado.total_inss or 0) + (resultado.total_iss or 0) + (resultado.total_irrf or 0)
                ),
                "liquido": float(resultado.total_liquido or 0),
            },
            "documentos": int(resultado.qtd_documentos or 0),
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    async def _get_empresa_tomadora(self):
        """
        Busca a empresa tomadora REAL no banco (tabela empresas).

        Nunca retorna placeholder: se não houver empresa com CNPJ cadastrado,
        levanta 422 honesto.
        """
        from modules.empresas.models.empresa import Empresa

        result = await self.db.execute(
            select(Empresa)
            .where(Empresa.cnpj.isnot(None))
            .order_by(Empresa.is_principal.desc().nulls_last(), Empresa.created_at)
            .limit(1)
        )
        empresa = result.scalars().first()

        if not empresa or not empresa.cnpj or not empresa.razao_social:
            raise HTTPException(
                status_code=422,
                detail=(
                    "CNPJ do tomador não informado e nenhuma empresa com CNPJ cadastrada na tabela "
                    "'empresas'. Informe tomador_cnpj/tomador_razao_social ou cadastre a empresa — "
                    "documento fiscal nunca é emitido com CNPJ placeholder."
                ),
            )

        return empresa

    async def _get_tabela_inss(self, data_referencia: date | None = None) -> dict:
        """
        Obtém tabela INSS vigente do banco (tabela_inss).

        Raises:
            HTTPException 422: se não há vigência cadastrada para o período
        """
        data = data_referencia or date.today()

        result = await self.db.execute(
            select(TabelaINSS)
            .where(
                TabelaINSS.is_active,
                TabelaINSS.vigencia_inicio <= data,
                or_(TabelaINSS.vigencia_fim.is_(None), TabelaINSS.vigencia_fim >= data),
            )
            .order_by(TabelaINSS.vigencia_inicio.desc())
            .limit(1)
        )
        tabela = result.scalars().first()

        if not tabela:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Tabela INSS não cadastrada para o período {data.isoformat()} "
                    "(tabela_inss). Cadastre a vigência — cálculo fiscal não usa valores chumbados."
                ),
            )

        return {
            "vigencia_inicio": tabela.vigencia_inicio.isoformat(),
            "vigencia_fim": tabela.vigencia_fim.isoformat() if tabela.vigencia_fim else None,
            "faixas": tabela.faixas,
            "teto": tabela.teto_contribuicao,
            "aliquota_autonomo": tabela.aliquota_autonomo,
        }

    async def _get_tabela_irrf(self, data_referencia: date | None = None) -> dict:
        """
        Obtém tabela IRRF vigente do banco (tabela_irrf).

        Raises:
            HTTPException 422: se não há vigência cadastrada para o período
        """
        data = data_referencia or date.today()

        result = await self.db.execute(
            select(TabelaIRRF)
            .where(
                TabelaIRRF.is_active,
                TabelaIRRF.vigencia_inicio <= data,
                or_(TabelaIRRF.vigencia_fim.is_(None), TabelaIRRF.vigencia_fim >= data),
            )
            .order_by(TabelaIRRF.vigencia_inicio.desc())
            .limit(1)
        )
        tabela = result.scalars().first()

        if not tabela:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Tabela IRRF não cadastrada para o período {data.isoformat()} "
                    "(tabela_irrf). Cadastre a vigência — cálculo fiscal não usa valores chumbados."
                ),
            )

        return {
            "vigencia_inicio": tabela.vigencia_inicio.isoformat(),
            "vigencia_fim": tabela.vigencia_fim.isoformat() if tabela.vigencia_fim else None,
            "faixas": tabela.faixas,
            "deducao_dependente": tabela.deducao_dependente,
        }


# Factory
def get_fiscal_service(db: AsyncSession) -> FiscalService:
    """Factory function para obter instância do serviço."""
    return FiscalService(db)
