"""Registro de teste na base que o dono consulta — marcado, filtrado, nunca apagado.

O PROBLEMA (BUG-07, 30/09/2026)
«AA2-FIXTURE DGX AA2 / Cliente de fixture / R$ 2.501,00» era o PRIMEIRO item de
`listar_propostas`. O lead «QA Bateria E2E 14/09 / CONDOMINIO TESTE QA» estava no funil.
O dono abre a listagem para decidir e lê lixo de teste misturado com R$ 100 mil de
negócio real.

A DECISÃO: MARCAR E FILTRAR, NÃO APAGAR
Jordan foi explícito («Não apague nada sem me perguntar»), e ele tem razão além da
cautela: PROP-2026-00098, 00118, 00123 e 00124 foram criadas por ELE testando o fluxo —
são registro do que foi exercitado, e apagar perderia essa história. O que incomoda não é
existirem, é aparecerem.

`fixture = true` some da listagem padrão. `incluir_fixtures=true` traz de volta. Nada
sai da base, e desmarcar é um UPDATE.

POR QUE A MARCA É COLUNA E NÃO REGEX NA HORA DE LER
Filtrar por padrão de nome esconderia uma proposta REAL chamada «Teste de carga —
Condomínio X» no dia em que ela existir, e ninguém descobriria: o defeito seria ausência
silenciosa numa listagem. A regex decide UMA VEZ, na marcação, e o resultado fica à vista
e reversível na coluna.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Assinaturas de registro de teste. Usadas para MARCAR (uma vez, com a lista à vista) e
#: pela trava `checar_fixture_viva`, nunca para filtrar leitura.
#: `qa ` e `teste` com espaço/limite de palavra: sem isso «Toscana» casa com «qa».
ASSINATURA = r"(fixture|lixo-|\mqa\M|\mteste\M|\mtestes\M|e2e|\mdgx\M|não usar|nao usar)"

#: Onde a marca vive. Tabela → coluna(s) de texto que carregam a assinatura.
ALVOS = {
    "proposals": ("title", "client_name", "number"),
    "leads": ("name", "company"),
}

DDL = tuple(f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS fixture boolean NOT NULL DEFAULT false" for t in ALVOS) + (
    "COMMENT ON COLUMN proposals.fixture IS "
    "'Registro de TESTE (30/09/2026). Some das listagens; `incluir_fixtures=true` traz de "
    "volta. Marcado uma vez por assinatura de nome, nunca filtrado por regex na leitura — "
    "senão uma proposta real chamada Teste sumiria em silêncio.'",
)


async def garantir_colunas(db: AsyncSession) -> None:
    for ddl in DDL:
        await db.execute(text(ddl))
    await db.commit()


def _where_assinatura(colunas: tuple[str, ...]) -> str:
    return " OR ".join(f"coalesce({c},'') ~* :re" for c in colunas)


async def candidatos(db: AsyncSession, tabela: str) -> list[dict]:
    """Linhas que PARECEM teste e ainda não estão marcadas. Não marca nada."""
    cols = ALVOS[tabela]
    rs = await db.execute(
        text(
            f"SELECT id::text AS id, {', '.join(cols)} FROM {tabela} "  # noqa: S608 — `tabela` vem de ALVOS
            f" WHERE coalesce(fixture,false) = false AND ({_where_assinatura(cols)})"
            f" ORDER BY created_at DESC"
        ),
        {"re": ASSINATURA},
    )
    return [dict(r) for r in rs.mappings().all()]


async def marcar(db: AsyncSession, tabela: str, ids: list[str]) -> int:
    if not ids:
        return 0
    r = await db.execute(
        text(f"UPDATE {tabela} SET fixture = true WHERE id::text = ANY(:ids)"),  # noqa: S608
        {"ids": ids},
    )
    await db.commit()
    return r.rowcount or 0
