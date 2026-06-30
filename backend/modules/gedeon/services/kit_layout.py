"""
GEDEON — Layout do kit no formato que a equipe ENTREGA hoje aos condomínios.

Estrutura (igual aos kits de referência da Innovare):
    [ROOT workspace] / [Condomínio] / [Mês do kit] / [todos os PDFs, num nível só]

Nomes de arquivo descritivos (ex.: "Comprovante de Pagamento de Salário_João.pdf").

Mapeamento de competência → mês do kit: salário/encargos são pagos em arrears, então
a folha de competência X entra no kit do mês X+1 (competência 05.2026 → kit "Junho").
"""

from __future__ import annotations

from modules.gdrive.services.gdrive_service import gdrive_service

ROOT_WORKSPACE_ID = "1oigpHoCvFT-M2tm96FDvE0LvowciNLKJ"

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


def garantir_pasta_kit(condominio: str, competencia: str, cache: dict | None = None) -> str | None:
    """Garante [Condomínio]/[Mês do kit] e devolve o ID da pasta do mês (flat)."""
    if not gdrive_service._service:
        gdrive_service.check_status()
    cache = cache if cache is not None else {}
    cond_folder = _garantir_pasta(cache, condominio, ROOT_WORKSPACE_ID)
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
    if n.startswith("nota fiscal") or n.startswith("boleto"):
        return SUB_FATURAMENTO
    if (
        "vale transporte" in n
        or "vale aliment" in n
        or "_va_vt" in n
        or n.startswith("vt ")
        or n.startswith("vr ")
        or n.startswith("va_")
        or "sinetran" in n
    ):
        return SUB_VTVR
    if "cnd" in n or "certid" in n or "dctfweb" in n or "fgts" in n or "inss" in n:
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
