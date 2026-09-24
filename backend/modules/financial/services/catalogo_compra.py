"""Nota de compra → catálogo de produto, com proposta de agrupamento (DGX AA1).

24/09/2026. Pedido do dono: *«baseado nas notas fiscais de compra da Conecta Eletrônica cadastrar
os produtos, ter cuidado com duplicidades, pois aí na hora de fazer o orçamento fazemos pelo CRM,
já estará lá com toda a descrição, só seleciona o item e as quantidades»*. E, no mesmo dia, a regra
que cancela qualquer preço automático: *«nos produtos cadastrados deixem sem valor, quando eu for
fazer os orçamentos eu edito o preço, porque os preços variam muito»*.

O que foi CAVADO antes de construir (sandbox = cópia de produção de 23/09):

  · **A fonte única já estava escolhida pelo próprio código, e ninguém tinha escrito isso.**
    `modules/crm/services/catalogo.py` — o catálogo que o orçamento do CRM lê — já faz
    `UNION` de `crm_products` (115, com preço praticado) com **`products`** (867, do Bling, com
    NCM/CEST/unidade). Quem entra em `products` aparece no orçamento **sem mais nenhuma linha de
    código**. `fin_produtos` (95, da Z1) não é catálogo: é **um registro por NCM distinto** das
    compras — as 10 botas em 10 tamanhos viraram UMA linha lá. Logo: **`products` é o catálogo,
    `fin_produtos` é a face fiscal dele, e o elo é uma coluna** (`fin_produtos.product_id`).

  · **Casar os dois por código é FALSO — medido.** `products.code` (Bling) e
    `nfe_compras_estoque.item_code` (fornecedor) colidem: das 16 linhas de compra cujo código
    existe em `products`, **9 são produtos diferentes** — «ENXADA LARGA 30CM» casou com «Desempeno
    das portas», «AREIA EM SACO» com «Controle remoto xac 4000 smart», «COLHER PEDREIRO N10» com
    «DVR 16 portas». Só os códigos que carregam o espaço do fornecedor (`VTV-*`) são verdadeiros
    (7 de 7). Por isso o código aqui é **evidência, nunca prova**: sozinho ele não casa nada.

  · **«Mesmo NCM = mesmo produto» está errado nas duas direções**, e também foi medido:
    NCM 64039190 = 10 linhas que são UMA bota em 10 tamanhos (N36…N45); NCM 34025000 = 9 linhas
    que são 9 produtos diferentes (detergente, lava-roupas, limpa-vidros, multiuso, sabão em pó de
    três marcas). O NCM **não entra** na régua de agrupamento — ele viaja como dado fiscal do item.

A régua de semelhança é a do `produto_fiscal.py` (`_toks`/`_sim`/`_CORTE_FORTE = 0,80`), importada
e não copiada. O corte 0,80 foi medido lá: em 0,70 «Cabo de rede 4PX0,5 bobina 300MT» casou com
«TESTADOR DE CABO DE REDE».

**Nada entra sozinho.** Este módulo só escreve em `fin_catalogo_candidatos` (a proposta). Quem
cria produto é `aprovar()`, chamada por uma pessoa na tela, e cada linha aprovada guarda quem,
quando, com que score e por qual motivo — porque **fusão no escuro é o defeito que esta frente
existe para impedir**.

**Preço: nada.** Nenhuma das seis colunas de preço de `products` (`reference_price`,
`last_purchase_price`, `average_price`, `min_price`, `max_price`, `price_history`) é escrita aqui —
as 867 linhas estão todas zeradas hoje e continuam. O **custo** da compra (`unit_cost` da nota)
aparece na tela rotulado como custo, e não é copiado para campo nenhum de venda.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy import text

from .produto_fiscal import _CORTE_FORTE, _sim, _toks

logger = logging.getLogger(__name__)

#: Um token é «de variação» quando ele sozinho distingue tamanho, volume, potência ou cor —
#: o resto da descrição sendo igual. Numeração de calçado (`N36`), medida com unidade (`500ML`,
#: `4KG`, `300MT`, `11W`) e cor. Não inclui tamanho de uma letra só (P/M/G): `_toks` descarta
#: token de 1 caractere, então eles nem chegam aqui — ver §5 do relatório.
_UNIDADES = "ML|L|KG|G|MG|MT|M|CM|MM|W|V|A|VA|TON|POL|LTS|UN|PCS"
_RE_VARIACAO = re.compile(rf"^(?:N\d{{2}}|\d+(?:[.,]\d+)?(?:{_UNIDADES})|\d{{2,3}}X\d{{2,3}})$")
_CORES = {
    "PRETO",
    "PRETA",
    "BRANCO",
    "BRANCA",
    "AZUL",
    "VERMELHO",
    "VERMELHA",
    "VERDE",
    "AMARELO",
    "AMARELA",
    "CINZA",
    "MARROM",
    "ROSA",
    "LARANJA",
    "BEGE",
    "PRATA",
    "DOURADO",
    "DOURADA",
    "TRANSPARENTE",
    "INCOLOR",
    "ROXO",
    "ROXA",
}

#: Só o código bate e a descrição concorda **um pouco**. Abaixo disso o código é tratado como
#: colisão de namespace (os 9 casos medidos) e a linha vira candidato NOVO, com o aviso escrito.
_CORTE_CODIGO = 0.30

CLASSES = ("novo", "igual", "variacao")


#: Dígito sozinho — `_toks` joga fora token de 1 caractere, e aqui isso funde produto.
#: MEDIDO: «BUCHA NYLON S- 6 C/ ABA» saía com semelhança 1,00 contra «Bucha nylon S- 8 c/ aba»,
#: porque o 6 e o 8 sumiam. São buchas de bitolas diferentes. Guardar o dígito derruba para 0,75.
_RE_DIGITO_SO = re.compile(r"(?<![A-Z0-9])(\d)(?![A-Z0-9])")


def _eh_variacao(tok: str) -> bool:
    return bool(_RE_VARIACAO.match(tok)) or tok in _CORES


def _toks_cat(s: str) -> set[str]:
    """`_toks` do `produto_fiscal` + os dígitos solitários. Ver `_RE_DIGITO_SO`."""
    t = unicodedata.normalize("NFKD", str(s or "").upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return _toks(s) | set(_RE_DIGITO_SO.findall(re.sub(r"[^A-Z0-9]", " ", t)))


def _comparar(a: set[str], b: set[str]) -> tuple[float, set[str], set[str], set[str], set[str]]:
    """score · variação de cada lado · o que sobra de diferente **em cada lado**.

    A diferença entre `resto` de um lado só e `resto` dos DOIS lados é o que separa «a nota é mais
    detalhada que o catálogo» de «cada um afirma uma coisa que o outro nega». MEDIDO: «LIMPADOR
    PERF **AMEIXA** DOURADA 120ML COALA» × «LIMPADOR PERF **ROMA** 120ML COALA» tem semelhança
    0,80 e uma cor no meio — mas sobra AMEIXA de um lado e ROMA do outro: são dois perfumes, dois
    produtos. Já as 10 botas sobram só «USAFE» de um lado (a marca escrita de dois jeitos).
    """
    score = _sim(a, b)
    va = {t for t in (a - b) if _eh_variacao(t)}
    vb = {t for t in (b - a) if _eh_variacao(t)}
    return score, va, vb, (a - b) - va, (b - a) - vb


async def _ensure(db) -> None:
    """DDL idempotente. Nunca alembic, nunca DROP."""
    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS fin_catalogo_candidatos (
                id SERIAL PRIMARY KEY,
                item_code TEXT NOT NULL UNIQUE,
                descricao TEXT NOT NULL,
                ncm VARCHAR(8),
                unidade VARCHAR(12),
                custo_unitario NUMERIC(14,4),   -- CUSTO da nota de compra. NUNCA preço de venda.
                classe VARCHAR(12) NOT NULL,
                score NUMERIC(4,2) NOT NULL DEFAULT 0,
                motivo TEXT NOT NULL,
                alvo_product_id UUID,
                alvo_item_code TEXT,
                traco TEXT,
                status VARCHAR(12) NOT NULL DEFAULT 'pendente',
                product_id UUID,
                decidido_por TEXT,
                decidido_em TIMESTAMP,
                criado_em TIMESTAMP NOT NULL DEFAULT now()
            )
            """
        )
    )
    await db.execute(
        text("CREATE INDEX IF NOT EXISTS ix_fin_cat_cand_status ON fin_catalogo_candidatos (status, classe)")
    )
    # O elo comercial ↔ fiscal: UMA coluna, não uma terceira tabela. `IF EXISTS` porque a tabela
    # é da frente Z1 e a ordem de merge não é garantida.
    await db.execute(text("ALTER TABLE IF EXISTS fin_produtos ADD COLUMN IF NOT EXISTS product_id UUID"))
    await db.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_fin_produtos_product "
            "ON fin_produtos (product_id) WHERE product_id IS NOT NULL"
        )
    )
    await db.commit()


