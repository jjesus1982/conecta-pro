# Revisão government_integrations (agente só-leitura, sem contato com governo, 08/09/2026 ~10h)

224 rotas únicas (448 no inventário: main_production.py:942 e :1000 montam o mesmo router duas vezes), 25 controllers. VIVA 16 · LIGAR 4 · INTERNA 15 · MORTA 189 (84%). Nenhuma das 33 tabelas dos models do módulo existe no banco (gov_*, gov_esocial_events, gov_notas_fiscais, fgts_recolhimentos, inss_contribuicoes, fgts_inss_*). ESOCIAL_AMBIENTE=producao, NFSE_MANAUS_ENVIRONMENT=producao, NFSE_NACIONAL_ENVIRONMENT=homologacao.

## Defeitos (mais grave primeiro)
1. [8 segurança] `controllers/esocial_controller.py:76,258,292,352,393,432` — seis POSTs (/evento, /configurar-empresa, /calcular-folha, /validar-evento, /gerar-lote, /transmitir-s1000) SEM Depends(get_current_user); /evento e /transmitir-s1000 transmitem SOAP+mTLS real em produção. Porta 8080 publicada em 0.0.0.0 e DOCKER-USER só fecha a 3001. Prova: POST /esocial/validar-evento sem token → 200.
2. [8/7] `core/esocial_transmitter.py:579,681,944-1063` + `services/esocial_service.py:127-133` — eventos em dict por chamada; nunca persistidos; repetir o POST reenvia S-2200/S-2299 sem dedupe.
3. [8/7/3] `controllers/nfse_nacional_controller.py:48-119` → `core/nfse_nacional.py:390-421` — "Emitir" transmite DPS em homologação, numero_dps = timestamp, nada gravado, HTTP 202 mesmo rejeitada, IM vazio.
4. [5/8] `gedeon/services/kit_faturamento_service.py:117-131` → `nfse_manaus_service.py:119-131` → `core/nfse_manaus.py:541-575` — "Faturar kit" com confirmar=true envia RecepcionarLoteRps ao Ábaco (provedor abandonado desde 12/2025) em produção; RPS/lote = timestamp; sem trava.
5. [8] `controllers/extraction_controller.py:262-382` → `extractors/sefaz/nfe_extractor.py:153-190` — DistDFe do NSU 0, laço de 100, sem trava, nada gravado; concorre com o consumidor legítimo (checkpoint 843) → cStat 656. Sem chamador. Apagar /extracao/*.
6. [8/6] `jobs/monitoring_tasks.py:44-100` + `celery_app.py:406-408` — verificar_disponibilidade a cada 5 min: ~2.000 GETs/dia a 27 SEFAZ para empresa que não emite NF-e; chave NfeStatusServico4 não existe na matriz → AM sempre "degraded".
7. [1/6] `controllers/fgts_inss_controller.py:145,189` — filtra document_type grf_fgts/gps_inss (inexistentes; reais fgts_guia=15, gfd_fgts_mensal=14, inss_guia=7); mes_ref "2026-03" nunca casa com %m.%Y → MCP guias_fgts sempre vazia.
8. [6] `controllers/esocial_controller.py:173-235` — lê eventos_esocial (órfã, 0); a verdade é esocial_eventos_espelho (290). MCP listar_eventos_esocial e 5 agentes recebem [].
9. [5] `services/dctfweb_service.py:35,156-166` — get_empresa_fiscal() sem slug → sempre Eletrônica (Patrimonial nunca apurada); terceiros SEST/SENAT/SENAR em vez de SESC/SENAC/SEBRAE (FPAS 515), 5,3% ≠ 5,8%; RAT 3% fixo.
10. [3/6] `controllers/govbr_controller.py:142-171` + `core/govbr.py:207-247` — callback exige Bearer → 401; troca de token não faz HTTP; 12 rotas mortas.
11. [3] `services/ecac_service.py:259-274` — POST /ecac/certidao devolve CND vazia com success=True; situação fiscal é só fiscal_obligations local rotulado como e-CAC.
12. [1/2/6] `controllers/sync_controller.py` (16), `jobs_controller.py` (8) — sombreamento, métodos inexistentes, tabelas gov_* inexistentes → 500. Apagar.
13. [2] `controllers/sefaz_am_controller.py:206-458`, `sefaz_controller.py:38,85` — TypeError/AttributeError 500. Apagar.
14. [3] `services/efd_reinf_service.py:456` rejeição vira sucesso; `core/efd_reinf.py:242` cpfCtt zeros; enviar-lote "enviado" sem enviar.
15. [3 dinheiro] `core/fgts_digital.py:295-304,421-444` — guia e PIX fabricados; multa 40% sempre. Aposentar.
16. [5] `services/fgts_inss_service.py:151-190` tabela INSS 2024 rotulada 2026.
17. [5] `esocial_controller.py:527-537` gaps S-2200 contam is_active (65) em vez de CLT ativo (53).
18. [2] `mcp-server/server.py:2682` esocial_timeline_funcionario passa UUID a /espelho/timeline/{cpf}.
19. [4] fuso: `esocial_espelho_service.py:115` CURRENT_DATE UTC (orçamento de 10 acessos/dia vira às 21h); `core/nfse_nacional.py` dhEmi now()-3h com -03:00 literal; certificate_manager valid_until naive; cte/mdfe -04:00 fixo; dashboard_controller utcnow vs Manaus.
20. [3/6] beat: sincronizar_nfse_entrada 405 diário reportado como sucesso (redundante com financial.sincronizar_nfse_nacional); verificar_certificados, reprocessar_falhas, gerar_relatorio_diario, limpar_cache não fazem nada. sincronizar_nfe_entrada fica (correto).
21. [6] mocks com success=True sem chamador: nfce, migração NFS-e "prevista 2026", cancelar/substituir/consultar NFS-e, DAS simulado, cte/mdfe em dict, sped_fiscal com NFS-e como modelo 55, sped_contabil singleton, certificate store em memória, status_controller hardcode, extraction status.
22. [3/6] clássico chamando errado: esocial/page (422), dctfweb/page (422), sped.service → /efd-reinf/importar (404), fgts-simples GET em POST (405), useGovBrECAC → /govbr-ecac (inexistente).

## Vereditos
- esocial_espelho (3): sincronizar VIVA (redesign DP), resumo VIVA (MCP), timeline/{cpf} LIGAR.
- esocial (10): gaps-funcionarios, eventos-suportados INTERNA; 8 MORTA (eventos órfã, evento/configurar/transmitir sem auth, consultar, calcular-folha mock, validar, gerar-lote 501).
- dctfweb (11): status INTERNA; consolidar, gerar-darfs, consultar/{periodo} LIGAR (após empresa/terceiros); 7 MORTA.
- efd-reinf (10): r1000/r2010/r2099/r4010/r4020 VIVA (clássico, XML em memória); status, classificacoes INTERNA; naturezas, enviar-lote, r1000/transmitir MORTA.
- fgts-digital (11): status INTERNA; 10 MORTA. fgts_inss (5): MORTA como estão (corrigir guias → INTERNA para MCP). receita_federal (3): MORTA.
- nfse_nacional (13): emitir VIVA-com-defeito; tomadores VIVA (lento, 80 páginas do ADN por request); status INTERNA; 10 MORTA. nfse_manaus (8): emitir VIVA-com-defeito (kit), consultar/rps INTERNA, 6 MORTA.
- nfce (9), sefaz (2), sefaz-am (8), cte (10), mdfe (14): MORTA. certificate (7): GET / INTERNA, 6 MORTA. sped_contabil (13): gerar VIVA, status INTERNA, 11 MORTA. sped_fiscal (13): status INTERNA, 12 MORTA. simples_nacional (10): status INTERNA, 9 MORTA. ecac (9): status, situacao-fiscal, debitos, parcelamentos VIVA (dado local rotulado como RFB), 5 MORTA. govbr (12): MORTA. dashboard (7): status VIVA (clássico) + LIGAR; dashboard/, certificados/alertas INTERNA; metricas, eventos, endpoints, verificar MORTA. status (2): MORTA. sync (16), jobs (8), extracao (10): MORTA.
- Beat: sincronizar_nfe_entrada OK; sincronizar_espelho_esocial OK; verificar_disponibilidade nocivo; sincronizar_nfse_entrada quebrado; 4 tasks vazias.
