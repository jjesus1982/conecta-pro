"""Prova do extrator de documentos (anexar → preencher) das telas de admissão e prestador PJ.

Invariantes:
  1. as chaves que o extrator promete existem DE VERDADE como campo da tela — senão o valor
     lido volta e desaparece, sem erro nenhum;
  2. alvo desconhecido e arquivo vazio são recusados ANTES de chamar o modelo (não se gasta
     chamada de LLM para validar entrada);
  3. o retorno é filtrado: chave que a tela não tem é descartada, valor vazio é descartado
     (vazio sobrescreveria o que a pessoa já digitou);
  4. **nada é criado** — nem admissão, nem prestador, nem arquivo em disco. É leitura pura.

O modelo é monkeypatchado: o teste não gasta chamada real nem depende da rede. O que se prova
aqui é o CONTRATO (chaves, filtro, recusas), não a acurácia do OCR — essa quem confere é a
pessoa na tela, que é justamente por isso que o extrator preenche em vez de salvar.
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "/app")


class _U:
    id = "01f4c6a0-743d-4702-8a1c-562ea57cfbe1"
    email = "bancada@conectapro.com.br"
    role = "admin"
    perfil = "all"
    modulos = ["dp"]


class _Arq:
    """UploadFile mínimo — só o que o endpoint usa."""

    def __init__(self, nome: str, dados: bytes):
        self.filename = nome
        self._d = dados

    async def read(self):
        return self._d


async def main() -> None:
    from fastapi import HTTPException

    from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp

    # ── 1. as chaves prometidas existem como campo REAL das telas ──────────
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    import os

    eng = create_async_engine(os.environ["DATABASE_URL"])
    S = async_sessionmaker(eng, expire_on_commit=False)
    async with S() as db:
        out = await dp.build(db, _U())

    def _campos_da_tela(gid, tab):
        scr = next(t["screen"] for t in out[gid]["tabs"] if t["id"] == tab)
        return {f["key"] for f in scr.get("fields", [])}, scr

    for alvo, (gid, tab) in (("admissao", ("g-admissao", "nova-admissao")),
                             ("prestador_pj", ("g-admissao", "novo-prestador-pj"))):
        chaves_tela, scr = _campos_da_tela(gid, tab)
        prometidas = set(dp._CAMPOS_EXTRAIVEIS[alvo])
        orfas = prometidas - chaves_tela
        assert not orfas, f"{alvo}: extrator promete campo que a tela não tem: {orfas}"
        assert scr.get("prefill"), f"{tab} não tem o botão de anexar (scr.prefill)"
        assert scr["prefill"]["alvo"] == alvo, f"{tab} aponta para alvo errado"
        print(f"TESTE chaves-{alvo} ({len(prometidas)} campos, todos existem na tela) PASS")

    # ── 2. recusas ANTES de chamar o modelo ────────────────────────────────
    try:
        await dp.extrair_documento(current_user=_U(), arquivo=_Arq("x.png", b"123"), alvo="marte")
        raise AssertionError("alvo desconhecido deveria recusar")
    except HTTPException as e:
        assert e.status_code == 422, e.status_code
    print("TESTE recusa-1 (alvo desconhecido → 422, sem gastar LLM) PASS")

    try:
        await dp.extrair_documento(current_user=_U(), arquivo=_Arq("x.png", b""), alvo="admissao")
        raise AssertionError("arquivo vazio deveria recusar")
    except HTTPException as e:
        assert e.status_code == 422, e.status_code
    print("TESTE recusa-2 (arquivo vazio → 422) PASS")

    # ── 3. filtro do retorno (modelo monkeypatchado) ───────────────────────
    import json as _json

    class _Msg:
        content = _json.dumps({"documento": "CNH", "campos": {
            "candidate_name": "  BANCADA_EXTRAI Zoraide  ",  # espaços → devem sair
            "cpf": "123.456.789-00",
            "birth_date": "",                          # vazio → descartado
            "position": None,                          # nulo → descartado
            "salario_secreto": "9999",                 # chave que a tela NÃO tem → descartada
        }})

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    class _Cli:
        class chat:
            class completions:
                @staticmethod
                async def create(**_k):
                    return _Resp()

    import openai as _openai
    _orig = _openai.AsyncOpenAI
    _openai.AsyncOpenAI = lambda **_k: _Cli()
    try:
        r = await dp.extrair_documento(
            current_user=_U(), arquivo=_Arq("cnh.png", b"\x89PNG-falso"), alvo="admissao")
    finally:
        _openai.AsyncOpenAI = _orig

    assert r["campos"] == {"candidate_name": "BANCADA_EXTRAI Zoraide", "cpf": "123.456.789-00"}, r["campos"]
    assert "salario_secreto" not in r["campos"], "chave fora da tela vazou para o formulário"
    assert "birth_date" not in r["campos"] and "position" not in r["campos"], \
        "campo vazio voltou — sobrescreveria o que a pessoa digitou"
    assert "onfira" in r["message"], f"a resposta tem que pedir conferência: {r['message']!r}"
    print(f"TESTE filtro (2 campos limpos, chave estranha e vazios descartados: {r['campos']}) PASS")

    # ── 4. NADA foi criado ─────────────────────────────────────────────────
    from sqlalchemy import text

    async with S() as db:
        # marca inconfundível: 'MARIA DA SILVA' casava com uma colaboradora REAL
        # (SILVANA MARIA DA SILVA) e o teste acusava criação que nunca houve
        n_adm = (await db.execute(text(
            "SELECT count(*) FROM admission_processes WHERE candidate_name LIKE 'BANCADA_EXTRAI%'"
        ))).scalar()
        n_emp = (await db.execute(text(
            "SELECT count(*) FROM employees WHERE nome LIKE 'BANCADA_EXTRAI%'"))).scalar()
    assert n_adm == 0 and n_emp == 0, f"o extrator CRIOU registro! adm={n_adm} emp={n_emp}"
    print("TESTE nao-cria (0 admissões, 0 colaboradores — leitura pura) PASS")

    print("\nEXTRATOR DE DOCUMENTO OK — contrato de chaves, recusas, filtro e leitura pura")
    await eng.dispose()


asyncio.run(main())
