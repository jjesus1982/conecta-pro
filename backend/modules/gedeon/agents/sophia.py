"""
SOPHIA v2.0 — Busca Semântica Cross-Módulo do GEDEON
"Qualquer documento encontrado em linguagem natural"

Versão: 2.0
Escopo: DP · RH · GED · Operacional · Fiscal · Contratos · Licitações · Financeiro

Motor: OpenAI embeddings (text-embedding-3-large, dimensions=1536) + fallback dense 1536 dims
Síntese/rerank LLM: cascata OpenAI (gpt-5) → Anthropic (fallback) → síntese local
Capacidades:
- busca_semantica com filtros cross-módulo
- perguntar_linguagem_natural
- alertas_vencimento
- buscar_impacto_folha
- detectar_modulo_implicito
- reindexar_acervo

Armazenamento: PostgreSQL gedeon_document_index
(colunas v2: modulo, vencimento, impacto_folha, embedding_anthropic, embedding_model)
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import subprocess
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────

EMBEDDING_DIM = 1536
OPENAI_EMBEDDING_MODEL = "text-embedding-3-large"  # chamado com dimensions=1536 (compat. índice dense)
OPENAI_LLM_MODEL = "gpt-5"  # síntese/rerank (diretriz do dono: melhor modelo em tudo)
ANTHROPIC_MODEL = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")  # fallback da cascata LLM
EMBEDDING_MODEL_NAME_OPENAI = "openai_text-embedding-3-large_1536"
EMBEDDING_MODEL_NAME_ANTHROPIC = "anthropic_haiku_1536"  # legado (linhas antigas no índice)
EMBEDDING_MODEL_NAME_FALLBACK = "sophia_dense_1536"
SIMILARITY_THRESH = 0.60

POSTGRES_CONTAINER = "conecta-pro-postgres"
POSTGRES_DB = "conecta_pro"
POSTGRES_USER = "postgres"

# ── Módulos e termos de domínio ───────────────────────────────────────────────

MODULOS_ESCOPO = {
    "dp": "Departamento Pessoal",
    "rh": "Recursos Humanos",
    "ged": "Gestão Eletrônica de Documentos",
    "operacional": "Operacional",
    "fiscal": "Fiscal e Contábil",
    "contratos": "Contratos",
    "licitacoes": "Licitações",
    "financeiro": "Financeiro",
}

TERMOS_MODULOS: dict[str, list[str]] = {
    "dp": [
        "holerite",
        "folha",
        "salário",
        "pagamento",
        "admissão",
        "demissão",
        "rescisão",
        "férias",
        "13o",
        "décimo",
        "inss",
        "fgts",
        "irrf",
        "caged",
        "esocial",
        "ctps",
        "pis",
        "funcionario",
        "colaborador",
        "empregado",
        "contrato_trabalho",
        "clt",
        "cargo",
        "registro",
        "competencia",
        "folha_pagamento",
        "holerite_mensal",
    ],
    "rh": [
        "treinamento",
        "capacitação",
        "nr",
        "aso",
        "atestado",
        "exame",
        "médico",
        "admissional",
        "demissional",
        "periódico",
        "certificado",
        "qualificação",
        "curso",
        "formação",
        "desempenho",
        "avaliação",
        "benefício",
        "plano_saude",
        "vale_transporte",
        "vale_refeição",
        "recrutamento",
        "seleção",
        "contratação",
        "onboarding",
    ],
    "ged": [
        "certidão",
        "crf",
        "cndt",
        "cnd",
        "regularidade",
        "certidao",
        "alvará",
        "licença",
        "vencimento",
        "validade",
        "documento",
        "kit",
        "acervo",
        "arquivo",
        "digital",
        "assinatura",
        "certificado_digital",
        "kit_documental",
        "certidao_negativa",
    ],
    "operacional": [
        "posto",
        "ocorrência",
        "ocorrencia",
        "ronda",
        "escala",
        "porteiro",
        "segurança",
        "guarda",
        "turno",
        "diária",
        "plantão",
        "cliente_posto",
        "supervisor",
        "coordenador",
        "incidente",
        "relatório_operacional",
        "ronda_eletrônica",
    ],
    "fiscal": [
        "nfse",
        "nfe",
        "nota_fiscal",
        "danfe",
        "iss",
        "icms",
        "pis_cofins",
        "sped",
        "reinf",
        "dctfweb",
        "efd",
        "apuração",
        "tributo",
        "imposto",
        "faturamento",
        "emissão_fiscal",
        "xml_fiscal",
        "arquivo_fiscal",
    ],
    "contratos": [
        "contrato",
        "experiência",
        "prazo",
        "vigência",
        "renovação",
        "aditivo",
        "rescisão_contratual",
        "prestação_serviços",
        "contrato_experiencia",
        "contrato_prazo_determinado",
        "contrato_terceirização",
    ],
    "licitacoes": [
        "edital",
        "pregão",
        "licitação",
        "licitacao",
        "dispensa",
        "inexigibilidade",
        "proposta",
        "certame",
        "pe",
        "tribunal",
        "órgão_público",
        "governo",
        "homologação",
        "adjudicação",
        "sessão_pública",
        "ata_registro_preço",
    ],
    "financeiro": [
        "fatura",
        "boleto",
        "cobrança",
        "recebimento",
        "pagamento_cliente",
        "inadimplência",
        "vencimento_fatura",
        "conta_receber",
        "conta_pagar",
        "fluxo_caixa",
        "extrato",
        "conciliação",
        "banco",
        "transferência",
        "nf_servico",
    ],
}

TIPOS_POR_MODULO: dict[str, list[str]] = {
    "dp": [
        "holerite",
        "contrato_trabalho",
        "contrato_experiencia",
        "rescisao",
        "trct",
        "aviso_previo",
        "ferias",
        "decimo_terceiro",
        "admissao",
        "demissao",
        "atestado",
        "aso",
        "epi",
        "ficha_epi",
        "ppp",
        "beneficios",
        "vale_transporte",
    ],
    "rh": [
        "avaliacao_desempenho",
        "treinamento",
        "certificado_nr",
        "onboarding",
        "plano_carreira",
        "feedback_360",
        "advertencia",
        "suspensao",
    ],
    "ged": [
        "kit_documental",
        "cnd_federal",
        "cnd_estadual",
        "cnd_municipal",
        "crf_fgts",
        "certidao_trabalhista",
        "alvara",
        "licenca",
        "comprovante",
    ],
    "operacional": [
        "ocorrencia",
        "relatorio_ronda",
        "escala",
        "substituicao",
        "comunicado_posto",
        "cat",
        "registro_visita",
    ],
    "fiscal": [
        "nfse",
        "nota_fiscal",
        "guia_inss",
        "guia_fgts",
        "darf",
        "gps",
        "declaracao_ir",
        "esocial",
        "sped",
    ],
    "contratos": [
        "contrato_prestacao_servico",
        "aditivo_contrato",
        "contrato_experiencia_vencendo",
        "rescisao_contrato_cliente",
        "medicao_servico",
    ],
    "licitacoes": [
        "edital",
        "proposta_tecnica",
        "proposta_comercial",
        "habilitacao",
        "impugnacao",
        "recurso",
        "ata_pregao",
        "contrato_licitacao",
        "certidao_habilitacao",
    ],
    "financeiro": [
        "fatura",
        "boleto",
        "comprovante_pagamento_salario",
        "comprovante_pagamento_fgts",
        "extrato_bancario",
        "dre",
        "fluxo_caixa",
        "inadimplencia",
        "nota_debito",
    ],
}

# Stopwords PT-BR
_STOPWORDS = {
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "na",
    "no",
    "nas",
    "nos",
    "e",
    "ou",
    "a",
    "o",
    "as",
    "os",
    "um",
    "uma",
    "para",
    "por",
    "com",
    "que",
    "se",
    "ao",
    "aos",
    "às",
}

# ── Utilitários de texto ──────────────────────────────────────────────────────


def _tokenizar(texto: str) -> list[str]:
    """Tokenizar texto em português."""
    texto = texto.lower()
    texto = re.sub(r"[^\w\sáéíóúâêîôûãõàèìòùç]", " ", texto)
    return [t for t in texto.split() if len(t) > 2 and t not in _STOPWORDS]


def _normalizar(texto: str) -> str:
    """Normaliza texto: minúsculas, sem acentos (ASCII simplificado)."""
    import unicodedata

    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ── Embedding ─────────────────────────────────────────────────────────────────


def _texto_para_vetor(texto: str) -> list[float]:
    """
    Gera vetor denso de EMBEDDING_DIM (1536) dimensões a partir do texto.
    Estratégia: hash determinístico + termos de domínio + posição de tokens.
    Garante exatamente 1536 dimensões sem dependência externa.
    """
    tokens = _tokenizar(texto)
    vetor = [0.0] * EMBEDDING_DIM

    if not tokens:
        return vetor

    # Bloco 1 (0-511): hash por token → posição determinística
    for i, token in enumerate(tokens[:256]):
        h = int(hashlib.md5(token.encode(), usedforsecurity=False).hexdigest(), 16)  # noqa: S324
        pos = h % 512
        # peso: posição no texto importa (primeiros tokens = mais relevantes)
        weight = 1.0 / math.sqrt(i + 1)
        vetor[pos] = min(1.0, vetor[pos] + weight)

    # Bloco 2 (512-1023): TF normalizado por bigrams
    for i in range(len(tokens) - 1):
        bigram = tokens[i] + "_" + tokens[i + 1]
        h = int(hashlib.md5(bigram.encode(), usedforsecurity=False).hexdigest(), 16)  # noqa: S324
        pos = 512 + (h % 512)
        vetor[pos] = min(1.0, vetor[pos] + 0.5)

    # Bloco 3 (1024-1279): módulos detectados
    texto_norm = _normalizar(texto)
    for m_idx, (_modulo, termos) in enumerate(TERMOS_MODULOS.items()):
        base = 1024 + m_idx * 32
        for t_idx, termo in enumerate(termos[:32]):
            if termo.replace("_", " ") in texto_norm or termo in texto_norm:
                pos = base + (t_idx % 32)
                vetor[pos] = min(1.0, vetor[pos] + 1.0)

    # Bloco 4 (1280-1535): frequência TF normalizada
    n_tokens = len(tokens) or 1
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    for token, cnt in freq.items():
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        pos = 1280 + (h % 256)
        vetor[pos] = min(1.0, vetor[pos] + cnt / n_tokens)

    # Normalização L2
    norm = math.sqrt(sum(x * x for x in vetor))
    if norm > 0:
        vetor = [x / norm for x in vetor]

    return vetor


def _gerar_embedding(texto: str, client: Any | None) -> tuple[list[float], str]:
    """
    Gera embedding via OpenAI text-embedding-3-large com dimensions=1536 (primário)
    ou dense fallback (mesma dimensão — índice existente continua compatível).
    Retorna (vetor, model_name).

    `client` é um cliente OpenAI (openai.OpenAI) ou None.
    """
    if client is not None:
        try:
            response = client.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL,
                input=texto[:8000],
                # 3-large nativo é 3072 dims; travamos em 1536 p/ manter o índice
                dimensions=EMBEDDING_DIM,
            )
            vetor = list(response.data[0].embedding)
            if len(vetor) == EMBEDDING_DIM:
                return vetor, EMBEDDING_MODEL_NAME_OPENAI
            logger.warning(
                "SOPHIA: embedding OpenAI com dimensão inesperada (%d) — usando dense fallback",
                len(vetor),
            )
        except Exception as e:
            logger.debug("SOPHIA: OpenAI embedding fallback: %s", e)

    # Fallback: dense 1536
    vetor = _texto_para_vetor(texto)
    return vetor, EMBEDDING_MODEL_NAME_FALLBACK


def _similaridade_coseno(v1: list[float], v2: list[float]) -> float:
    """Calcula similaridade de cosseno entre dois vetores."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (n1 * n2)))