async def _catalogo(db) -> list[tuple]:
    """(id, code, name, ncm) de `products` ativos, com os tokens já calculados."""
    linhas = (
        await db.execute(
            text(
                "SELECT id, coalesce(code,''), coalesce(name,''), coalesce(ncm,'') "
                "FROM products WHERE coalesce(ativo, true)"
            )
        )
    ).fetchall()
    return [(pid, code, nome, ncm, _toks_cat(nome)) for pid, code, nome, ncm in linhas]


async def _ncms_vigentes(db) -> set[str]:
    """Os códigos da nomenclatura oficial (`ncms`, 10.515 vigentes, Portal Único Siscomex)."""
    if not (await db.execute(text("SELECT to_regclass('ncms')"))).scalar():
        return set()
    return {str(r[0]) for r in (await db.execute(text("SELECT codigo FROM ncms WHERE active IS NOT false"))).fetchall()}


async def classificar(db) -> dict:
    """Recalcula a proposta a partir de `nfe_compras_estoque`. **Não cria produto nenhum.**

    Ordem da evidência (a mesma lógica de força do `sugerir_ncm`: documento antes de palpite):

      1. **descrição forte** (score ≥ 0,80 contra um produto do catálogo) — se o que difere são
         só tokens de variação, é `variacao`; senão é `igual`;
      2. **código do fornecedor + descrição concordando em parte** (≥ 0,30) — `igual`, com as duas
         evidências escritas no motivo;
      3. senão **`novo`**. Se o código colide com um produto de descrição diferente, o motivo diz
         isso e a aprovação usa um código livre — nunca sobrescreve a linha de outro produto.

    Depois, entre os `novo`, agrupa o que é variação um do outro (as 10 botas): o de menor código
    fica como representante e os outros viram `variacao` apontando para ele (`alvo_item_code`).

    Linhas já decididas (`status <> 'pendente'`) não são tocadas — reclassificar o que uma pessoa
    já aprovou seria desfazer decisão dela.
    """
    await _ensure(db)
    catalogo = await _catalogo(db)
    vigentes = await _ncms_vigentes(db)
    por_codigo = {str(r[1]).strip().upper(): r for r in catalogo if str(r[1]).strip()}

    itens = (
        await db.execute(
            text(
                "SELECT e.item_code, coalesce(e.descricao,''), coalesce(e.ncm,''), "
                "coalesce(e.unidade,''), e.unit_cost, coalesce(n.numero,''), coalesce(n.emitente_nome,'') "
                "FROM nfe_compras_estoque e "
                "LEFT JOIN nfe_entradas n ON n.chave_acesso = e.last_nfe_key "
                "WHERE coalesce(e.descricao,'') <> '' "
                "ORDER BY e.item_code"
            )
        )
    ).fetchall()

    decididos = {
        r[0]
        for r in (
            await db.execute(text("SELECT item_code FROM fin_catalogo_candidatos WHERE status <> 'pendente'"))
        ).fetchall()
    }

    props: list[dict] = []
    for item_code, desc, ncm, unidade, custo, numero, emitente in itens:
        if item_code in decididos:
            continue
        alvo = _toks_cat(desc)
        fonte = f"NF-e {numero}" if numero else "nota de compra"
        if emitente:
            fonte += f" de {str(emitente)[:30]}"
        p = {
            "item_code": item_code,
            "descricao": desc,
            "ncm": ncm or None,
            "unidade": unidade or None,
            "custo_unitario": custo,
            "classe": "novo",
            "score": 0.0,
            "motivo": f"nada parecido no catálogo — {fonte}",
            "alvo_product_id": None,
            "alvo_item_code": None,
            "traco": None,
        }
        gemeo = por_codigo.get(str(item_code).strip().upper())
        if not alvo:
            props.append(p)
            continue

        score, row = max(((_sim(alvo, row[4]), row) for row in catalogo), key=lambda x: x[0], default=(0.0, None))
        va = vb = ra = rb = set()
        if row is not None:
            _, va, vb, ra, rb = _comparar(alvo, row[4])

        if row is not None and score >= _CORTE_FORTE and not (ra and rb):
            # O que sobra de diferente está só de um lado: a nota é mais detalhada que o catálogo
            # (ou o contrário). Quando sobra dos DOIS, cada descrição nega a outra — ver `_comparar`.
            nome = row[2]
            sobra = ra | rb
            extra = f"; a nota ainda traz {', '.join(sorted(sobra))}" if sobra else ""
            if va or vb:
                traco = " / ".join(sorted(va | vb))
                p.update(
                    classe="variacao",
                    score=score,
                    alvo_product_id=row[0],
                    traco=traco,
                    motivo=f"variação de «{nome[:46]}» — muda só {traco} (semelhança {score:.2f}){extra}",
                )
            else:
                p.update(
                    classe="igual",
                    score=score,
                    alvo_product_id=row[0],
                    motivo=f"mesma descrição de «{nome[:46]}» — semelhança {score:.2f}{extra}",
                )
        elif gemeo is not None and _sim(alvo, gemeo[4]) >= _CORTE_CODIGO:
            sc_cod = _sim(alvo, gemeo[4])
            p.update(
                classe="igual",
                score=sc_cod,
                alvo_product_id=gemeo[0],
                motivo=(
                    f"código {item_code} é o mesmo de «{gemeo[2][:40]}» no catálogo e as descrições "
                    f"concordam em parte (semelhança {sc_cod:.2f}) — {fonte}"
                ),
            )
        else:
            # NOVO é o padrão SEGURO: fundir é o ato perigoso, então ele exige sinal limpo.
            # O parecido continua gravado em `alvo_product_id` para o botão «não é novo, é este».
            aviso = []
            if row is not None and score >= _CORTE_FORTE:
                p["alvo_product_id"] = row[0]
                p["score"] = score
                aviso.append(
                    f"parece «{row[2][:40]}» (semelhança {score:.2f}) mas cada um afirma o que o "
                    f"outro nega: {', '.join(sorted(ra))} × {', '.join(sorted(rb))} — confira antes de fundir"
                )
            if gemeo is not None:
                if p["alvo_product_id"] is None:
                    p["alvo_product_id"] = gemeo[0]  # o parecido para o botão «é este produto»
                aviso.append(
                    f"o código {item_code} já existe no catálogo como «{gemeo[2][:40]}» e as descrições "
                    f"não se parecem (semelhança {_sim(alvo, gemeo[4]):.2f}) — código de fornecedor não é "
                    "código de catálogo; confira se é o mesmo produto antes de fundir"
                )
            p["motivo"] = ("; ".join(aviso) + f" — {fonte}") if aviso else f"nada parecido no catálogo — {fonte}"
        props.append(p)

    _agrupar_novos(props)

    # Depois do agrupamento, porque ele reescreve o motivo de quem virou variação.
    # Mesmo princípio da Z1: o fornecedor pode ter errado (65119000, «CAPACETE DE SEGURANCA
    # BRANCO» — o capítulo 65 termina em 6507). NCM errado é multa e glosa de crédito, então ele
    # NÃO viaja para o catálogo: a linha avisa, e classificar é trabalho de gente (tela da Z1).
    for p in props:
        if p["ncm"] and vigentes and p["ncm"] not in vigentes:
            p["motivo"] += (
                f" · ATENÇÃO: o NCM {p['ncm']} da nota não existe na nomenclatura vigente — o produto nasce SEM NCM"
            )

    await db.execute(text("DELETE FROM fin_catalogo_candidatos WHERE status = 'pendente'"))
    for p in props:
        await db.execute(
            text(
                "INSERT INTO fin_catalogo_candidatos "
                "(item_code, descricao, ncm, unidade, custo_unitario, classe, score, motivo, "
                " alvo_product_id, alvo_item_code, traco) "
                "VALUES (:item_code, :descricao, :ncm, :unidade, :custo_unitario, :classe, :score, "
                "        :motivo, :alvo_product_id, :alvo_item_code, :traco) "
                "ON CONFLICT (item_code) DO NOTHING"
            ),
            p,
        )
    await db.commit()
    return {c: sum(1 for p in props if p["classe"] == c) for c in CLASSES} | {"total": len(props)}


