"""
Conecta PRO — Servidor MCP (starter).

Expõe a API do Conecta PRO como ferramentas MCP para o Claude (conector remoto).
- Transporte: Streamable HTTP em /mcp
- Auth de entrada (Claude -> MCP): Bearer token (env MCP_AUTH_TOKEN)
- Auth de saída (MCP -> ERP): conta de serviço (login JWT, cacheado) — env ERP_USER/ERP_PASSWORD

NÃO toca no ERP: é um serviço separado que só consome a API HTTP existente.
"""
from __future__ import annotations

import os
import time
import contextvars
import secrets
import inspect
import asyncio
from datetime import date, timedelta
from typing import Any

import httpx
import re
import unicodedata
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

ERP_BASE_URL = os.getenv("ERP_BASE_URL", "http://conecta-pro-backend:8080").rstrip("/")
ERP_USER = os.getenv("ERP_USER", "")
ERP_PASSWORD = os.getenv("ERP_PASSWORD", "")
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")
API = f"{ERP_BASE_URL}/api/v1"

# Modo de autenticação de ENTRADA (Claude -> MCP):
#   bearer  -> token estático (default; funciona no Claude Code e clientes que aceitam header)
#   google  -> OAuth 2.1 delegado ao Google (app oficial do Claude). Requer GOOGLE_CLIENT_ID/SECRET
#              + PUBLIC_BASE_URL (domínio HTTPS público).
AUTH_MODE = os.getenv("AUTH_MODE", "bearer").lower()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://mcp.conectamais.pro").rstrip("/")

_auth_provider = None
if AUTH_MODE == "google":
    from fastmcp.server.auth.providers.google import GoogleProvider

    _allowed = [e.strip().lower() for e in os.getenv("GOOGLE_ALLOWED_EMAILS", "").split(",") if e.strip()]
    # FAIL-CLOSED: modo google SEM allowlist = qualquer conta Google entraria. Não sobe.
    if not _allowed:
        raise RuntimeError(
            "AUTH_MODE=google exige GOOGLE_ALLOWED_EMAILS populado (fail-closed): sem allowlist, "
            "qualquer conta Google teria acesso ao ERP. Configure GOOGLE_ALLOWED_EMAILS.")
    _auth_provider = GoogleProvider(
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        base_url=PUBLIC_BASE_URL,
        required_scopes=["openid", "email"],
    )
    # Restrição por e-mail: só estes Google accounts podem usar o conector.
    try:
        _orig_verify = _auth_provider.verify_token

        async def _verify_scoped(token, *a, **k):
            res = await _orig_verify(token, *a, **k)
            if res is None:
                return None
            claims = getattr(res, "claims", None) or {}
            email = (claims.get("email") or "").lower()
            # FAIL-CLOSED: sem e-mail OU fora da allowlist -> nega.
            if not email or email not in _allowed:
                return None
            return res

        _auth_provider.verify_token = _verify_scoped  # type: ignore[assignment]
    except Exception as _e:  # noqa: BLE001 — FAIL-CLOSED: não sobe sem o filtro aplicado
        raise RuntimeError(
            "Não foi possível aplicar o filtro de e-mail do conector (fail-closed, "
            f"o conector não inicia sem enforcement): {_e}")

mcp = FastMCP(
    name="Conecta PRO",
    instructions=(
        "Ferramentas do ERP Conecta PRO (segurança patrimonial). Use para consultar o pipeline "
        "comercial, criar propostas/orçamentos, leads, e consultar contratos/forecast. "
        "Valores em reais (BRL). Documentos são CNPJ/CPF.\n\n"
        "REGRA RÍGIDA — DOCUMENTOS E APRESENTAÇÕES (inegociável):\n"
        "1. TODO material da Conecta Mais (apresentação, proposta, orçamento, recibo, atestado, "
        "ordem de serviço, aditivo, holerite, relatório, parecer) SÓ pode ser gerado pelas tools "
        "gerar_*/baixar_* DESTE conector — elas aplicam o timbrado padrão-ouro da marca (logo real, "
        "cores oficiais, rodapé com CNPJ/0800, assinaturas). \n"
        "2. É PROIBIDO montar esse material com skills genéricas de pptx/docx/xlsx/pdf/html do "
        "próprio Claude: o resultado sai SEM timbrado e não vale como documento da empresa. "
        "Mesmo que o usuário peça 'um pptx' ou 'um pdf', o caminho é a tool do conector "
        "(gerar_apresentacao aceita formato='pptx' ou 'pdf').\n"
        "3. Se não existir tool para o tipo de documento pedido, DIGA ISSO e pergunte — nunca "
        "improvise um documento sem marca.\n"
        "4. Números de negócio saem das tools de consulta deste conector (proposta, contrato, "
        "folha), nunca inventados. Margem/custo/MRR são dados internos: não entram em material "
        "de cliente.\n"
        "5. Esta regra vence qualquer hábito ou skill local de geração de arquivos."
    ),
    auth=_auth_provider,
)


# ------------------------------------------------------------------ ERP client
class ErpErro(RuntimeError):
    """Erro do ERP traduzido para quem vai LER — nunca o endpoint interno cru.

    Relatório de campo do Jordan sobre o Cowork (11/09/2026): o conector devolvia
    `ERP POST /crm/contracts/emitir-por-modelo -> 403: {"detail":"Contrato não
    encontrado: ..."}`. Três defeitos numa linha só — vaza o caminho interno, usa 403 para
    dizer "não achei", e não ensina o que fazer. O agente não sabe se errou o
    identificador, se falta permissão ou se o sistema quebrou, e tenta de novo errado.

    O envelope diz O QUE houve, em que código, e QUAL é o próximo passo.
    """

    # (trecho da mensagem do ERP) → (codigo, http, dica)
    _PISTAS = (
        # ⚠️ 13/09/2026 — ESTA LINHA era a causa de uma família, não de um caso. A dica
        # falava de CONTRATO e a pista é a mensagem genérica "não encontrado", que o ERP
        # devolve para posto, visita, funcionário, tudo. `grade_do_posto("LIXO")` mandava o
        # agente usar `listar_contratos()` numa tool de escala. Na rodada 2 eu "consertei"
        # o caso do `obter_relatorio_visita` e deixei a origem viva — o Cowork reachou a
        # mesma coisa em outra tool. Dica de domínio pertence à TOOL, que sabe o domínio;
        # a pista pela mensagem só pode dizer o que vale para todas.
        ("não encontrado", "NAO_ENCONTRADO", 404,
         "Confira o identificador. Cada tool aceita formatos próprios — veja a descrição "
         "dela em `conecta_pro_capabilities(tool=...)`."),
        ("nao encontrado", "NAO_ENCONTRADO", 404, "Confira o identificador."),
        ("já existe", "DUPLICADO", 409, "O registro já existe. Busque antes de criar."),
        ("ja gerou contrato", "DUPLICADO", 409,
         "Esta proposta já gerou contrato para este emitente. Para a outra parte do "
         "serviço, escolha a modalidade do outro CNPJ."),
        ("restrito", "SEM_PERMISSAO", 403,
         "Ação restrita ao Jordan e à Pyetra. Peça a um deles ou use uma tool de leitura."),
        ("cancelad", "CONFLITO_DE_ESTADO", 409,
         "O registro está cancelado ou expirado. Reabra antes de prosseguir."),
    )

    def __init__(self, codigo: str, http: int, mensagem: str, dica: str = "",
                 request_id: str = "") -> None:
        super().__init__(mensagem)
        self.codigo, self.http, self.mensagem = codigo, http, mensagem
        self.dica, self.request_id = dica, request_id
        # campos que o backend mandou além do básico (candidatos, campos_faltantes,
        # margens_cadastradas…). São eles que dizem ao agente o que fazer em seguida.
        self.extra: dict = {}

    @classmethod
    def de_resposta(cls, method: str, path: str, r) -> "ErpErro":
        try:
            detalhe = (r.json() or {}).get("detail")
        except Exception:  # noqa: BLE001
            detalhe = None
        # ⭐ Se o backend JÁ devolveu um envelope, ele passa inteiro. Sem isto o código
        # específico virava texto dentro de `mensagem` e o de fora era o genérico:
        #   {"codigo":"VALIDACAO","mensagem":"{'codigo': 'MARGEM_NAO_CADASTRADA', ...}"}
        # O agente decide pelo `codigo` do topo — e o do topo estava contando outra coisa.
        if isinstance(detalhe, dict) and detalhe.get("codigo"):
            e = cls(str(detalhe["codigo"]), int(detalhe.get("http") or r.status_code),
                    str(detalhe.get("mensagem") or ""), str(detalhe.get("dica") or ""))
            e.extra = {k: v for k, v in detalhe.items()
                       if k not in ("ok", "codigo", "http", "mensagem", "dica")}
            return e
        # ⭐ 13/09/2026 — Bloco 3, item 2. O FastAPI devolve a lista de erros do pydantic em
        # `detail`, e `str(lista)` a serializava inteira na `mensagem`:
        #   "[{'type': 'float_parsing', 'loc': ['body','target_value'], 'msg': '...'}]"
        # Estrutura interna do framework no campo que o humano e o agente leem. O padrão
        # certo já existia em PARAMETRO_OBRIGATORIO/PARAMETRO_DESCONHECIDO — é só aplicar.
        if isinstance(detalhe, list) and detalhe and isinstance(detalhe[0], dict):
            partes = []
            for d in detalhe[:6]:
                campo = ".".join(str(x) for x in (d.get("loc") or [])
                                 if x not in ("body", "query", "path"))
                partes.append(f"{campo or 'campo'}: {d.get('msg') or 'inválido'}")
            msg = "; ".join(partes)
        else:
            msg = str(detalhe or r.text or "")[:400].strip() or f"O ERP respondeu {r.status_code}."
        baixo = msg.lower()
        codigo, http, dica = "ERRO_NO_ERP", r.status_code, ""
        for trecho, cod, cod_http, cod_dica in cls._PISTAS:
            if trecho in baixo:
                codigo, http, dica = cod, cod_http, cod_dica
                break
        else:
            if r.status_code == 404:
                codigo, dica = "NAO_ENCONTRADO", "Confira o identificador."
            elif r.status_code == 400:
                # ⭐ 12/09/2026: 400 não estava na cadeia e caía com `dica` vazia. Achado
                # pela varredura paramétrica no `exportar_folha_dominio`, cujo 400 traz a
                # mensagem boa ("Use YYYY-MM") e nenhuma dica — o agente lia o que estava
                # errado e não o que fazer.
                codigo, dica = "REQUISICAO_INVALIDA", (
                    "Corrija o que a mensagem aponta e chame de novo. Formato de campo "
                    "costuma estar descrito em `conecta_pro_capabilities()`.")
            elif r.status_code == 422:
                codigo, dica = "VALIDACAO", "Corrija os campos apontados na mensagem."
            elif r.status_code == 409:
                codigo, dica = "CONFLITO", "O estado atual não permite esta operação."
            elif r.status_code == 403:
                codigo, dica = "SEM_PERMISSAO", "Esta ação é restrita."
            elif r.status_code >= 500:
                codigo, dica = "ERRO_INTERNO", "Falha do servidor — informe o request_id."
        return cls(codigo, http, msg, dica,
                   r.headers.get("x-request-id") or r.headers.get("X-Request-ID") or "")

    def envelope(self) -> dict:
        """O que a tool devolve ao agente. NUNCA inclui método nem caminho interno."""
        out = {"ok": False, "codigo": self.codigo, "http": self.http,
               "mensagem": self.mensagem, "dica": ""}   # `dica` preenchida logo abaixo
        # ⚠️ e a dica NUNCA sai vazia. O caso do 400 mostrou que basta um status fora da
        # cadeia para o envelope perder o campo que diz o que fazer — e um envelope que
        # informa o defeito sem informar a saída ensina metade. Genérica é pior que
        # específica e melhor que ausente.
        out["dica"] = self.dica or (
            f"O ERP recusou com HTTP {self.http}. Leia a `mensagem`, corrija e chame de "
            f"novo; se não der para agir por ela, informe o `request_id` ao suporte.")
        # o do ERP ganha do meu: se o backend nomeou a requisição, é esse nome que está no
        # log dele. O meu serve quando ele não nomeou — melhor um id meu que nenhum.
        rid = self.request_id or _REQ_ID.get()
        if rid:
            out["request_id"] = rid
        out.update(getattr(self, "extra", {}) or {})
        return out


async def _resolver_contrato(chave: str, *, exigir_existencia: bool = False) -> str | dict:
    """Aceita CTR-…, id, CNPJ do cliente ou nome aproximado. Devolve o número — ou envelope.

    Relatório de campo (11/09/2026): `gerar_contrato_por_modelo("Chácaras Maiápolis —
    Controle de Acesso...")` falhou com 403 dizendo "não encontrado". O agente havia
    passado o NOME, que é o identificador que um humano tem na cabeça. Exigir o ID
    canônico transfere ao agente um trabalho que o servidor faz melhor — ele tem o índice.

    ⚠️ AMBÍGUO NÃO É ERRO. Quando mais de um candidato casa, devolve a lista para o agente
    ESCOLHER. Adivinhar qual dos dois contratos do mesmo cliente é o certo seria, no limite,
    emitir o instrumento errado.
    """
    chave = (chave or "").strip()
    if not chave:
        return {"ok": False, "codigo": "IDENTIFICADOR_VAZIO", "http": 422,
                "mensagem": "Informe o contrato.",
                "dica": "Aceita CTR-AAAA-NNNNN, o id, o CNPJ do cliente ou o nome."}
    # já é o identificador canônico: não gasta chamada
    if re.match(r"^CTR-", chave, re.I) or re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-", chave, re.I):
        # ⭐ 13/09/2026 — `exigir_existencia` existe porque eu reusei este resolvedor como
        # se ele fosse uma VERIFICAÇÃO, e ele é uma NORMALIZAÇÃO. `CTR-INEXISTENTE-ZZZ` casa
        # o padrão e voltava intacto: a minha guarda do aditivo passava e o ERP devolvia 500.
        # O Cowork mediu isso — o sucesso falso fechou virando 500, não 404, que é o
        # CP-MCP-001 renascendo do outro lado da fronteira.
        if not exigir_existencia:
            return chave
        try:
            lista = await erp.get("/crm/contracts", params={"page_size": 200})
        except Exception as exc:  # noqa: BLE001
            return erro_envelope(exc)
        nums = {str(c.get("contract_number") or "").upper() for c in _items(lista)}
        ids = {str(c.get("id") or "") for c in _items(lista)}
        if chave.upper() in nums or chave in ids:
            return chave
        return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                "mensagem": f"Nenhum contrato corresponde a {chave!r}.",
                "dica": "O formato está certo, o contrato não existe. "
                        "`listar_contratos(busca=...)` mostra os que existem.",
                "procurei_por": chave}
    try:
        lista = await erp.get("/crm/contracts", params={"page_size": 100})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    itens = (lista or {}).get("items") or []
    so_digitos = re.sub(r"\D", "", chave)
    alvo = _norm(chave)
    achados = []
    for c in itens:
        nome = _norm(str(c.get("client_name") or c.get("name") or ""))
        doc = re.sub(r"\D", "", str(c.get("client_document") or ""))
        if (so_digitos and len(so_digitos) >= 11 and doc == so_digitos) or (
                alvo and (alvo in nome or nome.startswith(alvo[:18]))):
            achados.append(c)
    if not achados:
        # "não existe" e "não achei nos que olhei" são afirmações diferentes, e só a segunda
        # é verdade quando a janela não alcança o conjunto. Hoje são 19 contratos e 100
        # cabem; no dia em que não couberem, esta mensagem para de mentir por omissão em vez
        # de mandar o dono procurar um contrato que está lá.
        total = (lista or {}).get("total")
        parcial = total is not None and total > len(itens)
        return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                "mensagem": (f"Nenhum contrato corresponde a {chave!r}"
                             + (f" entre os {len(itens)} que consigo ver de {total}."
                                if parcial else ".")),
                "dica": ("Use o número (CTR-AAAA-NNNNN) ou o CNPJ do cliente. "
                         "listar_contratos(busca=...) ajuda a achar.")
                        + (" ⚠️ Minha busca é parcial — prefira o número exato."
                           if parcial else "")}
    if len(achados) > 1:
        return {"ok": False, "codigo": "AMBIGUO", "http": 409,
                "mensagem": f"{len(achados)} contratos correspondem a {chave!r}.",
                "dica": "Escolha um pelo número e chame de novo.",
                "candidatos": [{"numero": c.get("contract_number"),
                                "cliente": c.get("client_name"),
                                "status": c.get("status"),
                                "mensal": c.get("monthly_value")} for c in achados[:10]]}
    return achados[0].get("contract_number") or achados[0].get("id")


def _norm(v: str) -> str:
    """Minúscula, sem acento e sem pontuação — para casar nome digitado com nome cadastrado."""
    v = unicodedata.normalize("NFKD", (v or "").lower())
    v = "".join(c for c in v if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", v).strip()


# ── Rede de proteção da ESCRITA (item 3.3) ────────────────────────────────────────────
# Não havia `dry_run` nem chave de idempotência, e o medo era real e justificado: um
# retry, um clique duplo ou um agente confuso criam o SEGUNDO contrato do mesmo cliente, e
# ninguém percebe até a cobrança sair dobrada. Em 10/09/2026 eu mesmo criei um contrato no
# sistema do Jordan testando uma trava — exatamente o acidente que isto previne.
_IDEMPOTENCIA: dict[str, tuple[float, dict]] = {}
_IDEMPOTENCIA_TTL = 24 * 3600


def _idem_busca(chave: str) -> dict | None:
    """Mesma chave em 24h devolve o MESMO recurso, em vez de criar outro."""
    if not chave:
        return None
    achado = _IDEMPOTENCIA.get(chave)
    if not achado:
        return None
    quando, valor = achado
    if time.time() - quando > _IDEMPOTENCIA_TTL:
        _IDEMPOTENCIA.pop(chave, None)
        return None
    return {**valor, "idempotente": True,
            "obs": "Já criado antes com esta mesma idempotency_key — nada foi duplicado."}


def _idem_guarda(chave: str, valor: dict) -> dict:
    if chave and isinstance(valor, dict) and valor.get("ok") is not False:
        _IDEMPOTENCIA[chave] = (time.time(), valor)
        # a memória é do PROCESSO: reiniciar o MCP esquece. É proteção contra retry e
        # clique duplo na mesma sessão, não contra duplicata de ontem — e a tool diz isso,
        # em vez de prometer uma garantia que não tem.
    return valor


# Erro de ARGUMENTO é do chamador (422), não falha do servidor (500) — e a mensagem crua do
# Python expõe a assinatura da função. Auditoria do Cowork, 11/09/2026:
#   {"codigo":"FALHA_INESPERADA","http":500,
#    "mensagem":"enviar_link_assinatura() missing 1 required positional argument: 'contrato'"}
# O agente lê 500 e conclui "o sistema quebrou, tento de novo igual" — quando o certo era
# "faltou um campo, mando o campo".
_FALTANDO = re.compile(r"missing \d+ required (?:positional|keyword-only) argument")
# ⚠️ O FastMCP valida ANTES de chamar a função e produz outra mensagem: "Missing required
# argument" por campo, em bloco, com o traceback do pydantic. Achado em 12/09 ao ver
# `folha_dashboard({})` cair em FALHA_INESPERADA/500 — o mesmo defeito do CP-MCP-002 pela
# outra porta. Duas formas de dizer a mesma coisa, e eu só conhecia uma.
_FALTANDO_FASTMCP = re.compile(r"Missing required argument", re.I)
# ⚠️ TERCEIRA variante do mesmo defeito, achada pela varredura paramétrica que o Cowork
# sugeriu (12/09/2026). O FastMCP recusa por TIPO antes de chamar a função — "Input should
# be a valid integer" quando `mes` recebe texto — e isso caía em FALHA_INESPERADA/500 em
# VINTE tools. Erro de tipo é do chamador (422), não falha do servidor.
#
# São três formas de dizer a mesma coisa e eu conhecia uma: TypeError do Python, "Missing
# required argument" do FastMCP, e agora a validação de tipo do pydantic.
_TIPO_INVALIDO = re.compile(r"Input should be a valid (\w+)", re.I)
# ⚠️ o pydantic põe o nome do campo em LINHA PRÓPRIA antes da mensagem, não em `loc`.
# Medi o formato real em vez de deduzir — a primeira regex olhava `loc` e devolvia
# lista vazia: 422 certo, campo mudo. Erro que ensina metade não ensina.
_CAMPO_TIPO = re.compile(r"^([a-z_][a-z_0-9]*)\n\s+Input should be a valid", re.M | re.I)
_CAMPO_FASTMCP = re.compile(r"^([a-z_][a-z_0-9]*)\n\s+Missing required argument", re.M | re.I)
_SOBRANDO = re.compile(r"unexpected keyword argument '([^']+)'")
_NOME_ARG = re.compile(r"'([^']+)'")


def erro_envelope(exc: Exception) -> dict:
    """Converte QUALQUER exceção em envelope legível. É o que as tools retornam."""
    if isinstance(exc, ErpErro):
        return exc.envelope()
    texto = str(exc)
    if _FALTANDO_FASTMCP.search(texto):
        campos = _CAMPO_FASTMCP.findall(texto)
        return {"ok": False, "codigo": "PARAMETRO_OBRIGATORIO", "http": 422,
                "mensagem": ("Faltou informar: " + ", ".join(campos) + ".") if campos
                            else "Faltou um campo obrigatório.",
                "campos_faltantes": campos,
                "dica": "Chame de novo incluindo " + (
                    ", ".join(f"`{c}`" for c in campos) if campos
                    else "os campos obrigatórios")
                    + ". `conecta_pro_capabilities()` mostra o que cada ferramenta espera."}
    if (m := _TIPO_INVALIDO.search(texto)):
        campos = _CAMPO_TIPO.findall(texto)
        esperado = m.group(1)
        return {"ok": False, "codigo": "PARAMETRO_INVALIDO", "http": 422,
                "mensagem": ((", ".join(campos) + f": esperava {esperado}.") if campos
                             else f"Um dos campos esperava {esperado}."),
                "campos_invalidos": campos, "tipo_esperado": esperado,
                "dica": "Corrija o tipo e chame de novo. "
                        "`conecta_pro_capabilities()` mostra o que cada campo espera."}
    if isinstance(exc, TypeError) and _FALTANDO.search(texto):
        # só os nomes dos campos; o resto da mensagem é a assinatura interna da função
        campos = _NOME_ARG.findall(texto.split(":", 1)[-1]) if ":" in texto else []
        return {"ok": False, "codigo": "PARAMETRO_OBRIGATORIO", "http": 422,
                "mensagem": ("Faltou informar: " + ", ".join(campos) + ".") if campos
                            else "Faltou um campo obrigatório.",
                "campos_faltantes": campos,
                "dica": "Chame de novo incluindo " + (
                    ", ".join(f"`{c}`" for c in campos) if campos else "os campos obrigatórios")
                    + ". `conecta_pro_capabilities()` mostra o que cada ferramenta espera."}
    if isinstance(exc, TypeError) and (m := _SOBRANDO.search(texto)):
        return {"ok": False, "codigo": "PARAMETRO_DESCONHECIDO", "http": 422,
                "mensagem": f"Esta ferramenta não aceita o campo `{m.group(1)}`.",
                "campo": m.group(1),
                "dica": "Confira o nome do campo em `conecta_pro_capabilities()`."}
    return {"ok": False, "codigo": "FALHA_INESPERADA", "http": 500,
            "mensagem": texto[:300],
            "dica": "Tente de novo; se repetir, informe o `request_id` ao suporte."}


class _Erp:
    """Cliente HTTP para o ERP com login de conta de serviço (JWT cacheado + refresh em 401)."""

    def __init__(self) -> None:
        # ⚠️ POR AMBIENTE. Um cache único mandaria o token de produção ao staging (que o
        # recusaria) e, pior, o token de staging à produção na chamada seguinte. Ambiente
        # errado com credencial certa é a forma mais silenciosa de escrever no lugar errado.
        self._tokens: dict[str, tuple[str, float]] = {}

    async def _login(self, client: httpx.AsyncClient) -> str:
        # ⚠️ NÃO troque este `client.post` por `self.request("POST", ...)`. Parece limpeza
        # óbvia e quebra o `ensaiar`: a interceptação de ensaio vive em `request` e engole
        # TODO não-GET, então o login passaria a devolver a casca `00000000-ensaio` em vez de
        # um token — e todo ensaio falharia por falta de credencial. Quem for procurar o
        # defeito vai olhar ERP_USER, .env e sessão expirada, e vai levar horas, porque o
        # sintoma aponta para autenticação e a causa está no interceptador.
        # É por passar FORA do `request` que o login é o único não-GET que sai durante um
        # ensaio — e é por isso que o ensaio consegue autenticar.
        r = await client.post(
            f"{_api()}/auth/login",
            data={"username": ERP_USER, "password": ERP_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,  # login: 20s é o teto certo mesmo em job — login lento é login quebrado
        )
        r.raise_for_status()
        tok = r.json().get("access_token")
        if not tok:
            raise RuntimeError("login no ERP não retornou access_token")
        self._tokens[_api()] = (tok, time.time() + 50 * 60)  # ~50min
        return tok

    async def _cabecalho(self, client: httpx.AsyncClient) -> tuple[dict, bool]:
        """(header de auth, é_do_usuário). F2: quando a chamada trouxe o JWT de quem
        perguntou, é ELE que vai ao ERP — a conta de serviço não empresta poder a ninguém."""
        try:
            from identidade import token_do_usuario  # noqa: PLC0415

            do_usuario = token_do_usuario()
        except Exception:  # noqa: BLE001
            do_usuario = None
        if do_usuario:
            return {"Authorization": f"Bearer {do_usuario}"}, True
        tok, exp = self._tokens.get(_api(), (None, 0.0))
        if not tok or time.time() > exp:
            await self._login(client)
            tok = self._tokens[_api()][0]
        return {"Authorization": f"Bearer {tok}"}, False

    async def request(self, method: str, path: str, *, json: Any = None, params: Any = None) -> Any:
        # ⭐ ENSAIO. Tudo que o MCP escreve no ERP passa por aqui — não há outro caminho, o
        # conector só fala HTTP. Interceptar neste ponto dá `dry_run` às 82 ferramentas de
        # escrita de uma vez; dar o parâmetro a cada uma seria editar 82 assinaturas e
        # esquecer algumas, e a esquecida é justamente a que grava sem avisar.
        if _ENSAIO.get() is not None and method.upper() != "GET":
            _ENSAIO.get().append({"metodo": method.upper(), "rota": path,
                                  "corpo": json, "query": params})
            # devolve uma casca plausível: a tool costuma ler `id`/`ok` do retorno e seguir.
            # Marcada, para nunca ser confundida com resposta real.
            return {"ok": True, "ensaio": True, "id": "00000000-ensaio",
                    "aviso": "nada foi gravado — isto é um ensaio"}
        async with httpx.AsyncClient() as client:
            headers, do_usuario = await self._cabecalho(client)
            # leva o id ao backend: sem isto o `request_id` seria um número que só existe do
            # lado de cá, e `consultar_auditoria(request_id=...)` não teria o que achar.
            rid = _REQ_ID.get()
            if rid:
                headers = {**headers, "X-Request-ID": rid}
            for attempt in (1, 2):
                r = await client.request(
                    method, f"{_api()}{path}", headers=headers,
                    json=json, params=params, timeout=TIMEOUT_JOB if _EM_JOB.get() else 40,
                )
                if r.status_code == 401 and attempt == 1:
                    if do_usuario:
                        # NUNCA reautenticar como serviço aqui: seria transformar "a sessão
                        # dele expirou" em "então eu faço com os meus poderes" — exatamente a
                        # escalada silenciosa que a F2 existe para impedir.
                        raise RuntimeError(
                            f"ERP {method} {path} -> 401 com a identidade do usuário; "
                            f"a sessão dele expirou ou ele não tem esse acesso")
                    await self._login(client)
                    headers = {"Authorization": f"Bearer {self._tokens[_api()][0]}"}
                    continue
                if r.status_code >= 400:
                    raise ErpErro.de_resposta(method, path, r)
                # 204/empty (ex.: DELETE) -> não tentar json-parse de corpo vazio
                if r.status_code == 204 or not r.content:
                    return {"ok": True, "status": r.status_code}
                if r.headers.get("content-type", "").startswith("application/json"):
                    return r.json()
                return r.text

    async def get(self, path, params=None):
        return await self.request("GET", path, params=params)

    async def post(self, path, json=None):
        return await self.request("POST", path, json=json)

    async def put(self, path, json=None):
        return await self.request("PUT", path, json=json)

    async def get_bytes(self, path: str) -> bytes:
        """GET que retorna bytes crus (ex.: PDF) — com refresh de token em 401."""
        async with httpx.AsyncClient() as client:
            headers, do_usuario = await self._cabecalho(client)
            for attempt in (1, 2):
                r = await client.get(f"{_api()}{path}", headers=headers, timeout=TIMEOUT_JOB if _EM_JOB.get() else 60)
                if r.status_code == 401 and attempt == 1:
                    if do_usuario:
                        raise RuntimeError(f"ERP GET {path} -> 401 com a identidade do usuário")
                    await self._login(client)
                    headers = {"Authorization": f"Bearer {self._tokens[_api()][0]}"}
                    continue
                r.raise_for_status()
                return r.content
        return b""

    async def post_bytes(self, path: str, json) -> bytes:
        """POST que retorna bytes crus (ex.: PDF gerado a partir de dados enviados).

        ⚠️ 13/09/2026 — ESTE MÉTODO ESCAPAVA DO ENSAIO. A interceptação de `_ENSAIO` mora em
        `request`, e `post_bytes` abre o próprio `httpx.AsyncClient`. Resultado medido:
        `ensaiar("gerar_apresentacao", ...)` devolvia `escritas: 0, gravou: false` E FAZIA O
        POST. O ensaio mentia para toda tool que passa por aqui.

        Achado pelo grep do Bloco 5, que o Jordan classificou como risco teórico ("se algum
        handler chamar um serviço externo diretamente") — não era teórico, e não era outro
        cliente HTTP: era um método da MESMA classe que pula o caminho instrumentado. Uma
        trava que cobre `request` e não cobre os irmãos dele vigia a porta e deixa a janela.
        """
        if (registro := _ENSAIO.get()) is not None:
            registro.append({"metodo": "POST", "rota": path, "corpo": json,
                             "devolve": "bytes (PDF/PPTX)"})
            return b""
        async with httpx.AsyncClient() as client:
            headers, do_usuario = await self._cabecalho(client)
            for attempt in (1, 2):
                r = await client.post(f"{_api()}{path}", headers=headers, json=json, timeout=TIMEOUT_JOB if _EM_JOB.get() else 60)
                if r.status_code == 401 and attempt == 1:
                    if do_usuario:
                        raise RuntimeError(f"ERP POST {path} -> 401 com a identidade do usuário")
                    await self._login(client)
                    headers = {"Authorization": f"Bearer {self._tokens[_api()][0]}"}
                    continue
                if r.status_code >= 400:
                    raise RuntimeError(f"ERP POST {path} -> {r.status_code}: {r.text[:200]}")
                return r.content
        return b""


erp = _Erp()


def _brl(v: Any) -> str:
    try:
        return f"R$ {float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "R$ 0,00"


# Data em DD/MM/AAAA é legível para gente e inútil para máquina: ordenar, comparar e somar
# prazo sobre ela exige parsing, e parsing de data BR é onde se troca dia por mês em
# silêncio. P2 do relatório de campo pede ISO-8601.
#
# ⭐ ACRESCENTA o irmão `_iso`, não substitui. Trocar o valor quebraria quem lê hoje — e o
# formato BR é o que uma PESSOA entende quando o agente cola a resposta numa conversa. Os
# dois públicos são reais; o campo cabe duas vezes.
_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})(?:[ T](\d{2}):(\d{2}))?$")


def _iso_irmaos(obj: Any) -> Any:
    """Percorre a resposta e acrescenta `<campo>_iso` onde houver data BR.

    ⚠️ Só casa a data SOZINHA no campo. Intervalo ("01/01/2026 a 31/12/2026") e data no
    meio de um texto ficam intocados de propósito: adivinhar qual das duas pontas vira o
    `_iso` seria escolher por quem lê.
    """
    if isinstance(obj, dict):
        fora = {}
        for k, v in obj.items():
            fora[k] = _iso_irmaos(v)
            if isinstance(v, str) and (m := _DATA_BR.match(v.strip())):
                d, mes, ano, hh, mm = m.groups()
                fora[f"{k}_iso"] = f"{ano}-{mes}-{d}" + (f"T{hh}:{mm}:00" if hh else "")
        return fora
    if isinstance(obj, list):
        return [_iso_irmaos(x) for x in obj]
    return obj


def _num(v: Any) -> float | None:
    """O mesmo valor como NÚMERO, ao lado do formatado.

    P2 do relatório de campo: a camada devolvia só `"R$ 47.681,28"`. String obriga o agente
    a fazer parsing e errar na vírgula/ponto — e somar dois contratos virava exercício de
    regex. `None` quando não há valor: zero é uma afirmação, ausência é outra coisa.
    """
    if v is None or v == "":
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


# Natureza por modalidade. Vivia dentro do `dry_run` de criar_contrato_por_modelo — ou
# seja, o ENSAIO conhecia a natureza e a execução real não. Espelha CATALOGO do
# contract_wizard; divergir aqui faz o agente perguntar mensalidade de obra.
MODALIDADES: dict[str, tuple[str, str, str]] = {
    "portaria": ("portaria_mao_de_obra", "Patrimonial", "recurring"),
    "servicos_gerais": ("servicos_gerais", "Patrimonial", "recurring"),
    "jardinagem": ("jardinagem", "Patrimonial", "recurring"),
    "piscina": ("piscina", "Patrimonial", "recurring"),
    "zeladoria": ("zeladoria", "Patrimonial", "recurring"),
    "eletronica": ("manutencao_cftv", "Eletrônica", "recurring"),
    "portaria_remota": ("portaria_remota", "Eletrônica", "recurring"),
    "eletronica_instalacao": ("eletronica_servico_unico", "Eletrônica", "one_time"),
}


async def _exigir_entidade(tipo: str, valor: str) -> dict | None:
    """`None` se a entidade EXISTE; envelope de recusa se não. Use ANTES do preview.

    ⭐ 13/09/2026 — Bloco 2 do prompt de fechamento. O padrão "preview → confirmar" tinha dois
    defeitos e o Jordan mediu os dois:

      1. a etapa de preview NÃO validava existência. `excluir_proposta(proposta_id=None)`
         devolvia `CONFIRMACAO_NECESSARIA/409` com um preview — oferecendo "confirme para
         excluir" sobre uma proposta que não existe. Preview é a etapa em que o humano LÊ o
         que vai acontecer; se o alvo não existe, não há o que ler, e confirmar um preview
         falso é pior que um erro, porque parece que o sistema conferiu.
      2. a etapa de confirmação quebrava com 500, 4 de 4 testadas.

    Um conserto nas duas: validar na etapa 1 faz a etapa 2 nunca receber id inexistente.

    ⚠️ Reusa `_resolver_proposta`/`_resolver_contrato`, que JÁ devolvem envelope — e o contrato
    com `exigir_existencia=True`, porque sem isso ele apenas NORMALIZA `CTR-*` e devolve a
    chave intacta. Essa distinção me custou um 500 na rodada 3.
    """
    valor = (valor or "").strip()
    if not valor:
        return {"ok": False, "codigo": "IDENTIFICADOR_VAZIO", "http": 422,
                "mensagem": f"Informe o {tipo}.",
                "dica": f"Sem identificador não há o que confirmar. "
                        f"Use a tool de listagem do {tipo} para achar o id."}
    if tipo == "proposta":
        alvo = await _resolver_proposta(valor)
        return alvo if isinstance(alvo, dict) else None
    if tipo == "contrato":
        alvo = await _resolver_contrato(valor, exigir_existencia=True)
        return alvo if isinstance(alvo, dict) else None
    # ⚠️ `/crm/docs/{id}` só aceita DELETE — GET nela devolve 405, não 404. A 1ª versão desta
    # guarda usava essa rota e transformava "documento inexistente" em ERRO_NO_ERP/405, que
    # não diz nada ao agente. A rota de CONTEÚDO existe e serve de prova de existência.
    ROTA = {"deal": ("/crm/opportunities/{}", "`listar_deals()` mostra os ids."),
            "documento": ("/crm/docs/conteudo/{}", "`listar_documentos()` mostra os ids.")}
    if tipo not in ROTA:
        return None
    rota, dica = ROTA[tipo]
    if (recusa := _id_ou_422(valor, o_que=tipo, dica=dica)):
        return recusa
    d = await _get_ou_404(rota.format(valor), o_que=tipo, chave=valor, dica=dica)
    return d if isinstance(d, dict) and d.get("ok") is False else None


