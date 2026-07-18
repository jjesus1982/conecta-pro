"""Bloco de contexto do GRUPO CONECTA MAIS para os consultores IA (Multi-CNPJ E8).

Fonte única: tabela `empresas` (+ fronteira da transição via env). Todos os
consultores injetam este bloco em vez de fatos societários hardcoded — quando a
estrutura mudar (ex.: CNPJ1 voltar ao Simples em 2027), muda AQUI/na tabela e
todos os 8 consultores ficam corretos de uma vez.

Nunca lança: em falha de banco devolve o fallback estático HONESTO (fatos
verificados em 2026-07-17/18 — documentos oficiais + dinheiro real conciliado).
"""

from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger(__name__)

_TTL_S = 300.0
_cache: list = [0.0, None]

_FALLBACK = """ESTRUTURA DO GRUPO CONECTA MAIS (2 empresas — fatos verificados 07/2026):
- CONECTAMAIS ELETRONICA LTDA (exibição: Conecta Mais Eletrônica), CNPJ 35.710.481/0001-03,
  IM 45177801, LUCRO REAL (retorno ao Simples previsto p/ 01/2027). Papel: SEGURANÇA
  ELETRÔNICA, CFTV/monitoramento e PORTARIA REMOTA. Banco: Inter. Só contratados PJ pós-transição.
- CONECTAMAIS PATRIMONIAL LTDA (exibição: Conecta Mais Patrimonial), CNPJ 66.014.833/0001-10,
  IM 721042001, SIMPLES NACIONAL (Anexo III), ATIVA desde 31/03/2026. Papel: TERCEIRIZAÇÃO DE
  MÃO DE OBRA (portaria presencial, limpeza, jardinagem, ASG). Banco: CORA (0001/7382527-7).
  JÁ EMITE NFS-e (desde 06/2026) e JÁ RECEBE no Cora. Todos os CLT migram para ela (competência
  de corte conforme transição executada pela Portte).
REGRAS AO RESPONDER:
- Dados agregados sem filtro de empresa = "GRUPO (2 CNPJs — consolidado)"; diga isso explicitamente.
- NFS-e de mão de obra tem INSS 11% retido na fonte pelo tomador → recebimento LÍQUIDO = bruto − 11%.
- Liminares (PIS/COFINS zero, INSS não retido) estão A SOLICITAR — NÃO aplicar como vigentes.
- Nunca invente número: sem dado integrado (ex.: novo banco), responda "aguardando integração"."""


def bloco_contexto_grupo() -> str:
    """Bloco dinâmico (empresas ativas do banco) com fallback estático honesto."""
    agora = time.monotonic()
    if _cache[1] and (agora - _cache[0]) < _TTL_S:
        return _cache[1]
    try:
        import psycopg2

        url = re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))
        conn = psycopg2.connect(url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nome_fantasia, razao_social, cnpj, inscricao_municipal, "
                    "regime_tributario, anexo_simples, regime_futuro FROM empresas "
                    "WHERE status='ativa' ORDER BY is_principal DESC"
                )
                rows = cur.fetchall()
        finally:
            conn.close()
        if not rows:
            raise LookupError("tabela empresas vazia")
        linhas = []
        for fant, razao, cnpj, im, regime, anexo, futuro in rows:
            extra = f", Anexo {anexo}" if anexo else ""
            fut = f" (futuro: {futuro})" if futuro else ""
            linhas.append(
                f"- {razao} (exibição: {fant}), CNPJ {cnpj}, IM {im or '-'}, "
                f"regime {str(regime).upper()}{extra}{fut}."
            )
        fronteira = (os.getenv("MULTICNPJ_FRONTEIRA_COMPETENCIA") or "").strip()
        transicao = (
            f"Competência de corte da folha/documentos: {fronteira} (anteriores = Eletrônica, sempre)."
            if fronteira
            else "Transição trabalhista em curso pela Portte — competência de corte ainda não cravada."
        )
        texto = (
            "ESTRUTURA DO GRUPO CONECTA MAIS (fonte: cadastro vivo do sistema):\n"
            + "\n".join(linhas)
            + "\nPapéis: Eletrônica = segurança eletrônica/CFTV/portaria REMOTA (banco Inter); "
            "Patrimonial = terceirização de mão de obra (banco CORA; NFS-e com INSS 11% retido "
            "na fonte → recebimento líquido = bruto − 11%).\n"
            + transicao
            + "\nREGRAS: agregados sem filtro de empresa = 'GRUPO (consolidado)' — explicite; "
            "liminares só valem se CONCEDIDAS no cadastro; sem dado integrado, responda "
            "'aguardando integração' — nunca invente número."
        )
        _cache[0], _cache[1] = agora, texto
        return texto
    except Exception as exc:  # noqa: BLE001
        logger.warning("contexto_grupo: usando fallback estático (%s)", exc)
        return _FALLBACK
