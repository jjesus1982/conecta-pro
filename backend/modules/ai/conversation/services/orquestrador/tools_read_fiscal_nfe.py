"""DGX Z6 — as consultas de NF-e de MERCADORIA que faltavam ao Bartolo (24/09/2026).

**Bartolo** é o nome que o dono dá ao assistente desta casa (o termo já vive no
`tool_registry` e no `consultor_escopado_controller`). Não nasce chat novo aqui: o chat é o
mesmo `POST /consultores/chat/consultar` com a lente `fiscal`. O que faltava era **alcance** —
medido pelas 10 perguntas do §1 do relatório, feitas pela rota real antes deste arquivo existir:

  · «Por que a NF-e número 2 foi rejeitada?» → *"não há registro de rejeição para a nota nº 2 —
    o módulo fiscal não guarda motivo de rejeição de NF-e"*. **Guarda**: `nfes.motivo_rejeicao`
    da nota 2 diz, literalmente, «Rejeicao: Informado NCM inexistente [nItem: 1]».
  · «Quantas NF-e de saída existem?» → *"não há NF-e de saída na base"*. Havia duas, desde
    11/04/2026, ambas rejeitadas. O Bartolo respondeu com NFS-e (serviço) e chamou de NF-e.
  · «O produto X está com NCM válido?» → procurou em `crm_products` e no GED, que não são o
    cadastro fiscal, e não olhou `products.ncm` nem a tabela oficial `ncms`.

Três "não existe" confiantes sobre dado que existe. Nenhum é defeito do modelo: nenhuma tool
do escopo fiscal lia `nfes`, `nfe_itens` nem o cadastro fiscal do produto.

**Só LEITURA.** Nenhuma op aqui emite, assina, transmite, cancela ou inutiliza documento fiscal
— nem grava linha nenhuma. O Bartolo tira dúvida; quem assina documento fiscal é gente.
`test_oraculo_z6_bartolo.py` varre este arquivo atrás de INSERT/UPDATE/DELETE e reprova se achar.

**Não reimplementa o que já existe.** `buscar_ncm` (tabela oficial, 10.515 códigos) já era op do
`consultar_fiscal` desde antes desta frente — aqui só se aponta para ela. A tributação NÃO é
recalculada: `tributacao_nfe` repassa **verbatim** o que `fiscal/services/tributacao_nfe.py`
(frente Z4) devolveu, com a `norma` que a Z4 registrou. Régua paralela é o defeito que este
arquivo existe para não ter.

**Honestidade.** Quando a casa não tem a resposta, a op devolve `nao_sei` com o texto do que
falta e `onde_decidir` apontando o painel do dono — nunca um NCM, uma alíquota ou um CFOP
inventado. Onde a Z4 marcou «sem fonte — decisão do contador», a frase chega inteira ao dono
porque o cálculo passa sem ser reescrito.
"""

from __future__ import annotations

from functools import wraps
from typing import Any

from sqlalchemy import text as _t
from sqlalchemy.exc import SQLAlchemyError

from core.auth.module_scope import user_has_module

from .read_dispatcher import registrar_read

_MOD = "fiscal"

#: Para onde aponta um "não sei" que é decisão de gente, não falta de consulta.
PAINEL_DECISOES = "/redesign/bi?t=decisoes-do-dono"

#: A frase EXATA da Z4 para regra sem dispositivo legal localizado. Repetida com estas
#: palavras, nunca parafraseada — é o que o dono combinou de ver quando não há fonte.
SEM_FONTE = "sem fonte — decisão do contador"


def _gate(user) -> None:
    """Suspenders: chamar o handler direto pula o Depends do controller. Gate de diretoria."""
    if not user_has_module(user, _MOD):
        raise PermissionError(_MOD)


def _nao_sei(o_que: str, onde: str = PAINEL_DECISOES) -> dict:
    """A resposta honesta. `nao_sei` é um campo, não um parágrafo: o modelo enxerga a chave."""
    return {
        "nao_sei": True,
        "resposta": "Não sei — a casa não tem esse dado registrado.",
        "o_que_falta": o_que,
        "onde_decidir": onde,
        "regra": (
            "NUNCA responder com NCM, alíquota ou CFOP inventado. Diga ao usuário, com estas "
            "palavras, que você não sabe, e mostre o que falta e onde a decisão está pendente."
        ),
    }