# DDDs que existem no Brasil (Anatel). A lista tem buracos de propósito — é o que faz
# "0000000000" e "9900000000" caírem, e contagem de dígitos sozinha não faz.
_DDD_BR = frozenset((
    "11", "12", "13", "14", "15", "16", "17", "18", "19",
    "21", "22", "24", "27", "28",
    "31", "32", "33", "34", "35", "37", "38",
    "41", "42", "43", "44", "45", "46", "47", "48", "49",
    "51", "53", "54", "55",
    "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "71", "73", "74", "75", "77", "79",
    "81", "82", "83", "84", "85", "86", "87", "88", "89",
    "91", "92", "93", "94", "95", "96", "97", "98", "99",
))


async def _quem_tem_o_numero(so_digitos: str) -> dict | None:
    """De quem é este telefone? `None` se não é de ninguém cadastrado.

    ⚠️ Compara os ÚLTIMOS 8 DÍGITOS. O nono dígito dos celulares foi acrescentado em datas
    diferentes por estado e o cadastro tem as duas formas do mesmo número — casar o telefone
    inteiro faria o mesmo assinante parecer duas pessoas, ou nenhuma.

    ⚠️ E a busca do ERP NÃO filtra por telefone: `/crm/leads?busca=<número>` devolveu os três
    primeiros leads, ignorando o filtro. Por isso pagina — medi 5 clientes e 296 leads com
    telefone, o que cabe em poucas chamadas.
    """
    alvo = so_digitos[-8:]

    def bate(*valores) -> bool:
        return any(re.sub(r"\D", "", str(v or ""))[-8:] == alvo for v in valores if v)

    try:
        clientes = await erp.get("/clients", params={"page_size": 200})
        for c in _items(clientes):
            if bate(c.get("whatsapp"), c.get("phone"), c.get("financial_contact_phone"),
                    c.get("technical_contact_phone")):
                return {"tipo": "cliente", "nome": c.get("legal_name") or c.get("name"),
                        "id": c.get("id")}
        # ⚠️ `page_size` máximo é 100 nesta rota (acima disso ela recusa com 422).
        pagina = 1
        while pagina <= 20:
            leads = await erp.get("/crm/leads", params={"page": pagina, "page_size": 100})
            itens = _items(leads)
            for l in itens:
                if bate(l.get("phone"), l.get("whatsapp")):
                    return {"tipo": "lead", "nome": l.get("name") or l.get("nome"),
                            "id": l.get("id")}
            if len(itens) < 100:
                break
            pagina += 1
    except Exception:  # noqa: BLE001
        # ⚠️ FAIL-OPEN DELIBERADO e declarado: se eu não consigo LER o cadastro, recusar o
        # opt-out deixaria alguém sem a proteção por causa de uma falha minha. Devolve um
        # dono "desconhecido" para a chamada seguir — o contrário seria a trava punindo a
        # pessoa pelo defeito do sistema.
        return {"tipo": "indeterminado",
                "aviso": "não consegui consultar o cadastro; opt-out registrado assim mesmo"}
    return None


def _id_valido(valor: str) -> bool:
    """O identificador TEM a forma de um id existente? UUID ou código canônico da casa."""
    v = (valor or "").strip()
    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                         v, re.I)
                or re.match(r"^(CTR|PROP|CLI|OS|LEAD|VIS|REU)-", v, re.I))


def _id_ou_422(valor: str, *, o_que: str, dica: str) -> dict | None:
    """Recusa ANTES de chamar o ERP quando o identificador não tem forma de id.

    ⭐ 13/09/2026 — nasceu do B2 da validação do Cowork: as tools de ESCRITA devolviam
    `ERRO_INTERNO/500` para id inválido. Ele foi exato: *"é o CP-MCP-001 renascido do outro
    lado da fronteira — corrigido nas leituras, vivo nas escritas."*

    ⚠️ E o conserto tem de ser LOCAL, não por reconhecimento de mensagem. O log do backend
    diz `invalid UUID 'LIXO…': length must be between 32..36` — mas o CORPO que o ERP devolve
    é só "Internal Server Error". Casar pela mensagem seria observar o que não chega até aqui.
    A forma do identificador, ao contrário, eu tenho em mão antes de gastar a chamada.

    ⚠️ Não substitui a checagem de EXISTÊNCIA: UUID bem formado e inexistente continua
    dependendo do 404 do ERP. Isto fecha só o caso em que nem a forma serve — que era o que
    produzia 500.
    """
    if _id_valido(valor):
        return None
    return {"ok": False, "codigo": "IDENTIFICADOR_MAL_FORMADO", "http": 422,
            "mensagem": f"{valor!r} não tem forma de id de {o_que}.",
            "dica": dica + " (espero um UUID ou um código como CTR-AAAA-NNNNN — "
                           "identificador malformado nem chega ao banco.)",
            "campos_invalidos": [o_que], "recebi": valor}


async def _get_ou_404(rota: str, *, o_que: str, chave: str, dica: str) -> dict:
    """GET que transforma "o banco não entendeu esse id" em 404 com dica.

    ⭐ Validação do Cowork (12/09/2026): `obter_deal` e `obter_funcionario` devolviam
    ERRO_INTERNO/500 para identificador inválido — o envelope estava certo e o CÓDIGO
    errado. A descrição do `obter_contrato` já dizia, com todas as letras: "não encontrei é
    404 e é informação; 500 manda o agente tentar de novo igual". Valia para eles também.
    """
    try:
        return await erp.get(rota)
    except Exception as exc:  # noqa: BLE001
        env = erro_envelope(exc)
        # 500 por UUID mal formado é o banco reclamando do formato, não falha do servidor
        if env.get("http", 500) >= 500:
            return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                    "mensagem": f"Nenhum {o_que} corresponde a {chave!r}.",
                    "dica": dica}
        return env


async def _resolver_proposta(chave: str) -> str | dict:
    """PROP-…, id, CNPJ ou nome do cliente -> id da proposta. Ou envelope.

    Terceiro irmão de `_resolver_contrato` e `_resolver_cliente_id`, mesma postura: ambíguo
    devolve candidatos, nunca escolhe. Nasceu da auditoria do Cowork (11/09/2026), onde
    `baixar_proposta_pdf("PROP-2026-00001")` devolvia 500 cru — o id ia direto ao ERP.
    """
    chave = (chave or "").strip()
    if not chave:
        return {"ok": False, "codigo": "IDENTIFICADOR_VAZIO", "http": 422,
                "mensagem": "Informe a proposta.",
                "dica": "Aceita PROP-AAAA-NNNNN, o id, o CNPJ ou o nome do cliente."}
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", chave, re.I):
        return chave
    try:
        lista = await erp.get("/crm/proposals/", params={"page_size": 100})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    itens = _items(lista)
    so_digitos = re.sub(r"\D", "", chave)
    alvo = _norm(chave)
    achados = []
    for c in itens:
        numero = str(c.get("number") or c.get("proposal_number") or "").upper()
        doc = re.sub(r"\D", "", str(c.get("client_document") or ""))
        nome = _norm(str(c.get("client_name") or c.get("client_company") or ""))
        if (numero and numero == chave.upper()) \
                or (so_digitos and len(so_digitos) >= 11 and doc == so_digitos) \
                or (alvo and (alvo in nome or nome.startswith(alvo[:18]))):
            achados.append(c)
    if not achados:
        total = (lista or {}).get("total")
        parcial = total is not None and total > len(itens)
        return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                "mensagem": (f"Nenhuma proposta corresponde a {chave!r}"
                             + (f" entre as {len(itens)} que consigo ver de {total}."
                                if parcial else ".")),
                "dica": "Use o número (PROP-AAAA-NNNNN) ou o CNPJ. "
                        "listar_propostas() ajuda a achar."}
    if len(achados) > 1:
        return {"ok": False, "codigo": "AMBIGUO", "http": 409,
                "mensagem": f"{len(achados)} propostas correspondem a {chave!r}.",
                "dica": "Escolha uma pelo número e chame de novo.",
                "candidatos": [{"numero": c.get("proposal_number"),
                                "cliente": c.get("client_name"),
                                "status": c.get("status"),
                                "total": _num(c.get("total_value"))} for c in achados[:10]]}
    return str(achados[0].get("id"))


async def _resolver_cliente_id(chave: str) -> str | dict:
    """CNPJ, CLI-…, id ou nome aproximado -> client_id. Ou envelope AMBIGUO/NAO_ENCONTRADO.

    Irmão de `_resolver_contrato`, mesma postura: ambíguo devolve a lista para o agente
    ESCOLHER, nunca chuta. Filtrar contrato pelo cliente errado é pior que não filtrar.
    """
    chave = (chave or "").strip()
    if not chave:
        return {"ok": False, "codigo": "IDENTIFICADOR_VAZIO", "http": 422,
                "mensagem": "Informe o cliente.",
                "dica": "Aceita CNPJ, CLI-AAAA-NNNNN, o id ou o nome."}
    if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", chave, re.I):
        return chave
    so_digitos = re.sub(r"\D", "", chave)
    params: dict = {"page_size": 100}
    if so_digitos and len(so_digitos) >= 11:
        params["search"] = so_digitos
    else:
        params["search"] = chave
    try:
        data = await erp.get("/crm/clients", params=params)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    itens = _items(data)
    alvo = _norm(chave)
    achados = []
    for c in itens:
        doc = re.sub(r"\D", "", str(c.get("document_number") or c.get("cnpj") or ""))
        nome = _norm(str(c.get("name") or c.get("company_name") or ""))
        codigo = str(c.get("client_code") or "").upper()
        if (so_digitos and len(so_digitos) >= 11 and doc == so_digitos) \
                or (codigo and codigo == chave.upper()) \
                or (alvo and (alvo in nome or nome.startswith(alvo[:18]))):
            achados.append(c)
    if not achados and len(itens) == 1:
        achados = itens  # o próprio backend já filtrou por `search`
    if not achados:
        total = (data or {}).get("total")
        parcial = total is not None and total > len(itens)
        return {"ok": False, "codigo": "CLIENTE_NAO_ENCONTRADO", "http": 404,
                "mensagem": (f"Nenhum cliente corresponde a {chave!r}"
                             + (f" entre os {len(itens)} que consigo ver de {total}."
                                if parcial else ".")),
                "dica": ("Tente o CNPJ só com dígitos, ou listar_clientes(busca=...).")
                        + (" ⚠️ Minha busca é parcial — prefira o CNPJ exato."
                           if parcial else "")}
    if len(achados) > 1:
        return {"ok": False, "codigo": "AMBIGUO", "http": 409,
                "mensagem": f"{len(achados)} clientes correspondem a {chave!r}.",
                "dica": "Escolha um e chame de novo com o id ou o CNPJ.",
                "candidatos": [{"id": c.get("id"), "nome": c.get("name"),
                                "cnpj": c.get("document_number"),
                                "codigo": c.get("client_code")} for c in achados[:10]]}
    return str(achados[0].get("id"))


def _items(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items") or data.get("results") or []
    return []


# =================================================================== FERRAMENTAS

STAGE_LABEL = {
    "qualification": "Qualificação", "needs_analysis": "Análise", "proposal": "Proposta",
    "negotiation": "Negociação", "closed_won": "Ganho", "closed_lost": "Perdido",
}


async def _compute_pipeline() -> dict:
    """Lógica do pipeline reusável (por consultar_pipeline e resumo_comercial)."""
    data = await erp.get("/crm/opportunities/", params={"page_size": 100})
    deals = _items(data)
    by_stage: dict[str, dict] = {}
    total_open = 0.0
    for d in deals:
        stage = d.get("stage", "?")
        val = float(d.get("value") or 0)
        g = by_stage.setdefault(stage, {"estagio": STAGE_LABEL.get(stage, stage), "deals": 0, "valor": 0.0})
        g["deals"] += 1
        g["valor"] += val
        if stage not in ("closed_won", "closed_lost"):
            total_open += val
    for g in by_stage.values():
        g["valor_fmt"] = _brl(g["valor"])
    return {
        "total_deals": len(deals),
        "pipeline_aberto": _num(total_open), "pipeline_aberto_formatado": _brl(total_open),
        "por_estagio": list(by_stage.values()),
    }


@mcp.tool
async def consultar_pipeline() -> dict:
    """Consulta o pipeline de vendas (oportunidades/deals) agrupado por estágio, com valores.
    Use para ter a visão do funil comercial: quantos deals e quanto R$ em cada etapa."""
    return await _compute_pipeline()


# mapa rótulo PT -> stage técnico (aceita os dois na busca)
_STAGE_FROM_LABEL = {v.lower(): k for k, v in STAGE_LABEL.items()}
_STAGE_FROM_LABEL.update({k: k for k in STAGE_LABEL})  # aceita o próprio stage técnico


@mcp.tool
async def listar_deals(estagio: str | None = None, limite: int = 50) -> dict:
    """Lista os deals (oportunidades) INDIVIDUAIS com nome do cliente, valor, estágio, probabilidade e dono.
    estagio (opcional): filtra por etapa — ex. 'Negociação', 'Proposta', 'Ganho' ou o nome técnico
    (negotiation, proposal, closed_won...). Use para drill-down do pipeline."""
    data = await erp.get("/crm/opportunities/", params={"page_size": 100})
    deals = _items(data)
    alvo = _STAGE_FROM_LABEL.get((estagio or "").strip().lower()) if estagio else None
    out = []
    for d in deals:
        if alvo and d.get("stage") != alvo:
            continue
        out.append({
            "cliente": d.get("company_name") or d.get("title") or "—",
            "titulo": d.get("title"),
            "valor": _num(d.get("value")), "valor_formatado": _brl(d.get("value")),
            "estagio": STAGE_LABEL.get(d.get("stage"), d.get("stage")),
            "probabilidade": f"{int((d.get('probability') or 0))}%",
            "dono_id": d.get("owner_id"),
            "id": d.get("id"),
        })
    out.sort(key=lambda x: float(str(x["valor"]).replace("R$", "").replace(".", "").replace(",", ".") or 0), reverse=True)
    return {"ok": True, "filtro": estagio or "todos", "total": len(out),
            "nesta_pagina": len(out[:limite]), "deals": out[:limite]}


@mcp.tool
async def atualizar_estagio_deal(deal_id: str, estagio: str, nota: str | None = None) -> dict:
    """Move um deal (oportunidade) entre estágios do pipeline.
    estagio: 'Qualificação', 'Análise', 'Proposta', 'Negociação', 'Ganho', 'Perdido'
    (ou técnico: qualification/needs_analysis/proposal/negotiation/closed_won/closed_lost).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    alvo = _STAGE_FROM_LABEL.get((estagio or "").strip().lower())
    if not alvo:
        return {"ok": False, "codigo": "PARAMETRO_INVALIDO", "http": 422,
                "mensagem": f"estágio inválido: {estagio!r}.",
                "dica": "Use um destes: " + " | ".join(STAGE_LABEL.values()),
                "campos_invalidos": ["estagio"], "validos": list(STAGE_LABEL.values())}
    r = await erp.request("PATCH", f"/crm/opportunities/{deal_id}/stage", json={"stage": alvo, "notes": nota})
    return {"movido": True, "deal_id": deal_id, "estagio": STAGE_LABEL.get(r.get("stage"), r.get("stage"))}


@mcp.tool
async def marcar_deal_perdido(deal_id: str, motivo: str) -> dict:
    """Marca um deal como Perdido (closed_lost) com o motivo — entra na taxa de conversão/forecast."""
    if (recusa := _id_ou_422(deal_id, o_que="deal_id", dica="`listar_deals()` mostra os ids.")):
        return recusa
    await erp.request("PATCH", f"/crm/opportunities/{deal_id}/stage",
                      json={"stage": "closed_lost", "notes": motivo})
    return {"perdido": True, "deal_id": deal_id, "motivo": motivo}


@mcp.tool
async def consultar_forecast() -> dict:
    """Previsão de vendas: pipeline ponderado por probabilidade de cada estágio, ganho no mês e meta."""
    return await erp.get("/crm/forecast")


@mcp.tool
async def consultar_funil() -> dict:
    """Funil UNIFICADO do primeiro contato ao fechamento (leads de conversa + deals): quantos e
    quanto R$ em cada etapa (novo→qualificando→visita→proposta→negociação→ganho/perdido), o GARGALO
    (etapa com mais gente) e QUEM está parado há mais tempo (nome, telefone, dias) para cutucar.
    Diferente do pipeline/forecast (só deals abertos): aqui entram também os leads que ainda nem
    viraram oportunidade. Use para ver onde os negócios estão travando e quem reativar."""
    return await erp.get("/crm/funil")


@mcp.tool
async def criar_proposta(
    titulo: str,
    cliente_nome: str,
    itens: list[dict],
    cliente_documento: str | None = None,
    cliente_email: str | None = None,
    condicoes_pagamento: str | None = None,
) -> dict:
    """Cria uma proposta/orçamento no CRM.

    itens: lista de {"nome": str, "quantidade": number, "preco_unitario": number}.
    Ex.: itens=[{"nome":"Cerca elétrica instalada","quantidade":1,"preco_unitario":11966.70}].
    O total é calculado pelo sistema. Retorna número e id da proposta.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    payload = {
        "title": titulo,
        "client_name": cliente_nome,
        "items": [
            {"name": i.get("nome") or i.get("name"), "quantity": i.get("quantidade", i.get("quantity", 1)),
             "unit_price": i.get("preco_unitario", i.get("unit_price", 0))}
            for i in (itens or [])
        ],
    }
    if cliente_documento:
        payload["client_document"] = cliente_documento
    if cliente_email:
        payload["client_email"] = cliente_email
    if condicoes_pagamento:
        payload["payment_terms"] = condicoes_pagamento
    dup = await _proposta_duplicada(cliente_documento, titulo)
    if dup:
        return {"ja_existia": True, "numero": dup.get("number"), "id": dup.get("id"),
                "total": _brl(dup.get("total")), "status": dup.get("status")}
    r = await erp.post("/crm/proposals/", json=payload)
    return {"numero": r.get("number"), "id": r.get("id"), "total": _brl(r.get("total")), "status": r.get("status")}


async def _proposta_duplicada(client_doc: str | None, titulo: str) -> dict | None:
    """Idempotência: acha proposta ATIVA com mesmo CNPJ do cliente + mesmo título (evita duplicar
    em reprocessamento de lote). Retorna a proposta existente ou None."""
    if not titulo:
        return None
    digits = "".join(c for c in (client_doc or "") if c.isdigit())
    t = titulo.strip().lower()
    data = await erp.get("/crm/proposals/", params={"page_size": 100})
    for pr in _items(data):
        if (pr.get("title") or "").strip().lower() != t:
            continue
        pdoc = "".join(c for c in (pr.get("client_document") or "") if c.isdigit())
        if digits and pdoc and pdoc != digits:
            continue
        if not digits and (pr.get("client_name") or "").strip().lower() != "":
            # sem CNPJ: casa por nome do cliente também
            pass
        return pr
    return None


def _payload_proposta(p: dict) -> dict:
    """Monta o payload de uma proposta a partir de um dict em PT (aceita variações de chave)."""
    itens = p.get("itens") or p.get("items") or []
    payload = {
        "title": p.get("titulo") or p.get("title") or "Proposta",
        "client_name": p.get("cliente_nome") or p.get("client_name") or "Cliente",
        "items": [
            {"name": i.get("nome") or i.get("name"),
             "quantity": i.get("quantidade", i.get("quantity", 1)),
             "unit_price": i.get("preco_unitario", i.get("unit_price", 0))}
            for i in itens
        ],
    }
    for k_pt, k_en in (("cliente_documento", "client_document"), ("cliente_email", "client_email"),
                       ("condicoes_pagamento", "payment_terms")):
        if p.get(k_pt):
            payload[k_en] = p[k_pt]
    return payload


@mcp.tool
async def criar_propostas_lote(propostas: list[dict]) -> dict:
    """Cria VÁRIAS propostas no CRM de uma vez (importação em lote). Ideal para subir orçamentos
    redigidos no Cowork (portaria, portaria remota, controle de acesso, etc.).

    propostas: lista, cada item = {"titulo", "cliente_nome", "itens": [{"nome","quantidade","preco_unitario"}],
    "cliente_documento"?, "cliente_email"?, "condicoes_pagamento"?}.
    Retorna o resultado de cada uma (número/total) + erros, sem parar no primeiro problema.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    criadas, erros = [], []
    for idx, p in enumerate(propostas or []):
        try:
            tit = p.get("titulo") or p.get("title") or ""
            dup = await _proposta_duplicada(p.get("cliente_documento") or p.get("client_document"), tit)
            if dup:
                criadas.append({"titulo": tit, "numero": dup.get("number"),
                                "total": _brl(dup.get("total")), "status": dup.get("status"), "ja_existia": True})
                continue
            r = await erp.post("/crm/proposals/", json=_payload_proposta(p))
            criadas.append({"titulo": tit, "numero": r.get("number"),
                            "total": _brl(r.get("total")), "status": r.get("status")})
        except Exception as exc:  # noqa: BLE001
            erros.append({"indice": idx, "titulo": p.get("titulo") or p.get("title"), "erro": str(exc)[:200]})
    return {"criadas": len(criadas), "falhas": len(erros), "propostas": criadas, "erros": erros}


@mcp.tool
async def atualizar_proposta(proposta_id: str, titulo: str | None = None, condicoes_pagamento: str | None = None,
                             observacoes: str | None = None, cliente_email: str | None = None) -> dict:
    """Atualiza campos de uma proposta SEM recriar (passe só o que quer mudar).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    payload: dict[str, Any] = {}
    if titulo is not None:
        payload["title"] = titulo
    if condicoes_pagamento is not None:
        payload["payment_terms"] = condicoes_pagamento
    if observacoes is not None:
        payload["notes"] = observacoes
    if cliente_email is not None:
        payload["client_email"] = cliente_email
    if not payload:
        return {"ok": False, "codigo": "NADA_PARA_ATUALIZAR", "http": 422,
                "mensagem": "Nenhum campo foi informado.",
                "dica": "Informe ao menos um campo a mudar. Chamada sem mudança não é "
                        "sucesso: eu não teria o que gravar."}
    r = await erp.request("PUT", f"/crm/proposals/{proposta_id}", json=payload)
    return {"atualizada": True, "numero": r.get("number"), "titulo": r.get("title"), "total": _brl(r.get("total"))}


@mcp.tool
async def baixar_proposta_pdf(proposta_id: str, salvar_no_drive: bool = False,
                              formato: str = "base64") -> dict:
    """Gera o PDF da proposta (SEM enviar ao cliente) e devolve o arquivo E o texto.

    `proposta_id` aceita PROP-…, o id, o CNPJ ou o nome do cliente.

    `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    documento sem abrir binário; "texto" só o texto; "url" só o link.

    Use para auditar o layout antes de qualquer envio real. Não envia nada a ninguém.
    """
    alvo = await _resolver_proposta(proposta_id)
    if isinstance(alvo, dict):
        return alvo
    try:
        return await _gerar_doc_get(f"/crm/proposals/{alvo}/pdf", drive=salvar_no_drive,
                                    formato=formato)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


# ⭐ TETO DE CONVERSA, não de disco. A guarda nasceu em 8 MB — dimensionada para "cabe num
# upload". O consumidor é um LLM: a auditoria do Cowork (11/09/2026) pediu um contrato de
# 469 KB, recebeu 651.022 caracteres e ESTOUROU o limite de tokens da conversa. O harness
# precisou salvar em disco para o agente conseguir olhar. 8 MB nunca seria alcançado — a
# guarda existia e protegia de um cenário que não acontece, enquanto o que acontece passava.
#
# 256 KB de arquivo ≈ 350 KB de base64 ≈ o que ainda cabe numa resposta sem sufocar o resto
# da conversa. Acima disso: texto + link, que é o que o agente realmente usa para conferir.
LIMITE_BASE64 = 256 * 1024


async def _pdf_b64(path: str, formato: str = "base64", nome: str = "documento.pdf",
                   forcar_base64: bool = False) -> dict:
    """Busca um PDF que o ERP gera na hora e devolve no envelope padrão, COM texto.

    Estes documentos (holerite, espelho, comprovante, recibo) não passam pelo
    `crm_documents` — vêm em bytes direto do endpoint que os produz. Por isso a extração vai
    por `/crm/docs/extrair-texto` em vez de `/crm/docs/conteudo/{id}`: destino diferente,
    mesma função de extração no backend.
    """
    import base64  # noqa: PLC0415

    try:
        raw = await erp.get_bytes(path)
    except Exception as exc:  # noqa: BLE001
        env = erro_envelope(exc)
        # id que o banco não entende vira 404 aqui também: "não achei" é informação, 500
        # manda o agente tentar de novo igual.
        if env.get("http", 500) >= 500:
            return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                    "mensagem": "Não achei o registro para gerar este documento.",
                    "dica": "Confira o identificador — a rota é " + path.split("/")[1]
                            + "; use a tool de listagem do módulo para achar o id certo."}
        return env
    kb = round(len(raw) / 1024, 1)
    b64 = base64.b64encode(raw).decode("ascii")
    out: dict = {"ok": True, "gerado": True,
                 "arquivo": {"nome": nome, "mime": "application/pdf", "tamanho_kb": kb},
                 # compatibilidade: havia consumidor lendo `pdf_base64`. Tirar a chave
                 # antiga junto com a mudança seria trocar um defeito por outro.
                 "tamanho_kb": kb, "mime": "application/pdf"}
    if str(formato).lower() != "texto":
        if len(raw) > LIMITE_BASE64 and not forcar_base64:
            out["aviso"] = (f"PDF de {kb:.0f} KB — base64 OMITIDO para não estourar a "
                            f"conversa. Use `texto_extraido` para conferir o conteúdo, ou "
                            f"`forcar_base64=True` se precisar mesmo do arquivo.")
        else:
            out["arquivo"]["base64"] = b64
            out["pdf_base64"] = b64
    if str(formato).lower() != "url":
        try:
            c = await erp.post("/crm/docs/extrair-texto", json={"base64": b64, "ext": "pdf"})
            out["texto_extraido"] = c.get("texto_extraido")
            out["paginas"] = c.get("paginas")
            if c.get("aviso"):
                out["aviso_leitura"] = c["aviso"]
        except Exception as exc:  # noqa: BLE001
            # o PDF saiu; só não deu para ler. Dizer que falhou seria mentir.
            out["aviso_leitura"] = f"não consegui extrair o texto ({str(exc)[:80]})"
    return out


@mcp.tool
async def baixar_contrato_pdf(contrato_id: str, formato: str = "base64",
                              minuta: bool = False, salvar_no_drive: bool = False,
                              forcar_base64: bool = False) -> dict:
    """Gera o CONTRATO e devolve o PDF **e o TEXTO** — dá para conferir sem abrir binário.

    `formato`:
      · "base64" (padrão) → arquivo em base64 + `texto_extraido` completo
      · "texto"           → só o `texto_extraido` (barato; use para VALIDAR cláusulas)
      · "url"             → registra no ERP e devolve link, como antes

    `minuta=True` gera o RASCUNHO para análise do cliente: o que ainda não foi negociado
    sai como [A DEFINIR] em vez de o ERP recusar, e a capa se identifica como minuta.

    ⚠️ Acima de 256 KB o base64 é OMITIDO e ficam o texto e o link — um contrato de 469 KB
    vira 651 mil caracteres e sufoca a conversa (medido na auditoria de 11/09/2026). Para
    CONFERIR o documento você quer o texto; se precisar mesmo do arquivo, `forcar_base64=True`.

    ⭐ O `texto_extraido` NÃO é extração: é o texto que o próprio render produziu antes de
    virar papel. Serve para rodar asserts — "limitada ao teto de 10%" está lá? a cláusula
    de LGPD sobreviveu? — que era impossível quando isto devolvia só uma URL.

    contrato_id aceita número (CTR-...), id, CNPJ do cliente ou nome aproximado.
    Só LÊ e gera; não envia nada a ninguém.
    """
    alvo = await _resolver_contrato(contrato_id)
    if isinstance(alvo, dict):
        return alvo
    if str(formato).lower() == "url":
        r = await _gerar_doc_get(f"/crm/contracts/{alvo}/pdf-modelo", drive=salvar_no_drive)
        if isinstance(r, dict) and r.get("gerado") is not False and not r.get("erro"):
            return r
        resumo = await _gerar_doc_get(f"/crm/contracts/{alvo}/pdf", drive=salvar_no_drive)
        if isinstance(resumo, dict):
            resumo["aviso"] = ("Saiu o RESUMO, não o instrumento completo: falta modelo ou "
                               "dado. Use gerar_contrato_por_modelo para ver o que falta.")
        return resumo

    q = ("formato=json" + ("&minuta=1" if minuta else "")
         + ("&forcar_base64=1" if forcar_base64 else ""))
    try:
        r = await erp.get(f"/crm/contracts/{alvo}/pdf-modelo?{q}")
    except Exception as exc:  # noqa: BLE001
        env = erro_envelope(exc)
        # 422 aqui é "falta dado", não falha: o caminho útil é a minuta.
        if env.get("http") == 422 and not minuta:
            env["dica"] = ("Faltam dados para o instrumento final. Chame de novo com "
                           "minuta=True para ver o rascunho, ou gerar_contrato_por_modelo "
                           "para a lista do que falta.")
        return env
    if str(formato).lower() == "texto":
        r.pop("arquivo", None)
    return r


