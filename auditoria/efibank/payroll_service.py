"""
Orquestração da folha em lote.

A Efí NÃO tem endpoint de lote nativo — o "lote" é responsabilidade do Conecta
PRO: um envio por funcionário, com concorrência limitada e idempotência forte.

Garantias desenhadas aqui:
  1. Nunca pagar duas vezes: id_envio determinístico + UNIQUE no banco +
     claim atômico via SELECT ... FOR UPDATE SKIP LOCKED.
  2. Nunca disparar lote não conferido: soma dos itens tem que bater com
     total_esperado e o lote precisa estar AUTORIZADO (OTP interno).
  3. Falha de rede != falha de pagamento: erro antes de confirmar vira
     ERRO_ENVIO e é reprocessado com o MESMO id_envio (a Efí deduplica).
"""
from __future__ import annotations

import re
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .efi_client import EfiClient, EfiError
from .models import Pagamento, LotePagamento

MAX_WORKERS = 5           # concorrência: respeita rate limit da Efí (confirmar teto)
MAX_TENTATIVAS = 4
BACKOFF_BASE_S = 1.5

_ID_ENVIO_RE = re.compile(r"[^A-Za-z0-9]")


def montar_id_envio(lote_id: int, favorecido_id: int) -> str:
    """Determinístico e estável. Mesmo (lote, favorecido) => mesmo id_envio
    sempre => reprocesso não duplica. <=35 chars, só alfanumérico."""
    bruto = f"CP{lote_id}L{favorecido_id}F"
    return _ID_ENVIO_RE.sub("", bruto)[:35]


# ---------------------------------------------------------------------------
# 1) Autorização (guard antes de qualquer disparo)
# ---------------------------------------------------------------------------
def autorizar_lote(session: Session, lote_id: int, usuario: str, otp_ok: bool) -> None:
    """Trava de negócio. Sem isto, executar_lote se recusa a rodar."""
    lote = session.get(LotePagamento, lote_id, with_for_update=True)
    if lote is None:
        raise ValueError("lote inexistente")
    if lote.status != "RASCUNHO":
        raise ValueError(f"lote não está em RASCUNHO (está {lote.status})")

    soma = session.scalar(
        select(text("COALESCE(SUM(valor_centavos),0)"))
        .select_from(Pagamento).where(Pagamento.lote_id == lote_id)
    )
    if soma != lote.total_esperado_centavos:
        # Guard duro: divergência de centavo aborta. Folha não admite "quase".
        raise ValueError(f"soma dos itens ({soma}) != total esperado "
                         f"({lote.total_esperado_centavos}). Abortando.")
    if not otp_ok:
        raise PermissionError("OTP interno não validado")

    lote.status = "AUTORIZADO"
    lote.autorizado_por = usuario
    lote.autorizado_em = dt.datetime.now(dt.timezone.utc)
    session.commit()


# ---------------------------------------------------------------------------
# 2) Execução do lote
# ---------------------------------------------------------------------------
def executar_lote(
    session_factory: Callable[[], Session],
    client: EfiClient,
    lote_id: int,
) -> dict[str, int]:
    """Dispara todos os itens elegíveis. Idempotente: pode ser chamado de novo
    após falha parcial que ele só retoma o que não liquidou."""
    with session_factory() as s:
        lote = s.get(LotePagamento, lote_id)
        if lote is None or lote.status not in ("AUTORIZADO", "EM_EXECUCAO", "CONCLUIDO_COM_FALHAS"):
            raise ValueError(f"lote {lote_id} não está apto a executar")
        lote.status = "EM_EXECUCAO"
        s.commit()
        ids = list(s.scalars(
            select(Pagamento.id).where(
                Pagamento.lote_id == lote_id,
                Pagamento.status.in_(("PENDENTE", "ERRO_ENVIO")),
            )
        ))

    resumo = {"disparados": 0, "processando": 0, "falhou": 0, "pulados": 0}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(_processar_item, session_factory, client, pid) for pid in ids]
        for f in as_completed(futures):
            r = f.result()
            resumo[r] = resumo.get(r, 0) + 1
            resumo["disparados"] += 1

    _fechar_lote(session_factory, lote_id)
    return resumo