def _agrupar_novos(props: list[dict]) -> None:
    """As 10 botas: entre os `novo`, quem é variação de quem.

    O de menor código fica como representante (continua `novo`, é ele que vira produto) e os
    demais viram `variacao` apontando para ele por `alvo_item_code`. Assim o orçamento ganha UMA
    linha «bota», e o tamanho continua morando na grade (`sst_uniforme_grade`, frente 10) — não
    no catálogo.
    """
    novos = [p for p in props if p["classe"] == "novo"]
    toks = {p["item_code"]: _toks_cat(p["descricao"]) for p in novos}
    representantes: list[dict] = []
    for p in sorted(novos, key=lambda x: str(x["item_code"])):
        a = toks[p["item_code"]]
        if not a:
            representantes.append(p)
            continue
        for rep in representantes:
            score, va, vb, ra, rb = _comparar(a, toks[rep["item_code"]])
            if score >= _CORTE_FORTE and (va or vb) and not (ra and rb):
                traco = " / ".join(sorted(va | vb))
                p.update(
                    classe="variacao",
                    score=score,
                    alvo_item_code=rep["item_code"],
                    traco=traco,
                    motivo=(
                        f"variação de «{rep['descricao'][:46]}» (item {rep['item_code']}, desta "
                        f"mesma leva) — muda só {traco} (semelhança {score:.2f})"
                    ),
                )
                break
        else:
            representantes.append(p)


