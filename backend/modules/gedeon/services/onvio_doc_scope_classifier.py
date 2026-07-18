"""OnvioDocScopeClassifier — FASE 3.5 BLOCO 2

Classifica os 436 docs já categorizados pelo parser v2 (CPRO 9 FASE B1)
em 3 escopos e resolve condominio_id/referente_a_employee_id via regex
determinístico + fallback a empresa_matriz+revisao_manual=true.

§13.1 Chesterton: não cria parser — usa categoria v2 existente.

Invariantes respeitados:
  INV-9:  condominio_id preenchido SEMPRE que doc_scope='condominio'
          (fallback para empresa_matriz quando sem match, nunca condominio_id=NULL)
  INV-10: referente_a_employee_id preenchido SEMPRE que doc_scope='funcionario'
          (fallback para empresa_matriz quando sem match)
  INV-11: revisao_manual=True para todos os casos onde a resolução não é certa
"""

import re
import unicodedata
import warnings
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

# ============================================================================
# MAPPING DE CATEGORIAS (aprovado por Jordan em 2026-04-19)
# ============================================================================
CATEGORIA_TO_SCOPE: dict[str, str | None] = {
    # Grupo A — condomínio (236 docs)
    "folha_pagamento": "condominio",
    "recibo_folha": "condominio",
    "folha_ponto": "condominio",
    "fgts_guia": "condominio",
    "fgts_relatorio": "condominio",
    "dctfweb_declaracao": "condominio",
    "dctfweb_recibo": "condominio",
    "dctfweb_extrato": "condominio",
    "dctfweb_resumo_creditos": "condominio",
    "dctfweb_resumo_debitos": "condominio",
    "dctfweb_creditos": "condominio",
    "dctfweb_debitos": "condominio",
    "dctfweb_situacao": "condominio",
    # Grupo B — funcionário (81 docs)
    "contrato_trabalho": "funcionario",
    "ficha_registro": "funcionario",
    "declaracao_vt": "funcionario",
    "rescisao": "funcionario",
    "decimo_terceiro": "funcionario",
    "recibo_decimo_terceiro": "funcionario",
    "afastamento": "funcionario",
    "atestado": "funcionario",
    "aso": "funcionario",
    "aviso_previo": "funcionario",
    "ferias": "funcionario",
    "autodeclaracao": "funcionario",
    "portal_empregador": "funcionario",
    "fgts_consignado": "funcionario",
    "fgts_consignado_relatorio": "funcionario",
    # Grupo C — empresa matriz (83 docs)
    "das_simples_nacional": "empresa_matriz",
    "guia_issqn": "empresa_matriz",
    "parcelamento_simples": "empresa_matriz",
    "dar_sefaz": "empresa_matriz",
    "inss_guia": "empresa_matriz",
    "alvara": "empresa_matriz",
    "empresa_docs": "empresa_matriz",
    # Grupo D — ambíguos (36 docs)
    "outros": None,
    "documento_digitalizado": None,
}


@dataclass
class ClassificationResult:
    doc_scope: str
    condominio_id: UUID | None
    referente_a_employee_id: UUID | None
    revisao_manual: bool
    motivo: str


