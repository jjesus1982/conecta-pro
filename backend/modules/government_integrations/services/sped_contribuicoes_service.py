"""EFD Contribuições — carga do dado REAL e geração por CNPJ.

Lê o que existe: as NFS-e emitidas e autorizadas do CNPJ, no período. Nada de fixture,
nada de «para não gerar arquivo oco» — mês sem nota gera arquivo sem documento, que é a
verdade. Esse atalho já existiu no gerador da EFD ICMS/IPI e fez ele declarar NOTA DE
SERVIÇO como mercadoria.

O regime vem do CADASTRO (`nfse_parametros_empresa.regime` / `empresas.regime_tributario`)
e o montador RECUSA o que não souber escriturar. A Eletrônica é Lucro Real e apura
PIS/COFINS no CUMULATIVO — decisão do dono em 26/09/2026, coerente com o art. 10 da Lei
10.833/2003, que mantém vigilância e transporte de valores no cumulativo.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras

from ..core.empresa_context import get_empresa_fiscal
from ..core.sped_contribuicoes import (
    ALIQ_COFINS_CUMULATIVO,
    ALIQ_PIS_CUMULATIVO,
    Contabilista,
    ServicoPrestado,
    SPEDContribuicoesManager,
    Tomador,
)

logger = logging.getLogger(__name__)

#: Regimes de PIS/COFINS que este serviço sabe escriturar hoje.
REGIMES_ESCRITURAVEIS = ("cumulativo",)


def _so_digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def _db_url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


class RegimeNaoDeclaradoError(Exception):
    """O CNPJ não tem regime de PIS/COFINS declarado — e não se escritura por suposição."""


class DispensadaDaEFDError(Exception):
    """O CNPJ não é obrigado a esta escrituração. Recusar aqui é a resposta CERTA.

    A primeira versão recusava a Patrimonial dizendo «falta declarar o regime», o que é
    verdade e é a razão errada: ela é do Simples Nacional e **dispensada** da EFD
    Contribuições. Recusa que dá o motivo errado manda alguém consertar o que não está
    quebrado — o mesmo defeito das réguas que reprovam o que o dono decidiu.
    """


class SPEDContribuicoesService:
    """Gera a EFD Contribuições de um CNPJ, num período."""

    #: Enquanto não houver coluna própria, o regime de PIS/COFINS de cada CNPJ mora aqui,
    #: com a fonte escrita. Ler `empresas.regime_tributario` (lucro_real) e deduzir
    #: «não-cumulativo» seria o erro clássico: a regra geral é essa, mas vigilância está
    #: entre as exceções do art. 10 da Lei 10.833 e fica no cumulativo.
    REGIME_PIS_COFINS: dict[str, tuple[str, str]] = {
        "35710481000103": (
            "cumulativo",
            "decisão de Jordan Jesus em 26/09/2026; coerente com o art. 10, inciso XXIV "
            "da Lei 10.833/2003 — serviços de vigilância permanecem no cumulativo mesmo "
            "no Lucro Real",
        ),
    }

    def __init__(self, empresa_slug: str | None = None):
        empresa = get_empresa_fiscal(empresa_slug)
        self.empresa_slug = empresa_slug
        self.cnpj = _so_digitos(empresa.cnpj)
        self.razao_social = empresa.razao_social
        self.uf = empresa.uf
        self.cod_municipio = empresa.codigo_municipio
        self.inscricao_estadual = getattr(empresa, "inscricao_estadual", "") or ""
        self.inscricao_municipal = getattr(empresa, "inscricao_municipal", "") or ""

        regime_da_empresa = (getattr(empresa, "regime_tributario", "") or "").strip().lower()
        if regime_da_empresa in ("simples_nacional", "simples", "mei"):
            raise DispensadaDaEFDError(
                f"{self.razao_social} ({self.cnpj}) é do {regime_da_empresa.replace('_', ' ')} e "
                "NÃO entrega EFD Contribuições — o PIS/COFINS dela já está dentro do DAS. "
                "A obrigação mensal dessa empresa é o PGDAS-D."
            )

        declarado = self.REGIME_PIS_COFINS.get(self.cnpj)
        if not declarado:
            raise RegimeNaoDeclaradoError(
                f"O CNPJ {self.cnpj} não tem regime de PIS/COFINS declarado em "
                "`REGIME_PIS_COFINS`. Lucro Real NÃO implica não-cumulativo: vigilância e "
                "transporte de valores ficam no cumulativo (Lei 10.833, art. 10). "
                "Escriturar sem saber o regime produz arquivo legal errado com aparência "
                "de certo — declare o regime e a sua fonte antes de gerar."
            )
        self.regime, self.regime_fonte = declarado

        self.manager = SPEDContribuicoesManager(
            cnpj=self.cnpj,
            razao_social=self.razao_social,
            uf=self.uf,
            codigo_municipio=self.cod_municipio,
            inscricao_municipal=self.inscricao_municipal,
            inscricao_estadual=self.inscricao_estadual,
            regime=self.regime,
            contabilista=self._contabilista(),
        )
        logger.info(
            "SPEDContribuicoesService: CNPJ=%s regime=%s (%s)",
            self.cnpj, self.regime, self.regime_fonte,
        )

    def _contabilista(self) -> Contabilista:
        """O 0100 exige contabilista com CRC. Não existe campo para isso no banco, então
        ele sai VAZIO e o registro não é emitido — declarar um CRC inventado é pior que
        um arquivo que o contador completa."""
        return Contabilista()

    # ── carga ─────────────────────────────────────────────────────────────────────────
    def carregar_periodo(self, inicio: date, fim: date) -> dict[str, Any]:
        """Traz as NFS-e do CNPJ no período. Cancelada entra com COD_SIT 02 e fora da base."""
        conn = psycopg2.connect(_db_url())
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT n.numero, n.chave_acesso, n.competencia, n.data_emissao::date AS dt,
                           n.tomador_cnpj, coalesce(n.tomador_nome, '(sem nome)') AS tomador_nome,
                           coalesce(n.valor_servicos, 0) AS valor, coalesce(n.iss_valor, 0) AS iss,
                           coalesce(n.codigo_servico, '') AS cod, coalesce(n.descricao, '') AS descr,
                           coalesce(n.cancelada, FALSE) AS cancelada
                      FROM nfse_emitidas_nacional n
                      JOIN empresas e ON e.id = n.empresa_id
                     WHERE regexp_replace(e.cnpj, '[^0-9]', '', 'g') = %s
                       AND coalesce(n.ambiente, '') <> 'homologacao'
                       AND n.data_emissao::date BETWEEN %s AND %s
                     ORDER BY n.data_emissao, n.numero
                    """,
                    (self.cnpj, inicio, fim),
                )
                linhas = cur.fetchall()
        finally:
            conn.close()

        vistos: dict[str, str] = {}
        for i, r in enumerate(linhas, start=1):
            doc = _so_digitos(r["tomador_cnpj"])
            cod = vistos.get(doc)
            if not cod:
                cod = f"P{i:04d}"
                vistos[doc] = cod
                self.manager.adicionar_tomador(
                    Tomador(codigo=cod, nome=r["tomador_nome"][:100], cnpj_cpf=doc)
                )
            self.manager.adicionar_servico(
                ServicoPrestado(
                    numero=str(r["numero"]),
                    #: a série da DPS não vem no feed do ADN; o documento é identificado
                    #: pela CHAVE, que vem, e o campo fica vazio em vez de inventado
                    serie="",
                    chave=r["chave_acesso"] or "",
                    data_emissao=r["dt"],
                    tomador_codigo=cod,
                    valor_servico=Decimal(str(r["valor"])),
                    valor_iss=Decimal(str(r["iss"])),
                    codigo_servico=r["cod"],
                    descricao=r["descr"][:255],
                    situacao="02" if r["cancelada"] else "00",
                )
            )
        return {
            "documentos": len(linhas),
            "cancelados": sum(1 for r in linhas if r["cancelada"]),
            "tomadores": len(vistos),
        }

    # ── geração ───────────────────────────────────────────────────────────────────────
    def gerar_arquivo(self, inicio: date, fim: date) -> dict[str, Any]:
        carga = self.carregar_periodo(inicio, fim)
        conteudo = self.manager.gerar_arquivo(inicio, fim)
        linhas = conteudo.split("\r\n")
        return {
            "sucesso": True,
            "cnpj": self.cnpj,
            "empresa": self.razao_social,
            "regime": self.regime,
            "regime_fonte": self.regime_fonte,
            "periodo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
            **carga,
            "base_calculo": float(self.manager.receita_tributavel),
            "aliquota_pis": float(ALIQ_PIS_CUMULATIVO),
            "aliquota_cofins": float(ALIQ_COFINS_CUMULATIVO),
            "pis_apurado": float(self.manager.pis_apurado),
            "cofins_apurado": float(self.manager.cofins_apurado),
            "registros": len(linhas),
            "tamanho_bytes": len(conteudo.encode("latin-1", errors="replace")),
            "conteudo": conteudo,
            "assinado": False,
            "transmitido": False,
            "aviso": (
                "Arquivo NÃO assinado e NÃO transmitido. O registro 0100 (contabilista) "
                "sai ausente porque não há CRC cadastrado — quem assina completa."
            ),
        }
