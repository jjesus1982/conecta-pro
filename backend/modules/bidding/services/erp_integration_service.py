"""
Service de Integracao ERP - Licitacoes
======================================
Bridge: Licitacao -> Contrato Operacional -> Financeiro -> Fiscal

Converte contratos publicos (bidding) em entidades operacionais
(postos, alocacoes) e gera medicoes/faturas para o financeiro.
Gera NFS-e via integracao com modulo fiscal.
"""

import contextlib
import logging
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from modules.bidding.models.measurement import Measurement, MeasurementStatus, MeasurementType
from modules.bidding.models.public_contract import ContractStatus, PublicContract
from modules.operacional.models.allocation import Allocation, AllocationStatus
from modules.operacional.models.post import Post, PostStatus, PostType, ShiftType

logger = logging.getLogger(__name__)

# Prazo padrao de vencimento em dias (usado quando contrato nao especifica)
_DEFAULT_PAYMENT_DAYS = 30


class ERPIntegrationService:
    """
    Service de integracao ERP para o modulo de licitacoes.

    Responsavel por:
    - Converter contratos publicos em entidades operacionais (postos/alocacoes)
    - Gerar medicoes baseadas em alocacoes e horas trabalhadas
    - Gerar faturas a partir de medicoes aprovadas
    - Consultar status de integracao entre modulos
    """

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ #
    #  1. Converter contrato publico -> entidades operacionais           #
    # ------------------------------------------------------------------ #

    async def converter_para_contrato_operacional(
        self,
        contract_id: UUID,
        postos_config: list[dict] | None = None,
        user_id: UUID | None = None,
    ) -> dict:
        """
        Converte um contrato publico (bidding) em entidades operacionais.

        Cria postos de trabalho e (opcionalmente) alocacoes iniciais
        vinculados ao contrato de licitacao.

        Args:
            contract_id: ID do contrato publico (bidding_public_contracts)
            postos_config: Lista de configuracoes de postos a criar.
                Cada item: {
                    "name": str,
                    "post_type": str (PostType value),
                    "shift_type": str (ShiftType value),
                    "headcount": int,
                    "address": str | None,
                    "city": str | None,
                    "state": str | None,
                    "hourly_rate": float | None,
                    "monthly_cost": float | None,
                    "requires_armed": bool,
                }
                Se None, cria um posto generico baseado no objeto do contrato.
            user_id: ID do usuario que esta realizando a conversao.

        Returns:
            dict com contrato, postos criados e resumo.

        Raises:
            ValueError: Se contrato nao encontrado, inativo ou ja convertido.
        """
        # Busca contrato
        result = await self.db.execute(
            select(PublicContract)
            .options(selectinload(PublicContract.medicoes))
            .where(PublicContract.id == contract_id, PublicContract.ativo)
        )
        contract = result.scalar_one_or_none()

        if not contract:
            raise ValueError(f"Contrato {contract_id} nao encontrado ou inativo")

        if contract.status not in (ContractStatus.ACTIVE.value, ContractStatus.DRAFT.value):
            raise ValueError(
                f"Contrato {contract.numero_contrato}/{contract.ano_contrato} "
                f"com status '{contract.status}' nao pode ser convertido. "
                f"Status permitidos: active, draft"
            )

        # Verifica se ja existem postos vinculados
        existing_posts = await self._get_postos_por_contrato(contract_id)
        if existing_posts:
            raise ValueError(
                f"Contrato {contract.numero_contrato}/{contract.ano_contrato} "
                f"ja possui {len(existing_posts)} posto(s) operacional(is) vinculado(s). "
                f"Use status_integracao() para consultar."
            )

        # Gera codigo sequencial para postos
        code_base = await self._next_post_code()

        # Cria postos
        created_posts = []
        if postos_config:
            for i, cfg in enumerate(postos_config):
                post = await self._criar_posto(
                    contract=contract,
                    code=f"POST-{code_base + i:04d}",
                    config=cfg,
                    user_id=user_id,
                )
                created_posts.append(post)
        else:
            # Posto generico baseado no objeto do contrato
            post = await self._criar_posto(
                contract=contract,
                code=f"POST-{code_base:04d}",
                config={
                    "name": f"Posto - {contract.objeto_resumido or contract.objeto[:80]}",
                    "post_type": PostType.PORTEIRO.value,
                    "shift_type": ShiftType.DIURNO.value,
                    "headcount": 1,
                    "address": None,
                    "city": None,
                    "state": contract.orgao_uf,
                },
                user_id=user_id,
            )
            created_posts.append(post)

        await self.db.commit()

        # Refresh para obter IDs gerados
        for post in created_posts:
            await self.db.refresh(post)

        logger.info(
            "Contrato %s/%s convertido: %d posto(s) criado(s)",
            contract.numero_contrato,
            contract.ano_contrato,
            len(created_posts),
        )

        return {
            "contrato_id": str(contract.id),
            "numero_contrato": contract.numero_contrato,
            "ano_contrato": contract.ano_contrato,
            "orgao_nome": contract.orgao_nome,
            "valor_contrato": float(contract.valor_contrato),
            "vigencia_inicio": contract.data_vigencia_inicio.isoformat(),
            "vigencia_fim": contract.data_vigencia_fim.isoformat(),
            "postos_criados": [
                {
                    "id": p.id,
                    "code": p.code,
                    "name": p.name,
                    "post_type": p.post_type,
                    "shift_type": p.shift_type,
                    "required_headcount": p.required_headcount,
                    "monthly_cost": p.monthly_cost,
                }
                for p in created_posts
            ],
            "total_postos": len(created_posts),
            "total_headcount": sum(p.required_headcount for p in created_posts),
            "custo_mensal_estimado": sum(p.monthly_cost for p in created_posts),
            "proximos_passos": [
                "Alocar funcionarios nos postos criados",
                "Configurar escalas de trabalho",
                "Gerar primeira medicao apos inicio da vigencia",
            ],
        }

    # ------------------------------------------------------------------ #
    #  2. Gerar medicao para um periodo                                  #
    # ------------------------------------------------------------------ #

    async def gerar_medicao(
        self,
        contract_id: UUID,
        competencia: str,
        periodo_inicio: date,
        periodo_fim: date,
        user_id: UUID | None = None,
    ) -> dict:
        """
        Gera uma medicao para um contrato em um periodo especifico.

        Calcula o valor bruto baseado nos postos/alocacoes ativas e
        horas trabalhadas no periodo.

        Args:
            contract_id: ID do contrato publico.
            competencia: Competencia no formato YYYY-MM.
            periodo_inicio: Data inicio do periodo de medicao.
            periodo_fim: Data fim do periodo de medicao.
            user_id: ID do usuario.

        Returns:
            dict com dados da medicao criada.

        Raises:
            ValueError: Se contrato nao encontrado ou periodo invalido.
        """
        # Busca contrato
        result = await self.db.execute(
            select(PublicContract)
            .options(selectinload(PublicContract.medicoes))
            .where(PublicContract.id == contract_id, PublicContract.ativo)
        )
        contract = result.scalar_one_or_none()

        if not contract:
            raise ValueError(f"Contrato {contract_id} nao encontrado")

        if contract.status != ContractStatus.ACTIVE.value:
            raise ValueError(
                f"Contrato {contract.numero_contrato}/{contract.ano_contrato} "
                f"nao esta ativo (status: {contract.status})"
            )

        if periodo_inicio > periodo_fim:
            raise ValueError("periodo_inicio deve ser anterior a periodo_fim")

        # Verifica se ja existe medicao para esta competencia
        existing = await self.db.execute(
            select(Measurement).where(
                Measurement.contrato_id == contract_id,
                Measurement.competencia == competencia,
                Measurement.ativo,
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Ja existe medicao para competencia {competencia} "
                f"no contrato {contract.numero_contrato}/{contract.ano_contrato}"
            )

        # Calcula valor baseado nos postos e alocacoes
        postos = await self._get_postos_por_contrato(contract_id)
        alocacoes = await self._get_alocacoes_ativas_por_contrato(contract_id)

        # Calcula dias uteis no periodo (simplificado: todos os dias)
        dias_periodo = (periodo_fim - periodo_inicio).days + 1

        # Valor bruto: soma do custo mensal dos postos proporcional ao periodo
        valor_bruto = Decimal("0")
        itens_medidos = []

        if postos:
            for post in postos:
                # Proporcional: monthly_cost * (dias_periodo / 30)
                custo_proporcional = Decimal(str(post.monthly_cost)) * Decimal(str(dias_periodo)) / Decimal("30")
                valor_bruto += custo_proporcional

                # Conta alocacoes ativas neste posto
                alocacoes_posto = [a for a in alocacoes if a.post_id == post.id]

                itens_medidos.append(
                    {
                        "descricao": f"{post.name} ({post.code})",
                        "unidade": "mes",
                        "quantidade": str(Decimal(str(dias_periodo)) / Decimal("30")),
                        "valor_unitario": str(Decimal(str(post.monthly_cost))),
                        "valor_total": str(custo_proporcional),
                        "headcount_previsto": post.required_headcount,
                        "headcount_alocado": len(alocacoes_posto),
                    }
                )
        else:
            # Sem postos: usa valor mensal do contrato
            valor_mensal = contract.valor_contrato / Decimal(str(contract.prazo_meses or 12))
            valor_bruto = valor_mensal * Decimal(str(dias_periodo)) / Decimal("30")
            itens_medidos.append(
                {
                    "descricao": f"Servicos - {contract.objeto_resumido or contract.objeto[:80]}",
                    "unidade": "mes",
                    "quantidade": str(Decimal(str(dias_periodo)) / Decimal("30")),
                    "valor_unitario": str(valor_mensal),
                    "valor_total": str(valor_bruto),
                }
            )

        # Proxima numeracao
        numero = len(contract.medicoes or []) + 1

        # Cria medicao
        measurement = Measurement(
            id=uuid4(),
            contrato_id=contract_id,
            numero_medicao=numero,
            competencia=competencia,
            tipo=MeasurementType.MENSAL.value,
            periodo_inicio=periodo_inicio,
            periodo_fim=periodo_fim,
            valor_bruto=valor_bruto,
            valor_retencoes=Decimal("0"),
            valor_glosas=Decimal("0"),
            valor_liquido=valor_bruto,
            status=MeasurementStatus.DRAFT.value,
            itens_medidos=itens_medidos,
            descricao_servicos=(
                f"Medicao #{numero} - {competencia} - {contract.numero_contrato}/{contract.ano_contrato}"
            ),
            created_by=user_id,
        )

        # Calcula retencoes padrao
        measurement.calcular_retencoes()

        self.db.add(measurement)
        await self.db.commit()
        await self.db.refresh(measurement)

        logger.info(
            "Medicao #%d gerada para contrato %s/%s - Competencia %s - Valor bruto: R$ %s",
            numero,
            contract.numero_contrato,
            contract.ano_contrato,
            competencia,
            valor_bruto,
        )

        return {
            "id": str(measurement.id),
            "contrato_id": str(contract_id),
            "numero_contrato": contract.numero_contrato,
            "numero_medicao": measurement.numero_medicao,
            "competencia": measurement.competencia,
            "periodo_inicio": measurement.periodo_inicio.isoformat(),
            "periodo_fim": measurement.periodo_fim.isoformat(),
            "valor_bruto": float(measurement.valor_bruto),
            "valor_retencoes": float(measurement.valor_retencoes),
            "valor_glosas": float(measurement.valor_glosas),
            "valor_liquido": float(measurement.valor_liquido),
            "status": measurement.status,
            "itens_medidos": measurement.itens_medidos,
            "postos_vinculados": len(postos),
            "alocacoes_ativas": len(alocacoes),
        }

    # ------------------------------------------------------------------ #
    #  3. Gerar fatura a partir de medicao                               #
    # ------------------------------------------------------------------ #

    async def gerar_fatura(
        self,
        medicao_id: UUID,
        user_id: UUID | None = None,
    ) -> dict:
        """
        Gera fatura (conta a receber + NFS-e) a partir de uma medicao aprovada.

        Integra com:
        - Modulo financeiro: cria conta a receber (ReceivableAccount)
        - Modulo fiscal: prepara/emite NFS-e via NfseMultiEmpresaService

        Ambas integracoes sao opcionais — se falharem, a fatura e retornada
        com dados stub e um aviso no log.

        Args:
            medicao_id: ID da medicao aprovada.
            user_id: ID do usuario.

        Returns:
            dict com dados da fatura (real quando integrado, stub quando nao).

        Raises:
            ValueError: Se medicao nao encontrada ou nao aprovada.
        """
        # ----- Busca medicao -----
        result = await self.db.execute(
            select(Measurement).where(
                Measurement.id == medicao_id,
                Measurement.ativo,
            )
        )
        measurement = result.scalar_one_or_none()

        if not measurement:
            raise ValueError(f"Medicao {medicao_id} nao encontrada")

        if not measurement.esta_aprovada:
            raise ValueError(
                f"Medicao #{measurement.numero_medicao} ({measurement.competencia}) "
                f"nao esta aprovada (status: {measurement.status}). "
                f"Aprove a medicao antes de gerar a fatura."
            )

        # ----- Busca contrato para dados complementares -----
        result = await self.db.execute(select(PublicContract).where(PublicContract.id == measurement.contrato_id))
        contract = result.scalar_one_or_none()

        # Dados comuns
        descricao = (
            f"Medicao #{measurement.numero_medicao} - {measurement.competencia} - "
            f"Contrato {contract.numero_contrato}/{contract.ano_contrato}"
            if contract
            else f"Medicao #{measurement.numero_medicao} - {measurement.competencia}"
        )
        data_emissao = date.today()
        data_vencimento = self._calcular_vencimento(measurement, contract)

        # Inicializa fatura com stubs
        fatura = {
            "id": str(uuid4()),  # ID provisorio — substituido se financeiro criar
            "status": "pendente_integracao",
            "medicao_id": str(measurement.id),
            "contrato_id": str(measurement.contrato_id),
            "numero_contrato": contract.numero_contrato if contract else None,
            "competencia": measurement.competencia,
            "valor_bruto": float(measurement.valor_bruto),
            "valor_retencoes": float(measurement.valor_retencoes or 0),
            "valor_liquido": float(measurement.valor_liquido),
            "cliente_cnpj": contract.orgao_cnpj if contract else None,
            "cliente_nome": contract.orgao_nome if contract else None,
            "descricao": descricao,
            "data_emissao": data_emissao.isoformat(),
            "data_vencimento": data_vencimento.isoformat() if data_vencimento else None,
            "nota_fiscal": {
                "status": "pendente",
                "numero": None,
                "mensagem": "NFS-e sera gerada apos integracao com modulo fiscal",
            },
            "conta_a_receber": {
                "status": "pendente",
                "id": None,
                "mensagem": "Conta a receber sera criada apos integracao com modulo financeiro",
            },
            "integracao_pendente": True,
            "mensagem": (
                "Fatura gerada em modo stub. Integracao com modulos financeiro e fiscal pendente de implementacao."
            ),
        }

        # ------------------------------------------------------------------ #
        #  TASK 1 — Integracao Financeira (Contas a Receber)                  #
        # ------------------------------------------------------------------ #
        receivable_ok = await self._criar_conta_a_receber(
            fatura,
            measurement,
            contract,
            descricao,
            data_emissao,
            data_vencimento,
            user_id,
        )

        # ------------------------------------------------------------------ #
        #  TASK 2 — Integracao Fiscal (NFS-e)                                 #
        # ------------------------------------------------------------------ #
        nfse_ok = await self._emitir_nfse(
            fatura,
            measurement,
            contract,
            descricao,
        )

        # Atualiza status geral da fatura
        if receivable_ok and nfse_ok:
            fatura["status"] = "integrada"
            fatura["integracao_pendente"] = False
            fatura["mensagem"] = "Fatura gerada com sucesso. Conta a receber criada e NFS-e preparada."
        elif receivable_ok:
            fatura["status"] = "parcial_financeiro"
            fatura["integracao_pendente"] = True
            fatura["mensagem"] = "Conta a receber criada. NFS-e pendente (ver nota_fiscal.mensagem)."
        elif nfse_ok:
            fatura["status"] = "parcial_fiscal"
            fatura["integracao_pendente"] = True
            fatura["mensagem"] = "NFS-e preparada. Conta a receber pendente (ver conta_a_receber.mensagem)."
        # else: mantém stubs originais

        logger.info(
            "Fatura gerada para medicao #%d do contrato %s - Valor: R$ %s - Status: %s",
            measurement.numero_medicao,
            contract.numero_contrato if contract else "N/A",
            measurement.valor_liquido,
            fatura["status"],
        )

        return fatura

    # ------------------------------------------------------------------ #
    #  Helpers de integracao (fatura)                                      #
    # ------------------------------------------------------------------ #

    async def _criar_conta_a_receber(
        self,
        fatura: dict,
        measurement: Measurement,
        contract: PublicContract | None,
        descricao: str,
        data_emissao: date,
        data_vencimento: date | None,
        user_id: UUID | None,
    ) -> bool:
        """
        Tenta criar conta a receber no modulo financeiro.

        Retorna True se criou com sucesso, False caso contrario.
        Atualiza ``fatura["conta_a_receber"]`` in-place.
        """
        try:
            from modules.financial.models.receivable_account import (
                ReceivableAccount,
                ReceivableStatus,
                ReceivableType,
            )

            logger.info(
                "[erp_fatura] Criando conta a receber para medicao #%d - R$ %s",
                measurement.numero_medicao,
                measurement.valor_liquido,
            )

            # Competencia como date (primeiro dia do mes)
            comp_parts = measurement.competencia.split("-")
            competence_date = date(int(comp_parts[0]), int(comp_parts[1]), 1)

            valor_liquido = Decimal(str(measurement.valor_liquido))

            receivable = ReceivableAccount(
                description=descricao,
                receivable_type=ReceivableType.AVULSA.value,
                status=ReceivableStatus.PENDENTE.value,
                gross_value=measurement.valor_bruto,
                net_value=valor_liquido,
                paid_value=Decimal("0"),
                discount_value=Decimal("0"),
                addition_value=Decimal("0"),
                interest_value=Decimal("0"),
                penalty_value=Decimal("0"),
                interest_rate=Decimal("1"),
                penalty_rate=Decimal("2"),
                grace_days=0,
                issue_date=data_emissao,
                entry_date=data_emissao,
                due_date=data_vencimento or (data_emissao + timedelta(days=_DEFAULT_PAYMENT_DAYS)),
                competence_date=competence_date,
                total_installments=1,
                is_recurring=False,
                cost_center="licitacoes",
                notes=(
                    f"Gerado automaticamente via ERP Integration — "
                    f"Medicao #{measurement.numero_medicao} ({measurement.competencia}) | "
                    f"Contrato {contract.numero_contrato}/{contract.ano_contrato}"
                    if contract
                    else (
                        f"Gerado automaticamente via ERP Integration — "
                        f"Medicao #{measurement.numero_medicao} ({measurement.competencia})"
                    )
                ),
                tags=["licitacao", "medicao", measurement.competencia],
                # condominio_id — NOT NULL no banco; usa placeholder ate integrar com multi-empresa
                condominio_id=uuid4()
                if not hasattr(contract, "empresa_id") or not getattr(contract, "empresa_id", None)
                else contract.empresa_id,
            )

            if user_id:
                receivable.created_by = user_id

            self.db.add(receivable)
            await self.db.flush()  # Obtem ID sem commit (commit sera feito pelo caller se necessario)

            receivable_id = str(receivable.id)

            logger.info(
                "[erp_fatura] Conta a receber criada: %s - Vencimento: %s - R$ %s",
                receivable_id,
                receivable.due_date,
                valor_liquido,
            )

            fatura["conta_a_receber"] = {
                "status": "criada",
                "id": receivable_id,
                "code": getattr(receivable, "code", None),
                "due_date": receivable.due_date.isoformat(),
                "net_value": float(valor_liquido),
                "mensagem": "Conta a receber criada com sucesso no modulo financeiro.",
            }
            # Substitui ID provisorio pelo real do receivable
            fatura["id"] = receivable_id

            await self.db.commit()
            return True

        except Exception as exc:
            logger.warning(
                "[erp_fatura] Falha ao criar conta a receber para medicao #%d: %s",
                measurement.numero_medicao,
                exc,
            )
            fatura["conta_a_receber"] = {
                "status": "erro",
                "id": None,
                "mensagem": f"Falha ao criar conta a receber: {exc}",
            }
            # Rollback parcial para nao contaminar a sessao
            with contextlib.suppress(Exception):
                await self.db.rollback()
            return False

    async def _emitir_nfse(
        self,
        fatura: dict,
        measurement: Measurement,
        contract: PublicContract | None,
        descricao: str,
    ) -> bool:
        """
        Tenta gerar NFS-e via modulo fiscal (NfseMultiEmpresaService).

        Retorna True se preparou/emitiu com sucesso, False caso contrario.
        Atualiza ``fatura["nota_fiscal"]`` e ``measurement.nota_fiscal_*`` in-place.
        """
        try:
            from modules.fiscal.services.nfse_multi_empresa_service import (
                DadosNFSeMultiEmpresa,
                NfseMultiEmpresaService,
            )

            logger.info(
                "[erp_fatura] Preparando NFS-e para medicao #%d - R$ %s",
                measurement.numero_medicao,
                measurement.valor_liquido,
            )

            # Determina tipo de servico para selecao de empresa
            tipo_servico = "vigilancia"  # default para licitacoes de seguranca
            if contract and contract.objeto:
                objeto_lower = contract.objeto.lower()
                if any(kw in objeto_lower for kw in ("eletron", "remota", "cftv", "monitoramento", "alarme")):
                    tipo_servico = "seguranca_eletronica"

            # Extrai ano/mes da competencia
            comp_parts = measurement.competencia.split("-")
            comp_ano = int(comp_parts[0])
            comp_mes = int(comp_parts[1])

            dados_nfse = DadosNFSeMultiEmpresa(
                tipo_servico=tipo_servico,
                descricao_servico=measurement.descricao_servicos or descricao,
                valor_servico=float(measurement.valor_liquido),
                tomador_cnpj_cpf=contract.orgao_cnpj if contract and contract.orgao_cnpj else "00000000000000",
                tomador_razao_social=contract.orgao_nome if contract else "Orgao Publico",
                tomador_email=None,
                competencia_ano=comp_ano,
                competencia_mes=comp_mes,
            )

            nfse_service = NfseMultiEmpresaService()
            resultado = nfse_service.preparar_dados_nfse(dados_nfse)

            if resultado.sucesso:
                # Atualiza dados da nota fiscal na medicao
                measurement.nota_fiscal_numero = resultado.numero_rps or resultado.protocolo
                measurement.nota_fiscal_data = date.today()

                # Persiste atualizacao da medicao
                try:
                    await self.db.commit()
                except Exception:
                    await self.db.rollback()

                logger.info(
                    "[erp_fatura] NFS-e preparada com sucesso - Empresa: %s - Liminares: %s",
                    resultado.empresa_emissora,
                    resultado.liminares_aplicadas,
                )

                fatura["nota_fiscal"] = {
                    "status": "preparada",
                    "numero": resultado.numero_rps,
                    "protocolo": resultado.protocolo,
                    "empresa_emissora": resultado.empresa_emissora,
                    "ambiente": resultado.ambiente,
                    "valor_servico": resultado.valor_servico,
                    "valor_liquido_nfse": resultado.valor_liquido,
                    "pis": resultado.pis,
                    "cofins": resultado.cofins,
                    "iss": resultado.iss,
                    "inss_retido": resultado.inss_retido,
                    "liminares_aplicadas": resultado.liminares_aplicadas,
                    "xml_gerado": resultado.xml_gerado is not None,
                    "mensagem": resultado.mensagem,
                }
                return True
            else:
                # NFS-e nao pode ser emitida (ex: CNPJ em abertura)
                logger.warning(
                    "[erp_fatura] NFS-e nao emitida para medicao #%d: %s",
                    measurement.numero_medicao,
                    resultado.mensagem,
                )
                fatura["nota_fiscal"] = {
                    "status": "indisponivel",
                    "numero": None,
                    "empresa_emissora": resultado.empresa_emissora,
                    "ambiente": resultado.ambiente,
                    "valor_servico": resultado.valor_servico,
                    "valor_liquido_nfse": resultado.valor_liquido,
                    "pis": resultado.pis,
                    "cofins": resultado.cofins,
                    "iss": resultado.iss,
                    "inss_retido": resultado.inss_retido,
                    "liminares_aplicadas": resultado.liminares_aplicadas,
                    "mensagem": resultado.mensagem,
                }
                return False

        except Exception as exc:
            logger.warning(
                "[erp_fatura] Falha ao gerar NFS-e para medicao #%d: %s",
                measurement.numero_medicao,
                exc,
            )
            fatura["nota_fiscal"] = {
                "status": "erro",
                "numero": None,
                "mensagem": f"Falha ao gerar NFS-e: {exc}",
            }
            return False

    @staticmethod
    def _calcular_vencimento(
        measurement: Measurement,
        contract: PublicContract | None,
    ) -> date:
        """
        Calcula data de vencimento da fatura.

        Usa data_aprovacao da medicao + prazo do contrato (ou 30 dias padrao).
        """
        base = measurement.data_aprovacao or date.today()

        # Se contrato tem prazo de pagamento definido, usa-o
        prazo_dias = _DEFAULT_PAYMENT_DAYS
        if contract:
            prazo = getattr(contract, "prazo_pagamento_dias", None)
            if prazo and isinstance(prazo, int) and prazo > 0:
                prazo_dias = prazo

        return base + timedelta(days=prazo_dias)

    # ------------------------------------------------------------------ #
    #  4. Status de integracao                                           #
    # ------------------------------------------------------------------ #

    async def status_integracao(self, contract_id: UUID) -> dict:
        """
        Retorna o status completo de integracao de um contrato publico.

        Mostra o que ja foi criado em cada modulo (operacional, medicoes,
        faturas) e quais passos estao pendentes.

        Args:
            contract_id: ID do contrato publico.

        Returns:
            dict com status detalhado da integracao.

        Raises:
            ValueError: Se contrato nao encontrado.
        """
        # Busca contrato
        result = await self.db.execute(
            select(PublicContract)
            .options(selectinload(PublicContract.medicoes))
            .where(PublicContract.id == contract_id)
        )
        contract = result.scalar_one_or_none()

        if not contract:
            raise ValueError(f"Contrato {contract_id} nao encontrado")

        # Busca postos operacionais vinculados
        postos = await self._get_postos_por_contrato(contract_id)

        # Busca alocacoes ativas
        alocacoes = await self._get_alocacoes_ativas_por_contrato(contract_id)

        # Medicoes
        medicoes = contract.medicoes or []
        medicoes_por_status = {}
        for m in medicoes:
            medicoes_por_status.setdefault(m.status, []).append(
                {
                    "id": str(m.id),
                    "numero": m.numero_medicao,
                    "competencia": m.competencia,
                    "valor_bruto": float(m.valor_bruto),
                    "valor_liquido": float(m.valor_liquido),
                }
            )

        # Determina etapas concluidas e pendentes
        tem_postos = len(postos) > 0
        tem_alocacoes = len(alocacoes) > 0
        tem_medicoes = len(medicoes) > 0
        tem_medicoes_aprovadas = any(m.esta_aprovada for m in medicoes)

        # Monta headcount info por posto
        postos_info = []
        for post in postos:
            aloc_posto = [a for a in alocacoes if a.post_id == post.id]
            postos_info.append(
                {
                    "id": post.id,
                    "code": post.code,
                    "name": post.name,
                    "post_type": post.post_type,
                    "shift_type": post.shift_type,
                    "status": post.status,
                    "required_headcount": post.required_headcount,
                    "current_headcount": len(aloc_posto),
                    "monthly_cost": post.monthly_cost,
                    "preenchido": len(aloc_posto) >= post.required_headcount,
                }
            )

        total_headcount_necessario = sum(p.required_headcount for p in postos)
        total_headcount_alocado = len(alocacoes)

        etapas = {
            "contrato_licitacao": {
                "concluido": True,
                "detalhes": {
                    "id": str(contract.id),
                    "numero": f"{contract.numero_contrato}/{contract.ano_contrato}",
                    "orgao": contract.orgao_nome,
                    "status": contract.status,
                    "valor": float(contract.valor_contrato),
                    "vigencia_inicio": (
                        contract.data_vigencia_inicio.isoformat() if contract.data_vigencia_inicio else None
                    ),
                    "vigencia_fim": (contract.data_vigencia_fim.isoformat() if contract.data_vigencia_fim else None),
                },
            },
            "postos_operacionais": {
                "concluido": tem_postos,
                "quantidade": len(postos),
                "detalhes": postos_info,
            },
            "alocacoes": {
                "concluido": tem_alocacoes,
                "total_necessario": total_headcount_necessario,
                "total_alocado": total_headcount_alocado,
                "percentual_preenchimento": (
                    round(total_headcount_alocado / total_headcount_necessario * 100, 1)
                    if total_headcount_necessario > 0
                    else 0
                ),
            },
            "medicoes": {
                "concluido": tem_medicoes,
                "total": len(medicoes),
                "por_status": medicoes_por_status,
                "valor_total_bruto": sum(float(m.valor_bruto) for m in medicoes),
                "valor_total_liquido": sum(float(m.valor_liquido) for m in medicoes),
            },
            "faturas": {
                "concluido": tem_medicoes_aprovadas,
                "mensagem": (
                    "Integracao com modulo financeiro ativa (gerar_fatura cria conta a receber)"
                    if tem_medicoes_aprovadas
                    else "Nenhuma medicao aprovada para gerar fatura"
                ),
                "medicoes_aptas": sum(1 for m in medicoes if m.esta_aprovada),
            },
            "nfse": {
                "concluido": any(m.nota_fiscal_numero for m in medicoes),
                "mensagem": (
                    "NFS-e emitida para medicoes com nota fiscal"
                    if any(m.nota_fiscal_numero for m in medicoes)
                    else "Integracao com NFS-e ativa (gerar_fatura prepara NFS-e automaticamente)"
                ),
            },
        }

        # Calcula progresso geral
        etapas_total = 6
        etapas_concluidas = sum(1 for e in etapas.values() if e.get("concluido", False))

        # Pendencias
        pendencias = []
        if not tem_postos:
            pendencias.append("Criar postos operacionais (converter contrato)")
        if tem_postos and not tem_alocacoes:
            pendencias.append("Alocar funcionarios nos postos")
        if tem_postos and total_headcount_alocado < total_headcount_necessario:
            vagas = total_headcount_necessario - total_headcount_alocado
            pendencias.append(f"Preencher {vagas} vaga(s) nos postos")
        if not tem_medicoes:
            pendencias.append("Gerar primeira medicao")
        if tem_medicoes and not tem_medicoes_aprovadas:
            pendencias.append("Aprovar medicoes pendentes")
        if tem_medicoes_aprovadas:
            pendencias.append("Gerar faturas para medicoes aprovadas (integracao financeira)")
        pendencias.append("Configurar emissao de NFS-e (integracao fiscal)")

        return {
            "contrato_id": str(contract.id),
            "numero_contrato": f"{contract.numero_contrato}/{contract.ano_contrato}",
            "orgao": contract.orgao_nome,
            "progresso": {
                "etapas_concluidas": etapas_concluidas,
                "etapas_total": etapas_total,
                "percentual": round(etapas_concluidas / etapas_total * 100, 1),
            },
            "etapas": etapas,
            "pendencias": pendencias,
        }

    # ------------------------------------------------------------------ #
    #  5. Contrato -> CRM (Comercial)                                    #
    # ------------------------------------------------------------------ #

    async def contrato_para_crm(self, contract_id: UUID) -> dict:
        """
        Contrato Publico -> Modulo CRM (Comercial).

        Cria ou vincula um registro de cliente no CRM a partir dos dados
        do orgao contratante do contrato publico.

        Args:
            contract_id: ID do contrato publico.

        Returns:
            dict com status da integracao e dados do cliente CRM.

        Raises:
            ValueError: Se contrato nao encontrado.
        """
        contract = await self._get_contract(contract_id)

        try:
            from modules.comercial.crm.services import ClientService

            client_service = ClientService(self.db)

            # Tenta encontrar cliente existente pelo CNPJ do orgao
            cliente_existente = None
            if contract.orgao_cnpj:
                cliente_existente = await client_service.buscar_por_cnpj(contract.orgao_cnpj)

            if cliente_existente:
                logger.info(
                    "CRM: cliente existente encontrado para orgao %s (CNPJ %s): %s",
                    contract.orgao_nome,
                    contract.orgao_cnpj,
                    cliente_existente.id,
                )
                return {
                    "status": "vinculado",
                    "cliente_id": str(cliente_existente.id),
                    "cliente_nome": getattr(cliente_existente, "nome", None)
                    or getattr(cliente_existente, "razao_social", None),
                    "contrato_id": str(contract.id),
                    "numero_contrato": f"{contract.numero_contrato}/{contract.ano_contrato}",
                    "mensagem": "Cliente CRM existente vinculado ao contrato.",
                }

            # Cria novo cliente a partir dos dados do orgao
            novo_cliente = await client_service.criar_cliente(
                {
                    "razao_social": contract.orgao_nome,
                    "cnpj": contract.orgao_cnpj,
                    "uf": contract.orgao_uf,
                    "tipo": "orgao_publico",
                    "origem": "licitacao",
                    "observacoes": (
                        f"Cliente criado automaticamente a partir do contrato "
                        f"{contract.numero_contrato}/{contract.ano_contrato} (licitacao)"
                    ),
                }
            )

            await self.db.commit()

            logger.info(
                "CRM: novo cliente criado para orgao %s (CNPJ %s): %s",
                contract.orgao_nome,
                contract.orgao_cnpj,
                novo_cliente.id,
            )

            return {
                "status": "criado",
                "cliente_id": str(novo_cliente.id),
                "cliente_nome": contract.orgao_nome,
                "contrato_id": str(contract.id),
                "numero_contrato": f"{contract.numero_contrato}/{contract.ano_contrato}",
                "mensagem": "Novo cliente CRM criado e vinculado ao contrato.",
            }

        except ImportError as e:
            logger.warning("CRM integration not available (module not found): %s", e)
            return {
                "status": "pendente_integracao",
                "contrato_id": str(contract.id),
                "numero_contrato": f"{contract.numero_contrato}/{contract.ano_contrato}",
                "orgao_nome": contract.orgao_nome,
                "orgao_cnpj": contract.orgao_cnpj,
                "mensagem": f"Modulo CRM nao disponivel: {e}",
            }
        except Exception as e:
            logger.warning("CRM integration failed for contract %s: %s", contract_id, e)
            return {
                "status": "pendente_integracao",
                "contrato_id": str(contract.id),
                "numero_contrato": f"{contract.numero_contrato}/{contract.ano_contrato}",
                "orgao_nome": contract.orgao_nome,
                "orgao_cnpj": contract.orgao_cnpj,
                "mensagem": f"Falha na integracao CRM: {e}",
            }

    async def _get_contract(self, contract_id: UUID) -> PublicContract:
        """Busca contrato publico por ID. Raises ValueError se nao encontrado."""
        result = await self.db.execute(
            select(PublicContract).where(
                PublicContract.id == contract_id,
                PublicContract.ativo,
            )
        )
        contract = result.scalar_one_or_none()
        if not contract:
            raise ValueError(f"Contrato {contract_id} nao encontrado ou inativo")
        return contract

    # ------------------------------------------------------------------ #
    #  Metodos auxiliares (privados)                                      #
    # ------------------------------------------------------------------ #

    async def _get_postos_por_contrato(self, contract_id: UUID) -> list[Post]:
        """Busca postos operacionais vinculados a um contrato."""
        result = await self.db.execute(
            select(Post).where(
                Post.contract_id == str(contract_id),
                Post.is_active,
            )
        )
        return list(result.scalars().all())

    async def _get_alocacoes_ativas_por_contrato(self, contract_id: UUID) -> list[Allocation]:
        """Busca alocacoes ativas nos postos de um contrato."""
        result = await self.db.execute(
            select(Allocation)
            .join(Post, Allocation.post_id == Post.id)
            .where(
                Post.contract_id == str(contract_id),
                Post.is_active,
                Allocation.status == AllocationStatus.ACTIVE.value,
                Allocation.is_active,
            )
        )
        return list(result.scalars().all())

    async def _next_post_code(self) -> int:
        """Retorna proximo numero sequencial para codigo de posto."""
        result = await self.db.execute(select(func.count(Post.id)))
        count = result.scalar() or 0
        return count + 1

    async def _criar_posto(
        self,
        contract: PublicContract,
        code: str,
        config: dict,
        user_id: UUID | None = None,
    ) -> Post:
        """Cria um posto de trabalho vinculado ao contrato."""
        post = Post(
            id=str(uuid4()),
            code=code,
            name=config.get("name", f"Posto {code}"),
            description=(
                f"Posto criado a partir do contrato "
                f"{contract.numero_contrato}/{contract.ano_contrato} - "
                f"{contract.orgao_nome}"
            ),
            post_type=config.get("post_type", PostType.PORTEIRO.value),
            status=PostStatus.ACTIVE.value,
            shift_type=config.get("shift_type", ShiftType.DIURNO.value),
            contract_id=str(contract.id),
            client_id=None,
            address=config.get("address"),
            city=config.get("city"),
            state=config.get("state", contract.orgao_uf),
            required_headcount=config.get("headcount", 1),
            current_headcount=0,
            hourly_rate=config.get("hourly_rate", 0.0),
            monthly_cost=config.get("monthly_cost", 0.0),
            requires_armed=config.get("requires_armed", False),
            requires_vehicle=config.get("requires_vehicle", False),
            notes=(
                f"Origem: Licitacao - Contrato {contract.numero_contrato}/{contract.ano_contrato} | "
                f"Orgao: {contract.orgao_nome} | "
                f"Vigencia: {contract.data_vigencia_inicio} a {contract.data_vigencia_fim}"
            ),
            created_by=str(user_id) if user_id else None,
        )

        self.db.add(post)
        return post