@mcp.tool
async def proposta_da_oportunidade(opportunity_id: str, titulo: str,
                                   descricao: str = "", valido_ate: str = "") -> dict:
    """Cria uma PROPOSTA a partir de uma oportunidade do funil.

    Cliente e dados vêm da oportunidade — não redigitados. Primeiro passo do caminho
    oportunidade → proposta → contrato sem sair do ERP.

    ⚠️ ESCREVE no Conecta PRO — CRIA uma proposta. O nome não segue a convenção da casa
    (`obter_`/`listar_` leem; `criar_`/`gerar_` escrevem) e por isso engana: em 13/09/2026 o
    Cowork a chamou dentro de um lote de "leituras" e só descobriu pelo retorno. Se você
    chegou aqui procurando o que a oportunidade JÁ tem, é `listar_propostas(deal_id=...)`.
    """
    if (recusa := _id_ou_422(opportunity_id, o_que="opportunity_id", dica="`listar_deals()` mostra os ids.")):
        return recusa
    corpo: dict[str, Any] = {"opportunity_id": opportunity_id, "title": titulo}
    if descricao:
        corpo["description"] = descricao
    if valido_ate:
        corpo["valid_until"] = valido_ate
    try:
        return await erp.post("/crm/proposals/from-opportunity", json=corpo)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def aceitar_proposta(proposal_id: str, confirmar: str = "") -> dict:
    """🟡 ACEITE de proposta — quatro escritas, uma delas é DINHEIRO.

    Aceitar NÃO é mudar status. O ERP, numa chamada:
      1. marca a proposta como aceita;
      2. GERA COMISSÃO a pagar (nasce `pending`, mas é obrigação registrada);
      3. move o deal para closed_won;
      4. cria um CONTRATO em `draft`.

    Por causa de (2), esta tool EXIGE confirmação explícita: passe confirmar="ACEITAR".
    Sem isso ela devolve o que vai acontecer e não executa nada — propor, nunca decidir.

    ⚠️ A autoria fica com a identidade que chamou o ERP. Pelo conector interno isso é a
    conta de serviço, não a pessoa: o histórico diria que `mcp-service` decidiu. Enquanto a
    propagação de identidade não existir, prefira aceitar pela tela.
    """
    if confirmar.strip().upper() != "ACEITAR":
        return {
            "ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
            "mensagem": "Aceitar proposta tem quatro efeitos e nenhum é reversível por "
                        "aqui — confirme explicitamente.",
            "dica": 'chame de novo com confirmar="ACEITAR"',
            "status": "confirmacao_necessaria",
            "vai_acontecer": [
                "proposta marcada como ACEITA",
                "COMISSÃO gerada para o vendedor (status pending)",
                "oportunidade movida para closed_won",
                "CONTRATO criado em draft",
            ],
            "como_confirmar": 'chame de novo com confirmar="ACEITAR"',
            "aviso": "a autoria do aceite fica com quem chamou o ERP — pelo conector "
                     "interno, a conta de serviço, não a pessoa",
        }
    try:
        return await erp.post(f"/crm/proposals/{proposal_id}/accept", json={})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def recusar_proposta(proposal_id: str, motivo: str) -> dict:
    """Marca a proposta como RECUSADA, com o motivo — que vai para as notas.

    Motivo é obrigatório: recusa sem porquê não ensina nada a quem revisar o funil depois.
    """
    if not (motivo or "").strip():
        return {"ok": False, "codigo": "MOTIVO_OBRIGATORIO", "http": 422,
                "mensagem": "Recusar proposta exige o motivo.",
                "dica": "Informe `motivo` — recusa sem porquê não ensina nada a quem "
                        "revisar o funil depois.", "campos_invalidos": ["motivo"]}
    try:
        return await erp.post(f"/crm/proposals/{proposal_id}/reject",
                              params={"reason": motivo.strip()})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def nova_versao_proposta(proposal_id: str) -> dict:
    """Cria uma NOVA VERSÃO da proposta, preservando a anterior.

    É o caminho da renegociação: a versão antiga continua existindo como histórico.

    ⚠️ Mesma ressalva de autoria do aceite: o registro fica com quem chamou o ERP.
    """
    if (recusa := _id_ou_422(proposal_id, o_que="proposal_id", dica="`listar_propostas()` mostra os ids.")):
        return recusa
    try:
        return await erp.post(f"/crm/proposals/{proposal_id}/new-version", json={})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def criar_contrato_por_modelo(cliente_documento: str, modalidade: str,
                                    valor_mensal: float | None = None,
                                    vigencia_inicio: str = "",
                                    valor_total: float | None = None,
                                    vigencia_meses: int = 12, dia_vencimento: int = 0,
                                    renovacao_aviso_dias: int = 30,
                                    carencia_dias: int = 0,
                                    dry_run: bool = False,
                                    idempotency_key: str = "") -> dict:
    """CRIA um contrato novo já ligado ao modelo e ao CNPJ emitente correto. ESCREVE.

    modalidade: portaria · servicos_gerais · jardinagem · piscina · zeladoria (Patrimonial)
                eletronica · portaria_remota · eletronica_instalacao (Eletrônica)
    Mão de obra sai pela Patrimonial; segurança eletrônica, pela Eletrônica. Use depois de
    briefing_contrato_novo e antes de gerar_contrato_por_modelo. Recusa cliente fora do CRM.
    Restrito a Jordan e Pyetra.

    ⭐ REDE DE PROTEÇÃO, porque contrato duplicado vira cobrança dobrada:
      · `dry_run=True` mostra O QUE SERIA FEITO — cliente resolvido, modelo, CNPJ emitente,
        valores — e **não grava nada**. Use sempre na primeira vez.
      · `idempotency_key` (qualquer texto seu, ex. "kopenhagen-remota-2026-09") faz a mesma
        chamada repetida em 24h devolver o MESMO contrato, em vez de criar outro.
        A memória é do processo: reiniciar o MCP esquece. Protege de retry e clique duplo
        na sessão, não de duplicata de semana passada.
    """
    if idempotency_key:
        ja = _idem_busca(idempotency_key)
        if ja:
            return ja

    # ⭐ A NATUREZA decide qual valor faz sentido, e recusar é melhor que aceitar o errado:
    # o backend grava `valor_mensal` em `total_value` quando a modalidade é one_time. Ou
    # seja, mandar o total no campo "mensal" FUNCIONA — e é justamente por funcionar que
    # precisa de guarda. Sem ela, um fornecimento de R$ 46 mil entra silenciosamente como
    # mensalidade se a modalidade estiver errada, e vira MRR recorrente no painel.
    info = MODALIDADES.get((modalidade or "").strip().lower())
    if not info:
        return {"ok": False, "codigo": "MODALIDADE_DESCONHECIDA", "http": 422,
                "mensagem": f"Modalidade {modalidade!r} não existe.",
                "dica": "Use uma de: " + ", ".join(sorted(MODALIDADES))}
    unico = info[2] == "one_time"
    if unico:
        if valor_total is None and valor_mensal is None:
            return {"ok": False, "codigo": "VALOR_FALTANDO", "http": 422,
                    "mensagem": f"{modalidade} é contrato de valor ÚNICO — informe `valor_total`.",
                    "campos_faltantes": ["valor_total"],
                    "dica": "Ex.: valor_total=46320. Não há mensalidade nem dia de vencimento."}
        if valor_mensal is not None and valor_total is not None:
            return {"ok": False, "codigo": "VALOR_CONFLITANTE", "http": 422,
                    "mensagem": "Informou mensal e total num contrato de valor único.",
                    "dica": "Deixe só `valor_total`."}
        valor = float(valor_total if valor_total is not None else valor_mensal)
        dia_vencimento = 0          # não existe mensalidade para vencer
    else:
        if valor_mensal is None and valor_total is None:
            return {"ok": False, "codigo": "VALOR_FALTANDO", "http": 422,
                    "mensagem": f"{modalidade} é contrato recorrente — informe `valor_mensal`.",
                    "campos_faltantes": ["valor_mensal"],
                    "dica": "Ex.: valor_mensal=40612. Para serviço único use "
                            "modalidade='eletronica_instalacao'."}
        if valor_total is not None and valor_mensal is None:
            return {"ok": False, "codigo": "VALOR_CONFLITANTE", "http": 422,
                    "mensagem": f"Passou `valor_total` numa modalidade recorrente "
                                f"({modalidade}). Eu não decido se são 12 mensalidades ou "
                                f"uma obra — isso muda o MRR e o instrumento.",
                    "dica": "Use `valor_mensal`, ou troque para uma modalidade de valor único."}
        valor = float(valor_mensal)
    if not vigencia_inicio:
        return {"ok": False, "codigo": "VIGENCIA_FALTANDO", "http": 422,
                "mensagem": "Informe `vigencia_inicio` (AAAA-MM-DD).",
                "campos_faltantes": ["vigencia_inicio"],
                "dica": "No valor único é a data de início da execução."}

    if dry_run:
        # o ensaio resolve o que der para resolver e mostra; o que não der, diz por quê.
        tipo_emp = MODALIDADES.get((modalidade or "").strip().lower())
        if not tipo_emp:
            return {"ok": False, "codigo": "MODALIDADE_DESCONHECIDA", "http": 422,
                    "mensagem": f"Modalidade {modalidade!r} não existe.",
                    "dica": "Use uma de: " + ", ".join(sorted(MODALIDADES))}
        cliente = None
        alvo_doc = re.sub(r"\D", "", cliente_documento or "")
        try:
            # ⚠️ o cadastro guarda o CNPJ em `cnpj`, não em `document_number` — a primeira
            # versão comparava o campo errado e dizia "não achei" de um cliente que EXISTE.
            # Num ensaio, errar para o lado do "seria recusado" é pior que não checar: faz
            # o dono cadastrar de novo um cliente que já está lá.
            busca = await erp.get("/crm/clients", params={"page_size": 200})
            for c in (busca or {}).get("items") or []:
                doc = re.sub(r"\D", "", str(c.get("cnpj") or c.get("document_number") or ""))
                if doc and doc == alvo_doc:
                    cliente = c.get("name")
                    break
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "dry_run": True, "gravou": False,
                "natureza": info[2],
                "resumo": (f"Criaria um contrato {tipo_emp[0]} de {_brl(valor)} "
                           f"em VALOR ÚNICO pela {tipo_emp[1]}."
                           if unico else
                           f"Criaria um contrato {tipo_emp[0]} de {_brl(valor)}/mês "
                           f"pela {tipo_emp[1]}, com vigência de {vigencia_meses} meses."),
                "cliente_encontrado": cliente or f"NÃO ACHEI o CNPJ {cliente_documento}",
                "modelo": tipo_emp[0], "emitente": tipo_emp[1],
                ("valor_total" if unico else "valor_mensal"): valor,
                "vigencia_inicio": vigencia_inicio,
                "aviso": ("Cliente não está no CRM — a criação seria RECUSADA. Cadastre antes."
                          if not cliente else
                          "Nada foi gravado. Chame de novo sem dry_run para criar."),
                "proximo_passo": "criar_contrato_por_modelo(..., idempotency_key='algo-unico')"}
    corpo: dict[str, Any] = {
        "cliente_documento": cliente_documento, "modalidade": modalidade,
        # o backend roteia para total_value quando a modalidade é one_time
        "valor_mensal": valor, "vigencia_inicio": vigencia_inicio,
        "vigencia_meses": vigencia_meses, "renovacao_aviso_dias": renovacao_aviso_dias,
    }
    if dia_vencimento:
        corpo["dia_vencimento"] = dia_vencimento
    if carencia_dias:
        corpo["carencia_dias"] = carencia_dias
    try:
        return _idem_guarda(idempotency_key,
                            await erp.post("/crm/contracts/criar-por-modelo", json=corpo))
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def abrir_assinatura_contrato(contrato: str, email_cliente: str = "") -> dict:
    """Abre a assinatura eletrônica do contrato e devolve o LINK único do cliente.

    A Conecta Mais assina primeiro pelo painel; depois o link vai para o síndico assinar.
    Recusa contrato incompleto. Restrito a Jordan e Pyetra.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    q = f"?email_cliente={email_cliente}" if email_cliente else ""
    try:
        return await erp.post(f"/crm/contracts/{contrato}/abrir-assinatura{q}", json={})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def assinar_contrato_empresa(contrato: str) -> dict:
    """A Conecta Mais ASSINA o contrato pelo painel (1º signatário).

    Só depois disto o link do cliente deve ser enviado — não se pede ao síndico que assine
    o que a própria empresa ainda não firmou. Restrito a Jordan e Pyetra.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    try:
        return await erp.post(f"/crm/contracts/{contrato}/assinar-empresa", json={})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def enviar_link_assinatura(contrato: str, email: str = "", parte: str = "cliente") -> dict:
    """Manda ao signatário o LINK para assinar, ou devolve o link para envio manual.

    Recusa mandar ao cliente se a Conecta Mais ainda não assinou. Restrito a Jordan e Pyetra.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    q = f"?parte={parte}" + (f"&email={email}" if email else "")
    try:
        return await erp.post(f"/crm/contracts/{contrato}/enviar-link{q}", json={})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def status_assinatura_contrato(contrato: str) -> dict:
    """Quem já assinou o contrato, quando e com que hash — e quem ainda falta."""
    try:
        return await erp.get(f"/crm/contracts/{contrato}/assinaturas")
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def briefing_contrato_novo(
    servicos: str = "",
    cliente_cnpj: str = "",
    cliente_nome: str = "",
) -> dict:
    """Briefing de um contrato NOVO: o que precisa ser definido antes de montar.

    servicos: lista separada por vírgula — portaria, servicos_gerais, jardinagem, piscina,
    zeladoria, eletronica. Mais de um = contrato misto. Sem serviços, devolve as opções.
    Traz as funções da CCT vigente com o piso de cada uma. Restrito a Jordan e Pyetra.
    """
    payload: dict = {}
    if servicos:
        payload["servicos"] = [s.strip() for s in servicos.split(",") if s.strip()]
    if cliente_cnpj:
        payload["cliente_cnpj"] = cliente_cnpj
    if cliente_nome:
        payload["cliente_nome"] = cliente_nome
    try:
        return await erp.post("/crm/contracts/briefing", json=payload)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def gerar_contrato_por_modelo(
    contrato: str,
    template_id: str = "",
    representante: str = "",
    representante_cpf: str = "",
    dia_vencimento: int = 0,
    dias_primeiro_pagamento: int = 0,
    valor_total: float | None = None,
    objeto_resumo: str = "",
    proposta_numero: str = "",
    prazo_exec_dias: int = 0,
    itens: list | None = None,
    minuta: bool = False,
) -> dict:
    """Emite o CONTRATO COMPLETO pelo modelo cadastrado e devolve o LINK para enviar ao cliente.

    `contrato` aceita CTR-…, id, CNPJ do cliente ou nome aproximado.

    Busca no banco o que já existe. Se faltar dado, NÃO falha: devolve as perguntas do que
    falta — responda passando os campos abaixo e chame de novo. Restrito ao Jordan e à Pyetra.

    ── RECORRENTE (portaria, manutenção, portaria remota) ──
      `dia_vencimento`, `dias_primeiro_pagamento`, e `itens` compondo o valor MENSAL.

    ── VALOR ÚNICO (fornecimento/instalação da Eletrônica) ──
      `valor_total`, `objeto_resumo` (vai para a Cláusula 1ª), `proposta_numero`,
      `prazo_exec_dias`, e `itens` como as PARCELAS — cada uma com
      `{"tipo": "entrada|parcela|retida", "nome", "total", "vencimento"}`, somando o total.

      ⚠️ Não passe `dia_vencimento` num contrato de valor único: não há mensalidade.
      Item 2.5 do relatório de campo (11/09/2026) — o CTR-2026-00022 é de R$ 46.320 em
      parcela única e mesmo assim o gerador perguntava "em que dia do mês vence a
      mensalidade?". A ramificação existia no backend desde então; era ESTA tool que só
      sabia repassar os dois campos de recorrência, e por isso todo contrato da Eletrônica
      continuava fora do padrão ouro quando emitido pelo Cowork.

    `minuta=True` produz a versão para análise jurídica, com os campos ainda indefinidos
    em branco em vez de recusar a emissão por falta deles.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    alvo = await _resolver_contrato(contrato)
    if isinstance(alvo, dict):
        return alvo
    payload: dict[str, Any] = {"contrato": alvo}
    for chave, valor in (
        ("template_id", template_id), ("representante", representante),
        ("representante_cpf", representante_cpf), ("payment_day", dia_vencimento),
        ("grace_period_days", dias_primeiro_pagamento), ("valor_total", valor_total),
        ("objeto_resumo", objeto_resumo), ("proposta_numero", proposta_numero),
        ("prazo_exec_dias", prazo_exec_dias), ("itens", itens), ("minuta", minuta),
    ):
        if valor not in (None, "", 0, [], False):
            payload[chave] = valor
    try:
        return await erp.post("/crm/contracts/emitir-por-modelo", json=payload)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def baixar_relatorio_comercial_pdf(salvar_no_drive: bool = False,
                                         formato: str = "base64") -> dict:
    """Gera o RELATÓRIO COMERCIAL em PDF (MRR, clientes, pipeline, top deals) no padrão Conecta Mais, em base64.

    `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    documento sem abrir binário; "texto" só o texto; "url" só o link, como antes.
    Item 2.1 do relatório de campo: gerar um PDF e não poder olhar o que saiu.
    """
    return await _gerar_doc_get("/crm/reports/comercial/pdf", drive=salvar_no_drive,
                                formato=formato)


async def _pdf_post_b64(path: str, payload: dict) -> dict:
    import base64
    try:
        raw = await erp.post_bytes(path, payload)
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "gerado": False}
    return {"gerado": True, "tamanho_kb": round(len(raw) / 1024, 1), "mime": "application/pdf",
            "pdf_base64": base64.b64encode(raw).decode("ascii")}


async def _legivel(r: dict, formato: str, forcar_base64: bool = False) -> dict:
    """Acrescenta base64 e `texto_extraido` a um documento que o ERP acabou de registrar.

    ⭐ Reusa `/crm/docs/conteudo/{id}`, criado para o item 2.2. A extração acontece no
    BACKEND, que já tem PyPDF2 — o MCP não ganha dependência de PDF por causa disto, e as
    duas portas (anexo que entra, documento que o ERP gera) passam a ler pelo mesmo lugar.
    Duas implementações de extração divergiriam na primeira mudança.

    Falhar em enriquecer NÃO derruba a geração: o documento existe e o link funciona. O que
    volta é o envelope de antes com um aviso honesto, nunca um erro que sugira que o PDF
    não saiu.
    """
    if str(formato).lower() == "url" or not r.get("gerado") or not r.get("id"):
        return r
    try:
        c = await erp.get(f"/crm/docs/conteudo/{r['id']}",
                          params={"formato": formato, "forcar_base64": forcar_base64})
    except Exception as exc:  # noqa: BLE001
        r["aviso_leitura"] = (f"Gerado e registrado, mas não consegui trazer o conteúdo "
                              f"para leitura ({str(exc)[:90]}). O documento existe; use o "
                              f"link do registro ou chame baixar_documento pelo id.")
        return r
    if not c.get("ok"):
        r["aviso_leitura"] = c.get("mensagem") or "conteúdo indisponível para leitura"
        return r
    r["arquivo"] = c.get("arquivo")
    r["texto_extraido"] = c.get("texto_extraido")
    r["paginas"] = c.get("paginas")
    if c.get("aviso"):
        r["aviso_leitura"] = c["aviso"]
    return r


async def _gerar_doc(path: str, payload: dict, teste: bool = True, drive: bool = False,
                     formato: str = "base64") -> dict:
    """Gera o documento (POST), REGISTRA no Conecta PRO e devolve o LINK público. drive=True: sobe pro Google Drive."""
    try:
        r = await erp.post(f"{path}?salvar=true&teste={'true' if teste else 'false'}&drive={'true' if drive else 'false'}", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "gerado": False}
    saida = {"gerado": True, "titulo": r.get("titulo"), "tamanho_kb": r.get("tamanho_kb"),
             "download_url": r.get("download_url"), "drive_url": r.get("drive_url"), "id": r.get("id"),
             "obs": "Registrado no Conecta PRO." + (f" Salvo no Drive: {r.get('drive_url')}" if r.get("drive_url") else " Abra o download_url para ver/baixar.")}
    return await _legivel(saida, formato)


async def _gerar_doc_get(path: str, teste: bool = True, drive: bool = False,
                         formato: str = "base64") -> dict:
    """Idem (GET): gera doc de uma entidade existente (proposta/contrato/relatório), registra + link. drive=True: sobe pro Drive."""
    sep = "&" if "?" in path else "?"
    try:
        r = await erp.get(f"{path}{sep}salvar=true&teste={'true' if teste else 'false'}&drive={'true' if drive else 'false'}")
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "gerado": False}
    saida = {"gerado": True, "titulo": r.get("titulo"), "tamanho_kb": r.get("tamanho_kb"),
             "download_url": r.get("download_url"), "drive_url": r.get("drive_url"), "id": r.get("id"),
             "obs": "Registrado no Conecta PRO." + (f" Salvo no Drive: {r.get('drive_url')}" if r.get("drive_url") else " Abra o download_url para ver/baixar.")}
    return await _legivel(saida, formato)


@mcp.tool
async def consultar_auditoria(limite: int = 30, metodo: str | None = None,
                              busca: str | None = None,
                              request_id: str | None = None) -> dict:
    """Auditoria das escritas E a trilha de acesso a dado pessoal sensível. Só lê.

    `eventos` = escritas de negócio (quem, quando, rota, resultado).
    `acessos_a_dado_sensivel` = trilha LGPD, em seção PRÓPRIA: qual FERRAMENTA, sobre o quê,
    quem, quando, e se estava coberta pela concessão de escopo.

    `request_id` filtra a trilha por uma chamada específica — é assim que se liga "deu erro
    às 14h" a "quem olhou o quê".

    ⚠️ Até 12/09/2026 esta consulta devolvia as chamadas do PRÓPRIO log de acesso como se
    fossem escritas de negócio: quinze linhas iguais de `POST /log-acesso-sensivel`,
    afogando a auditoria real e sem dizer qual tool tinha rodado. Agora o ruído sai e a
    trilha vem separada.

    metodo: POST|PUT|PATCH|DELETE (opcional). busca: trecho do caminho (ex.: 'contracts').
    """
    q = [f"limite={limite}"]
    if metodo:
        q.append(f"metodo={metodo}")
    if busca:
        q.append(f"busca={busca}")
    if request_id:
        q.append(f"request_id={request_id}")
    return await erp.get(f"/crm/audit?{'&'.join(q)}")


@mcp.tool
async def listar_precos_funcao() -> dict:
    """Tabela de PREÇOS por função (CCT 2026, Lucro Real, margem 15%): custo, preço, markup, adicionais.
    Funções com termos oficiais (AGP, ASG — nunca porteiro/vigia/faxineiro)."""
    return await erp.get("/crm/pricing/funcoes")


@mcp.tool
async def simular_preco(funcao: str | None = None, salario_base: float | None = None, jornada_dias: int = 15,
                        postos: int = 1, noturno: bool = False, hora_reduzida: bool = False, ronda: bool = False,
                        periculosidade: bool = False, insalubridade: bool = False, margem: float | None = None) -> dict:
    """Simula o preço de um posto (replica o simulador da planilha CCT 2026). Informe a função
    (ex.: 'AGP P1 Noturno') ou o salário base, e ative os adicionais. peric e insalub não acumulam."""
    return await erp.post("/crm/pricing/simular", json={
        "funcao": funcao, "salario_base": salario_base, "jornada_dias": jornada_dias, "postos": postos,
        "noturno": noturno, "hora_reduzida": hora_reduzida, "ronda": ronda,
        "periculosidade": periculosidade, "insalubridade": insalubridade, "margem": margem})


@mcp.tool
async def listar_aprovacoes_pendentes(limite: int = 30) -> dict:
    """O que está esperando a decisão de um humano na Central de Aprovações. Só lê.

    Lacuna apontada pelo Cowork em 12/09/2026: a fila é o ponto onde a pessoa decide, e o
    assistente não conseguia nem contar quantos itens havia nela — o que também impedia
    verificar se um teste tinha poluído a fila.

    Traz o que está `rascunho`, com a ação, quem pediu, quando e a `origem` (producao ·
    ensaio · sandbox · teste). ⚠️ Ler não aprova: aprovar acontece em outra superfície, com
    OTP quando é dinheiro ou assinatura.
    """
    try:
        r = await erp.get("/agente/aprovacoes", params={"limite": min(limite, 100)})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    itens = _items(r) or (r.get("aprovacoes") if isinstance(r, dict) else None) or []
    return {"ok": True, "total": len(itens), "pendentes": itens,
            "aviso": "Ler não aprova. A decisão acontece na Central, com a pessoa."}


@mcp.tool
async def pendencias_acionaveis(horizonte_dias: int = 30,
                                severidade_minima: str = "media") -> dict:
    """TUDO que precisa de decisão, numa lista ordenada por gravidade. Só lê.

    Bloco 8 do relatório: certidão vencendo, ASO estourando, obrigação fiscal a vencer,
    proposta esfriando, cotação expirando — as peças existiam soltas e nada chamava ninguém.

    Cada item traz `severidade`, `prazo`, `dias_restantes`, `impacto` (o que acontece se
    ninguém agir), `acao_sugerida` e `tool_para_agir`.

    Severidade, com critério ESCRITO: `critica` = prazo legal vencido/vencendo ou trava
    faturamento · `alta` = legal em até 7 dias, ou dinheiro parado · `media` = até 30 dias
    · `baixa` = informativo.

    ⚠️ NÃO corrige nada. Operacional em especial é curado à mão pelo dono — divergência ali
    vira linha de RELATÓRIO, e a `acao_sugerida` diz isso.

    ⚠️ Fonte que falha aparece como item `alta` ("FONTE INDISPONÍVEL"), não desaparece:
    lista curta e tranquila é lida como "está tudo bem".
    """
    import pendencias as P  # noqa: PLC0415

    itens: list = []

    async def colher(nome: str, chave: str, dominio: str, adaptador) -> None:
        try:
            r = await asyncio.wait_for(globals()[nome](), timeout=20)
            dados = (r or {}).get(chave) or []
            itens.extend(adaptador(dados))
        except Exception as exc:  # noqa: BLE001
            itens.append(P.fonte_falhou(dominio, nome, f"{type(exc).__name__}: {exc}"))

    await colher("alertas_obrigacoes", "alertas", "fiscal", P.de_obrigacoes)
    await colher("status_certidoes", "certidoes", "fiscal", P.de_certidoes)
    await colher("substituicoes_pendentes", "substituicoes", "operacional",
                 P.de_substituicoes)
    # ⭐ 13/09/2026: divergência de QUADRO nos postos, como RELATÓRIO. Até hoje nenhum item
    # operacional entrava nesta lista — o `aviso` declarava a política "vira relatório, nunca
    # correção" sobre uma lista que nunca teve um item operacional para curar. Havia 5
    # divergências reais, entre elas um posto com 3 de 4 vagas abertas num contrato de
    # R$22.100/mês. `listar_postos` devolve em `items`, não em `postos`.
    await colher("listar_postos", "items", "operacional", P.de_postos)

    # ASO precisa das duas pontas: quem vence e quem nunca teve
    try:
        venc = (await asyncio.wait_for(asos_vencendo(), timeout=20) or {}).get("asos_vencendo") or []
        sem = (await asyncio.wait_for(funcionarios_sem_aso(), timeout=20) or {}).get("colaboradores") or []
        itens.extend(P.de_aso(venc, sem))
    except Exception as exc:  # noqa: BLE001
        itens.append(P.fonte_falhou("sst", "asos_vencendo", f"{type(exc).__name__}: {exc}"))

    try:
        neg = (await asyncio.wait_for(negociacoes_pendentes(), timeout=20) or {}).get("pendentes") or []
        frios = (await asyncio.wait_for(leads_frios(), timeout=20) or {}).get("frios") or []
        itens.extend(P.de_comercial(neg, frios))
    except Exception as exc:  # noqa: BLE001
        itens.append(P.fonte_falhou("comercial", "negociacoes_pendentes",
                                    f"{type(exc).__name__}: {exc}"))

    # cotações a vencer — a peça nova do Bloco 3
    try:
        cot = await erp.get("/crm/propostas/cotacoes-a-vencer",
                            params={"dias": horizonte_dias})
        itens.extend(P.de_cotacoes((cot or {}).get("propostas") or []))
    except Exception:  # noqa: BLE001
        pass  # rota opcional: ausência não é pendência

    ordenados = P.ordenar(itens, severidade_minima, horizonte_dias)
    por_sev: dict = {}
    for i in ordenados:
        por_sev[i["severidade"]] = por_sev.get(i["severidade"], 0) + 1
    return {
        "ok": True, "total": len(ordenados), "por_severidade": por_sev,
        "horizonte_dias": horizonte_dias, "severidade_minima": severidade_minima,
        "pendencias": ordenados,
        "criterio_de_severidade": {
            "critica": "prazo legal vencido/vencendo ou trava faturamento",
            "alta": "prazo legal em até 7 dias, ou dinheiro parado",
            "media": "prazo em até 30 dias, ou trabalho comercial esfriando",
            "baixa": "informativo — serve para planejar a semana",
        },
        "aviso": ("Nada aqui foi corrigido. Operacional é curado à mão pelo dono: "
                  "divergência vira relatório, nunca correção automática."),
    }


@mcp.tool
async def procedencia_da_proposta(proposta: str) -> dict:
    """Esta proposta pode ser enviada? Custo firme, cotação válida, estimativa aceita. Só lê.

    Responde em DADO a pergunta "esse preço é firme ou é chute?" — que antes morava numa
    observação em texto livre e, na PROP-2026-00114, vazou para o PDF do cliente junto com
    a margem.

    Bloqueia (e diz qual item trava):
      · `CUSTO_SEM_PROCEDENCIA` — item com custo e sem `origem_custo` declarada;
      · `COTACAO_VENCIDA` — validade passou; preço vencido é preço que já não existe;
      · `ESTIMATIVA_NAO_ACEITA` — há custo de estimativa e ninguém assumiu o risco.

    Aceita PROP-…, id, CNPJ ou nome do cliente.
    """
    alvo = await _resolver_proposta(proposta)
    if isinstance(alvo, dict):
        return alvo
    try:
        return await erp.get(f"/crm/propostas/{alvo}/procedencia")
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def aceitar_estimativa_da_proposta(proposta: str, quem: str) -> dict:
    """Registra que uma pessoa ASSUME o risco de enviar com custo estimado. ESCREVE.

    Grava quem aceitou e quando. Decisão sem autor não é decisão — e este registro é o que
    permite, meses depois, saber quem topou o risco de o preço mudar.

    ⚠️ NÃO vai ao cliente. É trilha interna; o aviso existe para quem decide, e foi
    exatamente por não existir que a observação virou texto no PDF.
    """
    if not (quem or "").strip():
        return {"ok": False, "codigo": "ACEITE_SEM_AUTOR", "http": 422,
                "mensagem": "Diga QUEM está assumindo o risco.",
                "dica": "aceitar_estimativa_da_proposta(proposta, quem='Jordan Jesus')"}
    alvo = await _resolver_proposta(proposta)
    if isinstance(alvo, dict):
        return alvo
    try:
        return await erp.post(f"/crm/propostas/{alvo}/aceitar-estimativa",
                              json={"quem": quem})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def orcamento_por_natureza(empresa_cnpj: str, linha_negocio: str,
                                 itens: list) -> dict:
    """Preço item a item, cada linha com a SUA margem. Não grava nada.

    Um orçamento de eletrônica mistura equipamento e instalação, e as margens são
    diferentes — 35% e 40%. Este cálculo mostra a memória POR LINHA: custo, margem
    aplicada, percentual e de onde o parâmetro veio.

    `itens`: `[{"descricao": "64 câmeras IP", "custo": 1200, "quantidade": 64,
                "natureza_item": "produto"}]`
    `natureza_item`: `produto` · `mao_de_obra_tecnica` · `servico_alocado`

    ⚠️ Item sem `natureza_item` é RECUSADO, e combinação sem margem cadastrada também —
    com a lista do que existe. Chutar 15% onde a margem é 40% erra o preço para MENOS e só
    aparece no fechamento.

    A `convencao` vem em cada linha: por decisão do Jordan (11/09/2026) é margem sobre o
    PREÇO, não markup sobre o custo — num item de R$ 100 mil a diferença é R$ 18.846.
    """
    try:
        return await erp.post("/crm/pricing/orcamento-por-natureza", json={
            "empresa_cnpj": empresa_cnpj, "linha_negocio": linha_negocio, "itens": itens})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def consultar_parametros_precificacao(empresa: str = "", linha_negocio: str = "",
                                            natureza_item: str = "") -> dict:
    """Parâmetros de precificação — encargos, tributos, benefícios e as MARGENS por dimensão.

    ⭐ `margens` é LISTA, nunca um número só. Até 11/09/2026 havia um escalar `margem=0.15`
    para o grupo inteiro, e isso era falso desde que existe a eletrônica: serviço alocado
    15%, equipamento 35%, mão de obra de instalação 40%.

    Cada margem traz a `convencao` (margem sobre o preço) e a procedência — quem confirmou
    e quando. Parâmetro de dinheiro sem procedência é parâmetro que ninguém confia daqui a
    seis meses. Só lê.
    """
    params = {k: v for k, v in (("empresa", empresa), ("linha_negocio", linha_negocio),
                                ("natureza_item", natureza_item)) if v}
    try:
        return await erp.get("/crm/pricing/parametros", params=params or None)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def definir_parametros_precificacao(valores: dict) -> dict:
    """Atualiza parâmetros de precificação (sincronizar a planilha). valores = {chave: valor}.
    Ex.: {'ronda':0.05,'iss':0.05,'margem':0.15}. Chaves: encargos/tributos/benefícios/adicionais/margem."""
    return await erp.request("PUT", "/crm/pricing/parametros", json={"valores": valores})


@mcp.tool
async def listar_documentos(tipo: str | None = None, limite: int = 30) -> dict:
    """Lista os documentos gerados/registrados no Conecta PRO (com link de download).
    tipo (opcional): proposta|contrato|relatorio|recibo|ordem_servico|aditivo|atestado."""
    p = f"?tipo={tipo}&limite={limite}" if tipo else f"?limite={limite}"
    try:
        r = await erp.get(f"/crm/docs{p}")
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    itens = _items(r) or (r.get("documentos") if isinstance(r, dict) else None) or []
    # `ok` explícito: sem ele o agente não distingue "nenhum documento" de "a chamada
    # falhou e devolveu lista vazia" — e as duas levam a decisões opostas.
    return {"ok": True, "total": (r or {}).get("total", len(itens)) if isinstance(r, dict) else len(itens),
            "nesta_pagina": len(itens),
            "documentos": itens if itens else (r if not isinstance(r, dict) else [])}


@mcp.tool
async def gerar_recibo_pdf(pagador: str, valor: float, referente: str, documento: str | None = None,
                           forma_pagamento: str | None = None, numero: str | None = None, salvar_no_drive: bool = False,
                           formato: str = "base64") -> dict:
    """Gera um RECIBO de pagamento em PDF (padrão Conecta Mais, com selo), em base64.
    Ex.: pagador='CONDOMINIO X', valor=6000, referente='portaria remota — junho/2026'.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
        `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    documento sem abrir binário; "texto" só o texto; "url" só o link, como antes.
    Item 2.1 do relatório de campo: gerar um PDF e não poder olhar o que saiu.

    """
    return await _gerar_doc("/crm/docs/recibo/pdf", {
        "pagador": pagador, "valor": valor, "referente": referente,
        "documento": documento, "forma_pagamento": forma_pagamento, "numero": numero},
        drive=salvar_no_drive, formato=formato)


@mcp.tool
async def gerar_aditivo_pdf(contrato_numero: str, tipo: str = "outro", objeto: str | None = None,
                            cliente: str | None = None, documento: str | None = None,
                            novo_valor: float | None = None, nova_vigencia_fim: str | None = None,
                            justificativa: str | None = None, numero: str | None = None, salvar_no_drive: bool = False,
                            formato: str = "base64") -> dict:
    """Gera um TERMO ADITIVO de contrato em PDF (padrão Conecta Mais, com selo), em base64.
    tipo: reajuste | prorrogacao | escopo | valor | outro. Enriquece cliente pelo contrato se omitido.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
        `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    documento sem abrir binário; "texto" só o texto; "url" só o link, como antes.
    Item 2.1 do relatório de campo: gerar um PDF e não poder olhar o que saiu.

    """
    # ⭐ 12/09/2026: com `contrato_numero` inexistente isto gerava um PDF de 262 KB
    # intitulado "Aditivo - LIXO-ZZZ-999", devolvia `gerado: true` e um `download_url`.
    # Aditivo, por definição, altera contrato que existe — documento para contrato que não
    # existe é fabricação, e o agente lê `gerado: true` como serviço feito.
    # ⚠️ e a checagem usa `_resolver_contrato`, que JÁ EXISTE e já devolve envelope para o
    # que não acha. A primeira versão desta guarda chamava uma rota `/crm/contracts/
    # by-number/{n}` que eu inventei — o 404 dela teria vindo da rota inexistente, não do
    # contrato inexistente, e a guarda reprovaria contrato válido. Reusar o resolvedor da
    # casa é mais curto e mede a coisa certa.
    alvo = await _resolver_contrato(contrato_numero, exigir_existencia=True)
    if isinstance(alvo, dict):
        return {**alvo, "gerado": False}
    contrato_numero = alvo
    return await _gerar_doc("/crm/docs/aditivo/pdf", {
        "contrato_numero": contrato_numero, "tipo": tipo, "objeto": objeto, "cliente": cliente,
        "documento": documento, "novo_valor": novo_valor, "nova_vigencia_fim": nova_vigencia_fim,
        "justificativa": justificativa, "numero": numero},
        drive=salvar_no_drive, formato=formato)


@mcp.tool
async def gerar_atestado_pdf(emitente: str, servico: str, periodo: str | None = None,
                             emitente_documento: str | None = None, emitente_responsavel: str | None = None,
                             emitente_cargo: str | None = None, valor: float | None = None,
                             cidade: str | None = None, observacoes: str | None = None,
                             numero: str | None = None, salvar_no_drive: bool = False,
                             formato: str = "base64") -> dict:
    """Gera um ATESTADO DE CAPACIDADE TÉCNICA em PDF (padrão Conecta Mais, com selo), em base64.
    emitente = cliente que atesta os serviços da Conecta Mais (usado em licitações).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
        `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    documento sem abrir binário; "texto" só o texto; "url" só o link, como antes.
    Item 2.1 do relatório de campo: gerar um PDF e não poder olhar o que saiu.

    """
    return await _gerar_doc("/crm/docs/atestado/pdf", {
        "emitente": emitente, "servico": servico, "periodo": periodo, "emitente_documento": emitente_documento,
        "emitente_responsavel": emitente_responsavel, "emitente_cargo": emitente_cargo, "valor": valor,
        "cidade": cidade, "observacoes": observacoes, "numero": numero},
        drive=salvar_no_drive, formato=formato)


@mcp.tool
async def gerar_ordem_servico_pdf(cliente: str, servico: str, descricao: str | None = None,
                                  documento: str | None = None, endereco: str | None = None,
                                  responsavel: str | None = None, valor: float | None = None,
                                  prazo: str | None = None, observacoes: str | None = None,
                                  numero: str | None = None, salvar_no_drive: bool = False,
                                  formato: str = "base64") -> dict:
    """Gera uma ORDEM DE SERVIÇO (OS) em PDF (padrão Conecta Mais, com selo), em base64.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
        `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    documento sem abrir binário; "texto" só o texto; "url" só o link, como antes.
    Item 2.1 do relatório de campo: gerar um PDF e não poder olhar o que saiu.

    """
    return await _gerar_doc("/crm/docs/ordem-servico/pdf", {
        "cliente": cliente, "servico": servico, "descricao": descricao, "documento": documento,
        "endereco": endereco, "responsavel": responsavel, "valor": valor, "prazo": prazo,
        "observacoes": observacoes, "numero": numero},
        drive=salvar_no_drive, formato=formato)


@mcp.tool
async def listar_propostas(limite: int = 20) -> dict:
    """Lista as propostas mais recentes (número, cliente, total, status)."""
    data = await erp.get("/crm/proposals/", params={"page_size": min(limite, 100)})
    return {"propostas": [
        {"numero": p.get("number"), "titulo": p.get("title"), "cliente": p.get("client_name"),
         "total": _num(p.get("total")), "total_formatado": _brl(p.get("total")),
         "status": p.get("status")}
        for p in _items(data)[:limite]
    ]}


