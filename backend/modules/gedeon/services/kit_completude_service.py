"""GEDEON — completude REAL dos kits, lendo a estrutura do Google Drive.

Substitui o percentual fake do GED antigo (tabela ged_document_kits, nunca populada)
pela verdade: lê as 4 subpastas de cada condomínio no Drive, classifica os arquivos
contra um checklist do que o kit DEVE conter e calcula o % de montagem.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from sqlalchemy import text

logger = logging.getLogger(__name__)

_FOLDER_MIME = "application/vnd.google-apps.folder"

# subpastas (mesma convenção do kit_layout.SUBPASTAS)
# 10/09/2026 — unificado com `kit_layout`: as cinco pastas do módulo GED. Os nomes das constantes
# ficam como estão porque o CHECKLIST inteiro casa por eles; o que mudou é para onde apontam.
SUB_PESSOAL = "Funcionarios"
SUB_VALE = "Beneficios"
SUB_IMPOSTOS = "Certidoes"
SUB_GUIAS = "Guias"
SUB_FATURAMENTO = "Financeiro"

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
        # "espelho de ponto" é o nome do documento no DP; o kit chama de folha de ponto. Mesmo papel.
        "match": [
            "ponto assinada",
            "ponto assinado",
            "folha de ponto",
            "folhas de ponto",
            "espelho de ponto",
            "espelho_ponto",
        ],
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
        "sub": SUB_GUIAS,
        "match": ["guia", "dctfweb", "gfd", "relatorio fgts", "fgts"],
        "esperado": 1,
    },
    {
        "key": "inss",
        "label": "Comprovante INSS",
        "sub": SUB_GUIAS,
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


#: Pastas do layout ANTIGO → bloco de hoje. Os 391 arquivos de meses já entregues moram lá; não se
#: escreve mais neles, mas some da ficha se ninguém ler.
_EQUIV_LEGADO = {
    "1. Folha e Pessoal": SUB_PESSOAL,
    "2. Vale Transporte e Alimentação": SUB_VALE,
    "3. Impostos e Certidões": SUB_IMPOSTOS,
    "4. Faturamento": SUB_FATURAMENTO,
}

#: "Julho", "Agosto"… — o nome que a pasta do kit tinha antes da unificação de 10/09/2026.
_MESES_PT_LEGADO = {
    "janeiro",
    "fevereiro",
    "março",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
}


def _mes_pt_da_entrega(competencia: str) -> str:
    """'08.2026' -> 'setembro'. O layout antigo nomeava a pasta pelo mês de ENTREGA, competência+1."""
    meses = [
        "",
        "janeiro",
        "fevereiro",
        "março",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    try:
        m = int(competencia.split(".")[0]) + 1
    except Exception:  # noqa: BLE001
        return ""
    return meses[1 if m > 12 else m]


def _ler_legado(_list, base_novo: str, cond: str, competencia: str) -> dict[str, list[dict]]:
    """Arquivos dos meses no layout ANTIGO, irmãos da pasta do kit de hoje.

    Até 10/09/2026 o GEDEON escrevia em "[Condomínio]/Setembro/1. Folha e Pessoal…" e o módulo GED
    em "[Condomínio]/2026-08 Kit Documental/Funcionarios…". Nenhum dos dois lia o outro: no kit do
    Michelangelo a ficha dizia 9 documentos e 40% de completude com 45 arquivos no Drive — e o
    Hermes, que lê por aqui, repetia o número errado com toda a confiança.

    A ESCRITA foi unificada na estrutura nova. Esta função existe para que o que já foi entregue
    continue aparecendo. Some sozinha quando não houver mais mês em português na pasta do cliente.
    """
    from modules.gdrive.services.gdrive_service import gdrive_service

    svc = gdrive_service._service
    if not svc or not base_novo:
        return {}
    try:
        pai = (
            svc.files().get(fileId=base_novo, fields="parents", supportsAllDrives=True).execute().get("parents")
            or [None]
        )[0]
    except Exception:  # noqa: BLE001 — sem o pai não há irmão a ler; segue com o que já leu
        logger.warning("kit legado de %s: não consegui subir para a pasta do condomínio", cond)
        return {}
    if not pai:
        return {}
    # SÓ o mês que corresponde a ESTA competência. O layout antigo nomeava a pasta pelo mês de
    # ENTREGA (competência + 1): "Setembro" É o kit de 08/2026. Ler todos os meses juntos foi o que
    # o Hermes reprovou em 10/09 — os mesmos arquivos apareciam em Funcionarios e em
    # "Agosto · 1. Folha e Pessoal", com o mesmo id, e o kit contava duas vezes.
    esperado = _mes_pt_da_entrega(competencia)
    out: dict[str, list[dict]] = {}
    for mes in _list(pai):
        if mes["mimeType"] != _FOLDER_MIME or mes["name"].strip().lower() != esperado:
            continue
        for sub in _list(mes["id"]):
            bloco = _EQUIV_LEGADO.get(sub["name"])
            if not bloco or sub["mimeType"] != _FOLDER_MIME:
                continue
            out.setdefault(f"{mes['name']} · {sub['name']}", []).extend(
                {"id": x["id"], "name": x["name"], "link": x.get("webViewLink")}
                for x in _list(sub["id"])
                if x["mimeType"] != _FOLDER_MIME
            )
    return out


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
            # Funcionarios tem um nível a mais (Folhas de Ponto / Contracheques / Comprovantes de
            # Pagamento / Recibos e Comprovantes de VA e VT) — sem descer, some metade do bloco.
            files = []
            for x in _list(folders.get(sp, "")):
                if x["mimeType"] == _FOLDER_MIME:
                    files += [
                        {"id": y["id"], "name": y["name"], "link": y.get("webViewLink")}
                        for y in _list(x["id"])
                        if y["mimeType"] != _FOLDER_MIME
                    ]
                else:
                    files.append({"id": x["id"], "name": x["name"], "link": x.get("webViewLink")})
            arquivos_por_sub[sp] = files
            subpastas.append({"nome": sp, "docs": len(files), "arquivos": files})
            total += len(files)

        # 10/09/2026 — ESTA CASA TEM DOIS KITS na mesma pasta do cliente, e até hoje esta leitura só
        # enxergava um. O GEDEON escreve em "[Condomínio]/Setembro/1. Folha e Pessoal…"; o módulo GED
        # escreve em "[Condomínio]/2026-08 Kit Documental/Funcionarios|Certidoes|Guias|Beneficios|
        # Financeiro". Medido no kit do Michelangelo: a ficha dizia 9 documentos e 40% de completude
        # com 45 arquivos no Drive — e o Hermes, que lê por aqui, relatava a mesma coisa errada com
        # toda a confiança do mundo.
        #
        # Enquanto a unificação da ESCRITA não acontece (decisão do dono, mexe em cinco robôs), a
        # LEITURA passa a somar os dois. Ver menos do que existe é pior do que ver duas convenções.
        for rotulo, files in _ler_legado(_list, base, cond, competencia).items():
            bloco = _EQUIV_LEGADO[rotulo.split(" · ", 1)[1]]
            arquivos_por_sub.setdefault(bloco, []).extend(files)
            subpastas.append({"nome": f"{rotulo} (mês antigo)", "docs": len(files), "arquivos": files})
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
            # 08/09: pastas de BLOCO criadas na raiz por engano ("1. Folha e Pessoal", "2. Vale…") entravam como
            # condomínio e derrubavam a média (19 "kits", 4 fantasmas a 0%)
            and not re.match(r"^\d+\.\s", f["name"].strip())
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
