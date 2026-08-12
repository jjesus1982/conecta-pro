---
name: gold-standard-pdf
description: Use ao gerar, criar ou ajustar QUALQUER documento PDF do Conecta PRO (holerite, recibo, contrato, proposta, ordem de serviço, atestado, aditivo, NF-e/DANFSE, kit GEDEON, relatório, licitação). Garante o padrão-ouro da marca Conecta Mais — logo, cores, rodapé com ícones, assinaturas digitais datadas, tudo dentro das caixas, 1 folha A4 harmoniosa. Marca centralizada em pdf_branding.py; mudar lá muda todos.
---

# Gold-Standard PDF — marca Conecta Mais

## Fonte ÚNICA da marca
`backend/modules/crm/services/pdf_branding.py` (módulo `B`). Mudou o `B` → mudou TODOS os documentos. NUNCA hardcode marca no gerador.

`EMPRESA`: nome="CONECTA MAIS ELETRÔNICA" (nome do cartão CNPJ), razao="Jordan Santos de Jesus Ltda", cnpj 35.710.481/0001-03, site www.conectamais.pro, email jjesus@conectamais.pro, instagram @conectamaisoficial, ceo "JORDAN JESUS" (maiúsculo). Cores: AZUL_ESCURO #1E3A5F, AZUL_MEDIO #2D5F8B, LARANJA #F97316, TEXTO #1F2937, FUNDO_CLARO #F8FAFC.

## Como todo gerador deve ser
- **SimpleDocTemplate**: `topMargin=40mm, bottomMargin=16mm, left/right=16mm` +
  `doc.build(story, onFirstPage=lambda c,d: B.header_footer(c,d,titulo="<TÍTULO>"), onLaterPages=...)`.
  `B.header_footer` já desenha: faixa laranja, logo cheia, "CONECTA MAIS ELETRÔNICA", título, e o RODAPÉ (2 linhas centralizadas: linha1 com ícones prédio·doc·telefone + nome/CNPJ/fone; linha2 site·email·instagram; paginação discreta canto inf. direito). NÃO desenhe header/rodapé próprio.
- **canvas.Canvas** (comprovante, NF-e): `y = B.marca_canvas(c, titulo=...)` no topo + `B.rodape_canvas(c, pagina=n)`.
- Estilos: `st = B.styles()`. Seção: `B.secao(titulo, st)`. Dinheiro: `B.brl(v)`. Datas: `B.br_date`/`B.data_extenso`.

## Assinaturas — `B.campos_assinatura(...)`
Âncoras invisíveis `ASSINAR::FUNCIONARIO` / `ASSINAR::EMPRESA` (o motor de assinatura do Conecta PRO sobrepõe a assinatura no campo de cada nome). Params:
- `funcionario_nome`, `funcionario_cpf`, `funcionario_doc_rotulo` ("CPF" ou "CNPJ/CPF" p/ cliente), `funcionario_label` ("Assinatura do Funcionário"/"do Cliente"/"do Contratante"/"do Emitente").
- `digital_funcionario=True` → "Assinatura digital · Portal do Funcionário" (funcionário assina depois, ao receber). Cliente em contrato/proposta = `digital_funcionario=False`.
- `digital_empresa=True` + `data_empresa=<DD/MM/AAAA>` → **empresa (JORDAN JESUS) assina na DATA DO PAGAMENTO** (sistema coleta data+assinatura ao pagar). Sub-rótulo "Assinatura digital · DD/MM/AAAA".
- `data_prefixo="Pago em "` + `espaco_antes` (respiro).

## Regras estéticas (o Jordan é exigente)
- **1 folha A4** sempre que possível (holerite fecha em 1 pág; se estourar, compacte paddings/margens, não quebre pra 2).
- **Texto SEMPRE dentro das caixas** — use `Paragraph` nas células de tabela (não string crua que transborda).
- Nada de sobreposição (o rodapé em 2 linhas resolveu @instagram×paginação).
- **VERIFIQUE VISUALMENTE**: gere o PDF, dê `Read` no arquivo e confira você mesmo ANTES de mostrar ao Jordan. Ver [[superpowers:verification-before-completion]].
- Logo mantém a tagline "SEGURANÇA E TECNOLOGIA" (arte do PNG); o TEXTO do doc usa "CONECTA MAIS ELETRÔNICA".

## Exemplos canônicos (copiar o padrão)
- `people_management/folha/services/holerite_pdf.py` (holerite padrão-ouro, 1 pág, ícones de seção, CBO).
- `people_management/folha/services/recibo_vt_vr_pdf.py` (recibo VT/VR + citação legal Lei 7.418/1985).
- `gedeon/services/comprovante_generator.py` (canvas + marca_canvas, aprovado).
- Dado do doc vem REAL do banco (ver [[veracity-sweep]]); dado legal de folha vem das regras da [[folha-cct]].

## Deploy
Gerador é backend baked → ver [[deploy-bake]] (docker cp + bake). Endpoint holerite real: `GET /api/v1/people-management/folha/holerite/{id}/{mes}/{ano}/pdf`. SCP p/ o Jordan: ele puxa do VPS (`scp root@82.25.75.74:/opt/conecta-pro/<arquivo>.pdf ~/Downloads/`).
