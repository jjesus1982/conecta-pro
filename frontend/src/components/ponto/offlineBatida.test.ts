/**
 * 502 não é recusa — a batida que o nginx engoliu tem de ir para a fila do aparelho.
 *
 * 🔴 MEDIDO EM 28/09/2026. Das 13:00 às 13:02 o backend ficou fora do ar e o nginx devolveu
 * 502 a 205 requisições; 72 delas eram batidas de ponto, de 4 pessoas. As mesmas quatro
 * disseram "apertei e nada aconteceu": Telma, Livia, Daniel e Edilene. Era a volta do almoço,
 * o minuto de maior movimento do dia.
 *
 * A regra dizia `if (err?.response?.status) return false` — "o servidor respondeu, então não é
 * falta de sinal". Vale para 4xx e para 5xx do aplicativo. **Não vale para 502/503**, que vêm do
 * NGINX e significam que o aplicativo nunca viu a batida. Recusar ali apaga um fato que
 * aconteceu de verdade.
 */

import { describe, expect, it } from 'vitest';

import { ehFalhaDeRede } from './offlineBatida';

const comStatus = (status: number) => ({ response: { status }, message: `HTTP ${status}` });

describe('ehFalhaDeRede', () => {
  it('502 e 503 contam como falta de sinal — o aplicativo não viu a batida', () => {
    // Foi o estado de 28/09: 72 batidas 502 perdidas por serem lidas como recusa.
    expect(ehFalhaDeRede(comStatus(502))).toBe(true);
    expect(ehFalhaDeRede(comStatus(503))).toBe(true);
  });

  it('504 NÃO conta — o aplicativo pode ter gravado, e guardar duplicaria o ponto', () => {
    expect(ehFalhaDeRede(comStatus(504))).toBe(false);
  });

  it('recusa do aplicativo continua sendo recusa — conserto não pode virar contorno de gate', () => {
    // O rosto que não bateu, a geofence fora do posto e o 500 do próprio app são DECISÃO.
    // Mandar para a fila offline seria driblar a trava, que é pior que o defeito original.
    for (const st of [400, 401, 403, 409, 422, 500]) {
      expect(ehFalhaDeRede(comStatus(st))).toBe(false);
    }
  });

  it('sem resposta nenhuma continua sendo falta de sinal (o 4G da guarita às 06:00)', () => {
    expect(ehFalhaDeRede({ code: 'ERR_NETWORK', message: 'Network Error' })).toBe(true);
    expect(ehFalhaDeRede(new Error('timeout of 0ms exceeded'))).toBe(true);
    expect(ehFalhaDeRede(undefined)).toBe(true);
  });
});