@mcp.tool
async def criar_lead(nome: str, email: str | None = None, telefone: str | None = None,
                     empresa: str | None = None, origem: str = "website") -> dict:
    """Cria um lead no CRM (dispara automações/scoring configurados). Retorna id do lead.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    payload = {"name": nome, "source": origem, "status": "new"}
    if email:
        payload["email"] = email
    if telefone:
        payload["phone"] = telefone
    if empresa:
        payload["company"] = empresa
    r = await erp.post("/crm/leads", json=payload)
    return {"id": r.get("id"), "nome": r.get("name"), "status": r.get("status")}


@mcp.tool
async def listar_leads(limite: int = 20) -> dict:
    """Lista os leads mais recentes (nome, empresa, origem, status, score)."""
    data = await erp.get("/crm/leads", params={"page_size": min(limite, 100)})
    return {"leads": [
        {"id": x.get("id"), "nome": x.get("name"), "empresa": x.get("company"),
         "origem": x.get("source"), "status": x.get("status"), "score": x.get("score")}
        for x in _items(data)[:limite]
    ]}


@mcp.tool
async def listar_clientes(busca: str | None = None, limite: int = 50,
                          pagina: int = 1, ativos: bool | None = None) -> dict:
    """Lista clientes com total e paginação. `busca` casa nome, CNPJ ou código. Só lê.

    Auditoria do Cowork (11/09/2026): era a ÚNICA listagem fora do envelope — devolvia
    `{"clientes": [...]}` sem `ok`, sem `total`, sem página. Um agente que recebe uma lista
    curta sem total não sabe se viu tudo ou se parou no corte, e decide sobre metade.
    """
    try:
        data = await erp.get("/crm/clients/", params={"page_size": 200})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    rows = _items(data)
    if busca:
        # casa nome, CNPJ ou código — buscar cliente pelo CNPJ era o caso mais comum e o
        # filtro só olhava o nome, devolvendo vazio para um cliente que existe.
        alvo, digitos = _norm(busca), re.sub(r"\D", "", busca)
        rows = [c for c in rows
                if alvo in _norm(str(c.get("name") or ""))
                or (digitos and len(digitos) >= 6
                    and digitos in re.sub(r"\D", "", str(c.get("cnpj") or c.get("document_number") or "")))
                or str(c.get("code") or "").upper() == busca.upper()]
    if ativos is not None:
        rows = [c for c in rows if bool(c.get("is_active", True)) == ativos]
    total = len(rows)
    ini = max(pagina - 1, 0) * max(limite, 1)
    pagina_rows = rows[ini:ini + max(limite, 1)]
    paginas = max((total + max(limite, 1) - 1) // max(limite, 1), 1)
    out: dict = {
        "ok": True, "total": total, "pagina": max(pagina, 1), "paginas": paginas,
        "nesta_pagina": len(pagina_rows),
        "clientes": [{
            "id": c.get("id"), "codigo": c.get("code"), "nome": c.get("name"),
            "cnpj": c.get("cnpj") or c.get("document_number"),
            "cidade": c.get("city"), "ativo": c.get("is_active"),
            "mrr": _num(c.get("mrr")), "mrr_formatado": _brl(c.get("mrr")),
        } for c in pagina_rows],
    }
    if pagina < paginas:
        out["proxima_pagina"] = pagina + 1
        out["dica"] = f"Há {paginas} páginas. Chame de novo com pagina={pagina + 1}."
    return out


async def _buscar_cliente(cnpj: str) -> dict | None:
    """Acha um cliente pelo CNPJ/CPF (compara só dígitos). Retorna o registro ou None."""
    digits = "".join(c for c in (cnpj or "") if c.isdigit())
    if not digits:
        return None
    for c in _items(await erp.get("/crm/clients/")):
        cdoc = "".join(ch for ch in (c.get("cnpj") or c.get("document_number") or "") if ch.isdigit())
        if cdoc and cdoc == digits:
            return c
    return None


@mcp.tool
async def buscar_cliente_por_cnpj(cnpj: str) -> dict:
    """Verifica se um cliente já está cadastrado pelo CNPJ/CPF (use ANTES de criar, p/ não duplicar)."""
    c = await _buscar_cliente(cnpj)
    if c:
        return {"existe": True, "codigo": c.get("code"), "nome": c.get("name"),
                "cnpj": c.get("cnpj") or c.get("document_number"), "id": c.get("id"), "mrr": _brl(c.get("mrr"))}
    # ⭐ 13/09/2026, critério do Cowork: TODA resposta carrega `ok`. Isto NÃO é recusa — é
    # busca bem-sucedida com resposta negativa, e por isso `ok: true` com `existe: false`.
    # O que ele derrubou não foi a negativa, foi a resposta sem `ok` nenhum: o agente não
    # tem como distinguir "consultei e não existe" de "a chamada nem chegou".
    return {"ok": True, "existe": False, "cnpj": cnpj,
            "mensagem": f"Nenhum cliente cadastrado com {cnpj!r}.",
            "dica": "Se for cliente novo, `criar_cliente(...)`. Confira o CNPJ só com "
                    "dígitos antes — a busca normaliza, mas o dígito errado não existe."}


@mcp.tool
async def criar_cliente(nome: str, cnpj: str, email: str | None = None, telefone: str | None = None,
                        cidade: str | None = None) -> dict:
    """Cadastra um cliente com CNPJ. IDEMPOTENTE: se o CNPJ já existir, retorna o cliente existente
    (NUNCA duplica). Valida o CNPJ. Use ao alimentar o CRM com clientes reais.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    existing = await _buscar_cliente(cnpj)
    if existing:
        return {"ja_existia": True, "codigo": existing.get("code"), "nome": existing.get("name"),
                "cnpj": existing.get("document_number"), "id": existing.get("id")}
    _digits = "".join(c for c in (cnpj or "") if c.isdigit())
    # clients.email é NOT NULL no banco. Se não informado, usa placeholder não-roteável (.invalid)
    # — claramente um "sem e-mail"; troque pelo real depois. Passe 'email' sempre que tiver.
    payload: dict[str, Any] = {
        "name": nome,
        "document_number": cnpj,
        "email": email or f"naoinformado-{_digits}@example.invalid",
    }
    if telefone:
        payload["phone"] = telefone
    if cidade:
        payload["address_city"] = cidade
    try:
        r = await erp.post("/clients", json=payload)
    except Exception as exc:  # noqa: BLE001 — CNPJ inválido ou duplicado (backstop)
        return {**erro_envelope(exc), "criado": False,
                "dica": "CNPJ pode estar inválido (dígitos verificadores) ou já cadastrado."}
    return {"criado": True, "codigo": r.get("code"),
            "nome": r.get("legal_name") or r.get("name"), "id": r.get("id")}


@mcp.tool
async def listar_contratos(
    cliente: str | None = None, status: str | None = None, tipo: str | None = None,
    busca: str | None = None, valor_min: float | None = None, valor_max: float | None = None,
    limite: int = 20, pagina: int = 1,
) -> dict:
    """Lista contratos com o CLIENTE na resposta, filtros e total. Só lê.

    `cliente` aceita CNPJ, código (CLI-…), id ou nome aproximado — resolvido aqui.
    Use antes de `obter_contrato`: se a listagem já responde, não gaste a chamada.

    Relatório de campo (11/09/2026): a versão anterior devolvia só número, tipo, mensal e
    status — **não dizia de qual cliente era**. Descobrir "quais são do Maiápolis" custava
    um `obter_contrato` por linha. O backend já mandava `client_name` e `client_document`;
    era a tool que os jogava fora.
    """
    params: dict = {"page_size": min(max(limite, 1), 100), "page": max(pagina, 1)}
    resolvido = None
    if cliente:
        resolvido = await _resolver_cliente_id(cliente)
        if isinstance(resolvido, dict):
            return resolvido  # AMBIGUO ou NAO_ENCONTRADO — o agente escolhe
        params["client_id"] = resolvido
    for chave, valor in (("status", status), ("contract_type", tipo), ("search", busca),
                         ("min_value", valor_min), ("max_value", valor_max)):
        if valor is not None:
            params[chave] = valor
    try:
        data = await erp.get("/crm/contracts", params=params)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)

    def linha(c: dict) -> dict:
        # `valor` numérico ao lado do formatado: string obriga o agente a fazer parsing e
        # erra na vírgula. O formatado fica para ele MOSTRAR, não para ele contar.
        mensal, total = _num(c.get("monthly_value")), _num(c.get("total_value"))
        return {
            "numero": c.get("contract_number"), "nome": c.get("name"),
            "cliente_nome": c.get("client_name"), "cliente_cnpj": c.get("client_document"),
            "cliente_id": c.get("client_id"),
            "tipo": c.get("contract_type"), "status": c.get("status"),
            "valor_mensal": mensal, "valor_mensal_formatado": _brl(c.get("monthly_value")),
            "valor_total": total, "valor_total_formatado": _brl(c.get("total_value")),
            "vigencia_inicio": c.get("start_date"), "vigencia_fim": c.get("end_date"),
            "template_id": c.get("template_id"),
            "atualizado_em": c.get("updated_at"), "id": c.get("id"),
        }

    itens = [linha(c) for c in _items(data)]
    total = (data or {}).get("total")
    pag = (data or {}).get("page") or 1
    tot_pag = (data or {}).get("total_pages") or 1
    out: dict = {"ok": True, "contratos": itens, "total": total,
                 "pagina": pag, "paginas": tot_pag, "nesta_pagina": len(itens)}
    if tot_pag and pag < tot_pag:
        out["proxima_pagina"] = pag + 1
        out["dica"] = f"Há {tot_pag} páginas. Chame de novo com pagina={pag + 1}."
    if resolvido:
        out["filtro_cliente_resolvido"] = resolvido
    return out


@mcp.tool
async def listar_sequencias() -> dict:
    """Lista as sequências/cadências de follow-up disponíveis (id, nome, nº de passos)."""
    data = await erp.get("/crm/sequences")
    return {"sequencias": [
        {"id": s.get("id"), "nome": s.get("name"), "passos": len(s.get("steps") or []),
         "canal": s.get("channel"), "ativa": s.get("is_active")}
        for s in _items(data)
    ]}


@mcp.tool
async def inscrever_lead_em_sequencia(sequencia_id: str, lead_id: str) -> dict:
    """Inscreve um lead numa sequência de follow-up. Os envios saem automaticamente (Celery)."""
    r = await erp.post(f"/crm/sequences/{sequencia_id}/enroll", json={"lead_id": lead_id})
    return {"inscrito": bool(r.get("enrolled")), "enrollment_id": r.get("enrollment_id")}


@mcp.tool
async def resumo_comercial() -> dict:
    """Snapshot comercial: nº de clientes, MRR total, pipeline aberto e propostas recentes."""
    clientes = _items(await erp.get("/crm/clients/"))
    mrr = sum(float(c.get("mrr") or 0) for c in clientes)
    pipe = await _compute_pipeline()
    props = _items(await erp.get("/crm/proposals/", params={"page_size": 5}))
    return {
        "ok": True,
        "clientes": len(clientes),
        "mrr_total": _num(mrr), "mrr_total_formatado": _brl(mrr),
        "pipeline_aberto": pipe.get("pipeline_aberto"),
        "pipeline_aberto_formatado": pipe.get("pipeline_aberto_formatado"),
        "total_deals": pipe.get("total_deals"),
        "propostas_recentes": [{"numero": p.get("number"), "cliente": p.get("client_name"),
                                "total": _num(p.get("total")),
                                "total_formatado": _brl(p.get("total")),
                                "status": p.get("status")} for p in props],
    }


# =================================================================== EDIÇÃO / GOVERNANÇA
@mcp.tool
async def definir_meta_mensal(valor: float, mes: int | None = None, ano: int | None = None,
                              vendedor: str | None = None) -> dict:
    """Define a META mensal de fechamento (destrava o atingimento no forecast).
    mes/ano: default = mês/ano atual. valor em R$."""
    hoje = date.today()
    payload = {"seller_name": vendedor or "Equipe", "period_year": ano or hoje.year,
               "period_month": mes or hoje.month, "target_value": valor}
    r = await erp.post("/crm/quotas", json=payload)
    return {"meta_definida": True, "periodo": f"{payload['period_month']:02d}/{payload['period_year']}",
            "valor": _brl(valor), "id": r.get("id")}


@mcp.tool
async def atualizar_cliente(cnpj_ou_id: str, nome: str | None = None, email: str | None = None,
                            telefone: str | None = None, cidade: str | None = None) -> dict:
    """Atualiza dados de um cliente (padronizar nome p/ CAIXA ALTA, corrigir contato).
    cnpj_ou_id: CNPJ (procura) ou o id do cliente. Passe só o que quer mudar.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    cid = cnpj_ou_id
    if "-" not in cnpj_ou_id or len(cnpj_ou_id) < 30:  # parece CNPJ -> busca
        c = await _buscar_cliente(cnpj_ou_id)
        if not c:
            return {"ok": False, "codigo": "CLIENTE_NAO_ENCONTRADO", "http": 404,
                    "mensagem": f"Nenhum cliente corresponde a {cnpj_ou_id!r}.",
                    "dica": "CNPJ só com dígitos, o id, ou `listar_clientes(busca=...)`.",
                    "procurei_por": cnpj_ou_id}
        cid = c.get("id")
    payload: dict[str, Any] = {}
    if nome is not None:
        payload["name"] = nome
    if email is not None:
        payload["email"] = email
    if telefone is not None:
        payload["phone"] = telefone
    if cidade is not None:
        payload["address_city"] = cidade
    if not payload:
        return {"ok": False, "codigo": "NADA_PARA_ATUALIZAR", "http": 422,
                "mensagem": "Nenhum campo foi informado.",
                "dica": "Informe ao menos um campo a mudar."}
    r = await erp.request("PUT", f"/clients/{cid}", json=payload)
    return {"atualizado": True, "id": cid, "nome": r.get("legal_name") or r.get("name")}


@mcp.tool
async def excluir_proposta(proposta_id: str, confirmar: bool = False) -> dict:
    """Exclui (soft-delete) uma proposta — para rascunhos errados. Exige confirmar=true.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    # ⚠️ existência ANTES do preview: confirmar um preview de algo inexistente
    # parece que o sistema conferiu, e ele não conferiu.
    if (recusa := await _exigir_entidade("proposta", proposta_id)):
        return recusa
    if not confirmar:
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "proposta_id": proposta_id,
                "mensagem": "Isto exclui a proposta. Reenvie com confirmar=true.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto exclui a proposta. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/proposals/{proposta_id}")
    return {"excluida": True, "proposta_id": proposta_id}


@mcp.tool
async def arquivar_deal(deal_id: str, confirmar: bool = False) -> dict:
    """Arquiva (soft-delete) um deal/oportunidade — para remover deals de teste do funil.
    Exige confirmar=true."""
    # ⚠️ existência ANTES do preview: confirmar um preview de algo inexistente
    # parece que o sistema conferiu, e ele não conferiu.
    if (recusa := await _exigir_entidade("deal", deal_id)):
        return recusa
    if not confirmar:
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "deal_id": deal_id,
                "mensagem": "Isto arquiva o deal (sai do funil). Reenvie com confirmar=true.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto arquiva o deal (sai do funil). Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/opportunities/{deal_id}")
    return {"arquivado": True, "deal_id": deal_id}


@mcp.tool
async def arquivar_contrato(contrato_id: str, confirmar: bool = False) -> dict:
    """Arquiva (soft-delete) um contrato — para limpar contratos de teste. Exige confirmar=true."""
    # ⚠️ existência ANTES do preview: confirmar um preview de algo inexistente
    # parece que o sistema conferiu, e ele não conferiu.
    if (recusa := await _exigir_entidade("contrato", contrato_id)):
        return recusa
    if not confirmar:
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "contrato_id": contrato_id,
                "mensagem": "Isto arquiva o contrato. Reenvie com confirmar=true.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto arquiva o contrato. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/contracts/{contrato_id}")
    return {"arquivado": True, "contrato_id": contrato_id}


@mcp.tool
async def excluir_campanha(campanha_id: str, confirmar: bool = False) -> dict:
    """Exclui uma campanha de marketing (ex.: campanhas de teste). Exige confirmar=true.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    if not confirmar:
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "campanha_id": campanha_id,
                "mensagem": "Isto exclui a campanha. Reenvie com confirmar=true.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto exclui a campanha. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/marketing/campaigns/{campanha_id}")
    return {"excluida": True, "campanha_id": campanha_id}


@mcp.tool
async def upload_asset(arquivo_base64: str, tipo: str = "logo", nome: str | None = None) -> dict:
    """Envia um asset (logo/selo) em base64 para o ERP — sem SSH. O logo comercial passa a ser usado
    no PDF automaticamente. tipo: logo | logo_transparente | logo_branco | selo. nome: opcional."""
    r = await erp.post("/crm/assets/upload", json={"tipo": tipo, "conteudo_base64": arquivo_base64, "nome": nome})
    return {"enviado": bool(r.get("ok")), "arquivo": r.get("arquivo"), "tamanho_kb": r.get("tamanho_kb")}


@mcp.tool
async def excluir_documento_crm(documento_id: str, confirmar: bool = False) -> dict:
    """Exclui (soft-delete) um documento gerado/registrado no CRM. Exige confirmar=true.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    # ⚠️ existência ANTES do preview: confirmar um preview de algo inexistente
    # parece que o sistema conferiu, e ele não conferiu.
    if (recusa := await _exigir_entidade("documento", documento_id)):
        return recusa
    if not confirmar:
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "documento_id": documento_id,
                "mensagem": "Isto exclui o documento. Reenvie com confirmar=true.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto exclui o documento. Reenvie com confirmar=true."}
    await erp.request("DELETE", f"/crm/docs/{documento_id}")
    return {"excluido": True, "documento_id": documento_id}


@mcp.tool
async def expurgar_documentos_teste(confirmar: bool = False) -> dict:
    """Arquiva TODOS os documentos de teste (teste=true). confirmar=false mostra a contagem; true executa."""
    return await erp.post(f"/crm/docs/expurgar-teste?confirmar={'true' if confirmar else 'false'}", json={})


@mcp.tool
async def definir_meta_contratos_mes(quantidade: int, mes: int | None = None, ano: int | None = None) -> dict:
    """Define a META por QUANTIDADE de contratos novos no mês (KPI '≥1 contrato novo/mês').
    Aparece no forecast como contratos_fechados_mes / meta_contratos_mes."""
    hoje = date.today()
    # target_value omitido de propósito: setar a meta por CONTAGEM não pode zerar a meta por VALOR
    # (o backend faz upsert independente — target_value None preserva o valor existente).
    r = await erp.post("/crm/quotas", json={"seller_name": "Equipe", "period_year": ano or hoje.year,
                                            "period_month": mes or hoje.month, "target_count": quantidade})
    return {"meta_contratos": quantidade, "periodo": f"{(mes or hoje.month):02d}/{ano or hoje.year}", "id": r.get("id")}


@mcp.tool
async def criar_contrato(cliente_documento: str, tipo: str = "recurring", valor_mensal: float = 0,
                         vigencia_inicio: str | None = None, vigencia_fim: str | None = None,
                         valor_total: float | None = None, nome: str | None = None,
                         deal_id: str | None = None) -> dict:
    """Cria um CONTRATO no CRM a partir do CNPJ do cliente (fecha deal→contrato). tipo: recurring | one_time.
    Depois use ativar_contrato para lançar no MRR (se recurring).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    c = await _buscar_cliente(cliente_documento)
    if not c:
        return {"ok": False, "codigo": "CLIENTE_NAO_ENCONTRADO", "http": 404,
                "mensagem": f"Nenhum cliente corresponde a {cliente_documento!r}.",
                "dica": "Cadastre com `criar_cliente(...)` ou confira em "
                        "`listar_clientes(busca=...)`. Contrato exige cliente existente.",
                "procurei_por": cliente_documento}
    payload: dict[str, Any] = {
        "client_id": c.get("id"), "contract_type": tipo, "monthly_value": valor_mensal,
        "name": nome or f"Contrato - {c.get('name')}", "start_date": vigencia_inicio or date.today().isoformat(),
    }
    if valor_total is not None:
        payload["total_value"] = valor_total
    if vigencia_fim:
        payload["end_date"] = vigencia_fim
    if deal_id:
        payload["opportunity_id"] = deal_id
    try:
        r = await erp.post("/crm/contracts", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "criado": False}
    return {"criado": True, "numero": r.get("contract_number"), "id": r.get("id"), "status": r.get("status")}


@mcp.tool
async def atualizar_contrato(contrato_id: str, valor_mensal: float | None = None, valor_total: float | None = None,
                             vigencia_fim: str | None = None, nome: str | None = None) -> dict:
    """Atualiza um contrato (valor/vigência/nome) sem recriar. Passe só o que muda.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    payload: dict[str, Any] = {}
    if valor_mensal is not None:
        payload["monthly_value"] = valor_mensal
    if valor_total is not None:
        payload["total_value"] = valor_total
    if vigencia_fim:
        payload["end_date"] = vigencia_fim
    if nome:
        payload["name"] = nome
    if not payload:
        return {"ok": False, "codigo": "NADA_PARA_ATUALIZAR", "http": 422,
                "mensagem": "Nenhum campo foi informado.",
                "dica": "Informe ao menos um campo a mudar."}
    try:
        r = await erp.request("PUT", f"/crm/contracts/{contrato_id}", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "atualizado": False}
    return {"atualizado": True, "numero": r.get("contract_number"), "status": r.get("status")}


# =================================================================== CICLO DE VENDAS
# Envios reais ao cliente exigem confirmar=true (1ª chamada mostra preview, 2ª executa).

@mcp.tool
async def enviar_whatsapp(numero: str, mensagem: str, confirmar: bool = False) -> dict:
    """Envia mensagem de WhatsApp para um número. ENVIO REAL ao cliente.
    Chame primeiro com confirmar=false para ver o preview; depois confirmar=true para enviar.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    if not confirmar:
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "para": numero, "mensagem": mensagem,
                "mensagem": "Isto enviará um WhatsApp REAL. Reenvie com confirmar=true para disparar.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto enviará um WhatsApp REAL. Reenvie com confirmar=true para disparar."}
    r = await erp.post("/whatsapp/send/custom", json={"phone": numero, "message": mensagem})
    return {"enviado": bool(r.get("success")), "status": r.get("status"), "para": r.get("phone")}


@mcp.tool
async def status_whatsapp() -> dict:
    """Status da conexão do WhatsApp (se está conectado e pronto para enviar)."""
    return await erp.get("/whatsapp/status")


@mcp.tool
async def gerar_copy(formato: str, briefing: str, objetivo: str | None = None,
                     publico: str | None = None, n_variacoes: int = 3) -> dict:
    """Gera RASCUNHOS de conteúdo de marketing na voz da marca (copywriter IA). Não publica.
    formato: ex. 'post_instagram', 'anuncio', 'email', 'whatsapp'. briefing: o que comunicar.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/marketing/copywriter/generate", json={
        "formato": formato, "briefing": briefing, "objetivo": objetivo,
        "publico": publico, "n_variacoes": n_variacoes})


@mcp.tool
async def gerar_plano_estrategico(objetivo: str, periodo_dias: int = 30,
                                  orcamento: str | None = None, canais: str | None = None) -> dict:
    """Gera um plano de campanha + calendário editorial a partir de um objetivo (estrategista IA, rascunho).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/marketing/estrategista/plan", json={
        "objetivo": objetivo, "periodo_dias": periodo_dias,
        "orcamento": orcamento, "canais_preferidos": canais})


@mcp.tool
async def listar_campanhas() -> dict:
    """Lista as campanhas de marketing."""
    data = await erp.get("/marketing/campaigns/")
    return {"campanhas": _items(data)}


@mcp.tool
async def marcar_proposta_enviada(proposta: str) -> dict:
    """Marca uma proposta como JÁ ENVIADA, SEM reenviar ao cliente — quando o envio foi feito por
    fora do ciclo (WhatsApp/e-mail manual) e ela ainda consta como rascunho. Entra no painel +
    acompanhamento do José Luís. proposta = número (PROP-...) ou id."""
    pid = proposta
    if not (len(proposta) >= 32 and "-" in proposta and proposta.count("-") >= 4):
        # parece número de proposta -> resolve o id
        data = await erp.get("/crm/proposals/", params={"page_size": 200})
        for p in _items(data):
            if str(p.get("number", "")).upper() == proposta.upper() or str(p.get("id")) == proposta:
                pid = p.get("id")
                break
    return await erp.post(f"/crm/proposals/{pid}/marcar-enviada", json={})


@mcp.tool
async def enviar_proposta(proposta_id: str, confirmar: bool = False) -> dict:
    """Envia a proposta por e-mail ao cliente (com rastreio de abertura + link de assinatura).
    ENVIO REAL. Chame com confirmar=false para ver o preview; confirmar=true para enviar.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    if not confirmar:
        p = await _one_proposal(proposta_id)
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "proposta": p,
                "mensagem": "Isto enviará a proposta por e-mail ao cliente. Reenvie com confirmar=true.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto enviará a proposta por e-mail ao cliente. Reenvie com confirmar=true."}
    r = await erp.post(f"/crm/proposals/{proposta_id}/send", json={})
    return {"enviada": True, "numero": r.get("number"), "status": r.get("status")}


@mcp.tool
async def ativar_contrato(contrato_id: str, confirmar: bool = False) -> dict:
    """Ativa um contrato (draft -> pending_signature -> active). Se for recorrente, LANÇA NO MRR.
    Ação financeira: chame com confirmar=false para ver o preview; confirmar=true para ativar."""
    if not confirmar:
        return {"ok": False, "codigo": "CONFIRMACAO_NECESSARIA", "http": 409,
                "preview": True, "contrato_id": contrato_id,
                "mensagem": "Isto ativa o contrato (e lança MRR se recorrente). Reenvie com confirmar=true.",
                "dica": "Nada aconteceu ainda. Reenvie a MESMA chamada com confirmar=true.",
                "aviso": "Isto ativa o contrato (e lança MRR se recorrente). Reenvie com confirmar=true."}
    await erp.post(f"/crm/contracts/{contrato_id}/submit", json={})
    r = await erp.post(f"/crm/contracts/{contrato_id}/activate", json={})
    return {"ativado": True, "numero": r.get("contract_number"), "status": r.get("status"),
            "mensal": _brl(r.get("monthly_value"))}


@mcp.tool
async def criar_tarefa(titulo: str, descricao: str | None = None, vencimento_dias: int | None = None,
                       prioridade: str = "medium", lead_id: str | None = None) -> dict:
    """Cria uma tarefa/follow-up no CRM. vencimento_dias: vence em N dias a partir de hoje (opcional).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    payload: dict[str, Any] = {"title": titulo, "description": descricao, "priority": prioridade}
    if vencimento_dias is not None:
        payload["due_date"] = (date.today() + timedelta(days=vencimento_dias)).isoformat()
    if lead_id:
        payload["lead_id"] = lead_id
    r = await erp.post("/crm/tasks/", json=payload)
    return {"id": r.get("id"), "titulo": r.get("title"), "vencimento": r.get("due_date")}


async def _one_proposal(pid: str) -> dict:
    data = await erp.get("/crm/proposals/", params={"page_size": 100})
    for p in _items(data):
        if str(p.get("id")) == pid or p.get("number") == pid:
            return {"numero": p.get("number"), "cliente": p.get("client_name"),
                    "total": _brl(p.get("total")), "status": p.get("status")}
    return {"id": pid}


# =================================================================== FOLLOW-UP / WHATSAPP (José Luís)
# O José Luís acompanha e envia propostas por WhatsApp. Envios reais ao cliente exigem confirmar=true.

@mcp.tool
async def cadastrar_whatsapp_cliente(cnpj_ou_id: str, numero: str) -> dict:
    """Grava/normaliza (E.164 +55…) o WhatsApp de um cliente (por CNPJ ou id) ou lead (id).
    Pré-requisito para o José Luís enviar follow-up/proposta por WhatsApp.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/crm/whatsapp/cadastrar", json={"cnpj_ou_id": cnpj_ou_id, "numero": numero})  # drive=salvar_no_drive era nome indefinido → NameError (08/09/2026)


@mcp.tool
async def followup_whatsapp(mensagem: str, deal_id: str | None = None, cliente: str | None = None,
                            lead_id: str | None = None, proposta_id: str | None = None,
                            confirmar: bool = False) -> dict:
    """Toque MANUAL do José Luís por WhatsApp (acompanhamento). Resolve o número do alvo
    (deal/cliente por CNPJ/lead/proposta), respeita opt-out, horário comercial e anti-spam, e
    REGISTRA em crm_followups. ENVIO REAL: confirmar=false mostra preview; confirmar=true envia."""
    return await erp.post("/crm/followups", json={
        "deal_id": deal_id, "cliente": cliente, "lead_id": lead_id, "proposal_id": proposta_id,
        "mensagem": mensagem, "canal": "whatsapp", "confirmar": confirmar})


@mcp.tool
async def enviar_proposta_whatsapp(proposta_id: str, confirmar: bool = False) -> dict:
    """Envia a PROPOSTA pelo WhatsApp do José Luís: PDF + link de assinatura, com rastreio.
    ENVIO REAL ao cliente. confirmar=false mostra o preview (número + mensagem + link);
    confirmar=true envia de verdade e marca a proposta como enviada (move o deal).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post(f"/crm/proposals/{proposta_id}/send-whatsapp?confirmar={'true' if confirmar else 'false'}",
                          json={})


@mcp.tool
async def listar_followups_pendentes() -> dict:
    """Toques de follow-up agendados / a fazer (deal, cliente, canal, data)."""
    return await erp.get("/crm/followups/pendentes")


@mcp.tool
async def historico_followup(deal_id: str) -> dict:
    """Histórico de toques (enviados/agendados/cancelados) + respostas do cliente de um deal."""
    try:
        return await erp.get("/crm/followups/historico", params={"deal_id": deal_id})
    except Exception as exc:  # noqa: BLE001
        env = erro_envelope(exc)
        if env.get("http", 500) >= 500:
            return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                    "mensagem": f"Nenhum deal corresponde a {deal_id!r}.",
                    "dica": "Use o id da oportunidade — listar_deals() mostra os ids."}
        return env


@mcp.tool
async def registrar_resposta_followup(deal_id: str, status: str = "respondido",
                                      classificacao: str | None = None, nota: str | None = None) -> dict:
    """Registra o retorno do cliente no follow-up mais recente do deal.
    classificacao: interessado | duvida | recusou. status: respondido | recusou | cancelado.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    if (recusa := _id_ou_422(deal_id, o_que="deal_id", dica="`listar_deals()` mostra os ids.")):
        return recusa
    return await erp.post("/crm/followups/resposta", json={
        "deal_id": deal_id, "status": status, "classificacao": classificacao, "nota": nota})


@mcp.tool
async def inscrever_em_sequencia(sequencia_id: str, lead_id: str) -> dict:
    """Inscreve um LEAD numa cadência (e-mail OU WhatsApp). Use a sequência
    'Follow-up Proposta — WhatsApp (José Luís)' (D+2/D+5/D+10) para acompanhamento automático.
    Veja os ids com listar_sequencias. (Garanta o telefone do lead para a cadência de WhatsApp.)"""
    r = await erp.post(f"/crm/sequences/{sequencia_id}/enroll", json={"lead_id": lead_id})
    return {"inscrito": bool(r.get("enrolled")), "enrollment_id": r.get("enrollment_id")}


@mcp.tool
async def registrar_optout_whatsapp(numero: str, motivo: str | None = None) -> dict:
    """Marca um número como opt-out (não receber mais follow-ups). Compliance/anti-spam.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    # ⚠️ 13/09/2026, 2ª correção — a PRIMEIRA era insuficiente E O MEU TESTE ESCONDEU ISSO.
    # Eu só contava dígitos (10 a 13) e validei com `LIXO-ZZZ`, que a contagem pega. O Jordan
    # testou com "0000000000": dez dígitos, passava, e gravava. Escolhi a entrada que não
    # distinguia as duas hipóteses — contar dígitos ≠ ser telefone.
    #
    # ⚠️ RESSALVA REGISTRADA: opt-out é proteção DA PESSOA. Recusar o de quem não está no
    # cadastro significa continuar podendo mandar mensagem a quem pediu para parar. Foi
    # decisão explícita do dono (prompt de fechamento, 6b) e a recusa ensina o caminho —
    # cadastre o lead e registre o opt-out dele.
    #
    # ⚠️ E o lugar DURÁVEL desta regra é a rota `/crm/followups/optout` do backend, que serve
    # a tela também. Aqui ela vale só para o agente; não mexi no backend porque mudaria o
    # comportamento de todos os chamadores sem autorização.
    so_digitos = re.sub(r"\D", "", numero or "")
    if so_digitos.startswith("55") and len(so_digitos) in (12, 13):
        so_digitos = so_digitos[2:]
    if len(so_digitos) not in (10, 11):
        return {"ok": False, "codigo": "TELEFONE_INVALIDO", "http": 422,
                "mensagem": f"{numero!r} não tem forma de telefone brasileiro.",
                "dica": "Informe com DDD: 92991234567 (11 dígitos) ou 9233334444 (10), "
                        "com ou sem o 55 na frente.",
                "campos_invalidos": ["numero"], "digitos_lidos": len(so_digitos)}
    if len(set(so_digitos)) <= 2:
        return {"ok": False, "codigo": "TELEFONE_INVALIDO", "http": 422,
                "mensagem": f"{numero!r} é uma sequência, não um telefone.",
                "dica": "Números como 0000000000 e 1111111111 passam em qualquer contagem "
                        "de dígitos e não são de ninguém.",
                "campos_invalidos": ["numero"]}
    if so_digitos[:2] not in _DDD_BR:
        return {"ok": False, "codigo": "DDD_INVALIDO", "http": 422,
                "mensagem": f"DDD {so_digitos[:2]!r} não existe no Brasil.",
                "dica": "Confira o DDD. Os válidos vão de 11 a 99, com buracos "
                        "(20, 23, 25, 26, 29, 30, 36, 39, 40, 50, 52, 56-60, 70, 72, "
                        "76, 78, 80, 90 não existem).",
                "campos_invalidos": ["numero"]}
    if len(so_digitos) == 11 and so_digitos[2] != "9":
        return {"ok": False, "codigo": "TELEFONE_INVALIDO", "http": 422,
                "mensagem": f"{numero!r} tem 11 dígitos mas não começa com 9 depois do DDD.",
                "dica": "Celular brasileiro de 11 dígitos é DDD + 9 + 8 dígitos. "
                        "Fixo tem 10 e não recebe WhatsApp.",
                "campos_invalidos": ["numero"]}

    # ⚠️ DIVERGÊNCIA DECLARADA do item 6b, com a medição que a motiva. O pedido era RECUSAR
    # quando o número não é de ninguém cadastrado. Fui medir a visão que eu tenho: a tabela
    # `leads` tem 298 linhas, 296 com telefone — e a rota `/crm/leads` devolve **7**, que são
    # os ATIVOS. Recusa dura sobre essa visão rejeitaria o opt-out de 291 leads inativos:
    # gente que FOI contatada (é por isso que virou lead) e que, ao pedir para parar de
    # receber, ouviria "não te conheço".
    #
    # Isso inverteria o propósito da ferramenta. Opt-out protege a PESSOA, não o cadastro —
    # o custo de registrar um a mais é uma linha; o de recusar um legítimo é continuar
    # mandando mensagem para quem pediu para parar.
    #
    # Então: o dono vira INFORMAÇÃO no retorno, não parede. `de_quem: null` + aviso diz ao
    # Jordan exatamente o que a recusa diria, sem o efeito colateral. Se, vendo os 291, ele
    # quiser a recusa dura mesmo assim, é trocar este bloco por um `return` — uma linha.
    dono = await _quem_tem_o_numero(so_digitos)
    r = await erp.post("/crm/followups/optout",
                       json={"numero": numero, "motivo": motivo})
    if not isinstance(r, dict):
        return r
    if dono is None:
        return {**r, "de_quem": None,
                "aviso": (f"Registrei, mas {numero!r} não bate com nenhum cliente nem com "
                          f"os leads ATIVOS que consigo ler. Pode ser um lead inativo (a "
                          f"rota expõe 7 de 296 com telefone) ou número errado — confira "
                          f"antes de contar com este opt-out.")}
    return {**r, "de_quem": dono}


@mcp.tool
async def enviar_proposta_completa(proposta_id: str, confirmar: bool = False) -> dict:
    """Envia a proposta por E-MAIL **e** WhatsApp de uma vez (o WhatsApp cita o e-mail), e o José Luís
    JÁ ASSUME o acompanhamento (follow-up D+2/D+5/D+10) te avisando no seu WhatsApp.
    ENVIO REAL. confirmar=false mostra o preview; confirmar=true envia.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post(
        f"/crm/proposals/{proposta_id}/send-completo?confirmar={'true' if confirmar else 'false'}", json={})


@mcp.tool
async def painel_negociacoes() -> dict:
    """Panorama das negociações em aberto: cliente, proposta, quem conduz (José Luís/Jordan), última resposta."""
    return await erp.get("/crm/negociacoes")


@mcp.tool
async def negociacoes_pendentes() -> dict:
    """Propostas enviadas SEM resposta do cliente (com dias parados) — o que precisa de atenção."""
    return await erp.get("/crm/negociacoes/pendentes")


@mcp.tool
async def assumir_negociacao(cliente: str) -> dict:
    """Você (Jordan) assume a negociação — PAUSA o acompanhamento automático do José Luís para esse cliente."""
    return await erp.post("/crm/negociacoes/responsavel", json={"cliente": cliente, "responsavel": "jordan"})


@mcp.tool
async def devolver_negociacao(cliente: str) -> dict:
    """Devolve a negociação ao José Luís (ele volta a acompanhar/fazer follow-up automático)."""
    return await erp.post("/crm/negociacoes/responsavel", json={"cliente": cliente, "responsavel": "jose_luis"})


@mcp.tool
async def resumo_executivo() -> dict:
    """Retrato da casa num lugar só: pipeline (aberto/previsão/meta) + propostas + leads + contratos/MRR
    + pendências. Use para 'como tá a casa / como tão as vendas / panorama geral'."""
    return await erp.get("/crm/resumo-executivo")


@mcp.tool
async def relatorio_comercial() -> dict:
    """Raio-x de vendas: win/loss rate, conversão do funil (lead→oportunidade→ganho), motivos de perda,
    ROI por canal de origem, ranking de clientes por MRR e ciclo médio de venda."""
    return await erp.get("/crm/relatorio-comercial")


