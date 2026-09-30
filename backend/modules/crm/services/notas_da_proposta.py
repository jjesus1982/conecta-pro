"""Da PROPOSTA para as NOTAS — uma por classe fiscal, nunca uma nota misturada.

A REGRA (prompt 2 [3], decisão do Jordan em 30/09/2026)
A proposta PODE misturar material, serviço técnico e mão de obra. A nota NUNCA pode:
cada classe sai por um CNPJ, num regime tributário diferente, com natureza de serviço
diferente. Uma proposta com material + instalação + posto de portaria para o MESMO
cliente gera TRÊS notas.

Isso já estava escrito no mapa de capacidades do ERP desde agosto. O que faltava era o
sistema EXECUTAR a regra em vez de documentá-la — e enquanto não executava, o operador
emitia na tela de nota, à mão, sem proposta e sem registro comercial. Maiápolis R$ 23.160,
Parise R$ 2.000, Gelain R$ 6.000, Green Hills R$ 500, Parque dos Franceses R$ 1.800
saíram assim.

O QUE ESTE MÓDULO FAZ E O QUE NÃO FAZ
Ele MONTA e devolve o plano. Não emite. `preview()` é a resposta a
«quantas notas, de qual empresa, com qual valor e qual natureza», e só depois de o humano
ver esse plano é que a emissão acontece — pelo caminho que já existe, com as três camadas
de trava do `nfse_nacional`.

ABORTA em vez de chutar, em três situações, e as três já morderam:
  · item sem `classe_fiscal`      → não sei por qual CNPJ sai (era o 500 do BUG-02)
  · material pela Patrimonial     → objeto social não cobre e o Anexo IV não comporta
  · tipo B/C/D sem `data_execucao` → serviço não executado não se fatura (prompt 2 [7])
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.crm.services import classe_fiscal as cf

#: Natureza do serviço sugerida por classe. `fin_codigos_servico.ctribnac` é a chave; a
#: tabela já existia com os 4 códigos em uso — não foi criada aqui (ver prompt 2 [4]).
#: `material` não tem código de SERVIÇO: material sai em nota de PRODUTO (NF-e), não NFS-e.
_NATUREZA = {
    "servico_tecnico": "140601",  # Instalação e montagem de aparelhos e equipamentos
    "mao_de_obra": "110201",  # Vigilância, segurança ou monitoramento
}

#: Que documento cada classe gera. Material NÃO é NFS-e — foi assim que 47 notas de
#: «Vigilância» saíram pela Eletrônica: tudo virava NFS-e porque só havia esse caminho.
DOCUMENTO = {"material": "NF-e", "servico_tecnico": "NFS-e", "mao_de_obra": "NFS-e"}


async def preview(db: AsyncSession, proposta_id: str) -> dict[str, Any]:
    """O plano de emissão: quantas notas, de quem, de quanto, de qual natureza.

    Nunca emite. Devolve `{ok: False, erro: ...}` quando o plano não pode ser montado —
    e a mensagem diz o que preencher, não «erro interno».
    """
    await cf.garantir_colunas(db)

    prop = (
        (
            await db.execute(
                text(
                    "SELECT p.id::text AS id, p.number, p.title, p.status, p.client_name,"
                    "       p.client_document, coalesce(p.total,0) AS total,"
                    "       p.tipo_negocio, p.data_execucao, p.executado_por"
                    "  FROM proposals p WHERE p.id = CAST(:i AS uuid)"
                ),
                {"i": str(proposta_id)},
            )
        )
        .mappings()
        .first()
    )
    if not prop:
        return {"ok": False, "erro": f"proposta {proposta_id!r} não existe."}

    itens = (
        (
            await db.execute(
                text(
                    "SELECT i.id::text AS id, i.name, i.classe_fiscal, i.empresa_id::text AS empresa_id,"
                    "       coalesce(i.total,0) AS total, coalesce(i.quantity,1) AS qtd"
                    "  FROM proposal_items i"
                    " WHERE i.proposal_id = CAST(:i AS uuid) AND coalesce(i.is_active,true)"
                    " ORDER BY i.sort_order"
                ),
                {"i": str(proposta_id)},
            )
        )
        .mappings()
        .all()
    )
    if not itens:
        return {"ok": False, "erro": f"a proposta {prop['number']} não tem itens."}

    sem_classe = [
        f"{n}. {r['name'][:44]}" for n, r in enumerate(itens, 1) if not cf.normalizar_classe(r["classe_fiscal"])
    ]
    if sem_classe:
        return {
            "ok": False,
            "erro": "não emito sem saber a classe fiscal de cada item: "
            + "; ".join(sem_classe)
            + ". Classifique como `material`, `servico_tecnico` ou `mao_de_obra` — "
            "chutar a classe é chutar o CNPJ, o regime e a natureza do serviço de "
            "uma vez só.",
        }

    # A trava da execução (prompt 2 [7]). Tipo A é recorrente e não passa por ela.
    tipo = prop["tipo_negocio"] or cf.derivar_tipo_negocio(list(itens))
    if tipo in cf.TIPOS_COM_EXECUCAO and not prop["data_execucao"]:
        return {
            "ok": False,
            "erro": f"a proposta {prop['number']} é tipo {tipo} e não tem `data_execucao`. "
            f"Serviço que não consta executado não se fatura. Registre a execução "
            f"(`registrar_execucao`) antes de emitir.",
        }

    grupos: dict[str, dict[str, Any]] = {}
    for r in itens:
        classe = cf.normalizar_classe(r["classe_fiscal"])
        empresa = cf.CLASSE_EMPRESA[classe]
        # Cinto e suspensório: o item carrega `empresa_id` e a classe também manda numa.
        # Se divergirem, é o mesmo defeito que o BUG-02 fecha na criação — mas item antigo
        # pode ter sido gravado antes da trava, e emitir é a hora de conferir de novo.
        if r["empresa_id"] and str(r["empresa_id"]) != empresa:
            return {
                "ok": False,
                "erro": f"o item «{r['name'][:40]}» é classe '{classe}' (sai pela "
                f"{cf._nome_curto(empresa)}) mas está carimbado com a "
                f"{cf._nome_curto(str(r['empresa_id']))}. Corrija antes de emitir.",
            }
        g = grupos.setdefault(
            classe,
            {
                "classe_fiscal": classe,
                "empresa_id": empresa,
                "empresa": cf._nome_curto(empresa),
                "cnpj": cf.cnpj_da_empresa(empresa),
                "documento": DOCUMENTO[classe],
                "codigo_servico": _NATUREZA.get(classe),
                # ISS só existe em NOTA DE SERVIÇO. Material paga ICMS, e o preview mostrando
                # «ISS 5%» numa NF-e ensinaria o erro em vez de evitá-lo — foi o que apareceu
                # na primeira prova do cenário 4.
                "iss_aliquota": (cf.ISS_POR_EMPRESA[empresa] if DOCUMENTO[classe] == "NFS-e" else None),
                "tributo": ("ISS" if DOCUMENTO[classe] == "NFS-e" else "ICMS"),
                "itens": [],
                "valor": 0.0,
            },
        )
        g["itens"].append({"nome": r["name"], "qtd": float(r["qtd"]), "total": float(r["total"])})
        g["valor"] += float(r["total"] or 0)

    for g in grupos.values():
        g["valor"] = round(g["valor"], 2)
        if g["tributo"] == "ICMS":
            # O CST de entrada é o que decide o de saída, e ele só existe no XML da nota
            # de COMPRA. Medido em 24/09/2026: 46% do estoque entrou com CST 60 (ST já
            # recolhida) e 35% com CST 00. Sem ler a entrada, dizer a alíquota aqui seria
            # inventar número fiscal. O preview declara a lacuna em vez de preenchê-la.
            g["aviso_icms"] = (
                "alíquota e CST de saída dependem do CST de ENTRADA de cada "
                "produto, que está no XML da nota de compra — confira antes "
                "de emitir a NF-e"
            )
        g["linha_bancaria"] = cf.linha_bancaria(g["empresa_id"])
        if g["classe_fiscal"] == "mao_de_obra":
            # Deduções de VT/VA vêm da folha do período e não estão aqui: sem elas a base
            # é o bruto. O preview DIZ isso em vez de calcular por cima de uma suposição.
            g["inss"] = {
                **cf.retencao_inss(g["valor"]),
                "aviso": "base sem deduções de VT/VA — informe-as antes de emitir",
            }

    ordem = ["material", "servico_tecnico", "mao_de_obra"]
    planos = [grupos[c] for c in ordem if c in grupos]
    return {
        "ok": True,
        "proposta": {
            "id": prop["id"],
            "numero": prop["number"],
            "titulo": prop["title"],
            "status": prop["status"],
            "cliente": prop["client_name"],
            "cliente_documento": prop["client_document"],
            "tipo_negocio": tipo,
            "total": float(prop["total"]),
        },
        "notas": planos,
        "quantidade": len(planos),
        "resumo": " + ".join(f"{p['documento']} {p['empresa']} R$ {p['valor']:,.2f}" for p in planos),
        "confirmar": (
            "Este é o PLANO, nada foi emitido. Confira tomador, valor e natureza "
            "de cada nota e chame de novo com `confirmar=true`."
        ),
    }


async def registrar_execucao(
    db: AsyncSession, proposta_id: str, *, data_execucao, executado_por: str, aceite_cliente: dict | None = None
) -> dict:
    """Substitui a ordem de serviço, que o dono decidiu não usar (prompt 2 [7]).

    `listar_ordens_servico` devolvia ZERO: o módulo de OS existe desde sempre e nunca foi
    usado. Em vez de fazer o dono adotar um módulo morto, os três campos moram na própria
    proposta e são a trava do faturamento.
    """
    await cf.garantir_colunas(db)
    import json as _json

    r = await db.execute(
        text(
            "UPDATE proposals SET data_execucao = :d, executado_por = :q,"
            "       aceite_cliente = CAST(:a AS jsonb), updated_at = now()"
            " WHERE id = CAST(:i AS uuid) RETURNING number"
        ),
        {
            "d": data_execucao,
            "q": str(executado_por)[:160],
            "a": (_json.dumps(aceite_cliente) if aceite_cliente else None),
            "i": str(proposta_id),
        },
    )
    linha = r.first()
    await db.commit()
    if not linha:
        return {"ok": False, "erro": f"proposta {proposta_id!r} não existe."}
    return {
        "ok": True,
        "proposta": linha[0],
        "data_execucao": str(data_execucao),
        "executado_por": executado_por,
        "mensagem": "Execução registrada. A proposta pode ser faturada.",
    }
