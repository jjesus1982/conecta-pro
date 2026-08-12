import { describe, it, expect } from 'vitest';
import {
  applyCPFMask,
  applyCNPJMask,
  applyPhoneMask,
  applyCEPMask,
  applyCurrencyMask,
  removeMask,
  currencyToNumber,
} from '../masks';

describe('Masks', () => {
  describe('removeMask', () => {
    it('remove todos os caracteres não numéricos', () => {
      expect(removeMask('123.456.789-09')).toBe('12345678909');
    });

    it('retorna string vazia para input vazio', () => {
      expect(removeMask('')).toBe('');
    });

    it('retorna string vazia para input nulo', () => {
      expect(removeMask(null as any)).toBe('');
    });

    it('mantém apenas números em string mista', () => {
      expect(removeMask('abc123def456')).toBe('123456');
    });

    it('retorna string vazia se não houver números', () => {
      expect(removeMask('abc-def')).toBe('');
    });
  });

  describe('applyCPFMask', () => {
    it('aplica máscara em CPF sem formatação', () => {
      expect(applyCPFMask('12345678909')).toBe('123.456.789-09');
    });

    it('aplica máscara em CPF parcial', () => {
      expect(applyCPFMask('123456')).toBe('123.456');
    });

    it('aplica máscara em CPF muito parcial', () => {
      expect(applyCPFMask('123')).toBe('123');
    });

    it('mantém máscara já aplicada', () => {
      expect(applyCPFMask('123.456.789-09')).toBe('123.456.789-09');
    });

    it('remove caracteres além do 11º dígito', () => {
      expect(applyCPFMask('1234567890912')).toBe('123.456.789-09');
    });

    it('retorna string vazia para input vazio', () => {
      expect(applyCPFMask('')).toBe('');
    });

    it('ignora caracteres não numéricos', () => {
      expect(applyCPFMask('abc123def456ghi789jkl09')).toBe('123.456.789-09');
    });
  });

  describe('applyCNPJMask', () => {
    it('aplica máscara em CNPJ sem formatação', () => {
      expect(applyCNPJMask('11222333000181')).toBe('11.222.333/0001-81');
    });

    it('aplica máscara em CNPJ parcial', () => {
      expect(applyCNPJMask('11222333')).toBe('11.222.333');
    });

    it('aplica máscara em CNPJ muito parcial', () => {
      expect(applyCNPJMask('11')).toBe('11');
    });

    it('mantém máscara já aplicada', () => {
      expect(applyCNPJMask('11.222.333/0001-81')).toBe('11.222.333/0001-81');
    });

    it('remove caracteres além do 14º dígito', () => {
      expect(applyCNPJMask('1122233300018112')).toBe('11.222.333/0001-81');
    });

    it('retorna string vazia para input vazio', () => {
      expect(applyCNPJMask('')).toBe('');
    });

    it('ignora caracteres não numéricos', () => {
      expect(applyCNPJMask('ab11cd222e333f0001g81')).toBe('11.222.333/0001-81');
    });
  });

  describe('applyPhoneMask', () => {
    it('aplica máscara em celular (11 dígitos)', () => {
      expect(applyPhoneMask('11987654321')).toBe('(11) 98765-4321');
    });

    it('aplica máscara em telefone fixo (10 dígitos)', () => {
      expect(applyPhoneMask('1134567890')).toBe('(11) 3456-7890');
    });

    it('aplica máscara parcial para celular', () => {
      // Para celular parcial (menos de 11 dígitos), usa formatação de fixo
      expect(applyPhoneMask('1198765')).toBe('(11) 9876-5');
    });

    it('aplica máscara parcial para fixo', () => {
      expect(applyPhoneMask('113456')).toBe('(11) 3456');
    });

    it('mantém máscara já aplicada', () => {
      expect(applyPhoneMask('(11) 98765-4321')).toBe('(11) 98765-4321');
    });

    it('remove caracteres além do 11º dígito', () => {
      expect(applyPhoneMask('1198765432112')).toBe('(11) 98765-4321');
    });

    it('retorna string vazia para input vazio', () => {
      expect(applyPhoneMask('')).toBe('');
    });

    it('ignora caracteres não numéricos', () => {
      expect(applyPhoneMask('(11) 98765-4321')).toBe('(11) 98765-4321');
    });
  });

  describe('applyCEPMask', () => {
    it('aplica máscara em CEP completo', () => {
      expect(applyCEPMask('12345678')).toBe('12345-678');
    });

    it('aplica máscara em CEP parcial', () => {
      expect(applyCEPMask('12345')).toBe('12345');
    });

    it('mantém máscara já aplicada', () => {
      expect(applyCEPMask('12345-678')).toBe('12345-678');
    });

    it('remove caracteres além do 8º dígito', () => {
      expect(applyCEPMask('1234567890')).toBe('12345-678');
    });

    it('retorna string vazia para input vazio', () => {
      expect(applyCEPMask('')).toBe('');
    });

    it('ignora caracteres não numéricos', () => {
      expect(applyCEPMask('12.345-678')).toBe('12345-678');
    });
  });

  describe('applyCurrencyMask', () => {
    it('formata número inteiro como moeda', () => {
      expect(applyCurrencyMask(100)).toBe('R$\u00a0100,00');
    });

    it('formata número com decimais como moeda', () => {
      expect(applyCurrencyMask(1234.56)).toBe('R$\u00a01.234,56');
    });

    it('formata string numérica como moeda', () => {
      expect(applyCurrencyMask('123456')).toBe('R$\u00a01.234,56');
    });

    it('formata zero como moeda', () => {
      expect(applyCurrencyMask(0)).toBe('R$\u00a00,00');
    });

    it('formata centavos corretamente', () => {
      expect(applyCurrencyMask('99')).toBe('R$\u00a00,99');
    });

    it('formata valores muito grandes', () => {
      expect(applyCurrencyMask(1000000)).toBe('R$\u00a01.000.000,00');
    });

    it('retorna string vazia para input vazio', () => {
      expect(applyCurrencyMask('')).toBe('');
    });

    it('retorna string vazia para input nulo', () => {
      expect(applyCurrencyMask(null as any)).toBe('');
    });

    it('retorna string vazia para NaN', () => {
      expect(applyCurrencyMask('abc')).toBe('');
    });
  });

  describe('currencyToNumber', () => {
    it('converte valor formatado para número', () => {
      expect(currencyToNumber('R$ 1.234,56')).toBe(1234.56);
    });

    it('converte valor sem símbolo', () => {
      expect(currencyToNumber('1.234,56')).toBe(1234.56);
    });

    it('converte valor sem separador de milhar', () => {
      expect(currencyToNumber('R$ 100,00')).toBe(100);
    });

    it('converte valor inteiro', () => {
      expect(currencyToNumber('R$ 100,00')).toBe(100);
    });

    it('converte centavos', () => {
      expect(currencyToNumber('R$ 0,99')).toBe(0.99);
    });

    it('retorna 0 para string vazia', () => {
      expect(currencyToNumber('')).toBe(0);
    });

    it('retorna 0 para string inválida', () => {
      expect(currencyToNumber('abc')).toBe(0);
    });

    it('converte valor negativo', () => {
      expect(currencyToNumber('-R$ 100,00')).toBe(-100);
    });
  });
});
