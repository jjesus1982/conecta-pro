# As telas da Pyetra medidas de ponta a ponta — e o que o ensaio revelou de passagem

**29/09/2026.** Verificação das três etapas que o Jordan autorizou: competência nas telas de kit,
tela de conferência com ensaio antes de aplicar, e as pessoas sem posto pedindo condomínio.
Medido pelo despachante e por um **ensaio real**, não por leitura de código.

## ✅ As telas existem e respondem

`GET /api/v1/redesign/data/documentos` → **HTTP 200, 45 telas**, 15 delas de kit.

| tela | campos | padrão |
|---|---|---|
| `kits-montar` | competencia · condominios · blocos | **`08.2026`** (ponto — a API do GEDEON exige) |
| `kits-conferir` | competencia · acao | **`08/2026`** (barra) |
| `kit-definir-condominio` | competencia · employee_id · condominio · motivo | `08/2026` |
| `kit-anexar-comprovante` | kit_id · employee_id · document_type · document_name · notes · **file** | — |

⚠️ **Sobre o padrão da competência**, e é ambiguidade da instrução, não do código: o Jordan pediu
«mês corrente como padrão» e, na mesma frase, «o comportamento de hoje continua sendo o default».
As duas metades divergem. Implementei o **mês anterior**, seguindo o exemplo concreto dele («o kit
de setembro com o mês de competência sendo agosto»), que é também o que a operação usa. Se ele
preferir o mês corrente, é uma linha.

## ✅ O ensaio roda, e a contagem é exata

`POST /api/v1/redesign/action/kits-conferir` com `acao=ensaio`:

> Competência 08/2026 · **8 kit(s) de cliente** · **53 pessoa(s) no roster** · ENSAIO — nada foi
> alterado. 2 vínculo(s) a remover. 1 kit(s) sem roster (não tocados). **Ninguém sem condomínio.**

**53** é exatamente o número que o Jordan deu. E as colunas são as que ele pediu:

| Condomínio | Colaborador | O que acontece | Por quê |
|---|---|---|---|
| GREEN HILLS | — | **nada — precisa de conferência humana** | não casou com nenhum condomínio que teve batida |
| VILLA DEI FIORI | Jordan Santos de Jesus | remover 8 vínculo(s) | nenhuma batida em posto de cliente nesse mês |
| MIRANTE DAS FLORES | EULER FELIPE FERNANDES | remover 9 vínculo(s) | trabalhou em Laranjeiras Village nesse mês |

⭐ **A contagem do ensaio está certa ao documento.** Conferi os 8 do primeiro caso: são
exatamente as linhas de 08/2026 (PIX Folha ×2, Adiantamento 40%, VR, VT, Contracheque, Folha de
Ponto, Recibo de Adiantamento) — as de 09/2026 ficam fora, corretamente.

## O susto que não era, e a correção da minha própria hipótese

Ao ver «Jordan Santos de Jesus» num kit de cliente eu levantei que a **folha do dono** estivesse
indo para um condomínio. **Errado.** O cadastro diz: *AGENTE DE PORTARIA · status `candidato` ·
contrato `experiencia` · sem papel de usuário*. É um homônimo ou registro de teste — não o sócio.

E ninguém foi exposto:

| verificação | resultado |
|---|---|
| kits com `sent_at` preenchido | **0 de 139** |
| acessos ao kit do Fiori 08/2026 | **12, todos `internal`** |
| último acesso de ator `client` **em qualquer kit** | **30/06/2026** — antes destes kits existirem |

⚠️ Mas **19 kits têm `google_drive_link`**, inclusive esse. Então o canal de entrega existe; o que
não há é registro de entrega. Vale o Jordan dizer se a entrega acontece pelo Drive à mão — porque
pelos dados do sistema **nenhum kit jamais foi entregue**, e isso é ou capacidade desligada ou
registro faltando.

## O caso que sobra de verdade

Esse «Jordan Santos de Jesus»: **0 batidas · 23 turnos · 13 documentos de folha · admitido
19/07/2026 · status `candidato`**.

⭐ **Folha de pagamento gerada para quem nunca bateu um ponto.** Contracheque, folha de ponto e
comprovantes PIX, todos `auto_generated`. É o mesmo padrão dos 16 sem batida medida do outro
relatório, levado ao extremo: o gerador não pergunta se houve trabalho.

## ⚠️ Uma armadilha que eu quase publiquei como achado

Medi que kits carregam documentos de folha de gente não-ativa: 15 inativos (225 docs), 6
demitidos (136), 2 afastados (45), 1 suspenso (15), 1 candidato (13) — **25 pessoas, 434
documentos**. Ia chamar de defeito.

**Não é.** `status` é fato de HOJE; o kit é fato HISTÓRICO. Quem foi demitido em setembro
pertence ao kit de agosto. Julgar pertencimento por status atual é exatamente o erro que o
roster evita ao se ancorar no **`posto_id` da batida**. O único caso que sobra é o candidato com
zero batida — porque ali não há trabalho histórico nenhum a que o documento corresponda.

## Veredito por lente

| Lente | Status | Evidência |
|---|---|---|
| DADO | ✅ | ensaio real: 8 kits, 53 pessoas, 2 remoções, contagem conferida ao documento |
| TELA | ⚠️ **parcial** | despachante 200 com os campos e padrões certos; **não abri o navegador** |
| CÓDIGO | ✅ | 23 oráculos de ponto/folha/kit verdes por código de saída |

⚠️ A lente TELA está parcial de propósito e não vou dizer que está verde: medi o **contrato** que
o front recebe, não o clique. Falta alguém abrir `/redesign/documentos` e rodar o ensaio no
navegador — os campos podem estar certos no JSON e a tela não renderizar a coluna «Por quê», que
é justamente a que dá à Pyetra o direito de discordar.
