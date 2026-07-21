"""Task 3 (Fase −1) — prova que o vazamento LGPD dos consultores está fechado.

- Consultor CEO (cross-módulo: folha+financeiro+jurídico) = só diretoria (jjesus+pjesus).
- Consultores de módulo = exigem a permissão do módulo (bloqueiam quem não tem, liberam quem tem).
Roda contra o servidor vivo em 127.0.0.1:8080 (dentro do container).
"""
import asyncio
import urllib.error
import urllib.request

from sqlalchemy import text

from core.auth import create_access_token
from core.database import async_session_factory

BASE = "http://127.0.0.1:8080/api/v1"


def _token(email: str) -> str:
    async def _get():
        async with async_session_factory() as db:
            return (await db.execute(text("SELECT id FROM users WHERE email=:e"), {"e": email})).scalar()
    uid = asyncio.run(_get())
    assert uid, f"usuário {email} inexistente"
    return create_access_token(str(uid))


def _status(path: str, tok: str) -> int:
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + tok})
    try:
        return urllib.request.urlopen(req, timeout=30).status
    except urllib.error.HTTPError as e:
        return e.code


def test_ceo_bloqueia_nao_diretoria():
    # egonzaga é gerente_operacional (não diretoria) → 403 no Consultor CEO
    assert _status("/gestao/consultor/panorama", _token("egonzaga@conectamais.pro")) == 403


def test_ceo_libera_jordan():
    # jjesus (diretoria) passa o gate (≠403; pode ser 200 ou erro de dado, mas não bloqueio)
    assert _status("/gestao/consultor/panorama", _token("jjesus@conectamais.pro")) != 403


def test_fiscal_bloqueia_sem_modulo():
    # egonzaga não tem module:fiscal → 403 no Consultor Fiscal
    assert _status("/fiscal/consultor/panorama", _token("egonzaga@conectamais.pro")) == 403


def test_operacional_libera_com_modulo():
    # egonzaga tem module:operacional → passa o gate do Consultor COO (≠403)
    assert _status("/operacional/consultor/panorama", _token("egonzaga@conectamais.pro")) != 403
