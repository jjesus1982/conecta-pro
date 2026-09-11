"""
Controller das 9 features de crescimento do CRM (HubSpot-like).
Um único router montado sob /crm. Endpoints públicos: /public/forms/* e /public/booking/*.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser

from core.auth.dependencies import get_current_active_user
from core.database import get_db
from modules.crm.services import growth_services as G

router = APIRouter(tags=["CRM - Growth"])


def _rows(result) -> list[dict]:
    return [dict(r) for r in result.mappings().all()]


async def _one(db, sql, params) -> dict | None:
    r = (await db.execute(text(sql), params)).mappings().first()
    return dict(r) if r else None


_PUBLIC_ERP = os.getenv("PUBLIC_ERP_URL", "https://erp.conectamais.pro").rstrip("/")
_DOCS_DIR = os.getenv("UPLOADS_DIR", "/app/uploads") + "/docs"


async def _salvar_pdf(db, tipo: str, titulo: str, pdf_bytes: bytes, *, ref_tipo=None, ref_id=None, teste=False, drive=False, filename=None) -> dict:
    """Persiste + registra + link público (delega ao docs_registry). drive=True: sobe pro Google Drive."""
    from modules.crm.services.docs_registry import salvar_pdf

    return await salvar_pdf(db, tipo, titulo, pdf_bytes, ref_tipo=ref_tipo, ref_id=ref_id, teste=teste, drive=drive, filename=filename)


@router.get("/docs/download/{doc_id}")
async def baixar_documento(doc_id: str, t: str = "", db: AsyncSession = Depends(get_db)):
    """Download PÚBLICO (tokenizado) de um documento registrado — clicável no navegador/Cowork."""
    from fastapi import Response

    row = await _one(
        db, "SELECT tipo, titulo, arquivo, token FROM crm_documents WHERE id=:id AND arquivado=false", {"id": doc_id}
    )
    if not row or not t or row["token"] != t:
        raise HTTPException(404, "Documento não encontrado")
    import os as _os

    if not _os.path.exists(row["arquivo"]):
        raise HTTPException(404, "Arquivo não disponível")
    with open(row["arquivo"], "rb") as fh:
        data = fh.read()
    fn = f"{row['tipo']}_{doc_id[:8]}.pdf"
    return Response(
        content=data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{fn}"'}
    )


@router.get("/docs")
async def listar_documentos(db: AsyncSession = Depends(get_db), tipo: str | None = None, limite: int = 50):
    """Lista os documentos gerados/registrados (registro no Conecta PRO). Ignora arquivados."""
    where = "WHERE arquivado=false" + (" AND tipo=:tipo" if tipo else "")
    rows = _rows(
        await db.execute(
            text(f"""
        SELECT id, tipo, titulo, token, tamanho_kb, teste, to_char(created_at,'DD/MM/YYYY HH24:MI') criado
        FROM crm_documents {where} ORDER BY created_at DESC LIMIT :lim
    """),
            {"tipo": tipo, "lim": limite} if tipo else {"lim": limite},
        )
    )
    for r in rows:
        r["download_url"] = f"{_PUBLIC_ERP}/api/v1/crm/docs/download/{r['id']}?t={r.pop('token')}"
    return {"total": len(rows), "documentos": rows}


@router.get("/audit")
async def consultar_auditoria(
    db: AsyncSession = Depends(get_db), limite: int = 50, metodo: str | None = None, busca: str | None = None
):
    """Log de auditoria das escritas (quem/quando/o quê/resultado). Filtra por método (POST/PUT/DELETE)
    ou trecho do caminho (busca)."""
    where, p = ["1=1"], {"lim": limite}
    if metodo:
        where.append("a.method = :m")
        p["m"] = metodo.upper()
    if busca:
        where.append("a.path ILIKE :b")
        p["b"] = f"%{busca}%"
    rows = _rows(
        await db.execute(
            text(f"""
        SELECT to_char(a.ts,'DD/MM/YYYY HH24:MI:SS') quando, COALESCE(u.name, u.email, '—') quem,
               a.method metodo, a.path caminho, a.status, a.ip
        FROM crm_audit_log a LEFT JOIN users u ON u.id = a.user_id
        WHERE {" AND ".join(where)} ORDER BY a.ts DESC LIMIT :lim
    """),
            p,
        )
    )
    return {"total": len(rows), "eventos": rows}


# ===================================================================== PRECIFICAÇÃO (CCT 2026)
@router.get("/pricing/parametros")
async def pricing_parametros(db: AsyncSession = Depends(get_db)):
    """Parâmetros editáveis de precificação (Lucro Real, CCT 2026) — encargos, tributos, margem, benefícios."""
    rows = _rows(
        await db.execute(text("SELECT chave, valor, label, grupo FROM crm_pricing_params ORDER BY grupo, chave"))
    )
    for r in rows:
        r["valor"] = float(r["valor"])
    return {"regime": "Grupo Conecta Mais · CCT 2026 SINDECOMPRESTS · encargos por regime da empresa do contrato (revisão multi-CNPJ)", "parametros": rows}


class ParamsIn(BaseModel):
    valores: dict


@router.put("/pricing/parametros")
async def pricing_atualizar_parametros(
    data: ParamsIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Atualiza parâmetros (sincronizar a planilha). valores = {chave: valor}."""
    n = 0
    for k, v in (data.valores or {}).items():
        res = await db.execute(
            text("UPDATE crm_pricing_params SET valor=:v, updated_at=now() WHERE chave=:k"), {"v": float(v), "k": k}
        )
        n += res.rowcount or 0
    await db.commit()
    return {"atualizados": n}


@router.get("/pricing/funcoes")
async def pricing_funcoes(db: AsyncSession = Depends(get_db)):
    """Tabela de preços por função (custo, preço, markup, adicionais) — alinhada à planilha."""
    from modules.crm.services.pricing_cct import calcular_funcao

    rows = _rows(await db.execute(text("SELECT * FROM crm_pricing_funcoes WHERE ativo ORDER BY ordem")))
    out = []
    for r in rows:
        c = await calcular_funcao(db, r)
        out.append(
            {
                "funcao": c["funcao"],
                "adicionais": c["adicionais"],
                "salario_base": c["salario_base"],
                "custo_total": c["custo_total"],
                "preco": c["preco"],
                "markup_pct": c["markup_pct"],
                "lucro_liquido": c["lucro_liquido"],
            }
        )
    return {"regime": "Grupo Conecta Mais · Margem 15% · CCT 2026 · encargos por regime da empresa (revisão multi-CNPJ)", "funcoes": out}


class SimularIn(BaseModel):
    funcao: str | None = None
    salario_base: float | None = None
    jornada_dias: int = 15
    postos: int = 1
    noturno: bool = False
    hora_reduzida: bool = False
    ronda: bool = False
    intrajornada: bool = False
    periculosidade: bool = False
    insalubridade: bool = False
    margem: float | None = None


