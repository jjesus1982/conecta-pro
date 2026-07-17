"""
Puxador de guias do Google Drive (pacote mensal da Portte via Onvio).

O fluxo hoje: Portte Contábil emite as guias (FGTS Digital, DARF/INSS, DCTFWeb,
consignado, parcelamentos) no Onvio; o Jordan baixa e joga na pasta do Drive
`Documentos Temporários/<Mês>/`. Este serviço puxa TUDO de lá para dentro do
Conecta PRO:

  1. Lista as subpastas mensais da pasta raiz e baixa cada PDF novo.
  2. Extrai o texto (PyMuPDF) e CLASSIFICA POR CONTEÚDO (nunca só pelo nome).
  3. GUIAS DE PAGAMENTO (GFD FGTS, GFD Consignado, DARF/INSS, DAS, ISS) fazem
     upsert em `fiscal_obligations` com o VALOR REAL, vencimento, nº do
     documento/recibo e metadados (código de barras / PIX copia-e-cola) em
     `observacoes` (JSON) — que alimentam o Painel Fiscal, o CFO e o kit.
  4. RELATÓRIOS/DECLARAÇÕES (DCTFWeb, relatórios GFD) viram evidência: a
     DCTFWeb transmitida (nº de recibo real) marca as acessórias da
     competência como CUMPRIDAS (DCTFWEB/ESOCIAL/EFD_REINF).

Honestidade: nada é fabricado — todo valor gravado vem do PDF oficial; PDFs
não reconhecidos são reportados como "nao_classificado" (nunca chutados).
Idempotência: o file_id do Drive fica em `observacoes`; reprocessar não duplica.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import text as _sql

logger = logging.getLogger(__name__)

# Pasta raiz onde o Jordan despeja o pacote mensal (Documentos Temporários)
GUIAS_DRIVE_ROOT = os.environ.get("FISCAL_GUIAS_DRIVE_FOLDER", "1YmspqFF9wOol9Uz087xtxv0n3TvnqVlf")
GUIAS_STORAGE = os.environ.get("FISCAL_GUIAS_STORAGE", "/app/uploads/fiscal_guias")
# Pasta das guias de PARCELAMENTO (DARF Dívida Ativa PGFN/SISPAR + comprovantes)
PARCELAMENTOS_DRIVE_FOLDER = os.environ.get(
    "FISCAL_PARCELAMENTOS_DRIVE_FOLDER", "1wrgjMheUh0uC_LM9yPGb48iQ_TVmvYn7"
)

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}

_VAL = r"([\d.]+,\d{2})"


def _dec(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _data_br(s: str | None) -> date | None:
    if not s:
        return None
    try:
        d, m, a = s.strip().split("/")
        return date(int(a), int(m), int(d))
    except Exception:  # noqa: BLE001
        return None


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


@dataclass
class GuiaParseada:
    """Resultado do parse de um PDF do pacote."""

    tipo: str  # FGTS | FGTS_CONSIGNADO | INSS | DAS | ISS | DCTFWEB_DECLARACAO | ANEXO | nao_classificado
    competencia_mes: int | None = None
    competencia_ano: int | None = None
    valor: float | None = None
    vencimento: date | None = None
    numero_documento: str | None = None
    numero_recibo: str | None = None
    codigo_barras: str | None = None
    pix_copia_cola: str | None = None
    detalhe: dict[str, Any] = field(default_factory=dict)


def _competencia(texto: str) -> tuple[int | None, int | None]:
    """Extrai competência MM/AAAA (ou 'Junho/2026') do texto."""
    m = re.search(r"PA:?\s*(\d{2})/(\d{4})", texto)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"Per[ií]odo\s+(?:de\s+)?[Aa]pura[cç][aã]o\s*\n?\s*(\d{2})/(\d{4})", texto)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"([A-Za-zçÇ]+)/(\d{4})", texto)
    if m and _sem_acento(m.group(1)).lower() in MESES_PT:
        return MESES_PT[_sem_acento(m.group(1)).lower()], int(m.group(2))
    # bloco "Competência" explícito (GFD lista MM/AAAA algumas linhas abaixo do rótulo)
    m = re.search(r"Compet[êe]ncia[\s\S]{0,120}?(?<![\d/])(\d{2})/(\d{4})", texto)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1)), int(m.group(2))
    # fallback: MM/AAAA solto — lookbehind evita casar dentro de datas dd/mm/aaaa
    m = re.search(r"(?<![\d/])(\d{2})/(\d{4})\b", texto)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(1)), int(m.group(2))
    return None, None


def parse_pdf_guia(caminho: str, nome_arquivo: str) -> GuiaParseada:
    """Classifica e parseia um PDF do pacote mensal PELO CONTEÚDO."""
    import fitz

    doc = fitz.open(caminho)
    texto = "\n".join(p.get_text() for p in doc)
    doc.close()

    nome_up = _sem_acento(nome_arquivo).upper()
    mes, ano = _competencia(texto)

    # ── DARF (INSS e afins) — Documento de Arrecadação de Receitas Federais ──
    if "Documento de Arrecada" in texto and "Receitas Federais" in texto:
        valor = _dec((re.search(r"Valor Total do Documento\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br((re.search(r"Pagar (?:este documento )?at[eé]:?\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1])
        recibo = (re.search(r"Recibo Declara[cç][aã]o:\s*(\d+)", texto) or [None, None])[1]
        num_doc = (re.search(r"(\d{2}\.\d{2}\.\d{5}\.\d{7}-\d)", texto) or [None, None])[1]
        barras = None
        mb = re.search(r"(858\d{8,9}\s*\d\s*\d{11}\s*\d\s*\d{11}\s*\d\s*\d{11}\s*\d)", texto)
        if mb:
            barras = re.sub(r"\s+", "", mb.group(1))
        # composição por código (1082/1138/1646/…)
        comp = {c: _dec(v) for c, v in re.findall(r"\n(\d{4})\s*\n[^\n]+\n" + _VAL, texto)}
        return GuiaParseada(
            tipo="INSS", competencia_mes=mes, competencia_ano=ano, valor=valor,
            vencimento=venc, numero_documento=num_doc, numero_recibo=recibo,
            codigo_barras=barras, detalhe={"composicao": comp},
        )

    # ── GFD — Guia do FGTS Digital (guia de PAGAMENTO) ──
    if "GFD - Guia do FGTS Digital" in texto:
        valor = _dec((re.search(r"Valor a recolher\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br((re.search(r"Pagar este documento at[eé]\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1])
        ident = (re.search(r"Identificador\s*\n?\s*([\d-]{10,})", texto) or [None, None])[1]
        pix = (re.search(r"(000201\S{50,})", texto) or [None, None])[1]
        consignado = "CONSIGNADO" in nome_up or "Total Consignado" in texto
        return GuiaParseada(
            tipo="FGTS_CONSIGNADO" if consignado else "FGTS",
            competencia_mes=mes, competencia_ano=ano, valor=valor, vencimento=venc,
            numero_documento=ident, pix_copia_cola=pix,
        )

    # ── Relatórios GFD (detalhe por trabalhador/tomador) — ANEXO ──
    if "Detalhe da Guia Emitida" in texto:
        num = (re.search(r"N[uú]mero da Guia:\s*\n?\s*([\d-]{10,})", texto) or [None, None])[1]
        total = _dec((re.search(_VAL + r"\s*\nTotal da Guia", texto) or [None, None])[1])
        tomadores = re.findall(r"Tomador:\s*\n?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", texto)
        return GuiaParseada(
            tipo="ANEXO", competencia_mes=mes, competencia_ano=ano, valor=total,
            numero_documento=num,
            detalhe={"relatorio": "GFD", "tomadores": sorted(set(tomadores))},
        )

    # ── DCTFWeb (declaração/resumos) — evidência de transmissão ──
    if "DCTFWeb" in texto and "N" in texto and re.search(r"N[uú]mero do Recibo", texto):
        recibo = (re.search(r"N[uú]mero do Recibo\s*\n?\s*(\d+)", texto) or [None, None])[1]
        transm = (re.search(r"Transmiss[aã]o\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1]
        recibos_aux = dict(re.findall(r"(\d{6,})\s*/\s*(Reinf CP|eSocial)", texto))
        return GuiaParseada(
            tipo="DCTFWEB_DECLARACAO", competencia_mes=mes, competencia_ano=ano,
            numero_recibo=(recibo or "").lstrip("0") or recibo,
            detalhe={"transmissao": transm, "recibos_vinculados": {v: k for k, v in recibos_aux.items()}},
        )

    # ── Parcelamento PGFN — DARF de Dívida Ativa do Simples Nacional (SISPAR) ──
    # Cada PDF é UMA parcela mensal do acordo; agrupamos por SISPAR em fiscal_parcelamentos.
    m_sispar = re.search(r"SISPAR:?\s*(\d+)", texto)
    if m_sispar and "DIVIDA ATIVA" in _sem_acento(texto).upper():
        valor = _dec((re.search(r"Valor Total do Documento\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br((re.search(r"Pagar este documento at[eé]\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1])
        num = (re.search(r"(\d{2}\.\d{2}\.\d{5}\.\d{7}-\d)", texto) or [None, None])[1]
        return GuiaParseada(
            tipo="PARCELAMENTO_PGFN", competencia_mes=mes, competencia_ano=ano, valor=valor,
            vencimento=venc, numero_documento=num, detalhe={"sispar": m_sispar.group(1)},
        )

    # ── DAS (Simples) / ISS Manaus — padrões p/ quando aparecerem no pacote ──
    if re.search(r"\bDAS\b", texto) and "Simples Nacional" in texto:
        valor = _dec((re.search(r"Valor Total(?: do Documento)?\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br((re.search(r"(?:Pagar|Vencimento).{0,20}?(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1])
        return GuiaParseada(tipo="DAS", competencia_mes=mes, competencia_ano=ano, valor=valor, vencimento=venc)
    if "ISSQN" in texto or ("ISS" in texto and "Manaus" in texto):
        valor = _dec((re.search(r"Valor(?: Total| do Documento)?\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br((re.search(r"Vencimento\s*:?\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1])
        return GuiaParseada(tipo="ISS", competencia_mes=mes, competencia_ano=ano, valor=valor, vencimento=venc)

    return GuiaParseada(tipo="nao_classificado", competencia_mes=mes, competencia_ano=ano)


# ─────────────────────────────────────────────────────────────────────────────
# Sincronização (síncrona — chamar via run_in_threadpool no controller)
# ─────────────────────────────────────────────────────────────────────────────

NOMES = {
    "FGTS": "FGTS/GFIP",
    "FGTS_CONSIGNADO": "FGTS Consignado",
    "INSS": "INSS Patronal",
    "DAS": "DAS Simples Nacional",
    "ISS": "ISS Manaus",
}


def _db_sync():
    from core.database.session import SyncSessionLocal

    return SyncSessionLocal()


def _upsert_obrigacao(db, g: GuiaParseada, meta: dict[str, Any]) -> str:
    """Upsert em fiscal_obligations com o dado REAL da guia. Retorna a ação."""
    if not (g.competencia_mes and g.competencia_ano):
        return "sem_competencia"

    row = db.execute(
        _sql(
            "SELECT id, valor_devido, observacoes FROM fiscal_obligations "
            "WHERE tipo=:t AND competencia_mes=:m AND competencia_ano=:a AND active=true LIMIT 1"
        ),
        {"t": g.tipo, "m": g.competencia_mes, "a": g.competencia_ano},
    ).first()

    obs = {
        "fonte": "drive_portte",
        "drive_file_id": meta.get("file_id"),
        "arquivo": meta.get("nome"),
        "numero_documento": g.numero_documento,
        "codigo_barras": g.codigo_barras,
        "pix_copia_cola": g.pix_copia_cola,
        "sync_em": datetime.utcnow().isoformat(),
        **({"detalhe": g.detalhe} if g.detalhe else {}),
    }
    obs_json = json.dumps({k: v for k, v in obs.items() if v}, ensure_ascii=False)

    if row:
        antigo = float(row[1]) if row[1] is not None else None
        divergencia = antigo is not None and g.valor is not None and abs(antigo - g.valor) > 0.01
        db.execute(
            _sql(
                "UPDATE fiscal_obligations SET "
                "valor_devido = COALESCE(:v, valor_devido), "
                "data_vencimento = COALESCE(:venc, data_vencimento), "
                "numero_recibo = COALESCE(:rec, numero_recibo), "
                "observacoes = :obs, updated_at = NOW() WHERE id = :id"
            ),
            {
                "v": g.valor, "venc": g.vencimento, "rec": g.numero_recibo or g.numero_documento,
                "obs": (obs_json + (f" | DIVERGENCIA: valor anterior {antigo}" if divergencia else "")),
                "id": row[0],
            },
        )
        return "atualizada_divergente" if divergencia else "atualizada"

    db.execute(
        _sql(
            "INSERT INTO fiscal_obligations (id, condominio_id, tipo, nome, descricao, status, "
            "competencia_mes, competencia_ano, data_vencimento, valor_devido, numero_recibo, "
            "observacoes, created_at, updated_at, active) "
            "SELECT gen_random_uuid(), condominio_id, :t, :n, :d, 'pendente', :m, :a, :venc, :v, :rec, :obs, NOW(), NOW(), true "
            "FROM fiscal_obligations LIMIT 1"
        ),
        {
            "t": g.tipo, "n": NOMES.get(g.tipo, g.tipo),
            "d": f"Guia oficial (Portte/Onvio) — {meta.get('nome')}",
            "m": g.competencia_mes, "a": g.competencia_ano,
            "venc": g.vencimento, "v": g.valor,
            "rec": g.numero_recibo or g.numero_documento, "obs": obs_json,
        },
    )
    return "criada"


def _upsert_parcelamento(db, g: GuiaParseada, meta: dict[str, Any]) -> str:
    """Upsert em fiscal_parcelamentos agrupando por SISPAR. Cada DARF é uma parcela;
    rastreamos as competências conhecidas (crescem mês a mês). O TOTAL do acordo não
    consta no DARF → num_parcelas/valor_total refletem o CONHECIDO (honesto)."""
    sispar = (g.detalhe or {}).get("sispar")
    if not (sispar and g.valor):
        return "sem_sispar"
    numero_acordo = f"SISPAR {sispar}"
    comp = f"{g.competencia_mes:02d}/{g.competencia_ano}" if g.competencia_mes and g.competencia_ano else None

    row = db.execute(
        _sql("SELECT id, observacao, parcelas_pagas FROM fiscal_parcelamentos WHERE numero_acordo=:n LIMIT 1"),
        {"n": numero_acordo},
    ).first()

    # competências conhecidas ficam num JSON dentro de observacao (idempotente por competência)
    conhecidas: set[str] = set()
    pagas = 0
    if row:
        pagas = row[2] or 0
        try:
            meta_obs = json.loads(row[1]) if row[1] and row[1].strip().startswith("{") else {}
            conhecidas = set(meta_obs.get("competencias_conhecidas", []))
        except Exception:  # noqa: BLE001
            conhecidas = set()
    if comp:
        conhecidas.add(comp)
    n = len(conhecidas) or 1
    valor_total = round(g.valor * n, 2)
    obs = json.dumps({
        "nota": "Parcelamento Dívida Ativa Simples Nacional (PGFN). num_parcelas/valor_total = "
                "parcelas CONHECIDAS pelo puxador; total do acordo a confirmar no e-CAC/SISPAR.",
        "sispar": sispar,
        "parcela_valor": g.valor,
        "competencias_conhecidas": sorted(conhecidas),
        "ultimo_arquivo": meta.get("nome"),
        "sync_em": datetime.utcnow().isoformat(),
    }, ensure_ascii=False)

    if row:
        db.execute(
            _sql("UPDATE fiscal_parcelamentos SET parcela_valor=:pv, num_parcelas=:np, valor_total=:vt, "
                 "dia_vencimento=COALESCE(:dv, dia_vencimento), status='ativo', observacao=:obs, "
                 "fonte='drive_pgfn', updated_at=now() WHERE id=:id"),
            {"pv": g.valor, "np": n, "vt": valor_total,
             "dv": g.vencimento.day if g.vencimento else None, "obs": obs, "id": row[0]},
        )
        return "atualizado"
    db.execute(
        _sql("INSERT INTO fiscal_parcelamentos (orgao,numero_acordo,descricao,valor_total,num_parcelas,"
             "parcela_valor,dia_vencimento,competencia_inicio,parcelas_pagas,status,observacao,fonte,created_by,created_at,updated_at) "
             "VALUES ('PGFN',:na,:desc,:vt,:np,:pv,:dv,:ci,0,'ativo',:obs,'drive_pgfn','drive_puxador',now(),now())"),
        {"na": numero_acordo, "desc": "Parcelamento Dívida Ativa — Simples Nacional (PGFN) — total do acordo a confirmar",
         "vt": valor_total, "np": n, "pv": g.valor,
         "dv": g.vencimento.day if g.vencimento else None, "ci": comp, "obs": obs},
    )
    return "criado"


def _marcar_acessorias_cumpridas(db, g: GuiaParseada, meta: dict[str, Any]) -> list[str]:
    """DCTFWeb transmitida (recibo real) = acessórias da competência CUMPRIDAS."""
    if not (g.competencia_mes and g.competencia_ano and g.numero_recibo):
        return []
    marcadas = []
    for tipo in ("DCTFWEB", "ESOCIAL", "EFD_REINF"):
        r = db.execute(
            _sql(
                "UPDATE fiscal_obligations SET status='cumprida', numero_recibo=COALESCE(numero_recibo, :rec), "
                "observacoes = COALESCE(observacoes || ' | ', '') || :nota, updated_at=NOW() "
                "WHERE tipo=:t AND competencia_mes=:m AND competencia_ano=:a AND active=true "
                "AND status != 'cumprida'"
            ),
            {
                "rec": g.numero_recibo, "t": tipo, "m": g.competencia_mes, "a": g.competencia_ano,
                "nota": f"Transmitida (DCTFWeb recibo {g.numero_recibo} em {g.detalhe.get('transmissao')}; fonte drive {meta.get('nome')})",
            },
        )
        if r.rowcount:
            marcadas.append(tipo)
    return marcadas


def _ja_processado(db, file_id: str) -> bool:
    return bool(
        db.execute(
            _sql("SELECT 1 FROM fiscal_obligations WHERE observacoes LIKE :p LIMIT 1"),
            {"p": f'%"drive_file_id": "{file_id}"%'},
        ).first()
    )


def sync_guias_drive(forcar: bool = False) -> dict[str, Any]:
    """Varre a pasta raiz do Drive e sincroniza todas as guias. Retorna relatório."""
    from modules.gdrive.services.gdrive_service import GDriveService

    svc = GDriveService()
    if not svc.esta_conectado():
        return {"ok": False, "erro": "Google Drive não conectado (gdrive_config)"}

    rel: dict[str, Any] = {
        "ok": True, "pastas": [], "baixados": 0, "guias": [], "anexos": [],
        "acessorias_cumpridas": [], "nao_classificados": [], "ja_processados": 0,
        "parcelamentos": [],
    }
    db = _db_sync()
    try:
        raiz = svc.listar_arquivos(GUIAS_DRIVE_ROOT)
        pastas = [f for f in raiz if f.get("mimeType") == "application/vnd.google-apps.folder"]
        # PDFs soltos na raiz também contam
        alvos: list[tuple[str, dict]] = [("raiz", f) for f in raiz if f.get("mimeType") == "application/pdf"]
        for p in pastas:
            rel["pastas"].append(p["name"])
            alvos += [(p["name"], f) for f in svc.listar_arquivos(p["id"]) if f.get("mimeType") == "application/pdf"]
        # pasta dedicada de PARCELAMENTOS (DARF Dívida Ativa PGFN)
        if PARCELAMENTOS_DRIVE_FOLDER:
            alvos += [("parcelamentos", f) for f in svc.listar_arquivos(PARCELAMENTOS_DRIVE_FOLDER)
                      if f.get("mimeType") == "application/pdf"]

        _vistos: set[str] = set()
        for pasta, f in alvos:
            fid, nome = f["id"], f["name"]
            if fid in _vistos:   # dedupe: mesmo arquivo listado em 2 pastas
                continue
            _vistos.add(fid)
            if not forcar and _ja_processado(db, fid):
                rel["ja_processados"] += 1
                continue
            dest = os.path.join(GUIAS_STORAGE, pasta, f"{fid}__{nome}")
            if not os.path.exists(dest) and not svc.baixar_arquivo(fid, dest):
                rel.setdefault("erros_download", []).append(nome)
                continue
            rel["baixados"] += 1
            try:
                g = parse_pdf_guia(dest, nome)
            except Exception as exc:  # noqa: BLE001
                rel.setdefault("erros_parse", []).append(f"{nome}: {exc}")
                continue
            meta = {"file_id": fid, "nome": nome, "pasta": pasta}
            if g.tipo == "PARCELAMENTO_PGFN":
                acao = _upsert_parcelamento(db, g, meta)
                rel["parcelamentos"].append({
                    "arquivo": nome, "sispar": (g.detalhe or {}).get("sispar"),
                    "competencia": f"{g.competencia_mes:02d}/{g.competencia_ano}" if g.competencia_mes else None,
                    "parcela": g.valor, "acao": acao,
                })
            elif g.tipo in NOMES:
                acao = _upsert_obrigacao(db, g, meta)
                rel["guias"].append({
                    "arquivo": nome, "tipo": g.tipo, "competencia": f"{g.competencia_mes:02d}/{g.competencia_ano}" if g.competencia_mes else None,
                    "valor": g.valor, "vencimento": g.vencimento.isoformat() if g.vencimento else None, "acao": acao,
                })
            elif g.tipo == "DCTFWEB_DECLARACAO":
                marcadas = _marcar_acessorias_cumpridas(db, g, meta)
                rel["acessorias_cumpridas"].append({"arquivo": nome, "recibo": g.numero_recibo, "marcadas": marcadas})
            elif g.tipo == "ANEXO":
                rel["anexos"].append({"arquivo": nome, "relatorio": g.detalhe.get("relatorio"), "tomadores": g.detalhe.get("tomadores")})
            else:
                rel["nao_classificados"].append(nome)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("sync_guias_drive falhou")
        return {"ok": False, "erro": str(exc)}
    finally:
        db.close()
    return rel
