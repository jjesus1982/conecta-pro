#!/usr/bin/env python3
"""Aba declarada num grupo TEM que nascer com tela — senão ela some e ninguém sabe.

Origem (14/09/2026): a Pyetra perguntou como aprovar ponto no Conecta PRO e concluiu, de
boa-fé, que a função não existia. Ela existia: a aba «Revisar justificativas», com as 7
justificativas pendentes e os botões Deferir/Indeferir. Só que ela NÃO CHEGAVA NA TELA.

O que acontecia, e por que ninguém viu em meses:

  1. `_tela_revisar_justificativa` lia `current_user.id`. Esse objeto é do ORM e pertence à
     sessão do request; qualquer `commit()` anterior dentro do `build()` o EXPIRA. Ler um
     atributo depois disso dispara recarregamento do banco e o SQLAlchemy async estoura com
     «greenlet_spawn has not been called».
  2. O `except Exception:` mudo em volta do bloco engolia o erro.
  3. `montar_grupos` monta a aba a partir de `out.get(tid)` — que agora era None. Aba sem
     tela não é renderizada: ela simplesmente não existe para quem olha.

Nada explodia. Nada no log. A tela sumia. Em processo o defeito NÃO reproduz, porque ali o
`current_user` é um objeto simples — por isso testar por dentro dava verde.

O que este oráculo afirma: para cada módulo com grupos, TODA aba declarada em GRUPOS tem
tela montada. É a pergunta que expõe a família inteira, não só o caso do ponto.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/orq/test_aba_declarada_nasce.py

Linha canônica: `TOTAL: <n> aba(s) declarada(s) sem tela`. Exit 1 quando há achado.
"""
from __future__ import annotations

import asyncio
import sys

#: O `current_user` do request é um objeto do ORM. Reproduzir isso é o ponto: um objeto
#: que EXPLODE ao ter um atributo lido é o que o servidor entrega depois de um commit.
class _UsuarioExpirado:
    """Imita um objeto do ORM expirado: ler atributo levanta, como em produção."""

    def __init__(self, uid: str) -> None:
        object.__setattr__(self, "_uid", uid)

    def __getattr__(self, nome: str):
        if nome in ("id", "email", "role", "permissions", "is_active"):
            raise RuntimeError(
                "greenlet_spawn has not been called; can't call await_only() here "
                "(objeto do ORM expirado — simulado pelo oráculo)"
            )
        raise AttributeError(nome)


async def main() -> int:
    from core.database import async_session_factory  # noqa: PLC0415
    from modules.operacional.controllers import redesign_data_controller as RD  # noqa: PLC0415

    #: módulo -> função que devolve os grupos declarados
    grupos_por_modulo: dict[str, list] = {}
    try:
        from modules.operacional.controllers.redesign_builders._dp_grupos import (  # noqa: PLC0415
            GRUPOS as _G_DP,
        )

        grupos_por_modulo["departamento-pessoal"] = _G_DP
    except Exception as e:  # noqa: BLE001
        print(f"   ! não carreguei os grupos do DP: {e}")
    try:
        from modules.operacional.controllers.redesign_builders._op_grupos import (  # noqa: PLC0415
            GRUPOS as _G_OP,
        )

        grupos_por_modulo["operacional"] = _G_OP
    except Exception:  # noqa: BLE001
        pass
    try:
        from modules.operacional.controllers.redesign_builders._fin_grupos import (  # noqa: PLC0415
            GRUPOS as _G_FIN,
        )

        grupos_por_modulo["financeiro"] = _G_FIN
    except Exception:  # noqa: BLE001
        pass

    faltando: list[str] = []
    total_abas = 0

    for slug, grupos in grupos_por_modulo.items():
        builder = RD.BUILDERS.get(slug)
        if not builder:
            faltando.append(f"{slug}: sem builder registrado")
            continue

        import inspect as _i  # noqa: PLC0415

        aceita_user = "current_user" in _i.signature(builder).parameters
        async with async_session_factory() as db:
            try:
                # Com o usuário EXPIRADO — que é o que o servidor entrega de verdade.
                if aceita_user:
                    out = await builder(db, current_user=_UsuarioExpirado("00000000-0000-0000-0000-000000000000"))
                else:
                    out = await builder(db)
            except Exception as e:  # noqa: BLE001
                faltando.append(f"{slug}: o builder INTEIRO caiu — {type(e).__name__}: {str(e)[:90]}")
                continue

        # `montar_grupos` já rodou dentro do build: a tela real vive na aba do grupo.
        por_grupo = {
            gid: {a.get("id"): a.get("screen") for a in (out.get(gid) or {}).get("tabs") or []}
            for gid, *_ in grupos
        }
        for gid, _titulo, _sub, tabs in grupos:
            for tid, rotulo in tabs:
                total_abas += 1
                if por_grupo.get(gid, {}).get(tid) is None:
                    faltando.append(f"{slug} / {gid} / {tid} («{rotulo}») — declarada e SEM TELA")

    for f in faltando:
        print(f"   ✗ {f}")
    if not faltando:
        print(f"   ✓ {total_abas} aba(s) declarada(s) em {len(grupos_por_modulo)} módulo(s), todas com tela")
        print("     (medido com o usuário EXPIRADO, que é o que o servidor entrega)")
    print(f"\nTOTAL: {len(faltando)} aba(s) declarada(s) sem tela")
    return 1 if faltando else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
