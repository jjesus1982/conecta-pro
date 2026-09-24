"""Do orçamento à nota — o emissor CONSOME orçamento, nunca cria (frente DGX Z5, 24/09/2026).

A regra do dono, literal:

    «os orçamentos são criados pelo Claude Cowork via conector Conecta PRO MCP, até termos o
     sistema todo pronto. Não vai criar orçamento dentro do emissor de nota: ou subo o arquivo,
     ou crio dentro do CRM etc. Obedecer o fluxo natural.»

Portanto este módulo tem DUAS portas de entrada e nenhuma outra:

  (A) **Uma proposta que já existe** — `proposals` + `proposal_items`, criadas no CRM ou pelo
      Cowork via MCP (`criar_proposta`, `gerar_orcamento`, `criar_propostas_lote`).
  (B) **Um arquivo** — PDF, planilha ou foto do orçamento, lido pelo extrator.

Não há função que crie proposta aqui, e o oráculo `test_oraculo_z5_orcamento_nota.py` varre este
arquivo atrás de `INSERT INTO proposals/proposal_items` e dos construtores do ORM. Se você veio
acrescentar «criar orçamento aqui», o lugar certo é o CRM ou a ferramenta MCP.

O que foi cavado ANTES de construir (sandbox = cópia de produção de 23/09):

  · `purchase_quotations` (4 linhas) NÃO serve: é cotação de COMPRA (fornecedor → nós). A direção
    é contrária à da nota de saída. Fonte é `proposals` (37) + `proposal_items` (177).
  · O extrator de documento por LLM **já existe** e é o padrão da casa: o `POST /action/
    extrair-documento` do `departamento_pessoal.py`, com `_imagens_do_arquivo()` resolvendo o que
    é difícil (magic bytes em vez de extensão, recusa explicada do HEIC do iPhone, PDF escaneado
    rasterizado com fitz). Aqui esse mecanismo é REUSADO com um alvo novo — `orcamento` —, e só o
    prompt e a normalização são novos, porque o alvo devolve uma LISTA de itens e não um registro
    de campos planos como os alvos do DP.
  · O cadastro fiscal do produto (`fin_produtos`, frente Z1) é lido, nunca escrito: item que não
    casa volta com `produto_id = None` e a sugestão de NCM. **Nunca cria produto sozinho** — NCM
    errado foi exatamente o motivo da última rejeição da SEFAZ (11/04/2026, «NCM inexistente»).

O rascunho mora em tabela PRÓPRIA (`fiscal_nota_rascunho` + `_item`) e não em `nfes`, por uma
razão medida: `nfes` exige endereço completo do destinatário, CRT do emitente, forma e meio de
pagamento — tudo NOT NULL. Um orçamento não traz nada disso, e preencher com placeholder seria
inventar dado fiscal. Além disso `nfes` é território da Z2, que ainda está escolhendo entre os
dois emissores do repositório. A ponte é a coluna `nfe_id`: quando a Z3 abrir o rascunho e
emitir, grava o id da NF-e ali e o rastro fecha.
"""

from __future__ import annotations

import difflib
import hashlib
import logging
import os
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Estágio em que uma proposta pode virar nota. `accepted` = o cliente aceitou. `draft`/`sent`
#: ainda estão em negociação e `rejected` morreu — faturar qualquer um deles emitiria documento
#: fiscal de um negócio que não existe. Medido em 24/09: 3 accepted, 3 sent, 26 draft, 5 rejected.
STATUS_FATURAVEIS: tuple[str, ...] = ("accepted",)

#: Confiança mínima para aceitar um casamento por descrição. Abaixo disso o item volta como
#: NÃO CASADO com sugestão — melhor uma pessoa escolher do que um NCM errado ir para a SEFAZ.
CORTE_CASAMENTO = 0.88
#: Abaixo do casamento, mas ainda perto o bastante para SUGERIR o NCM (sugestão, não escolha).
CORTE_SUGESTAO = 0.55

