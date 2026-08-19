"""GEDEON — completude REAL dos kits, lendo a estrutura do Google Drive.

Substitui o percentual fake do GED antigo (tabela ged_document_kits, nunca populada)
pela verdade: lê as 4 subpastas de cada condomínio no Drive, classifica os arquivos
contra um checklist do que o kit DEVE conter e calcula o % de montagem.
"""

from __future__ import annotations

import unicodedata

from sqlalchemy import text

_FOLDER_MIME = "application/vnd.google-apps.folder"

# subpastas (mesma convenção do kit_layout.SUBPASTAS)
SUB_PESSOAL = "1. Folha e Pessoal"
SUB_VALE = "2. Vale Transporte e Alimentação"
SUB_IMPOSTOS = "3. Impostos e Certidões"
SUB_FATURAMENTO = "4. Faturamento"

# Checklist do kit: cada bloco vale 1 ponto (CND tem 5 itens → crédito proporcional).
# match = lista de termos (sem acento, minúsculo); o arquivo conta se contém QUALQUER um.
CHECKLIST = [
    {"key": "folha", "label": "Folha de Pagamento", "sub": SUB_PESSOAL, "match": ["folha de pagamento"], "esperado": 1},
    {
        "key": "contracheque",
        "label": "Contracheques",
        "sub": SUB_PESSOAL,
        "match": ["contracheque", "holerite"],
        "esperado": 1,
    },
    {
        "key": "salario",
        "label": "Comprovantes de salário",
        "sub": SUB_PESSOAL,
        "match": ["comprovante de pagamento de sal", "comprovante de sal", "comprovante salario"],
        "esperado": 1,
    },
    {
        "key": "ponto",
        "label": "Ponto assinado",
        "sub": SUB_PESSOAL,
        "match": ["ponto assinada", "ponto assinado", "folha de ponto", "folhas de ponto"],
        "esperado": 1,
    },
    {
        "key": "vavt",
        "label": "Vale Transporte / Alimentação",
        "sub": SUB_VALE,
        "match": [],
        "esperado": 1,
    },  # qualquer arquivo na subpasta conta
    {
        "key": "guias",
        "label": "Guias (FGTS / DCTFWeb / INSS)",
        "sub": SUB_IMPOSTOS,
        "match": ["guia", "dctfweb", "gfd", "relatorio fgts", "fgts"],
        "esperado": 1,
    },
    {
        "key": "inss",
        "label": "Comprovante INSS",
        "sub": SUB_IMPOSTOS,
        # Este bloco é o COMPROVANTE de recolhimento, não a certidão. "inss" sozinho
        # casaria também "CND INSS (RFB).pdf" e daria crédito de pagamento a quem só tem
        # certidão — cobertura inventada, e das piores, porque é sobre tributo. Os termos
        # abaixo cobrem o nome real que o montador gera ("INSS Patronal 07/2026.pdf") sem
        # pegar certidão.
        "match": ["inss patronal", "comprovante inss", "comprovante de pagamento inss", "guia inss", "darf inss"],
        "esperado": 1,
    },
    {
        "key": "cnd",
        "label": "Certidões (CNDs)",
        "sub": SUB_IMPOSTOS,
        "match": ["cnd", "crf", "certidao"],
        "esperado": 5,
    },
    {
        "key": "nfse",
        "label": "Nota Fiscal (NFS-e)",
        "sub": SUB_FATURAMENTO,
        "match": ["nota fiscal", "nfs", "danfse"],
        "esperado": 1,
    },
    {"key": "boleto", "label": "Boleto", "sub": SUB_FATURAMENTO, "match": ["boleto"], "esperado": 1},
]
TOTAL_BLOCOS = len(CHECKLIST)


def _norm(s: str) -> str:
    """Minúscula, sem acento, e com separador virando espaço.

    O underscore não é detalhe: o montador gera "Folhas_de_Ponto.pdf" e o checklist procura
    "folha de ponto". Sem normalizar, o bloco de ponto ficava 0/1 com o arquivo na pasta —
    pendência inventada, que some quando alguém renomeia por acaso.
    """
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().replace("_", " ").replace("-", " ").strip()


def _status_de_pct(pct: int) -> str:
    if pct >= 100:
        return "completo"
    if pct > 0:
        return "em_montagem"
    return "pendente"