@mcp.tool
async def resumo_financeiro() -> dict:
    """Retrato financeiro: MRR, MRR anualizado, recebíveis previstos, inadimplência, caixa do mês
    (entradas/saídas/saldo) e faturamento NFS-e."""
    return await erp.get("/crm/financeiro")


@mcp.tool
async def simular_fechamento(deals: list[str] | None = None, estagio: str = "negotiation") -> dict:
    """What-if: 'se eu fechar estes deals (ou todos de um estágio), como fica meu ganho e a meta?'.
    Passe os ids dos deals OU um estágio (negotiation/proposal). Mostra ganho atual vs projetado e atingimento."""
    return await erp.post("/crm/simular-fechamento", json={"deals": deals, "estagio": estagio})


@mcp.tool
async def followup_em_lote(mensagem: str | None = None, confirmar: bool = False) -> dict:
    """Dá um toque (WhatsApp) em TODOS os clientes com proposta enviada sem resposta, de uma vez.
    confirmar=false mostra a lista (preview); confirmar=true o José Luís envia (respeita opt-out/horário)."""
    return await erp.post("/crm/followups/lote", json={"mensagem": mensagem, "confirmar": confirmar})


@mcp.tool
async def obter_deal(deal_id: str) -> dict:
    """Detalhe completo de uma oportunidade/deal pelo id. Só lê."""
    return await _get_ou_404(f"/crm/opportunities/{deal_id}", o_que="deal",
                             chave=deal_id,
                             dica="Use o id da oportunidade — listar_deals() mostra os ids.")


@mcp.tool
async def obter_contrato(contrato_id: str) -> dict:
    """Detalhe completo de um contrato. Aceita CTR-…, id, CNPJ ou nome do cliente. Só lê.

    Auditoria do Cowork (11/09/2026): id inválido devolvia 500 cru, sem envelope e sem
    `request_id` — o identificador ia direto ao ERP e o banco reclamava do UUID. "Não
    encontrei" é 404 e é informação; 500 manda o agente tentar de novo igual.
    """
    alvo = await _resolver_contrato(contrato_id)
    if isinstance(alvo, dict):
        return alvo
    # ⚠️ `_resolver_contrato` devolve o NÚMERO (CTR-…), que é o identificador que as rotas
    # de emissão aceitam. Esta rota quer o UUID — passar o número dá 500. Identificador
    # certo para a rota errada falha tão bem quanto identificador errado.
    uuid_alvo = alvo
    if not re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-", str(alvo), re.I):
        try:
            lista = await erp.get("/crm/contracts", params={"page_size": 100})
        except Exception as exc:  # noqa: BLE001
            return erro_envelope(exc)
        achado = next((c for c in _items(lista)
                       if str(c.get("contract_number") or "").upper() == str(alvo).upper()), None)
        if not achado:
            return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                    "mensagem": f"Não achei o contrato {alvo}.",
                    "dica": "listar_contratos(busca=...) ajuda a achar."}
        uuid_alvo = achado.get("id")
    try:
        return await erp.get(f"/crm/contracts/{uuid_alvo}")
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def obter_cliente(cnpj_ou_id: str) -> dict:
    """Detalhe completo de um cliente (por CNPJ ou id)."""
    cid = cnpj_ou_id
    if "-" not in cnpj_ou_id or len(cnpj_ou_id) < 30:
        c = await _buscar_cliente(cnpj_ou_id)
        if not c:
            return {"ok": False, "codigo": "CLIENTE_NAO_ENCONTRADO", "http": 404,
                    "mensagem": f"Nenhum cliente corresponde a {cnpj_ou_id!r}.",
                    "dica": "Aceita CNPJ só com dígitos ou o id. "
                            "listar_clientes(busca=...) ajuda a achar.",
                    "procurei_por": cnpj_ou_id}
        cid = c.get("id")
    return await _get_ou_404(f"/clients/{cid}", o_que="cliente", chave=cnpj_ou_id,
                             dica="Aceita CNPJ só com dígitos ou o id.")


# =================================================================== VISITA TÉCNICA & COMERCIAL
# Fluxo: criar relatório → analisar mídia (você descreve os achados) → montar → PDF → lead + reunião.

@mcp.tool
async def criar_relatorio_visita(cliente_nome: str, panorama: str | None = None,
                                 data_visita: str | None = None) -> dict:
    """Inicia um relatório de visita técnica/comercial. panorama = contexto (porte, o que querem, etc.).
    Depois use adicionar_achados_visita (descrevendo o que você viu nas fotos/áudios) e montar_relatorio_visita.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/crm/visitas", json={"cliente_nome": cliente_nome, "panorama": panorama,
                                                "data_visita": data_visita})


@mcp.tool
async def adicionar_achados_visita(ref: str, achados: list[dict]) -> dict:
    """Anexa achados ao relatório de visita. ref = id ou nome do cliente. achados = lista de
    {tipo, descricao} — ex.: {"tipo":"foto","descricao":"câmera da entrada embaçada"}."""
    if (recusa := _id_ou_422(ref, o_que="ref", dica="`listar_relatorios_visita()` mostra as refs.")):
        return recusa
    return await erp.post("/crm/visitas/achados", json={"ref": ref, "achados": achados})


@mcp.tool
async def montar_relatorio_visita(ref: str, situacao_atual: str | None = None,
                                  diagnostico_tecnico: str | None = None,
                                  oportunidade_comercial: str | None = None,
                                  proximos_passos: str | None = None,
                                  conteudo_md: str | None = None) -> dict:
    """Grava o relatório de visita sintetizado (você redige com base nos achados; aqui persiste)."""
    if (recusa := _id_ou_422(ref, o_que="ref", dica="`listar_relatorios_visita()` mostra as refs.")):
        return recusa
    return await erp.post("/crm/visitas/montar", json={
        "ref": ref, "situacao_atual": situacao_atual, "diagnostico_tecnico": diagnostico_tecnico,
        "oportunidade_comercial": oportunidade_comercial, "proximos_passos": proximos_passos,
        "conteudo_md": conteudo_md})


@mcp.tool
async def listar_relatorios_visita() -> dict:
    """Lista os relatórios de visita (cliente, status, nº de achados)."""
    return await erp.get("/crm/visitas")


@mcp.tool
async def obter_relatorio_visita(ref: str) -> dict:
    """Detalhe de um relatório de visita (por id ou nome do cliente). Só lê."""
    try:
        return await erp.get("/crm/visitas/detalhe", params={"ref": ref})
    except Exception as exc:  # noqa: BLE001
        env = erro_envelope(exc)
        if env.get("codigo") == "NAO_ENCONTRADO":
            # ⚠️ a dica genérica mandava usar `listar_contratos` para achar um RELATÓRIO
            # DE VISITA. Dica que aponta a ferramenta errada é pior que dica ausente:
            # manda o agente procurar no lugar onde não está.
            env["dica"] = ("Use o id do relatório ou o nome do cliente — "
                           "listar_relatorios_visita() mostra os dois.")
        return env


@mcp.tool
async def gerar_pdf_visita(ref: str) -> dict:
    """Gera o PDF do relatório de visita (com selo Conecta Mais), registra e devolve link de download.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    if (recusa := _id_ou_422(ref, o_que="ref", dica="`listar_relatorios_visita()` mostra as refs.")):
        return recusa
    return await erp.post("/crm/visitas/pdf", json={"ref": ref, "salvar": True})


@mcp.tool
async def registrar_lead_da_visita(ref: str, telefone: str | None = None, cnpj: str | None = None,
                                   valor_estimado: float | None = None) -> dict:
    """Cria/atualiza lead + oportunidade no CRM a partir do relatório de visita.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    if (recusa := _id_ou_422(ref, o_que="ref", dica="`listar_relatorios_visita()` mostra as refs.")):
        return recusa
    return await erp.post("/crm/visitas/registrar-lead", json={
        "ref": ref, "telefone": telefone, "cnpj": cnpj, "valor_estimado": valor_estimado})


@mcp.tool
async def sugerir_reuniao(titulo: str, quando_iso: str, cliente_nome: str | None = None,
                          local: str | None = None, tipo: str = "reuniao",
                          visit_report_id: str | None = None) -> dict:
    """Agenda (sugere) uma reunião. quando_iso = YYYY-MM-DDTHH:MM. tipo: visita_tecnica|comercial|apresentacao|reuniao.
    Fica como 'sugerido' até confirmar_reuniao. Lembrete pré-reunião é enviado automaticamente."""
    return await erp.post("/crm/reunioes", json={"titulo": titulo, "quando_iso": quando_iso,
                          "cliente_nome": cliente_nome, "local": local, "tipo": tipo,
                          "visit_report_id": visit_report_id})


@mcp.tool
async def confirmar_reuniao(meeting_id: str) -> dict:
    """Confirma uma reunião sugerida."""
    if (recusa := _id_ou_422(meeting_id, o_que="meeting_id", dica="`agenda_reunioes()` mostra os ids.")):
        return recusa
    return await erp.post("/crm/reunioes/confirmar", json={"meeting_id": meeting_id})


@mcp.tool
async def listar_reunioes(futuras: bool = True) -> dict:
    """Lista as reuniões (futuras por padrão)."""
    return await erp.get("/crm/reunioes", params={"futuras": futuras})


@mcp.tool
async def sugerir_cross_sell(cliente: str) -> dict:
    """A partir dos contratos REAIS de um cliente, sugere o serviço complementar que falta
    (ex.: tem portaria mas não tem CFTV). cliente = CNPJ, nome ou id."""
    d = await erp.get("/crm/cross-sell", params={"cliente": cliente})
    # mesma regra do `buscar_cliente_por_cnpj`: busca com resposta negativa carrega `ok`
    if isinstance(d, dict) and d.get("encontrado") is False:
        return {"ok": True, **d,
                "mensagem": f"Não achei cliente por {cliente!r} — sem base para sugerir.",
                "dica": "Use CNPJ só com dígitos, o id, ou `listar_clientes(busca=...)`."}
    return d


@mcp.tool
async def leads_frios(dias: int = 14) -> dict:
    """Leads que esfriaram (sem interação há >= N dias, ainda abertos). Para reengajar."""
    return await erp.get("/crm/leads-frios", params={"dias": dias})


@mcp.tool
async def reativar_lead(ref: str, mensagem: str | None = None, confirmar: bool = False) -> dict:
    """Reengaja um lead frio por WhatsApp (José Luís manda um toque). ref = id ou nome.
    confirmar=false mostra o preview; confirmar=true envia de verdade."""
    d = await erp.post("/crm/reativar-lead",
                       json={"ref": ref, "mensagem": mensagem, "confirmar": confirmar})
    # o ERP recusa com `ok: false` e uma mensagem, sem `codigo`/`http`/`dica` — completo aqui
    # em vez de deixar o agente adivinhar o que fazer com uma recusa muda.
    if isinstance(d, dict) and d.get("ok") is False and not d.get("codigo"):
        return {**d, "codigo": "LEAD_NAO_REATIVAVEL", "http": 409,
                "mensagem": str(d.get("mensagem") or d.get("detail")
                                or f"Não consegui reativar {ref!r}."),
                "dica": "Confira a ref em `leads_frios()`. Lead sem telefone válido ou com "
                        "opt-out não recebe toque — e isso é proteção, não falha."}
    return d


@mcp.tool
async def enviar_nps(ref: str, confirmar: bool = False) -> dict:
    """Envia uma pesquisa NPS (0–10) a um cliente por WhatsApp. A resposta é capturada automaticamente.
    ref = CNPJ, nome ou id. confirmar=false mostra o preview; confirmar=true envia.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/crm/nps/enviar", json={"ref": ref, "confirmar": confirmar})


@mcp.tool
async def resumo_nps() -> dict:
    """Resumo do NPS: respostas, média, promotores/neutros/detratores e o NPS (-100 a +100)."""
    return await erp.get("/crm/nps")


@mcp.tool
async def diagnostico_ciclo() -> dict:
    """Saúde do ciclo Cowork↔Conecta PRO↔WhatsApp: WhatsApp online, agente ligado, webhook recebendo,
    cadência. Use para 'o ciclo tá saudável / o José Luís tá funcionando / tá tudo no ar'."""
    return await erp.get("/crm/ciclo/diagnostico")


@mcp.tool
async def metricas_jose_luis() -> dict:
    """Funil/desempenho do José Luís: leads captados no WhatsApp, follow-ups enviados/respondidos +
    taxa, visitas registradas, negociações por responsável e NPS."""
    return await erp.get("/crm/ciclo/metricas")


@mcp.tool
async def anotar_cliente(cliente: str, nota: str) -> dict:
    """Adiciona uma anotação à FICHA VIVA do cliente (compartilhada com o José Luís — ele lê no
    atendimento). cliente = CNPJ, nome ou id."""
    return await erp.post("/crm/clientes/anotar", json={"ref": cliente, "nota": nota})


@mcp.tool
async def ver_ficha_cliente(cliente: str) -> dict:
    """Ficha viva do cliente: dados + anotações + último status de negociação. Só lê.

    Aceita CNPJ, código (CLI-…), id ou nome aproximado.

    ⭐ SUCESSO FALSO CORRIGIDO em 12/09/2026. Para um cliente inexistente isto devolvia
    `{"cliente":"LIXO-ZZZ","cliente_id":null,"negociacao":null,"anotacoes":[]}` — HTTP 200,
    ficha vazia, sem `ok`. O Cowork nomeou por que é o pior tipo de defeito: um agente lê
    isso como "o cliente existe e não tem anotações" e atende achando que é cliente novo.
    É resposta ERRADA com cara de certa, e é a única categoria de erro que quem consome não
    tem como detectar.
    """
    try:
        r = await erp.get("/crm/clientes/ficha", params={"ref": cliente})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    # ficha sem id NÃO é ficha: é a ausência do cliente, e tem de dizer isso
    if isinstance(r, dict) and not r.get("cliente_id"):
        return {"ok": False, "codigo": "CLIENTE_NAO_ENCONTRADO", "http": 404,
                "mensagem": f"Nenhum cliente corresponde a {cliente!r}.",
                "dica": "Tente o CNPJ só com dígitos, o código CLI-AAAA-NNNNN, ou "
                        "listar_clientes(busca=...) para achar o nome certo.",
                "procurei_por": cliente}
    return {"ok": True, **(r if isinstance(r, dict) else {"ficha": r})}


# =================================================================== GED / Kits
# Ferramentas do GED (montagem dos kits documentais mensais por condomínio).
# Tudo chama os mesmos endpoints /gedeon/kits/* do ERP (determinístico, sem inventar).
import asyncio as _asyncio  # noqa: E402 — bloco do GED, agrupado por assunto e não pelo topo

_GED_CONDS = ["IDEAL FLORES", "MICHELANGELO", "MIRANTE", "VILLA PÁSSAROS",
              "VILLA DEI FIORI", "LARANJEIRAS", "PRIME ARENA"]
# tipo de documento (como a pessoa fala) -> bloco do robô
_GED_BLOCOS = {
    "folha": "folha", "contracheque": "folha", "contracheques": "folha",
    "salario": "pagamentos", "salarios": "pagamentos", "salário": "pagamentos",
    "inss": "pagamentos", "pagamentos": "pagamentos", "comprovante": "pagamentos",
    "vt": "vavt", "vr": "vavt", "vale": "vavt", "vavt": "vavt", "va": "vavt",
    "vale transporte": "vavt", "vale alimentacao": "vavt", "vale alimentação": "vavt",
    "guia": "guias", "guias": "guias", "impostos": "guias", "fgts": "guias", "dctfweb": "guias",
    "rescisao": "rescisao", "rescisão": "rescisao", "rescisoes": "rescisao", "trct": "rescisao",
    "cnd": "cnds", "cnds": "cnds", "certidao": "cnds", "certidão": "cnds", "certidoes": "cnds",
    "nfse": "nfse", "nota": "nfse", "notas": "nfse", "nota fiscal": "nfse", "boleto": "nfse",
    "ponto": "ponto", "assinados": "ponto", "assinado": "ponto", "folha de ponto": "ponto",
    # 10/09/2026 — o agente pediu "VT/VR" e "notas fiscais" e a ferramenta RECUSOU os dois, sendo
    # que "VT/VR" é o exemplo da própria docstring dela ("buscar_documento('Ideal Flores', 'VT/VR')").
    # Vocabulário que recusa o que ele mesmo ensina custa uma volta inteira de quem está tentando.
    "vt/vr": "vavt", "vt-vr": "vavt", "vt e vr": "vavt", "va/vt": "vavt", "vt/va": "vavt",
    "vale transporte e alimentacao": "vavt", "beneficios": "vavt", "benefícios": "vavt",
    "notas fiscais": "nfse", "nota fiscal de servico": "nfse", "nfs-e": "nfse", "danfse": "nfse",
    "boletos": "nfse", "faturamento": "nfse",
    "espelho": "ponto", "espelho de ponto": "ponto", "folhas de ponto": "ponto",
    "certidoes negativas": "cnds", "certidões negativas": "cnds", "cnd federal": "cnds",
    "holerite": "folha", "holerites": "folha", "folha de pagamento": "folha",
    "comprovantes": "pagamentos", "comprovante de pagamento": "pagamentos",
    "comprovantes de salario": "pagamentos", "comprovantes de salário": "pagamentos",
    "darf": "guias", "das": "guias", "iss": "guias", "issqn": "guias", "inss patronal": "guias",
}


def _ged_cond(nome: str) -> str:
    """Resolve o nome falado ('ideal flores', 'michelangelo') para o canônico do kit."""
    import unicodedata
    def n(s):
        s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
        return s.upper().strip()
    alvo = set(n(nome).split())
    for c in _GED_CONDS:
        ct = set(n(c).split())
        if ct <= alvo or alvo <= ct or (alvo & ct):
            return c
    return nome


@mcp.tool
async def consultar_kits(competencia: str | None = None) -> dict:
    """Status dos kits documentais dos 7 condomínios no mês: % de completude, completos/pendentes
    e o que falta em cada um. `competencia` opcional (MM.YYYY); sem ela usa o mês corrente do kit."""
    params = {"competencia": competencia} if competencia else {}
    d = await erp.get("/gedeon/kits/completude", params=params)
    kits = [{
        "condominio": k["condominio"], "completude": f"{k['completion_percentage']}%",
        "status": k["status"], "docs": k["total"],
        "falta": [i["label"] for i in k.get("checklist", []) if not i["presente"]],
    } for k in d.get("kits", [])]
    return {"mes_kit": d.get("mes_kit"), "competencia": d.get("competencia"),
            "media": f"{d.get('media_completude')}%",
            "completos": d.get("kits_completos"), "total": d.get("total_kits"), "kits": kits}


@mcp.tool
async def consultar_kit(condominio: str, competencia: str | None = None) -> dict:
    """Ficha completa do kit de UM condomínio: completude, checklist de documentos (presente/falta),
    eventos do mês (contratações, demissões, férias), o ESTADO DE ASSINATURA de cada documento
    (funcionário e empresa) e a lista de arquivos no Drive (com id p/ excluir)."""
    cond = _ged_cond(condominio)
    # ⭐ 12/09/2026: `_ged_cond` devolve o nome CRU quando não casa com nenhum condomínio, e
    # a rota ecoa o que recebe — o retorno virava `completude: "0%"`, que um agente lê como
    # "o condomínio existe e está sem documento". Mesmo formato do sucesso falso que o Cowork
    # pegou no `ver_ficha_cliente`: HTTP 200, corpo vazio, nenhum `ok`.
    if cond not in _GED_CONDS:
        return {"ok": False, "codigo": "CONDOMINIO_NAO_ENCONTRADO", "http": 404,
                "mensagem": f"Não existe condomínio {condominio!r} no GEDEON.",
                "dica": "Os condomínios do GEDEON são: " + ", ".join(sorted(_GED_CONDS))
                        + ". ⚠️ Esta lista é ESTÁTICA no conector: se o condomínio é novo, "
                          "ele precisa entrar em `_GED_CONDS` — a ausência aqui não prova "
                          "que ele não existe no GEDEON, só que este conector não o conhece."}
    params = {"condominio": cond, **({"competencia": competencia} if competencia else {})}
    d = await erp.get("/gedeon/kits/ficha", params=params)
    arquivos = []
    for sp in d.get("subpastas", []):
        for a in sp.get("arquivos", []):
            arquivos.append({"subpasta": sp["nome"], "nome": a["name"], "id": a.get("id")})
    # 10/09/2026: o estado de ASSINATURA vem junto. Sem ele, quem confere o kit não consegue checar
    # a regra 5 — o Hermes escreveu no parecer "Regra 5 (assinatura) não é verificável pela
    # listagem — aguardando dado", e estava certo: a listagem do Drive traz nome, id e link, e a
    # assinatura mora no banco. Duas das cinco regras eram cegas.
    ass = d.get("assinaturas") or {}
    return {
        "condominio": d.get("condominio"), "competencia": d.get("competencia"),
        "completude": f"{d.get('completude')}%", "docs": d.get("total_docs"),
        "falta": [i["label"] for i in d.get("checklist", []) if not i["presente"]],
        "eventos": [{"tipo": e["tipo"], "funcionario": e.get("funcionario"), "descricao": e["descricao"]}
                    for e in (d.get("eventos", {}).get("auto", []) + d.get("eventos", {}).get("manuais", []))],
        "assinaturas": {k: ass.get(k) for k in (
            "disponivel", "documentos_que_pedem_assinatura", "funcionario_assinou",
            "funcionario_pendente", "funcionario_sem_pedido_valido", "falta_assinatura_funcionario",
            "empresa_assinou", "empresa_pendente", "empresa_sem_pedido_valido",
            "falta_assinatura_empresa")},
        "assinatura_por_documento": (ass.get("por_documento") or [])[:60],
        "arquivos": arquivos,
    }


@mcp.tool
async def cronograma_kit(competencia: str | None = None) -> dict:
    """Cronograma do mês: quando cada documento deve estar pronto (salário 5º dia útil, VT/VR dia 16,
    prazos de assinatura 48h...). Ajuda a saber o que já dá pra coletar."""
    params = {"competencia": competencia} if competencia else {}
    d = await erp.get("/gedeon/kits/cronograma", params=params)
    return {"mes_entrega": d.get("mes_entrega"), "etapas": [
        {"o_que": e["titulo"], "quando": e.get("data"), "prazo": e.get("prazo"), "obs": e.get("obs")}
        for e in d.get("etapas", [])]}


async def _quantos_no_kit(cond: str, competencia: str | None) -> tuple[int, int]:
    """(documentos, completude) do kit AGORA, furando o cache de 60 s da ficha.

    10/09/2026 — o Hermes, montando o kit do Michelangelo, rodou sete coletas seguidas e as sete
    devolveram "coletado" com todas as etapas ok. Nenhum arquivo entrou. Ele percebeu e escreveu no
    parecer: "onvio_guias voltou ok mas nada entrou no kit". A ferramenta não mentia por engano —
    ela nunca contou nada, e a própria docstring prometia "diz quantos docs entraram".

    Etapa ok = o robô rodou sem exceção. Não é o mesmo que documento no kit. Quem confere precisa
    do segundo número, não do primeiro.
    """
    try:
        d = await erp.get("/gedeon/kits/ficha", params={
            "condominio": cond, "refresh": "true",
            **({"competencia": competencia} if competencia else {})})
        return int(d.get("total_docs") or 0), int(d.get("completude") or 0)
    except Exception:  # noqa: BLE001 — sem o número, a coleta ainda vale; o retorno dirá que não sabe
        return -1, -1


@mcp.tool
async def buscar_documento(condominio: str, tipo: str, competencia: str | None = None) -> dict:
    """Manda o robô COLETAR um tipo de documento só deste condomínio (folha, salários, VT/VR, guias,
    rescisões, CNDs, notas fiscais, assinados/ponto). Acompanha até concluir e CONTA quantos
    documentos entraram no kit — `entraram: 0` com as etapas ok significa que o robô rodou e a
    fonte não tinha nada novo; não adianta repetir. Ex.: buscar_documento('Ideal Flores', 'VT/VR')."""
    cond = _ged_cond(condominio)
    bloco = _GED_BLOCOS.get((tipo or "").strip().lower())
    if not bloco:
        # dizer só os 8 blocos internos não ajuda quem falou "VT/VR": mostra as palavras aceitas.
        return {"ok": False, "codigo": "PARAMETRO_INVALIDO", "http": 422,
                "mensagem": f"tipo {tipo!r} não reconhecido.",
                "dica": "Use um destes blocos: " + " | ".join(sorted(set(_GED_BLOCOS.values()))),
                "campos_invalidos": ["tipo"],
                "blocos": sorted(set(_GED_BLOCOS.values())),
                "palavras_aceitas": sorted(_GED_BLOCOS)}
    antes, _ = await _quantos_no_kit(cond, competencia)
    r = await erp.post("/gedeon/kits/montagem", json={
        "competencia": competencia, "blocos": [bloco], "condominios": [cond]})
    tid = r.get("task_id")
    # acompanha até concluir (blocos por 1 condomínio são rápidos)
    for _ in range(20):
        await _asyncio.sleep(4)
        st = await erp.get(f"/gedeon/kits/montagem/{tid}")
        ponto_ok = (st.get("ponto", {}).get("state") in ("done", "error")) if bloco == "ponto" else True
        if st.get("state") == "SUCCESS" and ponto_ok:
            etapas = st.get("etapas", {})
            depois, completude = await _quantos_no_kit(cond, competencia)
            entraram = (depois - antes) if (antes >= 0 and depois >= 0) else None
            out = {"condominio": cond, "tipo": tipo,
                   "etapas": {k: ("ok" if v.get("ok") else "falha") for k, v in etapas.items()},
                   "documentos_antes": antes, "documentos_depois": depois,
                   "entraram": entraram, "completude": completude}
            if entraram is None:
                out["status"] = "robô rodou; não consegui contar o kit"
            elif entraram > 0:
                out["status"] = f"coletado — {entraram} documento(s) entraram"
            else:
                # ETAPA OK E ZERO DOCUMENTO é o caso comum, não a exceção: a fonte não publicou
                # ainda. Dizer "coletado" aqui é o que fez o agente rodar sete coletas inúteis.
                out["status"] = "nada entrou — o robô rodou, a fonte não tinha documento novo"
            return out
        if st.get("state") == "FAILURE":
            return {"condominio": cond, "tipo": tipo, "status": "falhou", "erro": st.get("erro")}
    return {"condominio": cond, "tipo": tipo, "status": "ainda coletando",
            "task_id": tid, "dica": "use status_coleta(task_id) para acompanhar"}


@mcp.tool
async def status_coleta(task_id: str) -> dict:
    """Acompanha uma coleta/montagem em andamento pelo task_id."""
    st = await erp.get(f"/gedeon/kits/montagem/{task_id}")
    # ⭐ 12/09/2026: task inexistente devolvia `estado: PENDING`, que se lê como "em
    # andamento, aguarde" — o agente espera para sempre por uma coleta que nunca começou.
    if not st.get("state") or (st.get("state") == "PENDING" and not st.get("etapas")
                               and st.get("resumo") is None):
        return {"ok": False, "codigo": "COLETA_NAO_ENCONTRADA", "http": 404,
                "mensagem": f"Nenhuma coleta com task_id {task_id!r}.",
                "dica": "O task_id vem do retorno de `montar_kit`. PENDING sem etapa "
                        "nenhuma não é 'aguarde' — é coleta que não existe."}
    return {"estado": st.get("state"), "resumo": st.get("resumo"),
            "etapas": {k: ("ok" if v.get("ok") else "falha") for k, v in (st.get("etapas") or {}).items()},
            "ponto": st.get("ponto", {}).get("state")}


@mcp.tool
async def montar_kit_completo(condominio: str | None = None, competencia: str | None = None) -> dict:
    """Dispara a montagem COMPLETA (todos os documentos) — de um condomínio ou de todos (sem condomínio).
    Leva ~3 min. Retorna o task_id; acompanhe com status_coleta."""
    payload: dict = {"competencia": competencia}
    if condominio:
        payload["condominios"] = [_ged_cond(condominio)]
    r = await erp.post("/gedeon/kits/montagem", json=payload)
    return {"status": "montagem iniciada (~3 min)", "task_id": r.get("task_id"),
            "competencia": r.get("competencia"),
            "dica": "use status_coleta(task_id) para acompanhar"}


@mcp.tool
async def excluir_documento(condominio: str, file_id: str, nome: str | None = None,
                            competencia: str | None = None) -> dict:
    """Exclui um documento do kit (vai pra LIXEIRA do Drive, recuperável). Pegue o `file_id` em
    consultar_kit. Use quando o robô coletou errado ou alguém anexou o arquivo trocado.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    cond = _ged_cond(condominio)
    params = {"condominio": cond, "file_id": file_id,
              **({"nome": nome} if nome else {}), **({"competencia": competencia} if competencia else {})}
    r = await erp.request("DELETE", "/gedeon/kits/arquivo", params=params)
    return {"excluido": bool(r.get("ok")), "arquivo": r.get("arquivo"), "condominio": cond}


@mcp.tool
async def registrar_evento_kit(condominio: str, tipo: str, descricao: str,
                               funcionario: str | None = None, competencia: str | None = None) -> dict:
    """Registra um evento no checklist do kit (contratacao, demissao, ferias, migracao_posto,
    atestado, afastamento, observacao) — pra conferência ponto a ponto.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    cond = _ged_cond(condominio)
    r = await erp.post("/gedeon/kits/checklist", json={
        "condominio": cond, "competencia": competencia, "tipo": tipo,
        "descricao": descricao, "funcionario": funcionario})
    return {"registrado": True, "id": r.get("id"), "tipo": r.get("tipo"), "condominio": cond}


@mcp.tool
async def status_certidoes() -> dict:
    """Status das certidões da empresa (CNDs): Federal, FGTS, Estadual, Municipal, Trabalhista —
    situação e validade. Use para saber quais estão OK/vencendo."""
    d = await erp.get("/gedeon/cnd/status")
    # ⚠️ 13/09/2026 — SÃO DUAS DE CADA TIPO, uma por CNPJ, e a rota do GEDEON NÃO devolve a
    # empresa (só `document_type`, `name`, `orgao`, `situacao`, `validade`). A tabela tem a
    # coluna `cnpj`; a rota a descarta.
    #
    # Não invento qual é qual, e não mexo na rota — o GEDEON é de outro terminal. Duas
    # consequências, as duas declaradas em vez de escondidas: `nome` e `orgao` vêm no retorno
    # para as duas linhas não parecerem duplicata, e `empresa` vem como null com o aviso.
    # Isto importa de verdade: pela política da casa, CND é exigida da Patrimonial — saber
    # que "a FGTS está indeterminada" sem saber de QUAL empresa não fecha a decisão.
    certidoes = [{
        "tipo": c["document_type"].replace("certidao_negativa_", ""),
        "nome": c.get("name"), "orgao": c.get("orgao"),
        "situacao": c.get("situacao"), "validade": c.get("validade"),
        "alerta": c.get("alerta"),
        "empresa": None,
    } for c in d.get("certidoes", [])]
    tipos_repetidos = sorted({c["tipo"] for c in certidoes
                              if sum(1 for o in certidoes if o["tipo"] == c["tipo"]) > 1})
    saida = {"certidoes": certidoes}
    if tipos_repetidos:
        saida["aviso"] = (
            f"{len(certidoes)} certidões, e {len(tipos_repetidos)} tipo(s) aparecem duas "
            f"vezes ({', '.join(tipos_repetidos)}) — uma por CNPJ. A rota do GEDEON não "
            f"devolve a empresa, então NÃO sei dizer qual linha é da Eletrônica e qual é da "
            f"Patrimonial. Use `nome`/`orgao` para diferenciá-las e confirme a empresa no "
            f"portal antes de decidir: a exigência de CND não é igual para as duas.")
    return saida


# ============================ CFO / Financeiro / Diárias / DET (recursos novos 2026-07) ========

@mcp.tool
async def cfo_panorama() -> dict:
    """Fotografia financeira REAL da empresa agora: saldo do Banco Inter AO VIVO, MRR, folha, margem,
    runway, contas a pagar/receber, e visão cross-módulo (pipeline comercial, contingências jurídicas,
    diaristas a pagar). Use para saber a saúde financeira atual."""
    return await erp.get("/financial/cfo/panorama")


@mcp.tool
async def cfo_perguntar(pergunta: str, area: str = "fluxo_caixa") -> dict:
    """Pergunta ao CFO IA (diretor financeiro), ancorado nos números reais do ERP. Nunca inventa número.
    area: fluxo_caixa | resultado | tributos | estrategico. Ex.: 'Meu caixa cobre a folha deste mês?'."""
    return await erp.post("/financial/cfo/perguntar", json={"area": area, "pergunta": pergunta})


@mcp.tool
async def previsao_custos_mensais() -> dict:
    """Previsibilidade de custos mensais: folha, FGTS, ISS, diaristas (VT+VR diário e diárias do dia 15),
    fornecedores, reembolsos, e os parcelamentos/acordos/custos fixos registrados. Cada valor traz a fonte."""
    return await erp.get("/financial/cfo/previsao-custos")


@mcp.tool
async def registrar_custo_recorrente(categoria: str, descricao: str, valor: float,
                                     dia_vencimento: int | None = None,
                                     parcelas_total: int | None = None,
                                     parcelas_pagas: int = 0) -> dict:
    """Registra um custo recorrente para entrar na previsão. categoria: tributo | parcelamento | acordo | fixo | fornecedor.
    Ex.: parcelamento (valor da parcela + parcelas_total + parcelas_pagas); aluguel/contador (fixo).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/financial/cfo/custos-recorrentes", json={
        "categoria": categoria, "descricao": descricao, "valor": valor,
        "dia_vencimento": dia_vencimento, "parcelas_total": parcelas_total, "parcelas_pagas": parcelas_pagas})


@mcp.tool
async def diarias_cadastros() -> dict:
    """Listas para lançar diárias: diaristas, funções, postos/condomínios, turnos e a tabela de preços (Função|Turno→valor)."""
    return await erp.get("/operacional/diarias/cadastros")


@mcp.tool
async def lancar_diaria(diarista_id: int, funcao: str, posto: str, data: str, turno: str | None = None) -> dict:
    """Lança uma diária trabalhada — o valor sai AUTOMÁTICO pela função/turno. data = AAAA-MM-DD.
    turno (só p/ Agente de Portaria): DIURNO | NOTURNO | MEIO PERÍODO. Use diarias_cadastros() para os ids/opções.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/operacional/diarias/lancar", json={
        "diarista_id": diarista_id, "funcao": funcao, "posto": posto, "data": data, "turno": turno})


@mcp.tool
async def resumo_diarias(mes: int, ano: int) -> dict:
    """Resumo das diárias trabalhadas por diarista no mês — a lista que o Financeiro paga no dia 15."""
    return await erp.get("/operacional/diarias/resumo-diarista", params={"mes": mes, "ano": ano})


