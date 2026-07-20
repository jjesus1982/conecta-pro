"""Regressões multi-CNPJ (E1–E8) — travam os oráculos provados manualmente.

Roda DENTRO do container (precisa de DATABASE_URL): trava a identidade fiscal
por empresa, a regra anti-reescrita do branding por competência, o roteamento
de cobrança por empresa e a regra de validade das NFS-e (substituição).

Uso: PYTHONPATH=/app python tests/multicnpj_release/test_multicnpj_regressions.py
(ou via pytest). Como as suítes *_release, é gate de produção — bate no banco
real em modo leitura; nenhum dado é alterado.
"""

import os
import re

import psycopg2

_URL = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
_ELETRONICA = "35710481000103"
_PATRIMONIAL = "66014833000110"


def test_empresa_context_por_empresa():
    """get_empresa_fiscal(slug) resolve o CNPJ certo; default = principal (CNPJ1)."""
    from modules.government_integrations.core.empresa_context import get_empresa_fiscal

    assert get_empresa_fiscal().cnpj == _ELETRONICA, "default deve ser CNPJ1"
    assert get_empresa_fiscal("conecta_patrimonial").cnpj == _PATRIMONIAL
    assert get_empresa_fiscal("conecta_eletronica").cnpj == _ELETRONICA
    try:
        get_empresa_fiscal("nao_existe")
        raise AssertionError("empresa inexistente deveria levantar LookupError")
    except LookupError:
        pass


def test_branding_anti_reescrita_por_competencia():
    """Regra F1: competência < fronteira => CNPJ1 SEMPRE; >= fronteira => empresa do slug."""
    from modules.crm.services.pdf_branding import resolve_slug_por_competencia

    # simula fronteira 2026-07 independente do env (função pura testável)
    import modules.crm.services.pdf_branding as B

    orig = os.getenv("MULTICNPJ_FRONTEIRA_COMPETENCIA")
    os.environ["MULTICNPJ_FRONTEIRA_COMPETENCIA"] = "2026-07"
    try:
        assert resolve_slug_por_competencia("conecta_patrimonial", "2026-06") == "conecta_eletronica"
        assert resolve_slug_por_competencia("conecta_patrimonial", "2026-07") == "conecta_patrimonial"
        assert resolve_slug_por_competencia("conecta_eletronica", "2026-09") == "conecta_eletronica"
        # documento da Patrimonial em competência fechada nunca vira CNPJ1->CNPJ2 retroativo
        assert B.empresa_branding("conecta_patrimonial", "2026-05")["cnpj"] == "35.710.481/0001-03"
    finally:
        if orig is None:
            os.environ.pop("MULTICNPJ_FRONTEIRA_COMPETENCIA", None)
        else:
            os.environ["MULTICNPJ_FRONTEIRA_COMPETENCIA"] = orig


def test_cobranca_roteada_por_empresa():
    """Cada cliente com contrato ativo resolve a empresa credora certa (canônico)."""
    from modules.financial.services.recurring_billing_service import _empresa_credora_do_cliente

    esperado = {
        "IDEAL FLORES": "conecta_patrimonial", "MIRANTE": "conecta_patrimonial",
        "LARANJEIRAS": "conecta_patrimonial", "PRIME ARENA": "conecta_patrimonial",
        "VILLA DOS PASSAROS": "conecta_patrimonial", "VILLA DEI FIORI": "conecta_patrimonial",
        "MICHELANGELO": "conecta_patrimonial", "GELAIN": "conecta_eletronica",
        "PARISE": "conecta_eletronica", "GREEN HILLS": "conecta_eletronica",
    }
    import psycopg2.extras

    conn = psycopg2.connect(_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, name FROM clients WHERE status='active' AND mrr > 0")
    encontrados = {}
    for c in cur.fetchall():
        slug = _empresa_credora_do_cliente(cur, c["id"])
        for chave, exp in esperado.items():
            if chave in c["name"].upper():
                encontrados[chave] = (slug, exp)
    conn.close()
    erros = {k: v for k, v in encontrados.items() if v[0] != v[1]}
    assert not erros, f"roteamento errado: {erros}"
    assert len(encontrados) >= 9, f"esperava >=9 clientes canônicos, achei {len(encontrados)}"


def test_nfse_validade_substituicao():
    """filtrar_vivas: nota referenciada em <chSubstda> é MORTA; vigente sobrevive."""
    from modules.gedeon.services.nfse_nacional_adn import filtrar_vivas

    emitidas = [
        {"nsu": 1, "chave_acesso": "AAA", "_xml": "<x><vRetCP>0</vRetCP></x>"},
        {"nsu": 2, "chave_acesso": "BBB", "_xml": "<x><chSubstda>AAA</chSubstda></x>"},
    ]
    vivas, mortas = filtrar_vivas(emitidas)
    chaves = {n["chave_acesso"] for n in vivas}
    assert "AAA" not in chaves, "nota substituída deveria estar morta"
    assert "BBB" in chaves, "nota substituta deveria estar viva"
    assert mortas == 1


def _run_all():
    testes = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    falhas = []
    for t in testes:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            falhas.append((t.__name__, e))
            print(f"FAIL {t.__name__}: {e}")
    if falhas:
        raise SystemExit(f"{len(falhas)} falha(s) multi-CNPJ")
    print(f"OK — {len(testes)}/{len(testes)} regressões multi-CNPJ")


if __name__ == "__main__":
    _run_all()
