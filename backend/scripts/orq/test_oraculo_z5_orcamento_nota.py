"""Oráculo — Do orçamento à nota: o emissor CONSOME, nunca cria (frente Z5, 24/09/2026).

Por que existe
--------------
O dono deu a regra em uma frase: *«os orçamentos são criados pelo Claude Cowork via conector
Conecta PRO MCP, até termos o sistema todo pronto. Não vai criar orçamento dentro do emissor de
nota: ou subo o arquivo, ou crio dentro do CRM etc. Obedecer o fluxo natural.»*

Uma regra assim morre em silêncio: basta a próxima sessão achar «prático» pôr um formulário de
«novo orçamento» na tela de nota fiscal, e ninguém percebe até o CRM e o fiscal terem duas
verdades sobre o mesmo cliente. Este oráculo é a trava dessa frase.

O segundo risco é aritmético: nota fiscal é documento irreversível. Um rascunho que perde um
centavo do orçamento de origem vira nota errada, e nota errada só se conserta com carta de
correção ou cancelamento. O terceiro é de rastro: nota sem origem rastreável é problema na
auditoria — o fiscal precisa saber de QUE proposta (ou de que arquivo, com hash) cada item veio.

O que afirma
------------
 1. **Soma ao centavo.** Para todo rascunho de origem `proposta`, a soma dos itens do rascunho é
    igual à soma dos itens da proposta de origem, ao centavo. Recontado por SQL próprio deste
    oráculo, não pelo serviço.
 2. **Produto não casado não vira item de nota sozinho.** `itens_para_nota()` RECUSA um rascunho
    que tenha item sem `produto_id`; depois que um humano casa o item, ele passa.
 3. **Idempotente por origem.** Gerar rascunho duas vezes do mesmo orçamento não duplica: devolve
    o mesmo id com `ja_existia = True`, e o banco continua com um rascunho ativo para a proposta.
 4. **O extrator devolve os campos obrigatórios e marca confiança.** A normalização do que o LLM
    responde (função pura, sem rede) preenche descrição/unidade/quantidade/valor, mantém o trecho
    de origem, põe `confianca` em [0,1] e descarta linha sem descrição ou sem valor.
 5. **O rascunho guarda a origem.** Nenhuma linha de `fiscal_nota_rascunho` sem `proposal_id`
    (origem proposta) ou sem `arquivo_nome` + `arquivo_hash` (origem arquivo).
 6. **Nenhuma rota desta frente cria orçamento.** Varredura estática dos arquivos da frente: nem
    `INSERT INTO proposals/proposal_items`, nem `Proposal(...)`/`ProposalItem(...)` do ORM. Esta é
    a afirmação que guarda a regra do dono.

Estado medido no nascimento (sandbox, 24/09/2026)
-------------------------------------------------
`modules.fiscal.services.orcamento_para_nota` não existia → ModuleNotFoundError, VERMELHO em
tudo. No banco: 37 propostas (3 `accepted`, 26 `draft`, 5 `rejected`, 3 `sent`), 177 itens,
0 rascunhos de nota, 0 NF-e autorizadas (2 rejeitadas de 11/04/2026).

Como roda
---------
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
      -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z5_orcamento_nota.py

Sai 0 = verde, 1 = vermelho. Fixtures marcadas `FIXTURE DGX Z5` e apagadas no fim (inclusive se
uma afirmação falhar).
"""

from __future__ import annotations

import ast
import asyncio
import re
import sys
from decimal import Decimal
from pathlib import Path

#: As telas desta frente entram na régua: `checar_nao_vigiado.py` conta como vigiada a
#: tela cujo slug um oráculo cita, e a onda fiscal nasceu com 40 descobertas. Citar num
#: comentário enganaria o contador — `conferir_telas` monta o builder e prova que a tela
#: existe e não é casca.
TELAS_DA_FRENTE = ("nfe-do-orcamento", "nfe-do-arquivo", "nfe-rascunhos", "nfe-rascunho-itens")
MODULO_DA_FRENTE = "fiscal"