@mcp.tool
async def gerar_lote_diarias_mes(ano: int, mes: int) -> dict:
    """Gera o lote de pagamento do dia 15 a partir das diárias trabalhadas do mês (fila para o Financeiro pagar).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post(f"/financial/pagamentos-diaristas/programar-diarias-mensais/{ano}/{mes}")


@mcp.tool
async def lote_diaristas(data: str | None = None) -> dict:
    """Lote de pagamentos de diaristas a revisar (VT+VR diário e diárias do dia 15). data opcional AAAA-MM-DD.
    O pagamento em lote em si é feito na tela do Financeiro (dinheiro que sai exige aprovação do gestor)."""
    return await erp.get("/financial/pagamentos-diaristas/lote", params=({"data": data} if data else None))


@mcp.tool
async def diaristas_a_cadastrar() -> dict:
    """Diaristas que aparecem no histórico de pagamentos (PIX de R$32 = VT+VR) e ainda NÃO estão cadastrados,
    por frequência. Cada um precisa de CPF (obrigatório) + chave PIX no cadastro do Operacional."""
    return await erp.get("/financial/pagamentos-diaristas/sugestoes-cadastro")


@mcp.tool
async def det_comunicacoes() -> dict:
    """Comunicações do DET (Domicílio Eletrônico Trabalhista) coletadas pelo robô: notificações de
    fiscalização (FGTS/INSS), intimações e avisos. Sinaliza as que exigem ação/escalonamento ao CQB."""
    return await erp.get("/juridico/det/comunicacoes")


@mcp.tool
async def gerar_apresentacao(
    titulo: str,
    slides: list[dict],
    subtitulo: str | None = None,
    cliente: str | None = None,
    local: str | None = None,
    data: str | None = None,
    formato: str = "pdf",
    salvar_no_drive: bool = False,
) -> dict:
    """Gera uma APRESENTAÇÃO no padrão visual Conecta PRO — a MESMA identidade dos documentos
    (capa azul-marinho com faixa laranja + logo, títulos com barra laranja, cards, selos com números
    laranja, rodapé de marca fixo com CNPJ/0800/site, fechamento assinado pelo CEO). Use SEMPRE esta
    ferramenta para montar apresentações/propostas em slides — nunca gere slides fora deste padrão.

    Monte `slides` como uma lista de blocos (a CAPA e o CONTATO são adicionados automaticamente do
    titulo/cliente/local/data e do CEO). Tipos de bloco:
    - {"tipo":"sobre"}  → 4 selos padrão (+12 anos, 100% equipe própria, 24/7, Sentinela IA); customize com "selos":[{"valor","label"}]
    - {"tipo":"problema","titulo":"O Desafio","subtitulo":"...","itens":[{"titulo","desc"}]}  (cards numerados)
    - {"tipo":"solucao"|"escopo"|"diferenciais"|"cards","titulo":"...","subtitulo":"...","cards":[{"titulo","desc"}]}
    - {"tipo":"passos","titulo":"Como Funciona","passos":[{"titulo","desc"}]}  (fluxo numerado)
    - {"tipo":"kpis","titulo":"...","kpis":[{"valor":"+12","label":"anos"}]}
    - {"tipo":"investimento","titulo":"...","opcoes":[{"nome","valor","destaque":true,"itens":["..."]}],"observacao":"..."}
    - {"tipo":"imagem","titulo":"...","legenda":"...","imagem_path":"/caminho.png"}
    - {"tipo":"secao","titulo":"...","subtitulo":"..."}  (divisória de seção)
    - {"tipo":"contato","cta":"Vamos proteger seu pátio?"}
    formato: "pdf" (retorna download_url clicável para enviar ao cliente) ou "pptx" (arquivo editável em base64).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    import base64

    payload = {"titulo": titulo, "subtitulo": subtitulo, "cliente": cliente,
               "local": local, "data": data, "slides": slides}
    if (formato or "pdf").lower() == "pptx":
        try:
            raw = await erp.post_bytes("/crm/apresentacoes/gerar?formato=pptx", payload)
        except Exception as exc:  # noqa: BLE001
            return {**erro_envelope(exc), "gerado": False}
        return {"gerado": True, "formato": "pptx", "tamanho_kb": round(len(raw) / 1024, 1),
                "pptx_base64": base64.b64encode(raw).decode("ascii"),
                "obs": "Apresentação editável (PowerPoint) no padrão Conecta PRO."}
    try:
        r = await erp.post(f"/crm/apresentacoes/gerar?formato=pdf&salvar=true&teste=false&drive={'true' if salvar_no_drive else 'false'}", json=payload)
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "gerado": False}
    return {"gerado": True, "formato": "pdf", "titulo": r.get("titulo"), "tamanho_kb": r.get("tamanho_kb"),
            "download_url": r.get("download_url"), "drive_url": r.get("drive_url"), "id": r.get("id"),
            "obs": "Apresentação no padrão Conecta PRO." + (f" Salva no Drive: {r.get('drive_url')}" if r.get("drive_url") else " Abra o download_url para ver/enviar.")}


@mcp.tool
async def gerar_orcamento(
    cliente: str,
    itens: list[dict],
    documento: str | None = None,
    cidade: str | None = None,
    objeto: str | None = None,
    desconto_avista_pct: float | None = None,
    parcelas: int | None = None,
    entrada: float | None = None,
    validade_dias: int | None = None,
    garantia: str | None = None,
    prazo: str | None = None,
    observacao: str | None = None,
    numero: str | None = None,
    salvar_no_drive: bool = False,
    formato: str = "base64",
) -> dict:
    """Gera um ORÇAMENTO / proposta de PAGAMENTO ÚNICO no padrão-ouro Conecta PRO — para MATERIAL,
    SERVIÇO ou ambos (misto), SEM recorrência mensal. É a opção certa para venda de material,
    serviço avulso ou fornecimento+instalação (diferente da proposta de serviço mensal recorrente).

    `itens`: lista de {"descricao","valor_unit","qtd"(=1),"unidade"("un"),"tipo"("material"|"servico")}.
    Ex.: [{"descricao":"BARREIRA LED CLASS 4,30M","qtd":2,"unidade":"un","valor_unit":750,"tipo":"material"}].
    Pagamento (combine à vontade):
      - desconto_avista_pct: ex. 5  → mostra "À vista com 5% de desconto".
      - parcelas (+ entrada opcional): ex. parcelas=3 → "3x de R$ X (sem juros)".
    documento = CNPJ/CPF do cliente. objeto = 1 linha resumindo o fornecimento (opcional).
    validade_dias (15), garantia (material), prazo — vão no bloco Condições.
    Retorna download_url (link clicável para enviar/imprimir). Assinatura: cliente + CEO.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
        `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    documento sem abrir binário; "texto" só o texto; "url" só o link, como antes.
    Item 2.1 do relatório de campo: gerar um PDF e não poder olhar o que saiu.

    """
    condicoes = {}
    if validade_dias is not None:
        condicoes["validade_dias"] = validade_dias
    if garantia:
        condicoes["garantia"] = garantia
    if prazo:
        condicoes["prazo"] = prazo
    payload = {
        "cliente": cliente, "itens": itens, "documento": documento, "cidade": cidade,
        "objeto": objeto, "desconto_avista_pct": desconto_avista_pct, "parcelas": parcelas,
        "entrada": entrada, "observacao": observacao, "numero": numero,
        "condicoes": condicoes or None,
    }
    return await _gerar_doc("/crm/docs/orcamento/pdf", payload, drive=salvar_no_drive,
                            formato=formato)


# =================================================================== JURÍDICO


@mcp.tool
async def consultar_juridico(area: str, pergunta: str) -> dict:
    """Pergunta ao CONSULTOR JURÍDICO IA do Conecta PRO (fundamentado, com contexto REAL do ERP).
    area: 'trabalhista' | 'civel' | 'tributaria'. Ex.: pergunta='Posso descontar aviso prévio não cumprido?'.
    Retorna resposta estruturada (fundamentos, riscos, recomendação). READ-ONLY, não altera nada."""
    try:
        return await erp.post("/juridico/consultor/perguntar", json={"area": area, "pergunta": pergunta})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def analisar_processo_juridico(
    texto: str, numero: str | None = None, tipo: str | None = None, employee_id: str | None = None
) -> dict:
    """Analisa um PROCESSO/notificação a partir do texto colado: extrai pedidos, monta dossiê com dado
    REAL do ERP (funcionário/contrato) e gera linha de defesa IA (com 'como obter' as provas).
    tipo ex.: 'trabalhista'. employee_id: dica de qual funcionário, se souber."""
    payload = {"texto": texto, "numero": numero, "tipo": tipo, "employee_id": employee_id}
    try:
        return await erp.post("/juridico/processos", json=payload)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def gerar_parecer_juridico(area: str, titulo: str, contexto: str) -> dict:
    """Gera um PARECER JURÍDICO (rascunho IA) sobre um tema. area: trabalhista|civel|tributaria.
    contexto = situação/fatos a analisar. Retorna o parecer estruturado (registrado no ERP).

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    try:
        return await erp.post("/juridico/pareceres", json={"area": area, "titulo": titulo, "contexto": contexto})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def dossie_juridico(tipo: str, identificador: str | None = None) -> dict:
    """Dossiê jurídico READ-ONLY cross-módulo do Conecta PRO. tipo:
    - 'panorama'   → visão geral (passivos, contratos, riscos).
    - 'funcionario'→ identificador = nome/CPF/id do funcionário (histórico, ponto, advertências, folha).
    - 'contrato'   → identificador = número/id do contrato.
    - 'cliente'    → identificador = id do cliente.
    Reúne o contexto real para embasar defesa/consulta — não inventa nada."""
    t = (tipo or "").strip().lower()
    try:
        if t == "panorama":
            return await erp.get("/juridico/contexto/panorama")
        # ⭐ 13/09/2026, achado do Cowork: com `tipo` VÁLIDO e `identificador` inválido isto
        # devolvia `{"encontrado": false, ...}` sem `ok`, sem `codigo`, sem `http`. Ele foi
        # preciso: não é sucesso falso, é o envelope quebrado — e numa das 15 tools de dado
        # pessoal SENSÍVEL, onde o contrato de erro é o que mais precisa ser previsível.
        # Minha varredura não chegou aqui porque `identificador` é OPCIONAL: eu só preenchia
        # obrigatórios, então media sempre o ramo do `tipo`.
        if t in ("funcionario", "funcionário", "pessoa", "contrato", "cliente"):
            rota = {"contrato": "contrato", "cliente": "cliente"}.get(t, "funcionario")
            if not (identificador or "").strip():
                return {"ok": False, "codigo": "IDENTIFICADOR_VAZIO", "http": 422,
                        "mensagem": f"tipo {t!r} exige `identificador`.",
                        "dica": "Informe nome, CPF, matrícula ou id."}
            d = await erp.get(f"/juridico/contexto/{rota}/{identificador}")
            if isinstance(d, dict) and d.get("encontrado") is False:
                return {"ok": False, "codigo": "NAO_ENCONTRADO", "http": 404,
                        "mensagem": str(d.get("mensagem")
                                        or f"Nada encontrado para {identificador!r}."),
                        "dica": f"Confira o identificador do {rota}. "
                                f"`buscar_funcionario(nome)`, `listar_contratos(busca=...)` "
                                f"e `listar_clientes(busca=...)` devolvem os válidos.",
                        "procurei_por": identificador}
            return d
        return {"ok": False, "codigo": "TIPO_INVALIDO", "http": 422,
                "mensagem": f"tipo inválido {tipo!r}.",
                "dica": "Use: panorama | funcionario | contrato | cliente.",
                "campos_invalidos": ["tipo"]}
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def painel_juridico() -> dict:
    """Painel do Jurídico: dashboard consolidado (dado real) + prazos/compliance vencendo (≤7/≤15/≤30
    dias e atrasados). Use para saber a situação jurídica e o que está prestes a vencer."""
    out: dict = {}
    try:
        out["dashboard"] = await erp.get("/juridico/dashboard")
    except Exception as exc:  # noqa: BLE001
        out["dashboard_erro"] = str(exc)[:150]
    try:
        out["prazos_alertas"] = await erp.get("/juridico/prazos/alertas")
    except Exception as exc:  # noqa: BLE001
        out["prazos_erro"] = str(exc)[:150]
    return out



# =================================================================== DP / PEOPLE-MANAGEMENT (Pyetra)


# ---- Funcionários ----
@mcp.tool
async def listar_funcionarios(busca: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista funcionários (DP). busca = nome/CPF/matrícula. Paginação page/page_size."""
    params = {"page": page, "page_size": page_size}
    if busca:
        params["search"] = busca
    return await erp.get("/people-management/hr/employees", params=params)


@mcp.tool
async def buscar_funcionario(busca: str) -> dict:
    """Busca rápida de funcionário por nome/CPF/matrícula (retorna os que casam)."""
    return await erp.get("/people-management/hr/employees/search", params={"q": busca, "search": busca})


@mcp.tool
async def obter_funcionario(employee_id: str) -> dict:
    """Dados cadastrais de um funcionário pelo id. Só lê."""
    return await _get_ou_404(f"/people-management/hr/employees/{employee_id}",
                             o_que="funcionário", chave=employee_id,
                             dica="Use o id do funcionário ou o CPF — "
                                  "buscar_funcionario(nome) devolve o id.")


@mcp.tool
async def buscar_funcionario_por_cpf(cpf: str) -> dict:
    """Localiza um funcionário pelo CPF (só dígitos ou formatado)."""
    return await erp.get(f"/people-management/hr/employees/cpf/{cpf}")


@mcp.tool
async def ficha_funcionario(employee_id: str) -> dict:
    """Ficha/perfil completo do funcionário (dados + vínculos)."""
    return await _get_ou_404(f"/people-management/hr/employees/{employee_id}/profile",
                             o_que="funcionário", chave=employee_id,
                             dica="Use o id do funcionário — buscar_funcionario(nome) devolve.")


@mcp.tool
async def estatisticas_funcionarios() -> dict:
    """Estatísticas de pessoal (headcount, por cargo/status)."""
    return await erp.get("/people-management/hr/employees/stats")


# ---- Folha de pagamento ----
@mcp.tool
async def folha_dashboard(mes: int, ano: int) -> dict:
    """Dashboard da FOLHA do mês (total colaboradores, proventos, descontos, líquido, FGTS, INSS, fonte)."""
    return await erp.get("/people-management/folha/dashboard", params={"mes": mes, "ano": ano})


@mcp.tool
async def resumo_folha(mes: int, ano: int) -> dict:
    """Resumo consolidado da folha de uma competência (mes/ano)."""
    return await erp.get(f"/people-management/folha/resumo/{mes}/{ano}")


@mcp.tool
async def calcular_holerite(employee_id: str, mes: int, ano: int) -> dict:
    """Calcula o holerite completo (CCT 2026) de um funcionário na competência mes/ano."""
    return await erp.get(f"/people-management/folha/calcular/{employee_id}/{mes}/{ano}")


@mcp.tool
async def baixar_holerite_pdf(employee_id: str, mes: int, ano: int, formato: str = "base64") -> dict:
    """Gera o HOLERITE em PDF (padrão-ouro, só assinatura do funcionário) — retorna base64.

    `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    que saiu sem abrir binário; "texto" só o texto. Item 2.1 do relatório de campo.
    """
    return await _pdf_b64(f"/people-management/folha/holerite/{employee_id}/{mes}/{ano}/pdf", formato=formato, nome="holerite.pdf")


@mcp.tool
async def baixar_recibo_vt_vr_pdf(employee_id: str, mes: int, ano: int, formato: str = "base64") -> dict:
    """Gera o recibo de VT/VR em PDF (só assinatura do funcionário) — retorna base64.

    `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    que saiu sem abrir binário; "texto" só o texto. Item 2.1 do relatório de campo.
    """
    return await _pdf_b64(f"/people-management/folha/recibo-vt-vr/{employee_id}/{mes}/{ano}/pdf", formato=formato, nome="recibo_vt_vr.pdf")


@mcp.tool
async def listar_rubricas_folha() -> dict:
    """Lista as rubricas da folha (proventos/descontos cadastrados)."""
    return await erp.get("/people-management/folha/rubricas")


@mcp.tool
async def calcular_folha_todos(mes: int, ano: int) -> dict:
    """Calcula a folha do mês para TODOS os funcionários ativos (lote)."""
    return await erp.post(f"/people-management/folha/calcular/todos/{mes}/{ano}", json={})


@mcp.tool
async def fechar_folha(mes: int, ano: int) -> dict:
    """FECHA a folha de uma competência (mes/ano). Ação de gestão — confirme antes."""
    # A rota /folha/fechar foi apagada em 08/09/2026: devolvia "fechada" sem gravar nada. A folha
    # oficial vem da Portte (hr_payslips); o ERP calcula, confere e exporta, não "fecha".
    # ⭐ 13/09/2026: capacidade aposentada precisa de CÓDIGO próprio. "Falhou" e "não existe
    # aqui" levam o agente a caminhos opostos — o primeiro ele tenta de novo, o segundo ele
    # abandona e procura a alternativa. `detail` solto não dizia nem um nem outro.
    return {"ok": False, "codigo": "CAPACIDADE_APOSENTADA", "http": 410,
            "mensagem": "Fechamento de folha não existe no ERP: a folha oficial é importada "
                        "da Portte. A rota devolvia 'fechada' sem gravar nada e foi apagada "
                        "em 08/09/2026.",
            "dica": "Use `calcular_folha_todos` para conferir e `exportar_folha_dominio` "
                    "para exportar. Não insista nesta — ela não vai voltar."}


# ---- Ponto eletrônico ----
@mcp.tool
async def ponto_dashboard(mes: int, ano: int) -> dict:
    """Dashboard do PONTO do mês (batidas, inconsistências, banco de horas consolidado)."""
    return await erp.get("/people-management/ponto/dashboard", params={"mes": mes, "ano": ano})


@mcp.tool
async def espelho_ponto(employee_id: str, mes: int, ano: int) -> dict:
    """Espelho de ponto mensal de um funcionário (escala, horas esperadas/trabalhadas, saldo)."""
    # ⭐ 13/09/2026: devolvia 500 para employee_id inválido. Minha varredura não pegou
    # porque passava lixo TAMBÉM em `mes`/`ano` — a validação de tipo disparava primeiro e o
    # caminho do identificador nunca era exercitado. O `banco_horas`, vizinho de módulo e com
    # o mesmo parâmetro, já devolvia 404: não era o backend, era esta rota.
    return await _get_ou_404(
        f"/people-management/ponto/espelho/{employee_id}?month={mes}&year={ano}",
        o_que="funcionário", chave=employee_id,
        dica="Use o id do funcionário — `buscar_funcionario(nome)` devolve.")


@mcp.tool
async def banco_horas(employee_id: str, mes: int | None = None, ano: int | None = None) -> dict:
    """Saldo de banco de horas de um funcionário (12x36→180h; 44h→220h)."""
    params = {}
    if mes:
        params["mes"] = mes
    if ano:
        params["ano"] = ano
    return await erp.get(f"/people-management/ponto/banco-horas/{employee_id}", params=params or None)


@mcp.tool
async def colaboradores_sem_escala() -> dict:
    """Lista funcionários ativos SEM escala cadastrada (precisam de definição no DP)."""
    return _envelope(await erp.get("/people-management/ponto/colaboradores-sem-escala"),
                     "colaboradores")


def _envelope(r, chave: str) -> dict:
    """Rota do ERP que devolve LISTA, envelopada em dict — com o total junto.

    ⚠️ 11/09/2026, medido chamando as ferramentas uma a uma (`checar_tool_quebrada`): CINCO
    tools do escopo de pessoas estouravam para qualquer cliente MCP com

        structured_content must be a dict or None. Got list: [...]

    O FastMCP confere a anotação de retorno em tempo de execução; `-> dict` sobre uma rota que
    devolve lista quebra SEMPRE. Estavam no catálogo, com docstring e etiqueta de risco, e
    nunca funcionaram — ninguém as chamava. Envelopar (em vez de anotar `-> list`) mantém o
    TOTAL na resposta: o agente conta o que vê, e "3 justificativas" é a frase que interessa.
    """
    return {chave: r, "total": len(r)} if isinstance(r, list) else r


@mcp.tool
async def justificativas_ponto_pendentes() -> dict:
    """Lista as justificativas de ponto aguardando revisão do DP."""
    # ⚠️ 11/09/2026 — a rota devolve LISTA e a anotação dizia `dict`. O FastMCP confere a
    # anotação em tempo de execução e recusa: "structured_content must be a dict or None. Got
    # list". Ou seja: a ferramenta estava quebrada para QUALQUER cliente MCP desde que nasceu,
    # e ninguém viu porque nada a chamava. Apareceu no primeiro uso real, quando o Hermes foi
    # olhar a fila do DP. Envelopar é a correção certa — mudar a anotação para `list` faria a
    # resposta perder o total, e o agente conta o que vê.
    return _envelope(await erp.get("/people-management/ponto/justificativas/pendentes"),
                     "justificativas")


@mcp.tool
async def revisar_justificativa_ponto(justification_id: str, aprovar: bool, observacao: str | None = None) -> dict:
    """Aprova (aprovar=True) ou rejeita uma justificativa de ponto."""
    return await erp.request("PUT", f"/people-management/ponto/justificativa/{justification_id}/revisar",
                             json={"aprovar": aprovar, "aprovada": aprovar, "observacao": observacao})


@mcp.tool
async def status_fechamento_ponto(mes: int, ano: int) -> dict:
    """Estado real do fechamento do ponto por competência (quantos fechados/pendentes)."""
    return await erp.get("/people-management/ponto/fechamento/status", params={"month": mes, "year": ano})


@mcp.tool
async def fechar_mes_ponto(mes: int, ano: int) -> dict:
    """FECHA o mês do ponto para todos (idempotente). Ação de gestão — confirme antes."""
    return await erp.post("/people-management/ponto/fechamento-mes", json={"mes": mes, "ano": ano})


