"""Motor do orquestrador escopado: loop de function-calling in-backend.

Executa cada tool-handler com a identidade REAL do usuário (db, user, scope) — o
RBAC/escopo barra na fonte. Groundedness BRANDO (flag, não bloqueia) sobre a fonte
acumulada dos resultados das tools + auditoria append-only. NÃO usa consultor_hub.gerar
(não retorna tool_calls); usa AsyncOpenAI direto, como o molde do whatsapp/agent_service.
"""
from __future__ import annotations

from core.llm_client import novo_cliente
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.ai.conversation.services.garantia import agent_audit, groundedness

from .tool_registry import ToolDef, openai_schema

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "Resposta gerada por consultor de IA sobre os SEUS dados (escopo do seu perfil). "
    "Confira antes de agir. Ações que mexem em ponto/folha exigem aprovação humana."
)


def _model() -> str:
    return os.getenv("OPENAI_AGENT_MODEL", "gpt-5.1")


def _chat_kwargs(model: str, max_tokens: int, temperature: float = 0.2) -> dict[str, Any]:
    """gpt-5.x/o-series: max_completion_tokens, sem temperature custom. gpt-4.x: clássico.
    Espelha whatsapp/agent_service._chat_kwargs (315)."""
    m = model.lower()
    if m.startswith(("gpt-5", "o1", "o3", "o4")):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens, "temperature": temperature}


def _extrair_documentos(tool_results: list[Any]) -> list[dict[str, Any]]:
    """Coleta os artefatos de documento (gera-doc) dos retornos das tools: só dicts
    com arquivo_base64 E nome (recusa/erro não viram documento)."""
    return [
        {"nome": r["nome"], "arquivo_base64": r["arquivo_base64"], "resumo": r.get("resumo", "")}
        for r in tool_results
        if isinstance(r, dict) and r.get("arquivo_base64") and r.get("nome")
    ]


def _extrair_rascunho(tool_results: list[Any]) -> dict[str, Any] | None:
    """Último rascunho criado nesta rodada (criar_rascunho devolve status='rascunho'+draft_id).

    Vai no retorno para o chat poder oferecer a CONFIRMAÇÃO na hora — sem isto o usuário
    precisa sair da conversa e ir à Central de Aprovações. `gate` viaja junto porque decide
    se dá para confirmar ali mesmo ou se o caminho é OTP (dinheiro/eSocial)."""
    for r in reversed(tool_results):
        if isinstance(r, dict) and r.get("status") == "rascunho" and r.get("draft_id"):
            return {"draft_id": str(r["draft_id"]), "titulo": r.get("titulo", ""),
                    "tipo": r.get("tipo", ""), "gate": r.get("gate", "")}
    return None


