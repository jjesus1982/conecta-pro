"""GEDEON — Part 2 do GED do Sólides: mapeia cada documento assinado -> condomínio e arquiva
no kit (subpasta certa pelo nome). Roda no CONTAINER (gdrive + parsing da folha).

O `parent.name` do GED pode ser: o FUNCIONÁRIO (mapeia via folha -> condomínio), o próprio
CONDOMÍNIO (usa direto), ou uma pasta genérica ("Documentos"/"Colaboradores" -> ignora).
Uso: python solides_ged_part2.py [COMPETENCIA=MM.YYYY]"""

import io
import json
import os
import sys
import unicodedata

from googleapiclient.http import MediaIoBaseDownload

from modules.gdrive.services.gdrive_service import gdrive_service as g
from modules.gedeon.services.inter_kit_service import extrair_funcionarios_folha
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo


def norm(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper().strip()


COMP = sys.argv[1] if len(sys.argv) > 1 else "05.2026"
CONDS = ["IDEAL FLORES", "MICHELANGELO", "MIRANTE", "VILLA PÁSSAROS", "VILLA DEI FIORI", "LARANJEIRAS", "PRIME ARENA"]
SRC = "/app/uploads/solides_ged"
g.check_status()
svc = g._service

# 1) mapa funcionário -> condomínio (da Folha de Pagamento.pdf de cada kit). Monta dois índices:
#    - por (primeiro, último) nome  - preciso
#    - por PRIMEIRO nome só quando é ÚNICO entre todos os condomínios (p/ pastas do GED que
#      têm só o 1º nome, ex.: "MALAQUIAS", "GRACIENE"). Se ambíguo, não casa.
emp2cond = {}
primeiro_idx: dict = {}  # primeiro_nome -> set(condominios)
empregados: list = []  # [(set(tokens_nome_completo), cond)] p/ casar por subconjunto
cond_norm = {norm(c): c for c in CONDS}
for cond in CONDS:
    folder = pasta_kit_arquivo(cond, COMP, "Folha de Pagamento.pdf")
    if not folder:
        continue
    it = (
        svc.files()
        .list(
            q=f"'{folder}' in parents and name='Folha de Pagamento.pdf' and trashed=false",
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )
    if not it:
        continue
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, svc.files().get_media(fileId=it[0]["id"]))
    d = False
    while not d:
        _, d = dl.next_chunk()
    for nome, _r in extrair_funcionarios_folha(buf.getvalue()):
        p = norm(nome).split()
        if len(p) >= 2:
            emp2cond[(p[0], p[-1])] = cond
        if p:
            primeiro_idx.setdefault(p[0], set()).add(cond)
            empregados.append((set(p), cond))


def achar_condominio(funcionario: str) -> str | None:
    nf = norm(funcionario)
    tok = set(nf.split())
    # (a) parent é o próprio condomínio? (todos os tokens do condomínio presentes, ex.:
    #     "VILLA DOS PASSAROS" casa "VILLA PASSAROS")
    for cn, cond in cond_norm.items():
        ctoks = set(cn.split())
        if cn in nf or ctoks <= tok:
            return cond
    p = nf.split()
    # (b) primeiro+último exatos
    if len(p) >= 2 and (p[0], p[-1]) in emp2cond:
        return emp2cond[(p[0], p[-1])]
    # (c) tokens da pasta ⊆ tokens do nome completo na folha (ex.: "FERNANDO MIGUEL" ⊆
    #     "FERNANDO MIGUEL GOMES DA SILVA"); só casa se levar a um único condomínio
    if len(tok) >= 2:
        cands = {cond for ts, cond in empregados if tok <= ts}
        if len(cands) == 1:
            return next(iter(cands))
    # (d) pasta com só o 1º nome: índice de 1º nome, só quando único entre os condomínios
    if p:
        conds = primeiro_idx.get(p[0])
        if conds and len(conds) == 1:
            return next(iter(conds))
    return None


man = json.load(open(f"{SRC}/manifesto.json"))
arq = 0
naoachou = []
for e in man:
    cond = achar_condominio(e["funcionario"])
    if not cond:
        naoachou.append(f"{e['funcionario']} ({e['tipo']})")
        continue
    fn = f"{e['label']}_{e['funcionario'].title()}.pdf"  # nome roteia p/ a subpasta certa
    folder = pasta_kit_arquivo(cond, COMP, fn)
    path = f"{SRC}/{e['arquivo']}"
    if folder and os.path.exists(path) and not _arquivo_ja_existe(folder, fn):
        if g.fazer_upload_arquivo(path, folder, fn):
            arq += 1
            print(f"  {cond:15s} <- {e['label']} / {e['funcionario']}")

print(
    f"\ncompetencia: {COMP} | funcionarios mapeados: {len(emp2cond)} | arquivados: {arq} | nao casaram: {len(naoachou)}"
)
for x in naoachou[:20]:
    print("   (sem condomínio):", x)