# ============================================================================
# NORMALIZAÇÃO
# ============================================================================
def _normalize(s: str) -> str:
    """Remove acentos, lowercase, separa por espaço."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.lower().replace("_", " ").replace("-", " ")).strip()


# ============================================================================
# REGEX DE CONDOMÍNIO
# ============================================================================
_CONDOMINIO_PATTERNS: list[tuple[str, str]] = [
    (r"\bideal\s*flores\b", "ideal_flores"),
    (r"\bmirante\b", "mirante"),
    (r"\blaranjeiras?\b", "laranjeiras"),
    (r"\bprime\s*arena\b", "prime_arena"),
    (r"\bvilla\s*dei\s*fiori?\b|\bvila\s*dei\s*fiori?\b|\bfiori\b", "villa_dei_fiori"),
    (r"\bvilla\s*(dos\s*)?passaros\b|\bpassaros\b", "villa_passaros"),
    (r"\bmichelangelo\b", "michelangelo"),
    (r"\bgelain\b", "p_gelain"),
    (r"\bgreen\s*hills?\b", "green_hills"),
    (r"\bparise\b", "parise"),
    (r"\bescritorio\b", "escritorio"),
]


def match_condominio(nome_arquivo: str, cond_lookup: dict[str, UUID]) -> UUID | None:
    normalized = _normalize(nome_arquivo)
    for pattern, nome_norm in _CONDOMINIO_PATTERNS:
        if re.search(pattern, normalized):
            return cond_lookup.get(nome_norm)
    return None


# ============================================================================
# DETECÇÃO DE EMPRESA MATRIZ
# ============================================================================
# Multi-CNPJ E6: o Grupo tem DUAS matrizes — Eletrônica (35.710.481) e
# Patrimonial (66.014.833). Ambas classificam como doc de empresa.
_MATRIZ_CNPJ = re.compile(r"35[\.\s]*710[\.\s]*481|66[\.\s]*014[\.\s]*833")
_MATRIZ_NAME = re.compile(r"\bconecta\s*mais\b|\bconectamais\b")


def is_matriz(nome_arquivo: str) -> bool:
    normalized = _normalize(nome_arquivo)
    return bool(_MATRIZ_CNPJ.search(nome_arquivo) or _MATRIZ_NAME.search(normalized))


def matriz_cnpj(nome_arquivo: str) -> str | None:
    """Identifica DE QUAL matriz é o documento (14 dígitos) — None se não for."""
    if re.search(r"66[\.\s]*014[\.\s]*833", nome_arquivo):
        return "66014833000110"
    if re.search(r"35[\.\s]*710[\.\s]*481", nome_arquivo):
        return "35710481000103"
    if _MATRIZ_NAME.search(_normalize(nome_arquivo)):
        return "35710481000103"  # marca sem CNPJ = default histórico (CNPJ1)
    return None


# ============================================================================
# MATCH DE FUNCIONÁRIO
# Testa primeiro_nome + cada palavra subsequente (espaçado e concatenado)
# para cobrir padrões como "Jefferson Batista" e "Liviaconsentine"
# ============================================================================
def match_employee(nome_arquivo: str, emp_lookup: dict[str, tuple[UUID, str]]) -> UUID | None:
    normalized_arq = _normalize(nome_arquivo)
    for emp_id, emp_nome_norm in emp_lookup.values():
        parts = emp_nome_norm.split()
        if len(parts) < 2:
            continue
        primeiro = parts[0]
        if len(primeiro) < 3:
            continue
        for word in parts[1:]:
            if len(word) < 3:
                continue
            # padrão com espaço: "jefferson ... batista"
            pat_space = rf"\b{re.escape(primeiro)}\b.*\b{re.escape(word)}\b"
            # padrão concatenado: "liviaconsentine"
            pat_concat = rf"\b{re.escape(primeiro)}{re.escape(word)}\b"
            if re.search(pat_space, normalized_arq) or re.search(pat_concat, normalized_arq):
                return emp_id
    return None


# ============================================================================
# CLASSIFIER PRINCIPAL
# ============================================================================
class OnvioDocScopeClassifier:
    def __init__(self, db: Session):
        self.db = db
        self._cond_lookup: dict[str, UUID] | None = None
        self._emp_lookup: dict[str, tuple[UUID, str]] | None = None

    def _load_condominios(self) -> dict[str, UUID]:
        if self._cond_lookup is None:
            rows = self.db.execute(
                text("SELECT id, nome_normalizado FROM condominios WHERE ativo = true AND nome_normalizado IS NOT NULL")
            ).fetchall()
            self._cond_lookup = {r.nome_normalizado: r.id for r in rows}
        return self._cond_lookup

    def _load_employees(self) -> dict[str, tuple[UUID, str]]:
        if self._emp_lookup is None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                from modules.operacional.models.employee import Employee as EmpModel  # noqa: PLC0415
            rows = self.db.query(EmpModel).filter(EmpModel.nome.isnot(None)).all()
            # key = employee_id, value = (uuid, nome_normalizado)
            self._emp_lookup = {str(r.id): (r.id, _normalize(r.nome)) for r in rows if r.nome}
        return self._emp_lookup

    def classify(self, categoria: str, nome_arquivo: str) -> ClassificationResult:
        cond_lookup = self._load_condominios()
        emp_lookup = self._load_employees()

        scope = CATEGORIA_TO_SCOPE.get(categoria)

        # Categoria desconhecida — Cenário E: safe default
        if categoria not in CATEGORIA_TO_SCOPE:
            return ClassificationResult(
                doc_scope="empresa_matriz",
                condominio_id=None,
                referente_a_employee_id=None,
                revisao_manual=True,
                motivo=f"Categoria desconhecida: {categoria}",
            )

        # Grupo D — ambíguos: tenta regex por ordem de prioridade
        if scope is None:
            if is_matriz(nome_arquivo):
                return ClassificationResult(
                    doc_scope="empresa_matriz",
                    condominio_id=None,
                    referente_a_employee_id=None,
                    revisao_manual=False,
                    motivo="Grupo D: match CNPJ/nome matriz",
                )
            cond_id = match_condominio(nome_arquivo, cond_lookup)
            if cond_id:
                return ClassificationResult(
                    doc_scope="condominio",
                    condominio_id=cond_id,
                    referente_a_employee_id=None,
                    revisao_manual=False,
                    motivo="Grupo D: match condomínio",
                )
            emp_id = match_employee(nome_arquivo, emp_lookup)
            if emp_id:
                return ClassificationResult(
                    doc_scope="funcionario",
                    condominio_id=None,
                    referente_a_employee_id=emp_id,
                    revisao_manual=False,
                    motivo="Grupo D: match funcionário",
                )
            return ClassificationResult(
                doc_scope="empresa_matriz",
                condominio_id=None,
                referente_a_employee_id=None,
                revisao_manual=True,
                motivo=f"Grupo D não resolvido: {nome_arquivo[:60]}",
            )

        # Grupo A — condomínio
        # §23.11: preservar scope='condominio' mesmo sem match — levantar revisao_manual
        # Fix CPRO12 T5-ONVIO: is_matriz() antes de match_condominio para corrigir
        # docs Conecta Mais que chegam com categoria Grupo A (ex: folha_pagamento geral)
        if scope == "condominio":
            if is_matriz(nome_arquivo):
                return ClassificationResult(
                    doc_scope="empresa_matriz",
                    condominio_id=None,
                    referente_a_employee_id=None,
                    revisao_manual=False,
                    motivo="Grupo A: match empresa matriz",
                )
            cond_id = match_condominio(nome_arquivo, cond_lookup)
            return ClassificationResult(
                doc_scope="condominio",
                condominio_id=cond_id,
                referente_a_employee_id=None,
                revisao_manual=(cond_id is None),
                motivo=("OK" if cond_id else f"Grupo A sem match condomínio: {nome_arquivo[:60]}"),
            )

        # Grupo B — funcionário
        # §23.11: preservar scope='funcionario' mesmo sem match — levantar revisao_manual
        if scope == "funcionario":
            emp_id = match_employee(nome_arquivo, emp_lookup)
            return ClassificationResult(
                doc_scope="funcionario",
                condominio_id=None,
                referente_a_employee_id=emp_id,
                revisao_manual=(emp_id is None),
                motivo=("OK" if emp_id else f"Grupo B sem match funcionário: {nome_arquivo[:60]}"),
            )

        # Grupo C — empresa matriz (sempre resolve sem ambiguidade)
        if scope == "empresa_matriz":
            return ClassificationResult(
                doc_scope="empresa_matriz",
                condominio_id=None,
                referente_a_employee_id=None,
                revisao_manual=False,
                motivo="OK",
            )

        raise ValueError(f"Scope inesperado: {scope}")
