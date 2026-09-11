"""O que o funcionário pergunta sobre a PRÓPRIA vida na empresa — lido do portal dele.

Jordan, 11/09/2026: *"dê a ele tudo o que ele não tem"*. O diagnóstico era este: o portal do
funcionário tem 100 rotas no backend — holerite, espelho, férias, benefícios, comunicado,
documento para assinar — e o José Luís alcançava CINCO coisas. Quem perguntava "cadê meu
holerite" era transferido para um humano ler a mesma tela que o agente podia ler.

⭐ O DESENHO, e ele é o ponto deste arquivo: **nada aqui reimplementa consulta**. Cada função
chama a MESMA função que o app do funcionário chama, com um usuário-sombra que carrega só o
`employee_id` resolvido pelo TELEFONE. Reescrever as consultas criaria uma segunda verdade
sobre o holerite de alguém — e duas verdades sobre dinheiro é como esta casa já se machucou.

A identidade continua vindo do telefone (`whatsapp/identidade.quem_e`), nunca de argumento: o
agente não escolhe de quem é o holerite que vai ler.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Manaus")


@dataclass
class _UsuarioSombra:
    """O mínimo que as funções do portal pedem: quem é a pessoa. Nada além disso.

    Não é um usuário logado e não deve virar um: ele não tem sessão, não tem senha e não
    responde por nada fora deste `employee_id`, que veio do telefone que mandou a mensagem.
    """

    employee_id: str
    id: str = "jose-luis"
    email: str = "jose-luis@conectamais.pro"
    full_name: str = "José Luís (atendimento)"


async def _chamar(fn, employee_id: str, **kwargs) -> Any:
    """Chama uma função do portal com o usuário-sombra. Erro vira resposta legível, não crash.

    ⚠️ A saída passa por `jsonable_encoder`. As funções do portal devolvem modelos Pydantic,
    `date` e `Decimal` porque quem as consome é o FastAPI, que serializa no caminho de volta.
    Aqui quem consome é o agente, e o `json.dumps` dele estoura com "Object of type
    MyPayslipResponse is not JSON serializable" — foi o que aconteceu na primeira prova: a
    ferramenta trouxe o holerite CERTO e a conversa morreu em "estou com um problema técnico".
    """
    from fastapi import HTTPException
    from fastapi.encoders import jsonable_encoder

    from core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            return jsonable_encoder(
                await fn(db=db, current_user=_UsuarioSombra(employee_id=str(employee_id)), **kwargs))
        except HTTPException as e:
            return {"erro": str(e.detail)[:300]}
        except Exception as e:  # noqa: BLE001 — uma consulta ruim não pode calar o atendimento
            logger.warning("vida_do_funcionario.%s falhou: %s", getattr(fn, "__name__", "?"), e)
            return {"erro": "não consegui consultar isso agora"}


async def holerites(employee_id: str, mes: int | None = None, ano: int | None = None) -> dict:
    """Holerites da pessoa. Sem mês, a lista do ano; com mês e ano, o detalhe daquele.

    ⚠️ Os parâmetros vão SEMPRE explícitos. As funções do portal declaram `Query(default=None)`
    como valor padrão, e chamá-las direto (sem o FastAPI no meio) entrega o objeto `Query` em
    vez do None — que é truthy e vaza para dentro do SQL como `Query(None)`. Na primeira prova
    o holerite voltou vazio por isso, sem erro nenhum na cara.
    """
    from modules.people_management.employee_portal.controllers import self_service_controller as P

    hoje = datetime.now(_TZ)
    if mes and ano:
        return await _chamar(P.meu_holerite_mes, employee_id, month=int(mes), year=int(ano))
    return await _chamar(P.meus_holerites, employee_id, year=int(ano or hoje.year))


async def escala(employee_id: str) -> dict:
    """A escala dela e o próximo turno — a pergunta mais frequente depois do ponto."""
    from modules.people_management.employee_portal.controllers import self_service_controller as P

    hoje = datetime.now(_TZ)
    return {"escala": await _chamar(P.minha_escala, employee_id, mes=hoje.month, ano=hoje.year),
            "proximo_turno": await _chamar(P.meu_proximo_turno, employee_id)}


async def ferias(employee_id: str) -> dict:
    """Saldo de férias e solicitações."""
    from modules.people_management.employee_portal.controllers import self_service_controller as P

    return {"saldo": await _chamar(P.minhas_ferias_saldo, employee_id),
            "solicitacoes": await _chamar(P.minhas_ferias_solicitacoes, employee_id)}


async def beneficios(employee_id: str) -> dict:
    """VT, VR, plano — o que a pessoa recebe."""
    from modules.people_management.employee_portal.controllers import self_service_controller as P

    return await _chamar(P.meus_beneficios, employee_id)


async def documentos(employee_id: str) -> dict:
    """Documentos dela, inclusive o que espera assinatura."""
    from modules.people_management.employee_portal.controllers import self_service_controller as P

    return await _chamar(P.meus_documentos, employee_id)


async def comunicados(employee_id: str) -> dict:
    """Avisos e notificações do portal — o que a empresa mandou e ela talvez não tenha visto."""
    from modules.people_management.employee_portal.controllers import self_service_controller as P

    return await _chamar(P.minhas_notificacoes, employee_id)


#: ⚠️ TUDO comparado como TEXTO. `gp_clock_punches.employee_id` é uuid e
#: `gp_justifications.employee_id` é varchar — usar o mesmo parâmetro nos dois faz o asyncpg
#: inferir UM tipo só e estourar com "operator does not exist: character varying = uuid".
_SQL_HISTORICO = """
SELECT
  (SELECT count(*) FROM gp_clock_punches p WHERE p.employee_id::text = :e
     AND p.device_type = 'contingencia' AND p.punch_timestamp > current_date - 30) AS contingencias_30d,
  (SELECT to_char(max(p.punch_timestamp),'DD/MM HH24:MI') FROM gp_clock_punches p
    WHERE p.employee_id::text = :e AND p.device_type = 'contingencia') AS ultima_contingencia,
  (SELECT count(*) FROM gp_clock_punches p WHERE p.employee_id::text = :e
     AND p.device_type IN ('mobile','web') AND p.punch_timestamp > current_date - 30) AS pelo_app_30d,
  (SELECT count(*) FROM gp_clock_punches p WHERE p.employee_id::text = :e
     AND p.device_type = 'tangerino' AND p.punch_timestamp > current_date - 30) AS pelo_tangerino_30d,
  (SELECT count(*) FROM gp_justifications j WHERE j.employee_id = :e
     AND j.status = 'pendente') AS justificativas_pendentes,
  (SELECT count(*) FROM gp_audit_logs a WHERE a.related_funcionario_id = :e
     AND a.action = 'ponto.tentativa_falhou'
     AND a.timestamp > (now() AT TIME ZONE 'America/Manaus') - interval '30 days') AS falhas_faciais_30d,
  (SELECT string_agg(x.d, ' · ') FROM (
     SELECT to_char(a.timestamp,'DD/MM') || ': ' ||
            left(coalesce(a.extra_data->>'detalhe', a.description,''), 90) AS d
       FROM gp_audit_logs a
      WHERE a.related_funcionario_id = :e AND a.action = 'ponto.pesquisa_resposta'
      ORDER BY a.timestamp DESC LIMIT 3) x) AS ja_relatou
