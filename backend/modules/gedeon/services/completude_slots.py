"""A completude do kit — UMA fórmula, um dono.

🔴 O DEFEITO, medido em 14/08/2026 no banco de produção. O painel do GEDEON anunciava:

    competência   kits   completude gravada   completude pela PRÓPRIA fórmula
    2026-07        11           7,7%                    53,4%
    2026-06        10          20,9%                    43,5%
    2026-05        11          12,2%                    93,7%   ← 93,7, anunciando 12,2

**Maio estava 93,7% montado e o sistema dizia 12,2%.** 49 dos 52 kits divergiam. E a conta
que revela isso é a MESMA que o código já usava — `slot com arquivo ÷ total_documents`. Não
havia erro de fórmula: o número estava VELHO.

Por quê: o percentual só era recalculado dentro do `Hermes.processar_mes`, que roda pelo beat
do **dia 1 às 09:00**. Os arquivos entram durante o mês inteiro — pelo `kit_pdf_controller`,
que preenche o slot e vai embora sem recalcular nada. O percentual congela no que era quando
o kit nasceu; vários ficaram em `0.00` com todos os slots cheios.

A cadeia que isso alimenta é a que trava o módulo: completude falsa → o kit nunca chega a
100% → ninguém aprova → nada é enviado → **o cliente continua cobrando na mão.** 55 kits
montados, ZERO aprovados, UM enviado em oito meses.

POR QUE UM MÓDULO SÓ, e não uma linha em cada lugar: a fórmula vivia em `hermes.py:544` e os
outros dois pontos de escrita simplesmente não a tinham. Duas cópias divergem na primeira
mudança; três, mais rápido ainda. Aqui ela tem um dono, e quem preenche slot chama.

⚠️ NÃO CONFUNDA com `kit_completude_service`, que é outra coisa: aquele lê as pastas do
Google Drive e classifica por NOME de arquivo — é a visão de conferência, não o número
gravado. Arquivo de Drive não tem coluna de tipo; casar por nome ali é a única informação
que existe. Consertar aquele não move este número em um ponto sequer.
"""

from __future__ import annotations

from sqlalchemy import text