# ── PostgreSQL via subprocess ─────────────────────────────────────────────────


def _psql(query: str, params: dict | None = None) -> str:
    """Executa query no PostgreSQL via docker exec."""
    if params:
        # Substituição simples de parâmetros nomeados
        for key, val in params.items():
            if val is None:
                query = query.replace(f":{key}", "NULL")
            elif isinstance(val, bool):
                query = query.replace(f":{key}", "TRUE" if val else "FALSE")
            elif isinstance(val, (int, float)):
                query = query.replace(f":{key}", str(val))
            elif isinstance(val, list):
                arr_str = "ARRAY[" + ",".join(str(x) for x in val) + "]::FLOAT8[]"
                query = query.replace(f":{key}", arr_str)
            else:
                escaped = str(val).replace("'", "''")
                query = query.replace(f":{key}", f"'{escaped}'")

    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DB,
        "-t",
        "-A",
        "-c",
        query,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)  # noqa: S603
        return result.stdout.strip()
    except Exception as e:
        logger.warning("SOPHIA psql erro: %s", e)
        return ""


def _psql_rows(query: str) -> list[dict]:
    """Executa query e retorna lista de dicts (CSV parsing simples)."""
    # Usar -F para separador e incluir headers
    cmd = [
        "docker",
        "exec",
        POSTGRES_CONTAINER,
        "psql",
        "-U",
        POSTGRES_USER,
        "-d",
        POSTGRES_DB,
        "-t",
        "-A",
        "--csv",
        "-c",
        query,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)  # noqa: S603
        lines = result.stdout.strip().splitlines()
        if not lines or lines == [""]:
            return []
        # Primeira linha = headers
        if len(lines) < 1:
            return []
        # Re-run com header
        cmd2 = [
            "docker",
            "exec",
            POSTGRES_CONTAINER,
            "psql",
            "-U",
            POSTGRES_USER,
            "-d",
            POSTGRES_DB,
            "-A",
            "--csv",
            "-c",
            query,
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=30)  # noqa: S603
        lines2 = result2.stdout.strip().splitlines()
        if not lines2:
            return []
        import csv
        import io

        reader = csv.DictReader(io.StringIO(result2.stdout.strip()))
        return list(reader)
    except Exception as e:
        logger.warning("SOPHIA psql_rows erro: %s", e)
        return []


