# CONTRATO DA FUNDAÇÃO — Botões de Documento no Redesign (CONGELADO)

> Este é o contrato que os **3 terminais** seguem para ligar botões "abrir HTML + baixar PDF".
> A fundação (DocButtons/docsource/doc()/tbl-docsfn) está deployada e provada. **NÃO edite a
> fundação** (`ModuleView.tsx`, `docsource.ts`, `DocButtons.tsx`, o helper `doc()`/`tbl` no
> `redesign_data_controller.py`). Se precisar de um caso novo, **sinalize ao orquestrador (T1)**.

## Como um builder liga um documento

No seu `redesign_builders/<modulo>.py`, importe `doc`:
```python
from modules.operacional.controllers.redesign_data_controller import (..., doc, ...)
```

### 1) Documento nível-TELA (aparece abaixo do título) — `scr["docs"]`
Para documentos agregados/da tela (DRE do mês, relatório da tela, export da lista):
```python
out["relatorios"]["docs"] = [
    doc("DRE (PDF)", "/api/v1/financial/relatorio?tipo=dre&ano=2026", fmt="pdf", gate="financeiro"),
    doc("Balancete (PDF)", "/api/v1/financial/relatorio?tipo=balancete&ano=2026", fmt="pdf", gate="financeiro"),
    doc("Exportar conciliação", "/api/v1/financial/bank-reconciliations/{id}/export", fmt="csv", mode="json"),
    doc("SPED (aguardando)", disabled=True, motivo="Aguardando emissão real"),
]
```

### 2) Documento por-LINHA (holerite por colaborador, DANFSe por nota) — `docsfn` no `tbl`
Passe `docsfn=lambda r: [...]` ao `tbl`. **Inclua o id na 1ª coluna do SELECT** e use nas rotas:
```python
await safe("holerites", tbl(
    "Holerites", f"{n} colaboradores", "—",
    ["Colaborador", "Competência", "Líquido", "Status"], "2fr 1fr 1fr 0.9fr",
    "SELECT p.id, e.nome, p.competencia, p.net_salary, p.status "
    "FROM hr_payslips p JOIN employees e ON e.id=p.employee_id ORDER BY p.competencia DESC LIMIT 200",
    lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]), t(brl(r[3]), 600), b(r[4], "ok")],
    docsfn=lambda r: [doc("Holerite", f"/api/v1/people-management/portal/payslips/{r[0]}/download", fmt="pdf")]))
```
O `ModuleView` anexa automaticamente uma coluna "Documento" com os botões (retrocompatível: telas sem `docsfn` não mudam).

## Assinatura do `doc()`
```python
doc(label, url=None, fmt="pdf", mode="blob", filename=None, gate=None, disabled=False, motivo=None)
```
| campo | o que é |
|---|---|
| `label` | texto do chip/botão |
| `url` | **rota EXATA do backend** (copiar da MATRIZ/código — NUNCA adivinhar). Normalmente `/api/v1/...` |
| `fmt` | `pdf`·`html`·`xml`·`txt`·`xlsx`·`csv`·`zip`. Define ícone e se há "Abrir" (só pdf/html/xml/txt abrem inline; xlsx/csv/zip só baixam) |
| `mode` | `blob` (arquivo direto — FileResponse/StreamingResponse, **default**) ou `json` (endpoint devolve `{content,filename,mime?}`, ex. conciliação) |
| `filename` | nome sugerido no download (opcional) |
| `gate` | informativo/UX (o gate REAL é no endpoint do backend) |
| `disabled`+`motivo` | documento indisponível (stub/placeholder/sem transmissão real) → botão off honesto |

## Os 3 MODOS de fonte (o `DocButtons` cobre todos)
- **blob** (maioria): endpoint devolve o arquivo. Abrir = nova aba via object URL; Baixar = `<a download>`. Usa `abrirPdf`.
- **json**: endpoint devolve `{content, filename, mime?}` → decodificado p/ Blob client-side. Use `mode="json"`. (Ex.: `/financial/bank-reconciliations/{id}/export`.)
- **Content-Disposition**: honrado automaticamente no download (nome do arquivo do header).

## REGRAS DE OURO (do pré-mortem — inegociáveis)
1. **Rota EXATA** — copie do backend/MATRIZ; confirme que o router está montado em `main_production.py` (não `main.py`). Bases distintas: DP=`/people-management`, GED=`/ged`, portal=`/people-management/portal`, candidatos=`/human-resources`.
2. **Nunca fabricar** — documento stub/placeholder/sem-transmissão-real = `disabled=True` + `motivo` honesto. NUNCA um botão que abre lixo. (Ex. ⛔ da MATRIZ: DANFE/NFC-e placeholder, SPED, comodato, licitação-sem-rota, `/campo/visitas` sem-auth até corrigir.)
3. **Gate é no backend** — esconder botão é só UX; o endpoint DEVE gatear (financeiro=Jordan+Pyetra, fiscal idem). QA vai chamar com perfil sem permissão e esperar 403.
4. **Importe TODOS os helpers no topo** — `doc` inclusive. `except: pass` engole `NameError` → botão some em silêncio. `py_compile` antes de commitar.
5. **id na 1ª coluna do SELECT** para docs por-linha.
6. **Modo certo** — se o endpoint devolve `{content,filename}` (JSON), use `mode="json"`, senão abre JSON como se fosse PDF.
7. **Verifique pela rota da tela no domínio público** com cache-bust após o release.

## Piloto de referência (já no ar)
`redesign_builders/documentos.py` — tela `visao` tem `scr.docs` com os 3 modos (GED blob real · conciliação JSON · SPED disabled); tela `arquivos` tem `row.docs` (download GED por linha). Use como exemplo-âncora.
