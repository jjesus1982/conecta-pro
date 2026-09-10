"""
GEDEON — Layout do kit no formato que a equipe ENTREGA hoje aos condomínios.

Estrutura (igual aos kits de referência da Innovare):
    [ROOT workspace] / [Condomínio] / [Mês do kit] / [todos os PDFs, num nível só]

Nomes de arquivo descritivos (ex.: "Comprovante de Pagamento de Salário_João.pdf").

Mapeamento de competência → mês do kit: salário/encargos são pagos em arrears, então
a folha de competência X entra no kit do mês X+1 (competência 05.2026 → kit "Junho").
"""

from __future__ import annotations

import logging
import re

from modules.gdrive.services.gdrive_service import gdrive_service

logger = logging.getLogger(__name__)

ROOT_WORKSPACE_ID = "1oigpHoCvFT-M2tm96FDvE0LvowciNLKJ"

# Nome com extensão de arquivo NUNCA é condomínio. Incidentes de 30/06 e 16/07:
# chamadas com nome de ARQUIVO no lugar do condomínio criaram pastas-lixo na raiz
# do workspace ("Comprovante de Pagamento de Salário_Fulano.pdf/Julho/...") que
# poluíam o painel de completude (24 "kits" em vez de ~12). Guard no choke point:
# toda criação de pasta de condomínio passa por garantir_pasta_kit.
_RE_NOME_DE_ARQUIVO = re.compile(r"\.(pdf|xlsx?|docx?|csv|png|jpe?g|zip|txt|xml)$", re.IGNORECASE)


def nome_parece_arquivo(nome: str) -> bool:
    """True se o "condomínio" tem cara de nome de arquivo (defesa contra args trocados)."""
    return bool(_RE_NOME_DE_ARQUIVO.search((nome or "").strip()))


MESES_PT = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}


def mes_kit_de_competencia(competencia: str) -> str:
    """'08.2026' (competência) -> '2026-08 Kit Documental'.

    10/09/2026 — UNIFICAÇÃO. Esta casa tinha DOIS kits na mesma pasta do cliente: o do GEDEON, em
    "[Condomínio]/Setembro/1. Folha e Pessoal…", e o do módulo GED, em "[Condomínio]/2026-08 Kit
    Documental/Funcionarios|Certidoes|Guias|Beneficios|Financeiro". Nenhum enxergava o outro:
    medido no kit do Michelangelo, a ficha dizia 9 documentos e 40% com 45 arquivos no Drive.

    Fica a estrutura do GED, que o Jordan desenhou contra um kit real do Villa Dei Fiori e aprovou,
    e que classifica por TIPO do documento em vez de adivinhar pelo nome do arquivo. O nome da pasta
    passa a ser a COMPETÊNCIA, não o mês de entrega: o síndico pede "o kit de agosto", e agosto é a
    competência do que está lá dentro.

    Os meses antigos (Julho, Agosto, Setembro…) continuam LIDOS — ver `_ler_legado` no
    kit_completude_service. Nenhum mês entregue desaparece; só não se escreve mais neles.
    """
    mes, ano = competencia.split(".")
    return f"{ano}-{int(mes):02d} Kit Documental"


def _garantir_pasta(cache: dict, nome: str, parent_id: str) -> str | None:
    key = (parent_id, nome)
    if key in cache:
        return cache[key]
    fid = gdrive_service._criar_pasta(nome, parent_id)
    cache[key] = fid
    return fid