@router.post("/pricing/simular")
async def pricing_simular(data: SimularIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Simula o preço de uma função (replica o simulador da planilha). Aceita função existente OU salário base."""
    from modules.crm.services.pricing_cct import FLAGS_FUNCAO, calcular, carregar_params

    base, jornada = data.salario_base, data.jornada_dias
    # FLAGS_FUNCAO é a fonte única (pricing_cct). Enumerar à mão aqui já custou caro:
    # um adicional novo no motor ficava de fora e este simulador cotava mais barato
    # que /pricing/funcoes e que o José Luís, para a MESMA função.
    flags = {k: bool(getattr(data, k, False)) for k in FLAGS_FUNCAO}
    flags["margem"] = data.margem
    if data.funcao and base is None:
        # SELECT * de propósito: imune a coluna de flag nova na crm_pricing_funcoes.
        row = await _one(db, "SELECT * FROM crm_pricing_funcoes WHERE nome ILIKE :n", {"n": data.funcao})
        if row:
            base = float(row["salario_base"])
            jornada = int(row["jornada_dias"])
            # a função carrega seus adicionais; o payload pode ATIVAR mais (OR)
            for k in FLAGS_FUNCAO:
                flags[k] = bool(flags.get(k)) or bool(row.get(k))
    if base is None:
        base = 1670
    r = calcular(base, jornada, flags, await carregar_params(db))
    r["postos"] = data.postos
    r["preco_total_postos"] = round(r["preco"] * data.postos, 2)
    return r


@router.delete("/docs/{doc_id}", status_code=204)
async def excluir_documento(doc_id: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Exclui (soft-delete) um documento registrado."""
    await db.execute(text("UPDATE crm_documents SET arquivado=true WHERE id=:id"), {"id": doc_id})
    await db.commit()


@router.get("/contexto-cliente")
async def contexto_cliente(
    current_user: CurrentActiveUser,  # noqa: ARG001
    chave: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """DOSSIÊ do cliente numa chamada só: cadastro, contratos, propostas, oportunidades,
    documentos, recebíveis em aberto e últimas interações.

    Item 3.6 do relatório de campo do Jordan sobre o Cowork (11/09/2026): responder "como
    está o Kopenhagen?" custava ~6 chamadas, e o agente montava a resposta com pedaços que
    chegavam em ordens diferentes. Aqui é uma viagem, com o mesmo retrato para todo mundo.

    `chave` aceita CNPJ (com ou sem máscara), código (CLI-…), id ou nome aproximado.
    Só LÊ.
    """
    digitos = re.sub(r"\D", "", chave or "")
    cli = (await db.execute(text("""
        SELECT id::text, code, name, coalesce(document_number,'') AS doc,
               coalesce(email,'') AS email, coalesce(phone,'') AS fone,
               coalesce(address_city,'') AS cidade, coalesce(ativo,true) AS ativo
          FROM clients
         WHERE (:d <> '' AND regexp_replace(coalesce(document_number,''),'[^0-9]','','g') = :d)
            OR upper(coalesce(code,'')) = upper(:k)
            OR id::text = :k
            OR unaccent(lower(name)) LIKE '%' || unaccent(lower(:k)) || '%'
         ORDER BY ativo DESC, name
         LIMIT 5"""), {"d": digitos, "k": (chave or "").strip()})).mappings().all()
    if not cli:
        raise HTTPException(status_code=404, detail=f"Nenhum cliente corresponde a {chave!r}.")
    if len(cli) > 1:
        # AMBÍGUO não é erro: devolve a escolha. Montar o dossiê do cliente errado é pior
        # que não montar — o agente age sobre ele achando que é o certo.
        raise HTTPException(status_code=409, detail={
            "codigo": "AMBIGUO",
            "mensagem": f"{len(cli)} clientes correspondem a {chave!r}.",
            "candidatos": [{"codigo": c["code"], "nome": c["name"], "cnpj": c["doc"]}
                           for c in cli]})
    c = cli[0]
    cid = c["id"]

    contratos = (await db.execute(text("""
        SELECT ct.contract_number, ct.contract_type::text AS tipo, ct.status::text AS status,
               coalesce(ct.monthly_value,0) AS mensal, coalesce(ct.total_value,0) AS total,
               coalesce(ct.tipo_servico::text,'') AS servico,
               coalesce(e.razao_social,'') AS emitente,
               (SELECT count(*) FROM sig_signature_requests s
                 WHERE s.reference_code = ct.contract_number
                   AND upper(coalesce(s.status::text,'')) NOT IN ('CANCELLED','CANCELED','EXPIRED')) AS assin_abertas,
               (SELECT count(*) FROM sig_signature_requests s
                 WHERE s.reference_code = ct.contract_number AND s.signed_at IS NOT NULL) AS assin_feitas
          FROM contracts ct LEFT JOIN empresas e ON e.id = ct.empresa_id
         WHERE ct.client_id::text = :c ORDER BY ct.created_at DESC"""), {"c": cid})).mappings().all()

    props = (await db.execute(text("""
        SELECT number, coalesce(title,'') AS titulo, coalesce(total,0) AS valor, status::text AS status
          FROM proposals WHERE client_name ILIKE :n AND coalesce(is_active,true)
         ORDER BY created_at DESC LIMIT 10"""), {"n": f"%{c['name'][:24]}%"})).mappings().all()

    opps = (await db.execute(text("""
        SELECT coalesce(title,'') AS titulo, stage::text AS estagio, coalesce(value,0) AS valor
          FROM opportunities
         WHERE coalesce(is_active,true) AND unaccent(lower(coalesce(company_name,''))) LIKE
               '%' || unaccent(lower(:n)) || '%'
         ORDER BY updated_at DESC LIMIT 10"""), {"n": c["name"][:24]})).mappings().all()

    docs = (await db.execute(text("""
        SELECT tipo, titulo, coalesce(tamanho_kb,0) AS kb, created_at
          FROM crm_documents
         WHERE coalesce(arquivado,false) = false
           AND ((ref_tipo = 'cliente' AND ref_id = :c)
             OR (ref_tipo = 'contract' AND ref_id IN (
                   SELECT contract_number FROM contracts WHERE client_id::text = :c))
             OR (ref_tipo = 'contrato' AND ref_id IN (
                   SELECT contract_number FROM contracts WHERE client_id::text = :c)))
         ORDER BY created_at DESC LIMIT 15"""), {"c": cid})).mappings().all()

    receb = (await db.execute(text("""
        SELECT coalesce(sum(net_value),0) AS aberto, count(*) AS n,
               count(*) FILTER (WHERE due_date < current_date) AS vencidos
          FROM receivable_accounts
         WHERE customer_id::text = :c AND lower(coalesce(status::text,'')) NOT IN ('paga','pago','cancelada')"""),
        {"c": cid})).mappings().first()

    ativos = [x for x in contratos if x["status"] in ("active", "ativo", "vigente")]
    return {
        "ok": True,
        "cliente": {"codigo": c["code"], "nome": c["name"], "cnpj": c["doc"],
                    "email": c["email"], "telefone": c["fone"], "cidade": c["cidade"],
                    "ativo": c["ativo"]},
        "resumo": {
            "contratos": len(contratos), "contratos_ativos": len(ativos),
            "mrr": float(sum(float(x["mensal"] or 0) for x in ativos)),
            "propostas_abertas": len([p for p in props if p["status"] in ("sent", "draft")]),
            "oportunidades_abertas": len([o for o in opps
                                          if o["estagio"] not in ("closed_won", "closed_lost")]),
            "documentos": len(docs),
            "recebiveis_em_aberto": float(receb["aberto"] or 0) if receb else 0.0,
            "recebiveis_vencidos": int(receb["vencidos"] or 0) if receb else 0,
        },
        "contratos": [{"numero": x["contract_number"], "tipo": x["tipo"], "status": x["status"],
                       "servico": x["servico"], "emitente": x["emitente"],
                       "mensal": float(x["mensal"] or 0), "total": float(x["total"] or 0),
                       "assinaturas": f"{x['assin_feitas']}/{x['assin_abertas']}"
                       if x["assin_abertas"] else "não aberta"} for x in contratos],
        "propostas": [{"numero": p["number"], "titulo": p["titulo"][:60],
                       "valor": float(p["valor"] or 0), "status": p["status"]} for p in props],
        "oportunidades": [{"titulo": o["titulo"][:60], "estagio": o["estagio"],
                           "valor": float(o["valor"] or 0)} for o in opps],
        "documentos": [{"categoria": d["tipo"], "nome": d["titulo"][:60],
                        "tamanho_kb": float(d["kb"] or 0),
                        "criado_em": d["created_at"].isoformat() if d["created_at"] else None}
                       for d in docs],
    }


@router.post("/docs/anexar")
async def docs_anexar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Anexa um arquivo VINDO DE FORA ao registro de uma entidade (item 2.2).

    O ERP tinha o registro e o artefato morava fora — contrato final, planilha de custo,
    deck, parecer do cliente. Nunca sobrescreve: mesmo nome e categoria vira v2.
    """
    from modules.crm.services.docs_registry import anexar_documento

    try:
        return await anexar_documento(
            db,
            entidade=payload.get("entidade") or "",
            entidade_id=payload.get("entidade_id") or "",
            nome=payload.get("nome") or "",
            conteudo_b64=payload.get("conteudo_b64") or "",
            categoria=payload.get("categoria") or "anexo",
            descricao=payload.get("descricao") or "",
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("/docs/extrair-texto")
async def extrair_texto_de_arquivo(
    current_user: CurrentActiveUser,  # noqa: ARG001
    payload: dict = Body(...),
) -> dict:
    """Texto de um arquivo que o chamador já tem em mãos — sem passar pelo registro.

    As ferramentas de DP (holerite, espelho, comprovante, recibo VT/VR) buscam os bytes
    direto do endpoint que os gera. Sem esta rota elas devolveriam base64 e nenhum texto, e
    o agente continuaria sem poder conferir o que saiu.

    Não grava nada e não guarda o arquivo — o temporário morre no `finally`.
    """
    import base64 as _b64

    from modules.crm.services.docs_registry import extrair_de_bytes

    try:
        bruto = _b64.b64decode(payload.get("base64") or "", validate=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(422, "base64 inválido.") from e
    if not bruto:
        raise HTTPException(422, "arquivo vazio.")
    texto, paginas, motivo = extrair_de_bytes(bruto, (payload.get("ext") or "pdf").lower())
    return {"ok": True, "texto_extraido": texto, "paginas": paginas, "aviso": motivo}


@router.get("/docs/conteudo/{documento_id}")
async def baixar_documento_conteudo(
    documento_id: str,
    current_user: CurrentActiveUser,  # noqa: ARG001 — autenticada, ao contrário do /download público
    formato: str = "base64",
    forcar_base64: bool = False,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """O documento em base64 E em texto. Item 2.2 — o terceiro irmão de anexar/listar.

    Diferente de `/docs/download/{id}`, que é público por token e devolve o binário para o
    NAVEGADOR: aqui a chamada é autenticada e o retorno é legível por um agente.
    """
    from modules.crm.services.docs_registry import baixar

    try:
        return await baixar(db, documento_id=documento_id, formato=formato,
                            forcar_base64=forcar_base64)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(410, str(e)) from e


@router.get("/docs/da-entidade")
async def docs_da_entidade(
    current_user: CurrentActiveUser,  # noqa: ARG001
    entidade: str,
    entidade_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tudo que está pendurado numa entidade — o que o sistema gerou e o que foi anexado."""
    from modules.crm.services.docs_registry import listar_da_entidade

    return await listar_da_entidade(db, entidade=entidade, entidade_id=entidade_id)


@router.post("/docs/expurgar-teste")
async def expurgar_documentos_teste(
    _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db), confirmar: bool = False
):
    """Arquiva (soft-delete) TODOS os documentos de teste (teste=true). confirmar=false só mostra a contagem."""
    n = (await _one(db, "SELECT count(*) v FROM crm_documents WHERE teste=true AND arquivado=false", {})) or {}
    qtd = int(n.get("v", 0))
    if not confirmar:
        return {
            "preview": True,
            "documentos_teste": qtd,
            "aviso": f"{qtd} documento(s) de teste serão arquivados. Reenvie com confirmar=true.",
        }
    await db.execute(text("UPDATE crm_documents SET arquivado=true WHERE teste=true AND arquivado=false"))
    await db.commit()
    return {"expurgados": qtd}


# ===================================================================== ASSETS (upload sem SSH)
_ASSETS_DIR = os.getenv("UPLOADS_DIR", "/app/uploads") + "/assets"
_ASSET_NAMES = {  # tipo -> nome canônico do arquivo lido pelo gerador de PDF
    "logo": "logo-conecta-mais.png",
    "logo_transparente": "logo-transparente.png",
    "logo_branco": "logo-branco.png",
    "selo": "selo.png",
}


class AssetUploadIn(BaseModel):
    tipo: str = "logo"
    conteudo_base64: str
    nome: str | None = None


@router.post("/assets/upload", status_code=201)
async def upload_asset(data: AssetUploadIn, _=Depends(get_current_active_user)):
    """Recebe um asset (logo/selo) em base64 e grava no volume PERSISTENTE /app/uploads/assets.
    O gerador de PDF passa a usar o logo comercial automaticamente (sem rebuild)."""
    import base64
    import os

    raw = data.conteudo_base64
    if "," in raw and raw.strip().startswith("data:"):  # tira prefixo data URI se vier
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"base64 inválido: {exc}")
    if not blob:
        raise HTTPException(400, "conteúdo vazio")
    nome = data.nome or _ASSET_NAMES.get(data.tipo, f"{data.tipo}.png")
    nome = os.path.basename(nome)  # evita path traversal
    os.makedirs(_ASSETS_DIR, exist_ok=True)
    dest = os.path.join(_ASSETS_DIR, nome)
    with open(dest, "wb") as fh:
        fh.write(blob)
    return {"ok": True, "arquivo": nome, "tamanho_kb": round(len(blob) / 1024, 1), "destino": dest}


