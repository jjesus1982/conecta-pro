# DESENHO — Rastreador veicular × check-ins de visita (2026-07-10)

Objetivo do Jordan: carro e moto da empresa usados pela gestão de campo (PJ) sem controle.
Cruzar a posição REAL dos veículos com os check-ins das visitas: confirmar presença,
revelar visita não registrada e denunciar uso indevido. Tudo dentro do ERP.

## Arquitetura recomendada (decisão A)

**Traccar self-hosted** (open source, padrão de mercado, 200+ protocolos) em container no
servidor atual + rastreadores GT06 + chips M2M. Sem mensalidade de software; alternativa
seria rastreadora local com API (mensalidade R$40-80/veículo e dependência do fornecedor).

```
[GT06 no carro]──gprs──┐
[GT06 na moto]──gprs──►│ Traccar (container, porta 5023 devices / 8082 web via nginx)
                       │   └─ Postgres existente, database dedicado `traccar`
                       ▼
        ERP Conecta PRO (módulo operacional/frota)
        ├─ traccar_client.py (REST: /api/positions, /api/reports/{route,stops,trips})
        ├─ frota_veiculos (nome, placa, tipo, traccar_device_id)
        ├─ frota_atribuicoes (veículo × condutor, início/fim — quem está com o carro)
        └─ correlação com inspection_checkpoints (abaixo)
```

## A correlação (o coração)

1. **No check-in/check-out** (`checkin_condominio`/`checkout_condominio`): job assíncrono
   consulta a posição do veículo atribuído ao inspetor naquele instante e grava no
   `extra_data` do checkpoint: `{veiculo, distancia_m, lat/lon do veículo}` +
   flag **`veiculo_no_local`** (≤300 m). Check-in com veículo a >2 km = 🚩 possível
   check-in remoto.
2. **Visita não registrada**: paradas do veículo ≥15 min num raio de 300 m de um POSTO
   sem checkpoint correspondente → aparece no resumo como "parada em posto sem registro".
3. **Resumo por inspetor** (endpoint já existente `/rondas/gestao/resumo-inspetores`)
   ganha: km rodados, nº de paradas, % de check-ins com veículo no local, paradas
   não registradas.
4. **Timeline unificada** no modal de gestão: trips/stops do veículo intercalados com os
   checkpoints, sobre o link de mapa já existente.
5. **Alertas no SINO interno** (regra da casa — nada de Telegram): uso do veículo fora de
   janela (noite/fim de semana sem ronda ativa), veículo parado em endereço desconhecido
   por >2 h em horário comercial, check-in sem veículo próximo.
6. **Briefing 07:30**: linha por veículo (km de ontem, paradas, correlação com visitas).

## Enquadramento legal (LGPD/trabalhista)
- Rastrear o **veículo da empresa** é legítimo interesse — lícito e consolidado.
- Exigências: política escrita + ciência assinada dos condutores (transparência LGPD);
  retenção de posições limitada (90 dias); acesso restrito (Jordan/Pyetra).
- NÃO rastrear celular pessoal; a pessoa fora do veículo não é monitorada.
- PJ: continua controle por agenda/entregável — o rastreador audita o ATIVO da empresa.

## O que o Jordan precisa providenciar (F0)
| item | referência de custo |
|---|---|
| 2 rastreadores GT06/J16 (carro: GT06N; moto: versão à prova d'água) | R$120–250 cada |
| 2 chips M2M (Arqia/Links/Vivo M2M — dados ~10 MB/mês bastam) | R$15–30/mês cada |
| Instalação (eletricista automotivo, corte de ignição opcional) | R$80–150/veículo |
| Placa/apelido de cada veículo + quem anda com cada um | — |

Custo recorrente total ≈ **R$30–60/mês** (só os chips). Software: R$0.

## Fases de implementação (após F0)
- **F1** (1 sessão): container Traccar + nginx + database + cadastro dos 2 devices +
  tabelas frota_veiculos/frota_atribuicoes + tela simples de frota (posição atual no mapa).
- **F2** (1 sessão): correlação com checkpoints (flag veiculo_no_local, paradas sem
  registro), resumo-inspetores estendido, timeline unificada no modal.
- **F3** (curta): alertas no sino + seção no briefing.

Gate de segurança: porta 5023 exposta só para o APN dos chips (ou com senha de device);
web do Traccar atrás do nginx com auth; token de API do Traccar no .env do backend.

Status: DESENHO aprovado?→ aguardando F0 (hardware) do Jordan para iniciar F1.
