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
    """'05.2026' (competência) -> 'Junho' (mês do kit; competência+1, pago em arrears)."""
    mes, ano = competencia.split(".")
    m = int(mes) + 1
    if m > 12:
        m = 1
    return MESES_PT[m]


def _garantir_pasta(cache: dict, nome: str, parent_id: str) -> str | None:
    key = (parent_id, nome)
    if key in cache:
        return cache[key]
    fid = gdrive_service._criar_pasta(nome, parent_id)
    cache[key] = fid
    return fid


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
    cond_folder = _garantir_pasta(cache, nome_pasta_condominio(condominio), ROOT_WORKSPACE_ID)
    if not cond_folder:
        return None
    return _garantir_pasta(cache, mes_kit_de_competencia(competencia), cond_folder)


# ── Subpastas do kit (estrutura enxuta — 4 áreas) ──────────────────────────────
SUB_PESSOAL = "1. Folha e Pessoal"
SUB_VTVR = "2. Vale Transporte e Alimentação"
SUB_FISCAL = "3. Impostos e Certidões"
SUB_FATURAMENTO = "4. Faturamento"
SUBPASTAS = [SUB_PESSOAL, SUB_VTVR, SUB_FISCAL, SUB_FATURAMENTO]


def subpasta_do_arquivo(nome: str) -> str:
    """Classifica um documento do kit na sua subpasta (pela convenção do nome)."""
    n = (nome or "").lower()
    # `startswith` sozinho deixava "NFS-e 10.pdf" e "Boleto NFS-e 08/2026.pdf" caírem na
    # pasta de pessoal — nota fiscal arquivada como documento trabalhista. Medido em
    # 19/08/2026, depois que a união trouxe os PDFs do montador para o Drive.
    if n.startswith("nota fiscal") or n.startswith("boleto") or "nfs-e" in n or "nfse" in n or "danfse" in n:
        return SUB_FATURAMENTO
    if (
        "vale transporte" in n
        or "vale aliment" in n
        or "_va_vt" in n
        or n.startswith("vt ")
        or n.startswith("vr ")
        or n.startswith("va_")
        or "sinetran" in n
        or "solides" in n
        or "comprovante vt" in n
        or "comprovante va" in n
    ):
        return SUB_VTVR
    # Tributo é tributo, mesmo sem a palavra "guia" no nome. Medido em 19/08/2026 no kit do
    # Ideal Flores: "DARF IRRF 07/2026.pdf", "ISS Manaus 07/2026.pdf" e "EFD-Reinf
    # 07/2026.pdf" estavam arquivados em "1. Folha e Pessoal" — documento fiscal na pasta
    # trabalhista. O condomínio abre a pasta errada e não acha o que procura.
    if (
        "cnd" in n
        or "certid" in n
        or "dctfweb" in n
        or "dctf" in n
        or "fgts" in n
        or "inss" in n
        or "darf" in n
        or "irrf" in n
        or "issqn" in n
        or n.startswith("iss ")
        or "efd" in n
        or "reinf" in n
    ):
        return SUB_FISCAL
    # padrão: folha, contracheques, comprovante de salário, ponto assinado
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