#: Arquivos DESTA frente — a varredura do item 6 lê exatamente estes.
ARQUIVOS_DA_FRENTE = (
    "/app/modules/fiscal/services/orcamento_para_nota.py",
    "/app/modules/operacional/controllers/redesign_builders/dgx_z5_orcamento_nota.py",
)

#: O que jamais pode aparecer no código da frente. `proposals`/`proposal_items` são do CRM/MCP.
PROIBIDO = (
    (r"insert\s+into\s+\"?proposals\"?", "INSERT INTO proposals"),
    (r"insert\s+into\s+\"?proposal_items\"?", "INSERT INTO proposal_items"),
    (r"\bProposal\s*\(", "construtor ORM Proposal("),
    (r"\bProposalItem\s*\(", "construtor ORM ProposalItem("),
)

#: Soma dos itens da proposta, ao centavo, recontada aqui. Mesmo recorte do serviço (item ativo e
#: não-opcional), escrito de novo de propósito: o oráculo confere a régua, não a importa.
SQL_SOMA_PROPOSTA = """
SELECT coalesce(sum(round(i.total::numeric, 2)), 0)
  FROM proposal_items i
 WHERE i.proposal_id = CAST(:p AS uuid)
   AND coalesce(i.is_active, true) AND NOT coalesce(i.is_optional, false)
"""

SQL_SOMA_RASCUNHO = """
SELECT coalesce(sum(round(r.valor_total, 2)), 0)
  FROM fiscal_nota_rascunho_item r WHERE r.rascunho_id = CAST(:r AS uuid)
"""

#: Resposta CRUA plausível de um LLM lendo um orçamento em PDF — com o lixo que ele de fato
#: manda: linha de total, item sem valor, número com vírgula, confiança fora da faixa.
BRUTO_LLM = {
    "itens": [
        {
            "codigo": "CFTV-01",
            "descricao": "Câmera IP bullet 4MP com infravermelho",
            "unidade": "UN",
            "quantidade": "4",
            "valor_unitario": "1.250,00",
            "desconto_percent": "0",
            "confianca": 0.93,
            "trecho_origem": "4  CAMERA IP BULLET 4MP IR   1.250,00   5.000,00",
        },
        {
            "codigo": "",
            "descricao": "Instalação e configuração",
            "unidade": "SERV",
            "quantidade": "1",
            "valor_unitario": "800.00",
            "confianca": 1.4,
            "trecho_origem": "INSTALACAO E CONFIGURACAO  800,00",
        },
        {"descricao": "", "quantidade": "2", "valor_unitario": "10,00"},
        {"descricao": "TOTAL GERAL", "quantidade": "", "valor_unitario": ""},
    ],
    "documento": "orçamento de CFTV",
}


def _falha(lst: list[str], cond: bool, msg: str) -> None:
    if not cond:
        lst.append(msg)


def codigo_sem_prosa(fonte: str) -> str:
    """O fonte sem comentários e sem DOCSTRINGS — só o que executa.

    A 1ª versão desta varredura acusou o próprio serviço, porque o docstring dele CITA
    `INSERT INTO proposals` ao explicar a regra do dono. Apagar a explicação para calar o teste
    seria o pior dos dois mundos. Strings normais FICAM: o SQL da casa mora em string, e é
    justamente lá que um INSERT proibido apareceria.
    """
    linhas = fonte.splitlines()
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        arvore = None
    if arvore is not None:
        for no in ast.walk(arvore):
            corpo = getattr(no, "body", None)
            if not isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) or not corpo:
                continue
            p = corpo[0]
            if isinstance(p, ast.Expr) and isinstance(p.value, ast.Constant) and isinstance(p.value.value, str):
                for i in range(p.lineno - 1, (p.end_lineno or p.lineno)):
                    linhas[i] = ""
    return "\n".join(ln for ln in linhas if not ln.lstrip().startswith("#"))