async def _condominio(db) -> str:
    cid = (
        await db.execute(text("SELECT condominio_id FROM products WHERE condominio_id IS NOT NULL LIMIT 1"))
    ).scalar()
    if not cid:
        raise HTTPException(400, "Catálogo vazio: não há de onde herdar o condomínio do produto.")
    return str(cid)


async def _codigo_livre(db, item_code: str, condominio_id: str) -> str:
    """`item_code` quando livre; senão `NFE-<item_code>`. Nunca sobrescreve produto de outro."""
    base = str(item_code).strip()
    for cand in (base, f"NFE-{base}"):
        existe = (
            await db.execute(
                text("SELECT 1 FROM products WHERE upper(btrim(code)) = :c AND condominio_id = cast(:k AS uuid)"),
                {"c": cand.upper(), "k": condominio_id},
            )
        ).scalar()
        if not existe:
            return cand
    raise HTTPException(400, f"Código {base} e NFE-{base} já existem no catálogo — resolva na mão.")


async def aprovar(db, ids: list[int], usuario: str) -> dict:
    """Executa a proposta aprovada. **Ato de uma pessoa** — nunca chamado por rotina.

    · `novo`     → cria a linha em `products` (código, descrição, unidade, NCM). **Zero preço.**
    · `igual`    → não cria nada; preenche o NCM do produto **só se estiver vazio** (enriquecer é
                   permitido, sobrescrever não) e guarda o elo.
    · `variacao` → não cria nada; a linha fica ligada ao produto-pai.

    Em qualquer classe, se existir `fin_produtos` com esse `codigo`, o elo comercial ↔ fiscal é
    gravado ali (`product_id`). É esse elo que faz o orçamento aprovado virar nota sem redigitar.
    """
    await _ensure(db)
    if not ids:
        raise HTTPException(400, "Escolha pelo menos um candidato.")
    quem = str(usuario or "").strip() or "desconhecido"
    condominio_id = await _condominio(db)
    vigentes = await _ncms_vigentes(db)

    linhas = (
        await db.execute(
            text(
                "SELECT id, item_code, descricao, ncm, unidade, classe, alvo_product_id, alvo_item_code "
                "FROM fin_catalogo_candidatos WHERE id = ANY(:ids) AND status = 'pendente' "
                # representante antes da variação que aponta para ele
                "ORDER BY CASE classe WHEN 'novo' THEN 0 ELSE 1 END, id"
            ),
            {"ids": [int(i) for i in ids]},
        )
    ).fetchall()
    if not linhas:
        raise HTTPException(400, "Nenhum candidato pendente entre os escolhidos.")

    criados = 0
    ligados = 0
    divergencias: list[str] = []
    por_item: dict[str, str] = {}

    for cid, item_code, desc, ncm, unidade, classe, alvo_pid, alvo_item in linhas:
        if ncm and vigentes and ncm not in vigentes:
            divergencias.append(f"{item_code}: NCM {ncm} da nota não existe na nomenclatura — produto salvo sem NCM")
            ncm = None
        if classe == "novo":
            code = await _codigo_livre(db, item_code, condominio_id)
            pid = (
                await db.execute(
                    text(
                        "INSERT INTO products (id, condominio_id, code, name, unit_of_measure, ncm, "
                        "                      product_type, status, ativo, notes, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), cast(:k AS uuid), :code, :name, :un, :ncm, "
                        "        'material', 'ativo', true, :notes, now(), now()) "
                        "RETURNING id"
                    ),
                    {
                        "k": condominio_id,
                        "code": code,
                        "name": desc[:255],
                        "un": (unidade or "UN")[:20],
                        "ncm": ncm,
                        "notes": (
                            f"Cadastrado da nota de compra (item {item_code}) por {quem} — DGX AA1. "
                            "Sem preço de venda por decisão do dono em 24/09/2026."
                        ),
                    },
                )
            ).scalar()
            criados += 1
        else:
            pid = alvo_pid or (por_item.get(str(alvo_item)) if alvo_item else None)
            if pid is None:
                raise HTTPException(
                    400,
                    f"Candidato {item_code} é «{classe}» de {alvo_item or '—'}, que ainda não foi "
                    "aprovado. Aprove o item representante na mesma leva.",
                )
            if classe == "igual" and ncm:
                atual = (
                    await db.execute(
                        text("SELECT coalesce(ncm,'') FROM products WHERE id = cast(:p AS uuid)"), {"p": str(pid)}
                    )
                ).scalar()
                if not atual:
                    await db.execute(
                        text("UPDATE products SET ncm = :n, updated_at = now() WHERE id = cast(:p AS uuid)"),
                        {"n": ncm, "p": str(pid)},
                    )
                elif atual != ncm:
                    # Nunca sobrescrever NCM que já existe: NCM errado é multa e glosa de crédito.
                    # A divergência é DITA, e quem decide é gente. Ver §7 do relatório.
                    divergencias.append(f"{item_code}: nota diz {ncm}, catálogo diz {atual}")

        por_item[str(item_code)] = str(pid)
        await db.execute(
            text(
                "UPDATE fin_catalogo_candidatos SET status='aprovado', product_id=cast(:p AS uuid), "
                "decidido_por=:q, decidido_em=now() WHERE id=:i"
            ),
            {"p": str(pid), "q": quem, "i": cid},
        )
        ligados += await _ligar_fiscal(db, item_code, str(pid))

    await db.commit()
    return {"criados": criados, "elos_fiscais": ligados, "divergencias": divergencias, "total": len(linhas)}


