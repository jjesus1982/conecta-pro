"""
Service para SPED Contábil (ECD).

Camada de serviço que encapsula a lógica de negócio do SPED Contábil.
"""

import logging
import os
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg2

from ..core.empresa_context import get_empresa_fiscal
from ..core.sped_contabil import (
    ContaContabil,
    DemonstrativoBalancoPatrimonial,
    DemonstrativoDRE,
    LancamentoContabil,
    NaturezaConta,
    SPEDContabilManager,
    TipoConta,
    TipoECD,
)

logger = logging.getLogger(__name__)


class SPEDContabilService:
    """
    Service para operações do SPED Contábil.

    Encapsula todas as operações relacionadas ao SPED Contábil,
    incluindo geração de arquivos e demonstrações contábeis.
    """

    # Descrições dos blocos
    BLOCOS = {
        "0": "Abertura e Identificação",
        "I": "Lançamentos Contábeis",
        "J": "Demonstrações Contábeis",
        "K": "Conglomerados Econômicos",
        "9": "Controle e Encerramento",
    }

    # Tipos de ECD
    TIPOS_ECD = {
        "G": "Livro Diário Geral",
        "R": "Livro Diário Resumido",
        "A": "Livro Diário Auxiliar",
        "Z": "Livro Razão Auxiliar",
        "B": "Livro Balancetes Diários e Balanços",
    }

    def __init__(self):
        """Inicializa o service com a identificação REAL da empresa (tabela empresas)."""
        empresa = get_empresa_fiscal()
        self.cnpj = empresa.cnpj
        self.razao_social = empresa.razao_social
        self.tipo_ecd = os.environ.get("SPED_TIPO_ECD", "G")
        self._empresa_id = "619a3df1-8bce-49ce-b77a-04f80a0e8491"

        self.manager = SPEDContabilManager(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            tipo_ecd=TipoECD(self.tipo_ecd)
            if self.tipo_ecd in ["G", "R", "A", "Z", "B"]
            else TipoECD.LIVRO_DIARIO_GERAL,
        )

        logger.info(f"SPEDContabilService iniciado: CNPJ={self.cnpj}")

    def validar_status(self) -> dict[str, Any]:
        """Valida e retorna status da configuração."""
        return {
            "cnpj": self.cnpj,
            "razao_social": self.razao_social,
            "tipo_ecd": self.tipo_ecd,
            "versao_leiaute": self.manager.VERSAO_LEIAUTE,
            "operacoes_disponiveis": [
                "gerar_arquivo",
                "validar_arquivo",
                "calcular_saldos",
                "adicionar_conta",
                "adicionar_lancamento",
                "definir_balanco",
                "definir_dre",
            ],
        }

    def adicionar_conta(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Adiciona uma conta ao plano de contas.

        Args:
            dados: Dados da conta

        Returns:
            Conta adicionada
        """
        conta = ContaContabil(
            codigo=dados["codigo"],
            descricao=dados["descricao"],
            tipo=TipoConta(dados.get("tipo", "A")),
            nivel=dados["nivel"],
            natureza=NaturezaConta(dados["natureza"]),
            codigo_pai=dados.get("codigo_pai"),
            codigo_referencial=dados.get("codigo_referencial"),
            saldo_inicial_debito=Decimal(str(dados.get("saldo_inicial_debito", 0))),
            saldo_inicial_credito=Decimal(str(dados.get("saldo_inicial_credito", 0))),
        )

        self.manager.adicionar_conta(conta)

        logger.info(f"Conta adicionada: {conta.codigo}")

        return {
            "codigo": conta.codigo,
            "descricao": conta.descricao,
            "tipo": conta.tipo.value,
            "nivel": conta.nivel,
            "natureza": conta.natureza.value,
        }

    def adicionar_lancamento(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Adiciona um lançamento contábil.

        Args:
            dados: Dados do lançamento

        Returns:
            Lançamento adicionado
        """
        lancamento = LancamentoContabil(
            numero=dados["numero"],
            data=datetime.strptime(dados["data"], "%Y-%m-%d").date(),
            conta_debito=dados["conta_debito"],
            conta_credito=dados["conta_credito"],
            valor=Decimal(str(dados["valor"])),
            historico=dados["historico"],
            documento=dados.get("documento"),
            participante=dados.get("participante"),
        )

        self.manager.adicionar_lancamento(lancamento)

        logger.info(f"Lançamento adicionado: {lancamento.numero}")

        return {
            "numero": lancamento.numero,
            "data": lancamento.data.isoformat(),
            "conta_debito": lancamento.conta_debito,
            "conta_credito": lancamento.conta_credito,
            "valor": str(lancamento.valor),
            "historico": lancamento.historico,
        }

    def definir_balanco(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Define o balanço patrimonial.

        Args:
            dados: Dados do balanço

        Returns:
            Balanço definido
        """
        balanco = DemonstrativoBalancoPatrimonial(
            data_referencia=datetime.strptime(dados["data_referencia"], "%Y-%m-%d").date(),
            ativo_circulante=Decimal(str(dados.get("ativo_circulante", 0))),
            ativo_nao_circulante=Decimal(str(dados.get("ativo_nao_circulante", 0))),
            passivo_circulante=Decimal(str(dados.get("passivo_circulante", 0))),
            passivo_nao_circulante=Decimal(str(dados.get("passivo_nao_circulante", 0))),
            patrimonio_liquido=Decimal(str(dados.get("patrimonio_liquido", 0))),
        )

        self.manager.balanco = balanco

        logger.info(f"Balanço definido: {balanco.data_referencia}")

        return {
            "data_referencia": balanco.data_referencia.isoformat(),
            "ativo_circulante": str(balanco.ativo_circulante),
            "ativo_nao_circulante": str(balanco.ativo_nao_circulante),
            "total_ativo": str(balanco.total_ativo),
            "passivo_circulante": str(balanco.passivo_circulante),
            "passivo_nao_circulante": str(balanco.passivo_nao_circulante),
            "patrimonio_liquido": str(balanco.patrimonio_liquido),
            "total_passivo_pl": str(balanco.total_passivo_pl),
        }

    def definir_dre(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Define a DRE.

        Args:
            dados: Dados da DRE

        Returns:
            DRE definida
        """
        dre = DemonstrativoDRE(
            periodo_inicio=datetime.strptime(dados["periodo_inicio"], "%Y-%m-%d").date(),
            periodo_fim=datetime.strptime(dados["periodo_fim"], "%Y-%m-%d").date(),
            receita_bruta=Decimal(str(dados.get("receita_bruta", 0))),
            deducoes_receita=Decimal(str(dados.get("deducoes_receita", 0))),
            custos=Decimal(str(dados.get("custos", 0))),
            despesas_operacionais=Decimal(str(dados.get("despesas_operacionais", 0))),
            resultado_financeiro=Decimal(str(dados.get("resultado_financeiro", 0))),
            outras_receitas_despesas=Decimal(str(dados.get("outras_receitas_despesas", 0))),
            irpj_csll=Decimal(str(dados.get("irpj_csll", 0))),
        )

        self.manager.dre = dre

        logger.info(f"DRE definida: {dre.periodo_inicio} a {dre.periodo_fim}")

        return {
            "periodo_inicio": dre.periodo_inicio.isoformat(),
            "periodo_fim": dre.periodo_fim.isoformat(),
            "receita_bruta": str(dre.receita_bruta),
            "deducoes_receita": str(dre.deducoes_receita),
            "receita_liquida": str(dre.receita_liquida),
            "custos": str(dre.custos),
            "lucro_bruto": str(dre.lucro_bruto),
            "despesas_operacionais": str(dre.despesas_operacionais),
            "lucro_operacional": str(dre.lucro_operacional),
            "resultado_financeiro": str(dre.resultado_financeiro),
            "outras_receitas_despesas": str(dre.outras_receitas_despesas),
            "lucro_antes_ir": str(dre.lucro_antes_ir),
            "irpj_csll": str(dre.irpj_csll),
            "lucro_liquido": str(dre.lucro_liquido),
        }

    def calcular_saldos(self, periodo_inicio: str, periodo_fim: str) -> dict[str, Any]:
        """
        Calcula saldos periódicos.

        Args:
            periodo_inicio: Data inicial YYYY-MM-DD
            periodo_fim: Data final YYYY-MM-DD

        Returns:
            Saldos calculados
        """
        dt_inicio = datetime.strptime(periodo_inicio, "%Y-%m-%d").date()
        dt_fim = datetime.strptime(periodo_fim, "%Y-%m-%d").date()

        saldos = self.manager.calcular_saldos(dt_inicio, dt_fim)

        return {
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "total_contas": len(saldos),
            "saldos": [
                {
                    "codigo_conta": s.codigo_conta,
                    "periodo_inicio": s.data_inicio.isoformat(),
                    "periodo_fim": s.data_fim.isoformat(),
                    "saldo_inicial_debito": str(s.valor_saldo_inicial_debito),
                    "saldo_inicial_credito": str(s.valor_saldo_inicial_credito),
                    "valor_debitos": str(s.valor_debitos),
                    "valor_creditos": str(s.valor_creditos),
                    "saldo_final_debito": str(s.saldo_final_debito),
                    "saldo_final_credito": str(s.saldo_final_credito),
                }
                for s in saldos
            ],
        }

    @staticmethod
    def _db_url() -> str:
        return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))

    @staticmethod
    def _competencias_do_periodo(dt_inicio, dt_fim) -> list[str]:
        """Lista de competências 'YYYY-MM' entre duas datas (inclusive)."""
        comps: list[str] = []
        ano, mes = dt_inicio.year, dt_inicio.month
        while (ano, mes) <= (dt_fim.year, dt_fim.month):
            comps.append(f"{ano:04d}-{mes:02d}")
            mes += 1
            if mes > 12:
                mes = 1
                ano += 1
        return comps

    def carregar_lancamentos_do_periodo(self, dt_inicio, dt_fim) -> int:
        """
        Popula o manager com os lançamentos REAIS do razão (accounting_entries) da
        empresa principal no período. Cada lançamento gera também as contas
        (débito/crédito) referenciadas, para que os blocos I050/I150/I155 não saiam
        vazios. Retorna a quantidade de lançamentos carregados.
        """
        url = self._db_url()
        if not url:
            return 0

        comps = self._competencias_do_periodo(dt_inicio, dt_fim)
        try:
            conn = psycopg2.connect(url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, data_lancamento, conta_debito, conta_credito,
                               valor, historico
                        FROM accounting_entries
                        WHERE status = 'confirmado'
                          AND empresa_id = %s::uuid
                          AND periodo_competencia = ANY(%s)
                        ORDER BY data_lancamento, id
                        """,
                        (self._empresa_id, comps),
                    )
                    rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("SPED Contábil: falha ao carregar lançamentos do período (%s)", e)
            return 0

        contas_vistas: set[str] = set()

        def _garante_conta(codigo: str):
            codigo = (codigo or "").strip()
            if not codigo or codigo in contas_vistas:
                return
            contas_vistas.add(codigo)
            # Natureza da conta (NaturezaConta): 01=Ativo, 02=Passivo, 03=PL,
            # 04=Resultado credora (receita), 05=Resultado devedora (despesa/custo).
            # Plano: 1=Ativo, 2=Passivo/PL, 3=Receita, 4=Despesa/Custo.
            primeiro = codigo[:1]
            if primeiro == "1":
                natureza = "01"
            elif primeiro == "2":
                natureza = "02"
            elif primeiro == "3":
                natureza = "04"
            else:  # "4" e demais: despesa/custo (resultado devedora)
                natureza = "05"
            self.adicionar_conta(
                {
                    "codigo": codigo,
                    "descricao": f"Conta {codigo}",
                    "tipo": "A",  # analítica
                    "nivel": codigo.count(".") + 1,
                    "natureza": natureza,
                }
            )

        carregados = 0
        for _id, data_lanc, c_deb, c_cred, valor, historico in rows:
            _garante_conta(c_deb)
            _garante_conta(c_cred)
            self.adicionar_lancamento(
                {
                    "numero": int(_id),
                    "data": data_lanc.strftime("%Y-%m-%d"),
                    "conta_debito": (c_deb or "").strip(),
                    "conta_credito": (c_cred or "").strip(),
                    "valor": str(valor or 0),
                    "historico": (historico or "")[:255],
                }
            )
            carregados += 1

        logger.info(
            "SPED Contábil: %d lançamentos reais + %d contas carregados do período %s",
            carregados,
            len(contas_vistas),
            comps,
        )
        return carregados

    def gerar_arquivo(
        self,
        ano_referencia: int,
        periodo_inicio: str,
        periodo_fim: str,
        numero_ordem: str = "00001",
        contas: list[dict[str, Any]] | None = None,
        lancamentos: list[dict[str, Any]] | None = None,
        balanco: dict[str, Any] | None = None,
        dre: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Gera o arquivo SPED Contábil.

        Args:
            ano_referencia: Ano de referência
            periodo_inicio: Data inicial YYYY-MM-DD
            periodo_fim: Data final YYYY-MM-DD
            numero_ordem: Número de ordem do livro
            contas: Lista de contas
            lancamentos: Lista de lançamentos
            balanco: Balanço patrimonial
            dre: DRE

        Returns:
            Arquivo gerado
        """
        # Adiciona dados se fornecidos
        if contas:
            for c in contas:
                self.adicionar_conta(c)

        if lancamentos:
            for lanc in lancamentos:
                self.adicionar_lancamento(lanc)

        if balanco:
            self.definir_balanco(balanco)

        if dre:
            self.definir_dre(dre)

        dt_inicio = datetime.strptime(periodo_inicio, "%Y-%m-%d").date()
        dt_fim = datetime.strptime(periodo_fim, "%Y-%m-%d").date()

        # Se nenhum lançamento foi passado, consolida o razão REAL (accounting_entries)
        # do período — em vez de gerar ECD com blocos I/J vazios.
        auto_carregados = 0
        if not lancamentos and not self.manager.lancamentos:
            auto_carregados = self.carregar_lancamentos_do_periodo(dt_inicio, dt_fim)

        conteudo = self.manager.gerar_arquivo(ano_referencia, dt_inicio, dt_fim, numero_ordem)

        # Valida
        validacao = self.manager.validar_arquivo(conteudo)

        total_lanc = len(self.manager.lancamentos)
        return {
            "ano_referencia": ano_referencia,
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "total_registros": validacao["total_registros"],
            "total_contas": len(self.manager.plano_contas),
            "total_lancamentos": total_lanc,
            "lancamentos_reais_carregados": auto_carregados,
            "hash_md5": validacao["hash"],
            "conteudo": conteudo,
            "veracidade": {
                "fonte_lancamentos": "accounting_entries" if auto_carregados else "manual",
                "status": ("consolidado_com_razao_real" if total_lanc else "sem_lancamentos_no_periodo"),
                "observacao": (
                    "ECD consolidada a partir do razão real (accounting_entries) da empresa "
                    "principal. Balanço/DRE (blocos J) e ajustes finais são responsabilidade "
                    "do contador quando não informados explicitamente."
                ),
            },
        }

    def validar_arquivo(self, conteudo: str) -> dict[str, Any]:
        """
        Valida um arquivo SPED.

        Args:
            conteudo: Conteúdo do arquivo

        Returns:
            Resultado da validação
        """
        return self.manager.validar_arquivo(conteudo)

    def listar_blocos(self) -> dict[str, Any]:
        """Lista blocos do SPED Contábil."""
        return {"blocos": [{"codigo": k, "descricao": v} for k, v in self.BLOCOS.items()]}

    def listar_tipos_ecd(self) -> dict[str, Any]:
        """Lista tipos de ECD."""
        return {"tipos": [{"codigo": k, "descricao": v} for k, v in self.TIPOS_ECD.items()]}

    def listar_contas(self) -> dict[str, Any]:
        """Lista contas do plano de contas."""
        return {
            "contas": [
                {
                    "codigo": c.codigo,
                    "descricao": c.descricao,
                    "tipo": c.tipo.value,
                    "nivel": c.nivel,
                    "natureza": c.natureza.value,
                }
                for c in self.manager.plano_contas.values()
            ]
        }

    def listar_lancamentos(self) -> dict[str, Any]:
        """Lista lançamentos."""
        return {
            "lancamentos": [
                {
                    "numero": lanc.numero,
                    "data": lanc.data.isoformat(),
                    "conta_debito": lanc.conta_debito,
                    "conta_credito": lanc.conta_credito,
                    "valor": str(lanc.valor),
                    "historico": lanc.historico,
                }
                for lanc in self.manager.lancamentos
            ]
        }

    def limpar_dados(self) -> dict[str, Any]:
        """Limpa dados do manager."""
        self.manager.plano_contas.clear()
        self.manager.lancamentos.clear()
        self.manager.saldos_periodicos.clear()
        self.manager.balanco = None
        self.manager.dre = None

        return {"message": "Dados limpos com sucesso"}


# Singleton
_service_instance: SPEDContabilService | None = None


def get_sped_contabil_service() -> SPEDContabilService:
    """Retorna instância singleton do service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SPEDContabilService()
    return _service_instance
