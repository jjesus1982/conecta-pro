"""Classificador CARGO → NATUREZA → CNPJ (para CONTRATAÇÃO nova).

O Grupo Conecta Mais opera com DOIS CNPJs / DUAS contas bancárias:

- **Conecta Eletrônica** (CNPJ1) → Banco **Inter** (bank_code 077).
  Mão de obra técnica/eletrônica: dev, suporte, monitoramento, CFTV, portaria remota.
- **Conecta Patrimonial** (CNPJ2) → Banco **Cora** (bank_code 403).
  Mão de obra HUMANIZADA: agente de portaria, serviços gerais, artífice, jardineiro,
  líder de portaria, vigilante, recepção, zelador, limpeza, copeira, auxiliar.

Enquanto o `contract_migrator.SERVICOS_HUMANIZADOS/ELETRONICOS` classifica por tipo de
SERVIÇO (contrato), aqui o eixo é o CARGO da pessoa que se pretende CONTRATAR — para
rotear "posso contratar N <cargo>?" ao caixa/folha do CNPJ certo.

Regra de decisão (case/acento-insensitive, sobre o nome do cargo):
1. Se bate alguma keyword ELETRÔNICA (mais específica/técnica) → Eletrônica/Inter.
2. Senão, se bate alguma keyword HUMANIZADA → Patrimonial/Cora.
3. Senão (indefinido) → **Patrimonial** (mão de obra é a maioria — comentário da
   migration E8 e da doutrina da transição).

Só leitura / decisão pura — não toca banco. UUIDs ancorados no cadastro `empresas`
(619a3df1… Eletrônica / 7d79ed12… Patrimonial), verificados em produção.
"""
from __future__ import annotations

import unicodedata

# Identidade das duas empresas (UUIDs verbatim do cadastro `empresas`, verificados no
# banco de produção 2026-07-23). Mantidos aqui como constante para o classificador ser
# uma decisão PURA (sem I/O); o caixa_service confirma os mesmos ids contra o banco.
EMPRESA_ELETRONICA_ID = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
EMPRESA_PATRIMONIAL_ID = "7d79ed12-d480-4906-b2e0-2b2c4d299bab"

META_EMPRESA = {
    "eletronica": {
        "empresa_id": EMPRESA_ELETRONICA_ID,
        "slug": "conecta_eletronica",
        "nome": "Conecta Mais Eletrônica",
        "banco": "Inter",
        "bank_code": "077",
    },
    "patrimonial": {
        "empresa_id": EMPRESA_PATRIMONIAL_ID,
        "slug": "conecta_patrimonial",
        "nome": "Conecta Mais Patrimonial",
        "banco": "Cora",
        "bank_code": "403",
    },
}


def _norm(texto: str) -> str:
    """lower + sem acento (NFKD → ascii) — para casar keyword insensível a acento/caixa."""
    s = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(s.lower().split())


# Keywords JÁ normalizadas (sem acento, minúsculas). Cobrem as duas grafias do brief.
_KW_PATRIMONIAL = [
    "agente de portaria", "porteiro", "servicos gerais", "artifice", "jardineiro",
    "lider de portaria", "vigilante", "recepcao", "zelador", "limpeza", "copeira",
    "auxiliar",
]
_KW_ELETRONICA = [
    "dev", "suporte", "tecnico", "mantenedor", "monitoramento", "cftv", "remota",
    "alarme", "controle de acesso", "seguranca eletronica",
]


def classificar_cargo_empresa(cargo: str) -> tuple[str, str]:
    """CARGO → (natureza, empresa_id).

    natureza ∈ {'patrimonial', 'eletronica'}; empresa_id = UUID da empresa/CNPJ alvo.
    Eletrônica tem precedência quando ambos batem (a keyword técnica é o sinal
    distintivo). Indefinido → patrimonial (default da mão de obra).
    """
    c = _norm(cargo)
    if any(kw in c for kw in _KW_ELETRONICA):
        return "eletronica", EMPRESA_ELETRONICA_ID
    if any(kw in c for kw in _KW_PATRIMONIAL):
        return "patrimonial", EMPRESA_PATRIMONIAL_ID
    return "patrimonial", EMPRESA_PATRIMONIAL_ID


def natureza_do_cargo(cargo: str) -> str:
    """Só a natureza ('patrimonial'|'eletronica'). Açúcar sobre o classificador."""
    return classificar_cargo_empresa(cargo)[0]


# ─────────────────────────────────────────────────────────────────────────────
# TESTE-ÂNCORA standalone (sem pytest): `python classificador_cargo.py`
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    casos_patrimonial = [
        "Agente de Portaria", "agente de portaria", "Porteiro", "Serviços Gerais",
        "servicos gerais", "Artífice", "artifice", "Jardineiro", "Líder de Portaria",
        "lider de portaria", "Vigilante", "Recepção", "Zelador", "Auxiliar de Limpeza",
        "Copeira", "cargo inexistente qualquer",  # default → patrimonial
    ]
    casos_eletronica = [
        "Dev Backend", "Suporte Técnico", "Técnico de Monitoramento",
        "tecnico de monitoramento", "Monitoramento", "Operador de CFTV", "cftv",
        "Portaria Remota", "Mantenedor de Alarme", "Controle de Acesso",
        "Segurança Eletrônica",
    ]
    for cargo in casos_patrimonial:
        nat, eid = classificar_cargo_empresa(cargo)
        assert nat == "patrimonial", f"{cargo!r} -> {nat} (esperado patrimonial)"
        assert eid == EMPRESA_PATRIMONIAL_ID, cargo
    for cargo in casos_eletronica:
        nat, eid = classificar_cargo_empresa(cargo)
        assert nat == "eletronica", f"{cargo!r} -> {nat} (esperado eletronica)"
        assert eid == EMPRESA_ELETRONICA_ID, cargo
    print(f"OK — {len(casos_patrimonial)} patrimonial + {len(casos_eletronica)} eletronica PASS")