def _consulta(fn):
    """Uma consulta que estoura NÃO pode derrubar a conversa inteira.

    Medido em 24/09/2026 pelo próprio oráculo desta frente: um `SELECT` com uma coluna que não
    existia (`proposal_items.total_price`) deixou a `AsyncSession` em «current transaction is
    aborted» — e as DUAS perguntas seguintes da mesma sessão morreram antes de chegar ao
    modelo, com um erro que não tinha nada a ver com elas. O `rollback` aqui é o que separa
    «esta consulta falhou» de «o Bartolo parou de funcionar».

    O erro é DEVOLVIDO, não engolido: vira `nao_sei` com o texto da exceção. Falha técnica
    nunca vira número chutado, e nunca vira «você não tem acesso».
    """

    @wraps(fn)
    async def _envolvido(db, user, scope, **kw):
        try:
            return await fn(db, user, scope, **kw)
        except PermissionError:
            raise  # RBAC é decisão, não defeito — sobe inteiro
        except SQLAlchemyError as exc:
            await db.rollback()
            causa = str(getattr(exc, "orig", exc)).splitlines()[0][:200]
            r = _nao_sei(
                f"a consulta `{fn.__name__.strip('_')}` falhou no banco: {causa}. "
                "Isso é defeito técnico, NÃO falta de permissão e NÃO significa que o "
                "dado não existe."
            )
            r["erro_tecnico"] = True
            return r

    return _envolvido


async def _tabela_existe(db, nome: str) -> bool:
    return bool((await db.execute(_t("SELECT to_regclass(:n)"), {"n": f"public.{nome}"})).scalar())