def _processar_item(session_factory, client: EfiClient, pagamento_id: int) -> str:
    """Claim atômico -> envio -> transição. Um item, uma sessão."""
    with session_factory() as s:
        # Claim: só pega se ninguém mais pegou (SKIP LOCKED evita corrida
        # entre workers/processos). Transição PENDENTE/ERRO_ENVIO -> ENVIANDO.
        row = s.execute(text("""
            SELECT id, lote_id, favorecido_id, valor_centavos, chave_pix_destino,
                   info_pagador, id_envio, tentativas, status
              FROM folha_efi.pagamento
             WHERE id = :id AND status IN ('PENDENTE','ERRO_ENVIO')
               FOR UPDATE SKIP LOCKED
        """), {"id": pagamento_id}).mappings().first()
        if row is None:
            return "pulados"
        lote = s.get(LotePagamento, row["lote_id"])
        _transicao(s, pagamento_id, row["status"], "ENVIANDO", "api")
        s.execute(text("UPDATE folha_efi.pagamento SET status='ENVIANDO',"
                       " tentativas=tentativas+1, enviado_em=now(), updated_at=now()"
                       " WHERE id=:id"), {"id": pagamento_id})
        s.commit()
        dados = dict(row)
        chave_origem = lote.chave_pix_origem

    # Chamada externa FORA da transação (não segura lock durante I/O de rede).
    try:
        resp = client.enviar_pix_por_chave(
            id_envio=dados["id_envio"],
            valor_centavos=dados["valor_centavos"],
            chave_origem=chave_origem,
            chave_destino=dados["chave_pix_destino"],
            info_pagador=dados["info_pagador"] or "Folha Conecta",
        )
    except EfiError as e:
        return _marcar_falha(session_factory, pagamento_id, e)

    e2e = resp.get("e2eId") or resp.get("e2e_id")
    with session_factory() as s:
        _transicao(s, pagamento_id, "ENVIANDO", "PROCESSANDO", "api", {"e2eId": e2e})
        s.execute(text("UPDATE folha_efi.pagamento SET status='PROCESSANDO',"
                       " e2e_id=:e2e, ultimo_erro=NULL, updated_at=now() WHERE id=:id"),
                  {"e2e": e2e, "id": pagamento_id})
        s.commit()
    return "processando"


def _marcar_falha(session_factory, pagamento_id: int, e: EfiError) -> str:
    novo = "ERRO_ENVIO" if e.retryavel else "FALHOU"
    with session_factory() as s:
        _transicao(s, pagamento_id, "ENVIANDO", novo, "api", {"erro": str(e), "status": e.status})
        s.execute(text("UPDATE folha_efi.pagamento SET status=:st, ultimo_erro=:err,"
                       " updated_at=now() WHERE id=:id"),
                  {"st": novo, "err": str(e)[:1000], "id": pagamento_id})
        s.commit()
    return "falhou"


def _transicao(s: Session, pagamento_id: int, de: str, para: str, origem: str, detalhe=None):
    s.execute(text("""INSERT INTO folha_efi.pagamento_evento
                      (pagamento_id, de_status, para_status, origem, detalhe)
                      VALUES (:pid, :de, :para, :origem, :det)"""),
              {"pid": pagamento_id, "de": de, "para": para, "origem": origem,
               "det": _json(detalhe)})


def _fechar_lote(session_factory, lote_id: int) -> None:
    with session_factory() as s:
        pend = s.scalar(text("SELECT COUNT(*) FROM folha_efi.pagamento"
                             " WHERE lote_id=:l AND status IN"
                             " ('PENDENTE','ENVIANDO','ERRO_ENVIO')"), {"l": lote_id})
        falhou = s.scalar(text("SELECT COUNT(*) FROM folha_efi.pagamento"
                               " WHERE lote_id=:l AND status='FALHOU'"), {"l": lote_id})
        if pend and pend > 0:
            novo = "EM_EXECUCAO"
        elif falhou and falhou > 0:
            novo = "CONCLUIDO_COM_FALHAS"
        else:
            novo = "CONCLUIDO"
        s.execute(text("UPDATE folha_efi.lote_pagamento SET status=:st, updated_at=now()"
                       " WHERE id=:l"), {"st": novo, "l": lote_id})
        s.commit()


def _json(obj):
    import json
    return json.dumps(obj) if obj is not None else None


# ---------------------------------------------------------------------------
# 3) Reconciliação (rede da segurança: PROCESSANDO que o webhook não fechou)
# ---------------------------------------------------------------------------
def reconciliar_pendentes(session_factory, client: EfiClient, mais_velho_que_s: int = 120) -> int:
    """Job periódico. Consulta a Efí por id_envio para itens presos em
    PROCESSANDO/ENVIANDO — cobre webhook perdido. Nunca reenvia; só LÊ status."""
    ajustados = 0
    with session_factory() as s:
        ids = list(s.execute(text("""
            SELECT id, id_envio FROM folha_efi.pagamento
             WHERE status IN ('PROCESSANDO','ENVIANDO')
               AND updated_at < now() - (:sec || ' seconds')::interval
        """), {"sec": mais_velho_que_s}).mappings())
    for row in ids:
        try:
            st = client.consultar_por_id_envio(row["id_envio"])
        except EfiError:
            continue
        destino = _mapear_status(st.get("status"))
        if destino:
            with session_factory() as s:
                s.execute(text("UPDATE folha_efi.pagamento SET status=:st,"
                               " e2e_id=COALESCE(e2e_id,:e2e),"
                               " liquidado_em=CASE WHEN :st='LIQUIDADO' THEN now() ELSE liquidado_em END,"
                               " updated_at=now() WHERE id=:id AND status IN ('PROCESSANDO','ENVIANDO')"),
                          {"st": destino, "e2e": st.get("e2eId"), "id": row["id"]})
                _transicao(s, row["id"], "PROCESSANDO", destino, "reconciliacao", st)
                s.commit()
                ajustados += 1
    return ajustados


def _mapear_status(efi_status: str | None) -> str | None:
    """Mapa Efí -> nosso. CONFIRMAR os literais exatos no sandbox."""
    if not efi_status:
        return None
    m = {"REALIZADO": "LIQUIDADO", "CONCLUIDA": "LIQUIDADO",
         "NAO_REALIZADO": "FALHOU", "REJEITADO": "FALHOU", "DEVOLVIDO": "FALHOU"}
    return m.get(efi_status.upper())