@router.get("/assets")
async def listar_assets(_=Depends(get_current_active_user)):
    """Lista os assets enviados (persistentes)."""
    import os

    if not os.path.isdir(_ASSETS_DIR):
        return {"assets": []}
    out = []
    for n in sorted(os.listdir(_ASSETS_DIR)):
        fp = os.path.join(_ASSETS_DIR, n)
        if os.path.isfile(fp):
            out.append({"nome": n, "tamanho_kb": round(os.path.getsize(fp) / 1024, 1)})
    return {"assets": out}


# =====================================================================================
# 4) CATÁLOGO DE PRODUTOS/SERVIÇOS (SKU)
# =====================================================================================
class ProductIn(BaseModel):
    name: str
    sku: str | None = None
    description: str | None = None
    category: str | None = None
    unit: str = "un"
    unit_price: float = 0
    is_recurring: bool = False
    service_type: str | None = None
    is_active: bool = True


@router.get("/products")
async def list_products(
    db: AsyncSession = Depends(get_db), search: str | None = None, category: str | None = None, only_active: bool = True
):
    where = ["1=1"]
    p: dict[str, Any] = {}
    if only_active:
        where.append("is_active = true")
    if search:
        # unaccent nos DOIS lados: quem digita "camera" tem de achar "Câmera Bullet IP".
        # Sem isso a busca devolvia 0 para o termo mais óbvio do catálogo de CFTV — medido
        # em 27/08/2026, camera=0 e Câmera=8. A extensão `unaccent` já está instalada.
        where.append("(unaccent(name) ILIKE unaccent(:s) OR unaccent(sku) ILIKE unaccent(:s))")
        p["s"] = f"%{search}%"
    if category:
        where.append("category = :c")
        p["c"] = category
    return _rows(await db.execute(text(f"SELECT * FROM crm_products WHERE {' AND '.join(where)} ORDER BY name"), p))