"""


async def historico(employee_id: str) -> dict:
    """O que já aconteceu com ESTA pessoa — para o agente falar com memória do caso.

    É o que permite a frase que faltava: *"é o terceiro dia seguido que você usa o registro
    para o DP validar"*. Sem isso cada conversa recomeça do zero e a pessoa repete a história
    toda vez — que é exatamente a sensação de não ser ouvido.
    """
    from sqlalchemy import text as sql

    from core.database import async_session_factory

    async with async_session_factory() as db:
        r = (await db.execute(sql(_SQL_HISTORICO), {"e": str(employee_id)})).mappings().first()
    d = dict(r or {})
    # tradução para frase: o agente não deve fazer conta, deve ler
    d["resumo"] = " · ".join(filter(None, [
        f"{d.get('pelo_app_30d') or 0} batidas pelo app em 30 dias",
        f"{d.get('pelo_tangerino_30d') or 0} pelo Tangerino",
        (f"{d['contingencias_30d']} vezes usou 'registrar para o DP validar' "
         f"(última em {d.get('ultima_contingencia')})") if d.get("contingencias_30d") else None,
        f"{d['falhas_faciais_30d']} falhas de reconhecimento facial" if d.get("falhas_faciais_30d") else None,
        f"{d['justificativas_pendentes']} justificativa(s) esperando o DP" if d.get("justificativas_pendentes") else None,
    ]))
    d["consultado_em"] = datetime.now(_TZ).strftime("%d/%m %H:%M")
    return d
