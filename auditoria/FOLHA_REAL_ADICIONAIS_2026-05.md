# Adicionais por Funcionário — Folha REAL 05/2026 (Domínio/Portte)

Fonte: 9 folhas por condomínio no Drive do Jordan (competência 05/2026). Adicionais são
INDIVIDUAIS (por posto/atividade), NÃO por cargo. Ex.: 2 ASG mesmo cargo, só quem limpa
a lixeira/mexe em resíduos recebe insalubridade.

## INSALUBRIDADE 10% (12 na folha; 11 ativos + Silvana demitida)
Ademir Salustiano (ASG), Antônio Carlos Vieira (Artífice), Daniel Vidal Larroque (ASG),
Fernando Miguel Gomes (ASG), Geilson Rodrigues (Jardineiro), Graciene Pereira (ASG),
Jaqueline Carlos (ASG), Kalel Silva (Artífice), Lorinaldo Oliveira (ASG — pediu demissão, desligado),
Malaquias Pereira (ASG), Oscar Soares da Costa (ASG), [Silvana Amazonas — DEMITIDA].
→ ASG SEM insalubridade (mesmo cargo): Celiane, Edilene, Sebastião, Telma, Vanderlice.

## RONDA 15% (12, todos ativos)
Adailson Serra, Ailton César, Anilson José, Antônio Diniz, Antônio Walcicley (Líder),
Ediwilson Correa (Líder), Eduardo Oliveira, Eidy Culier, Jonhata Diniz, Jonilson Martins,
Matheus Henrique, Rilem Ferreira.

## PERICULOSIDADE: NENHUM funcionário (0). Confirmado na folha real.

## Salários-base (batem com piso CCT): Agente Portaria/ASG/Jardineiro R$1.670; Artífice R$1.742,52; Líder Portaria R$1.787,53.

NOTA: Lorinaldo pediu demissão e foi desligado (sistema correto=inativo). A folha 05/2026 o
pegou trabalhando por ser anterior ao desligamento. Adicional zerado (inerte).

Aplicado no ERP: employees.insalubridade_percentual/periculosidade_percentual/adicional_ronda_percentual.
Folha lê do funcionário. Validado 53/53 sem erro. Commit e9af7255.

## PENDÊNCIA DE REVISÃO (Contador) — 2026-07-01
- **GEILSON RODRIGUES DE ANDRADE (Jardineiro)**: recebe INSALUBRIDADE 10% na folha 05/2026.
  Jordan aponta que jardineiro NÃO mexe com lixo → possivelmente deveria ser PERICULOSIDADE
  30% (opera roçadeira/motores a combustão — NR-16), que é excludente da insalubridade.
  DECISÃO DO JORDAN: **MANTER como está (insalubridade 10%, espelhando a folha) até o contador revisar**.
  NÃO reclassificar sem laudo NR-16. Se reclassificar: 10%→30%, some insalubridade, R$167→R$501.

## RECONCILIAÇÃO JUNHO 2026 (2 planilhas: Jordan + Pyetra) — aplicada
Fontes: "Adicionais_por_Posto" (Jordan preencheu adicionais) + "ESCALAS JUNHO 2026" (Pyetra: posto/turno/setor).
- 45 alocados: insalubridade + ronda já batiam. Não-listados (Gelson Bernardo, Raimundo José, Jordana Bacry): já inativos.
- Novos aplicados: Adeílson/Jonathan Mendes/Rene (AGP noturno), Daniel Souza (diurno), Angela+Paulo (ASG insalubridade).
- Divergências resolvidas pelo Jordan: Antônio Gama=rondista(15%), Francisco Ramon=rondista(15%),
  Keyson=Prime Arena/Diurno (sem noturno), Euler=ativo (cobre férias do Ediwilson).
- Totais: 51 ativos | insalubridade 10% = 12 | ronda 15% = 13 | noturno = 17 | diurno = 34.
- Backups: employees_status_bkp_20260701, employees_adicionais_bkp_20260701.

## ESTADO FINAL (após planilha atualizada do Jordon + Pyetra, 01/07)
- 50 ativos | 2 afastados INSS (Cintia + Elen, acidente moto) | 3 demitidos jun (Marta 08/06, Lorinaldo 01/06, Marcelino 29/06)
- Insalubridade 10% = 12 | Ronda 15% = 13 | Noturno = 16
- Sebastião: ASG→Artífice (carteira 30/06), salário R$1.742,52 + cct_cargo Artífice já alinhados.
- Geilson = Jardineiro (correto). "[não encontrado]" na planilha = artefato do meu gerador (sobrenome a mais no match), não erro real.
- PENDÊNCIA FUTURA (3/jul): Ediwilson entra de férias → Euler cobre Mirante, Kelly Patrícia (diarista, não-CLT) cobre Euler no Ideal. Ajustar alocação na data.
- Fonte de verdade: sistema reconciliado com folha real Domínio + planilha Jordan (adicionais) + escala Pyetra (posto/turno/junho).
