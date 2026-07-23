# BRIEFING — TERMINAL 2 (T2) · Pessoas: DP + Gestão-Pessoas + Portal + RH + Recrutamento

> Missão: ligar botões **abrir HTML + baixar PDF** em TODO documento do seu território no **redesign**.
> Trabalhe em **LOOP** até fechar o checklist. **NÃO faça deploy** (release único pelo orquestrador).
> Leia antes: `CONTRATO-FUNDACAO.md`, `MATRIZ-MESTRE-REDESIGN.md`, `PRE-MORTEM.md`.

## Seu território (edite SÓ estes builders)
`redesign_builders/`: **departamento_pessoal.py · gestao_de_pessoas.py · portal_do_funcionario.py · rh.py · recrutamento.py · homologacao.py**
Módulos redesign: departamento-pessoal (17), gestao-de-pessoas (15), portal-do-funcionario (9), rh (14), recrutamento (5), homologacao (1).
Você é o **dono das fronteiras GED/ponto/saúde** — evite colidir com T1 (que tem documentos/saude): **DP/RH/portal/recrutamento são seus; documentos-GED e saude-ocupacional são do T1**. Ponto/espelho: o builder DP/gestao-pessoas é seu.

> **NUNCA** edite fora da lista nem a fundação. Caso novo → orquestrador.

## Documentos a ligar (rota EXATA — atenção às BASES de API distintas!)
Bases: DP/folha/ponto = `/api/v1/people-management(/hr)` · portal = `/api/v1/people-management/portal` · candidatos = `/api/v1/human-resources`.

**✅ ready (por-linha, salvo indicado):**
- DP/folha → **Holerite** `/api/v1/people-management/portal/payslips/{id}/download` (💰 por-linha). *(a `/portal/payslips/{id}/download` que testei deu 404 num id — confirme o id/rota viva; o holerite vivo é o de people_management, não os 3 submódulos hr não-montados.)*
- DP/folha → **Folha consolidada** `/api/v1/people-management/folha/{mes}/{ano}/pdf` (por-tela, 💰).
- DP/folha → **Recibo VT/VR** `/api/v1/people-management/folha/recibo-vt-vr/{emp}/{mes}/{ano}/pdf` (L6 — por-linha, 💰).
- DP/folha → **Export Domínio** (TXT, por-tela, 💰).
- DP/rescisao → **TRCT** `/api/v1/people-management/.../trct/pdf` (⚖️).
- DP/aviso-previo → `/api/v1/people-management/.../aviso-previo/pdf` (PDF+HTML, par gerar→baixar).
- DP/ponto (espelho) → **Espelho 671** `/api/v1/people-management/hr/ponto/espelho/{emp}/{mes}/{ano}/pdf` (⚖️).
- DP/ponto → **AFD** `/api/v1/.../rep/afd/export/{device}/download` (TXT ⚖️).
- DP/contratos → **Contrato CLT** (PDF+HTML, par).
- DP/eSocial → **S-2200/S-2299 XML** `/api/v1/people-management/esocial/.../{id}/xml`.
- DP/documentos → **Documento do funcionário** `/api/v1/people-management/hr/documents/{id}/download` (blob por-linha).
- portal/contracheque → **Holerite** (mesma rota portal).
- portal/meus-documentos → documento do funcionário.
- recrutamento/candidatos → **Documento do candidato** `/api/v1/human-resources/candidatos/{id}/documento/{doc_id}` (L7, blob).
- gestao-pessoas/RH-relatórios → `/api/v1/.../rh/relatorio` (PDF/CSV).

**🔨 criar rota/render (só-JSON):**
- DP: PPP dados, prontuário, holerite/resumo/conferência da folha, termos de consentimento (só-JSON hoje).
- recrutamento: **dossiê KYC Infosimples** (só-JSON → precisa render PDF; sinalize).

**⛔ NÃO ligar (corrigir/desabilitar honesto):**
- ponto/atrasos e ponto/banco-horas — botão "Exportar" era **stub sem onClick** no clássico → só ligue se houver rota real, senão exporte a lista client-side.
- eSocial S-2210/2220/2230/2240 — XML transmitido mas **sem rota de preview** → `disabled` até criar rota (peça ao orquestrador se necessário).

## Cuidado especial (do pré-mortem)
- 💰 tudo de folha/holerite/TRCT/Domínio + 🏛️ eSocial/PPP: **gate no backend** (o endpoint tem que gatear). Não confie só em esconder o botão.
- Consolidar o gerador de holerite: há um `_generate_payslip_pdf` inline fora do `pdf_branding` — se topar, sinalize (não é seu conserto, é do backend).

## Fluxo do loop
Igual aos demais: rota real → `scr.docs`/`docsfn` → py_compile → oráculo in-process → `git add` só do seu builder → commit por etapa (2-3 telas) → checklist. **Sem deploy.**