def _norm_nome(s: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def item_ja_na_pasta(folder_id: str, chaves: list[str], empresa: str | None = None) -> str | None:
    """Já existe na pasta um arquivo do MESMO ITEM, com qualquer nome?

    `_arquivo_ja_existe` compara o nome exato — e foi assim que o kit ganhou duplicatas:
    a Pyetra sobe a nota original do portal como "NFS-e 7.pdf" e o montador subia a
    versão gerada como "Nota Fiscal NFS-26.pdf" ao lado (dono, 07/09/2026). Aqui o casamento
    é por palavra-chave (número da nota, tipo da certidão). `empresa` ("PATRIMONIAL" /
    "ELETRONICA"): um arquivo que cite OUTRA empresa não conta — o kit híbrido leva as
    certidões das duas. Devolve o nome do arquivo que já cobre o item, ou None.
    """
    svc = gdrive_service._service
    if not svc or not folder_id:
        return None
    try:
        r = (
            svc.files()
            .list(q=f"'{folder_id}' in parents and trashed=false", fields="files(name)", pageSize=200)
            .execute()
        )
    except Exception:  # noqa: BLE001 — sem listagem, não afirmo que existe
        return None
    chaves_n = [_norm_nome(c) for c in chaves if c]
    emp = _norm_nome(empresa) if empresa else ""
    outras = {"PATRIMONIAL", "ELETRONICA"} - ({emp} if emp else set())
    for f in r.get("files", []):
        nome = _norm_nome(f.get("name", ""))
        if not any(c in nome for c in chaves_n):
            continue
        if emp and any(o in nome for o in outras) and emp not in nome:
            continue  # é do mesmo tipo, mas da outra empresa
        return f.get("name")
    return None


def _arquivo_ja_existe(folder_id: str, nome: str) -> bool:
    svc = gdrive_service._service
    if not svc:
        return False
    safe = nome.replace("'", "\\'")
    q = f"name='{safe}' and '{folder_id}' in parents and trashed=false"
    try:
        r = svc.files().list(q=q, fields="files(id)").execute()
        return bool(r.get("files"))
    except Exception:
        return False


def nome_pasta_condominio(condominio: str) -> str:
    """Nome da pasta-raiz do condomínio no Drive: SEMPRE o do contrato.

    Existe porque os chamadores falam duas línguas. Os blocos que leem documento externo
    (boleto, NFS-e, Onvio) já resolvem o nome do pagador e passam "CONDOMINIO IDEAL FLORES
    DA CIDADE"; os que replicam em todo mundo (INSS, VA/VT) iteram CONDOMINIOS_PADRAO e
    passam "IDEAL FLORES". Como _criar_pasta casa por nome EXATO, o segundo grupo criava
    uma segunda pasta ao lado da primeira — foi assim que nasceram as 7 pastas curtas
    apagadas em 17/08/2026.

    Resolver aqui, e não em cada caller, é o que impede a terceira língua de aparecer.
    Sem correspondência, devolve o nome recebido: pasta nova de cliente novo continua
    funcionando sem ninguém editar mapa nenhum.
    """
    # 10/09/2026 — O BANCO ANTES DA HEURÍSTICA. `posts.client_id` está preenchido e correto nos 16
    # postos, e `clients.document_number` casa com `ged_clients.cnpj` em 15 deles. A adivinhação por
    # nome errava justo onde dói: "Condomínio Gelain" (posto) não resolvia para "CONDOMINIO PARQUE
    # RESIDENCIAL GELAIN" (cliente), e o robô de VT/VR criava uma pasta de cliente NOVA ao lado da
    # certa. Foi assim que nasceram as pastas curtas apagadas em 17/08 — e que voltaram.
    # A regra da casa é ler a fonte, não codificar a convenção: aqui a fonte é o join.
    try:
        from sqlalchemy import text as _sql

        from core.database.session import get_sync_db

        with get_sync_db() as _db:
            achado = _db.execute(
                _sql(
                    "SELECT g.name FROM posts p JOIN ged_clients g ON g.id = p.ged_client_id "
                    "WHERE upper(trim(p.name)) = upper(trim(:n)) AND p.ged_client_id IS NOT NULL LIMIT 1"
                ),
                {"n": condominio},
            ).scalar()
        if achado:
            return achado
    except Exception:  # noqa: BLE001 — banco fora, cai na heurística; nunca derruba o arquivamento
        logger.debug("nome_pasta_condominio: banco indisponível para %r, seguindo pela heurística", condominio)

    try:
        from modules.gedeon.services.onvio_kit_service import _condominio_do_nome

        return _condominio_do_nome(condominio) or condominio
    except Exception:  # noqa: BLE001 — resolver é conveniência; nunca derruba o arquivamento
        logger.warning("nome_pasta_condominio: nao resolvi %r, usando como veio", condominio)
        return condominio


def garantir_pasta_kit(condominio: str, competencia: str, cache: dict | None = None) -> str | None:
    """Garante [Condomínio]/[Mês do kit] e devolve o ID da pasta do mês (flat)."""
    if nome_parece_arquivo(condominio):
        logger.warning(
            "garantir_pasta_kit: %r parece nome de ARQUIVO, não condomínio — recusado (argumentos trocados no caller?)",
            condominio,
        )
        return None
    if not gdrive_service._service:
        gdrive_service.check_status()
    cache = cache if cache is not None else {}
    # 10/09/2026 — UMA autoridade para onde mora a pasta do cliente. O `google_drive_service` usava
    # `ged_clients.google_drive_folder_id` como pai e esta função usava a RAIZ fixa: o kit de
    # homologação foi escrito dentro de "_TESTE (homologação — não é cliente)" e a ficha procurava
    # na raiz, achando ZERO arquivos num kit com 85. Mesma doença das duas estruturas de pasta,
    # noutro lugar. Onde o cliente declara um pai, ele manda; quem não declara, vai para a raiz.
    nome_cli = nome_pasta_condominio(condominio)
    pai = ROOT_WORKSPACE_ID
    try:
        from sqlalchemy import text as _sql

        from core.database.session import get_sync_db

        with get_sync_db() as _db:
            declarado = _db.execute(
                _sql(
                    "SELECT google_drive_folder_id FROM ged_clients "
                    "WHERE upper(btrim(name)) = upper(btrim(:n)) AND coalesce(google_drive_folder_id,'') <> '' LIMIT 1"
                ),
                {"n": nome_cli},
            ).scalar()
        if declarado:
            pai = declarado
    except Exception:  # noqa: BLE001 — banco fora: raiz, que é o comportamento de sempre
        logger.debug("garantir_pasta_kit: banco indisponível para %r, usando a raiz", nome_cli)
    cond_folder = _garantir_pasta(cache, nome_cli, pai)
    if not cond_folder:
        return None
    return _garantir_pasta(cache, mes_kit_de_competencia(competencia), cond_folder)


# ── Subpastas do kit — as cinco do módulo GED, aprovadas pelo Jordan em 09/09/2026 ────────────
# Os nomes antigos das constantes ficam como APELIDO porque `kit_atlas_service` e os robôs os
# importam; o que mudou é para onde apontam.
SUB_PESSOAL = "Funcionarios"
SUB_VTVR = "Beneficios"
SUB_FISCAL = "Certidoes"
SUB_GUIAS = "Guias"
SUB_FATURAMENTO = "Financeiro"
SUBPASTAS = [SUB_PESSOAL, SUB_FISCAL, SUB_GUIAS, SUB_VTVR, SUB_FATURAMENTO]

#: Pastas do layout ANTIGO (4 blocos numerados) — não se escreve mais nelas, mas 391 arquivos de
#: meses já entregues moram lá e continuam sendo lidos.
SUBPASTAS_LEGADO = [
    "1. Folha e Pessoal",
    "2. Vale Transporte e Alimentação",
    "3. Impostos e Certidões",
    "4. Faturamento",
]


def subpasta_do_arquivo(nome: str) -> str:
    """Classifica um documento do kit na sua subpasta, PELO NOME do arquivo.

    ⚠️ Adivinhar pelo nome é o caminho fraco e esta função é a prova: em 19/08/2026 "DARF IRRF",
    "ISS Manaus" e "EFD-Reinf" estavam arquivados na pasta de folha, e o conserto foi acrescentar
    mais palavras à lista. Quem tem o `document_type` no banco deve usar `PASTA_DO_TIPO`
    (google_drive_service) — mapa explícito, com oráculo cobrando tipo novo. Isto aqui existe só
    para os robôs que depositam um ARQUIVO e não têm o tipo em mãos (CND, NFS-e, comprovante Inter).

    A ORDEM importa e é o que conserta dois erros do classificador antigo:
      · "Boleto Vale-Transporte SINETRAM" é benefício, não faturamento → VT/VA vem antes de boleto;
      · "CND-FGTS" é certidão, não guia → certidão vem antes de FGTS/INSS/DARF.
    """
    n = (nome or "").lower()

    # 1) benefício (VT/VA) — antes de faturamento, senão o boleto do SINETRAM vira nota fiscal
    if (
        "vale transporte" in n
        or "vale aliment" in n
        or "_va_vt" in n
        or n.startswith(("vt ", "vr ", "va_"))
        or "sinetran" in n
        or "sinetram" in n
        or "solides" in n
        or "sólides" in n
        or "comprovante vt" in n
        or "comprovante va" in n
        or "vt_vr" in n
        or "vt/vr" in n
    ):
        return SUB_VTVR

    # 2) certidão negativa — antes das guias, senão "CND-FGTS" e "CND INSS" viram guia
    if "cnd" in n or "certid" in n or "crf" in n or "cndt" in n:
        return SUB_FISCAL

    # 3) guia de recolhimento e o comprovante de pagamento dela
    if (
        "dctf" in n
        or "fgts" in n
        or "inss" in n
        or "darf" in n
        or "irrf" in n
        or "issqn" in n
        or n.startswith("iss ")
        or "efd" in n
        or "reinf" in n
        or "das " in n
        or "guia" in n
        or "gps" in n
        or "gfd" in n
    ):
        return SUB_GUIAS

    # 4) o que a Conecta Mais cobra do condomínio
    if n.startswith(("nota fiscal", "boleto")) or "nfs-e" in n or "nfse" in n or "danfse" in n:
        return SUB_FATURAMENTO

    # 5) padrão: folha, contracheque, comprovante de salário, ponto
    return SUB_PESSOAL


def pasta_kit_arquivo(condominio: str, competencia: str, nome_arquivo: str, cache: dict | None = None) -> str | None:
    """Garante [Condomínio]/[Mês]/[Subpasta do documento] e devolve o ID da subpasta."""
    cache = cache if cache is not None else {}
    base = garantir_pasta_kit(condominio, competencia, cache)
    if not base:
        return None
    return _garantir_pasta(cache, subpasta_do_arquivo(nome_arquivo), base)


_CONECTIVOS = {"da", "de", "do", "das", "dos", "e", "di", "del"}


def primeiro_e_ultimo(nome: str) -> str:
    """'MARTA DA SILVA PINHEIRO' -> 'Marta Silva' (1º nome + 1º sobrenome real, sem preposição)."""
    partes = [p for p in (nome or "").split() if p]
    if not partes:
        return "Funcionario"
    primeiro = partes[0]
    sobrenome = next((p for p in partes[1:] if p.lower() not in _CONECTIVOS), "")
    sel = [primeiro] + ([sobrenome] if sobrenome else [])
    return " ".join(p.capitalize() for p in sel)
