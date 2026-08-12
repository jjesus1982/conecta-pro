import { describe, it, expect } from 'vitest';
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatCNPJ,
  formatCPF,
  formatPhone,
  truncate,
  getInitials,
} from '../utils';

describe('formatCurrency', () => {
  it('formata valor inteiro', () => {
    const result = formatCurrency(1000);
    expect(result).toMatch(/1\.000/);
  });

  it('formata valor decimal', () => {
    const result = formatCurrency(1234.56);
    expect(result).toMatch(/1\.234/);
  });

  it('formata zero', () => {
    const result = formatCurrency(0);
    expect(result).toMatch(/0/);
  });

  it('inclui símbolo de moeda BRL', () => {
    const result = formatCurrency(100);
    expect(result).toMatch(/R\$|BRL/);
  });

  it('formata valores negativos', () => {
    const result = formatCurrency(-500);
    expect(result).toMatch(/500/);
  });
});

describe('formatDate', () => {
  it('formata string de data para pt-BR', () => {
    const result = formatDate('2024-01-15');
    expect(result).toMatch(/15\/01\/2024/);
  });

  it('formata objeto Date', () => {
    const date = new Date(2024, 0, 15); // Jan 15, 2024
    const result = formatDate(date);
    expect(result).toMatch(/15\/01\/2024/);
  });

  it('retorna data no formato dd/mm/yyyy', () => {
    const result = formatDate('2024-12-31');
    expect(result).toMatch(/31\/12\/2024/);
  });

  it('formata data de início do ano', () => {
    const result = formatDate('2024-01-01');
    expect(result).toMatch(/01\/01\/2024/);
  });
});

describe('formatDateTime', () => {
  it('formata string com data e hora', () => {
    const result = formatDateTime('2024-01-15T10:30:00');
    expect(result).toMatch(/15\/01\/2024/);
    expect(result).toMatch(/10:30/);
  });

  it('formata objeto Date com hora', () => {
    const date = new Date(2024, 0, 15, 10, 30);
    const result = formatDateTime(date);
    expect(result).toMatch(/15\/01\/2024/);
  });

  it('retorna string não vazia', () => {
    const result = formatDateTime('2024-06-01T00:00:00');
    expect(result.length).toBeGreaterThan(0);
  });
});

describe('formatCNPJ', () => {
  it('formata CNPJ sem formatação', () => {
    expect(formatCNPJ('11222333000181')).toBe('11.222.333/0001-81');
  });

  it('formata CNPJ com formatação existente (normaliza)', () => {
    // Remove non-digits first then formats
    expect(formatCNPJ('11.222.333/0001-81')).toBe('11.222.333/0001-81');
  });

  it('formata CNPJ com zeros', () => {
    expect(formatCNPJ('00000000000000')).toBe('00.000.000/0000-00');
  });

  it('retorna string parcialmente formatada para CNPJ incompleto', () => {
    const result = formatCNPJ('112223330001');
    // Does not match full pattern, returns cleaned or partial
    expect(typeof result).toBe('string');
  });
});

describe('formatCPF', () => {
  it('formata CPF sem formatação', () => {
    expect(formatCPF('12345678901')).toBe('123.456.789-01');
  });

  it('formata CPF com formatação existente (normaliza)', () => {
    expect(formatCPF('123.456.789-01')).toBe('123.456.789-01');
  });

  it('formata CPF com zeros', () => {
    expect(formatCPF('00000000000')).toBe('000.000.000-00');
  });

  it('retorna string para CPF incompleto (sem formatação aplicada)', () => {
    const result = formatCPF('123');
    expect(typeof result).toBe('string');
  });
});

describe('formatPhone', () => {
  it('formata celular com 11 dígitos', () => {
    expect(formatPhone('11987654321')).toBe('(11) 98765-4321');
  });

  it('formata telefone fixo com 10 dígitos', () => {
    expect(formatPhone('1134567890')).toBe('(11) 3456-7890');
  });

  it('remove formatação e reformata celular', () => {
    expect(formatPhone('(11) 98765-4321')).toBe('(11) 98765-4321');
  });

  it('remove formatação e reformata fixo', () => {
    expect(formatPhone('(11) 3456-7890')).toBe('(11) 3456-7890');
  });

  it('retorna string limpa para número com dígitos insuficientes', () => {
    const result = formatPhone('1234');
    expect(typeof result).toBe('string');
  });

  it('formata celular de São Paulo', () => {
    expect(formatPhone('11912345678')).toBe('(11) 91234-5678');
  });
});

describe('truncate', () => {
  it('trunca texto maior que o limite', () => {
    expect(truncate('Hello World', 5)).toBe('Hello...');
  });

  it('não trunca texto menor que o limite', () => {
    expect(truncate('Hello', 10)).toBe('Hello');
  });

  it('não trunca texto com tamanho exato ao limite', () => {
    expect(truncate('Hello', 5)).toBe('Hello');
  });

  it('trunca para zero caracteres', () => {
    expect(truncate('Hello', 0)).toBe('...');
  });

  it('retorna string vazia para input vazio', () => {
    expect(truncate('', 10)).toBe('');
  });

  it('trunca string longa', () => {
    const long = 'a'.repeat(100);
    const result = truncate(long, 10);
    expect(result).toBe('aaaaaaaaaa...');
  });
});

describe('getInitials', () => {
  it('retorna iniciais de nome simples', () => {
    expect(getInitials('João Silva')).toBe('JS');
  });

  it('retorna iniciais de nome único', () => {
    expect(getInitials('João')).toBe('J');
  });

  it('limita a 2 iniciais para nomes com mais palavras', () => {
    expect(getInitials('João da Silva Santos')).toBe('JD');
  });

  it('converte para maiúsculas', () => {
    expect(getInitials('alice bob')).toBe('AB');
  });

  it('filtra palavras sem caracteres', () => {
    expect(getInitials('João  Silva')).toBe('JS');
  });

  it('retorna string vazia para string vazia', () => {
    expect(getInitials('')).toBe('');
  });

  it('retorna inicial de nome com três palavras', () => {
    expect(getInitials('Maria Ana Costa')).toBe('MA');
  });
});
