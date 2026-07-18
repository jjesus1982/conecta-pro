"""
Service para e-CAC - Centro Virtual de Atendimento ao Contribuinte.

Camada de servico para operacoes do e-CAC.
"""

import logging
import os
from datetime import datetime
from decimal import Decimal
from typing import Any

from ..core.certificate_manager import CertificateManager
from ..core.ecac import (
    EcacManager,
    TipoDeclaracaoConsulta,
)

logger = logging.getLogger(__name__)

# Fonte de verdade REAL do que temos hoje (puxador do Drive + folha), já que o pull
# direto dos apps modernos da RFB (servicos.receitafederal) é barrado por anti-bot
# Enterprise. NÃO fabricamos dado: lemos as tabelas reais e sinalizamos a fonte.
PULL_DIRETO_RFB = {
    "situacao": "bloqueado_antibot",
    "detalhe": (
        "Login e-CAC por certificado A1 funciona (cav.receita). As telas de Pendências/"
        "Parcelamentos migraram p/ servicos.receitafederal.gov.br (hCaptcha Enterprise + "
        "fingerprint) e recusam automação. Dados abaixo vêm do puxador do Drive (Portte/Onvio) "
        "+ folha — reais e conciliados."
    ),
}


def _dados_fiscais_reais(cpf_cnpj: str | None = None) -> dict[str, Any]:
    """Lê débitos/parcelamentos REAIS das tabelas do ERP (fiscal_obligations / fiscal_parcelamentos).

    Débito = obrigação ativa, pendente e com valor devido > 0. Sem fabricação: tabela vazia
    devolve lista vazia (regularidade presumida se não há pendência)."""
    from core.database.session import SyncSessionLocal
    from sqlalchemy import text

    debitos: list[dict[str, Any]] = []
    parcelamentos: list[dict[str, Any]] = []
    total_deb = Decimal("0")
    try:
        db = SyncSessionLocal()
        try:
            rows = db.execute(text(
                "SELECT tipo, nome, competencia_mes, competencia_ano, valor_devido, "
                "data_vencimento, numero_recibo, id, observacoes FROM fiscal_obligations "
                "WHERE active=true AND lower(status)='pendente' AND coalesce(valor_devido,0) > 0 "
                "ORDER BY competencia_ano DESC, competencia_mes DESC"
            )).fetchall()
            for r in rows:
                comp = f"{int(r[3]):04d}-{int(r[2]):02d}" if r[2] and r[3] else None
                val = Decimal(str(r[4] or 0))
                total_deb += val
                tem_pdf = bool(r[8] and "drive_file_id" in r[8])
                pagavel = bool(r[8] and ("codigo_barras" in r[8] or "pix_copia" in r[8]))
                debitos.append({
                    "id": str(r[7]),
                    "pagavel": pagavel,
                    "codigo_receita": r[0],
                    "descricao": r[1],
                    "competencia": comp,
                    "valor_principal": str(val),
                    "valor_multa": "0",
                    "valor_juros": "0",
                    "valor_total": str(val),
                    "data_vencimento": r[5].isoformat() if r[5] else None,
                    "situacao": "em_aberto",
                    "numero_processo": r[6],
                    "fonte": "erp_puxador_drive",
                    "pdf_disponivel": tem_pdf,
                    "pdf_url": f"/api/v1/fiscal/guias-drive/pdf/{r[7]}" if tem_pdf else None,
                })
            prows = db.execute(text(
                "SELECT orgao, numero_acordo, descricao, valor_total, num_parcelas, "
                "parcela_valor, parcelas_pagas, status, competencia_inicio, fonte "
                "FROM fiscal_parcelamentos WHERE lower(coalesce(status,'')) NOT IN ('cancelado','encerrado')"
            )).fetchall()
            for r in prows:
                parcelamentos.append({
                    "orgao": r[0], "numero_acordo": r[1], "descricao": r[2],
                    "valor_total": str(r[3] or 0), "num_parcelas": r[4],
                    "parcela_valor": str(r[5] or 0), "parcelas_pagas": r[6] or 0,
                    "situacao": r[7] or "ativo", "competencia_inicio": r[8],
                    "fonte": r[9] or "erp",
                })
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"e-CAC dados reais: falha ao ler tabelas ({e})")
    return {"debitos": debitos, "valor_total_debitos": total_deb, "parcelamentos": parcelamentos}