_DDL = (
    """CREATE TABLE IF NOT EXISTS fiscal_nota_rascunho (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        origem_tipo varchar(10) NOT NULL,
        proposal_id uuid,
        arquivo_nome text,
        arquivo_hash varchar(64),
        cliente_nome text,
        cliente_documento varchar(20),
        valor_total numeric(15,2) NOT NULL DEFAULT 0,
        status varchar(20) NOT NULL DEFAULT 'rascunho',
        nfe_id uuid,
        observacao text,
        criado_por text,
        criado_em timestamp NOT NULL DEFAULT now(),
        atualizado_em timestamp)""",
    # idempotência por ORIGEM: um rascunho ativo por proposta, um por arquivo (hash do conteúdo).
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_z5_rascunho_proposta ON fiscal_nota_rascunho (proposal_id) "
    " WHERE proposal_id IS NOT NULL AND status <> 'cancelado'",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_z5_rascunho_arquivo ON fiscal_nota_rascunho (arquivo_hash) "
    " WHERE arquivo_hash IS NOT NULL AND status <> 'cancelado'",
    """CREATE TABLE IF NOT EXISTS fiscal_nota_rascunho_item (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        rascunho_id uuid NOT NULL REFERENCES fiscal_nota_rascunho(id) ON DELETE CASCADE,
        numero_item integer NOT NULL,
        codigo varchar(60),
        descricao varchar(200) NOT NULL,
        unidade varchar(6) NOT NULL DEFAULT 'UN',
        quantidade numeric(15,4) NOT NULL,
        valor_unitario numeric(15,10) NOT NULL,
        desconto_percent numeric(9,4) NOT NULL DEFAULT 0,
        valor_total numeric(15,2) NOT NULL,
        produto_id integer,
        produto_codigo varchar(60),
        ncm varchar(8),
        ncm_sugerido varchar(8),
        casamento varchar(20) NOT NULL DEFAULT 'nao_casado',
        confianca numeric(4,3),
        trecho_origem text,
        casado_por text,
        criado_em timestamp NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_z5_item_rascunho ON fiscal_nota_rascunho_item (rascunho_id)",
)


class ProdutoNaoCasadoError(Exception):
    """Item do rascunho sem produto do cadastro fiscal. Quem resolve é uma pessoa, não o código."""


async def ensure_schema(db: AsyncSession) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


# ── números e texto ─────────────────────────────────────────────────────────────────────────
def para_decimal(valor, casas: int = 2) -> Decimal:
    """Número em Decimal, aceitando o que um LLM ou uma planilha brasileira devolve.

    A regra que importa: `1.250,00` é mil duzentos e cinquenta (ponto = milhar), `800.00` é
    oitocentos (ponto = decimal). Com os dois sinais, a vírgula manda. Com só o ponto, três dígitos
    depois dele = milhar; qualquer outra coisa = decimal. Lixo vira 0 — nunca exceção, porque um
    campo ilegível não pode derrubar a leitura dos outros onze itens.
    """
    if isinstance(valor, Decimal):
        bruto = valor
    elif isinstance(valor, (int, float)):
        bruto = Decimal(str(valor))
    else:
        s = re.sub(r"[^\d,.\-]", "", str(valor or "")).strip()
        if not s or s in ("-", ".", ","):
            return Decimal(0).quantize(Decimal(10) ** -casas)
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif s.count(".") > 1 or re.search(r"\.\d{3}$", s):
            s = s.replace(".", "")
        try:
            bruto = Decimal(s)
        except InvalidOperation:
            return Decimal(0).quantize(Decimal(10) ** -casas)
    return bruto.quantize(Decimal(10) ** -casas, rounding=ROUND_HALF_UP)


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip().lower())


def _unidade(u, padrao: str = "UN") -> str:
    """`nfe_itens.unidade` é varchar(6); `proposal_items.unit` é varchar(20). Corta e não mente."""
    return (str(u or "").strip().upper() or padrao)[:6]


# ── (A) orçamento que já existe ─────────────────────────────────────────────────────────────
async def listar_orcamentos(db: AsyncSession, filtro: dict | None = None) -> list[dict]:
    """Propostas em estágio que permita faturar, com cliente, valor, data e quantos itens.

    `filtro`: `status` (lista; padrão `STATUS_FATURAVEIS`), `cliente` (trecho do nome),
    `apenas_sem_rascunho` (bool). Só LÊ — nenhuma escrita em `proposals`.
    """
    f = filtro or {}
    status = list(f.get("status") or STATUS_FATURAVEIS)
    sql = (
        "SELECT p.id::text, p.number, p.status, p.client_name, coalesce(p.client_document,''), "
        "       p.issue_date, coalesce(p.total,0), "
        "       (SELECT count(*) FROM proposal_items i WHERE i.proposal_id = p.id "
        "         AND coalesce(i.is_active,true) AND NOT coalesce(i.is_optional,false)), "
        "       coalesce((SELECT sum(round(i.total::numeric,2)) FROM proposal_items i "
        "         WHERE i.proposal_id = p.id AND coalesce(i.is_active,true) "
        "           AND NOT coalesce(i.is_optional,false)), 0), "
        "       (SELECT r.id::text FROM fiscal_nota_rascunho r WHERE r.proposal_id = p.id "
        "         AND r.status <> 'cancelado' LIMIT 1) "
        "  FROM proposals p WHERE p.status = ANY(:st) AND coalesce(p.is_active, true) "
    )
    params: dict = {"st": status}
    if f.get("cliente"):
        sql += " AND p.client_name ILIKE :cli"
        params["cli"] = f"%{f['cliente']}%"
    sql += " ORDER BY p.issue_date DESC NULLS LAST, p.number DESC"
    linhas = (await db.execute(text(sql), params)).fetchall()
    saida = [
        {
            "proposal_id": r[0],
            "numero": r[1],
            "status": r[2],
            "cliente": r[3],
            "documento": r[4],
            "data": r[5],
            "total_proposta": para_decimal(r[6]),
            "qtd_itens": int(r[7] or 0),
            "total_itens": para_decimal(r[8]),
            "rascunho_id": r[9],
        }
        for r in linhas
    ]
    if f.get("apenas_sem_rascunho"):
        saida = [s for s in saida if not s["rascunho_id"]]
    return saida


async def itens_do_orcamento(db: AsyncSession, proposal_id: str) -> list[dict]:
    """Itens da proposta já normalizados para virar item de nota.

    `proposal_items.total` é a fonte do valor, não `quantidade × unitário`: o desconto por item já
    está aplicado nele, e é ele que o cliente aceitou. Itens inativos e OPCIONAIS ficam de fora —
    opcional é o que o cliente pode não ter comprado, e faturar por engano é cobrar a mais.
    """
    linhas = (
        await db.execute(
            text(
                "SELECT coalesce(i.code,''), i.name, coalesce(i.description,''), i.unit, "
                "       i.quantity, i.unit_price, coalesce(i.discount_percent,0), i.total "
                "  FROM proposal_items i "
                " WHERE i.proposal_id = CAST(:p AS uuid) AND coalesce(i.is_active,true) "
                "   AND NOT coalesce(i.is_optional,false) "
                " ORDER BY i.sort_order, i.created_at"
            ),
            {"p": str(proposal_id)},
        )
    ).fetchall()
    return [
        {
            "codigo": (r[0] or "").strip()[:60],
            "descricao": (r[1] or r[2] or "—").strip()[:200],
            "unidade": _unidade(r[3]),
            "quantidade": para_decimal(r[4], 4),
            "valor_unitario": para_decimal(r[5], 10),
            "desconto_percent": para_decimal(r[6], 4),
            "valor_total": para_decimal(r[7]),
            "confianca": None,  # veio do banco, não de leitura: não há o que estimar
            "trecho_origem": None,
        }
        for r in linhas
    ]


# ── (B) o arquivo do orçamento ──────────────────────────────────────────────────────────────
#: Mesmas REGRAS INEGOCIÁVEIS do `_PROMPT_EXTRACAO` do DP (não deduza, vazio > errado), com o
#: alvo `orcamento`: aqui a resposta é uma LISTA de itens, e cada item traz de onde saiu.
_PROMPT_ORCAMENTO = (
    "Você lê ORÇAMENTOS e PROPOSTAS comerciais brasileiros (PDF, planilha ou foto) e extrai a "
    "lista de itens que serão faturados.\n\n"
    "Devolva SOMENTE um objeto JSON, sem texto em volta:\n"
    '{"itens": [{"codigo": "", "descricao": "", "unidade": "UN", "quantidade": "1", '
    '"valor_unitario": "0,00", "desconto_percent": "0", "confianca": 0.0, "trecho_origem": ""}], '
    '"documento": "que documento é este, 3 palavras"}\n\n'
    "REGRAS INEGOCIÁVEIS:\n"
    "1. Só devolva um item que esteja LEGÍVEL no documento. Não deduza, não complete, não "
    "corrija preço. Na dúvida, não devolva o item.\n"
    "2. É melhor devolver menos do que devolver errado: quem confere é uma pessoa do fiscal, e "
    "um valor trocado vira NOTA FISCAL errada, que só se desfaz com cancelamento.\n"
    "3. NÃO invente código de produto nem NCM. Código só se estiver escrito. NCM nunca.\n"
    "4. NÃO devolva linha de subtotal, total, frete, imposto, desconto geral ou observação — "
    "só as linhas de produto/serviço.\n"
    "5. `valor_unitario` e `quantidade` exatamente como aparecem no documento (pode manter "
    "'1.250,00'). `desconto_percent` só se o documento trouxer desconto NAQUELE item.\n"
    "6. `confianca` entre 0 e 1: o quanto você conseguiu LER aquela linha (1 = nítida, 0,5 = "
    "parte borrada/ambígua). Não é o quanto você acha que acertou o produto.\n"
    "7. `trecho_origem`: o texto da linha do documento de onde o item saiu, copiado como está. "
    "É o rastro da auditoria — sem ele o item é inútil."
)


def normalizar_itens_extraidos(bruto: dict) -> list[dict]:
    """A resposta crua do LLM vira itens com os mesmos campos de `itens_do_orcamento`.

    Função PURA (o oráculo bate nela sem rede e sem custo). Descarta o que não é item: sem
    descrição, sem valor, ou linha de total que escapou da regra 4 do prompt. `confianca` é
    grampeada em [0,1] — modelo às vezes devolve 1.4 — e cai para 0.5 quando vem ausente ou
    ilegível, que é o valor honesto para "não sei o quanto li bem".
    """
    saida: list[dict] = []
    for bloco in bruto.get("itens") or []:
        if not isinstance(bloco, dict):
            continue
        desc = re.sub(r"\s+", " ", str(bloco.get("descricao") or "").strip())[:200]
        if not desc or _norm(desc) in ("total", "total geral", "subtotal", "valor total"):
            continue
        qtd = para_decimal(bloco.get("quantidade"), 4)
        unit = para_decimal(bloco.get("valor_unitario"), 10)
        if qtd <= 0:
            qtd = Decimal("1.0000")
        if unit <= 0:
            continue  # item sem preço não vira item de nota — e não se chuta preço
        desc_pct = para_decimal(bloco.get("desconto_percent"), 4)
        total = (qtd * unit * (Decimal(1) - desc_pct / Decimal(100))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        try:
            conf = float(bloco.get("confianca"))
        except (TypeError, ValueError):
            conf = 0.5
        saida.append(
            {
                "codigo": str(bloco.get("codigo") or "").strip()[:60],
                "descricao": desc,
                "unidade": _unidade(bloco.get("unidade")),
                "quantidade": qtd,
                "valor_unitario": unit,
                "desconto_percent": desc_pct,
                "valor_total": total,
                "confianca": min(1.0, max(0.0, conf)),
                "trecho_origem": (str(bloco.get("trecho_origem") or "").strip() or desc)[:400],
            }
        )
    return saida


async def itens_do_arquivo(db: AsyncSession, nome: str, dados: bytes) -> dict:
    """Lê o arquivo do orçamento e devolve `{itens, documento, hash}`. NÃO grava nada.

    Reusa o mecanismo do `extrair-documento` do DP — `_imagens_do_arquivo()` decide por magic
    bytes se vai por visão ou por texto, recusa HEIC explicando, e rasteriza PDF escaneado. O
    import é tardio de propósito: o serviço fiscal não pode depender do builder do DP no import.
    """
    import json as _json

    from core.llm_client import modelo_visao, novo_cliente
    from modules.ai.conversation.services.orquestrador.anexos import extrair_texto_arquivo
    from modules.operacional.controllers.redesign_builders.departamento_pessoal import _imagens_do_arquivo

    imagens = _imagens_do_arquivo(nome, dados)
    if imagens:
        conteudo = [{"type": "text", "text": _PROMPT_ORCAMENTO}]
        conteudo += [{"type": "image_url", "image_url": {"url": u}} for u in imagens]
    else:
        texto = extrair_texto_arquivo(nome, dados)
        if len(texto) < 10:
            raise ValueError("Não consegui ler o arquivo. Tente um PDF com texto ou uma foto nítida (JPG/PNG).")
        conteudo = [{"type": "text", "text": f'{_PROMPT_ORCAMENTO}\n\nDOCUMENTO:\n"""\n{texto[:30000]}\n"""'}]

    cli = novo_cliente(origem="fiscal.z5.orcamento", timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "120") or 120))
    try:
        r = await cli.chat.completions.create(
            model=(modelo_visao() if imagens else os.getenv("OPENAI_AGENT_MODEL", "gpt-5.1")),
            messages=[{"role": "user", "content": conteudo}],
            response_format={"type": "json_object"},
            max_completion_tokens=4000,
        )
        cru = _json.loads(r.choices[0].message.content or "{}")
    except Exception as e:  # noqa: BLE001 — falha de leitura não derruba a tela
        logger.warning("[z5] extração do orçamento falhou (%s): %s", nome, e)
        raise ValueError("Não consegui interpretar o orçamento agora. Tente outro arquivo ou lance pelo CRM.") from e

    return {
        "itens": normalizar_itens_extraidos(cru),
        "documento": str(cru.get("documento") or "")[:60],
        "hash": hashlib.sha256(dados).hexdigest(),
    }


# ── casamento com o cadastro fiscal (Z1) — lê, nunca escreve ────────────────────────────────
async def cadastro_de_produto_existe(db: AsyncSession) -> bool:
    """`fin_produtos` é da frente Z1 e pode ainda não existir neste banco — então se pergunta."""
    return bool((await db.execute(text("SELECT to_regclass('public.fin_produtos')"))).scalar())


async def casar_produtos(db: AsyncSession, itens: list[dict]) -> list[dict]:
    """Para cada item, acha o produto no cadastro fiscal: por CÓDIGO, depois por DESCRIÇÃO.

    O que não casar volta com `produto_id = None` e, quando dá, `ncm_sugerido` — sugestão pela
    descrição parecida, para a pessoa confirmar. **Nunca cria produto.** Criar produto a partir de
    uma descrição de orçamento é inventar NCM, e NCM inventado é a rejeição que a SEFAZ já
    devolveu a esta empresa em 11/04/2026 («Informado NCM inexistente»).
    """
    itens = [dict(i) for i in itens]
    if not await cadastro_de_produto_existe(db):
        for i in itens:
            i.update(
                produto_id=None,
                produto_codigo=None,
                produto_descricao=None,
                ncm=None,
                ncm_sugerido=None,
                casamento="nao_casado",
                motivo="cadastro fiscal de produto (fin_produtos, frente Z1) ainda não existe neste banco",
            )
        return itens

    cad = (
        await db.execute(
            text(
                "SELECT id, coalesce(codigo,''), descricao, coalesce(ncm,''), coalesce(unidade_comercial,'') "
                "  FROM fin_produtos WHERE coalesce(ativo, true) ORDER BY id"
            )
        )
    ).fetchall()
    por_codigo = {_norm(p[1]): p for p in cad if (p[1] or "").strip()}
    por_desc = {_norm(p[2]): p for p in cad}
    descricoes = list(por_desc)

    for i in itens:
        achado, como = None, "nao_casado"
        cod = _norm(i.get("codigo"))
        if cod and cod in por_codigo:
            achado, como = por_codigo[cod], "codigo"
        else:
            d = _norm(i.get("descricao"))
            if d in por_desc:
                achado, como = por_desc[d], "descricao"
            else:
                perto = difflib.get_close_matches(d, descricoes, n=1, cutoff=CORTE_CASAMENTO)
                if perto:
                    achado, como = por_desc[perto[0]], "descricao"
        if achado is not None:
            i.update(
                produto_id=int(achado[0]),
                produto_codigo=achado[1] or None,
                produto_descricao=achado[2],
                ncm=achado[3] or None,
                ncm_sugerido=None,
                casamento=como,
                motivo=None,
            )
            if not i.get("unidade") and achado[4]:
                i["unidade"] = _unidade(achado[4])
            continue
        # não casou: sugere o NCM do produto mais parecido, se houver um parecido o bastante
        perto = difflib.get_close_matches(_norm(i.get("descricao")), descricoes, n=1, cutoff=CORTE_SUGESTAO)
        sug = por_desc[perto[0]] if perto else None
        i.update(
            produto_id=None,
            produto_codigo=None,
            produto_descricao=None,
            ncm=None,
            ncm_sugerido=(sug[3] or None) if sug else None,
            casamento="nao_casado",
            motivo=(
                f"não achei no cadastro; o mais parecido é «{sug[2][:50]}» (NCM {sug[3] or '—'})"
                if sug
                else "não achei nada parecido no cadastro fiscal — escolha o produto ou cadastre-o na tela de produtos"
            ),
        )
    return itens


# ── o rascunho ──────────────────────────────────────────────────────────────────────────────
async def rascunho_existente(
    db: AsyncSession, *, proposal_id: str | None = None, arquivo_hash: str | None = None
) -> str | None:
    """Id do rascunho ativo daquela origem, ou None. Existe para a rota NÃO gastar uma chamada de
    LLM relendo um arquivo que já foi lido: o sha256 do conteúdo responde antes."""
    if proposal_id:
        onde, chave = "proposal_id = CAST(:k AS uuid)", str(proposal_id)
    elif arquivo_hash:
        onde, chave = "arquivo_hash = :k", arquivo_hash
    else:
        return None
    return (
        await db.execute(
            text(f"SELECT id::text FROM fiscal_nota_rascunho WHERE {onde} AND status <> 'cancelado'"), {"k": chave}
        )
    ).scalar()


async def preparar_rascunho(
    db: AsyncSession,
    origem: str,
    *,
    proposal_id: str | None = None,
    arquivo_nome: str | None = None,
    arquivo_bytes: bytes | None = None,
    arquivo_hash: str | None = None,
    itens: list[dict] | None = None,
    cliente_nome: str | None = None,
    cliente_documento: str | None = None,
    observacao: str | None = None,
    usuario: str | None = None,
) -> dict:
    """Grava o rascunho de nota COM A ORIGEM e devolve o id para a tela da Z3 abrir.

    Idempotente por origem: pedir duas vezes o mesmo orçamento (ou subir o mesmo arquivo, que tem
    o mesmo sha256) devolve o rascunho que já existe, com `ja_existia = True`. Não duplica e
    também não sobrescreve o que uma pessoa já tiver ajustado nele.

    Nota fiscal sem origem rastreável é problema na auditoria — por isso `origem_tipo` só aceita
    `proposta` (com `proposal_id`) ou `arquivo` (com nome + hash do conteúdo).
    """
    await ensure_schema(db)
    origem = (origem or "").strip().lower()
    if origem not in ("proposta", "arquivo"):
        raise ValueError("Origem do rascunho deve ser 'proposta' ou 'arquivo'.")

    if origem == "proposta":
        if not proposal_id:
            raise ValueError("Informe a proposta de origem.")
        cab = (
            await db.execute(
                text(
                    "SELECT p.number, p.client_name, coalesce(p.client_document,''), p.status "
                    "  FROM proposals p WHERE p.id = CAST(:p AS uuid)"
                ),
                {"p": str(proposal_id)},
            )
        ).first()
        if not cab:
            raise ValueError("Proposta não encontrada.")
        if cab[3] not in STATUS_FATURAVEIS:
            raise ValueError(
                f"A proposta {cab[0]} está em «{cab[3]}» e não pode virar nota. "
                f"Faturável: {', '.join(STATUS_FATURAVEIS)}."
            )
        chave_sql = "proposal_id = CAST(:k AS uuid)"
        chave = str(proposal_id)
        cliente_nome = cliente_nome or cab[1]
        cliente_documento = cliente_documento or cab[2]
        if itens is None:
            itens = await casar_produtos(db, await itens_do_orcamento(db, proposal_id))
    else:
        if arquivo_hash is None:
            if not arquivo_bytes:
                raise ValueError("Suba o arquivo do orçamento.")
            arquivo_hash = hashlib.sha256(arquivo_bytes).hexdigest()
        if not arquivo_nome:
            raise ValueError("Arquivo sem nome.")
        chave_sql = "arquivo_hash = :k"
        chave = arquivo_hash
        if itens is None:
            lido = await itens_do_arquivo(db, arquivo_nome, arquivo_bytes or b"")
            itens = await casar_produtos(db, lido["itens"])

    ja = (
        await db.execute(
            text(f"SELECT id::text, valor_total FROM fiscal_nota_rascunho WHERE {chave_sql} AND status <> 'cancelado'"),
            {"k": chave},
        )
    ).first()
    if ja:
        return {
            "id": ja[0],
            "ja_existia": True,
            "valor_total": para_decimal(ja[1]),
            "qtd_itens": int(
                (
                    await db.execute(
                        text("SELECT count(*) FROM fiscal_nota_rascunho_item WHERE rascunho_id = CAST(:r AS uuid)"),
                        {"r": ja[0]},
                    )
                ).scalar_one()
            ),
            "mensagem": "Este orçamento já tem um rascunho de nota. Abri o que existe em vez de criar outro.",
        }

    if not itens:
        raise ValueError("Nenhum item para faturar — o orçamento não tem item ativo, ou o arquivo não trouxe nenhum.")

    total = sum((para_decimal(i["valor_total"]) for i in itens), Decimal("0.00"))
    rid = (
        await db.execute(
            text(
                "INSERT INTO fiscal_nota_rascunho (origem_tipo, proposal_id, arquivo_nome, arquivo_hash, "
                "  cliente_nome, cliente_documento, valor_total, observacao, criado_por) "
                "VALUES (:o, CAST(NULLIF(:p,'') AS uuid), NULLIF(:an,''), NULLIF(:ah,''), :cn, :cd, :vt, :ob, :us) "
                "RETURNING id::text"
            ),
            {
                "o": origem,
                "p": str(proposal_id or ""),
                "an": arquivo_nome or "",
                "ah": arquivo_hash or "",
                "cn": (cliente_nome or "—")[:200],
                "cd": re.sub(r"\D", "", cliente_documento or "")[:20] or None,
                "vt": total,
                "ob": observacao,
                "us": usuario,
            },
        )
    ).scalar_one()

    for n, i in enumerate(itens, start=1):
        await db.execute(
            text(
                "INSERT INTO fiscal_nota_rascunho_item (rascunho_id, numero_item, codigo, descricao, unidade, "
                "  quantidade, valor_unitario, desconto_percent, valor_total, produto_id, produto_codigo, ncm, "
                "  ncm_sugerido, casamento, confianca, trecho_origem) "
                "VALUES (CAST(:r AS uuid), :n, NULLIF(:cod,''), :desc, :un, :q, :vu, :dp, :vt, :pid, "
                "  NULLIF(:pcod,''), NULLIF(:ncm,''), NULLIF(:nsug,''), :cas, :conf, :tre)"
            ),
            {
                "r": rid,
                "n": n,
                "cod": (i.get("codigo") or "")[:60],
                "desc": (i.get("descricao") or "—")[:200],
                "un": _unidade(i.get("unidade")),
                "q": para_decimal(i.get("quantidade"), 4),
                "vu": para_decimal(i.get("valor_unitario"), 10),
                "dp": para_decimal(i.get("desconto_percent"), 4),
                "vt": para_decimal(i.get("valor_total")),
                "pid": i.get("produto_id"),
                "pcod": i.get("produto_codigo") or "",
                "ncm": i.get("ncm") or "",
                "nsug": i.get("ncm_sugerido") or "",
                "cas": i.get("casamento") or "nao_casado",
                "conf": (None if i.get("confianca") is None else round(float(i["confianca"]), 3)),
                "tre": i.get("trecho_origem"),
            },
        )
    await db.commit()
    pend = sum(1 for i in itens if not i.get("produto_id"))
    return {
        "id": rid,
        "ja_existia": False,
        "valor_total": total,
        "qtd_itens": len(itens),
        "itens_sem_produto": pend,
        "mensagem": (
            f"Rascunho criado com {len(itens)} item(ns), R$ {total}."
            + (f" {pend} item(ns) ainda sem produto do cadastro fiscal — escolha antes de emitir." if pend else "")
        ),
    }


async def itens_para_nota(db: AsyncSession, rascunho_id: str) -> list[dict]:
    """Itens do rascunho PRONTOS para virar item de NF-e. Recusa se algum não tiver produto.

    Esta é a trava que impede um item lido de um PDF de virar linha de nota fiscal sem que uma
    pessoa tenha dito de que produto se trata. O NCM sai do cadastro (Z1), nunca do arquivo.
    """
    linhas = (
        await db.execute(
            text(
                "SELECT numero_item, codigo, produto_codigo, descricao, unidade, quantidade, valor_unitario, "
                "       valor_total, produto_id, ncm "
                "  FROM fiscal_nota_rascunho_item WHERE rascunho_id = CAST(:r AS uuid) ORDER BY numero_item"
            ),
            {"r": str(rascunho_id)},
        )
    ).fetchall()
    if not linhas:
        raise ValueError("Rascunho sem itens.")
    pend = [f"item {r[0]} «{r[3][:40]}»" for r in linhas if r[8] is None]
    if pend:
        raise ProdutoNaoCasadoError(
            f"{len(pend)} item(ns) sem produto do cadastro fiscal: {'; '.join(pend[:5])}"
            f"{'…' if len(pend) > 5 else ''}. Escolha o produto de cada um antes de emitir."
        )
    return [
        {
            "numero_item": r[0],
            "codigo_produto": r[2] or r[1] or "SEM-CODIGO",
            "descricao": r[3][:120],
            "unidade": r[4],
            "quantidade": para_decimal(r[5], 4),
            "valor_unitario": para_decimal(r[6], 10),
            "valor_total": para_decimal(r[7]),
            "produto_id": r[8],
            "ncm": r[9],
        }
        for r in linhas
    ]


async def casar_item_manual(db: AsyncSession, item_id: str, produto_id: int, usuario: str | None = None) -> dict:
    """A pessoa escolheu o produto de um item pendente. NCM e código passam a vir do cadastro."""
    if not await cadastro_de_produto_existe(db):
        raise ValueError("O cadastro fiscal de produtos (frente Z1) ainda não existe neste ambiente.")
    prod = (
        await db.execute(
            text("SELECT id, coalesce(codigo,''), descricao, coalesce(ncm,'') FROM fin_produtos WHERE id = :p"),
            {"p": int(produto_id)},
        )
    ).first()
    if not prod:
        raise ValueError("Produto não encontrado no cadastro fiscal.")
    n = (
        await db.execute(
            text(
                "UPDATE fiscal_nota_rascunho_item SET produto_id = :pid, produto_codigo = NULLIF(:pcod,''), "
                "  ncm = NULLIF(:ncm,''), ncm_sugerido = NULL, casamento = 'manual', casado_por = :us "
                " WHERE id = CAST(:i AS uuid) RETURNING 1"
            ),
            {"pid": int(prod[0]), "pcod": prod[1], "ncm": prod[3], "us": usuario, "i": str(item_id)},
        )
    ).first()
    if not n:
        raise ValueError("Item do rascunho não encontrado.")
    await db.commit()
    return {"ok": True, "produto": prod[2], "ncm": prod[3] or None}
