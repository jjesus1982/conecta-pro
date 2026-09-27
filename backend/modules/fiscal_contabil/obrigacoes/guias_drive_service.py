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
PARCELAMENTOS_DRIVE_FOLDER = os.environ.get("FISCAL_PARCELAMENTOS_DRIVE_FOLDER", "1wrgjMheUh0uC_LM9yPGb48iQ_TVmvYn7")

MESES_PT = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_VAL = r"([\d.]+,\d{2})"

# ── Roteamento multi-CNPJ: cada guia vai para o empresa_id do CNPJ no texto do PDF ──
EMPRESAS_POR_CNPJ = {
    "35710481000103": "619a3df1-8bce-49ce-b77a-04f80a0e8491",  # Eletrônica (Lucro Real)
    "66014833000110": "7d79ed12-d480-4906-b2e0-2b2c4d299bab",  # Patrimonial (Simples)
}
EMPRESA_PRINCIPAL = "619a3df1-8bce-49ce-b77a-04f80a0e8491"  # Eletrônica (fallback histórico)


def _empresa_por_cnpj(texto: str, nome_arquivo: str = "") -> str:
    """Resolve o empresa_id pelo CNPJ presente no texto da guia; sem CNPJ, pelo NOME do arquivo.

    A GFD do FGTS Digital não traz CNPJ no texto (só o código de barras) — medido em
    27/09/2026: «GFD FGTS 08.2026_Conecta Patrimonial.pdf», R$ 7.981,94, caía no default e
    virava obrigação da ELETRÔNICA. O nome que a Portte dá ao arquivo diz a empresa; é a
    segunda fonte, e só entra quando a primeira (o CNPJ) não existe. Default: Eletrônica.
    """
    for m in re.finditer(r"(\d{2})\.?(\d{3})\.?(\d{3})/?(\d{4})-?(\d{2})", texto or ""):
        digs = "".join(m.groups())
        if digs in EMPRESAS_POR_CNPJ:
            return EMPRESAS_POR_CNPJ[digs]
    if "patrimonial" in _sem_acento(nome_arquivo or "").lower():
        return EMPRESAS_POR_CNPJ["66014833000110"]
    return EMPRESA_PRINCIPAL


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
    empresa_id: str | None = None
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
    _emp = _empresa_por_cnpj(texto, nome_arquivo)

    # ── DARF (INSS e afins) — Documento de Arrecadação de Receitas Federais ──
    if "Documento de Arrecada" in texto and "Receitas Federais" in texto:
        valor = _dec((re.search(r"Valor Total do Documento\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br(
            (re.search(r"Pagar (?:este documento )?at[eé]:?\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1]
        )
        recibo = (re.search(r"Recibo Declara[cç][aã]o:\s*(\d+)", texto) or [None, None])[1]
        num_doc = (re.search(r"(\d{2}\.\d{2}\.\d{5}\.\d{7}-\d)", texto) or [None, None])[1]
        barras = None
        mb = re.search(r"(858\d{8,9}\s*\d\s*\d{11}\s*\d\s*\d{11}\s*\d\s*\d{11}\s*\d)", texto)
        if mb:
            barras = re.sub(r"\s+", "", mb.group(1))
        # composição por código (1082/1138/1646/…)
        comp = {c: _dec(v) for c, v in re.findall(r"\n(\d{4})\s*\n[^\n]+\n" + _VAL, texto)}
        return GuiaParseada(
            empresa_id=_emp,
            tipo="INSS",
            competencia_mes=mes,
            competencia_ano=ano,
            valor=valor,
            vencimento=venc,
            numero_documento=num_doc,
            numero_recibo=recibo,
            codigo_barras=barras,
            detalhe={"composicao": comp},
        )

    # ── GFD — Guia do FGTS Digital (guia de PAGAMENTO) ──
    if "GFD - Guia do FGTS Digital" in texto:
        valor = _dec((re.search(r"Valor a recolher\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br(
            (re.search(r"Pagar este documento at[eé]\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1]
        )
        ident = (re.search(r"Identificador\s*\n?\s*([\d-]{10,})", texto) or [None, None])[1]
        pix = (re.search(r"(000201\S{50,})", texto) or [None, None])[1]
        consignado = "CONSIGNADO" in nome_up or "Total Consignado" in texto
        # GFD RESCISÓRIA é uma guia por desligamento, não a mensal: no 1º disparo real do
        # beat (27/09) as de Daniel (R$ 97,29) e Keyson (R$ 1.078,01) entraram como «FGTS»
        # 08/2026 e SOBRESCREVERAM a GFD mensal da Eletrônica (R$ 133,60), porque a chave do
        # upsert é (tipo, competência, empresa). Tipo próprio, e chave com o nº do documento.
        # SÓ pelo nome do arquivo: o texto da GFD MENSAL também traz «Rescis» (linha de
        # composição zerada) e a 1ª regra classificou TODAS as GFD como rescisórias — medido
        # 27/09, quatro linhas espúrias criadas e apagadas. A Portte nomeia as rescisórias
        # «GFD FGTS RESCISÃO - <nome>.pdf»; é esse o sinal.
        rescisorio = "RESCIS" in nome_up
        return GuiaParseada(
            empresa_id=_emp,
            tipo="FGTS_RESCISORIO" if rescisorio else ("FGTS_CONSIGNADO" if consignado else "FGTS"),
            competencia_mes=mes,
            competencia_ano=ano,
            valor=valor,
            vencimento=venc,
            numero_documento=ident,
            pix_copia_cola=pix,
        )

    # ── Relatórios GFD (detalhe por trabalhador/tomador) — ANEXO ──
    if "Detalhe da Guia Emitida" in texto:
        num = (re.search(r"N[uú]mero da Guia:\s*\n?\s*([\d-]{10,})", texto) or [None, None])[1]
        total = _dec((re.search(_VAL + r"\s*\nTotal da Guia", texto) or [None, None])[1])
        tomadores = re.findall(r"Tomador:\s*\n?\s*(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", texto)
        return GuiaParseada(
            empresa_id=_emp,
            tipo="ANEXO",
            competencia_mes=mes,
            competencia_ano=ano,
            valor=total,
            numero_documento=num,
            detalhe={"relatorio": "GFD", "tomadores": sorted(set(tomadores))},
        )

    # ── DCTFWeb (declaração/resumos) — evidência de transmissão ──
    if "DCTFWeb" in texto and "N" in texto and re.search(r"N[uú]mero do Recibo", texto):
        recibo = (re.search(r"N[uú]mero do Recibo\s*\n?\s*(\d+)", texto) or [None, None])[1]
        transm = (re.search(r"Transmiss[aã]o\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1]
        recibos_aux = dict(re.findall(r"(\d{6,})\s*/\s*(Reinf CP|eSocial)", texto))
        return GuiaParseada(
            empresa_id=_emp,
            tipo="DCTFWEB_DECLARACAO",
            competencia_mes=mes,
            competencia_ano=ano,
            numero_recibo=(recibo or "").lstrip("0") or recibo,
            detalhe={"transmissao": transm, "recibos_vinculados": {v: k for k, v in recibos_aux.items()}},
        )

    # ── Parcelamento PGFN — DARF de Dívida Ativa do Simples Nacional (SISPAR) ──
    # Cada PDF é UMA parcela mensal do acordo; agrupamos por SISPAR em fiscal_parcelamentos.
    m_sispar = re.search(r"SISPAR:?\s*(\d+)", texto)
    if m_sispar and "DIVIDA ATIVA" in _sem_acento(texto).upper():
        valor = _dec((re.search(r"Valor Total do Documento\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br(
            (re.search(r"Pagar este documento at[eé]\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1]
        )
        num = (re.search(r"(\d{2}\.\d{2}\.\d{5}\.\d{7}-\d)", texto) or [None, None])[1]
        return GuiaParseada(
            empresa_id=_emp,
            tipo="PARCELAMENTO_PGFN",
            competencia_mes=mes,
            competencia_ano=ano,
            valor=valor,
            vencimento=venc,
            numero_documento=num,
            detalhe={"sispar": m_sispar.group(1)},
        )

    # ── DAS (Simples) / ISS Manaus — padrões p/ quando aparecerem no pacote ──
    # O DAS que a Portte deixa no Onvio começa por «Documento de Arrecadação do Simples
    # Nacional» e NUNCA traz a sigla «DAS» no texto — só a exigência de \bDAS\b o deixava em
    # nao_classificado (medido em 27/09/2026: valor 18.399,33 e vencimento 21/09 legíveis, e
    # a obrigação seguia «sem guia» no gate). O número do documento também entra.
    if ("Simples Nacional" in texto) and (
        re.search(r"\bDAS\b", texto) or re.search(r"Documento de Arrecada[çc][ãa]o do Simples Nacional", texto)
    ):
        valor = _dec((re.search(r"Valor Total(?: do Documento)?\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        # «Pagar este documento até 21/09/2026»: 25 caracteres entre a âncora e a data — o
        # .{0,20} antigo deixava o DAS sem vencimento (medido 27/09).
        # [\s\S] porque no texto do PDF a data vem na linha seguinte («…até\n21/09/2026») e
        # «.» não cruza \n — o ramo do DARF já sabia disso (\s*\n?\s*); este não.
        venc = _data_br((re.search(r"(?:Pagar|Vencimento)[\s\S]{0,40}?(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1])
        num = (re.search(r"(\d{2}\.\d{2}\.\d{5}\.\d{7}-\d)", texto) or [None, None])[1]
        return GuiaParseada(
            empresa_id=_emp,
            tipo="DAS",
            competencia_mes=mes,
            competencia_ano=ano,
            valor=valor,
            vencimento=venc,
            numero_documento=num,
        )
    if "ISSQN" in texto or ("ISS" in texto and "Manaus" in texto):
        valor = _dec((re.search(r"Valor(?: Total| do Documento)?\s*\n?\s*" + _VAL, texto) or [None, None])[1])
        venc = _data_br((re.search(r"Vencimento\s*:?\s*\n?\s*(\d{2}/\d{2}/\d{4})", texto) or [None, None])[1])
        return GuiaParseada(
            empresa_id=_emp, tipo="ISS", competencia_mes=mes, competencia_ano=ano, valor=valor, vencimento=venc
        )

    return GuiaParseada(empresa_id=_emp, tipo="nao_classificado", competencia_mes=mes, competencia_ano=ano)


# ─────────────────────────────────────────────────────────────────────────────
# Sincronização (síncrona — chamar via run_in_threadpool no controller)
# ─────────────────────────────────────────────────────────────────────────────

NOMES = {
    "FGTS": "FGTS/GFIP",
    "FGTS_CONSIGNADO": "FGTS Consignado",
    "FGTS_RESCISORIO": "FGTS Rescisório (GFD por desligamento)",
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

    emp = g.empresa_id or EMPRESA_PRINCIPAL
    # Rescisória: uma por desligamento — a chave leva o nº do documento, senão duas rescisões
    # no mesmo mês (ou a rescisória e a mensal) colidem e a última apaga a anterior.
    extra = " AND observacoes LIKE :nd" if (g.tipo == "FGTS_RESCISORIO" and g.numero_documento) else ""
    row = db.execute(
        _sql(
            "SELECT id, valor_devido, observacoes FROM fiscal_obligations "
            "WHERE tipo=:t AND competencia_mes=:m AND competencia_ano=:a AND empresa_id=:emp AND active=true"
            + extra
            + " LIMIT 1"
        ),
        {
            "t": g.tipo,
            "m": g.competencia_mes,
            "a": g.competencia_ano,
            "emp": emp,
            **({"nd": f'%"numero_documento": "{g.numero_documento}"%'} if extra else {}),
        },
    ).first()

    obs = {
        "fonte": meta.get("fonte", "drive_portte"),
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
                "v": g.valor,
                "venc": g.vencimento,
                "rec": g.numero_recibo or g.numero_documento,
                "obs": (obs_json + (f" | DIVERGENCIA: valor anterior {antigo}" if divergencia else "")),
                "id": row[0],
            },
        )
        return "atualizada_divergente" if divergencia else "atualizada"

    db.execute(
        _sql(
            "INSERT INTO fiscal_obligations (id, condominio_id, empresa_id, tipo, nome, descricao, status, "
            "competencia_mes, competencia_ano, data_vencimento, valor_devido, numero_recibo, "
            "observacoes, created_at, updated_at, active) "
            "SELECT gen_random_uuid(), condominio_id, :emp, :t, :n, :d, 'pendente', :m, :a, :venc, :v, :rec, :obs, NOW(), NOW(), true "
            "FROM fiscal_obligations LIMIT 1"
        ),
        {
            "emp": emp,
            "t": g.tipo,
            "n": NOMES.get(g.tipo, g.tipo),
            "d": f"Guia oficial (Portte/Onvio) — {meta.get('nome')}",
            "m": g.competencia_mes,
            "a": g.competencia_ano,
            "venc": g.vencimento,
            "v": g.valor,
            "rec": g.numero_recibo or g.numero_documento,
            "obs": obs_json,
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
        _sql(
            "SELECT id, observacao, parcelas_pagas, parcela_valor "
            "  FROM fiscal_parcelamentos WHERE numero_acordo=:n LIMIT 1"
        ),
        {"n": numero_acordo},
    ).first()

    # competências conhecidas ficam num JSON dentro de observacao (idempotente por competência)
    conhecidas: set[str] = set()
    _pagas = 0
    if row:
        _pagas = row[2] or 0
        try:
            meta_obs = json.loads(row[1]) if row[1] and row[1].strip().startswith("{") else {}
            conhecidas = set(meta_obs.get("competencias_conhecidas", []))
        except Exception:  # noqa: BLE001
            conhecidas = set()
    if comp:
        conhecidas.add(comp)
    n = len(conhecidas) or 1
    valor_total = round(g.valor * n, 2)

    # `parcela_valor` e `dia_vencimento` descrevem a parcela CORRENTE, então só a competência
    # mais nova pode escrevê-los. Medido em 18/08/2026: o acervo é varrido por nome de
    # arquivo, e `PARC 9_145 … 06 2026` vem DEPOIS de `PARC 10_145 … 07 2026` na ordem
    # alfabética — o acordo terminava exibindo a parcela de junho (257,95) no lugar da de
    # julho (260,60). Cada parcela tem juros próprios; sobrescrever com a mais velha faz o
    # painel cobrar um valor que não é mais o devido.
    def _ordem(c: str) -> tuple[int, int]:
        mes, ano = c.split("/")
        return int(ano), int(mes)

    e_a_mais_nova = not comp or comp == max(conhecidas, key=_ordem)
    valor_corrente = g.valor if e_a_mais_nova else float(row[3] or g.valor)
    dia_corrente = g.vencimento.day if (e_a_mais_nova and g.vencimento) else None
    obs = json.dumps(
        {
            "nota": "Parcelamento Dívida Ativa Simples Nacional (PGFN). num_parcelas/valor_total = "
            "parcelas CONHECIDAS pelo puxador; total do acordo a confirmar no e-CAC/SISPAR.",
            "sispar": sispar,
            "parcela_valor": valor_corrente,
            "competencia_corrente": max(conhecidas, key=_ordem) if conhecidas else None,
            "competencias_conhecidas": sorted(conhecidas, key=_ordem),
            "ultimo_arquivo": meta.get("nome"),
            "sync_em": datetime.utcnow().isoformat(),
        },
        ensure_ascii=False,
    )

    if row:
        db.execute(
            _sql(
                "UPDATE fiscal_parcelamentos SET parcela_valor=:pv, num_parcelas=:np, valor_total=:vt, "
                "dia_vencimento=COALESCE(:dv, dia_vencimento), status='ativo', observacao=:obs, "
                "fonte=:fonte, updated_at=now() WHERE id=:id"
            ),
            {
                "pv": valor_corrente,
                "np": n,
                "vt": valor_total,
                "dv": dia_corrente,
                "fonte": meta.get("fonte", "drive_pgfn"),
                "obs": obs,
                "id": row[0],
            },
        )
        return "atualizado"
    db.execute(
        _sql(
            "INSERT INTO fiscal_parcelamentos (orgao,numero_acordo,descricao,valor_total,num_parcelas,"
            "parcela_valor,dia_vencimento,competencia_inicio,parcelas_pagas,status,observacao,fonte,created_by,created_at,updated_at) "
            "VALUES ('PGFN',:na,:desc,:vt,:np,:pv,:dv,:ci,0,'ativo',:obs,:fonte,'drive_puxador',now(),now())"
        ),
        {
            "na": numero_acordo,
            "desc": "Parcelamento Dívida Ativa — Simples Nacional (PGFN) — total do acordo a confirmar",
            "vt": valor_total,
            "np": n,
            "pv": g.valor,
            "fonte": meta.get("fonte", "drive_pgfn"),
            "dv": g.vencimento.day if g.vencimento else None,
            "ci": comp,
            "obs": obs,
        },
    )
    return "criado"


def marcar_acessorias(db, empresa_id: str, mes: int, ano: int, recibo: str, origem: str) -> list[str]:
    """DCTFWeb transmitida (recibo real) = acessórias da competência CUMPRIDAS.

    Núcleo em primitivos, e não em `GuiaParseada`, porque o recibo chega por DOIS caminhos e
    só um deles dava baixa. O do Drive chamava isto; o do **Onvio** — que é por onde os
    documentos realmente chegam — extraía `numero_recibo` e `data_transmissao` para
    `onvio_documents.detalhes_json` e parava ali. Resultado medido em 15/08/2026: a DCTFWeb
    de 07/2026 estava transmitida desde 11/08, com recibo `0000050000514331309` e **saldo a
    pagar R$ 0,00**, e as três acessórias apareciam `pendente` vencendo naquele dia.

    Prazo que já foi cumprido e continua aceso no painel é a mesma doença dos R$68 mil de
    abril a julho: assusta, não informa, e ensina a ignorar o painel.
    """
    if not (mes and ano and recibo):
        return []
    emp = empresa_id or EMPRESA_PRINCIPAL
    marcadas = []
    for tipo in ("DCTFWEB", "ESOCIAL", "EFD_REINF"):
        r = db.execute(
            _sql(
                "UPDATE fiscal_obligations SET status='cumprida', numero_recibo=COALESCE(numero_recibo, :rec), "
                "observacoes = COALESCE(observacoes || ' | ', '') || :nota, updated_at=NOW() "
                "WHERE tipo=:t AND competencia_mes=:m AND competencia_ano=:a AND empresa_id=:emp AND active=true "
                "AND status != 'cumprida'"
            ),
            {
                "rec": recibo,
                "t": tipo,
                "m": mes,
                "a": ano,
                "emp": emp,
                "nota": f"Transmitida (DCTFWeb recibo {recibo}; {origem})",
            },
        )
        if r.rowcount:
            marcadas.append(tipo)
    return marcadas


def _marcar_acessorias_cumpridas(db, g: GuiaParseada, meta: dict[str, Any]) -> list[str]:
    """Caminho do DRIVE — mantém a assinatura antiga e delega ao núcleo."""
    return marcar_acessorias(
        db,
        g.empresa_id or EMPRESA_PRINCIPAL,
        g.competencia_mes,
        g.competencia_ano,
        g.numero_recibo,
        f"em {g.detalhe.get('transmissao')}; fonte drive {meta.get('nome')}",
    )


# Donos do fiscal que recebem o sino (Jordan + Pyetra) — ver [[project_financeiro_auditoria_organizacao]]
FISCAL_OWNERS_EMAILS = ("jjesus@conectamais.pro", "pjesus@conectamais.pro")


def _emitir_notificacao_fiscal(db, titulo: str, corpo: str, action_url: str = "/modulos/fiscal/ecac") -> int:
    """Emite notificação no sino p/ os donos do fiscal. O sino filtra por
    tenant_id=getattr(user,'tenant_id',str(user.id))=id → gravamos tenant_id=user_id=id."""
    import uuid as _uuid

    try:
        rows = db.execute(
            _sql(
                "SELECT id FROM users WHERE email IN ('jjesus@conectamais.pro','pjesus@conectamais.pro') AND is_active"
            )
        ).fetchall()
        for (uid,) in rows:
            db.execute(
                _sql(
                    "INSERT INTO communication_notifications (id,tenant_id,user_id,title,body,type,"
                    "reference_type,channels,is_active,created_at,action_url) "
                    "VALUES (:id,:t,:u,:ti,:b,'alerta','fiscal_guia','[\"in_app\"]',true,now(),:url)"
                ),
                {
                    "id": str(_uuid.uuid4()),
                    "t": str(uid),
                    "u": str(uid),
                    "ti": titulo[:200],
                    "b": corpo[:500],
                    "url": action_url,
                },
            )
        return len(rows)
    except Exception as e:  # noqa: BLE001
        logger.warning("emitir_notificacao_fiscal: %s", e)
        return 0


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
        "ok": True,
        "pastas": [],
        "baixados": 0,
        "guias": [],
        "anexos": [],
        "acessorias_cumpridas": [],
        "nao_classificados": [],
        "ja_processados": 0,
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
            alvos += [
                ("parcelamentos", f)
                for f in svc.listar_arquivos(PARCELAMENTOS_DRIVE_FOLDER)
                if f.get("mimeType") == "application/pdf"
            ]

        _vistos: set[str] = set()
        for pasta, f in alvos:
            fid, nome = f["id"], f["name"]
            if fid in _vistos:  # dedupe: mesmo arquivo listado em 2 pastas
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
                rel["parcelamentos"].append(
                    {
                        "arquivo": nome,
                        "sispar": (g.detalhe or {}).get("sispar"),
                        "competencia": f"{g.competencia_mes:02d}/{g.competencia_ano}" if g.competencia_mes else None,
                        "parcela": g.valor,
                        "acao": acao,
                    }
                )
            elif g.tipo in NOMES:
                acao = _upsert_obrigacao(db, g, meta)
                rel["guias"].append(
                    {
                        "arquivo": nome,
                        "tipo": g.tipo,
                        "competencia": f"{g.competencia_mes:02d}/{g.competencia_ano}" if g.competencia_mes else None,
                        "valor": g.valor,
                        "vencimento": g.vencimento.isoformat() if g.vencimento else None,
                        "acao": acao,
                    }
                )
            elif g.tipo == "DCTFWEB_DECLARACAO":
                marcadas = _marcar_acessorias_cumpridas(db, g, meta)
                rel["acessorias_cumpridas"].append({"arquivo": nome, "recibo": g.numero_recibo, "marcadas": marcadas})
            elif g.tipo == "ANEXO":
                rel["anexos"].append(
                    {"arquivo": nome, "relatorio": g.detalhe.get("relatorio"), "tomadores": g.detalhe.get("tomadores")}
                )
            else:
                rel["nao_classificados"].append(nome)
        # SINO: notifica os donos do fiscal se veio guia/parcelamento NOVO ou divergente
        novas_guias = [g for g in rel["guias"] if g.get("acao") in ("criada", "atualizada_divergente")]
        novos_parc = [p for p in rel["parcelamentos"] if p.get("acao") == "criado"]
        if novas_guias or novos_parc:
            partes = []
            if novas_guias:
                partes.append(f"{len(novas_guias)} guia(s)")
            if novos_parc:
                partes.append(f"{len(novos_parc)} parcelamento(s)")
            rel["notificados"] = _emitir_notificacao_fiscal(
                db,
                "Puxador fiscal: novidades da Receita",
                "O puxador trouxe " + " e ".join(partes) + " do Drive (Portte/Onvio). Confira no e-CAC.",
            )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("sync_guias_drive falhou")
        return {"ok": False, "erro": str(exc)}
    finally:
        db.close()
    return rel


def sync_guias_onvio(mes_ref: str | None = None, forcar: bool = False, dias: int = 45) -> dict[str, Any]:
    """Aplica o MESMO parser/upsert do Drive aos PDFs que o Onvio já baixou.

    O Onvio é da Portte; quando a Portte sair, ele sai. Enquanto existe, os PDFs mensais
    (DAS, GFD do FGTS, DCTFWeb) já estão em `onvio_documents.caminho_local` — e até
    27/09/2026 ninguém os transformava em obrigação: o gate fiscal dizia «5 vencidas sem
    guia» com o DAS de R$ 18.399,33 parado no disco. Cada PDF vira `fiscal_obligations`
    com valor, vencimento e código de barras (procedência `onvio_portte`), idempotente pelo
    id do documento. O caminho permanente — puxar do governo por certificado — não existe
    hoje (os managers são casca) e é decisão do dono.

    Três paredes, todas medidas no primeiro disparo real pelo beat (27/09, 18:42):
    - **escopo**: sem `mes_ref`, só documentos dos últimos `dias` dias. A 1ª versão varreu
      os 73 históricos e um «PGDASD DECLARACAO 11/2025» virou DAS de 01/2024.
    - **guia sem vencimento ou sem valor não é guia** (é declaração/extrato): não grava,
      reporta em `sem_dado`. Era o NOT NULL de `data_vencimento` estourando.
    - **um documento ruim não derruba o lote**: commit por documento; o erro fica no
      relatório com o nome do arquivo. Antes, o rollback do lote apagava até as boas.
    """
    from sqlalchemy import text as _t  # noqa: PLC0415

    rel: dict[str, Any] = {
        "ok": True,
        "mes_ref": mes_ref,
        "dias": None if mes_ref else dias,
        "lidos": 0,
        "guias": [],
        "acessorias": [],
        "sem_dado": [],
        "nao_classificados": [],
        "ja_processados": 0,
        "erros": [],
    }
    db = _db_sync()
    try:
        rows = db.execute(
            _t(
                "SELECT onvio_id, nome_arquivo, caminho_local, categoria, mes_ref FROM onvio_documents "
                " WHERE caminho_local IS NOT NULL "
                "   AND categoria IN ('das_simples_nacional','fgts_guia','dctfweb_declaracao','dctfweb_recibo',"
                "                     'dctfweb_debitos','dctfweb_resumo_debitos','iss','darf') "
                "   AND ((:m IS NOT NULL AND mes_ref = :m) OR (:m IS NULL AND created_at >= now() - make_interval(days => :d))) "
                " ORDER BY mes_ref, categoria"
            ),
            {"m": mes_ref, "d": dias},
        ).all()
    except Exception as exc:  # noqa: BLE001
        db.close()
        return {**rel, "ok": False, "erros": [f"fatal ao listar: {exc}"]}
    for oid, nome, caminho, cat, mref in rows:
        fid = f"onvio:{oid}"
        try:
            if not forcar and _ja_processado(db, fid):
                rel["ja_processados"] += 1
                continue
            if not os.path.exists(caminho):
                rel["erros"].append(f"{nome}: arquivo não está no disco")
                continue
            rel["lidos"] += 1
            g = parse_pdf_guia(caminho, nome)
            meta = {"file_id": fid, "nome": nome, "pasta": f"onvio/{cat}/{mref}", "fonte": "onvio_portte"}
            if g.tipo in NOMES:
                if g.vencimento is None or g.valor is None:
                    rel["sem_dado"].append(f"{nome} ({g.tipo}: valor={g.valor}, vencimento={g.vencimento})")
                    continue
                acao = _upsert_obrigacao(db, g, meta)
                rel["guias"].append(
                    {
                        "arquivo": nome,
                        "tipo": g.tipo,
                        "empresa": (g.empresa_id or "")[:8],
                        "competencia": f"{g.competencia_mes:02d}/{g.competencia_ano}" if g.competencia_mes else None,
                        "valor": g.valor,
                        "vencimento": g.vencimento.isoformat(),
                        "acao": acao,
                    }
                )
            elif g.tipo == "DCTFWEB_DECLARACAO":
                rel["acessorias"] += _marcar_acessorias_cumpridas(db, g, meta)
            else:
                rel["nao_classificados"].append(nome)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            rel["erros"].append(f"{nome}: {type(exc).__name__}: {str(exc)[:160]}")
    db.close()
    rel["ok"] = not any(e.startswith("fatal") for e in rel["erros"])
    return rel


def parear_obrigacoes_com_extrato(dias_depois: int = 60, minimo: float = 50.0) -> dict[str, Any]:
    """Obrigação com valor + débito de VALOR EXATO no extrato na janela do vencimento = paga.

    Não havia pareador nenhum: em 27/09/2026 o gate dizia «vencida sem guia» para a GFD da
    Patrimonial de 07/2026 (R$ 7.883,53) que o extrato da Cora mostrava paga em 19/08 — o
    sistema sabia do pagamento e da obrigação e nunca juntou os dois. Regra: mesmo valor
    (±R$ 0,01), débito entre vencimento−5 e vencimento+`dias_depois`, valor ≥ `minimo`
    (abaixo disso a coincidência de valor é barata demais para valer como prova). Grava
    `status='cumprida'` e `pago_por` (id, data, conta) nas observações — o ato fica
    auditável e reversível. Idempotente: só toca linhas ainda não cumpridas.
    """
    from sqlalchemy import text as _t  # noqa: PLC0415

    rel: dict[str, Any] = {"pareadas": [], "sem_rastro": 0, "erros": []}
    db = _db_sync()
    try:
        cands = db.execute(
            _t(
                "SELECT o.id::text, o.tipo, o.competencia_mes, o.competencia_ano, o.data_vencimento, o.valor_devido, "
                "       t.id::text, t.transaction_date, t.bank_account_id::text, coalesce(t.description, t.memo, '') "
                "  FROM fiscal_obligations o "
                "  JOIN LATERAL (SELECT * FROM bank_transactions t WHERE t.amount < 0 "
                "                 AND abs(abs(t.amount) - o.valor_devido) < 0.01 "
                "                 AND t.transaction_date BETWEEN o.data_vencimento - 5 AND o.data_vencimento + :dd "
                "               ORDER BY abs(t.transaction_date - o.data_vencimento) LIMIT 1) t ON true "
                " WHERE o.active AND o.status <> 'cumprida' AND o.valor_devido IS NOT NULL AND o.valor_devido >= :mn"
            ),
            {"dd": dias_depois, "mn": minimo},
        ).all()
        for oid, tipo, m, a, _venc, v, tid, tdate, conta, desc in cands:
            try:
                db.execute(
                    _t(
                        "UPDATE fiscal_obligations SET status = 'cumprida', updated_at = NOW(), "
                        "  observacoes = CASE WHEN observacoes ~ '^\\s*\\{' THEN "
                        "     left(observacoes, length(observacoes) - 1) || ', \"pago_por\": ' || :pp || '}' "
                        "     ELSE coalesce(observacoes, '') || ' | pago_por=' || :pp END "
                        " WHERE id = CAST(:id AS uuid) AND status <> 'cumprida'"
                    ),
                    {
                        "id": oid,
                        "pp": json.dumps(
                            {
                                "bank_transaction_id": tid,
                                "data": str(tdate),
                                "conta": conta,
                                "descricao": desc[:60],
                                "regra": "valor exato na janela do vencimento",
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
                rel["pareadas"].append(
                    {
                        "tipo": tipo,
                        "competencia": f"{m:02d}/{a}",
                        "valor": float(v),
                        "pago_em": str(tdate),
                        "descricao": desc[:40],
                    }
                )
                db.commit()
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                rel["erros"].append(f"{tipo} {m}/{a}: {exc}")
        rel["sem_rastro"] = (
            db.execute(
                _t(
                    "SELECT count(*) FROM fiscal_obligations WHERE active AND status <> 'cumprida' AND valor_devido IS NOT NULL"
                )
            ).scalar()
            or 0
        )
    finally:
        db.close()
    return rel