async def _ligar_fiscal(db, item_code: str, product_id: str) -> int:
    """O elo `fin_produtos.product_id`. Só escreve onde ainda está vazio."""
    existe = (await db.execute(text("SELECT to_regclass('fin_produtos')"))).scalar()
    if not existe:
        return 0
    r = await db.execute(
        text("UPDATE fin_produtos SET product_id = cast(:p AS uuid) WHERE codigo = :c AND product_id IS NULL"),
        {"p": product_id, "c": item_code},
    )
    return int(r.rowcount or 0)


async def rejeitar(db, ids: list[int], usuario: str) -> int:
    await _ensure(db)
    if not ids:
        raise HTTPException(400, "Escolha pelo menos um candidato.")
    r = await db.execute(
        text(
            "UPDATE fin_catalogo_candidatos SET status='rejeitado', decidido_por=:q, decidido_em=now() "
            "WHERE id = ANY(:ids) AND status='pendente'"
        ),
        {"ids": [int(i) for i in ids], "q": str(usuario or "").strip() or "desconhecido"},
    )
    await db.commit()
    return int(r.rowcount or 0)


async def reclassificar(db, cand_id: int, classe: str, usuario: str) -> dict:
    """O humano confirma o que a régua não soube: «é este produto» / «é novo mesmo».

    Só entre `novo` e `igual`, e só enquanto pendente — mexer no que já foi decidido seria
    desfazer decisão de alguém. Vira `igual` apenas se a régua tiver guardado um parecido
    (`alvo_product_id`): sem alvo não há a que ligar, e escolher no escuro é o que não se faz aqui.
    """
    await _ensure(db)
    if classe not in ("novo", "igual"):
        raise HTTPException(400, "Só dá para alternar entre «novo» e «já existe».")
    linha = (
        await db.execute(
            text(
                "SELECT item_code, alvo_product_id FROM fin_catalogo_candidatos WHERE id = :i AND status = 'pendente'"
            ),
            {"i": int(cand_id)},
        )
    ).first()
    if linha is None:
        raise HTTPException(404, "Candidato não encontrado ou já decidido.")
    if classe == "igual" and linha[1] is None:
        raise HTTPException(400, "Este candidato não tem produto parecido para ligar.")
    await db.execute(
        text(
            # ⚠️ sem bind nu dentro do `||`: o asyncpg deduz dois tipos para o mesmo $1 e
            # levanta AmbiguousParameterError (medido em 24/09). Cada uso vai com cast próprio.
            "UPDATE fin_catalogo_candidatos SET classe = cast(:c AS varchar), traco = NULL, "
            "motivo = motivo || ' · reclassificado para «' || cast(:c AS text) || '» por ' "
            "                || cast(:q AS text) "
            "WHERE id = :i"
        ),
        {"c": classe, "i": int(cand_id), "q": str(usuario or "").strip() or "desconhecido"},
    )
    await db.commit()
    return {"item_code": linha[0], "classe": classe}


