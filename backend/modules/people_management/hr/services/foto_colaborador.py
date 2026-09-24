"""Foto do colaborador (DGX T1, 24/09/2026) — `employees.foto_url` finalmente tem quem escreva.

Medido antes: 0 de 63 ativos com foto; a coluna só era preenchida pelo sync Sólides (URL
externa) e o crachá da F6 saía com moldura vazia. O DGX faz por `POST /Colaboradores/IncluirFoto`
(multipart) e por `/frontend/empregadofotos` (lote). Aqui: um arquivo por pessoa em
`UPLOADS_DIR/employees/<id>.<ext>` e `foto_url = 'employees/<id>.<ext>'` — RELATIVO a UPLOADS_DIR,
que é exatamente o segundo candidato que `cracha_pdf.foto_path` já resolve. Nada em F6 muda.

Lote = ZIP com um arquivo por pessoa, batizado pela MATRÍCULA, pelo CPF (só dígitos) ou pelo
UUID do colaborador. O form do redesign manda UM arquivo (`type:"file"`), por isso ZIP.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path

from sqlalchemy import text

_MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_EXT_OK = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FOTO = 5 * 1024 * 1024  # 5 MB — foto de crachá, não de campo


def fotos_dir() -> Path:
    return Path(os.getenv("UPLOADS_DIR", "/app/uploads")) / "employees"


def ext_por_mime(content_type: str | None, nome: str = "") -> str | None:
    ext = _MIME_EXT.get((content_type or "").lower())
    if not ext:
        e = os.path.splitext(nome or "")[1].lower()
        ext = ".jpg" if e == ".jpeg" else (e if e in _EXT_OK else None)
    return ext


def _valida(conteudo: bytes, ext: str | None) -> str:
    if not ext:
        raise ValueError("Envie JPEG, PNG ou WebP.")
    if not conteudo:
        raise ValueError("Arquivo vazio.")
    if len(conteudo) > MAX_FOTO:
        raise ValueError("Foto acima de 5 MB.")
    # assinatura do arquivo, não a extensão que o navegador disse
    if not (conteudo[:3] == b"\xff\xd8\xff" or conteudo[:8] == b"\x89PNG\r\n\x1a\n" or conteudo[:4] == b"RIFF"):
        raise ValueError("O conteúdo não é uma imagem JPEG/PNG/WebP.")
    return ext


async def salvar_foto(db, employee_id: str, conteudo: bytes, content_type: str | None, nome: str = "") -> str:
    """Grava a foto e escreve `employees.foto_url`. Devolve a url relativa gravada. Lança ValueError."""
    ext = _valida(conteudo, ext_por_mime(content_type, nome))
    row = (await db.execute(text("SELECT id::text, foto_url FROM employees WHERE id::text = :e"), {"e": employee_id})).first()
    if not row:
        raise ValueError("Colaborador não encontrado.")
    d = fotos_dir()
    d.mkdir(parents=True, exist_ok=True)
    # apaga a anterior se tinha outra extensão (evita .jpg e .png da mesma pessoa)
    for old in d.glob(f"{row[0]}.*"):
        old.unlink(missing_ok=True)
    (d / f"{row[0]}{ext}").write_bytes(conteudo)
    url = f"employees/{row[0]}{ext}"
    await db.execute(text("UPDATE employees SET foto_url = :u, updated_at = now() WHERE id::text = :e"), {"u": url, "e": row[0]})
    await db.commit()
    return url


async def importar_zip(db, zip_bytes: bytes) -> dict:
    """ZIP → uma foto por pessoa. Casa pelo nome do arquivo: matrícula, CPF (11 dígitos) ou UUID."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("O arquivo não é um ZIP válido.")
    pessoas = (
        await db.execute(
            text(
                "SELECT id::text, nome, coalesce(matricula,''), regexp_replace(coalesce(cpf,''), '\\D', '', 'g') "
                "FROM employees WHERE data_demissao IS NULL"
            )
        )
    ).fetchall()
    por_matricula = {p[2]: p for p in pessoas if p[2]}
    por_cpf = {p[3]: p for p in pessoas if len(p[3]) == 11}
    por_id = {p[0]: p for p in pessoas}
    ok, nao_encontrados, ignorados = [], [], []
    for info in zf.infolist():
        if info.is_dir():
            continue
        base = os.path.basename(info.filename)
        chave, ext = os.path.splitext(base)
        chave = chave.strip()
        if ext.lower() not in _EXT_OK:
            ignorados.append(base)
            continue
        digitos = re.sub(r"\D", "", chave)
        p = por_id.get(chave.lower()) or por_matricula.get(chave) or (por_cpf.get(digitos) if len(digitos) == 11 else None)
        if not p:
            nao_encontrados.append(base)
            continue
        try:
            await salvar_foto(db, p[0], zf.read(info), None, base)
            ok.append({"nome": p[1], "valor": base})
        except ValueError as e:
            ignorados.append(f"{base} ({e})")
    return {"ok": ok, "nao_encontrados": nao_encontrados, "ignorados": ignorados}


def demo() -> None:
    assert ext_por_mime("image/jpeg") == ".jpg" and ext_por_mime(None, "x.JPEG") == ".jpg" and ext_por_mime(None, "x.gif") is None
    jpg = b"\xff\xd8\xff\xe0" + b"\0" * 10
    assert _valida(jpg, ".jpg") == ".jpg"
    for bad, ext in ((b"GIF89a", ".jpg"), (b"", ".jpg"), (jpg, None), (b"\xff" * (MAX_FOTO + 1), ".jpg")):
        try:
            _valida(bad, ext)
            raise AssertionError("aceitou o que devia recusar")
        except ValueError:
            pass
    print("ok foto_colaborador")


if __name__ == "__main__":
    demo()