@router.post("/products", status_code=201)
async def create_product(data: ProductIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    return (
        await _one(
            db,
            """
        INSERT INTO crm_products (id, sku, name, description, category, unit, unit_price, is_recurring,
                                  service_type, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :sku, :name, :description, :category, :unit, :unit_price, :is_recurring,
                :service_type, :is_active, now(), now()) RETURNING *
    """,
            data.model_dump(),
        )
        or {}
    )


@router.put("/products/{pid}")
async def update_product(
    pid: str, data: ProductIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    row = await _one(
        db,
        """
        UPDATE crm_products SET sku=:sku, name=:name, description=:description, category=:category,
            unit=:unit, unit_price=:unit_price, is_recurring=:is_recurring, service_type=:service_type,
            is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(), "id": pid},
    )
    if not row:
        raise HTTPException(404, "Produto não encontrado")
    return row


@router.delete("/products/{pid}", status_code=204)
async def delete_product(pid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("UPDATE crm_products SET is_active=false, updated_at=now() WHERE id=:id"), {"id": pid})
    await db.commit()


# =====================================================================================
# 1) SEQUÊNCIAS / CADÊNCIAS
# =====================================================================================
class SequenceIn(BaseModel):
    name: str
    description: str | None = None
    channel: str = "email"
    steps: list[dict] = []
    is_active: bool = True


@router.get("/sequences")
async def list_sequences(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_sequences ORDER BY created_at DESC")))


@router.post("/sequences", status_code=201)
async def create_sequence(data: SequenceIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    import json

    return (
        await _one(
            db,
            """
        INSERT INTO crm_sequences (id, name, description, channel, steps, is_active, created_at, updated_at)
        VALUES (gen_random_uuid(), :name, :description, :channel, CAST(:steps AS jsonb), :is_active, now(), now())
        RETURNING *
    """,
            {**data.model_dump(exclude={"steps"}), "steps": json.dumps(data.steps)},
        )
        or {}
    )


@router.put("/sequences/{sid}")
async def update_sequence(
    sid: str, data: SequenceIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    import json

    row = await _one(
        db,
        """
        UPDATE crm_sequences SET name=:name, description=:description, channel=:channel,
            steps=CAST(:steps AS jsonb), is_active=:is_active, updated_at=now() WHERE id=:id RETURNING *
    """,
        {**data.model_dump(exclude={"steps"}), "steps": json.dumps(data.steps), "id": sid},
    )
    if not row:
        raise HTTPException(404, "Sequência não encontrada")
    return row


@router.delete("/sequences/{sid}", status_code=204)
async def delete_sequence(sid: str, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    await db.execute(text("DELETE FROM crm_sequences WHERE id=:id"), {"id": sid})
    await db.commit()


class EnrollIn(BaseModel):
    lead_id: str


@router.post("/sequences/{sid}/enroll", status_code=201)
async def enroll_in_sequence(
    sid: str, data: EnrollIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    seq = await _one(db, "SELECT id, steps FROM crm_sequences WHERE id=:id AND is_active=true", {"id": sid})
    if not seq:
        raise HTTPException(404, "Sequência não encontrada ou inativa")
    eid = await G.enroll_lead(db, seq, data.lead_id)
    return {"enrollment_id": eid, "enrolled": bool(eid)}


@router.get("/sequences/{sid}/enrollments")
async def list_enrollments(sid: str, db: AsyncSession = Depends(get_db)):
    return _rows(
        await db.execute(
            text("""
        SELECT e.*, l.name lead_name, l.email lead_email FROM crm_sequence_enrollments e
        LEFT JOIN leads l ON l.id = e.lead_id WHERE e.sequence_id=:s ORDER BY e.enrolled_at DESC
    """),
            {"s": sid},
        )
    )


# =====================================================================================
# 2) WORKFLOWS / AUTOMAÇÃO
# =====================================================================================
class WorkflowIn(BaseModel):
    name: str
    description: str | None = None
    trigger_event: str
    conditions: list[dict] = []
    actions: list[dict] = []
    is_active: bool = True


class WorkflowTestIn(BaseModel):
    lead_id: str


# =====================================================================================
# 3) FORMULÁRIOS DE CAPTURA
# =====================================================================================
class FormIn(BaseModel):
    name: str
    slug: str
    fields: list[dict] = []
    redirect_url: str | None = None
    source: str = "website"
    is_active: bool = True


# =====================================================================================
# 5) AGENDAMENTO DE REUNIÃO/VISTORIA
# =====================================================================================
class BookingLinkIn(BaseModel):
    name: str
    slug: str
    duration_min: int = 60
    weekly_availability: dict = {}
    is_active: bool = True


class BookingIn(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    scheduled_at: datetime
    notes: str | None = None


# =====================================================================================
# 6) SEGMENTOS / LISTAS DINÂMICAS
# =====================================================================================
class SegmentIn(BaseModel):
    name: str
    entity: str = "lead"
    filters: list[dict] = []
    is_active: bool = True


class SegmentPreviewIn(BaseModel):
    entity: str = "lead"
    filters: list[dict] = []


# =====================================================================================
# 7) PROPRIEDADES CUSTOMIZADAS
# =====================================================================================
class CustomPropIn(BaseModel):
    entity: str
    key: str
    label: str
    field_type: str = "text"
    options: list | None = None
    is_active: bool = True


class CustomValuesIn(BaseModel):
    values: dict


# =====================================================================================
# 8) LEAD SCORING CONFIGURÁVEL
# =====================================================================================
class ScoringRuleIn(BaseModel):
    name: str
    field: str
    operator: str = "eq"
    value: str | None = None
    points: int = 0
    is_active: bool = True


# =====================================================================================
# 9) FORECAST / METAS
# =====================================================================================
STAGE_PROB = {
    "qualification": 0.1,
    "needs_analysis": 0.25,
    "proposal": 0.5,
    "negotiation": 0.75,
    "closed_won": 1.0,
    "closed_lost": 0.0,
}


class QuotaIn(BaseModel):
    seller_id: str | None = None
    seller_name: str | None = None
    period_year: int
    period_month: int
    target_value: float | None = None  # None = não mexe no valor (ex.: setar só a meta por contagem)
    target_count: int | None = None  # meta por QUANTIDADE de contratos/mês


@router.get("/quotas")
async def list_quotas(db: AsyncSession = Depends(get_db)):
    return _rows(await db.execute(text("SELECT * FROM crm_quotas ORDER BY period_year DESC, period_month DESC")))


@router.post("/quotas", status_code=201)
async def upsert_quota(data: QuotaIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    # UPSERT de verdade por (seller_id, ano, mês). A UNIQUE é NULLS NOT DISTINCT (migration
    # crm_followups_20260626), então metas da empresa (seller_id NULL) também conflitam — não
    # duplicam mais. target_value=None NÃO zera o valor; target_count=None NÃO zera a contagem,
    # permitindo setar valor e contagem independentemente sem um clobrar o outro.
    return (
        await _one(
            db,
            """
        INSERT INTO crm_quotas (id, seller_id, seller_name, period_year, period_month, target_value, target_count, created_at, updated_at)
        VALUES (gen_random_uuid(), :seller_id, :seller_name, :period_year, :period_month, COALESCE(:target_value, 0), :target_count, now(), now())
        ON CONFLICT (seller_id, period_year, period_month)
        DO UPDATE SET
            target_value = CASE WHEN :target_value IS NULL THEN crm_quotas.target_value ELSE :target_value END,
            target_count = COALESCE(:target_count, crm_quotas.target_count),
            seller_name  = COALESCE(:seller_name, crm_quotas.seller_name),
            updated_at = now()
        RETURNING *
    """,
            data.model_dump(),
        )
        or {}
    )


@router.get("/forecast")
async def forecast(db: AsyncSession = Depends(get_db)):
    """Previsão ponderada do pipeline aberto por estágio + total ponderado, e metas do mês."""
    by_stage = _rows(
        await db.execute(
            text("""
        SELECT stage, count(*) deals, COALESCE(SUM(value),0) total_value
        FROM opportunities WHERE stage NOT IN ('closed_won','closed_lost') AND is_active = true GROUP BY stage
    """)
        )
    )
    weighted_total = 0.0
    open_total = 0.0
    for s in by_stage:
        prob = STAGE_PROB.get(s["stage"], 0.2)
        s["probability"] = prob
        s["weighted"] = round(float(s["total_value"]) * prob, 2)
        weighted_total += s["weighted"]
        open_total += float(s["total_value"])
    won = await _one(
        db,
        """
        SELECT COALESCE(SUM(value),0) v, count(*) c FROM opportunities
        WHERE stage='closed_won'
          AND date_trunc('month', COALESCE(actual_close_date, (updated_at AT TIME ZONE 'America/Manaus')::date))
              = date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date)  -- era updated_at em UTC (08/09/2026)
    """,
        {},
    )
    quotas = await _one(
        db,
        """
        SELECT COALESCE(SUM(target_value),0) t, COALESCE(MAX(target_count),0) c FROM crm_quotas
        WHERE period_year=EXTRACT(YEAR FROM (now() AT TIME ZONE 'America/Manaus'))
          AND period_month=EXTRACT(MONTH FROM (now() AT TIME ZONE 'America/Manaus'))
    """,
        {},
    )
    target = float(quotas["t"]) if quotas else 0.0
    meta_contratos = int(quotas["c"]) if quotas else 0
    won_val = float(won["v"]) if won else 0.0
    contratos_fechados = won["c"] if won else 0
    return {
        "open_total": round(open_total, 2),
        "weighted_forecast": round(weighted_total, 2),
        "won_this_month": won_val,
        "won_deals": contratos_fechados,
        "month_target": target,
        "attainment_pct": round((won_val / target * 100), 1) if target else None,
        "projected_vs_target": round(won_val + weighted_total - target, 2) if target else None,
        # meta por QUANTIDADE de contratos (KPI "≥1 contrato novo/mês")
        "contratos_fechados_mes": contratos_fechados,
        "meta_contratos_mes": meta_contratos,
        "atingimento_contratos_pct": round((contratos_fechados / meta_contratos * 100), 1) if meta_contratos else None,
        "by_stage": by_stage,
    }


@router.get("/reports/comercial/pdf")
async def relatorio_comercial_pdf(
    _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db), salvar: bool = False, teste: bool = False, drive: bool = False
):
    """Gera o Relatório Comercial em PDF (MRR, clientes, pipeline, top deals). salvar=true: registra + link."""
    from fastapi import Response

    from modules.crm.services.orchestration import relatorio_comercial_ctx
    from modules.crm.services.report_pdf import build_commercial_report_pdf

    ctx = await relatorio_comercial_ctx(db)
    pdf = build_commercial_report_pdf(ctx)
    if salvar:
        return await _salvar_pdf(db, "relatorio", "Relatório Comercial", pdf, teste=teste, drive=drive)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="relatorio_comercial.pdf"'},
    )


# ===================================================================== DOCS (recibo / OS)
class ReciboIn(BaseModel):
    pagador: str
    valor: float
    referente: str
    documento: str | None = None
    forma_pagamento: str | None = None
    numero: str | None = None


class OrdemServicoIn(BaseModel):
    cliente: str
    servico: str
    descricao: str | None = None
    documento: str | None = None
    endereco: str | None = None
    responsavel: str | None = None
    valor: float | None = None
    prazo: str | None = None
    observacoes: str | None = None
    numero: str | None = None


@router.post("/docs/recibo/pdf")
async def gerar_recibo_pdf(
    data: ReciboIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    drive: bool = False,
    teste: bool = False,
):
    """Gera um RECIBO de pagamento em PDF no padrão Conecta Mais (com selo).
    salvar=true: registra no Conecta PRO e devolve link público de download."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_recibo_pdf

    pdf = build_recibo_pdf(data.model_dump())
    if salvar:
        return await _salvar_pdf(db, "recibo", f"Recibo {data.numero or ''} - {data.pagador}", pdf, teste=teste, drive=drive)
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="recibo.pdf"'}
    )


@router.post("/docs/ordem-servico/pdf")
async def gerar_os_pdf(
    data: OrdemServicoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    drive: bool = False,
    teste: bool = False,
):
    """Gera uma ORDEM DE SERVIÇO em PDF (com selo). salvar=true: registra + link de download."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_ordem_servico_pdf

    pdf = build_ordem_servico_pdf(data.model_dump())
    if salvar:
        return await _salvar_pdf(db, "ordem_servico", f"OS {data.numero or ''} - {data.cliente}", pdf, teste=teste, drive=drive)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="ordem_servico.pdf"'},
    )


class AditivoIn(BaseModel):
    contrato_numero: str
    cliente: str | None = None
    documento: str | None = None
    tipo: str = "outro"
    objeto: str | None = None
    novo_valor: float | None = None
    nova_vigencia_fim: str | None = None
    justificativa: str | None = None
    numero: str | None = None


class AtestadoIn(BaseModel):
    emitente: str
    emitente_documento: str | None = None
    emitente_responsavel: str | None = None
    emitente_cargo: str | None = None
    servico: str
    periodo: str | None = None
    valor: float | None = None
    cidade: str | None = None
    observacoes: str | None = None
    numero: str | None = None


@router.post("/docs/aditivo/pdf")
async def gerar_aditivo_pdf(
    data: AditivoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    drive: bool = False,
    teste: bool = False,
):
    """Gera um TERMO ADITIVO de contrato em PDF (com selo). Enriquece pelo contrato. salvar=true: registra + link."""
    from fastapi import Response

    payload = data.model_dump()
    if not payload.get("cliente") and payload.get("contrato_numero"):
        row = await _one(
            db,
            """SELECT cl.name client_name, cl.document_number doc FROM contracts c
                                LEFT JOIN clients cl ON cl.id=c.client_id WHERE c.contract_number=:k""",
            {"k": payload["contrato_numero"]},
        )
        if row:
            payload["cliente"] = row.get("client_name")
            payload["documento"] = payload.get("documento") or row.get("doc")
    from modules.crm.services.doc_pdf import build_aditivo_pdf

    pdf = build_aditivo_pdf(payload)
    if salvar:
        return await _salvar_pdf(
            db,
            "aditivo",
            f"Aditivo {data.numero or ''} - {data.contrato_numero}",
            pdf,
            ref_tipo="contract",
            ref_id=data.contrato_numero,
            teste=teste,
            drive=drive,
        )
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="aditivo.pdf"'}
    )


@router.post("/docs/atestado/pdf")
async def gerar_atestado_pdf(
    data: AtestadoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    drive: bool = False,
    teste: bool = False,
):
    """Gera um ATESTADO DE CAPACIDADE TÉCNICA em PDF (com selo). salvar=true: registra + link."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_atestado_pdf

    pdf = build_atestado_pdf(data.model_dump())
    if salvar:
        return await _salvar_pdf(db, "atestado", f"Atestado {data.numero or ''} - {data.emitente}", pdf, teste=teste, drive=drive)
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="atestado.pdf"'}
    )


