"""Que documento fiscal cada CNPJ do grupo emite — e, quando não emite, por quê.

**Por que existe.** Até 24/09/2026 o emissor de NF-e recusava a CONECTAMAIS PATRIMONIAL
com `EMITENTE_INCOMPLETO / falta: inscrição estadual, CEP` — texto que manda a pessoa
completar um cadastro. Só que não é cadastro incompleto: **é decisão do dono.** Jordan
Jesus, 24/09/2026:

    «a patrimonial tem apenas inscrição municipal, homologa também.
     nf de serviço e nf de produto pra eletronica e nf de serviço para a patrimonial»

A Patrimonial vende serviço — vigilância, portaria, limpeza — e o documento dela é a
NFS-e. Ela não vai emitir NF-e modelo 55, hoje nem depois de tirar inscrição estadual,
a menos que o dono mude de ideia. Uma recusa que diz «complete o cadastro» faz alguém
gastar o dia atrás de uma IE que ninguém pediu.

**Por que é dado e não `if`.** A regra mora na própria linha da empresa, ao lado da
`inscricao_estadual` que a motivou. Mudar a decisão é um UPDATE numa linha — um lugar só,
e o mesmo lugar onde já vive toda a identidade fiscal da empresa (foi o que a frente Z2
estabeleceu: nada de identidade fiscal chumbado em Python).

    UPDATE empresas SET emite_nfe_produto = true, motivo_nao_emite_nfe_produto = NULL
     WHERE slug = 'conecta_patrimonial';

O padrão (`DEFAULT true`) é emitir: empresa nova não nasce bloqueada por omissão.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text as sqltext
from sqlalchemy.ext.asyncio import AsyncSession

#: A decisão, com autor e data dentro do próprio texto que o usuário vai ler.
MOTIVO_PATRIMONIAL = (
    "A CONECTAMAIS PATRIMONIAL não emite NF-e de produto (modelo 55). Ela tem apenas "
    "inscrição MUNICIPAL (721042001) e o que vende é serviço — vigilância, portaria e "
    "limpeza. Decisão de Jordan Jesus em 24/09/2026. O documento fiscal dela é a NFS-e: "
    "use a tela «Emitir NFS-e (serviço)», no grupo Notas fiscais do módulo Fiscal."
)

#: Para onde mandar quem tentou o documento errado. Tela da frente Z7.
TELA_NFSE = "/redesign/fiscal?t=nfse-emitir-dps"

_DDL = (
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS emite_nfe_produto boolean NOT NULL DEFAULT true",
    "ALTER TABLE empresas ADD COLUMN IF NOT EXISTS motivo_nao_emite_nfe_produto text",
)


class DocumentoNaoPermitido(Exception):  # noqa: N818 — o nome é a frase que o usuário lê
    """A empresa não emite esse documento — por decisão, não por falta de cadastro."""

    def __init__(self, msg: str, *, empresa: str, documento: str, tela: str) -> None:
        super().__init__(msg)
        self.code = "DOCUMENTO_NAO_E_DESTA_EMPRESA"
        self.empresa = empresa
        self.documento = documento
        self.tela = tela


async def _ensure(db: AsyncSession) -> None:
    """DDL idempotente + a decisão de 24/09/2026, semeada só se ninguém decidiu ainda.

    O `WHERE emite_nfe_produto` no UPDATE é o que torna a semente inofensiva: se o dono
    já tiver religado a Patrimonial, rodar `_ensure` de novo não desfaz a escolha dele.
    """
    for sql in _DDL:
        await db.execute(sqltext(sql))
    await db.execute(
        sqltext(
            "UPDATE empresas SET emite_nfe_produto = false, motivo_nao_emite_nfe_produto = :m"
            " WHERE slug = 'conecta_patrimonial'"
            "   AND emite_nfe_produto"
            "   AND motivo_nao_emite_nfe_produto IS NULL"
        ),
        {"m": MOTIVO_PATRIMONIAL},
    )
    await db.commit()


async def politica(db: AsyncSession, *, slug: str | None = None, cnpj: str | None = None) -> dict[str, Any]:
    """O que esta empresa emite, lido de `empresas`. Sem linha = sem opinião."""
    await _ensure(db)
    import re

    _SEL = (
        "SELECT slug, razao_social, coalesce(emite_nfe_produto, true) AS nfe55,"
        " motivo_nao_emite_nfe_produto AS motivo FROM empresas WHERE "
    )
    if slug:
        sql, p = _SEL + "slug = :v", {"v": slug}
    else:
        sql, p = _SEL + "regexp_replace(cnpj,'\\D','','g') = :v", {"v": re.sub(r"\D", "", cnpj or "")}
    linha = (await db.execute(sqltext(sql), p)).mappings().first()
    if not linha:
        return {"slug": slug or cnpj, "nfe55": True, "nfse": True, "motivo": None}
    return {
        "slug": linha["slug"],
        "razao_social": linha["razao_social"],
        "nfe55": bool(linha["nfe55"]),
        # NFS-e: as duas empresas emitem — decisão do dono na mesma frase. Não há campo
        # porque não há caso de não emitir; o dia em que houver, ele nasce aqui do lado.
        "nfse": True,
        "motivo": linha["motivo"],
    }


async def exigir_nfe_produto(db: AsyncSession, *, slug: str | None = None, cnpj: str | None = None) -> None:
    """Levanta `DocumentoNaoPermitido` se esta empresa não emite NF-e modelo 55."""
    pol = await politica(db, slug=slug, cnpj=cnpj)
    if pol["nfe55"]:
        return
    raise DocumentoNaoPermitido(
        pol["motivo"] or f"{pol.get('razao_social') or pol['slug']} não emite NF-e de produto (modelo 55).",
        empresa=str(pol["slug"]),
        documento="nfe55",
        tela=TELA_NFSE,
    )
