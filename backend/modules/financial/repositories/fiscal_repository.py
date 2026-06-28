"""Repository para modulo Fiscal - CRUD e operacoes de NF-e, NFS-e, SPED, Retencoes."""
# pylint: disable=too-many-lines,too-many-public-methods,too-many-arguments
# pylint: disable=too-many-positional-arguments,too-many-locals,not-callable

import logging
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, extract, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from modules.financial.models.cfop_ncm import CFOP, NCM, RetencaoFederal
from modules.financial.models.fiscal_obligation import (
    FiscalObligation,
    SimplesNacionalDAS,
    SUFRAMAConfig,
    SUFRAMAOperacao,
)
from modules.financial.models.nfe import NFe, NFeItem
from modules.financial.models.nfse import CodigoServico, NFSe
from modules.financial.models.sped_file import SPEDFile

logger = logging.getLogger(__name__)


class FiscalRepository:
    """Repository para operacoes fiscais."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    # ============================================================
    # CFOP
    # ============================================================

    async def create_cfop(self, data: dict[str, Any]) -> CFOP:
        """Cria um CFOP."""
        cfop = CFOP(**data)
        self.session.add(cfop)
        await self.session.flush()
        await self.session.refresh(cfop)
        return cfop

    async def get_cfop_by_id(self, cfop_id: UUID) -> CFOP | None:
        """Busca CFOP por ID."""
        result = await self.session.execute(select(CFOP).where(CFOP.id == cfop_id))
        return result.scalar_one_or_none()

    async def get_cfop_by_codigo(self, codigo: str) -> CFOP | None:
        """Busca CFOP por codigo."""
        result = await self.session.execute(select(CFOP).where(CFOP.codigo == codigo))
        return result.scalar_one_or_none()

    async def list_cfops(
        self,
        tipo: str | None = None,
        grupo: str | None = None,
        natureza: str | None = None,
        zfm_aplicavel: bool | None = None,
        active: bool = True,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CFOP], int]:
        """Lista CFOPs com filtros."""
        query = select(CFOP).where(CFOP.active == active)

        if tipo:
            query = query.where(CFOP.tipo == tipo)
        if grupo:
            query = query.where(CFOP.grupo == grupo)
        if natureza:
            query = query.where(CFOP.natureza == natureza)
        if zfm_aplicavel is not None:
            query = query.where(CFOP.zfm_aplicavel == zfm_aplicavel)
        if search:
            query = query.where(
                or_(
                    CFOP.codigo.ilike(f"%{search}%"),
                    CFOP.descricao.ilike(f"%{search}%"),
                )
            )

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        # Paginate
        query = query.order_by(CFOP.codigo)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def update_cfop(self, cfop_id: UUID, data: dict[str, Any]) -> CFOP | None:
        """Atualiza CFOP."""
        cfop = await self.get_cfop_by_id(cfop_id)
        if not cfop:
            return None
        for key, value in data.items():
            if hasattr(cfop, key) and value is not None:
                setattr(cfop, key, value)
        await self.session.flush()
        await self.session.refresh(cfop)
        return cfop

    # ============================================================
    # NCM
    # ============================================================

    async def create_ncm(self, data: dict[str, Any]) -> NCM:
        """Cria um NCM."""
        ncm = NCM(**data)
        self.session.add(ncm)
        await self.session.flush()
        await self.session.refresh(ncm)
        return ncm

    async def get_ncm_by_id(self, ncm_id: UUID) -> NCM | None:
        """Busca NCM por ID."""
        result = await self.session.execute(select(NCM).where(NCM.id == ncm_id))
        return result.scalar_one_or_none()

    async def get_ncm_by_codigo(self, codigo: str) -> NCM | None:
        """Busca NCM por codigo."""
        result = await self.session.execute(select(NCM).where(NCM.codigo == codigo))
        return result.scalar_one_or_none()

    async def list_ncms(
        self,
        capitulo: str | None = None,
        posicao: str | None = None,
        tributacao_monofasica: bool | None = None,
        zfm_isento_ipi: bool | None = None,
        active: bool = True,
        vigente: bool = True,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[NCM], int]:
        """Lista NCMs com filtros."""
        query = select(NCM).where(NCM.active == active)

        if capitulo:
            query = query.where(NCM.capitulo == capitulo)
        if posicao:
            query = query.where(NCM.posicao == posicao)
        if tributacao_monofasica is not None:
            query = query.where(NCM.tributacao_monofasica == tributacao_monofasica)
        if zfm_isento_ipi is not None:
            query = query.where(NCM.zfm_isento_ipi == zfm_isento_ipi)
        if vigente:
            hoje = date.today()
            query = query.where(or_(NCM.valid_from.is_(None), NCM.valid_from <= hoje)).where(
                or_(NCM.valid_until.is_(None), NCM.valid_until >= hoje)
            )
        if search:
            query = query.where(
                or_(
                    NCM.codigo.ilike(f"%{search}%"),
                    NCM.descricao.ilike(f"%{search}%"),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        query = query.order_by(NCM.codigo)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def update_ncm(self, ncm_id: UUID, data: dict[str, Any]) -> NCM | None:
        """Atualiza NCM."""
        ncm = await self.get_ncm_by_id(ncm_id)
        if not ncm:
            return None
        for key, value in data.items():
            if hasattr(ncm, key) and value is not None:
                setattr(ncm, key, value)
        await self.session.flush()
        await self.session.refresh(ncm)
        return ncm

    # ============================================================
    # Retencao Federal
    # ============================================================

    async def create_retencao(self, condominio_id: UUID, data: dict[str, Any]) -> RetencaoFederal:
        """Cria configuracao de retencao federal."""
        retencao = RetencaoFederal(condominio_id=condominio_id, **data)
        self.session.add(retencao)
        await self.session.flush()
        await self.session.refresh(retencao)
        return retencao

    async def get_retencao_by_id(self, retencao_id: UUID) -> RetencaoFederal | None:
        """Busca retencao por ID."""
        result = await self.session.execute(select(RetencaoFederal).where(RetencaoFederal.id == retencao_id))
        return result.scalar_one_or_none()

    async def list_retencoes(
        self,
        condominio_id: UUID,
        servico_vigilancia: bool | None = None,
        active: bool = True,
    ) -> list[RetencaoFederal]:
        """Lista configuracoes de retencao."""
        query = select(RetencaoFederal).where(
            and_(
                RetencaoFederal.condominio_id == condominio_id,
                RetencaoFederal.active == active,
            )
        )

        if servico_vigilancia is not None:
            query = query.where(RetencaoFederal.servico_vigilancia == servico_vigilancia)

        query = query.order_by(RetencaoFederal.nome)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_retencao_padrao_vigilancia(self, condominio_id: UUID) -> RetencaoFederal | None:
        """Busca configuracao padrao para servicos de vigilancia."""
        result = await self.session.execute(
            select(RetencaoFederal)
            .where(
                and_(
                    RetencaoFederal.condominio_id == condominio_id,
                    RetencaoFederal.servico_vigilancia.is_(True),
                    RetencaoFederal.active.is_(True),
                )
            )
            .order_by(RetencaoFederal.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def update_retencao(self, retencao_id: UUID, data: dict[str, Any]) -> RetencaoFederal | None:
        """Atualiza configuracao de retencao."""
        retencao = await self.get_retencao_by_id(retencao_id)
        if not retencao:
            return None
        for key, value in data.items():
            if hasattr(retencao, key) and value is not None:
                setattr(retencao, key, value)
        await self.session.flush()
        await self.session.refresh(retencao)
        return retencao

    # ============================================================
    # NF-e
    # ============================================================

    async def create_nfe(self, condominio_id: UUID, data: dict[str, Any], itens: list[dict[str, Any]]) -> NFe:
        """Cria uma NF-e com itens."""
        nfe_data = {k: v for k, v in data.items() if k != "itens"}
        nfe = NFe(condominio_id=condominio_id, **nfe_data)
        self.session.add(nfe)
        await self.session.flush()

        # Adiciona itens
        for item_data in itens:
            item = NFeItem(nfe_id=nfe.id, **item_data)
            self.session.add(item)

        await self.session.flush()
        await self.session.refresh(nfe)
        return nfe

    async def get_nfe_by_id(self, nfe_id: UUID) -> NFe | None:
        """Busca NF-e por ID com itens."""
        result = await self.session.execute(select(NFe).options(selectinload(NFe.itens)).where(NFe.id == nfe_id))
        return result.scalar_one_or_none()

    async def get_nfe_by_chave(self, chave_acesso: str) -> NFe | None:
        """Busca NF-e por chave de acesso."""
        result = await self.session.execute(
            select(NFe).options(selectinload(NFe.itens)).where(NFe.chave_acesso == chave_acesso)
        )
        return result.scalar_one_or_none()

    async def list_nfes(
        self,
        condominio_id: UUID,
        tipo: str | None = None,
        status: str | None = None,
        serie: int | None = None,
        numero_inicial: int | None = None,
        numero_final: int | None = None,
        data_inicial: date | None = None,
        data_final: date | None = None,
        destinatario_cpf_cnpj: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[NFe], int]:
        """Lista NF-es com filtros."""
        query = select(NFe).where(
            and_(
                NFe.condominio_id == condominio_id,
                NFe.active.is_(True),
            )
        )

        if tipo:
            query = query.where(NFe.tipo == tipo)
        if status:
            query = query.where(NFe.status == status)
        if serie:
            query = query.where(NFe.serie == serie)
        if numero_inicial:
            query = query.where(NFe.numero >= numero_inicial)
        if numero_final:
            query = query.where(NFe.numero <= numero_final)
        if data_inicial:
            query = query.where(func.date(NFe.data_emissao) >= data_inicial)
        if data_final:
            query = query.where(func.date(NFe.data_emissao) <= data_final)
        if destinatario_cpf_cnpj:
            query = query.where(NFe.destinatario_cpf_cnpj == destinatario_cpf_cnpj)
        if search:
            query = query.where(
                or_(
                    NFe.chave_acesso.ilike(f"%{search}%"),
                    NFe.destinatario_razao_social.ilike(f"%{search}%"),
                    NFe.natureza_operacao.ilike(f"%{search}%"),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        query = query.options(selectinload(NFe.itens))
        query = query.order_by(desc(NFe.data_emissao))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def update_nfe(self, nfe_id: UUID, data: dict[str, Any]) -> NFe | None:
        """Atualiza NF-e."""
        nfe = await self.get_nfe_by_id(nfe_id)
        if not nfe:
            return None
        for key, value in data.items():
            if hasattr(nfe, key) and value is not None:
                setattr(nfe, key, value)
        await self.session.flush()
        await self.session.refresh(nfe)
        return nfe

    async def get_proximo_numero_nfe(self, condominio_id: UUID, serie: int) -> int:
        """Retorna o proximo numero de NF-e para uma serie."""
        result = await self.session.execute(
            select(func.max(NFe.numero)).where(
                and_(
                    NFe.condominio_id == condominio_id,
                    NFe.serie == serie,
                )
            )
        )
        ultimo = result.scalar() or 0
        return ultimo + 1

    async def get_nfes_periodo(
        self,
        condominio_id: UUID,
        data_inicial: date,
        data_final: date,
        status: str | None = "autorizada",
    ) -> list[Any]:
        """Busca NF-es de um periodo para relatorios.

        Le a tabela REAL `nfes` (o model NFe aponta para `nfe`, que nunca foi criada).
        Retorna Rows com acesso por atributo (.valor_total_nota, .data_emissao, etc.).
        """
        conds = [
            "condominio_id = :cid",
            "active IS true",
            "date(data_emissao) >= :di",
            "date(data_emissao) <= :df",
        ]
        params: dict[str, Any] = {"cid": condominio_id, "di": data_inicial, "df": data_final}
        if status:
            conds.append("status = :status")
            params["status"] = status
        sql = text(
            "SELECT id, numero, serie, chave_acesso, status, data_emissao, "
            "valor_total_nota, valor_total_produtos "
            "FROM nfes WHERE " + " AND ".join(conds) + " ORDER BY data_emissao"
        )
        result = await self.session.execute(sql, params)
        return list(result.all())

    # ============================================================
    # NFS-e
    # ============================================================

    async def create_nfse(self, condominio_id: UUID, data: dict[str, Any]) -> NFSe:
        """Cria uma NFS-e."""
        nfse = NFSe(condominio_id=condominio_id, **data)
        self.session.add(nfse)
        await self.session.flush()
        await self.session.refresh(nfse)
        return nfse

    async def get_nfse_by_id(self, nfse_id: UUID) -> NFSe | None:
        """Busca NFS-e por ID."""
        result = await self.session.execute(select(NFSe).where(NFSe.id == nfse_id))
        return result.scalar_one_or_none()

    async def get_nfse_by_numero(self, condominio_id: UUID, numero: str) -> NFSe | None:
        """Busca NFS-e por numero."""
        result = await self.session.execute(
            select(NFSe).where(
                and_(
                    NFSe.condominio_id == condominio_id,
                    NFSe.numero_nfse == numero,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_nfses(
        self,
        condominio_id: UUID,
        status: str | None = None,
        data_inicial: date | None = None,
        data_final: date | None = None,
        competencia_mes: int | None = None,
        competencia_ano: int | None = None,
        tomador_cpf_cnpj: str | None = None,
        codigo_servico: str | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[NFSe], int]:
        """Lista NFS-es com filtros."""
        query = select(NFSe).where(
            and_(
                NFSe.condominio_id == condominio_id,
                NFSe.active.is_(True),
            )
        )

        if status:
            query = query.where(NFSe.status == status)
        if data_inicial:
            query = query.where(func.date(NFSe.data_emissao) >= data_inicial)
        if data_final:
            query = query.where(func.date(NFSe.data_emissao) <= data_final)
        if competencia_mes:
            query = query.where(extract("month", NFSe.data_competencia) == competencia_mes)
        if competencia_ano:
            query = query.where(extract("year", NFSe.data_competencia) == competencia_ano)
        if tomador_cpf_cnpj:
            query = query.where(NFSe.tomador_cpf_cnpj == tomador_cpf_cnpj)
        if codigo_servico:
            query = query.where(NFSe.codigo_servico == codigo_servico)
        if search:
            query = query.where(
                or_(
                    NFSe.numero_nfse.ilike(f"%{search}%"),
                    NFSe.tomador_razao_social.ilike(f"%{search}%"),
                    NFSe.descricao_servico.ilike(f"%{search}%"),
                )
            )

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        query = query.order_by(desc(NFSe.data_emissao))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def update_nfse(self, nfse_id: UUID, data: dict[str, Any]) -> NFSe | None:
        """Atualiza NFS-e."""
        nfse = await self.get_nfse_by_id(nfse_id)
        if not nfse:
            return None
        for key, value in data.items():
            if hasattr(nfse, key) and value is not None:
                setattr(nfse, key, value)
        await self.session.flush()
        await self.session.refresh(nfse)
        return nfse

    async def get_proximo_numero_rps(self, condominio_id: UUID, serie: str) -> int:
        """Retorna o proximo numero de RPS para uma serie."""
        result = await self.session.execute(
            select(func.max(NFSe.numero_rps)).where(
                and_(
                    NFSe.condominio_id == condominio_id,
                    NFSe.serie_rps == serie,
                )
            )
        )
        ultimo = result.scalar() or 0
        return ultimo + 1

    async def get_nfses_competencia(
        self,
        condominio_id: UUID,
        mes: int,
        ano: int,
        status: str | None = "autorizada",
    ) -> list[Any]:
        """Busca NFS-es de uma competencia.

        Le a tabela REAL `nfses` (o model NFSe aponta para `nfse`, inexistente).
        Retorna Rows com acesso por atributo (.valor_servicos, .inss_valor, etc.).
        """
        conds = [
            "condominio_id = :cid",
            "active IS true",
            "extract(month from data_competencia) = :mes",
            "extract(year from data_competencia) = :ano",
        ]
        params: dict[str, Any] = {"cid": condominio_id, "mes": mes, "ano": ano}
        if status:
            conds.append("status = :status")
            params["status"] = status
        sql = text(
            "SELECT id, numero_nfse, numero_rps, status, data_emissao, data_competencia, "
            "valor_servicos, iss_aliquota, iss_valor, iss_retido, pis_valor, cofins_valor, "
            "inss_valor, ir_valor, csll_valor, inss_liminar_aplicada "
            "FROM nfses WHERE " + " AND ".join(conds) + " ORDER BY data_emissao"
        )
        result = await self.session.execute(sql, params)
        return list(result.all())

    async def calcular_total_retencoes_competencia(self, condominio_id: UUID, mes: int, ano: int) -> dict[str, Decimal]:
        """Calcula total de retencoes de uma competencia."""
        nfses = await self.get_nfses_competencia(condominio_id, mes, ano)

        totais = {
            "valor_servicos": Decimal("0"),
            "inss": Decimal("0"),
            "ir": Decimal("0"),
            "csll": Decimal("0"),
            "pis": Decimal("0"),
            "cofins": Decimal("0"),
            "iss": Decimal("0"),
            "total_retencoes": Decimal("0"),
            "economia_liminar": Decimal("0"),
        }

        for nfse in nfses:
            totais["valor_servicos"] += nfse.valor_servicos or Decimal("0")
            totais["inss"] += nfse.inss_valor or Decimal("0")
            totais["ir"] += nfse.ir_valor or Decimal("0")
            totais["csll"] += nfse.csll_valor or Decimal("0")
            totais["pis"] += nfse.pis_valor or Decimal("0")
            totais["cofins"] += nfse.cofins_valor or Decimal("0")
            if nfse.iss_retido:
                totais["iss"] += nfse.iss_valor or Decimal("0")

            # Economia da liminar (11% que nao foi retido)
            if nfse.inss_liminar_aplicada:
                economia = nfse.valor_servicos * Decimal("0.11")
                totais["economia_liminar"] += economia

        totais["total_retencoes"] = (
            totais["inss"] + totais["ir"] + totais["csll"] + totais["pis"] + totais["cofins"] + totais["iss"]
        )

        return totais

    # ============================================================
    # Codigo de Servico
    # ============================================================

    async def get_codigo_servico(self, codigo: str) -> CodigoServico | None:
        """Busca codigo de servico LC 116."""
        result = await self.session.execute(select(CodigoServico).where(CodigoServico.codigo == codigo))
        return result.scalar_one_or_none()

    async def list_codigos_servico(self, search: str | None = None) -> list[CodigoServico]:
        """Lista codigos de servico."""
        query = select(CodigoServico).where(CodigoServico.active.is_(True))

        if search:
            query = query.where(
                or_(
                    CodigoServico.codigo.ilike(f"%{search}%"),
                    CodigoServico.descricao.ilike(f"%{search}%"),
                )
            )

        query = query.order_by(CodigoServico.codigo)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    # ============================================================
    # SPED
    # ============================================================

    async def create_sped_file(self, condominio_id: UUID, data: dict[str, Any]) -> SPEDFile:
        """Cria arquivo SPED."""
        sped = SPEDFile(condominio_id=condominio_id, **data)
        self.session.add(sped)
        await self.session.flush()
        await self.session.refresh(sped)
        return sped

    async def get_sped_file_by_id(self, sped_id: UUID) -> SPEDFile | None:
        """Busca arquivo SPED por ID."""
        result = await self.session.execute(select(SPEDFile).where(SPEDFile.id == sped_id))
        return result.scalar_one_or_none()

    async def list_sped_files(
        self,
        condominio_id: UUID,
        tipo: str | None = None,
        status: str | None = None,
        ano: int | None = None,
        mes: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SPEDFile], int]:
        """Lista arquivos SPED com filtros."""
        query = select(SPEDFile).where(
            and_(
                SPEDFile.condominio_id == condominio_id,
                SPEDFile.active.is_(True),
            )
        )

        if tipo:
            query = query.where(SPEDFile.tipo == tipo)
        if status:
            query = query.where(SPEDFile.status == status)
        if ano:
            query = query.where(SPEDFile.ano == ano)
        if mes:
            query = query.where(SPEDFile.mes == mes)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        query = query.order_by(desc(SPEDFile.ano), desc(SPEDFile.mes))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def update_sped_file(self, sped_id: UUID, data: dict[str, Any]) -> SPEDFile | None:
        """Atualiza arquivo SPED."""
        sped = await self.get_sped_file_by_id(sped_id)
        if not sped:
            return None
        for key, value in data.items():
            if hasattr(sped, key) and value is not None:
                setattr(sped, key, value)
        await self.session.flush()
        await self.session.refresh(sped)
        return sped

    # ============================================================
    # Obrigacao Fiscal
    # ============================================================

    async def create_obrigacao(self, condominio_id: UUID, data: dict[str, Any]) -> FiscalObligation:
        """Cria obrigacao fiscal."""
        # As colunas reais do banco sao competencia_mes/competencia_ano/valor_devido —
        # repassadas diretamente (sem remapeamento) para casar com o model alinhado.
        obrigacao = FiscalObligation(condominio_id=condominio_id, **dict(data))
        self.session.add(obrigacao)
        await self.session.flush()
        await self.session.refresh(obrigacao)
        return obrigacao

    async def get_obrigacao_by_id(self, obrigacao_id: UUID) -> FiscalObligation | None:
        """Busca obrigacao por ID."""
        result = await self.session.execute(select(FiscalObligation).where(FiscalObligation.id == obrigacao_id))
        return result.scalar_one_or_none()

    async def list_obrigacoes(
        self,
        condominio_id: UUID,
        tipo: str | None = None,
        status: str | None = None,
        mes: int | None = None,
        ano: int | None = None,
        vencimento_inicio: date | None = None,
        vencimento_fim: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[FiscalObligation], int]:
        """Lista obrigacoes fiscais com filtros."""
        query = select(FiscalObligation).where(
            and_(
                FiscalObligation.condominio_id == condominio_id,
                FiscalObligation.active.is_(True),
            )
        )

        if tipo:
            query = query.where(FiscalObligation.tipo == tipo)
        if status:
            query = query.where(FiscalObligation.status == status)
        if mes:
            query = query.where(FiscalObligation.competencia_mes == mes)
        if ano:
            query = query.where(FiscalObligation.competencia_ano == ano)
        if vencimento_inicio:
            query = query.where(FiscalObligation.data_vencimento >= vencimento_inicio)
        if vencimento_fim:
            query = query.where(FiscalObligation.data_vencimento <= vencimento_fim)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        query = query.order_by(FiscalObligation.data_vencimento)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_obrigacoes_pendentes(self, condominio_id: UUID) -> list[FiscalObligation]:
        """Lista obrigacoes pendentes ordenadas por vencimento."""
        result = await self.session.execute(
            select(FiscalObligation)
            .where(
                and_(
                    FiscalObligation.condominio_id == condominio_id,
                    FiscalObligation.status.in_(["pendente", "em_andamento"]),
                    FiscalObligation.active.is_(True),
                )
            )
            .order_by(FiscalObligation.data_vencimento)
        )
        return list(result.scalars().all())

    async def get_obrigacoes_atrasadas(self, condominio_id: UUID) -> list[FiscalObligation]:
        """Lista obrigacoes atrasadas."""
        result = await self.session.execute(
            select(FiscalObligation)
            .where(
                and_(
                    FiscalObligation.condominio_id == condominio_id,
                    FiscalObligation.status == "atrasada",
                    FiscalObligation.active.is_(True),
                )
            )
            .order_by(FiscalObligation.data_vencimento)
        )
        return list(result.scalars().all())

    async def update_obrigacao(self, obrigacao_id: UUID, data: dict[str, Any]) -> FiscalObligation | None:
        """Atualiza obrigacao fiscal."""
        obrigacao = await self.get_obrigacao_by_id(obrigacao_id)
        if not obrigacao:
            return None
        for key, value in data.items():
            if hasattr(obrigacao, key) and value is not None:
                setattr(obrigacao, key, value)
        await self.session.flush()
        await self.session.refresh(obrigacao)
        return obrigacao

    # ============================================================
    # Simples Nacional / DAS
    # ============================================================

    async def create_das(self, condominio_id: UUID, data: dict[str, Any]) -> SimplesNacionalDAS:
        """Cria DAS do Simples Nacional."""
        das = SimplesNacionalDAS(condominio_id=condominio_id, **data)
        self.session.add(das)
        await self.session.flush()
        await self.session.refresh(das)
        return das

    async def get_das_by_id(self, das_id: UUID) -> SimplesNacionalDAS | None:
        """Busca DAS por ID."""
        result = await self.session.execute(select(SimplesNacionalDAS).where(SimplesNacionalDAS.id == das_id))
        return result.scalar_one_or_none()

    async def get_das_competencia(self, condominio_id: UUID, mes: int, ano: int) -> SimplesNacionalDAS | None:
        """Busca DAS de uma competencia."""
        result = await self.session.execute(
            select(SimplesNacionalDAS).where(
                and_(
                    SimplesNacionalDAS.condominio_id == condominio_id,
                    SimplesNacionalDAS.competencia_mes == mes,
                    SimplesNacionalDAS.competencia_ano == ano,
                    SimplesNacionalDAS.active.is_(True),
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_das(self, condominio_id: UUID, ano: int | None = None) -> list[SimplesNacionalDAS]:
        """Lista DAS de um condominio."""
        query = select(SimplesNacionalDAS).where(
            and_(
                SimplesNacionalDAS.condominio_id == condominio_id,
                SimplesNacionalDAS.active.is_(True),
            )
        )
        if ano:
            query = query.where(SimplesNacionalDAS.competencia_ano == ano)

        query = query.order_by(
            SimplesNacionalDAS.competencia_ano.desc(),
            SimplesNacionalDAS.competencia_mes.desc(),
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_receita_12_meses(self, condominio_id: UUID, mes_referencia: int, ano_referencia: int) -> Decimal:
        """Calcula receita bruta dos ultimos 12 meses para DAS."""
        # Calcula range de 12 meses
        total = Decimal("0")

        for i in range(12):
            mes = mes_referencia - i
            ano = ano_referencia
            if mes <= 0:
                mes += 12
                ano -= 1

            # Busca NFS-es do mes
            nfses = await self.get_nfses_competencia(condominio_id, mes, ano)
            for nfse in nfses:
                total += nfse.valor_servicos or Decimal("0")

            # Busca NF-es do mes
            data_inicio = date(ano, mes, 1)
            if mes == 12:
                data_fim = date(ano + 1, 1, 1)
            else:
                data_fim = date(ano, mes + 1, 1)
            nfes = await self.get_nfes_periodo(condominio_id, data_inicio, data_fim)
            for nfe in nfes:
                total += nfe.valor_total_nota or Decimal("0")

        return total

    # ============================================================
    # SUFRAMA
    # ============================================================

    async def create_suframa_config(self, condominio_id: UUID, data: dict[str, Any]) -> SUFRAMAConfig:
        """Cria configuracao SUFRAMA."""
        config = SUFRAMAConfig(condominio_id=condominio_id, **data)
        self.session.add(config)
        await self.session.flush()
        await self.session.refresh(config)
        return config

    async def get_suframa_config(self, condominio_id: UUID) -> SUFRAMAConfig | None:
        """Busca configuracao SUFRAMA ativa."""
        result = await self.session.execute(
            select(SUFRAMAConfig)
            .where(
                and_(
                    SUFRAMAConfig.condominio_id == condominio_id,
                    SUFRAMAConfig.active.is_(True),
                )
            )
            .order_by(SUFRAMAConfig.created_at.desc())
        )
        return result.scalar_one_or_none()

    async def create_suframa_operacao(self, condominio_id: UUID, data: dict[str, Any]) -> SUFRAMAOperacao:
        """Registra operacao com beneficio SUFRAMA."""
        operacao = SUFRAMAOperacao(condominio_id=condominio_id, **data)
        self.session.add(operacao)
        await self.session.flush()
        await self.session.refresh(operacao)
        return operacao

    async def list_suframa_operacoes(
        self,
        condominio_id: UUID,
        data_inicial: date | None = None,
        data_final: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SUFRAMAOperacao], int]:
        """Lista operacoes com beneficio SUFRAMA."""
        query = select(SUFRAMAOperacao).where(
            and_(
                SUFRAMAOperacao.condominio_id == condominio_id,
                SUFRAMAOperacao.active.is_(True),
            )
        )

        if data_inicial:
            query = query.where(SUFRAMAOperacao.data_operacao >= data_inicial)
        if data_final:
            query = query.where(SUFRAMAOperacao.data_operacao <= data_final)

        count_query = select(func.count()).select_from(query.subquery())
        total = await self.session.scalar(count_query) or 0

        query = query.order_by(desc(SUFRAMAOperacao.data_operacao))
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    async def get_economia_suframa_periodo(
        self,
        condominio_id: UUID,
        data_inicial: date,
        data_final: date,
    ) -> dict[str, Decimal]:
        """Calcula economia SUFRAMA de um periodo."""
        operacoes, _ = await self.list_suframa_operacoes(condominio_id, data_inicial, data_final, page_size=10000)

        economia = {
            "ipi": Decimal("0"),
            "icms": Decimal("0"),
            "pis_cofins": Decimal("0"),
            "total": Decimal("0"),
        }

        for op in operacoes:
            economia["ipi"] += op.valor_ipi_desonerado or Decimal("0")
            economia["icms"] += op.valor_icms_desonerado or Decimal("0")
            economia["pis_cofins"] += (op.valor_pis_suspenso or Decimal("0")) + (
                op.valor_cofins_suspenso or Decimal("0")
            )

        economia["total"] = economia["ipi"] + economia["icms"] + economia["pis_cofins"]

        return economia

    # ============================================================
    # Estatisticas e Dashboard
    # ============================================================

    async def get_fiscal_stats(self, condominio_id: UUID, mes: int, ano: int) -> dict[str, Any]:
        """Retorna estatisticas fiscais do mes."""
        # NF-e
        nfes_mes = await self.get_nfes_periodo(
            condominio_id,
            date(ano, mes, 1),
            date(ano, mes + 1, 1) if mes < 12 else date(ano + 1, 1, 1),
        )
        total_nfe_mes = sum(nfe.valor_total_nota or Decimal("0") for nfe in nfes_mes)

        # NFS-e
        nfses_mes = await self.get_nfses_competencia(condominio_id, mes, ano)
        total_nfse_mes = sum(nfse.valor_servicos or Decimal("0") for nfse in nfses_mes)

        # Retencoes
        retencoes = await self.calcular_total_retencoes_competencia(condominio_id, mes, ano)

        # Obrigacoes
        obrigacoes_pendentes = await self.get_obrigacoes_pendentes(condominio_id)
        obrigacoes_atrasadas = await self.get_obrigacoes_atrasadas(condominio_id)

        # DAS
        das = await self.get_das_competencia(condominio_id, mes, ano)

        # SUFRAMA economia ano
        economia_zfm = await self.get_economia_suframa_periodo(condominio_id, date(ano, 1, 1), date(ano, 12, 31))

        return {
            "total_nfe_emitidas": len(nfes_mes),
            "total_nfe_mes": len(nfes_mes),
            "valor_total_nfe_mes": total_nfe_mes,
            "total_nfse_emitidas": len(nfses_mes),
            "total_nfse_mes": len(nfses_mes),
            "valor_total_nfse_mes": total_nfse_mes,
            "total_retencoes_mes": retencoes["total_retencoes"],
            "economia_liminar_inss": retencoes["economia_liminar"],
            "obrigacoes_pendentes": len(obrigacoes_pendentes),
            "obrigacoes_atrasadas": len(obrigacoes_atrasadas),
            "proxima_obrigacao": (
                {
                    "tipo": obrigacoes_pendentes[0].tipo,
                    "vencimento": obrigacoes_pendentes[0].data_vencimento.isoformat(),
                }
                if obrigacoes_pendentes
                else None
            ),
            "das_mes_atual": das.valor_devido if das else None,
            "faixa_atual": das.faixa if das else None,
            "receita_12_meses": das.receita_bruta_12_meses if das else None,
            "economia_zfm_mes": None,  # Calcular separadamente se necessario
            "economia_zfm_ano": economia_zfm["total"],
        }
