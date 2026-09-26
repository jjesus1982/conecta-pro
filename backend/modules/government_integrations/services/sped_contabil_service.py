"""
Service para SPED Contábil (ECD).

Camada de serviço que encapsula a lógica de negócio do SPED Contábil.
"""

import json
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
    Signatario,
    SPEDContabilManager,
    TipoConta,
    TipoECD,
)

logger = logging.getLogger(__name__)


#: `account_type` do plano de contas → NaturezaConta do leiaute da ECD.
#: A ponte tem de existir explicitamente: o CÓDIGO da conta não diz a natureza, e já
#: mudou de significado uma vez nesta casa (plano aposentado em 13/08/2026).
NATUREZA_POR_TIPO = {
    "ASSET": "01",
    "LIABILITY": "02",
    "EQUITY": "03",
    "REVENUE": "04",
    "EXPENSE": "05",
    "COST": "05",
}


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

    def __init__(self, empresa_slug: str | None = None):
        """Inicializa o service com a identificação REAL da empresa (tabela empresas).

        `empresa_slug` escolhe o CNPJ. A ECD é POR CNPJ — um arquivo que misturasse as duas
        empresas não serve para nenhuma das duas. Antes o `empresa_id` do razão era uma
        constante no código (`619a3df1-…`), então a Patrimonial nunca teve como gerar a sua.
        """
        empresa = get_empresa_fiscal(empresa_slug)
        self.empresa_slug = empresa_slug
        self.cnpj = empresa.cnpj
        self.razao_social = empresa.razao_social
        self.tipo_ecd = os.environ.get("SPED_TIPO_ECD", "G")
        self._empresa_id = self._resolver_empresa_id(self.cnpj)

        self.manager = SPEDContabilManager(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            tipo_ecd=TipoECD(self.tipo_ecd)
            if self.tipo_ecd in ["G", "R", "A", "Z", "B"]
            else TipoECD.LIVRO_DIARIO_GERAL,
            uf=empresa.uf,
            inscricao_estadual=empresa.inscricao_estadual,
            codigo_municipio=empresa.codigo_municipio,
            inscricao_municipal=empresa.inscricao_municipal,
        )
        self.manager.signatarios = self._signatarios_declarados()

        logger.info(
            "SPEDContabilService iniciado: CNPJ=%s empresa_id=%s signatários=%d",
            self.cnpj, self._empresa_id, len(self.manager.signatarios),
        )

    @staticmethod
    def _signatarios_declarados() -> list[Signatario]:
        """Quem assina a ECD, declarado na env `SPED_ECD_SIGNATARIOS` (JSON).

        Vazio é resposta legítima e é o estado de 26/09/2026: quem assinava era a Portte,
        o dono decidiu fazer a própria contabilidade e o sistema nunca teve o campo. O
        arquivo sai SEM J930 e a falta aparece em `signatarios_faltando` — melhor que o
        que havia antes, um J930 com todos os campos em branco e o literal «CONTADOR»,
        que faz o arquivo parecer completo e ser recusado.
        """
        bruto = os.environ.get("SPED_ECD_SIGNATARIOS", "").strip()
        if not bruto:
            return []
        try:
            itens = json.loads(bruto)
        except Exception as exc:  # noqa: BLE001 — env malformada não derruba a geração
            logger.warning("SPED_ECD_SIGNATARIOS não é JSON válido (%s); ECD sai sem J930", exc)
            return []
        fora = []
        for it in itens if isinstance(itens, list) else []:
            fora.append(Signatario(
                nome=str(it.get("nome", "")),
                cpf=str(it.get("cpf", "")),
                qualificacao=str(it.get("qualificacao", "900")),
                crc=str(it.get("crc", "")),
                uf_crc=str(it.get("uf_crc", "")),
                email=str(it.get("email", "")),
                telefone=str(it.get("telefone", "")),
                responsavel_legal=bool(it.get("responsavel_legal", False)),
            ))
        return fora

    def _resolver_empresa_id(self, cnpj: str) -> str | None:
        """UUID da empresa em `empresas`, pelo CNPJ. None se não achar — e então a carga
        de lançamentos RECUSA em vez de trazer o razão de outro CNPJ."""
        url = self._db_url()
        if not url:
            return None
        try:
            conn = psycopg2.connect(url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id::text FROM empresas "
                        " WHERE regexp_replace(coalesce(cnpj,''), '\\D', '', 'g') = %s LIMIT 1",
                        (re.sub(r"\D", "", cnpj or ""),),
                    )
                    row = cur.fetchone()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("SPED Contábil: não resolveu empresa_id do CNPJ %s (%s)", cnpj, e)
            return None
        return row[0] if row else None

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
        if not self._empresa_id:
            # Sem saber de quem é o razão, trazer "todos os lançamentos" misturaria os dois
            # CNPJs num arquivo que não serve para nenhum dos dois. Recusa é o certo.
            logger.warning(
                "SPED Contábil: empresa_id desconhecido para CNPJ %s — carga recusada", self.cnpj
            )
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
                    # O PLANO DE CONTAS REAL. Sem ele a natureza era deduzida do primeiro
                    # dígito do código — e o mapa embutido descrevia o plano APOSENTADO em
                    # 13/08/2026 ("3=Receita, 4=Despesa"). No plano vigente 3 é Patrimônio
                    # Líquido, 4 é Receita e 5 é Despesa, então a receita do exercício saía
                    # classificada como resultado DEVEDOR e o I350 publicava R$ 0,00 no lugar
                    # de R$ 1.581.873,06. Também vinham daqui as descrições "Conta 5.1.1.02"
                    # em vez do nome verdadeiro.
                    with conn.cursor() as cur2:
                        cur2.execute(
                            "SELECT code, coalesce(name,''), upper(coalesce(account_type::text,'')), "
                            "       coalesce(level, 0), coalesce(accepts_entries, true) "
                            "  FROM fin_accounting_accounts"
                        )
                        plano = {
                            r[0]: {"nome": r[1], "tipo": r[2], "nivel": r[3], "analitica": r[4]}
                            for r in cur2.fetchall()
                        }
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
            # Vem do `account_type` do plano — NUNCA do primeiro dígito do código.
            info = plano.get(codigo)
            if info and info["tipo"] in NATUREZA_POR_TIPO:
                natureza = NATUREZA_POR_TIPO[info["tipo"]]
            else:
                # Conta no razão e fora do plano: 05 é o palpite menos danoso (resultado
                # devedor), mas fica registrado para não passar despercebido.
                natureza = "05"
                logger.warning(
                    "SPED Contábil: conta %s não está em fin_accounting_accounts — "
                    "natureza assumida 05",
                    codigo,
                )
            self.adicionar_conta(
                {
                    "codigo": codigo,
                    "descricao": (info or {}).get("nome") or f"Conta {codigo}",
                    "tipo": "A" if (info or {}).get("analitica", True) else "S",
                    "nivel": (info or {}).get("nivel") or (codigo.count(".") + 1),
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

        # Blocos J100/J150 (balanço e DRE): derivados do razão quando não informados.
        # O emissor deles já existia no manager e nunca recebia os demonstrativos — o bloco J
        # saía com J001/J005/J900/J930/J990 e ZERO J100, ZERO J150.
        demo = {"derivado": False, "motivo": "informado pelo chamador"}
        if not balanco and not dre:
            demo = self.derivar_demonstrativos_do_razao(dt_inicio, dt_fim)

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
            "signatarios": [
                {"nome": x.nome, "qualificacao": x.qualificacao, "crc": x.crc,
                 "completo": x.completo}
                for x in self.manager.signatarios
            ],
            "signatarios_faltando": (
                "" if any(x.completo and x.e_contabilista for x in self.manager.signatarios)
                else (
                    "A ECD é assinada por CONTABILISTA COM CRC ATIVO e nenhum software "
                    "substitui isso. Não há signatário declarado: o arquivo sai sem J930 e "
                    "o fisco o recusa. Declare em `SPED_ECD_SIGNATARIOS` (JSON): "
                    '[{"nome": "...", "cpf": "...", "qualificacao": "900", '
                    '"crc": "AM-012345/O-1", "uf_crc": "AM"}]'
                )
            ),
            "veracidade": {
                "fonte_lancamentos": "accounting_entries" if auto_carregados else "manual",
                "status": ("consolidado_com_razao_real" if total_lanc else "sem_lancamentos_no_periodo"),
                "empresa_id": self._empresa_id,
                "cnpj": self.cnpj,
                "demonstrativos_bloco_j": demo,
                "observacao": (
                    "ECD consolidada a partir do razão real (accounting_entries) DESTE CNPJ. "
                    "Ajustes finais e a assinatura do contabilista com CRC ativo continuam "
                    "sendo do contador — nenhum software substitui isso."
                ),
            },
        }

    def derivar_demonstrativos_do_razao(self, dt_inicio, dt_fim) -> dict[str, Any]:
        """Monta Balanço (J100) e DRE (J150) a partir do razão, pela natureza do plano.

        Usa exatamente a mesma régua do DRE das telas: a natureza vem de
        `fin_accounting_accounts.account_type`, NUNCA do primeiro dígito do código — 4.1.2
        FGTS e 4.1.3 INSS Patronal são EXPENSE com código de receita, e classificar por
        prefixo faria a mesma conta sair como receita aqui e despesa no balanço.

        RECUSA emitir o balanço se a identidade Ativo = Passivo + PL não fechar. Hoje ela
        não fecha: as 89 contas do plano estão com saldo de abertura ZERO — o razão nasce do
        nada em 01/01/2026 —, então o Ativo fecha CREDOR. Publicar um J100 que não fecha é
        pior que não publicar: o PVA recusaria, e um humano poderia não recusar.
        O saldo de abertura de 31/12/2025 está com a contabilidade atual; é o único item
        desta lista que o dono não consegue produzir depois da rescisão.
        """
        url = self._db_url()
        if not url or not self._empresa_id:
            return {"derivado": False, "motivo": "sem banco ou empresa_id indefinido"}

        comps = self._competencias_do_periodo(dt_inicio, dt_fim)
        try:
            conn = psycopg2.connect(url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        WITH mov AS (
                            SELECT conta_debito AS conta, valor AS v, tipo_lancamento AS t
                              FROM accounting_entries
                             WHERE status = 'confirmado' AND empresa_id = %s::uuid
                               AND periodo_competencia = ANY(%s)
                            UNION ALL
                            SELECT conta_credito, -valor, tipo_lancamento
                              FROM accounting_entries
                             WHERE status = 'confirmado' AND empresa_id = %s::uuid
                               AND periodo_competencia = ANY(%s)
                        )
                        SELECT mov.conta, upper(coalesce(a.account_type::text, '')),
                               round(sum(mov.v), 2),
                               round(sum(mov.v) FILTER (WHERE coalesce(mov.t,'') <> 'apuracao'), 2)
                          FROM mov LEFT JOIN fin_accounting_accounts a ON a.code = mov.conta
                         GROUP BY 1, 2
                        """,
                        (self._empresa_id, comps, self._empresa_id, comps),
                    )
                    linhas = cur.fetchall()
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("SPED Contábil: falha ao derivar demonstrativos (%s)", e)
            return {"derivado": False, "motivo": f"erro ao ler o razão: {e}"}

        def d(x) -> Decimal:
            return Decimal(str(x or 0))

        ac = anc = pc = pnc = pl = Decimal("0")
        receita = deducoes = custos = desp_op = fin = outras = Decimal("0")
        sem_tipo: list[str] = []

        for conta, tipo, saldo_total, saldo_sem_apur in linhas:
            st, ss = d(saldo_total), d(saldo_sem_apur)
            if tipo == "ASSET":
                if conta.startswith("1.1"):
                    ac += st
                else:
                    anc += st
            elif tipo == "LIABILITY":
                if conta.startswith("2.1"):
                    pc += -st
                else:
                    pnc += -st
            elif tipo == "EQUITY":
                pl += -st
            elif tipo == "REVENUE":
                receita += -ss
            elif tipo in ("EXPENSE", "COST"):
                if conta.startswith("5.2.2.01"):
                    deducoes += ss
                elif conta.startswith("5.2.3"):
                    fin += ss
                elif conta.startswith("5.1"):
                    custos += ss
                elif conta.startswith("5.2"):
                    desp_op += ss
                else:
                    outras += ss
            else:
                sem_tipo.append(conta)

        # O resultado do exercício ainda não encerrado compõe o PL do balanço.
        resultado = receita - deducoes - custos - desp_op - outras - fin
        pl_total = pl + resultado
        diferenca = (ac + anc) - (pc + pnc + pl_total)

        self.definir_dre(
            {
                "periodo_inicio": dt_inicio.isoformat(),
                "periodo_fim": dt_fim.isoformat(),
                "receita_bruta": str(receita),
                "deducoes_receita": str(deducoes),
                "custos": str(custos),
                "despesas_operacionais": str(desp_op + outras),
                "resultado_financeiro": str(-fin),
                "outras_receitas_despesas": "0",
                "irpj_csll": "0",
            }
        )

        if sem_tipo:
            return {
                "derivado": False, "dre": True, "balanco": False,
                "motivo": ("contas do razão sem classificação no plano — o balanço sairia "
                           f"incompleto: {sorted(set(sem_tipo))[:6]}"),
            }
        ativo_total = ac + anc
        # Duas recusas diferentes, e a segunda quase passou despercebida: a IDENTIDADE
        # Ativo = Passivo + PL fecha mesmo com o Ativo NEGATIVO, porque a falta de abertura
        # desloca os dois lados junto. Conferir só a identidade daria verde num balanço que
        # diz que a empresa tem menos que nada.
        if abs(diferenca) > Decimal("0.01") or ativo_total < 0:
            motivo = (
                f"Ativo total {ativo_total} é NEGATIVO — não existe balanço assim."
                if ativo_total < 0
                else f"Ativo {ativo_total} ≠ Passivo + PL {pc + pnc + pl_total} "
                     f"(diferença {diferenca})."
            )
            return {
                "derivado": False, "dre": True, "balanco": False,
                "motivo": (
                    motivo + " Causa conhecida: as 89 contas do plano estão com saldo de "
                    "abertura ZERO — o razão começa em 01/01/2026 sem o que já existia. O "
                    "J100 NÃO foi emitido de propósito: balanço que não fecha é recusado "
                    "pelo PVA, e um humano poderia não recusar. O saldo de abertura de "
                    "31/12/2025 está com a contabilidade atual — peça ANTES da rescisão."
                ),
                "ativo": str(ativo_total), "passivo_mais_pl": str(pc + pnc + pl_total),
                "diferenca": str(diferenca),
            }

        self.definir_balanco(
            {
                "data_referencia": dt_fim.isoformat(),
                "ativo_circulante": str(ac),
                "ativo_nao_circulante": str(anc),
                "passivo_circulante": str(pc),
                "passivo_nao_circulante": str(pnc),
                "patrimonio_liquido": str(pl_total),
            }
        )
        return {"derivado": True, "dre": True, "balanco": True,
                "ativo": str(ac + anc), "resultado_do_exercicio": str(resultado)}

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
#: Sem singleton. O service acumula `plano_contas` e `lancamentos` no manager; reutilizar a
#: instância entre requisições somava o período de uma geração na seguinte, e prendia o
#: arquivo ao CNPJ da primeira chamada.
_service_instance: SPEDContabilService | None = None


def get_sped_contabil_service() -> SPEDContabilService:
    """Retorna instância singleton do service."""
    return SPEDContabilService()