#: A conta, escrita uma vez.
#:
#: ⚠️ `total_documents` NÃO é meta nem template: é um espelho da contagem de slots — e
#: espelho envelhece. Em 18/08/2026, depois que o montador voltou a criar slots (o defeito
#: das duas tabelas de cliente), 14 kits ficaram com o declarado diferente do real:
#: Prime Arena declarava 7 com 25 slots e anunciou **357%**; o Mirante declarava 0 com 18
#: slots cheios e ficou em **0%**, fora do UPDATE por causa do antigo `total_documents > 0`.
#:
#: Por isso o número é REFRESCADO aqui, na mesma conta que o usa. Dividir por um valor
#: guardado por outra pessoa em outro momento é confiar em convenção; contar é ler a fonte.
# ─────────────────────────────────────────────────────────────────────────────
# A RÉGUA DO CONTRATO, DO LADO DO BANCO
#
# Até 19/08/2026 este módulo respondia "todo slot criado tem arquivo?" — e como o slot só
# nasce quando o documento é ENCONTRADO, a resposta tendia a 100% por construção. O Drive
# respondia outra coisa: "o kit está completo perante o contrato?" — 50%. Duas telas, dois
# números, e o Jordan conferindo sem saber em qual acreditar.
#
# Agora os dois lados usam a MESMA régua: os 10 blocos de `kit_completude_service.CHECKLIST`,
# recortados pelo contrato de cada cliente. O banco continua sendo o banco (conta slots) e o
# Drive continua lendo pasta — o que passa a ser comum é a PERGUNTA.
#
# Este mapa é a única tradução entre os 66 `document_type` do banco e os 10 blocos. Tipo
# desconhecido não entra em bloco nenhum: não inventa cobertura.
_BLOCO_DE_TIPO: dict[str, str] = {
    "folha_pagamento": "folha",
    "contracheque": "contracheque",
    "contracheques_consolidado": "contracheque",
    "recibo_folha": "contracheque",
    "comp_salario_individual": "salario",
    "comprovante_salario": "salario",
    "folha_ponto": "ponto",
    "folhas_ponto": "ponto",
    "folhas_ponto_consolidado": "ponto",
    "ponto": "ponto",
    # 09/09/2026 (Jordan): "a escala não vai no kit, pode excluir inclusive este documento".
    # Enquanto ela satisfazia o bloco `ponto`, um kit COM escala e SEM folha de ponto lia como
    # se tivesse o ponto. Hoje não há nenhum kit nessa situação — sai antes de haver.
    "comprovante_vt": "vavt",
    "comprovante_va": "vavt",
    "comprovante_vr": "vavt",
    "vale_vt_vr": "vavt",
    "comp_vt_individual": "vavt",
    "comp_va_solides": "vavt",
    "comp_vt_va_combinado": "vavt",
    "recibo_vt_va": "vavt",
    "declaracao_vt": "vavt",
    "relatorio_pedido_va": "vavt",
    "fgts_guia": "guias",
    "fgts_relatorio": "guias",
    "gfd_fgts": "guias",
    "gfd_fgts_mensal": "guias",
    "relatorio_gfd_fgts": "guias",
    "comp_pag_fgts": "guias",
    "comprovante_fgts": "guias",
    "dctfweb_declaracao": "guias",
    "dctfweb_recibo": "guias",
    "dctfweb_extrato": "guias",
    "dctf_declaracao": "guias",
    "dctf_recibo": "guias",
    "dctf_extrato": "guias",
    "guia_issqn": "guias",
    "inss_guia": "inss",
    "inss_mensal": "inss",
    "cnd_estadual": "cnd",
    "cnd_federal": "cnd",
    "cnd_municipal": "cnd",
    "cnd_trabalhista": "cnd",
    "cndt_trabalhista": "cnd",
    "cnd_sefaz": "cnd",
    "cnd_caixa": "cnd",
    "cnd_prefeitura": "cnd",
    "cnd_rfb": "cnd",
    "cnd_receita": "cnd",
    "crf_fgts": "cnd",
    "certidao": "cnd",
    # 10/09/2026 — GUIAS que o kit tem e a régua não contava. Medido: 22 tipos com pasta no Drive
    # e bloco NENHUM, ou seja, o documento chega ao cliente e a completude o ignora. É metade da
    # explicação para "55 kits montados, ZERO aprovados" — o kit não fechava porque a régua não
    # enxergava o que estava lá.
    "das_simples_nacional": "guias",
    "parcelamento_simples": "guias",
    "grf_fgts": "guias",
    "gfip_sefip": "guias",
    "dar_sefaz": "guias",
    "dctfweb_resumo_creditos": "guias",
    "dctfweb_resumo_debitos": "guias",
    "dctfweb_creditos": "guias",
    "dctfweb_debitos": "guias",
    "gps_inss": "inss",
    # 09/09/2026 (lista da Pyetra): o bloco de benefícios do kit real tem CINCO documentos da
    # empresa além do recibo do funcionário — a compra dos créditos, o pedido por colaborador e o
    # comprovante de pagamento de cada portal.
    "boleto_vt_sinetram": "vavt",
    "relatorio_vt_sinetram": "vavt",
    "relatorio_va_solides": "vavt",
    "comprovante_pagto_sinetram": "vavt",
    "comprovante_pagto_solides": "vavt",
    "nfse": "nfse",
    "nota_fiscal": "nfse",
    "nfs_servico": "nfse",
    "boleto": "boleto",
    "boleto_nfse": "boleto",
}

#: Quantas CNDs o bloco "cnd" exige para valer 1 ponto — igual ao CHECKLIST do Drive.
_CND_ESPERADO = 5

_VALUES_MAPA = ", ".join(f"('{t}','{b}')" for t, b in sorted(_BLOCO_DE_TIPO.items()))