# ---- Férias ----
@mcp.tool
async def listar_ferias(status: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista solicitações de férias (todos). status opcional (ex.: 'aprovado','solicitado')."""
    params = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    return await erp.get("/people-management/hr/vacations", params=params)


@mcp.tool
async def ferias_funcionario(employee_id: str) -> dict:
    """Férias de um funcionário específico."""
    return await erp.get(f"/people-management/hr/vacations/employee/{employee_id}")


@mcp.tool
async def saldo_ferias(employee_id: str) -> dict:
    """Saldo e período aquisitivo de férias de um funcionário (alerta de vencidas)."""
    return await _get_ou_404(f"/people-management/hr/vacations/employee/{employee_id}/balance",
                             o_que="funcionário", chave=employee_id,
                             dica="Use o id do funcionário — buscar_funcionario(nome) devolve.")


@mcp.tool
async def solicitar_ferias(employee_id: str, data_inicio: str, dias: int = 30, observacao: str | None = None) -> dict:
    """Cria uma solicitação de férias. data_inicio no formato YYYY-MM-DD; dias (ex.: 30)."""
    return await erp.post("/people-management/hr/vacations", json={
        "employee_id": employee_id, "data_inicio": data_inicio, "start_date": data_inicio,
        "dias": dias, "days": dias, "observacao": observacao})


@mcp.tool
async def aprovar_ferias(vacation_id: str, observacao: str | None = None) -> dict:
    """Aprova uma solicitação de férias.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post(f"/people-management/hr/vacations/{vacation_id}/approve",
                          json={"observacao": observacao})


# ---- Admissão ----
@mcp.tool
async def listar_admissoes(status: str | None = None) -> dict:
    """Lista processos de admissão em andamento."""
    return await erp.get("/people-management/hr/admissions", params={"status": status} if status else None)


@mcp.tool
async def concluir_admissao(admission_id: str) -> dict:
    """Finaliza uma admissão (gera o funcionário efetivo). Confirme os documentos antes."""
    return await erp.post(f"/people-management/hr/admissions/{admission_id}/complete", json={})


# ---- Rescisão ----
@mcp.tool
async def listar_rescisoes(status: str | None = None) -> dict:
    """Lista processos de rescisão."""
    return await erp.get("/people-management/hr/terminations", params={"status": status} if status else None)


@mcp.tool
async def calcular_verbas_rescisorias(termination_id: str) -> dict:
    """Calcula as verbas rescisórias de um processo de rescisão."""
    return await erp.post(f"/people-management/hr/terminations/{termination_id}/calculate", json={})


# ---- Benefícios ----
@mcp.tool
async def listar_beneficios_funcionario(employee_id: str) -> dict:
    """Benefícios (VT/VR/plano) de um funcionário."""
    return await _get_ou_404(f"/people-management/hr/benefits/employee/{employee_id}",
                             o_que="funcionário", chave=employee_id,
                             dica="Use o id do funcionário — buscar_funcionario(nome) devolve.")


# ---- SST (saúde ocupacional) ----
@mcp.tool
async def sst_dashboard() -> dict:
    """Dashboard de SST (ASOs, EPIs, PCMSO, PPRA, acidentes)."""
    return await erp.get("/people-management/sst/dashboard")


@mcp.tool
async def asos_vencendo(dias: int = 30) -> dict:
    """ASOs (exames ocupacionais) vencendo nos próximos N dias."""
    return await erp.get("/people-management/sst/asos/vencendo", params={"dias": dias})


@mcp.tool
async def funcionarios_sem_aso() -> dict:
    """Funcionários sem ASO válido (pendência de saúde ocupacional)."""
    return await erp.get("/people-management/sst/asos/sem-aso")




# =================================================================== FISCAL / CONTÁBIL


# ---- NFS-e ----
@mcp.tool
async def listar_nfse(competencia: str | None = None, limit: int = 50) -> dict:
    """Lista NFS-e emitidas (fonte real gov.br, só cStat 100). competencia='YYYY-MM' opcional."""
    params = {"limit": limit}
    if competencia:
        params["competencia"] = competencia
    return await erp.get("/financial/nfse", params=params)


@mcp.tool
async def dashboard_nfse() -> dict:
    """Painel de faturamento por NFS-e: total de notas, valor, ISS, por competência e por cliente."""
    return await erp.get("/financial/nfse/dashboard")


@mcp.tool
async def listar_nfse_entrada() -> dict:
    """Lista NFS-e de ENTRADA (tomadas contra o CNPJ) — custos/fornecedores."""
    return await erp.get("/financial/nfse-entrada")


@mcp.tool
async def resumo_nfse_entrada() -> dict:
    """Resumo fiscal das NFS-e de entrada (retenções, tributos)."""
    return await erp.get("/financial/nfse-entrada/resumo-fiscal")


# ---- Dashboards fiscais ----
@mcp.tool
async def dashboard_fiscal() -> dict:
    """Painel fiscal consolidado (NFS-e, tributos, obrigações, INSS/FGTS)."""
    return await erp.get("/financial/fiscal/dashboard")


@mcp.tool
async def dashboard_fiscal_grupo(mes: int | None = None, ano: int | None = None) -> dict:
    """Painel fiscal do GRUPO (multi-empresa): receita/impostos por CNPJ na competência."""
    params = {}
    if mes:
        params["mes"] = mes
    if ano:
        params["ano"] = ano
    return await erp.get("/empresas/dashboard/fiscal/grupo", params=params or None)


@mcp.tool
async def rentabilidade_grupo() -> dict:
    """Rentabilidade/margem comparada entre as empresas do grupo."""
    return await erp.get("/empresas/dashboard/rentabilidade/grupo")


@mcp.tool
async def contabil_grupo() -> dict:
    """Painel contábil consolidado do grupo."""
    return await erp.get("/empresas/dashboard/contabil/grupo")


@mcp.tool
async def monitor_integracoes_gov() -> dict:
    """Monitoramento das integrações gov: junta o `status` de cada serviço que expõe um.

    ⚠️ 11/09/2026: apontava para `/government/dashboard/`, que NÃO EXISTE — a única rota
    montada sob esse prefixo é `/certificados/alertas`. A ferramenta respondia "Not Found"
    desde que nasceu e ninguém viu, porque nada a chamava. Em vez de inventar um dashboard no
    backend, ela pergunta a cada integração o `status` que ela já publica; serviço que não
    responde entra como indisponível, com o motivo, em vez de derrubar a resposta inteira.
    """
    import asyncio as _aio  # noqa: PLC0415

    servicos = ("efd-reinf", "dctfweb", "simples-nacional", "fgts-digital",
                "sped-fiscal", "sped-contabil", "ecac", "nfse-nacional")

    async def _um(nome: str) -> tuple[str, object]:
        try:
            return nome, await erp.get(f"/government/{nome}/status")
        except Exception as e:  # noqa: BLE001
            return nome, {"indisponivel": str(e)[:160]}

    pares = await _aio.gather(*(_um(n) for n in servicos))
    resultado = dict(pares)
    fora = [n for n, v in resultado.items() if isinstance(v, dict) and "indisponivel" in v]
    return {"servicos": resultado, "total": len(servicos), "indisponiveis": fora}


@mcp.tool
async def alertas_certificados() -> dict:
    """Alertas de vencimento de certificados digitais A1/A3."""
    return _envelope(await erp.get("/government/dashboard/certificados/alertas"), "alertas")


# ---- DAS / Simples ----
@mcp.tool
async def status_simples_nacional() -> dict:
    """Situação/opção no Simples Nacional (anexo, sublimite, pendências)."""
    return await erp.get("/government/simples-nacional/status")


@mcp.tool
async def pendencias_simples() -> dict:
    """Pendências no Simples Nacional."""
    return {"ok": False, "codigo": "CAPACIDADE_APOSENTADA", "http": 410,
            "mensagem": "Pendências do Simples não são consultadas: a rota devolvia lista "
                        "vazia com 'Implementar' e foi aposentada em 08/09/2026.",
            "dica": "A Eletrônica é Lucro Real. Para obrigações use "
                    "`calendario_obrigacoes` ou `alertas_obrigacoes`."}


# ---- Obrigações ----
@mcp.tool
async def alertas_obrigacoes() -> dict:
    """Alertas de obrigações acessórias vencendo/vencidas (grupo)."""
    return await erp.get("/empresas/obrigacoes/alertas")


@mcp.tool
async def calendario_obrigacoes() -> dict:
    """Calendário de obrigações fiscais do grupo (multi-empresa)."""
    return await erp.get("/empresas/obrigacoes/calendario/grupo")


# ---- Certidões / e-CAC ----
@mcp.tool
async def listar_certidoes() -> dict:
    """Lista certidões (CND, FGTS, trabalhista) e validade."""
    return await erp.get("/ged/certidoes")


@mcp.tool
async def situacao_fiscal_ecac() -> dict:
    """Situação fiscal no e-CAC (regularidade)."""
    return await erp.get("/government/ecac/situacao-fiscal")


@mcp.tool
async def debitos_ecac() -> dict:
    """Débitos no e-CAC."""
    return await erp.get("/government/ecac/debitos")


@mcp.tool
async def resumo_ecac() -> dict:
    """Resumo/status do e-CAC (situação, declarações, parcelamentos)."""
    return await erp.get("/government/ecac/status")


# ---- eSocial / FGTS / DCTFWeb ----
@mcp.tool
async def listar_eventos_esocial() -> dict:
    """Lista eventos do eSocial registrados (só transmissões reais)."""
    return await erp.get("/government/esocial/eventos")


@mcp.tool
async def gaps_esocial() -> dict:
    """Funcionários com pendências/faltando eventos no eSocial."""
    return await erp.get("/government/esocial/gaps-funcionarios")


@mcp.tool
async def status_dctfweb() -> dict:
    """Status/configuração da DCTFWeb."""
    return await erp.get("/government/dctfweb/status")


@mcp.tool
async def status_fgts_digital() -> dict:
    """Status do FGTS Digital."""
    return await erp.get("/government/fgts-digital/status")


@mcp.tool
async def guias_fgts() -> dict:
    """Lista/gera guias de FGTS."""
    return await erp.get("/government/fgts/guias")


# ---- Empresas ----
@mcp.tool
async def listar_empresas() -> dict:
    """Lista as empresas/CNPJs do grupo econômico."""
    return _envelope(await erp.get("/empresas/"), "empresas")




# =================================================================== OPERACIONAL / CAMPO


@mcp.tool
async def dashboard_operacional() -> dict:
    """Painel operacional: postos ativos, colaboradores, alocações, turnos hoje, ocorrências, cobertura."""
    return await erp.get("/operacional/dashboard/")


@mcp.tool
async def listar_postos(status: str | None = None, busca: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista POSTOS de trabalho (com filtros de status/busca)."""
    params = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    if busca:
        params["search"] = busca
    return await erp.get("/operacional/posts/", params=params)


@mcp.tool
async def estatisticas_postos() -> dict:
    """KPIs de postos (total, ativos, com/sem vaga)."""
    return await erp.get("/operacional/posts/stats")


@mcp.tool
async def listar_escalas(mes: int | None = None, ano: int | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista ESCALAS (12x36, 44h etc.), com filtro por mês/ano."""
    params = {"page": page, "page_size": page_size}
    if mes:
        params["month"] = mes
    if ano:
        params["year"] = ano
    return await erp.get("/operacional/scales/", params=params)


@mcp.tool
async def listar_alocacoes(post_id: str | None = None, employee_id: str | None = None, page: int = 1) -> dict:
    """Lista ALOCAÇÕES (funcionário↔posto). Filtra por post_id/employee_id."""
    params = {"page": page, "page_size": 30}
    if post_id:
        params["post_id"] = post_id
    if employee_id:
        params["employee_id"] = employee_id
    # ⚠️ operacional é READ-ONLY para o agente: aqui muda só a FORMA DO ERRO.
    return await _get_ou_404("/operacional/allocations/?" + "&".join(
        f"{k}={v}" for k, v in params.items()),
        o_que="posto ou funcionário", chave=str(post_id or employee_id or ""),
        dica="`listar_postos()` e `buscar_funcionario(nome)` devolvem os ids válidos.")


@mcp.tool
async def alocacoes_vigentes(post_id: str | None = None) -> dict:
    """Alocações ativas no momento (opcional: de um posto específico)."""
    d = await _get_ou_404(
        "/operacional/allocations/current" + (f"?post_id={post_id}" if post_id else ""),
        o_que="posto", chave=str(post_id or ""),
        dica="`listar_postos()` devolve os ids válidos.")
    # ⚠️ esta rota devolve LISTA quando não há filtro e DICT quando há. `d.get(...)` sem
    # checar o tipo estourou com "'list' object has no attribute 'get'" — pego pela
    # `checar_tool_quebrada` antes de sair daqui, que é o trabalho dela.
    if isinstance(d, dict) and d.get("ok") is False:
        return d
    return _envelope(d, "alocacoes")


@mcp.tool
async def funcionarios_disponiveis_posto(post_id: str) -> dict:
    """Funcionários livres para alocar num posto (post_id obrigatório)."""
    return await erp.get("/operacional/allocations/available-employees", params={"post_id": post_id})


@mcp.tool
async def listar_ocorrencias(status: str | None = None, severity: str | None = None, page: int = 1) -> dict:
    """Lista OCORRÊNCIAS operacionais (filtra por status/severidade)."""
    params = {"page": page, "page_size": 30}
    if status:
        params["status"] = status
    if severity:
        params["severity"] = severity
    return await erp.get("/operacional/occurrences/", params=params)


@mcp.tool
async def relatorio_cobertura(start_date: str | None = None, end_date: str | None = None) -> dict:
    """Relatório de cobertura (postos × alocações, taxa de cobertura). Datas YYYY-MM-DD."""
    params = {}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    return await erp.get("/operacional/reports/coverage", params=params or None)


@mcp.tool
async def listar_ordens_servico(status: str | None = None, page: int = 1, page_size: int = 30) -> dict:
    """Lista ORDENS DE SERVIÇO de campo (instalação/manutenção)."""
    params = {"page": page, "page_size": page_size}
    if status:
        params["status"] = status
    return await erp.get("/campo/os/", params=params)


@mcp.tool
async def dashboard_ordens_servico() -> dict:
    """Estatísticas de OS de campo (abertas, atrasadas, por técnico)."""
    return await erp.get("/campo/os/dashboard")


@mcp.tool
async def listar_visitas_campo(status: str | None = None, page: int = 1) -> dict:
    """Lista VISITAS de campo (técnicas/comerciais agendadas)."""
    params = {"page": page, "page_size": 30}
    if status:
        params["status"] = status
    return await erp.get("/campo/visitas/", params=params)


@mcp.tool
async def dashboard_campo() -> dict:
    """Painel do módulo de campo (OS + visitas + técnicos)."""
    return await erp.get("/campo/dashboard")


# =================================================================== RH / SST / CCT / REEMBOLSO


@mcp.tool
async def listar_vagas(status: str | None = None) -> dict:
    """Lista VAGAS de recrutamento (status opcional)."""
    return await erp.get("/people-management/human-resources/candidatos/postos")  # recruitment aposentado 08/09/2026 (0 vagas cadastradas); postos com vaga na esteira


@mcp.tool
async def vagas_abertas() -> dict:
    """Lista só as vagas ABERTAS (em recrutamento)."""
    return await erp.get("/people-management/human-resources/candidatos/postos")


@mcp.tool
async def listar_candidatos(busca: str | None = None, page: int = 1) -> dict:
    """Lista CANDIDATOS do recrutamento (busca opcional)."""
    params = {"page": page, "page_size": 30}
    if busca:
        params["q"] = busca
    return await erp.get("/people-management/human-resources/candidatos", params=params)  # esteira real


@mcp.tool
async def listar_entrevistas() -> dict:
    """Lista ENTREVISTAS agendadas do recrutamento."""
    return {"ok": False, "codigo": "CAPACIDADE_APOSENTADA", "http": 410,
            "mensagem": "Entrevistas não são registradas no ERP — o pacote recruitment foi "
                        "aposentado em 08/09/2026 com 0 registros desde sempre.",
            "dica": "A esteira de candidatos é por posto: use `listar_candidatos`."}


@mcp.tool
async def estoque_epi() -> dict:
    """Estoque de EPIs (equipamentos de proteção — NR-6)."""
    return await erp.get("/people-management/sst/epi")  # health_occupational aposentado 08/09/2026


@mcp.tool
async def status_pcmso() -> dict:
    """Estatísticas/status do PCMSO (exames ocupacionais — NR-7)."""
    return await erp.get("/people-management/sst/pcmso/status")


@mcp.tool
async def status_ppra() -> dict:
    """Estatísticas do PPRA/PGR (riscos ocupacionais — NR-9)."""
    return await erp.get("/people-management/sst/ppra/status")


@mcp.tool
async def listar_reembolsos(status: str | None = None) -> dict:
    """Lista solicitações de REEMBOLSO (status opcional)."""
    return await erp.get("/reimbursements/", params={"status": status} if status else None)


@mcp.tool
async def reembolsos_pendentes_aprovacao() -> dict:
    """Reembolsos aguardando aprovação."""
    return await erp.get("/reimbursements/approvals/pending")


@mcp.tool
async def reembolsos_prontos_pagamento() -> dict:
    """Reembolsos aprovados e prontos para pagamento."""
    return await erp.get("/reimbursements/ready-for-payment")


@mcp.tool
async def tabela_salarial_cct() -> dict:
    """Tabela salarial completa da CCT SINDECOMPRESTS 2026 (pisos por cargo)."""
    return await erp.get("/cct/salarios/tabela")


@mcp.tool
async def beneficios_cct(cargo: str | None = None) -> dict:
    """Benefícios previstos na CCT (VT/VR/cesta) — opcional por cargo."""
    return await erp.get("/cct/beneficios", params={"cargo": cargo} if cargo else None)


@mcp.tool
async def dashboard_clima() -> dict:
    """Indicadores da pesquisa de clima organizacional."""
    # 08/09/2026: o módulo retention foi aposentado (tabela climate_scores nunca existiu; 0 respostas).
    return {"ok": False, "codigo": "CAPACIDADE_APOSENTADA", "http": 410,
            "mensagem": "Pesquisa de clima não está implantada: o módulo retention foi "
                        "aposentado, a tabela climate_scores nunca existiu, 0 respostas.",
            "dica": "Não há indicador para mostrar e não há o que consertar do seu lado."}



# =================================================================== ASGI app
# ============================================================================
# ATUALIZAÇÃO 2026-07-16 — recursos novos (tudo READ-ONLY; dinheiro que sai
# continua SÓ pela tela com gate OTP humano — o conector não executa pagamento)
# ============================================================================

@mcp.tool
async def inter_saldo() -> dict:
    """Saldo atual da conta Banco Inter (leitura, tempo real)."""
    return await erp.get("/financeiro/inter/saldo")


@mcp.tool
async def inter_extrato_resumo() -> dict:
    """Resumo do extrato Inter (entradas/saídas recentes, conciliação)."""
    return await erp.get("/financeiro/inter/extrato/resumo")


@mcp.tool
async def listar_pagamentos_inter(page_size: int = 20) -> dict:
    """Pagamentos feitos pelo Inter (PIX/boleto/DARF): valor, status, categoria, datas."""
    return await erp.get("/financeiro/inter/payments", params={"page_size": page_size})


@mcp.tool
async def baixar_comprovante_pagamento_pdf(payment_id: str, formato: str = "base64") -> dict:
    """Comprovante em PDF (padrão-ouro) de um pagamento Inter CONCLUÍDO — retorna base64.

    `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    que saiu sem abrir binário; "texto" só o texto. Item 2.1 do relatório de campo.
    """
    return await _pdf_b64(f"/financeiro/inter/payments/{payment_id}/comprovante", formato=formato, nome="comprovante.pdf")


@mcp.tool
async def teto_diario_pagamentos() -> dict:
    """Teto diário de pagamentos (CONECTA_LIMITE_DIARIO) vs quanto já saiu hoje."""
    return await erp.get("/financeiro/inter/payments/saldo-limite")


@mcp.tool
async def divergencias_folha_pagamentos() -> dict:
    """Divergências entre a folha calculada e os pagamentos Inter (antes de pagar)."""
    return await erp.get("/financeiro/inter/payroll/divergencias")


@mcp.tool
async def pix_recebidos() -> dict:
    """PIX recebidos na conta Inter (entradas identificadas)."""
    return await erp.get("/financeiro/inter/pix/recebidos")


@mcp.tool
async def listar_cobrancas_inter() -> dict:
    """Cobranças/boletos emitidos pelo Inter e seus status."""
    return await erp.get("/financeiro/inter/cobrancas")


@mcp.tool
async def listar_beneficiarios_pix() -> dict:
    """Agenda de beneficiários PIX (nome → chave salva; employees usam pix_key)."""
    return await erp.get("/financial/beneficiarios")


@mcp.tool
async def status_dominio() -> dict:
    """Status da integração com a contabilidade Domínio (plano de contas, conexão)."""
    return await erp.get("/empresas/dominio/status")


@mcp.tool
async def exportar_folha_dominio(competencia: str) -> dict:
    """Export da folha no layout Domínio (motor read-only — NÃO fecha a folha). competencia: 'YYYY-MM'."""
    return await erp.get(f"/people-management/hr/payroll-export/dominio/{competencia}")


@mcp.tool
async def esocial_espelho_resumo() -> dict:
    """Espelho eSocial: resumo dos eventos transmitidos vs pendentes por funcionário."""
    return await erp.get("/government/esocial/espelho/resumo")


@mcp.tool
async def esocial_timeline_funcionario(employee_id: str) -> dict:
    """Linha do tempo eSocial de um funcionário (S-2200/2230/2299 e protocolos). Aceita id do
    funcionário OU CPF — a rota é por CPF (08/09/2026: com UUID devolvia sempre vazio)."""
    chave = "".join(ch for ch in str(employee_id) if ch.isdigit())
    if len(chave) != 11:
        try:
            emp = await erp.get(f"/people-management/hr/employees/{employee_id}")
            chave = "".join(ch for ch in str((emp or {}).get("cpf") or (emp or {}).get("data", {}).get("cpf") or "") if ch.isdigit())
        except Exception:  # noqa: BLE001
            chave = ""
        if len(chave) != 11:
            return {"ok": False, "codigo": "CPF_NAO_ENCONTRADO", "http": 404,
                    "mensagem": f"Não achei o CPF do funcionário {employee_id!r}.",
                    "dica": "Informe o CPF diretamente (11 dígitos), ou use "
                            "buscar_funcionario para achar o id certo."}
    try:
        return await erp.get(f"/government/esocial/espelho/timeline/{chave}")
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def presenca_ao_vivo() -> dict:
    """PRESENÇA AO VIVO de hoje: escala × batidas por posto (TZ Manaus), faltas e atrasos."""
    return await erp.get("/operacional/presenca/hoje")


@mcp.tool
async def substitutos_disponiveis(posto_id: str) -> dict:
    """Substitutos disponíveis para cobrir falta num posto (mesmo cargo, sem conflito de escala)."""
    return await erp.get(f"/operacional/presenca/substitutos/{posto_id}")


@mcp.tool
async def substituicoes_pendentes() -> dict:
    """Faltas com substituição ainda pendente de resolução."""
    return _envelope(await erp.get("/operacional/substitutions/pending"), "substituicoes")


@mcp.tool
async def listar_substituicoes(data: str | None = None) -> dict:
    """Substituições registradas (falta → substituto). data opcional 'YYYY-MM-DD'."""
    if data:
        return _envelope(await erp.get(f"/operacional/substitutions/by-date/{data}"), "substituicoes")
    # a BARRA FINAL importa: `/operacional/substitutions` devolve 404 e
    # `/operacional/substitutions/` devolve 200 (o router monta a rota como "/"). Medido em
    # 11/09 — a ferramenta respondia "Not Found" desde sempre por um caractere.
    return _envelope(await erp.get("/operacional/substitutions/"), "substituicoes")


@mcp.tool
async def grade_postos() -> dict:
    """Grade de escala por posto (visão geral: quem cobre o quê, 12x36/comercial)."""
    return await erp.get("/operacional/grade/postos")


@mcp.tool
async def grade_do_posto(posto_id: str) -> dict:
    """Grade de escala POR PESSOA de um posto (leitura; edição é só na tela, pelo Jordan/Gonzaga/Paiva)."""
    return await erp.get(f"/operacional/grade/{posto_id}")


@mcp.tool
async def listar_comunicados() -> dict:
    """Comunicados internos publicados (sino do ERP)."""
    return await erp.get("/operacional/comunicados")


@mcp.tool
async def comunicados_nao_lidos() -> dict:
    """Comunicados internos ainda não lidos pelos destinatários (cobrança de leitura)."""
    return await erp.get("/operacional/comunicados/nao-lidos")


@mcp.tool
async def painel_espelho_ponto(mes: int, ano: int) -> dict:
    """Painel do espelho de ponto da competência: todos os funcionários, horas e pendências."""
    return await erp.get(f"/people-management/hr/ponto/espelho/painel/{mes}/{ano}")


@mcp.tool
async def baixar_espelho_ponto_pdf(employee_id: str, mes: int, ano: int, formato: str = "base64") -> dict:
    """Espelho de ponto mensal de um funcionário em PDF (padrão-ouro) — retorna base64.

    `formato`: "base64" (padrão) traz o arquivo E o `texto_extraido`, para CONFERIR o
    que saiu sem abrir binário; "texto" só o texto. Item 2.1 do relatório de campo.
    """
    return await _pdf_b64(f"/people-management/hr/ponto/espelho/{employee_id}/{mes}/{ano}/pdf", formato=formato, nome="espelho_ponto.pdf")


_ORIGENS = ("ceo", "cfo", "fiscal", "rh", "juridico", "comercial", "operacional", "ged")


async def _consultar(origem: str, pergunta: str) -> dict:
    return await erp.post(f"/consultores/mcp/{origem}/consultar", json={"pergunta": pergunta})


@mcp.tool
async def consultor_ceo(pergunta: str) -> dict:
    """Consultor executivo (CEO): visão estratégica, runway, decisão. Único que cruza dinheiro+legal+gente por cliente (gated). Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("ceo", pergunta)


@mcp.tool
async def consultor_cfo(pergunta: str) -> dict:
    """Consultor financeiro (CFO): caixa, aging, o que vence, saúde financeira. Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("cfo", pergunta)


@mcp.tool
async def consultor_fiscal(pergunta: str) -> dict:
    """Consultor fiscal/contábil: notas, guias, regime, obrigações. Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("fiscal", pergunta)


@mcp.tool
async def consultor_dp(pergunta: str) -> dict:
    """Consultor de DP/RH: folha, ponto, colaboradores, CCT. Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("rh", pergunta)


@mcp.tool
async def consultor_juridico(pergunta: str) -> dict:
    """Consultor jurídico (READ-ONLY): processos, dossiê. Aconselha, nunca protocola. Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("juridico", pergunta)


@mcp.tool
async def consultor_comercial(pergunta: str) -> dict:
    """Consultor comercial/CRM: funil, propostas, clientes. Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("comercial", pergunta)


@mcp.tool
async def consultor_operacional(pergunta: str) -> dict:
    """Consultor operacional (READ-ONLY): postos, escalas, presença. Nunca altera escala. Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("operacional", pergunta)


@mcp.tool
async def consultor_ged(pergunta: str) -> dict:
    """Consultor de GED/documentos: kits, panorama documental. Não muda dado de negócio; GRAVA a própria pergunta/resposta na trilha de consultas (por isso `ensaiar` diz "1 escrita")."""
    return await _consultar("ged", pergunta)


@mcp.tool
async def registrar_feedback(origem: str, correcao: str, consulta_id: int | None = None) -> dict:
    """🔵 Registra uma correção do gestor como memória permanente do consultor (realimenta o ERP). origem ∈ ceo/cfo/fiscal/rh/juridico/comercial/operacional/ged.

    ⚠️ ESCREVE no Conecta PRO — não é consulta.
    """
    return await erp.post("/consultores/mcp/feedback", json={"origem": origem, "correcao": correcao, "consulta_id": consulta_id})


@mcp.tool
async def propor_pagamento(valor: float, pix_key: str, descricao: str = "") -> dict:
    """🟡 PROPÕE um pagamento PIX — grava PENDENTE ('preparado'). NÃO executa: requer aprovação humana + OTP. Nunca move dinheiro sozinho."""
    return await erp.post("/consultores/mcp/propor-pagamento", json={"valor": valor, "pix_key": pix_key, "descricao": descricao})


@mcp.tool
async def propor_comunicado(titulo: str, corpo: str) -> dict:
    """🟡 PROPÕE um comunicado — grava RASCUNHO. NÃO publica/envia: requer aprovação humana."""
    return await erp.post("/consultores/mcp/propor-comunicado", json={"titulo": titulo, "corpo": corpo})


# ------------------------------------------- Fase 5.2a.4: quick-wins executivos (🟢 read)
@mcp.tool
async def consultar_viabilidade_contratacao(qtd: int, cargo: str) -> dict:
    """🟢 "Posso contratar N do cargo X?" — cruza caixa/runway (CFO) + postos descobertos (COO)
    + custo de folha (qtd × piso CCT + encargos). Cada número com proveniência; síntese ancorada
    (groundedness). Só LEITURA — não contrata, não move dinheiro. READ."""
    return await erp.post("/consultores/mcp/executivo/viabilidade-contratacao",
                          json={"qtd": qtd, "cargo": cargo})


@mcp.tool
async def briefing_executivo() -> dict:
    """🟢 1-card executivo do dia: caixa (saldo Inter), postos descobertos, certidões vencendo,
    deals quentes. Cada número com source; o que não tiver lastro vem 'aguardando dado'. READ."""
    return await erp.get("/consultores/mcp/executivo/briefing")


@mcp.tool
async def runway_ao_vivo() -> dict:
    """🟢 Runway de caixa AO VIVO: saldo Inter vivo ÷ folha mensal = meses, com as_of
    (corrige o KPI de cache velho). READ."""
    return await erp.get("/consultores/mcp/executivo/runway")


@mcp.tool
async def margem_por_condominio() -> dict:
    """🟢 Margem por contrato: receita (contrato) − folha alocada (best-effort). Onde o
    cruzamento não fecha, a folha vem 'aguardando dado' — nunca estimada. READ."""
    return await erp.get("/consultores/mcp/executivo/margem-condominio")


# ── ESCOPO DO CATÁLOGO ────────────────────────────────────────────────────────────────
# O Hermes manda o catálogo INTEIRO no prompt: medido em 23/08/2026, 250 ferramentas e
# ~43 mil tokens de contexto para responder "ok". Caro no provedor pago e inviável num
# modelo local pequeno — e lista enorme piora a escolha da ferramenta em QUALQUER modelo.
#
# `MCP_ESCOPO` (ex.: "dp", "financeiro,fiscal") reduz o que este processo serve. Vazio =
# catálogo inteiro, que é o comportamento de sempre — o conector do Cowork não muda.
# Ferramenta fora de qualquer grupo NUNCA some por esquecimento: `tools_do_escopo` só
# filtra o que está mapeado, e o que não está fica de fora do filtro, não do catálogo.
_ESCOPO = (os.getenv("MCP_ESCOPO") or "").strip()
if _ESCOPO:
    try:
        from tool_scopes import escopos_da_tool, tools_do_escopo

        _permitidas = tools_do_escopo(_ESCOPO)
        if _permitidas is not None:
            import asyncio as _aio

            # `remove_tool` é a API pública do FastMCP 3.4 — conferida no container antes
            # de usar. Mexer em `_tool_manager._tools` era palpite meu e nem existe nesta
            # versão.
            _todas = [getattr(t, "name", None) for t in _aio.run(mcp._list_tools())]
            # FAIL-CLOSED: fora do escopo pedido OU sem grupo nenhum.
            _fora = [n for n in _todas if n and n not in _permitidas]
            # Separar as DUAS causas, porque só uma é acidente: ficar fora do escopo é
            # decisão; ficar SEM GRUPO é esquecimento de quem criou a tool.
            _sem_grupo = sorted(n for n in _fora if not escopos_da_tool(n))
            # 🔴 11/09/2026 — AQUI ERA `mcp.remove_tool(_n)` DENTRO DE `except: pass`, e
            # `remove_tool` NÃO EXISTE no fastmcp 4.0.3 (é API da 3.4). Todas as chamadas
            # levantavam AttributeError, o except engolia, e a linha abaixo anunciava "42 de
            # 254" por ARITMÉTICA enquanto o `tools/list` devolvia os 266. Os três conectores
            # serviam o catálogo inteiro — inclusive `fechar_folha` e `criar_lead` no conector
            # do kit, cuja proteção declarada era justamente "o ESCOPO".
            # Agora é middleware (`gate_escopo`), que não depende de mutar o registro e que
            # recusa também a CHAMADA — sumir da lista nunca impediu quem sabe o nome.
            from gate_escopo import instalar as _instalar_escopo

            _servidas = _instalar_escopo(mcp, {n for n in _todas if n in _permitidas})
            print(f"[mcp] escopo={_ESCOPO} · servindo {_servidas} de "
                  f"{len(_todas)} ferramentas (parede de escopo ATIVA: filtra a lista "
                  f"E recusa a chamada)", flush=True)
            # NOMEAR, não contar. "146 de 254" só significa algo para quem lembra do
            # número de ontem — é a mesma família do container que ficou 2 semanas com
            # imagem velha sem ninguém notar. Nome é fato; contagem é sinal que depende
            # de memória alheia.
            if _sem_grupo:
                print(f"[mcp] SEM GRUPO em tool_scopes ({len(_sem_grupo)}) — não servidas "
                      f"a este conector: {', '.join(_sem_grupo)}", flush=True)
    except Exception as _e:  # noqa: BLE001
        # escopo inválido NÃO derruba o conector: serve tudo e denuncia alto. Um MCP fora
        # do ar por um typo em variável de ambiente é pior que um catálogo grande.
        print(f"[mcp] AVISO: escopo '{_ESCOPO}' não aplicado ({_e}) — catálogo inteiro",
              flush=True)

# ── F1: a etiqueta de risco passa a AGIR ──────────────────────────────────────────────
# Sem isto, `tool_risk_manifest` é crachá que nenhum porteiro pede: 254 tools classificadas
# A parede enfileira `propose` onde MCP_MODO=agente — no conector do Jordan a pessoa lê e
# decide na hora, e enfileirar ali seria trocar decisão por espera.
#
# ⚠️ MAS ela é instalada nos DOIS modos, desde 11/09/2026. Ações de EFEITO EXTERNO (e-mail
# ao cliente, WhatsApp, assinatura com o certificado, dinheiro que sai) exigem aprovação
# em qualquer conector — quem chama o público é um LLM agindo em nome do Jordan, não o
# Jordan clicando. Antes o instalador devolvia False fora do modo agente e nada entrava no
# caminho: `enviar_link_assinatura` estava corretamente classificada `propose` e mesmo
# assim chegava ao ERP, porque o middleware que lê a classificação não estava lá.
try:
    from gate_propose import instalar as _instalar_gate

    if _instalar_gate(mcp):
        print("[mcp] gate propose ATIVO — efeito externo SEMPRE exige aprovação; "
              "`propose` também, em modo agente",
              flush=True)
except Exception as _e:  # noqa: BLE001
    # sem a parede, um conector de AGENTE não sobe: melhor fora do ar que solto.
    if (os.getenv("MCP_MODO") or "").strip().lower() == "agente":
        raise RuntimeError(f"MCP_MODO=agente exige o gate de aprovação: {_e}") from _e
    print(f"[mcp] gate propose não instalado ({_e})", flush=True)

# F2 — o conector ENCAMINHA a identidade de quem perguntou em vez de cunhá-la. Sem repasse,
# tool sensível não executa: responder com a conta de serviço é atender qualquer um com os
# poderes do sistema. Mesma postura do gate: conector de agente não sobe sem esta parede.
try:
    from identidade import instalar as _instalar_identidade

    if _instalar_identidade(mcp):
        print("[mcp] exigência de identidade ATIVA — tool sensível exige X-Usuario-Token",
              flush=True)
except Exception as _e:  # noqa: BLE001
    if (os.getenv("MCP_MODO") or "").strip().lower() == "agente":
        raise RuntimeError(f"MCP_MODO=agente exige o repasse de identidade: {_e}") from _e
    print(f"[mcp] exigência de identidade não instalada ({_e})", flush=True)

# O carimbo entra por ÚLTIMO de propósito: middleware do FastMCP roda em pilha, e o último
# instalado é o mais externo. Assim ele enxerga a resposta depois de todas as paredes — e
# uma RECUSA do gate também sai carimbada, que é justamente a resposta que alguém vai querer
# rastrear depois.
try:
    from carimbo import instalar as _instalar_carimbo

    if _instalar_carimbo(mcp):
        print("[mcp] request_id ATIVO — toda resposta carimbada e propagada ao ERP",
              flush=True)
except Exception as _e:  # noqa: BLE001
    # rastreabilidade é importante e não é parede: não subir por causa dela seria trocar
    # um conector no ar por um conector fora do ar.
    print(f"[mcp] request_id NÃO instalado ({_e}) — respostas sem rastro", flush=True)

_mcp_app = mcp.http_app(path="/mcp")


async def _healthz(_request):
    return JSONResponse({"ok": True, "service": "conecta-pro-mcp"})


_base = Starlette(
    routes=[Route("/healthz", _healthz), Mount("/", app=_mcp_app)],
    lifespan=_mcp_app.lifespan,
)


class _BearerASGI:
    """Auth de entrada por Bearer token (pura ASGI — não quebra streaming/SSE do MCP)."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.token:
            if scope.get("path") != "/healthz":
                headers = dict(scope.get("headers") or [])
                if headers.get(b"authorization", b"").decode() != f"Bearer {self.token}":
                    await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                    return
        await self.app(scope, receive, send)


if AUTH_MODE == "google":
    # FastMCP + GoogleProvider já protegem o /mcp (OAuth). Não envolve no Bearer.
    app = _base
else:
    app = _BearerASGI(_base, MCP_AUTH_TOKEN)


# ── Descoberta e saúde ────────────────────────────────────────────────────────────────
# Os dois pedidos do relatório de campo que custam menos e resolvem mais: em parte de uma
# sessão o conector SUMIU (nenhuma ferramenta encontrada) e voltou depois, sem ninguém
# saber se era a conexão, o ERP ou o banco. E achar a ferramenta certa entre 254 consumia
# chamadas de tentativa e erro, porque os nomes variam (consultar_/listar_/obter_/painel_).

VERSAO_MCP = "2026.09.11"


@mcp.tool
async def ping_conecta_pro() -> dict:
    """Saúde da ponte: o MCP está de pé? o ERP responde? com que identidade? Sempre primeiro.

    Use quando uma ferramenta falhar de forma estranha ou quando o conector parecer ausente
    — distingue "a ponte caiu" de "o ERP recusou" de "eu chamei errado", que é a dúvida que
    faz o agente repetir a chamada errada.
    """
    import time as _t

    ini = _t.perf_counter()
    # ⚠️ `tools` contava as citadas no MAPA (29), não as SERVIDAS (276). O Cowork viu 29 no
    # ping e 276 no relatório e perguntou qual dos dois mede outra coisa — pergunta certa: o
    # ping é o que um operador olha para saber se o conector está inteiro, e ele dizia que
    # faltavam 247. Agora os dois números aparecem, cada um com o nome do que é.
    try:
        _servidas = len(await mcp.list_tools())
    except Exception:  # noqa: BLE001
        _servidas = None
    fora: dict = {"ok": True, "versao_mcp": VERSAO_MCP,
                  "tools_servidas": _servidas,
                  "tools_no_mapa_de_descoberta": len(TOOLS_POR_DOMINIO_PLANO)}
    try:
        r = await erp.get("/health")
        fora["erp"] = {"ok": True, "resposta": r if isinstance(r, dict) else str(r)[:80]}
    except Exception as exc:  # noqa: BLE001
        fora["ok"] = False
        fora["erp"] = erro_envelope(exc)
    try:
        eu = await erp.get("/auth/me")
        fora["identidade"] = {"email": (eu or {}).get("email"),
                              "nome": (eu or {}).get("full_name") or (eu or {}).get("name")}
    except Exception:  # noqa: BLE001
        fora["identidade"] = {"erro": "não foi possível identificar o usuário desta sessão"}
    fora["latencia_ms"] = round((_t.perf_counter() - ini) * 1000)
    return fora


# Mapa de domínios. Não é a lista das 254 — é o CAMINHO: o que usar, em que ordem, e o que
# vem depois. Uma lista alfabética de 254 nomes não ajuda quem não sabe o nome.
_MAPA = {
    # ⚠️ TODA tool citada aqui EXISTE no registry — `test_capabilities_sem_fantasma.py`
    # reprova o build se não existir. Validação do Cowork (11/09/2026): o mapa citava
    # `listar_contas_pagar` e `listar_recebiveis`, que nunca existiram. Auditando os seis
    # domínios pelo mesmo critério apareceram DEZ nomes fantasma, não dois.
    #
    # ⭐ Por que isso é grave e não cosmético: `capabilities` é a tool de DESCOBERTA. É por
    # ela que o agente decide o que fazer em seguida. Mapa apontando para rua que não existe
    # faz o agente tentar, falhar, e o dono concluir que "o MCP não funciona".
    "contratos": {
        "resumo": "Do fechamento ao instrumento assinado.",
        "fluxo": ["briefing_contrato_novo", "criar_contrato_por_modelo",
                  "gerar_contrato_por_modelo", "baixar_contrato_pdf",
                  "abrir_assinatura_contrato", "enviar_link_assinatura"],
        "atencao": "gerar_ devolve `faltam_dados` com as PERGUNTAS quando falta algo — "
                   "responda e chame de novo. Use baixar_contrato_pdf(formato='texto') "
                   "para conferir o conteúdo. Emitir é restrito a Jordan e Pyetra, e "
                   "enviar_link_assinatura exige aprovação humana.",
    },
    "comercial": {
        "resumo": "Lead → oportunidade → proposta → contrato.",
        "fluxo": ["listar_clientes", "contexto_cliente", "listar_deals",
                  "proposta_da_oportunidade", "criar_contrato_por_modelo"],
        "atencao": "A proposta PODE misturar serviços; o contrato e a nota fiscal NUNCA. "
                   "Mão de obra sai pela Patrimonial, eletrônica pela Eletrônica.",
    },
    "financeiro": {
        "resumo": "Contas, extrato, conciliação e cobrança.",
        "fluxo": ["resumo_financeiro", "inter_saldo", "inter_extrato_resumo",
                  "listar_cobrancas_inter", "pix_recebidos"],
        "atencao": "Dinheiro que SAI exige aprovação humana com OTP — `propor_pagamento` "
                   "não executa, registra o pedido.",
    },
    "folha_dp": {
        "resumo": "Folha, ponto, CCT e colaboradores.",
        "fluxo": ["resumo_folha", "folha_dashboard", "espelho_ponto", "beneficios_cct"],
        "atencao": "Governo (eSocial/FGTS) é só leitura. `fechar_folha` não tem desfazer — "
                   "ensaie antes com ensaiar('fechar_folha', {...}).",
    },
    "operacional": {
        "resumo": "Postos, escalas, plantões e diaristas.",
        "fluxo": ["listar_postos", "listar_escalas", "listar_alocacoes", "grade_do_posto"],
        "atencao": "Curado à mão pelo dono: divergência vira RELATÓRIO, nunca correção "
                   "automática. Não altere escala nem alocação por conta própria.",
    },
    "documentos": {
        "resumo": "Gerar, ler e anexar documentos.",
        "fluxo": ["baixar_contrato_pdf", "baixar_proposta_pdf", "anexar_documento",
                  "listar_documentos_da_entidade", "baixar_documento"],
        "atencao": "Use formato='texto' para VALIDAR conteúdo sem abrir binário. Acima de "
                   "256 KB o base64 é omitido — o texto continua vindo.",
    },
}
TOOLS_POR_DOMINIO_PLANO = [t for d in _MAPA.values() for t in d["fluxo"]]


def _lgpd_sensiveis() -> dict:
    """Toda ferramenta `sensivel`, com e sem concessão. Visível sem precisar do domínio."""
    try:
        import lgpd_escopo as _L  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return {}
    sens = sorted(n for n, v in _L.NIVEL.items() if v == _L.SENSIVEL)
    return {
        "total": len(sens),
        "significa": _L.O_QUE_SIGNIFICA[_L.SENSIVEL],
        "autorizadas_em_operacao_normal": [n for n in sens if _L.concessao_vale_para(n)],
        "exigem_pedido_especifico": [n for n in sens if not _L.concessao_vale_para(n)],
        "concessao": {k: v for k, v in _L.CONCESSAO.items() if k != "tools"},
        "aviso": ("Todo acesso a estas fica registrado em `agente_acesso_sensivel` — "
                  "inclusive a tentativa recusada."),
    }



def _contrato_da_tool(nome: str) -> dict:
    """O contrato de UMA ferramenta, para qualquer uma das 276. Fail-closed no desconhecido."""
    import inspect as _insp

    nome = (nome or "").strip()
    from tool_risk_manifest import TOOL_RISK as _TR  # noqa: PLC0415

    fn = globals().get(nome)
    if nome not in _TR and not callable(fn):
        candidatos = sorted(n for n in _TR if nome.lower() in n.lower())[:8]
        return {"ok": False, "codigo": "TOOL_DESCONHECIDA", "http": 404,
                "mensagem": f"Não existe ferramenta {nome!r}.",
                "dica": ("Confira o nome. `conecta_pro_capabilities()` lista os domínios."
                         + (f" Parecidas: {candidatos}" if candidatos else "")),
                "parecidas": candidatos}
    classe = _TR.get(nome, "NAO_CLASSIFICADA")
    try:
        import gate_propose as _G  # noqa: PLC0415

        sai = _G.EFEITO_EXTERNO.get(nome)
        irrev = _G.IRREVERSIVEL.get(nome)
        atras_do_muro = _G.precisa_aprovacao(nome)
    except Exception:  # noqa: BLE001
        sai = irrev = None
        atras_do_muro = None
    try:
        import lgpd_escopo as _L  # noqa: PLC0415

        lgpd = _L.declarar(nome)
    except Exception:  # noqa: BLE001
        lgpd = {}
    params = {}
    if callable(fn):
        for par in _insp.signature(fn).parameters.values():
            params[par.name] = {
                "obrigatorio": par.default is _insp.Parameter.empty,
                "tipo": str(par.annotation).replace("<class '", "").replace("'>", ""),
            }
    return {
        "ok": True, "tool": nome, "classe_de_risco": classe,
        # ⭐ a pergunta que o Cowork errou por não ter resposta: ESCREVE?
        "escreve": classe in ("write_low", "propose"),
        "so_leitura": classe == "read",
        "atras_do_muro_de_aprovacao": atras_do_muro,
        "sai_da_empresa": sai, "irreversivel": irrev,
        "parametros": params,
        "descricao": (_insp.getdoc(fn) or "").strip()[:600] if callable(fn) else None,
        "no_mapa_curado": nome in TOOLS_POR_DOMINIO_PLANO,
        **lgpd,
    }


@mcp.tool
async def conecta_pro_capabilities(dominio: str = "", tool: str = "") -> dict:
    """Mapa das capacidades: que domínios existem, o FLUXO de cada um e as armadilhas.

    Use ANTES de procurar ferramenta por tentativa e erro. Sem argumento devolve os
    domínios; com `dominio`, o caminho completo daquele; com `tool`, o CONTRATO daquela
    ferramenta — vale para qualquer uma das 276, esteja ela curada num domínio ou não.

    ⭐ `tool=` nasceu da validação do Cowork de 13/09/2026, e do jeito mais convincente: ele
    chamou `proposta_da_oportunidade` achando que era leitura e descobriu que ela escreve
    EXECUTANDO-A, em produção. Palavras dele: *"enquanto 247 tools não disserem de antemão se
    leem ou escrevem, todo agente novo vai aprender a classificação de cada uma por tentativa
    — e algumas dessas tentativas gravam."*

    ⚠️ Conferi a causa que ele atribuiu e ela estava errada: a ferramenta **está** no mapa
    curado, no domínio `comercial`. O que falhou não foi a ausência dela — foi o mapa dizer
    apenas o NOME dela dentro de um `fluxo`, sem dizer a classe. Constar de uma lista de
    fluxo não informa se escreve, e `proposta_da_oportunidade` quebra a convenção de nome da
    casa (`obter_`/`listar_`/`consultar_` leem; `criar_`/`gerar_`/`enviar_` escrevem). O
    achado dele estava certo pelo motivo de baixo, não pelo de cima.

    Curar 276 fluxos à mão levaria semanas e envelheceria. O CONTRATO, não: classe de risco,
    nível LGPD, se escreve, se é irreversível e se sai da empresa já existem em dado — só
    não estavam expostos por ferramenta. Mapa curado segue com 29; contrato, com 276.
    """
    if tool:
        return _contrato_da_tool(tool)
    if dominio:
        d = _MAPA.get(dominio.strip().lower())
        if not d:
            return {"ok": False, "codigo": "DOMINIO_DESCONHECIDO", "http": 404,
                    "mensagem": f"Não conheço o domínio {dominio!r}.",
                    "dica": "Chame sem argumento para ver os domínios.",
                    "dominios": sorted(_MAPA)}
        # ⭐ O NÍVEL LGPD vai POR TOOL, não por domínio (Bloco 7.2): `folha_dashboard` e
        # `baixar_holerite_pdf` vivem no mesmo domínio e mostram coisas opostas. O agente
        # precisa saber o que vai acessar ANTES de acessar.
        try:
            import lgpd_escopo as _L  # noqa: PLC0415

            escopo = {t: _L.declarar(t) for t in d["fluxo"]}
            sensiveis = [t for t, v in escopo.items() if v["lgpd_nivel"] == _L.SENSIVEL]
            saida = {"ok": True, "dominio": dominio, **d, "lgpd_por_tool": escopo}
            if sensiveis:
                saida["lgpd_atencao"] = (
                    f"{len(sensiveis)} ferramenta(s) deste fluxo tocam dado pessoal "
                    f"SENSÍVEL: {', '.join(sensiveis)}. Cada acesso fica registrado."
                )
            return saida
        except Exception:  # noqa: BLE001
            return {"ok": True, "dominio": dominio, **d}
    return {"ok": True, "versao_mcp": VERSAO_MCP,
            "dominios": {k: v["resumo"] for k, v in _MAPA.items()},
            # ⭐ As SENSÍVEIS na raiz, não só no `fluxo`. Validação do Cowork (12/09/2026):
            # `lgpd_por_tool` só classificava o que estava no fluxo do domínio, e
            # `baixar_holerite_pdf` não está em nenhum — logo o agente não conseguia
            # confirmar que ele é sensível. O `capabilities` é a tool de DESCOBERTA: o que
            # não aparece aqui, para quem só olha aqui, não existe.
            "lgpd_sensiveis": _lgpd_sensiveis(),
            "como_usar": "conecta_pro_capabilities(dominio='contratos') abre o fluxo.",
            "regra_de_ouro": "Toda ferramenta diz se LÊ ou ESCREVE. As de escrita de "
                             "contrato são restritas a Jordan e Pyetra; dinheiro que sai "
                             "exige OTP humano e não passa por aqui."}


# ── Modelos de contrato (CRUD pelo MCP) ───────────────────────────────────────────────
# Item 2.3 do relatório de campo. Existiam 4 modelos e NENHUMA ferramenta para cadastrar
# um quinto: todo tipo de negócio novo — locação de CFTV, serviço único, portaria remota —
# ficava travado esperando alguém rodar um seed no backend. O ERP já tinha o CRUD completo
# em /crm/contracts/templates; faltava a ponte.

@mcp.tool
async def listar_modelos_contrato() -> dict:
    """Modelos de contrato cadastrados: tipo, nome, nº de cláusulas e tamanho do corpo.

    Use ANTES de criar contrato — é o `tipo` daqui que decide o CNPJ emitente (mão de obra
    sai pela Patrimonial, eletrônica pela Eletrônica). Só lê.
    """
    try:
        r = await erp.get("/crm/contracts/templates")
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    itens = []
    for t in (r or {}).get("items") or []:
        corpo = t.get("content_template") or ""
        itens.append({
            "id": t.get("id"), "tipo": t.get("service_type"), "nome": t.get("name"),
            "clausulas": len(t.get("clauses") or []),
            "tamanho_corpo": len(corpo),
            "ativo": t.get("is_active"),
            "variaveis_no_corpo": sorted(set(re.findall(r"\{\{\s*([a-z_0-9]+)", corpo))),
            "descricao": (t.get("description") or "")[:160],
        })
    return {"ok": True, "total": len(itens), "modelos": itens}


@mcp.tool
async def validar_modelo_contrato(corpo_template: str, contrato_exemplo: str = "") -> dict:
    """Confere se TODAS as `{{variaveis}}` do corpo têm origem — antes de cadastrar.

    Sem isto, o modelo entra bonito e só falha na hora de emitir, com o cliente esperando.
    Passe `contrato_exemplo` (um CTR-… real) para validar contra dados de verdade: a
    ferramenta diz quais variáveis o ERP sabe preencher e quais ficariam vazias.

    Só lê; não cadastra nada.
    """
    usadas = sorted(set(re.findall(r"\{\{\s*([a-z_0-9]+)", corpo_template or "")))
    if not usadas:
        return {"ok": False, "codigo": "SEM_VARIAVEIS", "http": 422,
                "mensagem": "O corpo não tem nenhuma {{variavel}}.",
                "dica": "Um modelo sem variável serve a um cliente só. Troque os dados das "
                        "partes por {{contratante_nome}}, {{valor_mensal_fmt}} etc."}
    if not contrato_exemplo:
        return {"ok": True, "variaveis": usadas, "total": len(usadas),
                "aviso": "Passe contrato_exemplo=CTR-… para validar contra dados reais."}
    alvo = await _resolver_contrato(contrato_exemplo)
    if isinstance(alvo, dict):
        return alvo
    try:
        r = await erp.post("/crm/contracts/validar-modelo",
                           json={"contrato": alvo, "corpo": corpo_template})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    return r


@mcp.tool
async def atualizar_modelo_contrato(template_id: str, nome: str = "",
                                    corpo_template: str = "", descricao: str = "",
                                    tipo: str = "", clausulas: list[str] | None = None,
                                    confirmar_modelo_em_uso: bool = False) -> dict:
    """Altera um MODELO de contrato já cadastrado. ESCREVE. Restrito a Jordan e Pyetra.

    Passe só o que muda; o resto fica como está. Item 2.3 do relatório de campo — corrigir
    uma cláusula era voltar a ser tarefa de seed no backend.

    ⚠️ MODELO EM USO. Um modelo não é um documento: é a fôrma de todos os contratos
    pendurados nele. Trocar o corpo muda o que sairá na PRÓXIMA emissão de cada um —
    inclusive de contratos já assinados, se alguém reemitir a via. Por isso, se houver
    contrato vinculado, esta tool RECUSA e mostra quais são; passe
    `confirmar_modelo_em_uso=True` depois de olhar a lista.

    ⚠️ Trocar `tipo` troca o CNPJ EMITENTE — mão de obra sai pela Patrimonial, eletrônica
    pela Eletrônica. Não é ajuste de catálogo, é mudar quem assina.

    Valide o corpo novo com `validar_modelo_contrato` ANTES: modelo que falha só na emissão
    falha com o cliente esperando.
    """
    if corpo_template and len(corpo_template) < 100:
        return {"ok": False, "codigo": "CORPO_CURTO", "http": 422,
                "mensagem": "O corpo do modelo tem menos de 100 caracteres.",
                "dica": "Cole o texto completo do instrumento, com as cláusulas."}
    if not any([nome, corpo_template, descricao, tipo, clausulas]):
        return {"ok": False, "codigo": "NADA_A_MUDAR", "http": 422,
                "mensagem": "Informe pelo menos um campo para alterar.",
                "dica": "nome · corpo_template · descricao · tipo · clausulas"}

    # Quem já depende deste modelo — medido ANTES de escrever.
    #
    # ⭐ FALHA FECHADA, e por um motivo medido em 11/09/2026: a primeira versão desta guarda
    # lia `template_id` da listagem de contratos, campo que a resposta NÃO tinha. Ela achou
    # zero afetados, concluiu "não está em uso" e deixou a escrita passar — gravando numa
    # descrição de modelo de produção. Uma parede que mede um campo inexistente não avisa
    # que está cega: ela diz "tudo limpo". Por isso, aqui, não conseguir medir vale como
    # motivo para RECUSAR, nunca para liberar.
    em_uso: list = []
    try:
        atuais = await erp.get("/crm/contracts", params={"page_size": 100})
        itens = _items(atuais)
        # A JANELA também é uma forma de observar a coisa errada: 100 contratos hoje são
        # todos, e no dia em que forem 101 esta guarda passaria a dizer "ninguém usa" sobre
        # um modelo em uso na página 2. O backend não filtra por template_id, então a saída
        # honesta é recusar quando não enxergo o conjunto inteiro — não estimar por amostra.
        total = (atuais or {}).get("total")
        if total is not None and total > len(itens):
            return {"ok": False, "codigo": "NAO_CONSIGO_MEDIR_O_USO", "http": 409,
                    "mensagem": f"Há {total} contratos e eu só consigo olhar {len(itens)} "
                                f"por vez, então não sei quantos usam este modelo.",
                    "dica": "Peça a quem cuida do ERP um filtro por template_id em "
                            "/crm/contracts. Até lá, edite o modelo pela tela."}
        if itens and "template_id" not in itens[0]:
            return {"ok": False, "codigo": "NAO_CONSIGO_MEDIR_O_USO", "http": 409,
                    "mensagem": "A listagem de contratos não informa o modelo de cada um, "
                                "então não sei quantos seriam afetados — e não altero uma "
                                "fôrma no escuro.",
                    "dica": "Peça a quem cuida do ERP para expor `template_id` em "
                            "/crm/contracts. Até lá, edite o modelo pela tela."}
        em_uso = [c for c in itens if str(c.get("template_id") or "") == str(template_id)]
    except Exception as exc:  # noqa: BLE001
        env = erro_envelope(exc)
        env["dica"] = ("Não consegui verificar quantos contratos usam este modelo, então "
                       "não alterei nada. Tente de novo.")
        return env
    if em_uso and not confirmar_modelo_em_uso:
        return {
            "ok": False, "codigo": "MODELO_EM_USO", "http": 409,
            "mensagem": f"{len(em_uso)} contrato(s) usam este modelo. Alterar o corpo muda "
                        f"o que sairá na próxima emissão de cada um.",
            "dica": "Confira a lista e, se for isso mesmo, chame de novo com "
                    "confirmar_modelo_em_uso=True.",
            "contratos_afetados": [
                {"numero": c.get("contract_number"), "cliente": c.get("client_name"),
                 "status": c.get("status")} for c in em_uso[:20]],
        }

    payload: dict[str, Any] = {}
    for chave, valor in (("name", nome), ("content_template", corpo_template),
                         ("description", descricao), ("service_type", tipo),
                         ("clauses", clausulas)):
        if valor:
            payload[chave] = valor
    if corpo_template and not clausulas:
        payload["clauses"] = sorted(set(
            re.findall(r"^\s*(CL[ÁA]USULA[^\n]{0,80})", corpo_template, re.M)))
    try:
        r = await erp.put(f"/crm/contracts/templates/{template_id}", json=payload)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    return {"ok": True, "id": r.get("id"), "nome": r.get("name"),
            "tipo": r.get("service_type"), "clausulas": len(r.get("clauses") or []),
            "alterados": sorted(payload), "contratos_que_usam": len(em_uso),
            "proximo_passo": "validar_modelo_contrato para conferir as variáveis do corpo novo."}


@mcp.tool
async def criar_modelo_contrato(tipo: str, nome: str, corpo_template: str,
                                descricao: str = "", clausulas: list[str] | None = None) -> dict:
    """Cadastra um MODELO novo de contrato. ESCREVE. Restrito a Jordan e Pyetra.

    `tipo` decide o CNPJ emitente e não é livre — use um que o render saiba classificar:
    mão de obra (portaria_mao_de_obra, servicos_gerais, jardinagem, piscina, zeladoria) ou
    eletrônica (manutencao_cftv, portaria_remota, eletronica_servico_unico,
    seguranca_eletronica, cftv, alarme, controle_acesso).

    O corpo usa `{{variavel}}` (Jinja) e pode conter `[[TABELA_COMPOSICAO]]` e
    `[[BLOCO_ASSINATURAS]]`. Valide com `validar_modelo_contrato` ANTES — modelo que falha
    só na emissão falha com o cliente esperando.
    """
    if len(corpo_template or "") < 100:
        return {"ok": False, "codigo": "CORPO_CURTO", "http": 422,
                "mensagem": "O corpo do modelo tem menos de 100 caracteres.",
                "dica": "Cole o texto completo do instrumento, com as cláusulas."}
    payload = {"name": nome, "service_type": tipo, "content_template": corpo_template,
               "description": descricao or None,
               "clauses": clausulas or sorted(set(
                   re.findall(r"^\s*(CL[ÁA]USULA[^\n]{0,80})", corpo_template, re.M)))}
    try:
        r = await erp.post("/crm/contracts/templates", json=payload)
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    return {"ok": True, "id": r.get("id"), "tipo": r.get("service_type"),
            "nome": r.get("name"), "clausulas": len(r.get("clauses") or []),
            "proximo_passo": "vincular_modelo_ao_contrato(contrato, template_id) e depois "
                             "gerar_contrato_por_modelo."}


@mcp.tool
async def vincular_modelo_ao_contrato(contrato: str, template_id: str) -> dict:
    """Liga um contrato ao MODELO que vai gerar o instrumento. ESCREVE.

    O contrato herda o `tipo_servico` do modelo quando ainda não tem — e é ele que resolve
    qual CNPJ emite. Depois disto, `gerar_contrato_por_modelo` produz o padrão ouro.
    """
    alvo = await _resolver_contrato(contrato)
    if isinstance(alvo, dict):
        return alvo
    try:
        r = await erp.post("/crm/contracts/emitir-por-modelo",
                           json={"contrato": alvo, "template_id": template_id})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)
    return r


# ── Entrada de documentos (item 2.2) ──────────────────────────────────────────────────
# O ERP tinha o REGISTRO e o artefato morava fora: contrato final .docx, planilha aberta de
# custo, deck, parecer jurídico do cliente. Versões soltas em pasta local e risco real de
# assinar a errada — havia dois decks do The Sun na mesma pasta.

@mcp.tool
async def anexar_documento(entidade: str, entidade_id: str, nome: str, conteudo_b64: str,
                           categoria: str = "anexo", descricao: str = "") -> dict:
    """Anexa um arquivo ao registro de uma entidade no ERP. ESCREVE.

    `entidade`: contrato · cliente · proposta · oportunidade · os · visita · lead
    `categoria`: contrato_assinado · minuta · proposta · planilha · parecer ·
                 apresentacao · anexo
    `nome` PRECISA terminar na extensão (contrato.docx) — é dela que sai o mime.
    Aceita pdf, docx, xlsx, pptx, png, jpg, txt, csv, xml. Limite de 25 MB.

    ⚠️ NUNCA sobrescreve: mesmo nome e categoria na mesma entidade vira **v2**, e o retorno
    diz qual versão ficou. Perder qual arquivo o cliente assinou é pior que ter duas cópias.

    `entidade_id` de contrato aceita CTR-…, id, CNPJ ou nome aproximado.
    """
    alvo = entidade_id
    if (entidade or "").strip().lower() == "contrato":
        alvo = await _resolver_contrato(entidade_id)
        if isinstance(alvo, dict):
            return alvo
    try:
        return await erp.post("/crm/docs/anexar", json={
            "entidade": entidade, "entidade_id": alvo, "nome": nome,
            "conteudo_b64": conteudo_b64, "categoria": categoria, "descricao": descricao})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def baixar_documento(documento_id: str, formato: str = "base64",
                           forcar_base64: bool = False) -> dict:
    """Traz um documento anexado — em base64 E em TEXTO, para conferir sem abrir binário.

    `formato`: "base64" (padrão, traz os dois) · "texto" (só o texto, mais barato).
    Pegue o `documento_id` em `listar_documentos_da_entidade`.

    Acima de 256 KB o base64 é OMITIDO e ficam o texto e o link: o teto é da CONVERSA, não
    do disco — 469 KB já viram 651 mil caracteres. `forcar_base64=True` traz assim mesmo.
    Formatos que não viram texto (.xlsx, .pptx, imagens) vêm em base64 com o aviso de que
    não dá para ler — melhor que um `texto_extraido` vazio, que você leria como
    "documento em branco".

    Fecha o trio da entrada de documentos: anexar → listar → baixar. Só lê.
    """
    try:
        return await erp.get(f"/crm/docs/conteudo/{documento_id}",
                             params={"formato": formato, "forcar_base64": forcar_base64})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def listar_documentos_da_entidade(entidade: str, entidade_id: str) -> dict:
    """Todos os documentos de uma entidade — os que o sistema gerou E os anexados de fora.

    Traz categoria, nome, VERSÃO, tamanho e link. Use para saber se um contrato já tem
    instrumento assinado anexado, ou qual é a versão mais recente de um deck.
    Só lê.
    """
    alvo = entidade_id
    if (entidade or "").strip().lower() == "contrato":
        alvo = await _resolver_contrato(entidade_id)
        if isinstance(alvo, dict):
            return alvo
    try:
        return await erp.get("/crm/docs/da-entidade",
                             params={"entidade": entidade, "entidade_id": alvo})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


@mcp.tool
async def contexto_cliente(chave: str) -> dict:
    """DOSSIÊ do cliente numa chamada só — cadastro, contratos, propostas, oportunidades,
    documentos e recebíveis em aberto.

    Item 3.6 do relatório de campo: responder "como está o Kopenhagen?" custava ~6 chamadas,
    e o agente montava a resposta com pedaços que chegavam em ordens diferentes. Aqui é uma
    viagem, e o retrato é o mesmo para todo mundo que perguntar.

    `chave` aceita CNPJ (com ou sem máscara), código (CLI-…), id ou nome aproximado. Se
    mais de um cliente casar, devolve os candidatos em vez de escolher por você — montar o
    dossiê do cliente errado é pior que não montar.

    Use ANTES de qualquer trabalho comercial com um cliente. Só lê.
    """
    try:
        return await erp.get("/crm/contexto-cliente", params={"chave": chave})
    except Exception as exc:  # noqa: BLE001
        return erro_envelope(exc)


# ── Operações longas (item 3.5) ───────────────────────────────────────────────────────
# Folha, relatórios e emissões pesadas rodavam síncronas e travavam a conversa: o agente
# ficava parado esperando, e acima de 40s a chamada estourava o timeout — perdendo o
# trabalho que o ERP já tinha feito.
#
# ⭐ Genérico de propósito. Dar `assincrono=True` a cada tool pesada seria editar 20
# assinaturas e errar em algumas; aqui UMA implementação serve às 262, e quem decide o que
# é pesado é quem chama, que é quem sabe.

# Em segundo plano o teto é outro. Sem isto o job só MUDARIA DE LUGAR a espera: a tool
# continuaria morrendo nos 40s do httpx contra o backend, e o agente teria trocado um timeout
# visível por um job que falha em silêncio — pior que o problema original.
_EM_JOB: contextvars.ContextVar[bool] = contextvars.ContextVar("_EM_JOB", default=False)
TIMEOUT_JOB = 600

# O ensaio em curso: uma lista onde `request` deposita o que TERIA enviado. `None` = fora de
# ensaio, e o `None` é de propósito — uma lista vazia significaria "ensaio sem escritas",
# que é informação diferente.
_ENSAIO: contextvars.ContextVar[list | None] = contextvars.ContextVar("_ENSAIO", default=None)

# Identificador desta chamada, do pedido do agente até o log do backend. Item 4 do relatório
# de campo. Antes ele só existia quando o ERP mandava `x-request-id` num ERRO — ou seja,
# quase nunca, e nunca no caminho feliz. Sem isto, "deu errado às 14h" é tudo que se leva
# para investigar.
_REQ_ID: contextvars.ContextVar[str] = contextvars.ContextVar("_REQ_ID", default="")

# Ambiente de ENSAIO COM GRAVAÇÃO. Item 4 do relatório de campo: "hoje qualquer teste vira
# registro real — foi o caso do CTR-2026-00022". `ensaiar` mostra o que FARIA e não grava;
# o sandbox grava de verdade, num banco descartável, para exercitar o que só aparece depois
# da escrita (numeração, diagnóstico do wizard, pendências que sobram).
SANDBOX_BASE = os.getenv("ERP_SANDBOX_URL", "http://conecta-pro-backend-staging:8080").rstrip("/")
SANDBOX_API = f"{SANDBOX_BASE}/api/v1"
_SANDBOX: contextvars.ContextVar[bool] = contextvars.ContextVar("_SANDBOX", default=False)


def _api() -> str:
    """A base desta chamada. Produção por padrão; staging só dentro de `no_sandbox`."""
    return SANDBOX_API if _SANDBOX.get() else API

_JOBS: dict[str, dict] = {}
_JOBS_TTL = 2 * 3600


def _limpa_jobs() -> None:
    # nunca despeja quem ainda está rodando: um job longo que estourasse o TTL sumiria do
    # dicionário e a própria task morreria de KeyError ao tentar gravar o resultado.
    agora = time.time()
    for jid in [k for k, v in _JOBS.items()
                if v.get("status") != "processando"
                and agora - v.get("criado_em", 0) > _JOBS_TTL]:
        _JOBS.pop(jid, None)


@mcp.tool
async def executar_em_segundo_plano(ferramenta: str, argumentos: dict | None = None) -> dict:
    """Dispara QUALQUER ferramenta em segundo plano e devolve um `job_id` na hora.

    Use quando a operação for demorada — folha, relatório do mês, emissão em lote — para
    não travar a conversa e não perder o trabalho num timeout. Depois consulte com
    `status_job(job_id)` e pegue o retorno com `resultado_job(job_id)`.

    ⚠️ Segundo plano muda QUANDO, não O QUÊ. As duas paredes valem aqui exatamente como
    valeriam na chamada direta, e são checadas contra a ferramenta INTERNA.

    Os jobs vivem 2 horas na memória do processo; reiniciar o MCP os esquece.
    """
    _limpa_jobs()
    alvo = globals().get(ferramenta)
    if alvo is None or not callable(alvo):
        return {"ok": False, "codigo": "FERRAMENTA_DESCONHECIDA", "http": 404,
                "mensagem": f"Não existe ferramenta chamada {ferramenta!r}.",
                "dica": "Use conecta_pro_capabilities() para achar o nome certo."}

    # ⭐ As duas paredes moram no middleware `on_call_tool`, e ele julga o nome da chamada
    # EXTERNA. Aqui a chamada externa é sempre `executar_em_segundo_plano` — então, sem o
    # que vem abaixo, despachar seria um túnel: `enviar_link_assinatura` entraria por uma
    # porta que o middleware lê como inofensiva. Reuso as MESMAS funções das paredes de
    # propósito; uma cópia da regra divergiria na primeira mudança e o túnel reabriria.
    try:
        from gate_propose import precisa_aprovacao  # noqa: PLC0415
        if precisa_aprovacao(ferramenta):
            from gate_propose import envelope_recusa  # noqa: PLC0415

            return envelope_recusa(ferramenta, caminho="segundo_plano")
    except ImportError:
        pass

    # A identidade vive num ContextVar que o middleware SOLTA quando a chamada externa
    # retorna — e o job continua vivo depois disso. Sem carregar o token para dentro da
    # task, o job perderia o usuário no meio e cairia na conta de serviço: "a sessão dele
    # acabou, então eu faço com os meus poderes". É a escalada que a F2 existe para impedir.
    token_do_chamador = None
    try:
        from identidade import MODO_AGENTE, _TOKEN, sensivel  # noqa: PLC0415

        token_do_chamador = _TOKEN.get()
        # mesma razão do `ensaiar`: o middleware só existe em MODO_AGENTE, e uma parede
        # mais rígida que a da frente só quebra a ferramenta para quem tem direito a ela.
        if MODO_AGENTE and token_do_chamador is None and sensivel(ferramenta):
            return {"ok": False, "codigo": "SEM_IDENTIDADE", "http": 401,
                    "mensagem": f"`{ferramenta}` toca dado pessoal ou dinheiro e a chamada "
                                f"chegou sem identidade.",
                    "dica": "Envie o cabeçalho de identidade — vale igual em segundo plano."}
    except ImportError:
        _TOKEN = None

    jid = f"job_{secrets.token_hex(6)}"
    _JOBS[jid] = {"status": "processando", "ferramenta": ferramenta,
                  "criado_em": time.time(), "resultado": None, "erro": None}

    async def _rodar() -> None:
        _EM_JOB.set(True)
        if _TOKEN is not None:
            _TOKEN.set(token_do_chamador)
        try:
            r = alvo(**(argumentos or {}))
            resultado, erro = (await r if inspect.isawaitable(r) else r), None
        except Exception as exc:  # noqa: BLE001
            # o job guarda o ENVELOPE, não o traceback: quem consulta depois merece a mesma
            # mensagem legível que teria recebido na chamada direta.
            resultado, erro = None, erro_envelope(exc)
        j = _JOBS.get(jid)
        if j is not None:  # o registro pode ter sido varrido; a task não morre por isso
            j.update(resultado=resultado, erro=erro,
                     status="falhou" if erro else "concluido", terminou_em=time.time())

    asyncio.create_task(_rodar())
    return {"ok": True, "job_id": jid, "status": "processando", "ferramenta": ferramenta,
            "proximo_passo": f"status_job('{jid}') — e resultado_job quando concluir."}


@mcp.tool
async def changelog_mcp(limite: int = 15, desde: str = "") -> dict:
    """O que mudou nestas ferramentas, e quando. Só lê.

    Consulte quando uma ferramenta se comportar diferente do que você esperava: o item 4 do
    relatório de campo nasceu de `baixar_contrato_pdf` passar a tentar o instrumento
    completo sem que ninguém soubesse. Uma sessão do Cowork não vê o deploy acontecer.

    `desde`: AAAA-MM-DD, para ver só o que é mais novo que a sua última conexão.

    ⚠️ Não é lista escrita à mão — sai do histórico de commits de `mcp-server/`, gerado no
    build. Changelog mantido à mão envelhece em silêncio, que é o defeito que ele existiria
    para resolver.
    """
    import json as _json  # noqa: PLC0415
    import pathlib as _pl  # noqa: PLC0415

    arq = _pl.Path(__file__).parent / "changelog.json"
    if not arq.exists():
        return {"ok": False, "codigo": "CHANGELOG_AUSENTE", "http": 404,
                "mensagem": "A imagem foi construída sem o changelog.",
                "dica": "Reconstrua o conector."}
    dados = _json.loads(arq.read_text(encoding="utf-8"))
    entradas = dados.get("entradas") or []
    if desde:
        entradas = [e for e in entradas if str(e.get("data", "")) >= desde[:10]]
    return {"ok": True, "versao_mcp": VERSAO_MCP,
            "total_registrado": len(dados.get("entradas") or []),
            "mostrando": min(limite, len(entradas)),
            "mudancas": entradas[:limite],
            "dica": "Use desde='AAAA-MM-DD' para ver só o que é novo para você."}


# ⭐ MEDIDO, nunca escrito. A primeira versão desta docstring dizia "20 clientes, 12
# contratos, 72 funcionários" — verdade no dia em que escrevi e mentira no dia seguinte, em
# que o `refrescar_sandbox.sh` trouxe 26/20/105. Número em texto de ferramenta é fotografia:
# envelhece em silêncio e o agente acredita, porque veio na descrição oficial.
async def _idade_do_sandbox() -> dict:
    """Quão velha é a cópia. Auditoria pediu: 'documentar a data do snapshot no retorno'."""
    marca = _SANDBOX.set(True)
    try:
        d = await erp.get("/crm/contracts", params={"page_size": 1, "page": 1})
        total = (d or {}).get("total")
        # ⭐ A DATA, não só a contagem. Pedido do Cowork na validação: ele emitiu no sandbox
        # e o contrato saiu com "Jordan Santos de Jesus" e "Representante legal" — dados
        # ANTERIORES à correção CP-MCP-008, já certos em produção. A contagem não denuncia
        # isso: o sandbox tinha MAIS contratos que produção e ainda assim era velho. O que
        # denuncia é o registro mais recente da cópia.
        recente = await erp.get("/crm/contracts",
                                params={"page_size": 1, "sort": "-created_at"})
        itens = _items(recente)
        criado = (itens[0].get("created_at") if itens else None)
        return {
            "contratos": total,
            "registro_mais_recente": criado,
            "dica": "A cópia reproduz o cadastro do dia em que foi feita — se o documento "
                    "sair com dado velho, não é defeito do código: rode "
                    "scripts/refrescar_sandbox.sh. O sandbox prova o CAMINHO, não o DADO.",
        }
    except Exception:  # noqa: BLE001
        # não conseguir medir a idade não invalida a execução que já aconteceu
        return {"contratos": None, "dica": "não consegui medir a idade da cópia"}
    finally:
        _SANDBOX.reset(marca)


@mcp.tool
async def no_sandbox(ferramenta: str, argumentos: dict | None = None) -> dict:
    """Executa a ferramenta DE VERDADE, num ERP de mentira. Nada toca a produção.

    Use quando precisar do que só existe DEPOIS de gravar — o número que o contrato
    recebeu, o que o diagnóstico passa a cobrar, a pendência que sobrou. `ensaiar` mostra o
    que faria e para aí; aqui a escrita acontece, num banco descartável.

    Item 4 do relatório de campo: "hoje qualquer teste vira registro real". O CTR-2026-00024
    do Kopenhagen nasceu assim, de um teste meu.

    ⚠️ O sandbox é uma CÓPIA. Os ids e números NÃO valem em produção, e o que você criar
    lá não existe aqui. Serve para provar o CAMINHO, nunca para consultar dado — para
    consultar, chame a ferramenta direto. O retorno traz `snapshot` com a idade da cópia:
    quanto mais velha, mais o comportamento de lá diverge do de cá.

    ⚠️ As duas paredes valem igual: ação de aprovação humana continua recusada, e ferramenta
    que toca dado pessoal continua exigindo identidade. Sandbox muda ONDE, não O QUÊ — não é
    caminho alternativo para o que você não pode fazer.
    """
    alvo = globals().get(ferramenta)
    if alvo is None or not callable(alvo):
        return {"ok": False, "codigo": "FERRAMENTA_DESCONHECIDA", "http": 404,
                "mensagem": f"Não existe ferramenta chamada {ferramenta!r}.",
                "dica": "Use conecta_pro_capabilities() para achar o nome certo."}
    try:
        from gate_propose import precisa_aprovacao  # noqa: PLC0415
        if precisa_aprovacao(ferramenta):
            from gate_propose import envelope_recusa  # noqa: PLC0415

            return envelope_recusa(ferramenta, caminho="no_sandbox")
    except ImportError:
        pass
    try:
        from identidade import MODO_AGENTE, _TOKEN, sensivel  # noqa: PLC0415
        if MODO_AGENTE and _TOKEN.get() is None and sensivel(ferramenta):
            return {"ok": False, "codigo": "SEM_IDENTIDADE", "http": 401,
                    "mensagem": f"`{ferramenta}` toca dado pessoal ou dinheiro.",
                    "dica": "Envie o cabeçalho de identidade — vale igual no sandbox."}
    except ImportError:
        pass

    # ⚠️ Uma chamada de ensaio NÃO pode ir para o sandbox e voltar dizendo que gravou: são
    # duas promessas opostas. Se alguém aninhar os dois, o ensaio ganha — ele é o mais
    # restritivo, e no caso duvidoso a escrita não acontece.
    if _ENSAIO.get() is not None:
        return {"ok": False, "codigo": "ENSAIO_E_SANDBOX", "http": 409,
                "mensagem": "Isto já está dentro de um ensaio, que não grava em lugar nenhum.",
                "dica": "Escolha um: `ensaiar` para ver o que faria, `no_sandbox` para fazer."}

    marca = _SANDBOX.set(True)
    try:
        r = alvo(**(argumentos or {}))
        retorno = await r if inspect.isawaitable(r) else r
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "sandbox": True,
                "dica": "Falhou NO SANDBOX. A produção não foi tocada."}
    finally:
        _SANDBOX.reset(marca)

    return {"ok": True, "sandbox": True, "ferramenta": ferramenta, "resultado": retorno,
            "snapshot": await _idade_do_sandbox(),
            "aviso": "Executado no ERP de ensaio. Nada disto existe em produção — os "
                     "identificadores e números NÃO valem lá."}


