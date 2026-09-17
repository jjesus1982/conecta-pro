import { describe, it, expect, beforeEach } from 'vitest';
import {
  destinoSeguro,
  destinoPosLogin,
  guardarDestino,
  resgatarDestino,
} from '../destino-pos-login';

describe('destinoSeguro — fronteira de confiança', () => {
  it('aceita caminho interno', () => {
    expect(destinoSeguro('/modulos/meu-espaco?t=assinar')).toBe('/modulos/meu-espaco?t=assinar');
  });

  it('recusa redirect aberto', () => {
    for (const mau of ['//evil.com', '/\\evil.com', 'https://evil.com', 'evil.com', '']) {
      expect(destinoSeguro(mau)).toBeNull();
    }
  });

  it('recusa nulo e indefinido', () => {
    expect(destinoSeguro(null)).toBeNull();
    expect(destinoSeguro(undefined)).toBeNull();
  });
});

describe('destinoPosLogin — a regra que quebrou em 17/09', () => {
  it('o link de assinatura vence o padrão, seja qual for o papel', () => {
    const link = '/modulos/meu-espaco?t=assinar';
    expect(destinoPosLogin(link, 'funcionario')).toBe(link);
    expect(destinoPosLogin(link, 'admin')).toBe(link);
  });

  it('funcionário sem destino NÃO cai no painel da empresa', () => {
    expect(destinoPosLogin(null, 'funcionario')).toBe('/modulos/meu-espaco');
  });

  it('admin sem destino vai para o redesign', () => {
    expect(destinoPosLogin(null, 'admin')).toBe('/redesign');
    expect(destinoPosLogin(null, undefined)).toBe('/redesign');
  });

  it('redirect aberto não sequestra o login', () => {
    expect(destinoPosLogin('//evil.com', 'funcionario')).toBe('/modulos/meu-espaco');
    expect(destinoPosLogin('https://evil.com', 'admin')).toBe('/redesign');
  });
});

describe('guardar/resgatar — a volta do Google', () => {
  beforeEach(() => sessionStorage.clear());

  it('o destino atravessa o round-trip do OAuth', () => {
    guardarDestino('/modulos/meu-espaco?t=assinar');
    expect(resgatarDestino()).toBe('/modulos/meu-espaco?t=assinar');
  });

  it('é consumido: não vaza para o login seguinte', () => {
    guardarDestino('/modulos/meu-espaco?t=assinar');
    resgatarDestino();
    expect(resgatarDestino()).toBeNull();
  });

  it('não guarda redirect aberto', () => {
    guardarDestino('//evil.com');
    expect(resgatarDestino()).toBeNull();
  });

  it('login sem destino limpa o que sobrou do anterior', () => {
    guardarDestino('/modulos/meu-espaco?t=assinar');
    guardarDestino(null);
    expect(resgatarDestino()).toBeNull();
  });
});