#: Cliente responde por documento trabalhista? Mesma regra do Drive: contrato de mão de
#: obra (ou kit_mensal) E gente de fato alocada. A ponte de cliente é por CNPJ/nome porque
#: `ged_document_kits.client_id` aponta para `ged_clients` e `contracts.client_id` para
#: `clients` — duas tabelas sem FK entre si.
_SQL_RECALC = r"""
WITH mapa(document_type, bloco) AS (VALUES {values}),
cliente AS (
  SELECT k.id AS kit_id, c.id AS client_id
    FROM ged_document_kits k
    JOIN ged_clients g ON g.id = k.client_id
    LEFT JOIN clients c ON (
         (coalesce(g.cnpj,'') <> '' AND coalesce(c.document_number,'') <> ''
          AND regexp_replace(g.cnpj,'\D','','g') = regexp_replace(c.document_number,'\D','','g'))
      OR upper(btrim(g.name)) = upper(btrim(c.name)))
   WHERE {filtro}
),
regua AS (
  SELECT cl.kit_id,
         CASE WHEN EXISTS (
                SELECT 1 FROM contracts ct
                 WHERE ct.client_id = cl.client_id AND ct.status::text = 'active'
                   AND (coalesce(ct.kit_mensal,false) OR coalesce(ct.tipo_servico,'') = 'maodeobra'))
              AND EXISTS (
                SELECT 1 FROM posts p JOIN allocations a ON a.post_id = p.id AND a.status = 'active'
                 WHERE p.client_id = cl.client_id)
              THEN ARRAY['folha','contracheque','salario','ponto','vavt','guias','inss','cnd','nfse','boleto']
              ELSE ARRAY['cnd','nfse','boleto']
         END AS blocos
    FROM cliente cl
),
credito AS (
  SELECT r.kit_id,
         sum(LEAST(cnt, CASE WHEN b.bloco = 'cnd' THEN {cnd} ELSE 1 END)::numeric
             / CASE WHEN b.bloco = 'cnd' THEN {cnd} ELSE 1 END) AS score
    FROM regua r
    CROSS JOIN LATERAL unnest(r.blocos) AS b(bloco)
    LEFT JOIN LATERAL (
      SELECT count(*) AS cnt
        FROM ged_kit_documents d JOIN mapa m ON m.document_type = d.document_type
       WHERE d.kit_id = r.kit_id AND m.bloco = b.bloco
         AND d.file_path IS NOT NULL AND d.file_path <> ''
    ) ct ON true
   GROUP BY r.kit_id
)
UPDATE ged_document_kits k
   SET total_documents = (SELECT count(*) FROM ged_kit_documents d WHERE d.kit_id = k.id),
       completion_percentage = LEAST(100, round(100.0 * coalesce(cr.score,0)
                                / GREATEST(array_length(r.blocos,1),1), 2)),
       updated_at = now()
  FROM regua r LEFT JOIN credito cr ON cr.kit_id = r.kit_id
 WHERE k.id = r.kit_id
"""

_SQL_UM_KIT = text(_SQL_RECALC.format(values=_VALUES_MAPA, cnd=_CND_ESPERADO, filtro="k.id = CAST(:kit_id AS uuid)"))

# Sem o antigo `AND total_documents > 0`: era ele que deixava o kit zerado FORA do
# recálculo — justo o kit que mais precisava. Kit sem slot nenhum cai em 0% pelo coalesce.
_SQL_COMPETENCIA = text(
    _SQL_RECALC.format(values=_VALUES_MAPA, cnd=_CND_ESPERADO, filtro="k.reference_month = CAST(:ref_date AS date)")
)


def recalcular_kit(db, kit_id) -> int:
    """Recalcula a completude de UM kit. Chame logo depois de preencher um slot.

    Recebe a sessão de quem chamou e NÃO faz commit: o recálculo tem de entrar na mesma
    transação que gravou o `file_path`. Se entrasse em transação própria, um rollback do
    chamador deixaria o percentual falando de um arquivo que não existe.
    """
    return db.execute(_SQL_UM_KIT, {"kit_id": str(kit_id)}).rowcount


def recalcular_competencia(db, ref_date: str) -> int:
    """Recalcula todos os kits de uma competência (`AAAA-MM-01`). Sem commit, igual."""
    return db.execute(_SQL_COMPETENCIA, {"ref_date": ref_date}).rowcount


async def recalcular_kit_async(db, kit_id) -> int:
    """Mesma conta, para quem tem `AsyncSession`. O SQL é o mesmo objeto — não há segunda
    fórmula aqui, só o `await`."""
    return (await db.execute(_SQL_UM_KIT, {"kit_id": str(kit_id)})).rowcount


async def recalcular_competencia_async(db, ref_date: str) -> int:
    return (await db.execute(_SQL_COMPETENCIA, {"ref_date": ref_date})).rowcount
