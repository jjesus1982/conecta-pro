"""
Service para SPED Fiscal (EFD ICMS/IPI).

Camada de serviço que encapsula a lógica de negócio do SPED Fiscal.
"""

import logging
import os
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

import psycopg2

from ..core.empresa_context import get_empresa_fiscal
from ..core.sped_fiscal import (
    DocumentoFiscal,
    FinalidadeArquivo,
    Inventario,
    Participante,
    PerfilArquivo,
    Produto,
    SPEDFiscalManager,
)

logger = logging.getLogger(__name__)


class SPEDFiscalService:
    """
    Service para operações do SPED Fiscal.

    Encapsula todas as operações relacionadas ao SPED Fiscal,
    incluindo geração de arquivos e cálculos de apuração.
    """

    # Descrições dos blocos
    BLOCOS = {
        "0": "Abertura, Identificação e Referências",
        "C": "Documentos Fiscais I (Mercadorias)",
        "D": "Documentos Fiscais II (Serviços de Transporte)",
        "E": "Apuração do ICMS e do IPI",
        "G": "Controle do Crédito de ICMS do Ativo Permanente",
        "H": "Inventário Físico",
        "K": "Controle da Produção e do Estoque",
        "1": "Outras Informações",
        "9": "Controle e Encerramento do Arquivo",
    }

    def __init__(self):
        """Inicializa o service com a identificação REAL da empresa (tabela empresas)."""
        empresa = get_empresa_fiscal()
        self.cnpj = empresa.cnpj
        self.razao_social = empresa.razao_social
        self.ie = empresa.inscricao_estadual
        self.uf = empresa.uf
        self.cod_municipio = empresa.codigo_municipio
        self.perfil = os.environ.get("SPED_PERFIL", "A")
        self._empresa_id = "619a3df1-8bce-49ce-b77a-04f80a0e8491"

        self.manager = SPEDFiscalManager(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            inscricao_estadual=self.ie,
            uf=self.uf,
            codigo_municipio=self.cod_municipio,
            perfil=PerfilArquivo(self.perfil) if self.perfil in ["A", "B", "C"] else PerfilArquivo.PERFIL_A,
        )

        logger.info(f"SPEDFiscalService iniciado: CNPJ={self.cnpj}, UF={self.uf}")

    def validar_status(self) -> dict[str, Any]:
        """Valida e retorna status da configuração."""
        return {
            "cnpj": self.cnpj,
            "razao_social": self.razao_social,
            "inscricao_estadual": self.ie,
            "uf": self.uf,
            "perfil": self.perfil,
            "versao_leiaute": self.manager.VERSAO_LEIAUTE,
            "operacoes_disponiveis": [
                "gerar_arquivo",
                "validar_arquivo",
                "calcular_apuracao",
                "adicionar_participante",
                "adicionar_produto",
                "adicionar_documento",
                "adicionar_inventario",
            ],
        }

    def adicionar_participante(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Adiciona um participante ao cadastro.

        Args:
            dados: Dados do participante

        Returns:
            Participante adicionado
        """
        participante = Participante(
            codigo=dados["codigo"],
            nome=dados["nome"],
            cnpj_cpf=dados["cnpj_cpf"].replace(".", "").replace("-", "").replace("/", ""),
            inscricao_estadual=dados.get("inscricao_estadual"),
            codigo_municipio=dados.get("codigo_municipio"),
            uf=dados.get("uf"),
            endereco=dados.get("endereco"),
            cep=dados.get("cep"),
        )

        self.manager.adicionar_participante(participante)

        logger.info(f"Participante adicionado: {participante.codigo}")

        return {
            "codigo": participante.codigo,
            "nome": participante.nome,
            "cnpj_cpf": participante.cnpj_cpf,
            "tipo_pessoa": "Jurídica" if len(participante.cnpj_cpf) == 14 else "Física",
        }

    def adicionar_produto(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Adiciona um produto ao cadastro.

        Args:
            dados: Dados do produto

        Returns:
            Produto adicionado
        """
        produto = Produto(
            codigo=dados["codigo"],
            descricao=dados["descricao"],
            codigo_barras=dados.get("codigo_barras"),
            unidade=dados.get("unidade", "UN"),
            tipo_item=dados.get("tipo_item", "00"),
            ncm=dados.get("ncm"),
            cest=dados.get("cest"),
            aliquota_icms=Decimal(str(dados.get("aliquota_icms", 0))),
        )

        self.manager.adicionar_produto(produto)

        logger.info(f"Produto adicionado: {produto.codigo}")

        return {
            "codigo": produto.codigo,
            "descricao": produto.descricao,
            "ncm": produto.ncm,
            "unidade": produto.unidade,
        }

    def adicionar_documento(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Adiciona um documento fiscal.

        Args:
            dados: Dados do documento

        Returns:
            Documento adicionado
        """
        # Verifica se participante existe ou cria temporário
        cod_part = dados["codigo_participante"]
        if cod_part not in self.manager.participantes:
            self.manager.adicionar_participante(
                Participante(
                    codigo=cod_part,
                    nome=f"Participante {cod_part}",
                    cnpj_cpf="00000000000000",
                )
            )

        documento = DocumentoFiscal(
            tipo=dados["tipo"],
            chave=dados["chave"],
            numero=dados["numero"],
            serie=dados["serie"],
            data_emissao=datetime.strptime(dados["data_emissao"], "%Y-%m-%d").date(),
            data_entrada_saida=datetime.strptime(dados["data_entrada_saida"], "%Y-%m-%d").date(),
            participante=self.manager.participantes[cod_part],
            valor_total=Decimal(str(dados["valor_total"])),
            valor_icms=Decimal(str(dados.get("valor_icms", 0))),
            valor_ipi=Decimal(str(dados.get("valor_ipi", 0))),
            valor_pis=Decimal(str(dados.get("valor_pis", 0))),
            valor_cofins=Decimal(str(dados.get("valor_cofins", 0))),
            cfop=dados["cfop"],
        )

        self.manager.adicionar_documento(documento)

        logger.info(f"Documento adicionado: {documento.chave}")

        return {
            "tipo": documento.tipo,
            "chave": documento.chave,
            "numero": documento.numero,
            "valor_total": str(documento.valor_total),
        }

    def adicionar_inventario(self, dados: dict[str, Any]) -> dict[str, Any]:
        """
        Adiciona um item ao inventário.

        Args:
            dados: Dados do item

        Returns:
            Item adicionado
        """
        item = Inventario(
            codigo_item=dados["codigo_item"],
            descricao=dados["descricao"],
            unidade=dados.get("unidade", "UN"),
            quantidade=Decimal(str(dados["quantidade"])),
            valor_unitario=Decimal(str(dados["valor_unitario"])),
            valor_total=Decimal(str(dados["valor_total"])),
            propriedade=dados.get("propriedade", "0"),
            conta_contabil=dados.get("conta_contabil"),
        )

        self.manager.adicionar_inventario(item)

        logger.info(f"Item inventário adicionado: {item.codigo_item}")

        return {
            "codigo_item": item.codigo_item,
            "descricao": item.descricao,
            "quantidade": str(item.quantidade),
            "valor_total": str(item.valor_total),
        }

    def calcular_apuracao(self, periodo: str, documentos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """
        Calcula a apuração de ICMS do período.

        Args:
            periodo: Período YYYY-MM
            documentos: Lista de documentos (opcional)

        Returns:
            Resultado da apuração
        """
        # Adiciona documentos se fornecidos
        if documentos:
            for doc in documentos:
                self.adicionar_documento(doc)

        apuracao = self.manager.calcular_apuracao(periodo)

        return {
            "periodo": apuracao.periodo,
            "valor_debitos": str(apuracao.valor_debitos),
            "valor_creditos": str(apuracao.valor_creditos),
            "valor_estorno_debitos": str(apuracao.valor_estorno_debitos),
            "valor_estorno_creditos": str(apuracao.valor_estorno_creditos),
            "valor_saldo_credor_anterior": str(apuracao.valor_saldo_credor_anterior),
            "valor_ajustes_debito": str(apuracao.valor_ajustes_debito),
            "valor_ajustes_credito": str(apuracao.valor_ajustes_credito),
            "saldo_apurado": str(apuracao.saldo_apurado),
            "saldo_devedor": str(apuracao.saldo_devedor),
            "saldo_credor": str(apuracao.saldo_credor),
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

    def carregar_documentos_do_periodo(self, dt_inicio, dt_fim) -> int:
        """
        Popula o manager com as NFS-e emitidas reais (nfse_emitidas_nacional) do
        período, para que o arquivo SPED reflita os documentos de verdade em vez
        de sair vazio. Retorna a quantidade de documentos carregados.

        Nota de honestidade: a empresa é prestadora de SERVIÇOS (emite NFS-e), sem
        movimentação de mercadorias com ICMS/IPI — por isso os documentos entram
        sem débito de ICMS/IPI. A escrituração fiscal de ISS/serviços é municipal,
        mas os documentos reais são refletidos aqui para não gerar arquivo oco.
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
                        SELECT chave_acesso, numero, competencia, data_emissao,
                               tomador_cnpj, tomador_nome, valor_servicos
                        FROM nfse_emitidas_nacional
                        WHERE competencia = ANY(%s)
                        ORDER BY data_emissao
                        """,
                        (comps,),
                    )
                    rows = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("SPED Fiscal: falha ao carregar NFS-e do período (%s)", e)
            return 0

        carregados = 0
        for chave, numero, _comp, data_emissao, tom_cnpj, tom_nome, valor in rows:
            emissao = data_emissao.date() if data_emissao else dt_inicio
            self.adicionar_documento(
                {
                    "tipo": "55",
                    "chave": (chave or "")[:44],
                    "numero": str(numero or ""),
                    "serie": "1",
                    "data_emissao": emissao.strftime("%Y-%m-%d"),
                    "data_entrada_saida": emissao.strftime("%Y-%m-%d"),
                    "codigo_participante": (re.sub(r"\D", "", tom_cnpj or "") or "SEMDOC"),
                    "valor_total": str(valor or 0),
                    "cfop": "5933",  # prestação de serviço sujeito ao ISS
                }
            )
            # nomeia o participante recém-criado, se aplicável
            cod_part = re.sub(r"\D", "", tom_cnpj or "") or "SEMDOC"
            if cod_part in self.manager.participantes and tom_nome:
                self.manager.participantes[cod_part].nome = tom_nome
            carregados += 1

        logger.info("SPED Fiscal: %d NFS-e reais carregadas do período %s", carregados, comps)
        return carregados

    def gerar_arquivo(
        self,
        periodo_inicio: str,
        periodo_fim: str,
        finalidade: str = "0",
        participantes: list[dict[str, Any]] | None = None,
        produtos: list[dict[str, Any]] | None = None,
        documentos: list[dict[str, Any]] | None = None,
        inventario: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Gera o arquivo SPED Fiscal.

        Args:
            periodo_inicio: Data inicial YYYY-MM-DD
            periodo_fim: Data final YYYY-MM-DD
            finalidade: 0=Original, 1=Substituto
            participantes: Lista de participantes
            produtos: Lista de produtos
            documentos: Lista de documentos
            inventario: Lista de itens do inventário

        Returns:
            Arquivo gerado
        """
        # Adiciona dados se fornecidos
        if participantes:
            for p in participantes:
                self.adicionar_participante(p)

        if produtos:
            for p in produtos:
                self.adicionar_produto(p)

        if documentos:
            for d in documentos:
                self.adicionar_documento(d)

        if inventario:
            for i in inventario:
                self.adicionar_inventario(i)

        dt_inicio = datetime.strptime(periodo_inicio, "%Y-%m-%d").date()
        dt_fim = datetime.strptime(periodo_fim, "%Y-%m-%d").date()
        final = FinalidadeArquivo(finalidade)

        # Se nenhum documento foi passado explicitamente, consolida os documentos
        # REAIS (NFS-e emitidas) do período — em vez de gerar arquivo vazio.
        auto_carregados = 0
        if not documentos and not self.manager.documentos:
            auto_carregados = self.carregar_documentos_do_periodo(dt_inicio, dt_fim)

        conteudo = self.manager.gerar_arquivo(dt_inicio, dt_fim, final)

        # Valida
        validacao = self.manager.validar_arquivo(conteudo)

        total_docs = len(self.manager.documentos)
        return {
            "periodo_inicio": periodo_inicio,
            "periodo_fim": periodo_fim,
            "total_registros": validacao["total_registros"],
            "total_participantes": len(self.manager.participantes),
            "total_produtos": len(self.manager.produtos),
            "total_documentos": total_docs,
            "total_inventario": len(self.manager.inventario),
            "documentos_reais_carregados": auto_carregados,
            "hash_md5": validacao["hash"],
            "conteudo": conteudo,
            "veracidade": {
                "fonte_documentos": "nfse_emitidas_nacional" if auto_carregados else "manual",
                "status": ("consolidado_com_dados_reais" if total_docs else "sem_documentos_no_periodo"),
                "observacao": (
                    "EFD ICMS/IPI: empresa prestadora de serviços (NFS-e). Documentos reais do "
                    "período consolidados sem débito de ICMS/IPI; apuração de ISS é municipal. "
                    "Adições/ajustes fiscais são do contador."
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
        """Lista blocos do SPED Fiscal."""
        return {"blocos": [{"codigo": k, "descricao": v} for k, v in self.BLOCOS.items()]}

    def listar_participantes(self) -> dict[str, Any]:
        """Lista participantes cadastrados."""
        return {
            "participantes": [
                {
                    "codigo": p.codigo,
                    "nome": p.nome,
                    "cnpj_cpf": p.cnpj_cpf,
                    "uf": p.uf,
                }
                for p in self.manager.participantes.values()
            ]
        }

    def listar_produtos(self) -> dict[str, Any]:
        """Lista produtos cadastrados."""
        return {
            "produtos": [
                {
                    "codigo": p.codigo,
                    "descricao": p.descricao,
                    "ncm": p.ncm,
                    "unidade": p.unidade,
                }
                for p in self.manager.produtos.values()
            ]
        }

    def listar_documentos(self) -> dict[str, Any]:
        """Lista documentos cadastrados."""
        return {
            "documentos": [
                {
                    "tipo": d.tipo,
                    "chave": d.chave,
                    "numero": d.numero,
                    "cfop": d.cfop,
                    "valor_total": str(d.valor_total),
                    "valor_icms": str(d.valor_icms),
                }
                for d in self.manager.documentos
            ]
        }

    def limpar_dados(self) -> dict[str, Any]:
        """Limpa dados do manager."""
        self.manager.participantes.clear()
        self.manager.produtos.clear()
        self.manager.documentos.clear()
        self.manager.inventario.clear()
        self.manager.apuracao_icms = None

        return {"message": "Dados limpos com sucesso"}


# Singleton
_service_instance: SPEDFiscalService | None = None


def get_sped_fiscal_service() -> SPEDFiscalService:
    """Retorna instância singleton do service."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SPEDFiscalService()
    return _service_instance