# ── Classe principal ──────────────────────────────────────────────────────────


class Sophia:
    """
    SOPHIA v2.0 — Busca Semântica Cross-Módulo.

    Motor: OpenAI text-embedding-3-large (primário, 1536 dims) + dense 1536 fallback.
    Síntese LLM: cascata OpenAI (gpt-5) → Anthropic → síntese local.
    Escopo: dp, rh, ged, operacional, fiscal, contratos, licitacoes, financeiro.
    """

    def __init__(self) -> None:
        self._client: Any = None  # cliente OpenAI (embeddings)
        self._usando_openai: bool = False
        self._usando_anthropic: bool = False  # legado — Anthropic saiu do caminho de embeddings
        self._inicializar()

    def _inicializar(self) -> None:
        """Inicializa cliente OpenAI (embeddings) se API key disponível."""
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            logger.info("SOPHIA v2.0: OPENAI_API_KEY não configurada — usando dense fallback")
            return
        try:
            from openai import OpenAI

            self._client = OpenAI(api_key=api_key)
            # Teste rápido do endpoint de embeddings (com dimensions=1536, como no uso real)
            self._client.embeddings.create(
                model=OPENAI_EMBEDDING_MODEL, input="ok", dimensions=EMBEDDING_DIM
            )
            self._usando_openai = True
            logger.info("SOPHIA v2.0: OpenAI embeddings conectado — motor premium ativo")
        except Exception as e:
            logger.warning("SOPHIA v2.0: OpenAI indisponível (%s) — usando dense fallback", e)
            self._client = None
            self._usando_openai = False

    # ── Indexação ─────────────────────────────────────────────────────────────

    def indexar_documento(
        self,
        doc_id: str,
        texto: str,
        metadados: dict[str, Any] | None = None,
    ) -> bool:
        """
        Indexa documento no gedeon_document_index.
        Gera embedding 1536 dims e persiste via PostgreSQL.
        ON CONFLICT (doc_id) DO UPDATE.
        """
        if not texto or not texto.strip():
            return False

        metadados = metadados or {}
        try:
            # Gerar embedding
            vetor, model_name = _gerar_embedding(texto, self._client)

            # Extrair campos do metadados
            modulo = metadados.get("modulo") or self._detectar_modulo(texto)
            submodulo = metadados.get("submodulo")
            funcionario_id = metadados.get("funcionario_id")
            vencimento_raw = metadados.get("vencimento")
            impacto_folha = bool(metadados.get("impacto_folha", False))

            # Se não definido explicitamente, inferir impacto_folha
            if not impacto_folha and modulo in ("dp", "rh", "ged", "financeiro"):
                impacto_folha = True

            # Normalizar vencimento
            vencimento_sql = "NULL"
            if vencimento_raw:
                try:
                    if isinstance(vencimento_raw, str):
                        # aceita YYYY-MM-DD
                        parsed = datetime.strptime(vencimento_raw[:10], "%Y-%m-%d").date()
                        vencimento_sql = f"'{parsed.isoformat()}'"
                    elif isinstance(vencimento_raw, date):
                        vencimento_sql = f"'{vencimento_raw.isoformat()}'"
                except Exception:
                    pass

            doc_hash = hashlib.sha256(texto.encode()).hexdigest()[:16]
            texto_preview = texto[:500]
            tokens = _tokenizar(texto)
            metadados_json = json.dumps(metadados, ensure_ascii=False, default=str)
            tokens_json = json.dumps(sorted(set(tokens)), ensure_ascii=False)

            # Montar array embedding
            embedding_arr = "ARRAY[" + ",".join(f"{x:.8f}" for x in vetor) + "]::FLOAT8[]"

            # Campos opcionais
            modulo_sql = f"'{modulo}'" if modulo else "NULL"
            submodulo_sql = f"'{submodulo}'" if submodulo else "NULL"
            funcionario_id_sql = f"'{funcionario_id}'::UUID" if funcionario_id else "NULL"

            metadados_esc = metadados_json.replace("'", "''")
            tokens_esc = tokens_json.replace("'", "''")
            texto_esc = texto_preview.replace("'", "''")
            doc_id_esc = doc_id.replace("'", "''")

            sql = f"""
INSERT INTO gedeon_document_index
    (doc_id, texto_preview, metadados, tokens, embedding,
     embedding_anthropic, embedding_model, embedding_dim,
     modulo, submodulo, funcionario_id, vencimento, impacto_folha, hash)
VALUES
    ('{doc_id_esc}', '{texto_esc}', '{metadados_esc}'::jsonb, '{tokens_esc}'::jsonb,
     {embedding_arr}, {embedding_arr}, '{model_name}', {EMBEDDING_DIM},
     {modulo_sql}, {submodulo_sql}, {funcionario_id_sql}, {vencimento_sql},
     {"TRUE" if impacto_folha else "FALSE"}, '{doc_hash}')
ON CONFLICT (doc_id) DO UPDATE SET
    texto_preview = EXCLUDED.texto_preview,
    metadados = EXCLUDED.metadados,
    tokens = EXCLUDED.tokens,
    embedding = EXCLUDED.embedding,
    embedding_anthropic = EXCLUDED.embedding_anthropic,
    embedding_model = EXCLUDED.embedding_model,
    embedding_dim = EXCLUDED.embedding_dim,
    modulo = EXCLUDED.modulo,
    submodulo = EXCLUDED.submodulo,
    funcionario_id = EXCLUDED.funcionario_id,
    vencimento = EXCLUDED.vencimento,
    impacto_folha = EXCLUDED.impacto_folha,
    hash = EXCLUDED.hash,
    updated_at = NOW()
"""
            _psql(sql)
            return True
        except Exception as e:
            logger.warning("SOPHIA indexar_documento erro [%s]: %s", doc_id, e)
            return False

    # ── Busca ─────────────────────────────────────────────────────────────────

    def buscar(
        self,
        query: str,
        top_k: int = 10,
        filtros: dict[str, Any] | None = None,
        threshold: float = 0.30,
    ) -> list[dict]:
        """
        Busca semântica por similaridade de cosseno.
        Suporta filtros: modulo, cliente_id, funcionario_id, tipo, competencia,
                         impacto_folha, vencendo_em_dias, modulos (lista).
        """
        if not query or not query.strip():
            return []

        filtros = filtros or {}

        # Detectar módulo implícito na query
        # Módulo implícito detectado (usado para logs/debug)
        _modulo_implicito = self._detectar_modulo(query)

        # Gerar vetor da query (OpenAI se disponível; senão dense)
        query_vetor, query_model = _gerar_embedding(query, self._client)

        # Construir cláusula WHERE
        where_clauses = ["1=1"]

        if filtros.get("modulo"):
            m = filtros["modulo"].replace("'", "''")
            where_clauses.append(f"modulo = '{m}'")
        elif filtros.get("modulos"):
            mods = [f"'{m.replace(chr(39), chr(39) + chr(39))}'" for m in filtros["modulos"]]
            where_clauses.append(f"modulo IN ({','.join(mods)})")

        if filtros.get("cliente_id"):
            cid = filtros["cliente_id"].replace("'", "''")
            where_clauses.append(f"metadados->>'cliente_id' = '{cid}'")

        if filtros.get("funcionario_id"):
            fid = filtros["funcionario_id"].replace("'", "''")
            where_clauses.append(f"(funcionario_id = '{fid}'::UUID OR metadados->>'funcionario_id' = '{fid}')")

        if filtros.get("tipo"):
            t = filtros["tipo"].replace("'", "''")
            where_clauses.append(f"metadados->>'tipo' = '{t}'")

        if filtros.get("competencia"):
            comp = filtros["competencia"].replace("'", "''")
            where_clauses.append(f"metadados->>'competencia' = '{comp}'")

        if filtros.get("impacto_folha"):
            where_clauses.append("impacto_folha = TRUE")

        if filtros.get("vencendo_em_dias") is not None:
            dias = int(filtros["vencendo_em_dias"])
            where_clauses.append(f"vencimento IS NOT NULL AND vencimento <= CURRENT_DATE + INTERVAL '{dias} days'")

        where_sql = " AND ".join(where_clauses)

        # Buscar candidatos do banco (limitamos a 500 para calcular similaridade)
        sql = f"""
SELECT doc_id, texto_preview, metadados, embedding_anthropic, embedding,
       embedding_model, modulo, vencimento::text, impacto_folha
FROM gedeon_document_index
WHERE {where_sql}
  AND (embedding_anthropic IS NOT NULL OR embedding IS NOT NULL)
ORDER BY updated_at DESC
LIMIT 500
"""
        rows = _psql_rows(sql)

        # Também gerar vetor direto da query (dense, sem API) para docs indexados no espaço dense
        query_vetor_direto = _texto_para_vetor(query)

        resultados = []
        for row in rows:
            try:
                texto_doc = row.get("texto_preview", "")
                # Recuperar vetor (preferir embedding_anthropic)
                emb_raw = row.get("embedding_anthropic") or row.get("embedding") or ""
                score_cosine = 0.0
                if emb_raw and emb_raw not in ("", "NULL", None):
                    try:
                        # Parse do array PostgreSQL: {0.1,0.2,...}
                        emb_str = emb_raw.strip("{}")
                        doc_vetor = [float(x) for x in emb_str.split(",") if x.strip()]
                        if len(doc_vetor) == EMBEDDING_DIM:
                            # Comparar vetores no MESMO espaço: docs indexados via OpenAI
                            # usam o vetor OpenAI da query; docs legados (dense/anthropic-
                            # enriquecido) usam o vetor dense direto da query.
                            doc_model = row.get("embedding_model") or ""
                            if doc_model == EMBEDDING_MODEL_NAME_OPENAI and query_model == EMBEDDING_MODEL_NAME_OPENAI:
                                score_cosine = _similaridade_coseno(query_vetor, doc_vetor)
                            else:
                                score_cosine = _similaridade_coseno(query_vetor_direto, doc_vetor)
                    except Exception:
                        pass

                # Similaridade textual como complemento
                score_textual = self._similaridade_textual(query, texto_doc)

                # Score final: máximo entre cosine e textual
                score = max(score_cosine, score_textual)

                if score < threshold:
                    continue

                meta = {}
                try:
                    meta_raw = row.get("metadados", "{}")
                    if meta_raw:
                        meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                except Exception:
                    pass

                resultados.append(
                    {
                        "doc_id": row.get("doc_id", ""),
                        "preview": (row.get("texto_preview") or "")[:200],
                        "metadados": meta,
                        "score": round(score, 4),
                        "modulo": row.get("modulo") or meta.get("modulo", ""),
                        "tipo": meta.get("tipo", ""),
                        "cliente": meta.get("cliente_nome", "") or meta.get("cliente_id", ""),
                        "funcionario": meta.get("funcionario_nome", "") or meta.get("funcionario_id", ""),
                        "competencia": meta.get("competencia", ""),
                        "vencimento": row.get("vencimento") or meta.get("vencimento", ""),
                        "impacto_folha": row.get("impacto_folha") in ("TRUE", "t", "true", True),
                        "modo_busca": "sophia_v2_cosine",
                    }
                )
            except Exception as e:
                logger.debug("SOPHIA buscar row erro: %s", e)
                continue

        # Ordenar por score
        resultados.sort(key=lambda x: x["score"], reverse=True)
        return resultados[:top_k]

    def _similaridade_textual(self, query: str, texto: str) -> float:
        """Similaridade textual simples como fallback quando não há embedding."""
        q_tokens = set(_tokenizar(query))
        d_tokens = set(_tokenizar(texto))
        if not q_tokens or not d_tokens:
            return 0.0
        intersection = q_tokens & d_tokens
        union = q_tokens | d_tokens
        return len(intersection) / len(union) if union else 0.0

    # ── Detecção de módulo ────────────────────────────────────────────────────

    def _detectar_modulo(self, query: str) -> str:
        """
        Detecta módulo implícito a partir dos termos da query.
        Retorna o módulo com maior score de correspondência.
        """
        query_norm = _normalizar(query)
        scores: dict[str, float] = dict.fromkeys(MODULOS_ESCOPO, 0.0)

        for modulo, termos in TERMOS_MODULOS.items():
            for termo in termos:
                termo_norm = termo.replace("_", " ")
                if termo_norm in query_norm or termo in query_norm:
                    scores[modulo] += 1.0
                elif any(t in query_norm for t in termo_norm.split()):
                    scores[modulo] += 0.3

        best = max(scores, key=lambda k: scores[k])
        if scores[best] > 0:
            return best
        return "ged"  # default

    # ── Perguntar ─────────────────────────────────────────────────────────────

    def perguntar(
        self,
        pergunta: str,
        cliente_id: str | None = None,
        funcionario_id: str | None = None,
        modulo: str | None = None,
        competencia: str | None = None,
    ) -> dict:
        """
        Responde pergunta em linguagem natural com base no acervo documental.
        Busca documentos relevantes e sintetiza resposta.
        """
        filtros: dict[str, Any] = {}
        if cliente_id:
            filtros["cliente_id"] = cliente_id
        if funcionario_id:
            filtros["funcionario_id"] = funcionario_id
        if modulo:
            filtros["modulo"] = modulo
        if competencia:
            filtros["competencia"] = competencia

        # Detectar módulo implícito
        modulo_detectado = modulo or self._detectar_modulo(pergunta)

        # Buscar documentos relevantes
        docs = self.buscar(pergunta, top_k=8, filtros=filtros or None, threshold=0.25)

        if not docs:
            # Segunda tentativa sem filtros de módulo
            docs = self.buscar(pergunta, top_k=5, threshold=0.20)

        if not docs:
            return {
                "pergunta": pergunta,
                "resposta": f"Nenhum documento encontrado no acervo para '{pergunta}'.",
                "docs_usados": 0,
                "documentos": [],
                "modulo_detectado": modulo_detectado,
                "confianca": 0.0,
                "motor": "sophia_v2",
            }

        # Sintetizar resposta: cascata LLM (OpenAI → Anthropic) → síntese local
        resposta = self._sintetizar_llm(pergunta, docs)

        confianca = round(sum(d["score"] for d in docs[:3]) / min(3, len(docs)), 3)

        return {
            "pergunta": pergunta,
            "resposta": resposta,
            "docs_usados": len(docs),
            "documentos": docs[:5],
            "modulo_detectado": modulo_detectado,
            "confianca": confianca,
            "motor": "sophia_v2_openai" if self._usando_openai else "sophia_v2_dense",
        }

    def _sintetizar_llm(self, pergunta: str, docs: list[dict]) -> str:
        """Sintetiza resposta via cascata LLM (OpenAI gpt-5 → Anthropic → local)."""
        context = "\n".join(
            f"[{i + 1}] ({d.get('modulo', '?')}) {d.get('preview', '')[:150]}" for i, d in enumerate(docs[:5])
        )
        prompt = (
            f"Com base nos seguintes documentos do sistema ERP:\n\n{context}\n\n"
            f"Responda de forma direta e objetiva: {pergunta}\n\n"
            f"Seja conciso (máx 3 frases). Cite o tipo de documento quando relevante."
        )
        try:
            from core.llm_cascade import chat as llm_chat

            resposta = llm_chat(
                messages=[{"role": "user", "content": prompt}],
                model_openai=OPENAI_LLM_MODEL,
                model_anthropic=ANTHROPIC_MODEL,
                max_tokens=200,
            )
            if resposta:
                return resposta.strip()
        except Exception as e:
            logger.warning("SOPHIA sintetizar LLM erro: %s", e)
        return self._sintetizar_local(pergunta, docs)

    def _sintetizar_local(self, pergunta: str, docs: list[dict]) -> str:
        """Síntese local sem LLM (fallback honesto)."""
        p = pergunta.lower()

        if any(x in p for x in ["quantos", "total", "count", "número", "numero"]):
            return f"Encontrei {len(docs)} documentos relacionados a '{pergunta}'."

        if any(x in p for x in ["impacto", "folha", "afeta"]):
            impacto_docs = [d for d in docs if d.get("impacto_folha")]
            if impacto_docs:
                tipos = list({d.get("tipo", "documento") for d in impacto_docs[:3]})
                return f"Encontrei {len(impacto_docs)} documentos que impactam a folha: {', '.join(tipos)}."

        if any(x in p for x in ["vencendo", "vence", "vencimento", "expirar"]):
            venc_docs = [d for d in docs if d.get("vencimento")]
            if venc_docs:
                primeiro = venc_docs[0]
                return (
                    f"Documento '{primeiro.get('tipo', '?')}' vence em {primeiro.get('vencimento', '?')}. "
                    f"Total: {len(venc_docs)} documentos com vencimento próximo."
                )

        # Resposta genérica
        nomes = [f"{d.get('tipo', 'documento')} ({d.get('modulo', '?')})" for d in docs[:3]]
        return f"Encontrei {len(docs)} documentos relevantes. Os mais pertinentes: {', '.join(nomes)}."

    # ── Impacto na folha ──────────────────────────────────────────────────────

    def buscar_impacto_folha(self, competencia: str | None = None) -> list[dict]:
        """Retorna documentos que impactam a folha de pagamento."""
        where = "impacto_folha = TRUE"
        if competencia:
            comp_esc = competencia.replace("'", "''")
            where += f" AND metadados->>'competencia' = '{comp_esc}'"

        sql = f"""
SELECT doc_id, texto_preview, metadados, modulo, vencimento::text, impacto_folha
FROM gedeon_document_index
WHERE {where}
ORDER BY modulo, updated_at DESC
LIMIT 200
"""
        rows = _psql_rows(sql)
        resultados = []
        for row in rows:
            try:
                meta = {}
                try:
                    meta_raw = row.get("metadados", "{}")
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                except Exception:
                    pass
                resultados.append(
                    {
                        "doc_id": row.get("doc_id", ""),
                        "preview": (row.get("texto_preview") or "")[:200],
                        "modulo": row.get("modulo") or meta.get("modulo", ""),
                        "tipo": meta.get("tipo", ""),
                        "competencia": meta.get("competencia", ""),
                        "vencimento": row.get("vencimento", ""),
                        "impacto_folha": True,
                        "metadados": meta,
                    }
                )
            except Exception as exc:  # noqa: S112
                logger.debug("SOPHIA row parse erro: %s", exc)
                continue
        return resultados

    # ── Alertas de vencimento ─────────────────────────────────────────────────

    def alertas_vencimento(
        self,
        dias: int = 30,
        modulos: list[str] | None = None,
    ) -> list[dict]:
        """
        Retorna documentos com vencimento nos próximos N dias.
        Opcionalmente filtra por lista de módulos.
        """
        where = f"vencimento IS NOT NULL AND vencimento <= CURRENT_DATE + INTERVAL '{dias} days' AND vencimento >= CURRENT_DATE - INTERVAL '1 day'"

        if modulos:
            mods = [f"'{m.replace(chr(39), chr(39) + chr(39))}'" for m in modulos]
            where += f" AND modulo IN ({','.join(mods)})"

        sql = f"""
SELECT doc_id, texto_preview, metadados, modulo, vencimento::text, impacto_folha,
       (vencimento - CURRENT_DATE) AS dias_restantes
FROM gedeon_document_index
WHERE {where}
ORDER BY vencimento ASC
LIMIT 100
"""
        rows = _psql_rows(sql)
        resultados = []
        for row in rows:
            try:
                meta = {}
                try:
                    meta_raw = row.get("metadados", "{}")
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                except Exception:
                    pass

                dias_rest = row.get("dias_restantes", "")
                try:
                    dias_rest = int(dias_rest)
                except Exception:
                    dias_rest = None

                nivel = "info"
                if dias_rest is not None:
                    if dias_rest <= 0:
                        nivel = "critico"
                    elif dias_rest <= 7:
                        nivel = "urgente"
                    elif dias_rest <= 15:
                        nivel = "alto"
                    elif dias_rest <= 30:
                        nivel = "medio"

                resultados.append(
                    {
                        "doc_id": row.get("doc_id", ""),
                        "preview": (row.get("texto_preview") or "")[:200],
                        "modulo": row.get("modulo") or meta.get("modulo", ""),
                        "tipo": meta.get("tipo", ""),
                        "vencimento": row.get("vencimento", ""),
                        "dias_restantes": dias_rest,
                        "nivel": nivel,
                        "impacto_folha": row.get("impacto_folha") in ("TRUE", "t", "true", True),
                        "metadados": meta,
                    }
                )
            except Exception as exc:  # noqa: S112
                logger.debug("SOPHIA row parse erro: %s", exc)
                continue
        return resultados

    # ── Reindexação ───────────────────────────────────────────────────────────

    def reindexar_acervo(
        self,
        batch_size: int = 50,
        modulo_filter: str | None = None,
    ) -> dict:
        """
        Re-indexa documentos existentes com novo embedding v2.
        Processa documentos sem embedding_anthropic ou com model antigo.
        """
        where = "1=1"
        if modulo_filter:
            mf = modulo_filter.replace("'", "''")
            where = f"modulo = '{mf}'"

        sql = f"""
SELECT doc_id, texto_preview, metadados, modulo
FROM gedeon_document_index
WHERE {where}
  AND (embedding_anthropic IS NULL OR embedding_model != '{EMBEDDING_MODEL_NAME_OPENAI}')
ORDER BY created_at ASC
LIMIT {batch_size}
"""
        rows = _psql_rows(sql)
        total = len(rows)
        reindexados = 0

        for row in rows:
            try:
                meta = {}
                try:
                    meta_raw = row.get("metadados", "{}")
                    meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                except Exception:
                    pass

                texto = row.get("texto_preview", "")
                if not texto:
                    continue

                # Re-indexar com embedding v2
                ok = self.indexar_documento(
                    doc_id=row["doc_id"],
                    texto=texto,
                    metadados=meta,
                )
                if ok:
                    reindexados += 1
            except Exception as e:
                logger.debug("SOPHIA reindexar erro [%s]: %s", row.get("doc_id"), e)
                continue

        return {
            "total_processados": total,
            "reindexados": reindexados,
            "modelo": EMBEDDING_MODEL_NAME_OPENAI if self._usando_openai else EMBEDDING_MODEL_NAME_FALLBACK,
            "modulo_filter": modulo_filter,
            "batch_size": batch_size,
        }

    def indexar_acervo_completo(self, documentos: list[dict] | None = None) -> dict:
        """
        Indexa lista de documentos ou reconstrói do banco.
        documentos: lista de dicts com keys: doc_id, texto, metadados
        """
        if documentos is None:
            # Reindexar acervo existente sem embedding v2
            resultado = self.reindexar_acervo(batch_size=200)
            return {
                "indexados": resultado["reindexados"],
                "total": resultado["total_processados"],
                "modelo": resultado["modelo"],
            }

        indexados = 0
        for doc in documentos:
            doc_id = doc.get("doc_id") or doc.get("id", "")
            texto = doc.get("texto", "")
            meta = doc.get("metadados", {})
            if doc_id and texto:
                if self.indexar_documento(doc_id, texto, meta):
                    indexados += 1

        return {
            "indexados": indexados,
            "total": len(documentos),
            "modelo": EMBEDDING_MODEL_NAME_OPENAI if self._usando_openai else EMBEDDING_MODEL_NAME_FALLBACK,
        }

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        """Retorna status do índice SOPHIA v2.0."""
        try:
            total_raw = _psql("SELECT COUNT(*) FROM gedeon_document_index")
            total = int(total_raw) if total_raw.isdigit() else 0
        except Exception:
            total = 0

        try:
            com_embedding_raw = _psql(
                "SELECT COUNT(*) FROM gedeon_document_index WHERE embedding_anthropic IS NOT NULL"
            )
            com_embedding = int(com_embedding_raw) if com_embedding_raw.isdigit() else 0
        except Exception:
            com_embedding = 0

        try:
            por_modulo_raw = _psql(
                "SELECT modulo, COUNT(*) FROM gedeon_document_index WHERE modulo IS NOT NULL GROUP BY modulo ORDER BY modulo"
            )
            por_modulo = {}
            for line in por_modulo_raw.splitlines():
                parts = line.split("|")
                if len(parts) == 2:
                    por_modulo[parts[0]] = int(parts[1])
        except Exception:
            por_modulo = {}

        return {
            "versao": "2.0",
            "motor_ativo": EMBEDDING_MODEL_NAME_OPENAI if self._usando_openai else EMBEDDING_MODEL_NAME_FALLBACK,
            "using_openai": self._usando_openai,
            "using_anthropic": self._usando_anthropic,  # legado — sempre False (embeddings via OpenAI)
            "dimensao_embedding": EMBEDDING_DIM,
            "modulos_escopo": list(MODULOS_ESCOPO.keys()),
            "modulos_descricao": MODULOS_ESCOPO,
            "total_documentos": total,
            "documentos_com_embedding_v2": com_embedding,
            "distribuicao_modulos": por_modulo,
            "modelo_embedding": EMBEDDING_MODEL_NAME_OPENAI
            if self._usando_openai
            else EMBEDDING_MODEL_NAME_FALLBACK,
            "status": "operacional",
        }


# ── Singleton global ──────────────────────────────────────────────────────────

sophia = Sophia()

# Alias de retrocompatibilidade — código legado importa SophiaIndex
SophiaIndex = Sophia