async def classificar_se_houver_novidade(db) -> int:
    """Refaz a proposta quando chegou nota nova. Chamado pelo build da tela.

    Sem botão de propósito: a nota de compra entra pela F9 e a proposta tem de aparecer sozinha.
    A comparação é 147 × 867 conjuntos, cara demais para rodar a cada abertura da tela — então só
    roda quando há mais linha de compra do que candidato. Nada decidido é tocado (`classificar`).
    """
    n_itens = (
        await db.execute(text("SELECT count(*) FROM nfe_compras_estoque WHERE coalesce(descricao,'') <> ''"))
    ).scalar() or 0
    n_cands = (await db.execute(text("SELECT count(*) FROM fin_catalogo_candidatos"))).scalar() or 0
    if n_cands >= n_itens:
        return 0
    r = await classificar(db)
    return int(r["total"])


async def resumo(db) -> dict:
    await _ensure(db)
    linhas = (
        await db.execute(text("SELECT status, classe, count(*) FROM fin_catalogo_candidatos GROUP BY 1, 2"))
    ).fetchall()
    out = {"pendente": dict.fromkeys(CLASSES, 0), "aprovado": 0, "rejeitado": 0}
    for status, classe, n in linhas:
        if status == "pendente":
            out["pendente"][classe] = n
        else:
            out[status] = out.get(status, 0) + n
    return out
