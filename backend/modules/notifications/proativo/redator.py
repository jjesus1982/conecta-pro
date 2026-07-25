"""Fase 5.3 — Redator: o cérebro SÓ escreve o texto de uma condição já detectada.

A regra (SQL) já decidiu o disparo/destinatário/severidade. Aqui o consultor_hub
redige 1-2 frases no tom certo. Groundedness: o CONJUNTO de valores numéricos do
corpo do LLM tem que ser IGUAL (não subconjunto) ao do template — nada faltando
E nada fabricado a mais (ex.: "40% acima da média" que o LLM inventou). Senão
cai no template determinístico. LLM off → template.
NUNCA tool-calling aqui (é só redação; origem != 'executivo' p/ não acionar Hermes).

Fix pós-review (Task 4, Fase 5.3): o check antigo usava `issubset` (permitia
número extra fabricado) e comparava strings cruas (`f"{x:,.2f}"` em formato US
rejeitava o mesmo valor legítimo escrito em PT-BR pelo LLM, ex. "242.073,20").
Agora comparamos por VALOR canônico (Decimal), não por string — BR e US do
mesmo número casam; qualquer valor novo (fabricado) quebra a igualdade.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

_SYS = (
    "Você redige alertas curtos e diretos para um ERP de segurança patrimonial. "
    "Escreva NO MÁXIMO 2 frases, tom objetivo, português do Brasil. Use EXATAMENTE "
    "os números fornecidos — não invente nem arredonde. Não proponha ações; só informe."
)

# Token numérico "de conteúdo": dígitos com separadores '.'/',' colados só quando
# seguidos de mais dígitos — não gruda pontuação de fim de frase (ex. "...R$ 50.").
_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)*")


def _brl(valor: float | int) -> str:
    """Formata valor em padrão monetário brasileiro (milhar '.', decimal ',')."""
    texto_us = f"{float(valor):,.2f}"  # ex.: "242,073.20"
    milhar, _, decimal = texto_us.partition(".")
    return milhar.replace(",", "\x00").replace(".", ",").replace("\x00", ".") + "," + decimal


def _canonicaliza(token: str) -> Decimal | None:
    """Converte um token numérico cru (BR OU US) num Decimal canônico.

    Regra: o ÚLTIMO separador '.' ou ',' com 1-2 dígitos após é o decimal;
    todos os demais separadores no token são milhar e são removidos. Assim
    "242.073,20" (BR), "242,073.20" (US) e "242073.20" convergem pro mesmo Decimal.
    """
    sinal = ""
    t = token
    if t.startswith("-"):
        sinal, t = "-", t[1:]
    idx = max(t.rfind("."), t.rfind(","))
    if idx == -1:
        digitos = t
    else:
        antes, depois = t[:idx], t[idx + 1:]
        if 1 <= len(depois) <= 2 and depois.isdigit():
            digitos = re.sub(r"[.,]", "", antes) + "." + depois
        else:
            digitos = re.sub(r"[.,]", "", t)
    if not digitos or not re.fullmatch(r"\d+(\.\d+)?", digitos):
        return None
    try:
        return Decimal(sinal + digitos).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _valores(texto: str) -> set[Decimal]:
    """Conjunto de valores numéricos CANÔNICOS presentes no texto (BR ou US —
    ambos convergem pro mesmo Decimal). Base do groundedness por IGUALDADE de
    conjuntos: nada do template pode faltar E nada pode ser fabricado a mais."""
    out: set[Decimal] = set()
    for tok in _NUM_RE.findall(texto):
        v = _canonicaliza(tok)
        if v is not None:
            out.add(v)
    return out


async def redigir(regra, achado, *, gerar_fn=None):
    tpl_title, tpl_body = regra.template(achado.dados)
    # Severidade dinâmica: pendência das reviews T1/T2 — o achado pode carregar
    # uma severidade per-instância (ex. vencida=critico vs a vencer=atencao) que
    # sobrescreve a severidade estática da regra.
    severidade = achado.dados.get("severidade", regra.severidade)
    if gerar_fn is None:
        from modules.ai.conversation.services.consultor_hub import gerar as gerar_fn  # noqa: N806

    try:
        prompt = (
            f"Condição detectada (família {regra.familia}, severidade {severidade}). "
            f"Texto-base a reescrever no seu tom: \"{tpl_body}\". "
            f"Dados exatos: {achado.dados}."
        )
        # gpt-4.1 (não gpt-5): reescrita fiel exige um modelo que RESPEITE temperature=0.2
        # (gpt-5 é reasoning e roda temp=1 → paráfrase criativa que o groundedness rejeita,
        # caindo sempre no template). gpt-4.1 é rápido (~500ms) e passa o groundedness.
        texto, _meta = await gerar_fn(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=_SYS, max_tokens=180, temperature=0.2,
            origem=None, direct=True, model="gpt-4.1",
        )
        texto = (texto or "").strip()
        # Groundedness por IGUALDADE de conjuntos (não subconjunto): o corpo do LLM
        # só é aceito se tiver EXATAMENTE os mesmos valores do template — nada
        # faltando (omissão) e nada fabricado a mais (ex. "40% acima da média").
        # Comparação por VALOR canônico: BR ("242.073,20") e US ("242,073.20") do
        # mesmo número casam.
        if texto and _valores(texto) == _valores(tpl_body):
            return tpl_title, texto
        logger.info("[proativo] redator sem groundedness (%s) → template", regra.nome)
    except Exception as exc:  # noqa: BLE001 — degradação graciosa
        logger.info("[proativo] redator LLM off (%s: %s) → template", regra.nome, exc)
    return tpl_title, tpl_body


if __name__ == "__main__":
    import asyncio

    from modules.notifications.proativo.regras import REGISTRY, Achado

    async def main() -> None:
        # ---- unit: canonicalização BR/US/sem-separador convergem pro mesmo Decimal ----
        assert _brl(242073.2) == "242.073,20"
        assert _brl(10000) == "10.000,00"
        assert _valores("R$ 242.073,20") == _valores("R$ 242,073.20") == {Decimal("242073.20")}
        assert _valores("242073.20") == {Decimal("242073.20")}
        # pontuação de fim de frase não gruda no número
        assert _valores("Faltam 2.") == {Decimal("2.00")}

        # ============ posto_descoberto: caso simples (sem dinheiro) ============
        regra = REGISTRY["posto_descoberto"]
        achado = Achado(correlation_id="posto_descoberto:x",
                        dados={"post_id": "x", "posto": "Portaria Central",
                               "faltam": 2, "req": 3, "cur": 1})
        tpl_title, tpl_body = regra.template(achado.dados)

        # 1) LLM "bom" cita TODOS os números do template (mesmo conjunto) → usa o LLM
        texto_ok = "O posto Portaria Central está com 2 vaga(s) descoberta(s) (1/3); acione cobertura."
        async def gerar_ok(**kw):
            return (texto_ok, {})
        title, body = await redigir(regra, achado, gerar_fn=gerar_ok)
        assert title == tpl_title            # título sempre determinístico
        assert body == texto_ok              # aceitou o texto do LLM (não caiu no template)

        # 2) LLM "alucina" (não cita nenhum número) → cai no template
        async def gerar_ruim(**kw):
            return ("Tudo certo por aqui, sem novidades.", {})
        _, body2 = await redigir(regra, achado, gerar_fn=gerar_ruim)
        assert body2 == tpl_body

        # ============ caixa_baixo_cnpj: caso com dinheiro (BR × US × fabricação) ============
        regra_caixa = REGISTRY["caixa_baixo_cnpj"]
        achado_caixa = Achado(
            correlation_id="caixa_baixo:eletronica:2026-07",
            dados={"cnpj": "CONECTA ELETRONICA", "banco": "Banco Inter",
                   "saldo": 242073.20, "limiar": 10000.0, "usou_fallback": True},
        )
        tpl_title_caixa, tpl_body_caixa = regra_caixa.template(achado_caixa.dados)
        assert "R$ 242.073,20" in tpl_body_caixa, tpl_body_caixa  # fallback já em BR (fix templates)
        assert "R$ 10.000,00" in tpl_body_caixa, tpl_body_caixa

        # (a) corpo LLM com número FABRICADO extra (ex. "40%") → REJEITADO, cai no template
        texto_fabricado = (
            "O caixa da CONECTA ELETRONICA está em R$ 242.073,20, 40% abaixo "
            "do limiar de R$ 10.000,00."
        )
        async def gerar_fabricado(**kw):
            return (texto_fabricado, {})
        _, body_a = await redigir(regra_caixa, achado_caixa, gerar_fn=gerar_fabricado)
        assert body_a == tpl_body_caixa, body_a  # rejeitado → template, NUNCA o número fabricado

        # (b) corpo LLM com os MESMOS valores em formatação BR nativa → ACEITO
        texto_br_nativo = (
            "O caixa da CONECTA ELETRONICA está em R$ 242.073,20, abaixo do "
            "piso de R$ 10.000,00."
        )
        async def gerar_br(**kw):
            return (texto_br_nativo, {})
        _, body_b = await redigir(regra_caixa, achado_caixa, gerar_fn=gerar_br)
        assert body_b == texto_br_nativo, body_b  # aceito — BR do LLM casa com BR do template

        # (c) número faltando (omite o limiar) → cai no template
        texto_faltando = "O caixa da CONECTA ELETRONICA está baixo, apenas R$ 242.073,20 disponíveis."
        async def gerar_faltando(**kw):
            return (texto_faltando, {})
        _, body_c = await redigir(regra_caixa, achado_caixa, gerar_fn=gerar_faltando)
        assert body_c == tpl_body_caixa, body_c

        # (d) LLM explode → fallback template
        async def gerar_boom(**kw):
            raise RuntimeError("sem OPENAI_API_KEY")
        _, body_d = await redigir(regra_caixa, achado_caixa, gerar_fn=gerar_boom)
        assert body_d == tpl_body_caixa

        # (e) severidade dinâmica: achado.dados["severidade"] sobrescreve regra.severidade
        #    (usa certidao_vencendo, que carrega severidade per-achado)
        regra_cert = REGISTRY["certidao_vencendo"]
        achado_vencida = Achado(
            correlation_id="certidao:y:2026-01-01",
            dados={"cert_id": "y", "nome": "CND Federal", "dias": -5,
                   "expiry": "2026-01-01", "vencida": True, "severidade": "critico"},
        )
        assert regra_cert.severidade == "atencao"  # estática da regra
        capturado = {}

        async def gerar_captura(**kw):
            capturado["prompt"] = kw["messages"][0]["content"]
            raise RuntimeError("força fallback p/ não desviar do teste de severidade")
        await redigir(regra_cert, achado_vencida, gerar_fn=gerar_captura)
        assert "severidade critico" in capturado["prompt"], capturado["prompt"]
        assert "severidade atencao" not in capturado["prompt"]

        print("OK redator — groundedness canônico (igualdade BR/US) + fabricação barrada + fallback + severidade dinâmica")

    asyncio.run(main())
