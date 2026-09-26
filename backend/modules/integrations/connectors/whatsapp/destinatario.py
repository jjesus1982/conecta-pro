"""A ÚNICA porta para mandar mensagem a uma PESSOA. O número nunca vem de quem escreve.

🔴 POR QUE ESTE ARQUIVO EXISTE — 26/09/2026, eu errei o destinatário DUAS VEZES em dez minutos:

  · o passo a passo do ponto do **JAIR** foi para o **ANTONIO CARLOS VIEIRA**
  · o do **EULER** foi para o **ANTONIO DINIZ**

Nos dois casos eu digitei um número que estava no meu contexto de uma mensagem anterior, em vez
de LER o cadastro na hora do envio. E na mesma mensagem do Euler eu também inventei o e-mail
dele. Jordan: *"como consegue errar isso?"* e, depois: **"tem que ter o padrão"**.

⭐ ELE ESTÁ CERTO E A LIÇÃO É ESTRUTURAL: o remédio para "errei o número" não é *prestar mais
atenção* — é **tirar o número da mão de quem envia**. Enquanto existir um lugar onde se digita
`'5592...'`, alguém vai digitar o errado, e a mensagem certa chega na pessoa errada. Atenção não
é uma trava; a trava é não ter onde errar.

⚠️ Cinco pessoas nesta casa se chamam ANTONIO (Diniz, Carlos Vieira, Walcicley, Carlos Castro
Gama, Marcos Cavalcante). Duas se chamam Ramon. Por isso a regra mais importante daqui é
**AMBÍGUO RECUSA**: quando o nome casa com mais de uma pessoa, não existe "o mais provável" —
existe erro esperando. Quem chama passa o `employee_id`.

## Como usar

    from modules.integrations.connectors.whatsapp.destinatario import mandar

    r = await mandar(db, quem="JAIR SOARES DA ROCHA", texto=..., motivo="guia de ponto")
    if not r["ok"]:
        ...  # r["motivo"] diz exatamente o que faltou; NUNCA caia para um número literal

⚠️ `ok=True` só sai quando o serviço respondeu `status == 'sent'`. Os outros valores
(`error`, `exception`, `disabled`) são FALHA — esse defeito exato já marcou 4 pessoas como
avisadas com zero mensagens enviadas, em 25/09.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Celular brasileiro: 11 dígitos com DDD (9 dígitos após o 2016), 10 nos fixos antigos.
#: Fora disso é cadastro malformado — e a THAYNA tinha 12 dígitos nas duas tabelas.
_TAMANHOS_VALIDOS = (10, 11)

_SQL = text(
    "SELECT id::text AS employee_id, nome, coalesce(nullif(email,''), '') AS email, "
    "       coalesce(nullif(cpf,''), '') AS cpf, status, "
    "       regexp_replace(coalesce(nullif(celular,''), telefone, ''), '\\D', '', 'g') AS fone "
    "  FROM employees "
    " WHERE id::text = :q "
    "    OR upper(translate(nome, 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC')) "
    "       LIKE '%' || upper(translate(:q, 'ÁÀÂÃÉÊÍÓÔÕÚÇ', 'AAAAEEIOOOUC')) || '%'"
)


async def resolver(db: AsyncSession, quem: str, *, exigir_ativo: bool = True) -> dict[str, Any]:
    """Acha a pessoa e o telefone DELA no cadastro. Recusa ambíguo, desconhecido e malformado.

    Devolve `{"ok": True, "employee_id", "nome", "fone", "email", "cpf"}` ou
    `{"ok": False, "motivo": "..."}` — e o motivo é escrito para ser LIDO por quem chamou, não
    um booleano seco: `ok=False` sem explicação convida a improvisar um número.
    """
    q = (quem or "").strip()
    if not q:
        return {"ok": False, "motivo": "sem destinatário — recusado (fail-closed)"}

    rows = (await db.execute(_SQL, {"q": q})).mappings().all()
    if exigir_ativo:
        vivos = [r for r in rows if (r["status"] or "").lower().startswith(("ativo", "pj_", "afastado"))]
        rows = vivos or rows  # se só há demitido, deixo aparecer para o motivo dizer isso

    if not rows:
        return {"ok": False, "motivo": f"ninguém no cadastro casa com {q!r}"}
    if len(rows) > 1:
        # 🔴 A TRAVA QUE FALTAVA. Escolher aqui é o erro do Jair→Antonio Carlos.
        nomes = ", ".join(r["nome"] for r in rows[:6])
        return {"ok": False, "motivo": f"AMBÍGUO — {len(rows)} pessoas casam com {q!r}: {nomes}. "
                                      "Passe o employee_id; NÃO escolha por conta própria."}

    r = rows[0]
    if exigir_ativo and (r["status"] or "").lower() == "demitido":
        return {"ok": False, "motivo": f"{r['nome']} está DEMITIDO no cadastro — não mando"}
    if len(r["fone"]) not in _TAMANHOS_VALIDOS:
        return {"ok": False, "motivo": f"{r['nome']} tem telefone malformado no cadastro "
                                      f"({r['fone'] or 'vazio'!r}, {len(r['fone'])} dígitos). "
                                      "NÃO adivinho dígito: já mandamos mensagem nossa para o "
                                      "telefone de um estranho assim."}
    return {"ok": True, "employee_id": r["employee_id"], "nome": r["nome"],
            "fone": r["fone"], "email": r["email"], "cpf": r["cpf"]}


async def mandar(db: AsyncSession, *, quem: str, texto: str, motivo: str) -> dict[str, Any]:
    """Resolve o destinatário no cadastro e envia. `motivo` vai para o log — é a auditoria.

    ⚠️ NÃO aceita telefone. De propósito: um parâmetro `telefone=` aqui reabriria exatamente a
    porta que este módulo fecha.
    """
    from modules.integrations.connectors.whatsapp.service import whatsapp_service

    alvo = await resolver(db, quem)
    if not alvo["ok"]:
        logger.warning("destinatario: NÃO enviei (%s) — %s", motivo, alvo["motivo"])
        return alvo

    env = await whatsapp_service.send_custom("55" + alvo["fone"], texto)
    # `status == 'sent'` é o ÚNICO sucesso. Ver o docstring do módulo.
    ok = isinstance(env, dict) and env.get("status") == "sent"
    if not ok:
        logger.error("destinatario: envio para %s FALHOU (%s) — resposta: %s",
                     alvo["nome"], motivo, env)
    else:
        logger.info("destinatario: %s → %s (%s)", motivo, alvo["nome"], alvo["fone"])
    return {**alvo, "ok": ok, "enviado": ok, "motivo_envio": motivo, "resposta": env}