def _avaliar(arquivos_por_sub: dict[str, list[dict]], blocos: set | None = None) -> dict:
    """Recebe {subpasta: [ {name, link} ]} e devolve checklist avaliado + pct.

    `blocos` = o que ESTE contrato deve ter. None = o checklist inteiro (comportamento
    antigo). Bloco fora do contrato não entra no numerador nem no denominador: some da
    conta em vez de contar como pendência eterna.
    """
    considerar = [c for c in CHECKLIST if blocos is None or c["key"] in blocos]
    itens = []
    score = 0.0
    for c in considerar:
        files = arquivos_por_sub.get(c["sub"], [])
        if c["match"]:
            achados = [f for f in files if any(t in _norm(f["name"]) for t in c["match"])]
        else:  # bloco "qualquer arquivo na subpasta" (VA/VT)
            achados = list(files)
        cnt = len(achados)
        esp = c["esperado"]
        credito = min(cnt, esp) / esp
        score += credito
        itens.append(
            {
                "key": c["key"],
                "label": c["label"],
                "subpasta": c["sub"],
                "presente": cnt > 0,
                "encontrados": cnt,
                "esperado": esp,
                "arquivos": [a["name"] for a in achados],
            }
        )
    total = len(considerar) or TOTAL_BLOCOS
    pct = round(score / total * 100)
    return {"pct": pct, "status": _status_de_pct(pct), "itens": itens}