def _dig(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


# ─────────────────────────── NF-e de saída: a lista e o status ───────────────────────────

_SQL_NFE = """
SELECT n.id::text, n.numero, n.serie, n.status, n.ambiente, n.c_stat, n.empresa_slug,
       n.emitente_cnpj, n.emitente_razao_social, n.destinatario_razao_social,
       n.destinatario_cpf_cnpj, n.destinatario_uf, n.natureza_operacao,
       to_char(n.data_emissao, 'DD/MM/YYYY') AS emissao,
       to_char(n.data_emissao, 'YYYY-MM')    AS competencia,
       n.valor_total_nota, n.chave_acesso, n.protocolo_autorizacao, n.motivo_rejeicao,
       n.is_zfm, n.suframa_destinatario, n.justificativa_cancelamento
FROM nfes n
WHERE n.tipo = 'saida' AND COALESCE(n.active, TRUE)
  AND (CAST(:competencia AS text) IS NULL OR to_char(n.data_emissao, 'YYYY-MM') = :competencia)
  AND (CAST(:numero AS integer) IS NULL OR n.numero = :numero)
  AND (CAST(:serie AS integer) IS NULL OR n.serie = :serie)
  AND (CAST(:status AS text) IS NULL OR lower(n.status) = lower(:status))
  AND (CAST(:chave AS text) IS NULL OR n.chave_acesso = :chave)
  AND (CAST(:empresa AS text) IS NULL OR n.empresa_slug = :empresa OR n.emitente_cnpj = :empresa)
ORDER BY n.data_emissao DESC, n.numero DESC
LIMIT :lim
"""


def _linha_nota(r) -> dict:
    d = dict(r)
    d["valor_total_nota"] = float(d["valor_total_nota"] or 0)
    # xMotivo LITERAL, sem reescrita: é o texto que a SEFAZ devolveu.
    d["motivo_rejeicao"] = d["motivo_rejeicao"] or None
    return d


@_consulta
async def _nfe_saida(
    db, user, scope, *, competencia=None, numero=None, serie=None, status=None, chave=None, empresa=None, limite=50, **_
) -> Any:
    _gate(user)
    if not await _tabela_existe(db, "nfes"):
        return _nao_sei("a tabela `nfes` não existe neste banco — não há NF-e de mercadoria registrada para consultar.")
    p = {
        "competencia": str(competencia).strip() if competencia else None,
        "numero": int(numero) if str(numero or "").strip().isdigit() else None,
        "serie": int(serie) if str(serie or "").strip().isdigit() else None,
        "status": str(status).strip() if status else None,
        "chave": _dig(chave) or None,
        "empresa": str(empresa).strip() if empresa else None,
        "lim": max(1, min(int(limite), 200)),
    }
    linhas = [_linha_nota(x) for x in (await db.execute(_t(_SQL_NFE), p)).mappings().all()]
    if not linhas:
        return _nao_sei(
            "nenhuma NF-e de saída bate com esse filtro em `nfes`. Confira o número/série/"
            "competência, ou pergunte sem filtro para ver o que existe.",
            onde=PAINEL_DECISOES,
        )
    por_status: dict[str, int] = {}
    for x in linhas:
        por_status[x["status"] or "(sem status)"] = por_status.get(x["status"] or "(sem status)", 0) + 1
    return {
        "fonte": "nfes (NF-e modelo 55, mercadoria) — NÃO é NFS-e de serviço",
        "total": len(linhas),
        "por_status": por_status,
        "notas": linhas,
        "aviso": (
            "NF-e de MERCADORIA. As notas de SERVIÇO estão em `listar_nfse` — são coisas "
            "diferentes e não se somam. Nota com status 'rejeitada' NÃO existe para o fisco: "
            "use a consulta 'nfe_rejeicao' para ler o motivo literal e o que corrigir."
        ),
    }


# ──────────────── Rejeição: o xMotivo literal + o que corrigir, sem inventar ────────────────

#: Fragmento (minúsculo, sem acento de sobra) do xMotivo da SEFAZ → onde está o defeito.
#: Cada entrada aponta o CAMPO a corrigir — nunca um valor. Valor é do contribuinte.
_ONDE_CORRIGIR: tuple[tuple[str, str, str], ...] = (
    (
        "ncm inexistente",
        "item da nota → NCM (nfe_itens.ncm) e o cadastro fiscal do produto",
        "O NCM informado não está na tabela oficial vigente. Corrija no CADASTRO do produto, "
        "não só na nota — corrigido só na nota, a próxima sai rejeitada igual. Para achar o "
        "código vigente use a consulta 'buscar_ncm'; para ver o que o cadastro tem, "
        "'produto_fiscal'. O NCM é responsabilidade do contribuinte: o sistema sugere, "
        "quem classifica é gente.",
    ),
    (
        "ncm",
        "item da nota → NCM (nfe_itens.ncm)",
        "A rejeição fala do NCM do item. Leia o texto literal acima para saber se é código "
        "inexistente, dígito faltando ou NCM incompatível com a operação.",
    ),
    (
        "cfop",
        "item da nota → CFOP (nfe_itens.cfop)",
        "O CFOP não confere com a operação declarada (interna × interestadual, revenda × "
        "produção, destinatário contribuinte × consumidor final). A consulta "
        "'tributacao_nfe' devolve o CFOP que a regra da casa calcula, com a norma.",
    ),
    (
        "duplicidade",
        "numeração da nota (nfes.numero/serie por CNPJ)",
        "Já existe nota autorizada com esse número/série neste CNPJ. Emita no próximo número "
        "da série — não reaproveite número.",
    ),
    (
        "inscricao estadual",
        "destinatário → IE / indicador de IE (destinatario_ie, destinatario_ind_ie)",
        "A IE do destinatário não confere com o cadastro da SEFAZ, ou o indicador de IE está "
        "errado (contribuinte × isento × não contribuinte). Corrija na ficha do cliente.",
    ),
    (
        "certificado",
        "certificado digital do emitente",
        "O certificado A1/A3 usado na assinatura está vencido, revogado ou é de outro CNPJ. "
        "Isso não se corrige na nota — é infraestrutura.",
    ),
    (
        "ambiente",
        "ambiente da transmissão (nfes.ambiente / tpAmb)",
        "A nota foi enviada ao ambiente errado. Nesta casa, emissão de NF-e só acontece em "
        "HOMOLOGAÇÃO (tpAmb = 2) enquanto o dono não liberar produção.",
    ),
)


async def _ncms_invalidos_da_nota(db, nfe_id: str) -> list[dict]:
    """Quais itens têm NCM ausente da tabela oficial. MEDIDO, não deduzido do texto."""
    if not await _tabela_existe(db, "ncms"):
        return []
    linhas = (
        (
            await db.execute(
                _t(
                    "SELECT i.numero_item, i.codigo_produto, i.descricao, i.ncm, i.cfop "
                    "FROM nfe_itens i WHERE i.nfe_id = CAST(:id AS uuid) "
                    "AND NOT EXISTS (SELECT 1 FROM ncms m WHERE m.codigo = i.ncm) "
                    "ORDER BY i.numero_item"
                ),
                {"id": nfe_id},
            )
        )
        .mappings()
        .all()
    )
    return [dict(x) for x in linhas]


@_consulta
async def _nfe_rejeicao(db, user, scope, *, numero=None, serie=None, chave=None, id=None, **_) -> Any:  # noqa: A002
    _gate(user)
    if not await _tabela_existe(db, "nfes"):
        return _nao_sei("a tabela `nfes` não existe neste banco.")
    if not any([numero, chave, id]):
        return {
            "status": "recusado",
            "motivo": "informe `numero` (e `serie`, se houver mais de uma), `chave` ou `id` "
            "da nota. Sem identificar a nota não há rejeição a explicar.",
        }
    p = {
        "numero": int(numero) if str(numero or "").strip().isdigit() else None,
        "serie": int(serie) if str(serie or "").strip().isdigit() else None,
        "chave": _dig(chave) or None,
        "id": str(id).strip() if id else None,
    }
    linhas = (
        (
            await db.execute(
                _t(
                    "SELECT id::text, numero, serie, status, ambiente, c_stat, empresa_slug, "
                    "       emitente_cnpj, destinatario_razao_social, "
                    "       to_char(data_emissao,'DD/MM/YYYY') AS emissao, "
                    "       valor_total_nota, chave_acesso, protocolo_autorizacao, motivo_rejeicao "
                    "FROM nfes WHERE COALESCE(active, TRUE) "
                    "  AND (CAST(:numero AS integer) IS NULL OR numero = :numero) "
                    "  AND (CAST(:serie AS integer) IS NULL OR serie = :serie) "
                    "  AND (CAST(:chave AS text) IS NULL OR chave_acesso = :chave) "
                    "  AND (CAST(:id AS text) IS NULL OR id = CAST(:id AS uuid)) "
                    "ORDER BY data_emissao DESC LIMIT 10"
                ),
                p,
            )
        )
        .mappings()
        .all()
    )
    if not linhas:
        return _nao_sei(
            "nenhuma NF-e com esse número/chave em `nfes`. Confira se o número é "
            "de NF-e (mercadoria) e não de NFS-e (serviço) — são numerações "
            "diferentes, em sistemas diferentes."
        )

    notas = []
    for r in linhas:
        d = dict(r)
        d["valor_total_nota"] = float(d["valor_total_nota"] or 0)
        motivo = (d.get("motivo_rejeicao") or "").strip()
        d["xMotivo_literal"] = motivo or None
        if not motivo:
            d["explicacao"] = (
                f"Esta nota está com status {d['status']!r} e NÃO tem motivo de rejeição "
                "gravado. Não sei por que ela não passou — o retorno da SEFAZ não foi guardado."
            )
            d["nao_sei"] = True
            d["onde_decidir"] = PAINEL_DECISOES
        else:
            achou = next((e for e in _ONDE_CORRIGIR if e[0] in motivo.lower()), None)
            if achou:
                d["onde_corrigir"] = achou[1]
                d["o_que_fazer"] = achou[2]
            else:
                d["onde_corrigir"] = None
                d["o_que_fazer"] = (
                    "Não tenho tradução cadastrada para esta rejeição. O texto literal da "
                    "SEFAZ acima é o que vale — leve-o ao contador. Não invente a causa."
                )
                d["nao_sei"] = True
                d["onde_decidir"] = PAINEL_DECISOES
            if "ncm" in motivo.lower():
                d["itens_com_ncm_fora_da_tabela_oficial"] = await _ncms_invalidos_da_nota(db, d["id"])
        notas.append(d)
    return {
        "fonte": "nfes.motivo_rejeicao (retorno da SEFAZ, texto literal) + nfe_itens × ncms",
        "total": len(notas),
        "notas": notas,
        "aviso": (
            "Reproduza o xMotivo LITERAL para o usuário antes de explicar. A explicação diz "
            "qual CAMPO corrigir; ela nunca inventa o valor a pôr no campo."
        ),
    }


# ──────────────────────── Cadastro fiscal do produto (Z1, com queda) ────────────────────────

_SQL_FIN_PRODUTOS = """
SELECT p.codigo, p.descricao, p.ncm, p.unidade_comercial AS unidade, p.origem,
       p.cest, p.ean, p.cfop_padrao_dentro_uf, p.cfop_padrao_fora_uf,
       p.ativo::text AS ativo, p.motivo_inativo,
       (SELECT m.descricao_resumida FROM ncms m WHERE m.codigo = p.ncm) AS ncm_oficial
FROM fin_produtos p
WHERE (CAST(:codigo AS text) IS NULL OR lower(p.codigo) = lower(:codigo))
  AND (CAST(:busca AS text) IS NULL OR p.descricao ILIKE :like OR p.codigo ILIKE :like)
ORDER BY p.codigo LIMIT :lim
"""

_SQL_PRODUCTS = """
SELECT p.code AS codigo, p.name AS descricao, p.ncm, p.unit_of_measure AS unidade,
       p.origin AS origem, p.cest, p.cfop_out, p.status AS ativo,
       (SELECT m.descricao_resumida FROM ncms m WHERE m.codigo = p.ncm) AS ncm_oficial
FROM products p
WHERE (CAST(:codigo AS text) IS NULL OR lower(p.code) = lower(:codigo))
  AND (CAST(:busca AS text) IS NULL OR p.name ILIKE :like OR p.code ILIKE :like)
ORDER BY p.code LIMIT :lim
"""


def _falta_para_emitir(p: dict) -> list[str]:
    """O que impede a nota de sair. Fatos sobre o cadastro — nenhum valor é sugerido aqui."""
    f = []
    ncm = _dig(p.get("ncm"))
    if not ncm:
        f.append("NCM em branco")
    elif len(ncm) != 8:
        f.append(f"NCM com {len(ncm)} dígitos (a NF-e exige 8)")
    elif not p.get("ncm_oficial"):
        f.append(f"NCM {ncm} NÃO existe na tabela oficial `ncms` — é exatamente a rejeição «Informado NCM inexistente»")
    if not str(p.get("origem") or "").strip():
        f.append("origem da mercadoria em branco (Tabela A do MOC NF-e: 0 = nacional)")
    return f


@_consulta
async def _produto_fiscal(db, user, scope, *, codigo=None, busca=None, limite=20, **_) -> Any:
    _gate(user)
    z1 = await _tabela_existe(db, "fin_produtos")
    if not z1 and not await _tabela_existe(db, "products"):
        return _nao_sei("não há cadastro de produto neste banco (nem `fin_produtos`, nem `products`).")
    if not (codigo or busca):
        return {
            "status": "recusado",
            "motivo": "informe `codigo` (o código do produto) ou `busca` (parte da descrição). Não existe listar tudo.",
        }
    p = {
        "codigo": str(codigo).strip() if codigo else None,
        "busca": str(busca).strip() if busca else None,
        "like": f"%{str(busca).strip()}%" if busca else None,
        "lim": max(1, min(int(limite), 50)),
    }
    # As DUAS fontes, sempre. `fin_produtos` é o cadastro fiscal (frente Z1, semeado das NF-e
    # de compra); `products` é o catálogo de compra do Bling. Medido em 24/09/2026: o mesmo
    # item pode estar num e não no outro (VTV-121 está em `products` com NCM 85365090 e NÃO
    # está no cadastro fiscal). Responder por uma só esconde metade da verdade — e a metade
    # escondida é justamente «este item ainda não está pronto para emitir».
    linhas: list[dict] = []
    if z1:
        for x in (await db.execute(_t(_SQL_FIN_PRODUTOS), p)).mappings().all():
            linhas.append({**dict(x), "fonte": "cadastro fiscal (fin_produtos)"})
    if await _tabela_existe(db, "products"):
        for x in (await db.execute(_t(_SQL_PRODUCTS), p)).mappings().all():
            linhas.append({**dict(x), "fonte": "catálogo de compra (products) — NÃO é cadastro fiscal"})
    if not linhas:
        return _nao_sei(
            "nenhum produto com esse código/descrição, nem no cadastro fiscal nem no catálogo "
            "de compra. Sem o item identificado não há NCM a validar — e eu não invento NCM. "
            "Peça o código como ele aparece no cadastro."
        )
    for x in linhas:
        x["falta_para_emitir"] = _falta_para_emitir(x)
        x["pronto_para_emitir"] = not x["falta_para_emitir"]
    no_fiscal = [x for x in linhas if x["fonte"].startswith("cadastro fiscal")]
    return {
        "fonte": (
            "fin_produtos (cadastro FISCAL, frente Z1) + products (catálogo de compra) × ncms"
            if z1
            else "products (catálogo de compra/Bling) × ncms"
        ),
        "total": len(linhas),
        "produtos": linhas,
        "aviso": (
            "ATENÇÃO: `fin_produtos` (o cadastro fiscal) não existe neste banco — tudo acima é "
            "catálogo de compra, que não tem tributação por CNPJ. Diga isso ao usuário."
            if not z1
            else "O item só está pronto para virar linha de NF-e quando aparece com fonte «cadastro "
            "fiscal». Estar no catálogo de compra com NCM preenchido NÃO é o mesmo: o catálogo "
            "não tem CST/CSOSN por CNPJ nem CFOP. Diga isso em vez de responder «tem NCM, pode "
            "emitir»."
            if not no_fiscal
            else "Item presente no cadastro fiscal — confira `falta_para_emitir` antes de faturar."
        ),
    }


# ─────────── Tributação: repassa a Z4 VERBATIM (sem régua paralela, com a norma) ───────────


@_consulta
async def _tributacao_nfe(
    db,
    user,
    scope,
    *,
    empresa_cnpj=None,
    ncm=None,
    valor=None,
    quantidade=1,
    origem="0",
    destinatario=None,
    operacao="revenda",
    **_,
) -> Any:
    _gate(user)
    try:
        from modules.fiscal.services import tributacao_nfe as z4
    except ImportError:
        return _nao_sei(
            "o serviço de tributação de NF-e de mercadoria "
            "(`modules/fiscal/services/tributacao_nfe.py`, frente Z4) não está neste "
            "servidor. Sem ele eu NÃO calculo imposto: alíquota, CST/CSOSN e CFOP de "
            "mercadoria não saem de palpite meu."
        )
    if not empresa_cnpj or valor in (None, ""):
        return {
            "status": "recusado",
            "motivo": "informe `empresa_cnpj` (o CNPJ emitente) e `valor` (unitário, R$). "
            "Opcionais: ncm, quantidade, origem (0=nacional), operacao "
            "('revenda'|'producao') e `destinatario` "
            "{uf, cnpj, inscricao_estadual, inscricao_suframa, codigo_municipio}.",
        }
    produto = {
        "ncm": str(ncm or "").strip(),
        "valor": valor,
        "quantidade": quantidade or 1,
        "origem": str(origem or "0"),
    }
    dest = dict(destinatario or {})
    try:
        calculo = await z4.calcular(db, str(empresa_cnpj), produto, dest, str(operacao or "revenda"))
    except Exception as exc:  # noqa: BLE001 — erro do serviço é erro, nunca vira número chutado
        return _nao_sei(
            f"o serviço de tributação falhou: {type(exc).__name__}: {str(exc)[:200]}. "
            "Não substituo o cálculo dele por conta própria."
        )
    return {
        "fonte": "modules/fiscal/services/tributacao_nfe.py (frente Z4) — repassado sem alteração",
        "calculo": calculo,
        "aviso": (
            f"Repasse as linhas COMO ESTÃO, cada número com a sua `norma` e `origem_regra`. "
            f"Onde a regra disser «{SEM_FONTE}», diga exatamente essas palavras ao usuário e "
            f"aponte {PAINEL_DECISOES}. NUNCA complete um valor nulo com estimativa sua."
        ),
    }


# ────────────────────────────── Orçamento de origem (CRM) ──────────────────────────────


@_consulta
async def _orcamento_origem(db, user, scope, *, numero=None, busca=None, limite=10, **_) -> Any:
    _gate(user)
    if not await _tabela_existe(db, "proposals"):
        return _nao_sei("a tabela `proposals` (orçamentos/propostas) não existe neste banco.")
    if not (numero or busca):
        return {
            "status": "recusado",
            "motivo": "informe `numero` (ex.: PROP-2026-00096) ou `busca` (parte do nome do cliente ou do título).",
        }
    p = {
        "numero": str(numero).strip() if numero else None,
        "like": f"%{str(busca).strip()}%" if busca else None,
        "lim": max(1, min(int(limite), 30)),
    }
    props = [
        dict(x)
        for x in (
            await db.execute(
                _t(
                    "SELECT id::text, number, title, client_name, client_document, status, total, "
                    "       to_char(issue_date,'DD/MM/YYYY') AS emissao, "
                    "       to_char(valid_until,'DD/MM/YYYY') AS validade, "
                    "       to_char(responded_at,'DD/MM/YYYY') AS respondida_em, "
                    "       (approved_at IS NOT NULL) AS aprovada_internamente "
                    "FROM proposals WHERE COALESCE(is_active, TRUE) "
                    "  AND (CAST(:numero AS text) IS NULL OR upper(number) = upper(:numero)) "
                    "  AND (CAST(:like AS text) IS NULL OR client_name ILIKE :like OR title ILIKE :like) "
                    "ORDER BY created_at DESC LIMIT :lim"
                ),
                p,
            )
        )
        .mappings()
        .all()
    ]
    if not props:
        return _nao_sei("nenhum orçamento/proposta com esse número ou nome em `proposals`.")
    tem_itens = await _tabela_existe(db, "proposal_items")
    for pr in props:
        pr["total"] = float(pr["total"] or 0)
        pr["itens"] = (
            [
                dict(x)
                for x in (
                    await db.execute(
                        _t(
                            "SELECT code, name, description, unit, quantity, unit_price, total, natureza_item "
                            "FROM proposal_items WHERE proposal_id = CAST(:id AS uuid) "
                            "AND COALESCE(is_active, TRUE) ORDER BY sort_order, created_at"
                        ),
                        {"id": pr["id"]},
                    )
                )
                .mappings()
                .all()
            ]
            if tem_itens
            else []
        )
    return {
        "fonte": "proposals + proposal_items (o orçamento de origem, CRM/Cowork-MCP)",
        "total": len(props),
        "orcamentos": props,
        "aviso": (
            "'accepted' é ACEITE DO CLIENTE; `aprovada_internamente` é outra coisa. Um item de "
            "orçamento só vira linha de NF-e depois que uma PESSOA casa cada item com um produto "
            "do cadastro fiscal — descrição livre de orçamento não tem NCM nem CFOP, e eu não "
            "invento nenhum dos dois."
        ),
    }


# ───────────────────────────── registro no consultar_fiscal ─────────────────────────────

registrar_read(
    _MOD,
    "nfe_saida",
    "NF-e de MERCADORIA (modelo 55) emitidas/tentadas pela casa, com STATUS de cada "
    "uma. NÃO é NFS-e de serviço. Filtros: competencia ('AAAA-MM'), numero, serie, "
    "status, chave, empresa (slug ou CNPJ), limite.",
    _nfe_saida,
)
registrar_read(
    _MOD,
    "nfe_rejeicao",
    "Por que uma NF-e foi rejeitada: devolve o xMotivo LITERAL do retorno da SEFAZ, "
    "qual campo corrigir e — quando a rejeição é de NCM — quais itens da nota têm NCM "
    "fora da tabela oficial. Filtros: numero (+serie), chave ou id.",
    _nfe_rejeicao,
)
registrar_read(
    _MOD,
    "produto_fiscal",
    "Cadastro fiscal do produto (NCM, origem, CEST, unidade) e o que falta nele para a "
    "nota sair. Valida o NCM contra a tabela oficial `ncms`. Filtros: codigo ou busca "
    "(parte da descrição), limite. Para ACHAR um NCM pela descrição use 'buscar_ncm'.",
    _produto_fiscal,
)
registrar_read(
    _MOD,
    "tributacao_nfe",
    "Tributação calculada de uma venda de mercadoria (CFOP, CST/CSOSN, ICMS, IPI, "
    "PIS/COFINS), cada número com a NORMA que o fundamenta. Filtros: empresa_cnpj*, "
    "valor*, ncm, quantidade, origem, operacao ('revenda'|'producao'), destinatario "
    "{uf, cnpj, inscricao_estadual, inscricao_suframa, codigo_municipio}. É o cálculo "
    "do serviço fiscal da casa, repassado sem alteração — não recalcule por fora.",
    _tributacao_nfe,
)
registrar_read(
    _MOD,
    "orcamento_origem",
    "O orçamento/proposta que origina a nota, com seus itens. Filtros: numero "
    "(PROP-...) ou busca (cliente/título), limite.",
    _orcamento_origem,
)
