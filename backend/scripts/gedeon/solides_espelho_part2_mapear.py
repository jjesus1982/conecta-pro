"""GEDEON — Part 2 do ponto assinado: mapeia funcionário->condomínio e arquiva no kit.
Roda no CONTAINER (gdrive + parsing). Fonte do mapa = a "Folha de Pagamento.pdf" que o
orquestrador já põe em cada kit (auto-suficiente; não depende de pasta manual de folhas).
Uso: python solides_espelho_part2_mapear.py [COMPETENCIA=MM.YYYY]"""

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
g.check_status()
svc = g._service

# 1) mapa funcionário(primeiro+último)->condomínio a partir da Folha de Pagamento.pdf de cada kit
emp2cond = {}
for cond in CONDS:
    folder = pasta_kit_arquivo(cond, COMP, "Folha de Pagamento.pdf")  # subpasta "1. Folha e Pessoal"
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
    for nome, _resc in extrair_funcionarios_folha(buf.getvalue()):
        p = norm(nome).split()
        if len(p) >= 2:
            emp2cond[(p[0], p[-1])] = cond

# 2) para cada espelho baixado, acha o condomínio e arquiva "Folha de Ponto Assinada_Nome.pdf"
man = json.load(open("/app/uploads/solides_espelhos/manifesto.json"))
arq = 0
naoachou = []
for e in man:
    p = norm(e["nome"]).split()
    chave = (p[0], p[-1]) if len(p) >= 2 else None
    cond = emp2cond.get(chave)
    if not cond:
        naoachou.append(e["nome"])
        continue
    fn = f"Folha de Ponto Assinada_{e['nome'].title()}.pdf"
    folder = pasta_kit_arquivo(cond, COMP, fn)  # subpasta "1. Folha e Pessoal"
    path = f"/app/uploads/solides_espelhos/{e['arquivo']}"
    if folder and os.path.exists(path) and not _arquivo_ja_existe(folder, fn):
        if g.fazer_upload_arquivo(path, folder, fn):
            arq += 1
            print(f"  {cond:15s} <- {e['nome']}")
print(
    f"\ncompetencia: {COMP} | funcionarios mapeados: {len(emp2cond)} | "
    f"arquivados: {arq} | nao casaram (outros condominios): {len(naoachou)}"
)