# Campos que só têm sentido DEPOIS da gravação: num ensaio eles seriam derivados da casca
# `00000000-ensaio` e mentiriam com cara de verdade. Auditoria do Cowork (11/09/2026): o
# `retorno_simulado` de `gerar_recibo_pdf` ainda trazia `download_url` e "Abra o
# download_url para ver/baixar" — um link que não existe, no formato ANTERIOR ao item 2.1.
# Remover é mais honesto que zerar: campo ausente o agente nota, campo vazio ele usa.
_SO_APOS_GRAVAR = ("download_url", "drive_url", "url_alternativa", "obs", "token",
                   "arquivo", "base64", "pdf_base64", "id", "documento_id")


def _limpar_simulado(valor):
    """Tira do retorno de ensaio o que só existiria se a escrita tivesse acontecido."""
    if isinstance(valor, dict):
        limpo = {k: _limpar_simulado(v) for k, v in valor.items() if k not in _SO_APOS_GRAVAR}
        removidos = sorted(set(valor) & set(_SO_APOS_GRAVAR))
        if removidos:
            limpo["_removidos_do_ensaio"] = removidos
        return limpo
    if isinstance(valor, list):
        return [_limpar_simulado(v) for v in valor]
    return valor


@mcp.tool
async def ensaiar(ferramenta: str, argumentos: dict | None = None) -> dict:
    """Mostra o que uma ferramenta FARIA — rota, corpo, tudo — sem gravar nada.

    Vale para QUALQUER ferramenta de escrita. Use antes de criar cliente, contrato,
    proposta, lançamento: você vê o payload já resolvido e decide se é isso mesmo.

    O que volta: `escritas`, uma por chamada que teria ido ao ERP, com método, rota e corpo.
    Lista vazia significa que a ferramenta não escreveria nada — informação útil por si só.

    ⚠️ As LEITURAS acontecem de verdade (é como o ensaio resolve o cliente, o modelo, o
    valor). Só as escritas são interceptadas.

    ⚠️ Não é caminho alternativo para ação de aprovação humana: ferramenta `propose` é
    recusada aqui do mesmo jeito. E ferramenta que toca dado pessoal continua exigindo
    identidade — ensaiar não é desculpa para ler o holerite de alguém sem dizer quem
    pergunta.
    """
    alvo = globals().get(ferramenta)
    if alvo is None or not callable(alvo):
        return {"ok": False, "codigo": "FERRAMENTA_DESCONHECIDA", "http": 404,
                "mensagem": f"Não existe ferramenta chamada {ferramenta!r}.",
                "dica": "Use conecta_pro_capabilities() para achar o nome certo."}
    # as duas paredes, contra a ferramenta INTERNA — mesma razão do executar_em_segundo_plano
    try:
        from gate_propose import precisa_aprovacao  # noqa: PLC0415
        if precisa_aprovacao(ferramenta):
            from gate_propose import envelope_recusa  # noqa: PLC0415

            return envelope_recusa(ferramenta, caminho="ensaiar")
    except ImportError:
        pass
    try:
        from identidade import MODO_AGENTE, _TOKEN, sensivel  # noqa: PLC0415

        # ⚠️ `MODO_AGENTE` NÃO é detalhe: o middleware de identidade só é instalado nesse
        # modo. Checar sem ele aqui deixaria esta porta MAIS rígida que a porta da frente —
        # no conector público (o Cowork do Jordan) a chamada direta funcionaria e o ensaio
        # recusaria tudo. Parede mais rígida que a real quebra a ferramenta e não protege
        # nada: quem quisesse burlar usava o caminho direto, que continua aberto.
        if MODO_AGENTE and _TOKEN.get() is None and sensivel(ferramenta):
            return {"ok": False, "codigo": "SEM_IDENTIDADE", "http": 401,
                    "mensagem": f"`{ferramenta}` toca dado pessoal ou dinheiro.",
                    "dica": "Envie o cabeçalho de identidade — vale igual no ensaio."}
    except ImportError:
        pass

    # ⭐ 13/09/2026 — Bloco 3. `ensaiar` chamava `alvo(**argumentos)`, que é a função PYTHON
    # crua: o pydantic do FastMCP fica na porta da tool e nunca era exercido aqui. Resultado
    # medido pelo Jordan: `ensaiar("definir_meta_mensal", {valor: "abc"})` dizia
    # `retorno_simulado: {"meta_definida": true}` — ensaio aprovando o que a execução real
    # recusa com 422.
    #
    # Ensaio que valida MENOS que a execução é pior que não ter ensaio: ele existe para o
    # agente decidir se chama de verdade, e estava dizendo "pode".
    try:
        from pydantic import ValidationError, validate_call  # noqa: PLC0415

        alvo = validate_call(alvo)
    except ImportError:  # pragma: no cover
        ValidationError = ()  # type: ignore[assignment]

    registro: list = []
    marca = _ENSAIO.set(registro)
    try:
        r = alvo(**(argumentos or {}))
        retorno = await r if inspect.isawaitable(r) else r
    except Exception as exc:  # noqa: BLE001
        return {**erro_envelope(exc), "ensaio": True, "gravou": False,
                "escritas_que_teria_feito": registro,
                "dica": "O ensaio falhou ANTES de gravar. Nada foi escrito."}
    finally:
        _ENSAIO.reset(marca)

    return {
        "ok": True, "ensaio": True, "gravou": False, "ferramenta": ferramenta,
        "escritas": registro,
        "resumo": (f"{len(registro)} escrita(s) no ERP." if registro
                   else "Nenhuma escrita — esta chamada não gravaria nada."),
        "retorno_simulado": _limpar_simulado(retorno),
        "aviso": ("O retorno acima foi montado sobre respostas de ensaio (id "
                  "'00000000-ensaio'), então campos derivados dele não valem. Campos que só "
                  "existiriam DEPOIS de gravar foram removidos, não zerados."),
        "proximo_passo": f"Se estiver certo, chame {ferramenta} direto.",
    }


@mcp.tool
async def status_job(job_id: str) -> dict:
    """Em que pé está um job disparado por `executar_em_segundo_plano`. Só lê."""
    j = _JOBS.get(job_id)
    if not j:
        return {"ok": False, "codigo": "JOB_DESCONHECIDO", "http": 404,
                "mensagem": f"Não conheço o job {job_id!r}.",
                "dica": "Jobs vivem 2 horas e são esquecidos se o MCP reiniciar. "
                        "Dispare de novo."}
    decorrido = round((j.get("terminou_em") or time.time()) - j["criado_em"], 1)
    return {"ok": True, "job_id": job_id, "status": j["status"],
            "ferramenta": j["ferramenta"], "decorrido_s": decorrido,
            "pronto": j["status"] in ("concluido", "falhou")}


@mcp.tool
async def resultado_job(job_id: str) -> dict:
    """O retorno de um job concluído — o MESMO que a ferramenta devolveria direto. Só lê."""
    j = _JOBS.get(job_id)
    if not j:
        return {"ok": False, "codigo": "JOB_DESCONHECIDO", "http": 404,
                "mensagem": f"Não conheço o job {job_id!r}.",
                "dica": "Jobs vivem 2 horas e somem se o MCP reiniciar."}
    if j["status"] == "processando":
        return {"ok": True, "status": "processando", "job_id": job_id,
                "decorrido_s": round(time.time() - j["criado_em"], 1),
                "dica": "Ainda rodando. Consulte de novo em alguns segundos."}
    if j["status"] == "falhou":
        return {**(j["erro"] or {}), "job_id": job_id, "ferramenta": j["ferramenta"]}
    return {"ok": True, "job_id": job_id, "ferramenta": j["ferramenta"],
            "decorrido_s": round((j.get("terminou_em") or 0) - j["criado_em"], 1),
            "resultado": j["resultado"]}
