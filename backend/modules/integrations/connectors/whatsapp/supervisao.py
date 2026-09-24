"""Quem supervisiona, e o que acontece com pedido que MEXE NA ESCALA.

Duas decisões que o Jordan deu em 23/09/2026, e que moram juntas porque são a mesma
pergunta vista de dois lados:

1. **"Orlailson enxerga toda a operação."** Ele é o único supervisor hoje. A tentação era
   derivar isso de `employees.cargo ILIKE '%supervis%'` — e seria a trava observando a
   coisa errada de novo: `cargo` é texto que o Jordan edita na tela, e um "Supervisor de
   Portaria" cadastrado amanhã ganharia, **em silêncio**, visão sobre a vida de 61 pessoas.
   Autorização não se infere de rótulo.

   A autoridade já existia: `users.role = 'gerente_operacional'`, ligado ao colaborador por
   `users.employee_id`. Reuso ela. **Duas condições independentes**, e as duas precisam
   valer: o telefone resolve a um funcionário com VÍNCULO VIVO (`identidade.quem_e`, que
   recusa `inativo`/`candidato`/`pj_pendente`) **e** a conta dele tem o papel.

   ⚠️ E é por isso que as duas condições não são redundância: há HOJE um segundo
   `gerente_operacional` ativo — Eliziel Gonzaga — cujo colaborador está `inativo`. A conta
   viva com papel de gerente é um furo do RBAC do ERP (reportado ao Jordan, não consertado
   aqui: perfis são dele). Do lado do José Luís ele cai na primeira condição.

2. **"Pedido que muda escala — ele registra para ser aprovado por mim ou orlailson."**
   O operacional é curado à mão pelo Jordano e READ-ONLY para agentes. Então este módulo
   **não mexe em escala** — nem quando aprovado. Ele grava um pedido inerte na Central de
   Rascunhos e avisa quem decide. `ROLES_KIT_OP = ("admin", "gerente_operacional")` já é,
   literalmente, "eu ou o Orlailson".

   A aprovação autoriza a troca; **aplicar** segue sendo clique humano na tela de escala.
   O título diz isso em voz alta, porque um rascunho aprovado que parecesse "escala
   trocada" seria pior que não ter rascunho nenhum.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from core.logging import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Papéis de conta que enxergam a operação inteira. `admin` = Jordan e diretoria.
PAPEIS_SUPERVISAO = ("admin", "gerente_operacional")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(c))


#: Sinais de pedido que MEXE NA ESCALA. Só isto vira rascunho — "bom dia" e "tá chovendo"
#: não. Cada tupla é (rótulo, regex). O rótulo entra no título do rascunho para o Jordan
#: saber do que se trata sem abrir.
#:
#: ⚠️ A régua observa o PEDIDO, não a palavra. "Cobri o posto do Eduardo ontem" é relato e
#: não pede nada; "preciso que alguém cubra amanhã" pede. Daí os verbos de pedido/futuro
#: junto do objeto — e daí o `_RELATO` abaixo, que desarma o passado.
_PEDIDOS: tuple[tuple[str, str], ...] = (
    ("troca de plantão", r"\b(troca[r]?|permut[ae]r?|invert[er])\b.{0,30}\b(plantao|turno|escala|folga|dia)\b"),
    ("cobertura de posto", r"\b(cobr[ie]r?|substitu[ií]r?|repor|render)\b.{0,30}\b(posto|turno|plantao|vaga|ele|ela)\b"),
    ("falta anunciada", r"\b(nao vou|nao posso|nao consigo|vou faltar|faltarei|nao dou conta)\b.{0,40}\b(trabalhar|ir|comparecer|plantao|posto|amanha|hoje)\b"),
    ("atestado", r"\batestado\b|\b(passei|fui) no medico\b|\bmedico me afastou\b"),
    ("folga", r"\b(pedir|preciso de|queria|posso tirar|me d[aá])\b.{0,20}\bfolga\b"),
    ("férias", r"\bferias\b.{0,30}\b(quero|queria|posso|marcar|antecipar|adiar)\b|\b(quero|queria|posso|marcar)\b.{0,20}\bferias\b"),
    ("saída antecipada", r"\b(sair|liberar|liberacao)\b.{0,25}\b(mais cedo|antes|antecipad)"),
)

#: Relato do passado não é pedido. Sem isto, todo "ontem o Fulano cobriu" abriria rascunho.
_RELATO = re.compile(r"\b(ontem|anteontem|semana passada|mes passado|cobri|cobriu|cobrimos|ja foi|ja resolvi|resolvido)\b")


def classificar_pedido(texto: str | None) -> str | None:
    """Rótulo do pedido de escala, ou None quando a fala não pede nada.

    Determinístico e sem LLM, pelo mesmo motivo de `_papel_por_texto`: o que vira
    solicitação formal para o Jordan aprovar não pode depender de juízo do modelo.
    """
    t = _sem_acento(texto)
    if not t.strip():
        return None
    if _RELATO.search(t):
        return None
    for rotulo, padrao in _PEDIDOS:
        if re.search(padrao, t):
            return rotulo
    return None


async def papel_de_supervisao(db: AsyncSession, ident: Any) -> str | None:
    """`admin`/`gerente_operacional` quando a pessoa supervisiona; None caso contrário.

    Fail-closed em tudo: sem `employee_id` (telefone não resolveu a colaborador com vínculo
    vivo), sem conta, conta desativada ou papel fora da lista → None, e o José Luís trata a
    pessoa como funcionário comum, que é o comportamento de hoje.
    """
    emp = getattr(ident, "employee_id", None)
    if not emp or getattr(ident, "tipo", None) != "funcionario":
        return None
    try:
        row = (await db.execute(text(
            "SELECT role FROM users WHERE employee_id = :e AND is_active "
            "AND role = ANY(:papeis) LIMIT 1"),
            {"e": str(emp), "papeis": list(PAPEIS_SUPERVISAO)})).first()
    except Exception as e:  # noqa: BLE001
        logger.error("supervisao: papel não resolvido (%s) — tratando como funcionário", e)
        return None
    return row[0] if row else None


async def registrar_pedido_de_escala(
    db: AsyncSession,
    *,
    rotulo: str,
    texto: str,
    autor_nome: str | None,
    autor_fone: str | None,
    ident: Any = None,
    origem: str,
) -> dict[str, Any]:
    """Grava o pedido como rascunho inerte. NUNCA toca em escala, nem aqui nem na aprovação.

    `origem` é onde a pessoa falou (jid do grupo ou "privado") — entra no payload porque a
    mesma troca pedida em dois grupos é o mesmo pedido, e o Jordan precisa saber onde
    responder.
    """
    from types import SimpleNamespace  # noqa: PLC0415

    from modules.ai.conversation.services.orquestrador.acoes.base import ROLES_KIT_OP  # noqa: PLC0415
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho  # noqa: PLC0415

    # `solicitado_por` é trilha, não autoridade: quem pede não aprova (os aprovadores vêm de
    # ROLES_KIT_OP). Uso a conta do solicitante quando existe só para o histórico ficar
    # navegável; sem conta, fica só o nome.
    user_id = None
    emp = getattr(ident, "employee_id", None)
    if emp:
        try:
            user_id = (await db.execute(text(
                "SELECT id FROM users WHERE employee_id = :e LIMIT 1"), {"e": str(emp)})).scalar()
        except Exception:  # noqa: BLE001
            user_id = None

    nome = autor_nome or getattr(ident, "nome", None) or autor_fone or "desconhecido"
    quem = SimpleNamespace(id=user_id, nome=nome, name=nome)

    # ⚠️ O título diz "AUTORIZAR", não "trocar". Aprovar aqui autoriza a mudança; aplicar na
    # escala continua sendo o Jordan na tela. Um rascunho que se lesse "plantão trocado"
    # faria o aprovador acreditar num efeito que este módulo não produz.
    titulo = f"Autorizar {rotulo} — {nome}"
    resumo = (f'{nome} pediu em {origem}: "{texto.strip()[:220]}". '
              f"Aprovar AUTORIZA a mudança; a escala continua sendo aplicada à mão.")

    # Idempotência pela pessoa + rótulo + dia: a mesma pessoa repetindo o pedido três vezes
    # no grupo (o que acontece) não pode virar três rascunhos. O dia entra porque o pedido
    # de amanhã é outro pedido.
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415
    dia = (datetime.now(UTC) - timedelta(hours=4)).strftime("%Y-%m-%d")
    idem = f"escala:{emp or autor_fone or nome}:{rotulo}:{dia}"

    return await criar_rascunho(
        db, quem,
        tipo="escala_pedido",
        modulo="operacional",
        titulo=titulo,
        resumo=resumo,
        payload={
            "rotulo": rotulo,
            "texto": texto[:1000],
            "autor_nome": nome,
            "autor_fone": autor_fone,
            "employee_id": str(emp) if emp else None,
            "posto": getattr(ident, "posto", None),
            "origem": origem,
            # Declarado no payload para quem lê o rascunho não precisar confiar na prosa:
            # não há executor que escreva em escala, de propósito.
            "aplica_automaticamente": False,
        },
        gate="🟡",
        requires_otp=False,
        roles_aprovador=ROLES_KIT_OP,
        idempotency_key=idem,
    )