# =====================================================================================
# 10) FOLLOW-UP / WHATSAPP (José Luís) — PROMPT 7
# =====================================================================================
from modules.crm.services import followups as F  # noqa: E402
from modules.crm.services.phone import canonical_br, to_e164_br  # noqa: E402


class WhatsAppCadastroIn(BaseModel):
    cnpj_ou_id: str
    numero: str


@router.post("/whatsapp/cadastrar", status_code=201)
async def cadastrar_whatsapp(
    data: WhatsAppCadastroIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Grava/normaliza (E.164) o WhatsApp de um cliente (por CNPJ ou id) ou lead (id)."""
    e164 = to_e164_br(data.numero)
    if not e164:
        raise HTTPException(422, f"Número inválido: '{data.numero}'. Use DDD+número (ex.: 92 99123-4567).")
    alvo = data.cnpj_ou_id.strip()
    is_uuid = "-" in alvo and len(alvo) >= 32
    # tenta cliente
    if is_uuid:
        row = await _one(db, "SELECT id, name FROM clients WHERE id=:id", {"id": alvo})
    else:
        doc = "".join(c for c in alvo if c.isdigit())
        row = await _one(
            db,
            "SELECT id, name FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g')=:d LIMIT 1",
            {"d": doc},
        )
    if row:
        await db.execute(
            text("UPDATE clients SET whatsapp=:w, updated_at=now() WHERE id=:id"), {"w": e164, "id": row["id"]}
        )
        await db.commit()
        return {"ok": True, "tipo": "cliente", "id": str(row["id"]), "nome": row["name"], "whatsapp": e164}
    # senão, tenta lead por id
    if is_uuid:
        lead = await _one(db, "SELECT id, name FROM leads WHERE id=:id", {"id": alvo})
        if lead:
            await db.execute(
                text("UPDATE leads SET phone=:w, updated_at=now() WHERE id=:id"),
                {"w": canonical_br(e164), "id": lead["id"]},
            )
            await db.commit()
            return {"ok": True, "tipo": "lead", "id": str(lead["id"]), "nome": lead["name"], "whatsapp": e164}
    raise HTTPException(404, f"Cliente/lead não encontrado: '{alvo}'")


class FollowupIn(BaseModel):
    deal_id: str | None = None
    cliente: str | None = None  # id ou CNPJ
    lead_id: str | None = None
    proposal_id: str | None = None
    mensagem: str
    canal: str = "whatsapp"
    template: str | None = None
    confirmar: bool = False


@router.post("/followups", status_code=201)
async def criar_followup(data: FollowupIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Toque manual do José Luís. confirmar=false: preview (resolve número, sem enviar).
    confirmar=true: envia de verdade e registra em crm_followups (respeita opt-out/horário/anti-spam)."""
    target = await F.resolve_target(
        db, deal_id=data.deal_id, cliente=data.cliente, lead_id=data.lead_id, proposal_id=data.proposal_id
    )
    if not data.confirmar:
        return {
            "preview": True,
            "alvo": {"nome": target.get("nome"), "telefone": target.get("phone_e164"), "fonte": target.get("fonte")},
            "mensagem": data.mensagem,
            "canal": data.canal,
            "aviso": "Reenvie com confirmar=true para o José Luís disparar.",
            "sem_telefone": not target.get("phone_e164"),
        }
    return await F.send_followup(
        db,
        target=target,
        mensagem=data.mensagem,
        canal=data.canal,
        template=data.template,
        deal_id=data.deal_id,
        proposal_id=data.proposal_id,
        criado_por=getattr(user, "email", None),
    )


@router.get("/followups/pendentes")
async def followups_pendentes(db: AsyncSession = Depends(get_db)):
    """Toques agendados/a fazer (deal, cliente, canal, data)."""
    return {"pendentes": await F.list_pending(db)}


@router.get("/followups/historico")
async def followups_historico(deal_id: str, db: AsyncSession = Depends(get_db)):
    """Histórico de toques + respostas de um deal."""
    return {"deal_id": deal_id, "historico": await F.history(db, deal_id)}


class RespostaIn(BaseModel):
    deal_id: str | None = None
    followup_id: str | None = None
    status: str = "respondido"
    classificacao: str | None = None  # interessado | duvida | recusou
    nota: str | None = None


@router.post("/followups/resposta", status_code=201)
async def followup_resposta(data: RespostaIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Registra manualmente o retorno do cliente (quando não veio pelo inbound automático)."""
    r = await F.register_response(
        db,
        deal_id=data.deal_id,
        followup_id=data.followup_id,
        status=data.status,
        classificacao=data.classificacao,
        nota=data.nota,
    )
    if not r:
        raise HTTPException(404, "Nenhum follow-up enviado encontrado para esse deal.")
    return r


class OptoutIn(BaseModel):
    numero: str
    motivo: str | None = None


@router.post("/followups/optout", status_code=201)
async def followup_optout(data: OptoutIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Marca um número como opt-out (não receber follow-ups)."""
    c = canonical_br(data.numero)
    if not c:
        raise HTTPException(422, "Número inválido.")
    await F.add_optout(db, c, data.motivo)
    return {"ok": True, "phone": c, "opt_out": True}


# =====================================================================================
# 11) ORQUESTRAÇÃO José Luís ↔ Jordan (painel de negociações)
# =====================================================================================
from modules.crm.services import orchestration as O  # noqa: E402


@router.get("/negociacoes")
async def listar_negociacoes(db: AsyncSession = Depends(get_db)):
    """Painel das negociações em aberto: cliente, proposta, quem conduz, última resposta."""
    return {"negociacoes": await O.painel_negociacoes(db)}


@router.get("/negociacoes/pendentes")
async def negociacoes_pendentes(db: AsyncSession = Depends(get_db)):
    """Propostas enviadas SEM resposta do cliente (com dias parados)."""
    return {"pendentes": await O.pendentes_sem_resposta(db)}


class ResponsavelIn(BaseModel):
    cliente: str
    responsavel: str  # 'jordan' (assumir/pausa) | 'jose_luis' (devolver/reativa)


@router.post("/negociacoes/responsavel", status_code=201)
async def definir_responsavel(
    data: ResponsavelIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Define quem conduz a negociação. 'jordan' pausa o acompanhamento do José Luís; 'jose_luis' reativa."""
    if data.responsavel not in ("jordan", "jose_luis", "fechado"):
        raise HTTPException(422, "responsavel deve ser 'jordan', 'jose_luis' ou 'fechado'")
    r = await O.set_responsavel(db, data.cliente, data.responsavel)
    if not r.get("ok"):
        raise HTTPException(404, r.get("motivo", "negociação não encontrada"))
    return r


@router.get("/resumo-executivo")
async def resumo_executivo_endpoint(db: AsyncSession = Depends(get_db)):
    """Retrato da casa: pipeline + propostas + leads + contratos/MRR + pendências, num lugar só."""
    return await O.resumo_executivo(db)


# =====================================================================================
# 12) FASE 1 — Analytics comercial / Financeiro / What-if / Lote
# =====================================================================================
@router.get("/relatorio-comercial")
async def relatorio_comercial_endpoint(db: AsyncSession = Depends(get_db)):
    """Raio-x de vendas: win/loss, conversão do funil, motivos de perda, ROI por canal, ranking MRR, ciclo médio."""
    return await O.relatorio_comercial(db)


@router.get("/financeiro")
async def financeiro_endpoint(db: AsyncSession = Depends(get_db)):
    """Retrato financeiro: MRR, recebíveis, inadimplência, caixa do mês, faturamento NFS-e."""
    return await O.resumo_financeiro(db)


class SimularIn2(BaseModel):
    deals: list[str] | None = None
    estagio: str | None = "negotiation"


@router.post("/simular-fechamento")
async def simular_fechamento_endpoint(
    data: SimularIn2, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """What-if: se fechar estes deals (ou todos de um estágio), como fica ganho/meta."""
    return await O.simular_fechamento(db, deals=data.deals, estagio=data.estagio)


class LoteIn(BaseModel):
    mensagem: str | None = None
    confirmar: bool = False


@router.post("/followups/lote", status_code=201)
async def followup_lote_endpoint(data: LoteIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Toque em lote em todos os clientes com proposta pendente. confirmar=false = preview."""
    return await O.followup_em_lote(db, mensagem=data.mensagem, confirmar=data.confirmar)


# =====================================================================================
# 13) FASE 2 — Assistente de Visita Técnica & Comercial + Reuniões
# =====================================================================================
from modules.crm.services import visit_reports as V  # noqa: E402


class VisitaIn(BaseModel):
    cliente_nome: str
    panorama: str | None = None
    data_visita: str | None = None


@router.post("/visitas", status_code=201)
async def criar_visita(data: VisitaIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Inicia um relatório de visita técnica/comercial (rascunho)."""
    return await V.criar_relatorio(
        db,
        cliente_nome=data.cliente_nome,
        panorama=data.panorama,
        data_visita=data.data_visita,
        criado_por=getattr(user, "email", None),
    )


class AchadosIn(BaseModel):
    ref: str
    achados: list  # [{tipo, descricao}] ou ["nota livre"]


@router.post("/visitas/achados", status_code=201)
async def visita_achados(data: AchadosIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Anexa achados (análises de foto/áudio/vídeo ou notas) ao relatório."""
    return await V.adicionar_achados(db, data.ref, data.achados)


class MontarIn(BaseModel):
    ref: str
    situacao_atual: str | None = None
    diagnostico_tecnico: str | None = None
    oportunidade_comercial: str | None = None
    proximos_passos: str | None = None
    conteudo_md: str | None = None


@router.post("/visitas/montar", status_code=201)
async def visita_montar(data: MontarIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Grava o relatório sintetizado (o LLM redige; aqui persiste)."""
    return await V.montar_relatorio(
        db,
        data.ref,
        situacao_atual=data.situacao_atual,
        diagnostico_tecnico=data.diagnostico_tecnico,
        oportunidade_comercial=data.oportunidade_comercial,
        proximos_passos=data.proximos_passos,
        conteudo_md=data.conteudo_md,
    )


@router.get("/visitas")
async def listar_visitas(db: AsyncSession = Depends(get_db)):
    """Lista os relatórios de visita."""
    return {"visitas": await V.listar_relatorios(db)}


@router.get("/visitas/detalhe")
async def visita_detalhe(ref: str, db: AsyncSession = Depends(get_db)):
    """Detalhe de um relatório de visita (por id ou nome do cliente)."""
    r = await V.get_relatorio(db, ref)
    if not r:
        raise HTTPException(404, "relatório não encontrado")
    return r


class VisitaPdfIn(BaseModel):
    ref: str
    salvar: bool = True
    teste: bool = False
    drive: bool = False


@router.post("/visitas/pdf", status_code=201)
async def visita_pdf(data: VisitaPdfIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Gera o PDF do relatório de visita (com selo) e registra (download_url)."""
    from fastapi import Response

    from modules.crm.services.doc_pdf import build_visit_report_pdf

    pd = await V.pdf_data(db, data.ref)
    if not pd:
        raise HTTPException(404, "relatório não encontrado")
    pdf = build_visit_report_pdf(pd)
    if data.salvar:
        await V.finalizar(db, data.ref)
        return await _salvar_pdf(
            db, "relatorio_visita", f"Relatório de Visita - {pd.get('cliente_nome')}", pdf, teste=data.teste, drive=data.drive
        )
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="visita.pdf"'}
    )


class RegLeadVisitaIn(BaseModel):
    ref: str
    telefone: str | None = None
    cnpj: str | None = None
    valor_estimado: float | None = None


@router.post("/visitas/registrar-lead", status_code=201)
async def visita_registrar_lead(
    data: RegLeadVisitaIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Cria/atualiza lead + oportunidade a partir da visita."""
    return await V.registrar_lead_da_visita(
        db, data.ref, telefone=data.telefone, cnpj=data.cnpj, valor_estimado=data.valor_estimado
    )


# ── Reuniões ──
class ReuniaoIn(BaseModel):
    titulo: str
    quando_iso: str
    cliente_nome: str | None = None
    local: str | None = None
    tipo: str = "reuniao"
    lead_id: str | None = None
    deal_id: str | None = None
    visit_report_id: str | None = None
    notes: str | None = None


@router.post("/reunioes", status_code=201)
async def criar_reuniao(data: ReuniaoIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Sugere uma reunião (status 'sugerido' — Jordan confirma)."""
    from datetime import datetime, timedelta, timezone

    try:
        quando = datetime.fromisoformat(data.quando_iso.replace("Z", ""))
        if quando.tzinfo is None:
            quando = quando.replace(tzinfo=timezone(timedelta(hours=-4)))
    except Exception:
        raise HTTPException(422, "quando_iso inválido (use YYYY-MM-DDTHH:MM)")
    return await V.sugerir_reuniao(
        db,
        titulo=data.titulo,
        quando=quando,
        cliente_nome=data.cliente_nome,
        local=data.local,
        tipo=data.tipo,
        lead_id=data.lead_id,
        deal_id=data.deal_id,
        visit_report_id=data.visit_report_id,
        criado_por=getattr(user, "email", None),
        notes=data.notes,
    )


class MeetingActionIn(BaseModel):
    meeting_id: str


@router.post("/reunioes/confirmar", status_code=201)
async def confirmar_reuniao_ep(
    data: MeetingActionIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    return await V.confirmar_reuniao(db, data.meeting_id)


@router.post("/reunioes/cancelar", status_code=201)
async def cancelar_reuniao_ep(
    data: MeetingActionIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    return await V.cancelar_reuniao(db, data.meeting_id)


@router.get("/reunioes")
async def listar_reunioes_ep(db: AsyncSession = Depends(get_db), futuras: bool = True):
    """Lista as reuniões (futuras por padrão)."""
    return {"reunioes": await V.listar_reunioes(db, futuras=futuras)}


# =====================================================================================
# 14) FASE 3 — Cross-sell / Radar de frios / Reativação
# =====================================================================================
@router.get("/cross-sell")
async def cross_sell_endpoint(cliente: str, db: AsyncSession = Depends(get_db)):
    """Sugere serviço complementar que falta a um cliente (a partir dos contratos reais)."""
    return await O.sugerir_cross_sell(db, cliente)


@router.get("/leads-frios")
async def leads_frios_endpoint(db: AsyncSession = Depends(get_db), dias: int = 14):
    """Leads que esfriaram (sem interação há >= N dias, ainda abertos)."""
    return {"frios": await O.leads_frios(db, dias=dias)}


class ReativarIn(BaseModel):
    ref: str
    mensagem: str | None = None
    confirmar: bool = True


@router.post("/reativar-lead", status_code=201)
async def reativar_lead_endpoint(
    data: ReativarIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)
):
    """Reengaja um lead frio por WhatsApp (envio real). confirmar=false = preview."""
    return await O.reativar_lead(db, data.ref, mensagem=data.mensagem, confirmar=data.confirmar)


# =====================================================================================
# 15) FASE 4 — NPS pós-venda
# =====================================================================================
class NpsIn(BaseModel):
    ref: str
    confirmar: bool = False


@router.post("/nps/enviar", status_code=201)
async def nps_enviar(data: NpsIn, _=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Envia pesquisa NPS (0-10) a um cliente por WhatsApp. confirmar=false = preview."""
    return await O.enviar_nps(db, data.ref, confirmar=data.confirmar)


@router.get("/nps")
async def nps_resumo(db: AsyncSession = Depends(get_db)):
    """Resumo do NPS: respostas, média, promotores/neutros/detratores e o NPS."""
    return await O.resumo_nps(db)


# =====================================================================================
# 16) FECHAMENTO DO CICLO — heartbeat / métricas / ficha viva
# =====================================================================================
@router.get("/ciclo/diagnostico")
async def ciclo_diagnostico(db: AsyncSession = Depends(get_db)):
    """Saúde do ciclo Cowork↔Conecta PRO↔WhatsApp (WhatsApp online, agente, webhook, cadência)."""
    return await O.diagnostico_ciclo(db)


@router.get("/ciclo/metricas")
async def ciclo_metricas(db: AsyncSession = Depends(get_db)):
    """Funil/desempenho do José Luís: leads captados, follow-ups, taxa de resposta, visitas, NPS."""
    return await O.metricas_jose_luis(db)


@router.get("/funil")
async def funil(db: AsyncSession = Depends(get_db)):
    """Funil UNIFICADO (primeiro contato → fechamento): leads de conversa + deals, por etapa,
    com o gargalo e quem está parado há mais tempo (calculado dos dados existentes, sem migration)."""
    return await O.funil_comercial(db)


class NotaIn(BaseModel):
    ref: str
    nota: str


@router.post("/clientes/anotar", status_code=201)
async def anotar_cliente_ep(data: NotaIn, user=Depends(get_current_active_user), db: AsyncSession = Depends(get_db)):
    """Adiciona uma anotação à ficha viva do cliente (compartilhada com o José Luís)."""
    return await O.anotar_cliente(db, data.ref, data.nota, autor=getattr(user, "email", None))


@router.get("/clientes/ficha")
async def ficha_cliente_ep(ref: str, db: AsyncSession = Depends(get_db)):
    """Ficha viva do cliente: dados + anotações + último status de negociação."""
    return await O.ficha_cliente(db, ref)


# ==================== APRESENTAÇÕES (padrão Conecta PRO — slides + PDF) ====================


class ApresentacaoIn(BaseModel):
    """Estrutura de uma apresentação no padrão Conecta PRO (o cowork monta isto)."""

    titulo: str
    subtitulo: str | None = None
    cliente: str | None = None
    local: str | None = None
    data: str | None = None
    slides: list[dict[str, Any]] = []


@router.post("/apresentacoes/gerar")
async def gerar_apresentacao(
    data: ApresentacaoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    formato: str = "pptx",
    salvar: bool = False,
    drive: bool = False,
    teste: bool = False,
):
    """Gera uma APRESENTAÇÃO no padrão Conecta PRO (mesma identidade dos documentos).

    formato: 'pptx' (editável), 'pdf' (para envio). salvar=true (só pdf): devolve link
    público de download clicável (para o Cowork/WhatsApp)."""
    from fastapi import Response

    from modules.crm.services.presentation_builder import build_pptx, pptx_to_pdf

    dados = data.model_dump()
    fmt = (formato or "pptx").lower()
    pptx = build_pptx(dados)
    # ⚠️ O nome vai para o cabeçalho HTTP, que é LATIN-1: travessão, acento ou emoji no
    # título estouravam UnicodeEncodeError e derrubavam a geração inteira. Medido em
    # 27/08/2026 com o título "Oráculo — proposta técnica". Aqui o slug fica ASCII;
    # o TÍTULO dentro do documento continua intacto, com acento e tudo.
    import unicodedata as _ud  # noqa: PLC0415

    _bruto = (data.titulo or "apresentacao").lower().replace(" ", "_")
    _sem_acento = "".join(c for c in _ud.normalize("NFKD", _bruto)
                          if not _ud.combining(c))
    slug = "".join(c if (c.isalnum() or c == "_") else "_"
                   for c in _sem_acento).strip("_")[:40] or "apresentacao"

    if fmt == "pdf":
        pdf = pptx_to_pdf(pptx)
        if salvar:
            return await _salvar_pdf(db, "apresentacao", data.titulo, pdf, teste=teste, drive=drive)
        return Response(
            content=pdf, media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{slug}.pdf"'},
        )
    return Response(
        content=pptx,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{slug}.pptx"'},
    )


# ==================== ORÇAMENTO / PROPOSTA DE PAGAMENTO ÚNICO (material/serviço) ====================


class ItemOrcamentoIn(BaseModel):
    descricao: str
    valor_unit: float
    qtd: float = 1
    unidade: str = "un"
    tipo: str = "material"  # material | servico


class OrcamentoIn(BaseModel):
    cliente: str
    itens: list[ItemOrcamentoIn]
    documento: str | None = None          # CNPJ/CPF do cliente
    cidade: str | None = None
    numero: str | None = None
    titulo: str | None = None
    objeto: str | None = None
    desconto_avista_pct: float | None = None
    parcelas: int | None = None
    entrada: float | None = None
    condicoes: dict[str, Any] | None = None
    observacao: str | None = None


@router.post("/docs/orcamento/pdf")
async def gerar_orcamento_pdf(
    data: OrcamentoIn,
    _=Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    salvar: bool = False,
    drive: bool = False,
    teste: bool = False,
):
    """Gera um ORÇAMENTO / proposta de PAGAMENTO ÚNICO (material, serviço ou ambos) no padrão-ouro.
    Suporta à vista (com desconto) e/ou parcelado. salvar=true: registra + link público de download."""
    import time as _time

    from fastapi import Response

    from modules.crm.services.doc_pdf import build_orcamento_pdf

    payload = data.model_dump()
    if not payload.get("numero"):
        payload["numero"] = f"ORC-2026-{int(_time.time()) % 100000:05d}"
    pdf = build_orcamento_pdf(payload)
    if salvar:
        return await _salvar_pdf(db, "orcamento", f"Orçamento {payload['numero']} - {data.cliente}", pdf, teste=teste, drive=drive)
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="orcamento_{payload["numero"]}.pdf"'},
    )