def _ler_kit(svc, cond: str, competencia: str, blocos: set | None = None) -> dict:
    from modules.gedeon.services.kit_layout import SUBPASTAS, garantir_pasta_kit

    def _list(parent_id: str) -> list[dict]:
        if not parent_id:
            return []
        return (
            svc.files()
            .list(
                q=f"'{parent_id}' in parents and trashed=false",
                fields="files(id,name,mimeType,webViewLink)",
                pageSize=300,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )

    base = garantir_pasta_kit(cond, competencia)
    link, arquivos_por_sub, subpastas, total = None, {}, [], 0
    if base:
        try:
            meta = svc.files().get(fileId=base, fields="webViewLink", supportsAllDrives=True).execute()
            link = meta.get("webViewLink")
        except Exception:
            pass
        folders = {f["name"]: f["id"] for f in _list(base) if f["mimeType"] == _FOLDER_MIME}
        for sp in SUBPASTAS:
            files = [
                {"id": x["id"], "name": x["name"], "link": x.get("webViewLink")}
                for x in _list(folders.get(sp, ""))
                if x["mimeType"] != _FOLDER_MIME
            ]
            arquivos_por_sub[sp] = files
            subpastas.append({"nome": sp, "docs": len(files), "arquivos": files})
            total += len(files)

    aval = _avaliar(arquivos_por_sub, blocos)
    return {
        "condominio": cond,
        "total": total,
        "drive_link": link,
        "completion_percentage": aval["pct"],
        "status": aval["status"],
        "checklist": aval["itens"],
        "subpastas": subpastas,
    }


def condominios_do_workspace(svc=None) -> list[str]:
    """Lista os condomínios REAIS direto das pastas do workspace do GEDEON (escala automática:
    inclui os que não estão nos 7 padrão). Exclui pastas meta (_AUDITORIA, _VA_VT, Folhas de Ponto).
    Fallback p/ CONDOMINIOS_PADRAO se o Drive falhar."""
    from modules.gedeon.services.kit_layout import ROOT_WORKSPACE_ID
    from modules.gedeon.services.kit_orchestrator import CONDOMINIOS_PADRAO

    if svc is None:
        from modules.gdrive.services.gdrive_service import gdrive_service

        if not gdrive_service._service:
            gdrive_service.check_status()
        svc = gdrive_service._service
    if not svc:
        return list(CONDOMINIOS_PADRAO)
    try:
        folders = (
            svc.files()
            .list(
                q=f"'{ROOT_WORKSPACE_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                fields="files(name)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )
    except Exception:
        return list(CONDOMINIOS_PADRAO)
    from modules.gedeon.services.kit_layout import nome_parece_arquivo

    _meta = {"folhas de ponto", "documentos temporários", "documentos temporarios"}
    nomes = sorted(
        {
            f["name"]
            for f in folders
            if not f["name"].startswith("_")
            and f["name"].strip().lower() not in _meta
            # pasta-lixo com nome de arquivo (incidentes 30/06 e 16/07) não é condomínio
            and not nome_parece_arquivo(f["name"])
        }
    )
    return nomes or list(CONDOMINIOS_PADRAO)


_SQL_BLOCOS_CONTRATO = text(
    """
    SELECT c.name AS cliente,
           bool_or(coalesce(ct.kit_mensal, false))                      AS tem_kit_trabalhista,
           bool_or(coalesce(ct.tipo_servico,'') = 'maodeobra')          AS tem_mao_de_obra,
           count(DISTINCT a.employee_id) FILTER (WHERE a.status = 'active') AS alocados
      FROM clients c
      JOIN contracts ct ON ct.client_id = c.id AND ct.status::text = 'active'
      LEFT JOIN posts p ON p.client_id = c.id
      LEFT JOIN allocations a ON a.post_id = p.id
     GROUP BY c.name
    """
)

#: Blocos que só fazem sentido quando existe gente trabalhando no posto.
_BLOCOS_TRABALHISTAS = {"folha", "contracheque", "salario", "ponto", "vavt", "guias", "inss"}
#: Blocos que todo contrato ativo tem, mão de obra ou não.
_BLOCOS_SEMPRE = {"cnd", "nfse", "boleto"}


def blocos_por_condominio(db) -> dict[str, set[str]]:
    """O que CADA cliente deve ter no kit, segundo o contrato dele.

    O checklist era igual para todo mundo: 10 blocos fixos. Isso cobra folha, ponto e
    comprovante de VT de quem não tem UM funcionário alocado — o GELAIN, por exemplo, é
    portaria remota emitida pela Eletrônica, com zero alocados, e era medido contra a
    mesma régua de um posto com 13 porteiros. O percentual dele nunca poderia subir, e a
    média do painel afundava por causa de uma exigência que o contrato não faz.

    Contrato sem mão de obra responde por certidões, nota e boleto. Com mão de obra,
    responde por tudo. Quem não aparecer aqui cai no checklist inteiro — na dúvida, cobra.
    """
    out: dict[str, set[str]] = {}
    for r in db.execute(_SQL_BLOCOS_CONTRATO).mappings().all():
        trabalhista = bool(r["tem_kit_trabalhista"] or r["tem_mao_de_obra"]) and int(r["alocados"] or 0) > 0
        out[_norm(r["cliente"])] = set(_BLOCOS_SEMPRE) | (set(_BLOCOS_TRABALHISTAS) if trabalhista else set())
    return out


def _blocos_de(mapa: dict, cond: str) -> set | None:
    """Casa o nome da pasta do Drive com o nome do cliente no contrato.

    A pasta chama "CONDOMINIO IDEAL FLORES DA CIDADE" ou o apelido "IDEAL FLORES"; o
    contrato tem a razão social. Casa por continência, nos dois sentidos. Sem par, devolve
    None — e None é o checklist inteiro: na dúvida, cobra tudo.
    """
    alvo = _norm(cond)
    if alvo in mapa:
        return mapa[alvo]
    for nome, blocos in mapa.items():
        if alvo in nome or nome in alvo:
            return blocos
    return None


def completude_kits(competencia: str, blocos_por_cond: dict | None = None) -> dict:
    """Painel de completude REAL de TODOS os condomínios do workspace (lê o Drive)."""
    from modules.gdrive.services.gdrive_service import gdrive_service
    from modules.gedeon.services import kit_cache
    from modules.gedeon.services.kit_layout import mes_kit_de_competencia

    if not gdrive_service._service:
        gdrive_service.check_status()
    svc = gdrive_service._service
    if not svc:
        raise RuntimeError("Google Drive não conectado")

    conds = condominios_do_workspace(svc)  # escala: todos os condomínios reais do workspace
    # O cache é por (cond, competência) e não conhece os blocos; com checklist por contrato
    # ele devolveria o percentual da régua antiga. Só usa o cache quando não há recorte.
    if blocos_por_cond:
        kits = [_ler_kit(svc, cond, competencia, _blocos_de(blocos_por_cond, cond)) for cond in conds]
    else:
        kits = [kit_cache.ler_kit(svc, cond, competencia) for cond in conds]
    completos = sum(1 for k in kits if k["status"] == "completo")
    media = round(sum(k["completion_percentage"] for k in kits) / len(kits)) if kits else 0
    return {
        "competencia": competencia,
        "mes_kit": mes_kit_de_competencia(competencia),
        "total_kits": len(kits),
        "kits_completos": completos,
        "kits_pendentes": len(kits) - completos,
        "media_completude": media,
        "blocos_por_kit": TOTAL_BLOCOS,
        "checklist_por_contrato": bool(blocos_por_cond),
        "kits": kits,
    }