async def main() -> int:  # noqa: C901 — seis afirmações, cada uma curta
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.fiscal.services import orcamento_para_nota as z5

    falhas: list[str] = []
    medidas: list[str] = []

    # ── 6) varredura estática: nenhuma rota da frente cria orçamento ────────────────────────
    vistos = 0
    for caminho in ARQUIVOS_DA_FRENTE:
        p = Path(caminho)
        if not p.exists():  # fora do container: tenta relativo à raiz do repo
            p = Path(__file__).resolve().parents[2] / caminho.removeprefix("/app/")
        if not p.exists():
            falhas.append(f"arquivo da frente não encontrado para varrer: {caminho}")
            continue
        vistos += 1
        codigo = codigo_sem_prosa(p.read_text(encoding="utf-8"))
        for padrao, rotulo in PROIBIDO:
            if re.search(padrao, codigo, re.I):
                falhas.append(f"{p.name}: {rotulo} — a frente NÃO pode criar orçamento (regra do dono)")
    _falha(falhas, vistos == len(ARQUIVOS_DA_FRENTE), f"varreu {vistos}/{len(ARQUIVOS_DA_FRENTE)} arquivos da frente")
    medidas.append(f"varredura estática: {vistos} arquivo(s)")

    # ── 4) o extrator marca confiança e devolve os campos obrigatórios (função pura) ────────
    itens_llm = z5.normalizar_itens_extraidos(BRUTO_LLM)
    _falha(falhas, len(itens_llm) == 2, f"normalização devolveu {len(itens_llm)} item(ns); esperado 2 (2 linhas-lixo)")
    for it in itens_llm:
        for campo in ("descricao", "unidade", "quantidade", "valor_unitario", "valor_total", "confianca"):
            _falha(falhas, campo in it, f"item extraído sem o campo obrigatório {campo!r}")
        _falha(falhas, bool(it.get("trecho_origem")), "item extraído sem o trecho de origem")
        c = it.get("confianca")
        _falha(falhas, isinstance(c, float) and 0.0 <= c <= 1.0, f"confiança fora de [0,1]: {c!r}")
    if len(itens_llm) == 2:
        # "1.250,00" (pt-BR) × 4 = 5.000,00 — o ponto é separador de milhar, não decimal
        _falha(
            falhas,
            itens_llm[0]["valor_total"] == Decimal("5000.00"),
            f"total do 1º item extraído: {itens_llm[0]['valor_total']} (esperado 5000.00 — vírgula decimal pt-BR)",
        )
        _falha(
            falhas,
            itens_llm[1]["valor_total"] == Decimal("800.00"),
            f"total do 2º item extraído: {itens_llm[1]['valor_total']} (esperado 800.00)",
        )
    medidas.append(f"extrator: {len(itens_llm)} item(ns) de {len(BRUTO_LLM['itens'])} linhas cruas")

    fixtures: list[str] = []
    async with async_session_factory() as db:
        from _telas import conferir_telas  # noqa: PLC0415 — irmão em scripts/orq

        falhas.extend(await conferir_telas(db, MODULO_DA_FRENTE, TELAS_DA_FRENTE))
        await z5.ensure_schema(db)

        # ── 1+3) fixture a partir de uma proposta REAL (leitura), soma e idempotência ───────
        prop = (
            await db.execute(
                text(
                    "SELECT p.id::text, p.number FROM proposals p "
                    " WHERE p.status = ANY(:st) "
                    "   AND EXISTS (SELECT 1 FROM proposal_items i WHERE i.proposal_id = p.id "
                    "               AND coalesce(i.is_active,true) AND NOT coalesce(i.is_optional,false)) "
                    "   AND NOT EXISTS (SELECT 1 FROM fiscal_nota_rascunho r WHERE r.proposal_id = p.id "
                    "                   AND r.status <> 'cancelado') "
                    " ORDER BY p.number LIMIT 1"
                ),
                {"st": list(z5.STATUS_FATURAVEIS)},
            )
        ).first()
        if not prop:
            falhas.append(
                "nenhuma proposta faturável livre para a fixture "
                f"(status {z5.STATUS_FATURAVEIS}) — o item 1 e o 3 não puderam ser medidos"
            )
        else:
            pid, pnum = prop
            r1 = await z5.preparar_rascunho(db, "proposta", proposal_id=pid, observacao="FIXTURE DGX Z5")
            fixtures.append(r1["id"])
            _falha(falhas, not r1.get("ja_existia"), "1º preparar_rascunho já disse que existia")

            soma_prop = (await db.execute(text(SQL_SOMA_PROPOSTA), {"p": pid})).scalar_one()
            soma_rasc = (await db.execute(text(SQL_SOMA_RASCUNHO), {"r": r1["id"]})).scalar_one()
            _falha(
                falhas,
                Decimal(str(soma_prop)) == Decimal(str(soma_rasc)),
                f"soma do rascunho {soma_rasc} ≠ soma dos itens de {pnum} = {soma_prop}",
            )
            medidas.append(f"fixture {pnum}: itens somam R$ {soma_prop} no orçamento e R$ {soma_rasc} no rascunho")

            # 3) idempotência por origem
            r2 = await z5.preparar_rascunho(db, "proposta", proposal_id=pid, observacao="FIXTURE DGX Z5")
            _falha(falhas, r2["id"] == r1["id"], f"2ª chamada criou outro rascunho ({r2['id']} ≠ {r1['id']})")
            _falha(falhas, bool(r2.get("ja_existia")), "2ª chamada não avisou que o rascunho já existia")
            n = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM fiscal_nota_rascunho "
                        " WHERE proposal_id = CAST(:p AS uuid) AND status <> 'cancelado'"
                    ),
                    {"p": pid},
                )
            ).scalar_one()
            _falha(falhas, n == 1, f"{n} rascunhos ativos para {pnum} — deveria ser 1 (idempotente por origem)")

        # ── 2) item sem produto casado não vira item de nota ────────────────────────────────
        rasc_arq = await z5.preparar_rascunho(
            db,
            "arquivo",
            arquivo_nome="FIXTURE_DGX_Z5_orcamento.pdf",
            arquivo_bytes=b"FIXTURE DGX Z5 -- orcamento de teste do oraculo",
            itens=await z5.casar_produtos(db, itens_llm),
            cliente_nome="FIXTURE DGX Z5",
            observacao="FIXTURE DGX Z5",
        )
        fixtures.append(rasc_arq["id"])
        pendentes = (
            await db.execute(
                text(
                    "SELECT count(*) FROM fiscal_nota_rascunho_item "
                    " WHERE rascunho_id = CAST(:r AS uuid) AND produto_id IS NULL"
                ),
                {"r": rasc_arq["id"]},
            )
        ).scalar_one()
        if not pendentes:
            falhas.append("fixture de arquivo nasceu com todos os itens casados — item 2 não pôde ser medido")
        else:
            try:
                await z5.itens_para_nota(db, rasc_arq["id"])
                falhas.append(f"itens_para_nota ACEITOU rascunho com {pendentes} item(ns) sem produto casado")
            except z5.ProdutoNaoCasadoError as e:
                medidas.append(f"recusa correta: {pendentes} item(ns) sem produto — «{str(e)[:60]}»")

            # o humano escolhe → passa a valer. Produto de fixture, apagado no fim.
            if await z5.cadastro_de_produto_existe(db):
                prod = (await db.execute(text("SELECT id FROM fin_produtos ORDER BY id LIMIT 1"))).scalar()
                if prod is not None:
                    ids = [
                        r[0]
                        for r in (
                            await db.execute(
                                text(
                                    "SELECT id::text FROM fiscal_nota_rascunho_item "
                                    " WHERE rascunho_id = CAST(:r AS uuid) AND produto_id IS NULL"
                                ),
                                {"r": rasc_arq["id"]},
                            )
                        ).fetchall()
                    ]
                    for iid in ids:
                        await z5.casar_item_manual(db, iid, int(prod), usuario="oraculo-z5")
                    try:
                        prontos = await z5.itens_para_nota(db, rasc_arq["id"])
                        _falha(
                            falhas,
                            len(prontos) == len(ids),
                            f"depois do humano casar, itens_para_nota devolveu {len(prontos)} de {len(ids)}",
                        )
                        medidas.append(f"depois do humano casar: {len(prontos)} item(ns) liberados")
                    except z5.ProdutoNaoCasadoError as e:
                        falhas.append(f"itens_para_nota recusou mesmo com todos casados: {e}")
            else:
                medidas.append("fin_produtos ausente (Z1 ainda não entregou) — meia-prova do item 2: só a recusa")

        # ── 5) todo rascunho guarda a origem ───────────────────────────────────────────────
        sem_origem = (
            await db.execute(
                text(
                    "SELECT count(*) FROM fiscal_nota_rascunho "
                    " WHERE (origem_tipo = 'proposta' AND proposal_id IS NULL) "
                    "    OR (origem_tipo = 'arquivo' AND (coalesce(arquivo_nome,'') = '' "
                    "        OR coalesce(arquivo_hash,'') = '')) "
                    "    OR origem_tipo NOT IN ('proposta','arquivo')"
                )
            )
        ).scalar_one()
        _falha(falhas, sem_origem == 0, f"{sem_origem} rascunho(s) sem origem rastreável")
        total_rasc = (await db.execute(text("SELECT count(*) FROM fiscal_nota_rascunho"))).scalar_one()

        # ── 1) a soma fecha para TODO rascunho de proposta, não só o da fixture ─────────────
        divergentes = (
            await db.execute(
                text(
                    "SELECT r.id::text, coalesce(p.number,'?'), "
                    "       coalesce((SELECT sum(round(i.valor_total,2)) FROM fiscal_nota_rascunho_item i "
                    "                  WHERE i.rascunho_id = r.id), 0), "
                    "       coalesce((SELECT sum(round(pi.total::numeric,2)) FROM proposal_items pi "
                    "                  WHERE pi.proposal_id = r.proposal_id "
                    "                    AND coalesce(pi.is_active,true) "
                    "                    AND NOT coalesce(pi.is_optional,false)), 0) "
                    "  FROM fiscal_nota_rascunho r LEFT JOIN proposals p ON p.id = r.proposal_id "
                    " WHERE r.origem_tipo = 'proposta' AND r.status <> 'cancelado'"
                )
            )
        ).fetchall()
        for rid, num, s_r, s_p in divergentes:
            _falha(falhas, Decimal(str(s_r)) == Decimal(str(s_p)), f"rascunho {rid[:8]} de {num}: {s_r} ≠ {s_p}")
        medidas.append(f"{len(divergentes)} rascunho(s) de proposta conferido(s) ao centavo · {total_rasc} no total")

        # ── limpeza das fixtures ───────────────────────────────────────────────────────────
        for rid in fixtures:
            await db.execute(
                text("DELETE FROM fiscal_nota_rascunho_item WHERE rascunho_id = CAST(:r AS uuid)"), {"r": rid}
            )
        await db.execute(text("DELETE FROM fiscal_nota_rascunho WHERE observacao LIKE 'FIXTURE DGX Z5%'"))
        await db.commit()
        sobrou = (
            await db.execute(text("SELECT count(*) FROM fiscal_nota_rascunho WHERE observacao LIKE 'FIXTURE DGX Z5%'"))
        ).scalar_one()
        _falha(falhas, sobrou == 0, f"{sobrou} fixture(s) DGX Z5 sobraram no banco")

    for m in medidas:
        print("·", m)
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) entre o orçamento e o rascunho de nota")
    print(
        "OK Z5: o emissor consome orçamento (proposta ou arquivo), soma ao centavo, guarda a origem e NÃO cria orçamento"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        print("TOTAL desvios: >=1")
        sys.exit(1)
