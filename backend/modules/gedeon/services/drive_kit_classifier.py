"""
GEDEON — Classificador de arquivos do Google Drive → tipo de documento (slug).

O Onvio fornece uma `categoria` que mapeia pra um slug. Os arquivos que a equipe
monta manualmente no Drive só têm o NOME — então este classificador infere o slug
(um dos 32 tipos de kit_documental_templates) a partir do nome do arquivo.

Determinístico, por palavras-chave, ordenado por especificidade (padrões mais
específicos antes — ex.: "boleto de NFS" deve casar boleto, não nfse).
"""

from __future__ import annotations

import re
import unicodedata


def _norm(s: str) -> str:
    """minúsculas, sem acento, espaços colapsados."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("_", " ").replace("-", " ")
    s = s.replace("salaario", "salario").replace("comporvante", "comprovante")  # typos comuns
    return re.sub(r"\s+", " ", s).strip()


# (slug, escopo, [grupos de termos — TODOS os grupos devem casar (AND); dentro do grupo é OR]).
# Ordem importa: o primeiro match vence. Padrões mais específicos primeiro.
_RULES: list[tuple[str, str, list[list[str]]]] = [
    # --- por funcionário (1 por funcionário) ---
    (
        "comp_vt_va_combinado",
        "funcionario",
        [["vale alimentacao", "va"], ["vale transporte", "vt"], ["comprovante", "pagamento", "recibo"]],
    ),
    ("comp_va_solides", "funcionario", [["vale alimentacao"], ["comprovante", "pagamento"]]),
    ("comp_vt_individual", "funcionario", [["vale transporte"], ["comprovante", "pagamento"]]),
    ("comp_fgts_rescisao", "funcionario", [["fgts"], ["rescis"], ["comprovante", "pagamento"]]),
    ("comp_rescisao", "funcionario", [["rescis"], ["comprovante", "pagamento", "recibo"]]),
    ("comp_salario_individual", "funcionario", [["salario"], ["comprovante", "pagamento"]]),
    ("recibo_ferias", "funcionario", [["ferias"], ["recibo", "pagamento"]]),
    ("aviso_previo_ferias", "funcionario", [["aviso previo"]]),
    ("rescisao_contrato", "funcionario", [["rescis"], ["contrato", "termo"]]),
    ("contrato_trabalho", "funcionario", [["contrato de trabalho", "termo de contrato"]]),
    ("ficha_empregado", "funcionario", [["ficha"], ["empregado", "registro", "cadastr"]]),
    # --- por condomínio (1 por condomínio/mês) ---
    ("boleto", "condominio", [["boleto"]]),
    ("nfse", "condominio", [["nfs", "nota fiscal", "nfse"]]),
    ("aso", "condominio", [["aso"]]),
    ("folhas_ponto", "funcionario", [["folha"], ["ponto"]]),
    ("folha_pagamento", "condominio", [["folha de pagamento", "folha pagamento"]]),
    ("dctfweb_declaracao", "condominio", [["dctfweb", "dctf"], ["declaracao"]]),
    ("dctfweb_recibo", "condominio", [["dctfweb", "dctf"], ["recibo"]]),
    ("dctfweb_extrato", "condominio", [["dctfweb", "dctf"], ["extrato", "relatorio", "processamento"]]),
    ("comp_pag_fgts", "condominio", [["fgts"], ["comprovante", "pagamento"]]),
    ("relatorio_gfd_fgts", "condominio", [["gfd", "fgts"], ["relatorio"]]),
    ("gfd_fgts_mensal", "condominio", [["gfd", "fgts"]]),
    ("recibo_vt_va", "condominio", [["vale", "vt", "va"], ["recibo"]]),
    ("relatorio_pedido_va", "condominio", [["vale alimentacao", "va"], ["pedido", "relatorio"]]),
    ("contracheque", "condominio", [["contracheque"]]),
    # --- empresa matriz (CNDs etc.) ---
    ("cnd_sefaz", "empresa_matriz", [["sefaz"]]),
    ("cnd_caixa", "empresa_matriz", [["cnd", "certidao"], ["caixa", "fgts"]]),
    ("cnd_trabalhista", "empresa_matriz", [["trabalhista", "tst"]]),
    ("cnd_prefeitura", "empresa_matriz", [["prefeitura", "municipal"]]),
    ("cnd_rfb", "empresa_matriz", [["cnd", "certidao", "negativa"], ["rfb", "receita", "federal", "pgfn", "uniao"]]),
    # --- documentos do kit que ainda NÃO têm template (anotados p/ revisão) ---
    ("inss_mensal", "condominio", [["inss"]]),
]


def classify_filename(nome_arquivo: str) -> tuple[str | None, str | None, str]:
    """Retorna (slug, escopo, motivo). slug=None se não reconhecido."""
    n = _norm(nome_arquivo)
    if not n:
        return None, None, "vazio"
    for slug, escopo, grupos in _RULES:
        if all(any(termo in n for termo in grupo) for grupo in grupos):
            return slug, escopo, f"match: {slug}"
    return None, None, f"nao reconhecido: {nome_arquivo[:50]}"