@dataclass
class OrqScope:
    tier: str  # "gestor" | "lider" | "clt" | "cliente"
    employee_id: str | None = None
    post_ids: list[str] | None = None  # None = todos (gestor); [] = nenhum
    all_posts: bool = False
    is_manager: bool = False
    client_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def run_engine(
    db: AsyncSession,
    user,
    scope: OrqScope,
    tools: list[ToolDef],
    pergunta: str,
    *,
    system_prompt: str,
    origem: str = "consultor_escopado",
    max_rounds: int = 6,
    # 2500, medido em 24/08/2026 — NÃO é palpite e NÃO é a correção principal (ver abaixo).
    # O 1200 anterior era teto de resposta CURTA herdado de quando o motor era outro; a
    # migração para um modelo de RACIOCÍNIO deixou o número para trás, mesma família da
    # premissa envelhecida do ponto ("zero batidas de almoço" com 288 na base).
    # Medição: o raciocínio CRESCE com o teto (344 de 456 em 1200; 597 de 714 em 3000) e a
    # resposta fica constante (~400 chars). Ou seja, subir o teto compra menos do que parece —
    # por isso o conserto de verdade é a repetição em `finish_reason=length`, logo abaixo.
    max_tokens: int = 2500,
    client=None,
    imagens: list[str] | None = None,
) -> dict[str, Any]:
    if client is None:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = novo_cliente(origem="agente.orquestrador",
                              timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "90")))

    by_name = {t.name: t for t in tools}
    active_tools = [openai_schema(t) for t in tools]
    model = _model()

    # Anexo-foto: content vira lista (texto + image_url) p/ o modelo de visão enxergar.
    # O modelo de TEXTO pode não ler imagem — a deepseek-v4-flash devolve HTTP 400
    # "does not support image". Com anexo, troca-se de modelo, não se torce.
    # `pergunta` (str) segue intacta p/ audit/groundedness abaixo.
    user_content: Any = pergunta
    if imagens:
        from core.llm_client import modelo_visao  # noqa: PLC0415

        model = modelo_visao()
        user_content = [{"type": "text", "text": pergunta}] + [
            {"type": "image_url", "image_url": {"url": u}} for u in imagens
        ]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    tool_results: list[Any] = []  # tudo que as tools retornaram (fonte do groundedness)
    resposta = ""
    provider = "openai"

    for _round in range(1, max_rounds + 1):
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=active_tools if active_tools else None,
            tool_choice="auto" if active_tools else None,
            **_chat_kwargs(model, max_tokens),
        )
        escolha = resp.choices[0]
        msg = escolha.message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            resposta = (msg.content or "").strip()
            if not resposta and escolha.finish_reason == "length":
                # SUCESSO VAZIO: o modelo gastou o orçamento em `reasoning_content` e o texto
                # nunca começou. Medido em 24/08/2026: 11 de 59 chamadas do dia (18,6%)
                # terminaram assim, todas com ok=True na telemetria — não são ERRO, são
                # sucesso sem frase, que é pior de achar.
                # Uma repetição com o dobro do orçamento: o defeito é INTERMITENTE (a mesma
                # pergunta respondeu com 1200 numa corrida e morreu em 1200 noutra), então
                # subir o teto reduz probabilidade e a repetição é o que fecha.
                logger.warning("engine: finish_reason=length com content vazio (origem=%s, "
                               "max_tokens=%s) — repetindo com o dobro", origem, max_tokens)
                resp = await client.chat.completions.create(
                    model=model, messages=messages,
                    **_chat_kwargs(model, max_tokens * 2))
                escolha = resp.choices[0]
                resposta = (escolha.message.content or "").strip()
                if not resposta:
                    # NOMEIE A CAUSA. "(sem resposta)" é indistinguível de "o modelo não quis",
                    # "a tool falhou" e "o serviço caiu" — perdi tempo hoje decidindo qual dos
                    # três era. E fica em LOG + texto ao usuário, nunca em alerta: aviso que
                    # dispara sempre é aviso que morre (o falso positivo do groundedness).
                    resposta = ("A resposta foi cortada no limite de tamanho e eu não consegui "
                                "concluí-la. Isso é uma limitação minha, não um erro nos seus "
                                "dados — refaça a pergunta de forma mais direta, ou peça uma "
                                "parte de cada vez.")
                    logger.warning("engine: resposta cortada mesmo com %s tokens (origem=%s)",
                                   max_tokens * 2, origem)
            break

        _assistant = {
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ],
        }
        # ⚠️ 28/08/2026 — MESMO DEFEITO DO LAÇO DO WHATSAPP, achado lá e conferido aqui.
        # O modelo é de raciocínio e a DeepSeek recusa a rodada seguinte sem o
        # `reasoning_content` de volta: 400 "must be passed back to the API".
        # No José Luís isso virou 6 falhas hoje, cinco na mesma rajada — o Jordan recebeu
        # "tive uma falha" cinco vezes seguidas. Aqui ainda não apareceu porque o Bartolo
        # faz menos rodadas com tool; apareceria.
        # Só entra quando o modelo devolve — provedor sem raciocínio segue igual.
        _rc = getattr(msg, "reasoning_content", None)
        if _rc:
            _assistant["reasoning_content"] = _rc
        messages.append(_assistant)
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            tool = by_name.get(tc.function.name)
            if tool is None:
                result: Any = {"erro": "tool indisponível no seu escopo"}
            else:
                try:
                    result = await tool.handler(db, user, scope, **args)
                except PermissionError:
                    result = {"erro": "fora do seu escopo — aguardando dado"}
                except Exception as e:  # noqa: BLE001 — tool nunca derruba o loop
                    logger.warning("orq tool %s falhou: %s", tc.function.name, e)
                    # Erro TÉCNICO ≠ falta de permissão: não mascarar como "sem acesso"/"aguardando
                    # dado" (isso fazia bug virar trava percebida). Sinalizar que é técnico + detalhe.
                    result = {"erro": "erro técnico ao executar esta ação (NÃO é falta de permissão nem "
                                      "dado ausente) — pode tentar de novo; se persistir, avise o suporte",
                              "detalhe": str(e)[:200]}
            tool_results.append(result)
            # NÃO devolver o base64 do documento ao LLM: um PDF em base64 tem dezenas de
            # milhares de tokens e estoura o contexto (erro 400 context_length_exceeded).
            # O LLM só precisa saber que o documento saiu; o base64 segue no `documentos`
            # do retorno (para o frontend baixar).
            _llm_result = result
            if isinstance(result, dict) and result.get("arquivo_base64"):
                _llm_result = {k: v for k, v in result.items() if k != "arquivo_base64"}
                _llm_result["documento_gerado"] = result.get("nome") or "documento.pdf"
            messages.append(
                {"role": "tool", "tool_call_id": tc.id,
                 "content": json.dumps(_llm_result, ensure_ascii=False, default=str)}
            )
    else:
        # teto sem resposta final → última chamada SEM tools (força texto)
        resp = await client.chat.completions.create(
            model=model, messages=messages, **_chat_kwargs(model, max_tokens)
        )
        resposta = (resp.choices[0].message.content or "").strip()

    # GROUNDEDNESS BRANDO: fonte = números reais retornados pelas tools; flag, não bloqueia.
    fonte: dict[str, Any] = {f"tool_{i}": r for i, r in enumerate(tool_results)}
    g = groundedness.verificar(resposta, fonte)
    suspeitos = list(g.get("suspeitos") or [])
    flags: list[str] = []
    grounded = not suspeitos
    if suspeitos:
        # ARMADILHA ARMADA, não caçada. Em 24/08/2026 vi um `grounded=False` numa resposta
        # CERTA e, ao tentar reproduzir, o caso já estava verde — a pista morreu com a
        # ocorrência. Defeito não reproduzido volta; sem isto, a próxima vez recomeça do
        # zero. Aqui fica o suspeito, o trecho onde ele aparece e as chaves da fonte que o
        # agente tinha à mão — que é o que falta para decidir se é formato ou fabricação.
        #
        # LOG, nunca sino: aviso de verificador para humano é exatamente o ruído que
        # estamos consertando. Isto é para quem for depurar, não para quem for decidir.
        try:  # noqa: SIM105 — telemetria jamais derruba a resposta
            ctx = {}
            for s in suspeitos[:5]:
                i = resposta.find(s)
                ctx[s] = resposta[max(0, i - 45):i + len(s) + 45].replace("\n", " ") if i >= 0 else ""
            logger.warning(
                "groundedness ok=False origem=%s modelo=%s suspeitos=%s chaves_da_fonte=%s "
                "contexto=%s", origem, model, suspeitos[:8],
                sorted({k for r in tool_results if isinstance(r, dict) for k in r})[:20], ctx)
        except Exception:  # noqa: BLE001
            pass
        flags.append("confira: alguns números não puderam ser verificados contra as tools")
        resposta = resposta + (
            "\n\n[Aviso: alguns números acima não puderam ser verificados automaticamente "
            "contra os dados do ERP — confira antes de decidir.]"
        )

    try:
        await agent_audit.registrar_acao_agente(
            db, origem=origem, pergunta=pergunta, resposta=resposta,
            modelo=model, tier=scope.tier, provider=provider,
            groundedness_ok=grounded, trace_id=f"{origem}.{scope.tier}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("orq: falha ao auditar: %s", e)

    return {
        "resposta": resposta or "(sem resposta)",
        "provider": provider, "modelo": model, "grounded": grounded,
        "flags": flags, "origem": origem, "tier": scope.tier, "disclaimer": _DISCLAIMER,
        "documentos": _extrair_documentos(tool_results),
        "rascunho": _extrair_rascunho(tool_results),   # p/ confirmar sem sair da conversa
    }
