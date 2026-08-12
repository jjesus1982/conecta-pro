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
  // NBSP (non-breaking space) é usado pelo Intl.NumberFormat entre R$ e o valor
  const NBSP = '\xa0';

  it('deve formatar valor em reais', () => {
    expect(formatCurrency(1234.56)).toBe(`R$${NBSP}1.234,56`);
  });

  it('deve formatar zero', () => {
    expect(formatCurrency(0)).toBe(`R$${NBSP}0,00`);
  });

  it('deve formatar valores negativos', () => {
    expect(formatCurrency(-100)).toBe(`-R$${NBSP}100,00`);
  });

  it('deve formatar valores grandes', () => {
    expect(formatCurrency(1000000)).toBe(`R$${NBSP}1.000.000,00`);
  });

  it('deve formatar valores decimais corretamente', () => {
    expect(formatCurrency(0.99)).toBe(`R$${NBSP}0,99`);
  });

  it('deve formatar valores inteiros', () => {
    expect(formatCurrency(100)).toBe(`R$${NBSP}100,00`);
  });
});

describe('formatDate', () => {
  it('deve formatar data do tipo Date', () => {
    const date = new Date(2024, 0, 15); // 15/01/2024
    expect(formatDate(date)).toBe('15/01/2024');
  });

  it('deve formatar data string ISO', () => {
    expect(formatDate('2024-01-15')).toBe('15/01/2024');
  });

  it('deve formatar data string com hora', () => {
    expect(formatDate('2024-01-15T10:30:00')).toBe('15/01/2024');
  });

  it('deve formatar data no final do ano', () => {
    expect(formatDate('2024-12-31')).toBe('31/12/2024');
  });

  it('deve formatar data no início do ano', () => {
    expect(formatDate('2024-01-01')).toBe('01/01/2024');
  });
});

describe('formatDateTime', () => {
  it('deve formatar data e hora do tipo Date', () => {
    const date = new Date(2024, 0, 15, 10, 30);
    const result = formatDateTime(date);
    expect(result).toContain('15/01/2024');
    expect(result).toContain('10:30');
  });

  it('deve formatar data e hora string ISO', () => {
    const result = formatDateTime('2024-01-15T14:45:00');
    expect(result).toContain('15/01/2024');
    expect(result).toContain('14:45');
  });

  it('deve formatar meia-noite corretamente', () => {
    const result = formatDateTime('2024-01-15T00:00:00');
    expect(result).toContain('15/01/2024');
    expect(result).toContain('00:00');
  });
});

describe('formatCNPJ', () => {
  it('deve formatar CNPJ válido sem máscara', () => {
    expect(formatCNPJ('11222333000181')).toBe('11.222.333/0001-81');
  });

  it('deve formatar CNPJ com caracteres especiais', () => {
    expect(formatCNPJ('11.222.333/0001-81')).toBe('11.222.333/0001-81');
  });

  it('deve formatar CNPJ com espaços', () => {
    expect(formatCNPJ('11 222 333 0001 81')).toBe('11.222.333/0001-81');
  });

  it('deve retornar string vazia para CNPJ vazio', () => {
    expect(formatCNPJ('')).toBe('');
  });

  it('deve retornar valor sem formatação para CNPJ incompleto', () => {
    expect(formatCNPJ('11222333')).toBe('11222333');
  });
});

describe('formatCPF', () => {
  it('deve formatar CPF válido sem máscara', () => {
    expect(formatCPF('12345678901')).toBe('123.456.789-01');
  });

  it('deve formatar CPF com caracteres especiais', () => {
    expect(formatCPF('123.456.789-01')).toBe('123.456.789-01');
  });

  it('deve formatar CPF com espaços', () => {
    expect(formatCPF('123 456 789 01')).toBe('123.456.789-01');
  });

  it('deve retornar string vazia para CPF vazio', () => {
    expect(formatCPF('')).toBe('');
  });

  it('deve retornar valor sem formatação para CPF incompleto', () => {
    expect(formatCPF('12345678')).toBe('12345678');
  });
});

describe('formatPhone', () => {
  it('deve formatar telefone celular com 11 dígitos', () => {
    expect(formatPhone('11987654321')).toBe('(11) 98765-4321');
  });

  it('deve formatar telefone fixo com 10 dígitos', () => {
    expect(formatPhone('1134567890')).toBe('(11) 3456-7890');
  });

  it('deve formatar telefone com caracteres especiais', () => {
    expect(formatPhone('(11) 98765-4321')).toBe('(11) 98765-4321');
  });

  it('deve formatar telefone com espaços', () => {
    expect(formatPhone('11 98765 4321')).toBe('(11) 98765-4321');
  });

  it('deve retornar string vazia para telefone vazio', () => {
    expect(formatPhone('')).toBe('');
  });

  it('deve retornar valor sem formatação para telefone incompleto', () => {
    expect(formatPhone('1198765')).toBe('1198765');
  });
});

describe('truncate', () => {
  it('deve truncar texto maior que o limite', () => {
    expect(truncate('Este é um texto longo', 10)).toBe('Este é um ...');
  });

  it('deve retornar texto completo se menor que o limite', () => {
    expect(truncate('Curto', 10)).toBe('Curto');
  });

  it('deve retornar texto completo se igual ao limite', () => {
    expect(truncate('Exatamente', 10)).toBe('Exatamente');
  });

  it('deve truncar no limite exato', () => {
    expect(truncate('Texto maior', 5)).toBe('Texto...');
  });

  it('deve retornar apenas reticências se limite for zero', () => {
    expect(truncate('Qualquer', 0)).toBe('...');
  });

  it('deve lidar com texto vazio', () => {
    expect(truncate('', 10)).toBe('');
  });
});

describe('getInitials', () => {
  it('deve retornar iniciais de nome completo', () => {
    expect(getInitials('João Silva')).toBe('JS');
  });

  it('deve retornar iniciais de três nomes', () => {
    expect(getInitials('Maria Oliveira Souza')).toBe('MO');
  });

  it('deve retornar iniciais de nome com sobrenome composto', () => {
    expect(getInitials('Ana Maria Silva')).toBe('AM');
  });

  it('deve retornar uma letra para nome único', () => {
    expect(getInitials('Pedro')).toBe('P');
  });

  it('deve retornar string vazia para nome vazio', () => {
    expect(getInitials('')).toBe('');
  });

  it('deve converter para maiúsculas', () => {
    expect(getInitials('joão silva')).toBe('JS');
  });

  it('deve ignorar espaços extras', () => {
    expect(getInitials('João  Silva')).toBe('JS');
  });
});