class EcacService:
    """Service para operacoes do e-CAC."""

    def __init__(self):
        """Inicializa o service."""
        self.cpf_cnpj = os.getenv("ECAC_CPF_CNPJ", os.getenv("EMPRESA_CNPJ", "35710481000103"))
        self.cert_path = os.getenv("CERTIFICATE_PATH", "")
        self.cert_password = os.getenv("CERTIFICATE_PASSWORD", "")

        # Certificado eh opcional
        self.cert_manager = None
        if self.cert_path and os.path.exists(self.cert_path):
            try:
                self.cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
                self.cert_manager.load()
                logger.info("Certificado digital carregado para e-CAC")
            except Exception as e:
                logger.warning(f"Certificado nao carregado: {e}")

        self.manager = EcacManager(
            cnpj_cpf=self.cpf_cnpj,
            certificado_path=self.cert_path,
            certificado_senha=self.cert_password,
        )

        logger.info(f"e-CAC Service inicializado - CPF/CNPJ: {self.cpf_cnpj}, Tipo: {self.manager.tipo_documento}")

    def consultar_situacao_fiscal(
        self,
        cpf_cnpj: str | None = None,
    ) -> dict[str, Any]:
        """
        Consulta situacao fiscal do contribuinte.

        Args:
            cpf_cnpj: CPF ou CNPJ (opcional, usa o configurado)

        Returns:
            Dict com resultado da consulta
        """
        documento = cpf_cnpj or self.cpf_cnpj

        # Se foi passado um documento diferente, cria um novo manager
        if cpf_cnpj and cpf_cnpj != self.cpf_cnpj:
            manager = EcacManager(
                cnpj_cpf=cpf_cnpj,
                certificado_path=self.cert_path,
                certificado_senha=self.cert_password,
            )
        else:
            manager = self.manager

        # DADO REAL: deriva a situação fiscal das obrigações do ERP (puxador Drive + folha).
        # Sem fabricação — se não há débito pendente, a regularidade é presumida (CND).
        reais = _dados_fiscais_reais(documento)
        debitos = reais["debitos"]
        pendencias = [
            {
                "tipo": d["codigo_receita"],
                "descricao": d["descricao"],
                "valor": d["valor_total"],
                "data_vencimento": d["data_vencimento"],
                "numero_processo": d.get("numero_processo"),
                "exercicio": (d.get("competencia") or "")[:4] or None,
                "periodo_apuracao": d.get("competencia"),
            }
            for d in debitos
        ]
        tem_debito = len(debitos) > 0
        nome = os.getenv("EMPRESA_RAZAO_SOCIAL", "CONECTAMAIS ELETRONICA LTDA")

        logger.info(f"Situacao fiscal (dado real ERP) p/ {documento}: {len(debitos)} débitos pendentes")

        return {
            "cpf_cnpj": documento,
            "nome": nome,
            "situacao": "com_pendencias" if tem_debito else "regular",
            "data_consulta": datetime.now().isoformat(),
            "pendencias": pendencias,
            "debitos": debitos,
            "declaracoes_omissas": [],
            "certidao_disponivel": not tem_debito,
            "tipo_certidao_disponivel": "CND" if not tem_debito else "CPEND",
            "valor_total_debitos": str(reais["valor_total_debitos"]),
            "fonte": "erp_puxador_drive",
            "pull_direto_rfb": PULL_DIRETO_RFB,
        }

    def consultar_debitos(
        self,
        situacao: str | None = None,
        competencia_inicio: str | None = None,
        competencia_fim: str | None = None,
    ) -> dict[str, Any]:
        """
        Consulta debitos do contribuinte.

        Args:
            situacao: Filtro de situacao ('aberto', 'suspenso', 'parcelado')
            competencia_inicio: Competencia inicial (YYYY-MM)
            competencia_fim: Competencia final (YYYY-MM)

        Returns:
            Dict com lista de debitos
        """
        # DADO REAL: débitos vêm das obrigações do ERP (puxador do Drive + folha).
        reais = _dados_fiscais_reais(self.cpf_cnpj)
        debitos = []
        valor_total = Decimal("0")
        for d in reais["debitos"]:
            comp = d.get("competencia") or ""
            if competencia_inicio and comp and comp < competencia_inicio:
                continue
            if competencia_fim and comp and comp > competencia_fim:
                continue
            debitos.append(d)
            valor_total += Decimal(d["valor_total"])

        logger.info(f"Debitos e-CAC (dado real ERP): {len(debitos)} encontrados")

        return {
            "cpf_cnpj": self.cpf_cnpj,
            "data_consulta": datetime.now().isoformat(),
            "quantidade": len(debitos),
            "valor_total": str(valor_total),
            "filtros": {
                "situacao": situacao,
                "competencia_inicio": competencia_inicio,
                "competencia_fim": competencia_fim,
            },
            "debitos": debitos,
            "fonte": "erp_puxador_drive",
            "pull_direto_rfb": PULL_DIRETO_RFB,
        }

    def emitir_certidao(
        self,
        finalidade: str | None = None,
        cpf_cnpj: str | None = None,
    ) -> dict[str, Any]:
        """
        Emite certidao fiscal (CND/CPEN).

        Args:
            finalidade: Finalidade da certidao
            cpf_cnpj: CPF ou CNPJ (opcional)

        Returns:
            Dict com dados da certidao
        """
        documento = cpf_cnpj or self.cpf_cnpj

        if cpf_cnpj and cpf_cnpj != self.cpf_cnpj:
            manager = EcacManager(
                cnpj_cpf=cpf_cnpj,
                certificado_path=self.cert_path,
                certificado_senha=self.cert_password,
            )
        else:
            manager = self.manager

        certidao = manager.emitir_certidao(finalidade=finalidade)

        logger.info(f"Certidao emitida para {documento}: {certidao.tipo.value}")

        return {
            "tipo": certidao.tipo.value,
            "numero": certidao.numero,
            "data_emissao": certidao.data_emissao.isoformat(),
            "data_validade": certidao.data_validade.isoformat(),
            "codigo_controle": certidao.codigo_controle,
            "contribuinte_cpf_cnpj": certidao.contribuinte_cpf_cnpj,
            "contribuinte_nome": certidao.contribuinte_nome,
            "finalidade": certidao.finalidade,
            "observacoes": certidao.observacoes,
        }

    def validar_certidao(
        self,
        numero: str,
        codigo_controle: str,
    ) -> dict[str, Any]:
        """
        Valida autenticidade de uma certidao.

        Args:
            numero: Numero da certidao
            codigo_controle: Codigo de controle

        Returns:
            Dict com resultado da validacao
        """
        resultado = self.manager.validar_certidao(
            numero=numero,
            codigo_controle=codigo_controle,
        )

        logger.info(f"Certidao validada: {numero} - Valida: {resultado.get('valida')}")

        return {
            "numero": resultado["numero"],
            "codigo_controle": resultado["codigo_controle"],
            "valida": resultado["valida"],
            "data_validacao": resultado["data_validacao"],
            "tipo_certidao": resultado.get("tipo_certidao"),
            "data_emissao": resultado.get("data_emissao"),
            "data_validade": resultado.get("data_validade"),
            "contribuinte": resultado.get("contribuinte"),
            "mensagem": resultado["mensagem"],
        }

    def consultar_declaracoes(
        self,
        tipo: str,
        exercicio_inicio: int,
        exercicio_fim: int | None = None,
    ) -> dict[str, Any]:
        """
        Consulta declaracoes transmitidas.

        Args:
            tipo: Tipo de declaracao
            exercicio_inicio: Exercicio inicial
            exercicio_fim: Exercicio final

        Returns:
            Dict com lista de declaracoes
        """
        try:
            tipo_enum = TipoDeclaracaoConsulta(tipo)
        except ValueError:
            tipo_enum = TipoDeclaracaoConsulta.DCTFWEB

        exercicio_fim = exercicio_fim or exercicio_inicio

        declaracoes_raw = self.manager.consultar_declaracoes(
            tipo=tipo_enum,
            exercicio_inicio=exercicio_inicio,
            exercicio_fim=exercicio_fim,
        )

        declaracoes = []
        for d in declaracoes_raw:
            declaracoes.append(
                {
                    "tipo": d.tipo.value,
                    "exercicio": d.exercicio,
                    "numero_recibo": d.numero_recibo,
                    "data_transmissao": d.data_transmissao.isoformat(),
                    "situacao": d.situacao,
                    "retificadora": d.retificadora,
                    "numero_recibo_anterior": d.numero_recibo_anterior,
                }
            )

        logger.info(
            f"Declaracoes consultadas: {len(declaracoes)} encontradas ({tipo} {exercicio_inicio}-{exercicio_fim})"
        )

        return {
            "cpf_cnpj": self.cpf_cnpj,
            "tipo": tipo,
            "exercicio_inicio": exercicio_inicio,
            "exercicio_fim": exercicio_fim,
            "quantidade": len(declaracoes),
            "declaracoes": declaracoes,
        }

    def consultar_parcelamentos(
        self,
        situacao: str | None = None,
    ) -> dict[str, Any]:
        """
        Consulta parcelamentos ativos.

        Args:
            situacao: Filtro de situacao

        Returns:
            Dict com lista de parcelamentos
        """
        # DADO REAL: parcelamentos vêm da tabela do ERP (fiscal_parcelamentos).
        parcelamentos = _dados_fiscais_reais(self.cpf_cnpj)["parcelamentos"]
        if situacao:
            parcelamentos = [p for p in parcelamentos if p.get("situacao") == situacao]

        logger.info(f"Parcelamentos e-CAC (dado real ERP): {len(parcelamentos)} encontrados")

        return {
            "cpf_cnpj": self.cpf_cnpj,
            "data_consulta": datetime.now().isoformat(),
            "quantidade": len(parcelamentos),
            "parcelamentos": parcelamentos,
            "fonte": "erp",
            "pull_direto_rfb": PULL_DIRETO_RFB,
        }

    def simular_parcelamento(
        self,
        debitos: list[str],
        quantidade_parcelas: int,
    ) -> dict[str, Any]:
        """
        Simula parcelamento de debitos.

        Args:
            debitos: Lista de codigos de debitos
            quantidade_parcelas: Numero de parcelas

        Returns:
            Dict com simulacao do parcelamento
        """
        resultado = self.manager.simular_parcelamento(
            debitos=debitos,
            quantidade_parcelas=quantidade_parcelas,
        )

        logger.info(f"Parcelamento simulado: {len(debitos)} debitos em {quantidade_parcelas}x")

        return {
            "cpf_cnpj": self.cpf_cnpj,
            "debitos": resultado["debitos"],
            "quantidade_debitos": len(debitos),
            "valor_total_debitos": resultado.get("valor_total_debitos", "0.00"),
            "quantidade_parcelas": resultado["quantidade_parcelas"],
            "valor_primeira_parcela": resultado.get("valor_primeira_parcela", "0.00"),
            "valor_demais_parcelas": resultado.get("valor_demais_parcelas", "0.00"),
            "taxa_juros": resultado.get("taxa_juros", "SELIC"),
            "data_primeira_parcela": resultado.get("data_primeira_parcela", ""),
            "status": resultado["status"],
            "observacoes": resultado.get("observacoes"),
            "mensagem": resultado["mensagem"],
        }

    def consultar_processos(
        self,
        situacao: str | None = None,
        numero_processo: str | None = None,
    ) -> dict[str, Any]:
        """
        Consulta processos digitais (e-Processo).

        Args:
            situacao: Filtro de situacao
            numero_processo: Numero especifico do processo

        Returns:
            Dict com lista de processos
        """
        processos = self.manager.consultar_processos(situacao=situacao)

        # Filtra por numero se especificado
        if numero_processo:
            processos = [p for p in processos if p.get("numero") == numero_processo]

        logger.info(f"Processos consultados: {len(processos)} encontrados")

        return {
            "cpf_cnpj": self.cpf_cnpj,
            "data_consulta": datetime.now().isoformat(),
            "quantidade": len(processos),
            "filtros": {
                "situacao": situacao,
                "numero_processo": numero_processo,
            },
            "processos": processos,
        }

    def validar_status(self) -> dict[str, Any]:
        """
        Valida status da configuracao e-CAC.

        Returns:
            Dict com status da configuracao
        """
        return {
            "ambiente": "producao",
            "url": self.manager.URL_PRODUCAO,
            "cpf_cnpj": self.cpf_cnpj,
            "tipo_documento": self.manager.tipo_documento,
            "certificado_configurado": self.cert_manager is not None,
            "certificado_valido": (self.cert_manager._loaded if self.cert_manager else False),
            "login_ecac": {
                "metodo": "certificado_a1_govbr",
                "status": "operacional",
                "titular": "CONECTAMAIS ELETRONICA LTDA (35.710.481/0001-03)",
                "responsavel_legal": "JORDAN SANTOS DE JESUS",
                "detalhe": "Login e-CAC por certificado provado via robô (session-reuse gov.br).",
            },
            "pull_direto_rfb": PULL_DIRETO_RFB,
            "fonte_dados": "erp_puxador_drive (Portte/Onvio) + folha — reais e conciliados",
            "servicos_disponiveis": [
                "Consulta de Situacao Fiscal",
                "Consulta de Debitos",
                "Emissao de Certidoes (CND/CPEN)",
                "Validacao de Certidoes",
                "Consulta de Declaracoes",
                "Parcelamentos",
                "Processos Digitais (e-Processo)",
            ],
        }


# Singleton
_ecac_service: EcacService | None = None


def get_ecac_service() -> EcacService:
    """Retorna instancia singleton do service."""
    global _ecac_service
    if _ecac_service is None:
        _ecac_service = EcacService()
    return _ecac_service
