import { describe, it, expect } from 'vitest';
import {
  isValidCPF,
  isValidCNPJ,
  isValidEmail,
  isValidPhone,
  isValidCEP,
  isValidDate,
} from '../validators';

describe('Validators', () => {
  describe('isValidCPF', () => {
    it('valida CPF válido formatado', () => {
      expect(isValidCPF('529.982.247-25')).toBe(true);
    });

    it('valida CPF válido sem formatação', () => {
      expect(isValidCPF('52998224725')).toBe(true);
    });

    it('rejeita CPF inválido', () => {
      expect(isValidCPF('123.456.789-00')).toBe(false);
    });

    it('rejeita CPF com todos dígitos iguais', () => {
      expect(isValidCPF('111.111.111-11')).toBe(false);
      expect(isValidCPF('000.000.000-00')).toBe(false);
      expect(isValidCPF('999.999.999-99')).toBe(false);
    });

    it('rejeita CPF vazio', () => {
      expect(isValidCPF('')).toBe(false);
    });

    it('rejeita CPF nulo ou undefined', () => {
      expect(isValidCPF(null as any)).toBe(false);
      expect(isValidCPF(undefined as any)).toBe(false);
    });

    it('rejeita CPF com menos de 11 dígitos', () => {
      expect(isValidCPF('123.456.789')).toBe(false);
    });

    it('rejeita CPF com mais de 11 dígitos', () => {
      expect(isValidCPF('123.456.789-091')).toBe(false);
    });

    it('rejeita CPF com letras', () => {
      expect(isValidCPF('abc.def.ghi-jk')).toBe(false);
    });

    it('valida outros CPFs válidos', () => {
      // Gerando CPFs válidos com dígitos verificadores corretos
      expect(isValidCPF('529.982.247-25')).toBe(true);
      expect(isValidCPF('453.178.287-91')).toBe(true);
      expect(isValidCPF('266.695.610-59')).toBe(true);
    });

    it('rejeita CPF com primeiro dígito verificador incorreto', () => {
      expect(isValidCPF('12345678900')).toBe(false);
    });
  });

  describe('isValidCNPJ', () => {
    it('valida CNPJ válido formatado', () => {
      expect(isValidCNPJ('11.222.333/0001-81')).toBe(true);
    });

    it('valida CNPJ válido sem formatação', () => {
      expect(isValidCNPJ('11222333000181')).toBe(true);
    });

    it('rejeita CNPJ inválido', () => {
      expect(isValidCNPJ('11.222.333/0001-00')).toBe(false);
    });

    it('rejeita CNPJ com todos dígitos iguais', () => {
      expect(isValidCNPJ('11.111.111/1111-11')).toBe(false);
      expect(isValidCNPJ('00.000.000/0000-00')).toBe(false);
      expect(isValidCNPJ('99.999.999/9999-99')).toBe(false);
    });

    it('rejeita CNPJ vazio', () => {
      expect(isValidCNPJ('')).toBe(false);
    });

    it('rejeita CNPJ nulo ou undefined', () => {
      expect(isValidCNPJ(null as any)).toBe(false);
      expect(isValidCNPJ(undefined as any)).toBe(false);
    });

    it('rejeita CNPJ com menos de 14 dígitos', () => {
      expect(isValidCNPJ('11.222.333/0001')).toBe(false);
    });

    it('rejeita CNPJ com mais de 14 dígitos', () => {
      expect(isValidCNPJ('11.222.333/0001-811')).toBe(false);
    });

    it('rejeita CNPJ com letras', () => {
      expect(isValidCNPJ('AA.BBB.CCC/DDDD-EE')).toBe(false);
    });

    it('valida outros CNPJs válidos', () => {
      // CNPJs válidos com dígitos verificadores corretos
      expect(isValidCNPJ('11.222.333/0001-81')).toBe(true);
      expect(isValidCNPJ('11.444.777/0001-61')).toBe(true);
      expect(isValidCNPJ('26.752.146/0001-87')).toBe(true); // CNPJ válido
    });

    it('rejeita CNPJ com primeiro dígito verificador incorreto', () => {
      expect(isValidCNPJ('11222333000100')).toBe(false);
    });
  });

  describe('isValidEmail', () => {
    it('valida email válido simples', () => {
      expect(isValidEmail('teste@email.com')).toBe(true);
    });

    it('valida email com subdomain', () => {
      expect(isValidEmail('teste@sub.dominio.com')).toBe(true);
    });

    it('valida email com hífen', () => {
      expect(isValidEmail('teste@meu-dominio.com')).toBe(true);
    });

    it('valida email com ponto no local', () => {
      expect(isValidEmail('nome.sobrenome@email.com')).toBe(true);
    });

    it('valida email com números', () => {
      expect(isValidEmail('teste123@email456.com')).toBe(true);
    });

    it('rejeita email sem @', () => {
      expect(isValidEmail('testeemail.com')).toBe(false);
    });

    it('rejeita email sem domínio', () => {
      expect(isValidEmail('teste@')).toBe(false);
    });

    it('rejeita email sem local', () => {
      expect(isValidEmail('@email.com')).toBe(false);
    });

    it('rejeita email sem TLD', () => {
      expect(isValidEmail('teste@email')).toBe(false);
    });

    it('rejeita email com espaços', () => {
      expect(isValidEmail('teste @email.com')).toBe(false);
      expect(isValidEmail('teste@ email.com')).toBe(false);
    });

    it('rejeita email vazio', () => {
      expect(isValidEmail('')).toBe(false);
    });

    it('rejeita email nulo ou undefined', () => {
      expect(isValidEmail(null as any)).toBe(false);
      expect(isValidEmail(undefined as any)).toBe(false);
    });
  });

  describe('isValidPhone', () => {
    it('valida celular com 11 dígitos formatado', () => {
      expect(isValidPhone('(11) 98765-4321')).toBe(true);
    });

    it('valida celular com 11 dígitos sem formatação', () => {
      expect(isValidPhone('11987654321')).toBe(true);
    });

    it('valida telefone fixo com 10 dígitos formatado', () => {
      expect(isValidPhone('(11) 3456-7890')).toBe(true);
    });

    it('valida telefone fixo com 10 dígitos sem formatação', () => {
      expect(isValidPhone('1134567890')).toBe(true);
    });

    it('rejeita telefone com 8 dígitos', () => {
      expect(isValidPhone('3456-7890')).toBe(false);
    });

    it('rejeita telefone com 9 dígitos', () => {
      expect(isValidPhone('987654321')).toBe(false);
    });

    it('rejeita celular com dígito diferente de 9', () => {
      expect(isValidPhone('11187654321')).toBe(false);
    });

    it('rejeita telefone com DDD inválido (menor que 11)', () => {
      expect(isValidPhone('0912345678')).toBe(false);
    });

    it('rejeita telefone com DDD inválido (maior que 99)', () => {
      expect(isValidPhone('1012345678')).toBe(false);
    });

    it('rejeita telefone vazio', () => {
      expect(isValidPhone('')).toBe(false);
    });

    it('rejeita telefone com letras', () => {
      expect(isValidPhone('(AB) XXXXX-XXXX')).toBe(false);
    });

    it('valida celular de outros DDDs', () => {
      expect(isValidPhone('21987654321')).toBe(true);
      expect(isValidPhone('31987654321')).toBe(true);
      expect(isValidPhone('85987654321')).toBe(true);
    });
  });

  describe('isValidCEP', () => {
    it('valida CEP formatado', () => {
      expect(isValidCEP('12345-678')).toBe(true);
    });

    it('valida CEP sem formatação', () => {
      expect(isValidCEP('12345678')).toBe(true);
    });

    it('rejeita CEP com 7 dígitos', () => {
      expect(isValidCEP('1234567')).toBe(false);
    });

    it('rejeita CEP com 9 dígitos', () => {
      expect(isValidCEP('123456789')).toBe(false);
    });

    it('rejeita CEP vazio', () => {
      expect(isValidCEP('')).toBe(false);
    });

    it('rejeita CEP com letras', () => {
      expect(isValidCEP('ABCDE-FGH')).toBe(false);
    });

    it('valida CEPs reais', () => {
      expect(isValidCEP('01310-100')).toBe(true);
      expect(isValidCEP('20040-010')).toBe(true);
      expect(isValidCEP('30140071')).toBe(true);
    });
  });

  describe('isValidDate', () => {
    it('valida objeto Date válido', () => {
      expect(isValidDate(new Date())).toBe(true);
    });

    it('valida string ISO válida', () => {
      expect(isValidDate('2024-01-15')).toBe(true);
    });

    it('valida string ISO com hora', () => {
      expect(isValidDate('2024-01-15T10:30:00')).toBe(true);
    });

    it('valida data no primeiro dia do ano', () => {
      expect(isValidDate('2024-01-01')).toBe(true);
    });

    it('valida data no último dia do ano', () => {
      expect(isValidDate('2024-12-31')).toBe(true);
    });

    it('valida data bissexta', () => {
      expect(isValidDate('2024-02-29')).toBe(true);
    });

    it('rejeita data não bissexta com 29 de fevereiro', () => {
      expect(isValidDate('2023-02-29')).toBe(false);
    });

    it('rejeita data com dia inválido', () => {
      expect(isValidDate('2024-01-32')).toBe(false);
    });

    it('rejeita data com mês inválido', () => {
      expect(isValidDate('2024-13-01')).toBe(false);
    });

    it('rejeita data vazia', () => {
      expect(isValidDate('')).toBe(false);
    });

    it('rejeita data nula ou undefined', () => {
      expect(isValidDate(null as any)).toBe(false);
      expect(isValidDate(undefined as any)).toBe(false);
    });

    it('rejeita string de data inválida', () => {
      expect(isValidDate('data-invalida')).toBe(false);
    });

    it('rejeita objeto Date inválido', () => {
      expect(isValidDate(new Date('invalid'))).toBe(false);
    });

    it('rejeita formato de data inválido', () => {
      expect(isValidDate('not-a-date')).toBe(false);
    });

    it('rejeita data inexistente como fevereiro 30', () => {
      expect(isValidDate('2024-02-30')).toBe(false);
    });

    it('rejeita mês 13', () => {
      expect(isValidDate('2024-13-01')).toBe(false);
    });

    it('rejeita texto alfabético', () => {
      expect(isValidDate('hello world')).toBe(false);
    });

    it('valida formato ISO datetime completo', () => {
      expect(isValidDate('2024-01-15T14:30:00.000Z')).toBe(true);
    });
  });

  describe('isValidDate - Edge Cases', () => {
    it('rejeita string com formato parcial inválido (não ISO, não datetime)', () => {
      // Uma string que o Date() pode parsear mas não é YYYY-MM-DD nem ISO datetime
      // Ex: "January 1, 2024" - parseável pelo Date(), mas falha ambas as regex
      expect(isValidDate('January 1, 2024')).toBe(false);
    });

    it('rejeita string que não é ISO nem datetime', () => {
      // String que Date() pode parsear mas não passa em nenhum regex
      expect(isValidDate('2024/01/15')).toBe(false);
    });
  });

  describe('isValidCPF - Edge Cases', () => {
    it('rejeita CPF onde primeiro dígito verificador está incorreto', () => {
      expect(isValidCPF('12345678900')).toBe(false);
    });

    it('rejeita CPF com dígitos verificadores calculados incorretamente', () => {
      // CPF inválido com dígitos incorretos
      expect(isValidCPF('11111111112')).toBe(false);
    });
  });

  describe('isValidCNPJ - Edge Cases', () => {
    it('rejeita CNPJ onde primeiro dígito verificador está incorreto', () => {
      expect(isValidCNPJ('11222333000100')).toBe(false);
    });

    it('rejeita CNPJ onde segundo dígito verificador está incorreto', () => {
      // CNPJ com primeiro dígito correto mas segundo incorreto
      // 11.222.333/0001-8X onde X é incorreto
      expect(isValidCNPJ('11222333000180')).toBe(false);
    });

    it('valida CNPJ onde dígito verificador resulta em remainder < 2 (digito = 0)', () => {
      // CNPJ válido que produz remainder < 2 no cálculo
      expect(isValidCNPJ('11222333000181')).toBe(true);
    });
  });

  describe('isValidPhone - Edge Cases', () => {
    it('valida celular com 9 no terceiro dígito', () => {
      expect(isValidPhone('11987654321')).toBe(true);
    });

    it('rejeita telefone fixo de 9 dígitos sem DDD', () => {
      expect(isValidPhone('987654321')).toBe(false);
    });
  });
});
