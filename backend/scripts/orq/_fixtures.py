#!/usr/bin/env python3
"""Fixtures dos oráculos: acha usuário de teste por PAPEL, nunca por e-mail.

Quatro oráculos quebraram em 11/08/2026 porque hardcodavam `egonzaga@conectamais.pro` —
pessoa que saiu, 0 linhas em `users`. O que eles testam é o PAPEL (que tools um gestor
recebe), não aquela pessoa.

Amarrar teste a e-mail de gente é dívida garantida: quebra em toda saída, e a falha
aparece como se fosse defeito de produto — foi exatamente o que aconteceu, e três das
sete "falhas" do dia eram isto.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text


@dataclass
class _U:
    """Usuário mínimo que os oráculos precisam (id, papel, permissões)."""

    id: str
    role: str
    permissions: list = field(default_factory=list)


#: Exit code que a varredura lê como BLOQUEADO — nem verde nem vermelho. Nasceu em
#: 06/09/2026: `test_papel_fornecedor` reprovava por "Insufficient Balance" do provedor de
#: LLM e `test_caso_de_uso_porteiro` por não haver espelho apurado no dia 6 do mês. Nenhum
#: dos dois é defeito de produto, e os dois contavam como vermelho todo dia — e vermelho
#: que não é defeito ensina a ignorar o vermelho que é.
EXIT_BLOQUEADO = 3


def bloqueado(motivo: str) -> None:
    """Encerra o oráculo como BLOQUEADO: dependência externa fora ou pré-condição de dado.

    Use quando a pergunta do oráculo NÃO PODE ser respondida hoje — não quando a resposta é
    "não". Um `assert` que falha é vermelho; isto é "não deu para medir", que é resultado
    válido e diferente.
    """
    print(f"BLOQUEADO: {motivo}")
    raise SystemExit(EXIT_BLOQUEADO)


def exige_host(oque: str) -> None:
    """Encerra como BLOQUEADO quando o oráculo precisa do HOST e está rodando no container.

    A varredura da meia-noite roda tudo DENTRO do `conecta-pro-backend`, de propósito (um
    oráculo tem pico de 894 MB e derrubaria worker de celery por OOM). Mas alguns medem
    coisas que só existem no host: o código-fonte do frontend, o `docker` para falar com
    outro container, o crontab.

    Medido em 17/09/2026: cinco oráculos apareceram VERMELHOS na varredura por esse motivo —
    `test_link_assinatura_chega` acusou «destino-pos-login.ts sumiu» sobre um arquivo que
    está lá, e `test_envio_nao_mente` disse «o envio mente» quando o que faltava era
    /usr/bin/docker. Acusação falsa custa mais que trava nenhuma: ensina a ignorar o vermelho.

    Nem verde (não mediu) nem vermelho (nada quebrado): BLOQUEADO, com o motivo dito.
    """
    import pathlib as _pl

    if _pl.Path("/usr/bin/docker").exists() and _pl.Path("/opt/conecta-pro/frontend/src").is_dir():
        return
    bloqueado(
        f"{oque} — este oráculo mede o HOST e está rodando dentro do container. "
        f"Rode no host: python3 backend/scripts/orq/<nome>.py"
    )


def tela(telas: dict, slug: str) -> dict | None:
    """Resolve um slug do redesign até a tela REAL, seguindo `groupRef`.

    A reorganização de 05/08/2026 agrupou a sidebar (62 itens → 8 grupos): o slug antigo
    continua existindo, mas como `{"type": "redirect", "groupRef": {...}}` — a tela de
    verdade virou aba de um grupo. Oráculo que lê `telas[slug]` direto encontra o stub e
    conclui "tela vazia" sobre uma tela cheia. Foi exatamente o que aconteceu com
    `folha-nao-conformidades`, que tem 9 linhas.

    Devolve None se o slug não existe ou se o redirect aponta para aba inexistente — este
    segundo caso é defeito real (link quebrado), e quem chama deve tratar como falha.
    """
    s = telas.get(slug)
    if not s or s.get("type") != "redirect":
        return s
    ref = s.get("groupRef") or {}
    grupo = telas.get(ref.get("t")) or {}
    for aba in grupo.get("tabs") or []:
        if aba.get("id") == ref.get("tab"):
            return aba.get("screen")
    return None


async def usuario_por_papel(db, papel: str) -> _U | None:
    """Primeiro usuário ATIVO com o papel pedido. None se não houver.

    Devolve None em vez de explodir para o chamador escolher entre pular honestamente
    ou falhar — nem todo papel existe em toda base.
    """
    r = (
        await db.execute(
            text(
                "SELECT id::text AS id, role, permissions FROM users "
                "WHERE role = :p AND coalesce(is_active, true) "
                "ORDER BY created_at NULLS LAST LIMIT 1"
            ),
            {"p": papel},
        )
    ).first()
    if not r:
        return None
    return _U(r.id, r.role, list(r.permissions or []))


async def usuario_por_papel_com_colaborador(db, papel: str) -> _U | None:
    """Usuário ativo com o papel pedido E vinculado a um colaborador (`employee_id`).

    Existe porque alguns oráculos exigem escopo pessoal (tier CLT precisa de
    `employee_id`; líder precisa de posto). Pegar qualquer usuário do papel devolveria
    um sem vínculo e a asserção falharia por motivo errado.
    """
    r = (
        await db.execute(
            text(
                "SELECT id::text AS id, role, permissions FROM users "
                "WHERE role = :p AND coalesce(is_active, true) AND employee_id IS NOT NULL "
                "ORDER BY created_at NULLS LAST LIMIT 1"
            ),
            {"p": papel},
        )
    ).first()
    if not r:
        return None
    return _U(r.id, r.role, list(r.permissions or []))


async def exigir_usuario_com_colaborador(db, papel: str) -> _U:
    """Como acima, mas falha dizendo o que fazer."""
    u = await usuario_por_papel_com_colaborador(db, papel)
    if u is None:
        raise AssertionError(
            f"nenhum usuário ativo com papel '{papel}' E employee_id — o oráculo precisa "
            f"de alguém com vínculo de colaborador para resolver escopo pessoal."
        )
    return u


async def exigir_usuario_com_escopo(db, modulos: set[str]) -> tuple[_U, str]:
    """Um usuário ativo cujo ESCOPO DE MÓDULOS é exatamente `modulos`. Devolve (usuário, motivo).

    Por que não por papel, nem por e-mail — os dois já quebraram aqui, em sequência:
      · por E-MAIL: `egonzaga@conectamais.pro` saiu da empresa e o oráculo parou;
      · por PAPEL:  trocou-se para `supervisor`, e em 18/09/2026 NÃO HÁ NENHUM supervisor
        ativo (o único, o Eliziel, está inativo). O oráculo voltou a parar — e a mensagem
        pedia «crie um usuário com esse papel», que é mandar mexer no cadastro de gente para
        satisfazer um teste.

    O teste não precisa de um papel nem de uma pessoa: precisa de alguém com AQUELE ESCOPO.
    Medido no mesmo dia: dois ativos têm exatamente {dp, ged, operacional, sst}, ambos com
    papel `gerente_operacional`. Pedir o escopo sobrevive a renomeação de papel, a saída de
    pessoa e a mudança do modelo de permissão — porque pergunta o que o teste afirma.
    """
    from sqlalchemy import select  # noqa: PLC0415

    from core.auth.module_scope import user_modules  # noqa: PLC0415
    from core.models.user import User  # noqa: PLC0415

    usuarios = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
    for u in usuarios:
        if user_modules(u) == set(modulos):
            return u, f"{getattr(u, 'email', '?')} (papel {getattr(u, 'role', '?')})"
    papeis = sorted({(getattr(u, "role", None) or "?") for u in usuarios})
    raise AssertionError(
        f"nenhum usuário ativo com o escopo exato {sorted(modulos)} — o oráculo não pode "
        f"rodar. Papéis ativos hoje: {papeis}. Ou alguém perdeu acesso, ou o escopo mudou de "
        f"forma; conferir em `core/auth/module_scope.py` antes de mexer no cadastro de gente."
    )


async def exigir_usuario(db, papel: str) -> _U:
    """Como `usuario_por_papel`, mas falha com mensagem que diz o que fazer."""
    u = await usuario_por_papel(db, papel)
    if u is None:
        raise AssertionError(
            f"nenhum usuário ativo com papel '{papel}' — o oráculo não pode rodar. "
            f"Crie um usuário com esse papel ou ajuste o papel esperado no oráculo."
        )
    return u


if __name__ == "__main__":
    import asyncio
    import sys

    sys.path.insert(0, "/app")
    from core.database import async_session_factory

    _TELAS = {
        "direta": {"type": "table", "rows": [1]},
        "agrupada": {"type": "redirect", "groupRef": {"t": "g-x", "tab": "agrupada"}},
        "quebrada": {"type": "redirect", "groupRef": {"t": "g-x", "tab": "nao-existe"}},
        "g-x": {"type": "tabs", "tabs": [{"id": "agrupada", "screen": {"type": "table", "rows": [1, 2]}}]},
    }
    assert tela(_TELAS, "direta")["rows"] == [1]
    assert tela(_TELAS, "agrupada")["rows"] == [1, 2], "não seguiu o groupRef"
    assert tela(_TELAS, "quebrada") is None, "redirect para aba inexistente deve dar None"
    assert tela(_TELAS, "inexistente") is None

    async def _self_check() -> None:
        async with async_session_factory() as db:
            achou = 0
            for papel in ("admin", "lider", "funcionario"):
                u = await usuario_por_papel(db, papel)
                print(f"  {papel:<14} {'OK ' + u.id[:8] if u else 'nenhum'}")
                achou += 1 if u else 0
            assert achou >= 2, "esperava achar pelo menos admin e lider"
            assert await usuario_por_papel(db, "papel_que_nao_existe") is None
            try:
                await exigir_usuario(db, "papel_que_nao_existe")
            except AssertionError as exc:
                assert "não pode rodar" in str(exc)
            else:
                raise AssertionError("exigir_usuario deveria ter falhado")
            print("self-check OK")

    asyncio.run(_self_check())
