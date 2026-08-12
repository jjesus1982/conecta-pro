import { describe, it, expect } from 'vitest';
import {
  parseDate,
  formatDateBR,
  formatDateISO,
  addDays,
  subDays,
  addMonths,
  subMonths,
  isWeekend,
  isHoliday,
  diffInDays,
  startOfMonth,
  endOfMonth,
  isSameDay,
  getDayOfWeekName,
  getMonthName,
} from '../date';

describe('Date Utils', () => {
  describe('parseDate', () => {
    it('faz parse de data ISO válida', () => {
      const result = parseDate('2024-01-15');
      expect(result).toBeInstanceOf(Date);
      expect(result?.getFullYear()).toBe(2024);
      expect(result?.getMonth()).toBe(0);
      expect(result?.getDate()).toBe(15);
    });

    it('faz parse de data brasileira válida', () => {
      const result = parseDate('15/01/2024');
      expect(result).toBeInstanceOf(Date);
      expect(result?.getFullYear()).toBe(2024);
      expect(result?.getMonth()).toBe(0);
      expect(result?.getDate()).toBe(15);
    });

    it('faz parse de data ISO completa', () => {
      const result = parseDate('2024-01-15T10:30:00');
      expect(result).toBeInstanceOf(Date);
      expect(result?.getFullYear()).toBe(2024);
    });

    it('retorna null para data inválida', () => {
      expect(parseDate('data-invalida')).toBeNull();
    });

    it('retorna null para string vazia', () => {
      expect(parseDate('')).toBeNull();
    });

    it('retorna null para data inexistente', () => {
      expect(parseDate('2024-02-30')).toBeNull();
    });

    it('retorna null para mês inválido', () => {
      expect(parseDate('2024-13-01')).toBeNull();
    });

    it('faz parse de data bissexta válida', () => {
      const result = parseDate('2024-02-29');
      expect(result).toBeInstanceOf(Date);
      expect(result?.getDate()).toBe(29);
    });

    it('retorna null para 29 de fevereiro em ano não bissexto', () => {
      expect(parseDate('2023-02-29')).toBeNull();
    });

    it('retorna null para data brasileira com dia inválido', () => {
      expect(parseDate('31/02/2024')).toBeNull();
    });

    it('retorna null para data brasileira inválida', () => {
      expect(parseDate('32/13/2024')).toBeNull();
    });

    it('retorna null para string alfabética', () => {
      expect(parseDate('abc')).toBeNull();
    });
  });

  describe('formatDateBR', () => {
    it('formata Date para padrão brasileiro', () => {
      const date = new Date(2024, 0, 15);
      expect(formatDateBR(date)).toBe('15/01/2024');
    });

    it('formata string ISO para padrão brasileiro', () => {
      expect(formatDateBR('2024-01-15')).toBe('15/01/2024');
    });

    it('formata string brasileira para padrão brasileiro', () => {
      expect(formatDateBR('15/01/2024')).toBe('15/01/2024');
    });

    it('retorna string vazia para data inválida', () => {
      expect(formatDateBR('invalid')).toBe('');
    });

    it('formata primeiro dia do ano', () => {
      expect(formatDateBR('2024-01-01')).toBe('01/01/2024');
    });

    it('formata último dia do ano', () => {
      expect(formatDateBR('2024-12-31')).toBe('31/12/2024');
    });
  });

  describe('formatDateISO', () => {
    it('formata Date para padrão ISO', () => {
      const date = new Date(2024, 0, 15);
      expect(formatDateISO(date)).toBe('2024-01-15');
    });

    it('formata string brasileira para padrão ISO', () => {
      expect(formatDateISO('15/01/2024')).toBe('2024-01-15');
    });

    it('mantém formato ISO se já estiver no padrão', () => {
      expect(formatDateISO('2024-01-15')).toBe('2024-01-15');
    });

    it('retorna string vazia para data inválida', () => {
      expect(formatDateISO('invalid')).toBe('');
    });
  });

  describe('addDays', () => {
    it('adiciona dias a uma data', () => {
      const result = addDays('2024-01-15', 5);
      expect(formatDateISO(result)).toBe('2024-01-20');
    });

    it('adiciona dias mudando de mês', () => {
      const result = addDays('2024-01-30', 5);
      expect(formatDateISO(result)).toBe('2024-02-04');
    });

    it('adiciona zero dias', () => {
      const result = addDays('2024-01-15', 0);
      expect(formatDateISO(result)).toBe('2024-01-15');
    });

    it('aceita objeto Date', () => {
      const date = new Date(2024, 0, 15);
      const result = addDays(date, 10);
      expect(formatDateISO(result)).toBe('2024-01-25');
    });

    it('lança erro para data inválida', () => {
      expect(() => addDays('invalid', 5)).toThrow('Data inválida');
    });
  });

  describe('subDays', () => {
    it('subtrai dias de uma data', () => {
      const result = subDays('2024-01-15', 5);
      expect(formatDateISO(result)).toBe('2024-01-10');
    });

    it('subtrai dias mudando de mês', () => {
      const result = subDays('2024-02-05', 10);
      expect(formatDateISO(result)).toBe('2024-01-26');
    });

    it('subtrai zero dias', () => {
      const result = subDays('2024-01-15', 0);
      expect(formatDateISO(result)).toBe('2024-01-15');
    });
  });

  describe('addMonths', () => {
    it('adiciona meses a uma data', () => {
      const result = addMonths('2024-01-15', 2);
      expect(formatDateISO(result)).toBe('2024-03-15');
    });

    it('adiciona meses mudando de ano', () => {
      const result = addMonths('2024-10-15', 5);
      expect(formatDateISO(result)).toBe('2025-03-15');
    });

    it('ajusta dia quando mês destino tem menos dias', () => {
      const result = addMonths('2024-01-31', 1);
      // Fevereiro 2024 não tem dia 31 (só até 29), então overflow para março
      // Comportamento padrão do JavaScript Date
      expect(result.getMonth()).toBe(2); // Março = mês 2 (0-indexed)
      expect(result.getDate()).toBe(2); // 31 de jan + 1 mês = 2 de mar (overflow)
    });

    it('lança erro para string inválida', () => {
      expect(() => addMonths('not-a-date', 1)).toThrow('Data inválida');
    });
  });

  describe('subMonths', () => {
    it('subtrai meses de uma data', () => {
      const result = subMonths('2024-03-15', 2);
      expect(formatDateISO(result)).toBe('2024-01-15');
    });

    it('subtrai meses mudando de ano', () => {
      const result = subMonths('2024-01-15', 3);
      expect(formatDateISO(result)).toBe('2023-10-15');
    });
  });

  describe('isWeekend', () => {
    it('identifica domingo', () => {
      expect(isWeekend('2024-01-07')).toBe(true); // Domingo
    });

    it('identifica sábado', () => {
      expect(isWeekend('2024-01-06')).toBe(true); // Sábado
    });

    it('identifica segunda-feira como dia útil', () => {
      expect(isWeekend('2024-01-08')).toBe(false);
    });

    it('identifica sexta-feira como dia útil', () => {
      expect(isWeekend('2024-01-05')).toBe(false);
    });

    it('retorna false para data inválida', () => {
      expect(isWeekend('invalid')).toBe(false);
    });

    it('aceita objeto Date', () => {
      const saturday = new Date(2024, 0, 6);
      expect(isWeekend(saturday)).toBe(true);
    });
  });

  describe('isHoliday', () => {
    it('identifica Ano Novo', () => {
      expect(isHoliday('2024-01-01')).toBe(true);
    });

    it('identifica Tiradentes', () => {
      expect(isHoliday('2024-04-21')).toBe(true);
    });

    it('identifica Dia do Trabalho', () => {
      expect(isHoliday('2024-05-01')).toBe(true);
    });

    it('identifica Independência', () => {
      expect(isHoliday('2024-09-07')).toBe(true);
    });

    it('identifica Nossa Senhora Aparecida', () => {
      expect(isHoliday('2024-10-12')).toBe(true);
    });

    it('identifica Finados', () => {
      expect(isHoliday('2024-11-02')).toBe(true);
    });

    it('identifica Proclamação da República', () => {
      expect(isHoliday('2024-11-15')).toBe(true);
    });

    it('identifica Natal', () => {
      expect(isHoliday('2024-12-25')).toBe(true);
    });

    it('retorna false para dia comum', () => {
      expect(isHoliday('2024-01-15')).toBe(false);
    });

    it('retorna false para data inválida', () => {
      expect(isHoliday('invalid')).toBe(false);
    });
  });

  describe('diffInDays', () => {
    it('calcula diferença positiva', () => {
      expect(diffInDays('2024-01-01', '2024-01-10')).toBe(9);
    });

    it('calcula diferença negativa', () => {
      expect(diffInDays('2024-01-10', '2024-01-01')).toBe(-9);
    });

    it('retorna zero para mesma data', () => {
      expect(diffInDays('2024-01-15', '2024-01-15')).toBe(0);
    });

    it('calcula diferença entre anos', () => {
      expect(diffInDays('2023-12-31', '2024-01-01')).toBe(1);
    });

    it('retorna zero para data inválida', () => {
      expect(diffInDays('invalid', '2024-01-15')).toBe(0);
    });
  });

  describe('startOfMonth', () => {
    it('retorna primeiro dia do mês', () => {
      const result = startOfMonth('2024-01-15');
      expect(formatDateISO(result)).toBe('2024-01-01');
    });

    it('retorna primeiro dia quando já é o primeiro', () => {
      const result = startOfMonth('2024-01-01');
      expect(formatDateISO(result)).toBe('2024-01-01');
    });

    it('lança erro para data inválida', () => {
      expect(() => startOfMonth('invalid')).toThrow('Data inválida');
    });
  });

  describe('endOfMonth', () => {
    it('retorna último dia do mês', () => {
      const result = endOfMonth('2024-01-15');
      expect(formatDateISO(result)).toBe('2024-01-31');
    });

    it('retorna último dia de fevereiro em ano bissexto', () => {
      const result = endOfMonth('2024-02-15');
      expect(formatDateISO(result)).toBe('2024-02-29');
    });

    it('retorna último dia de fevereiro em ano não bissexto', () => {
      const result = endOfMonth('2023-02-15');
      expect(formatDateISO(result)).toBe('2023-02-28');
    });

    it('lança erro para data inválida', () => {
      expect(() => endOfMonth('invalid')).toThrow('Data inválida');
    });
  });

  describe('isSameDay', () => {
    it('retorna true para mesmo dia', () => {
      expect(isSameDay('2024-01-15', '2024-01-15')).toBe(true);
    });

    it('retorna false para dias diferentes', () => {
      expect(isSameDay('2024-01-15', '2024-01-16')).toBe(false);
    });

    it('retorna false para meses diferentes', () => {
      expect(isSameDay('2024-01-15', '2024-02-15')).toBe(false);
    });

    it('retorna false para anos diferentes', () => {
      expect(isSameDay('2024-01-15', '2023-01-15')).toBe(false);
    });

    it('retorna false para data inválida', () => {
      expect(isSameDay('invalid', '2024-01-15')).toBe(false);
    });
  });

  describe('getDayOfWeekName', () => {
    it('retorna nome completo do dia', () => {
      expect(getDayOfWeekName('2024-01-08')).toBe('Segunda-feira');
    });

    it('retorna nome curto quando solicitado', () => {
      expect(getDayOfWeekName('2024-01-08', true)).toBe('Seg');
    });

    it('retorna vazio para data inválida', () => {
      expect(getDayOfWeekName('invalid')).toBe('');
    });

    it('retorna Domingo para domingo', () => {
      expect(getDayOfWeekName('2024-01-07')).toBe('Domingo');
    });
  });

  describe('getMonthName', () => {
    it('retorna nome completo do mês', () => {
      expect(getMonthName('2024-01-15')).toBe('Janeiro');
    });

    it('retorna nome curto quando solicitado', () => {
      expect(getMonthName('2024-01-15', true)).toBe('Jan');
    });

    it('retorna vazio para data inválida', () => {
      expect(getMonthName('invalid')).toBe('');
    });

    it('retorna Dezembro para dezembro', () => {
      expect(getMonthName('2024-12-15')).toBe('Dezembro');
    });
  });

  describe('getDayOfWeekName - All Days', () => {
    it('retorna todos os dias da semana', () => {
      expect(getDayOfWeekName('2024-01-07')).toBe('Domingo');
      expect(getDayOfWeekName('2024-01-08')).toBe('Segunda-feira');
      expect(getDayOfWeekName('2024-01-09')).toBe('Terça-feira');
      expect(getDayOfWeekName('2024-01-10')).toBe('Quarta-feira');
      expect(getDayOfWeekName('2024-01-11')).toBe('Quinta-feira');
      expect(getDayOfWeekName('2024-01-12')).toBe('Sexta-feira');
      expect(getDayOfWeekName('2024-01-13')).toBe('Sábado');
    });
  });

  describe('getMonthName - All Months', () => {
    it('retorna todos os meses do ano', () => {
      expect(getMonthName('2024-01-15')).toBe('Janeiro');
      expect(getMonthName('2024-02-15')).toBe('Fevereiro');
      expect(getMonthName('2024-03-15')).toBe('Março');
      expect(getMonthName('2024-04-15')).toBe('Abril');
      expect(getMonthName('2024-05-15')).toBe('Maio');
      expect(getMonthName('2024-06-15')).toBe('Junho');
      expect(getMonthName('2024-07-15')).toBe('Julho');
      expect(getMonthName('2024-08-15')).toBe('Agosto');
      expect(getMonthName('2024-09-15')).toBe('Setembro');
      expect(getMonthName('2024-10-15')).toBe('Outubro');
      expect(getMonthName('2024-11-15')).toBe('Novembro');
      expect(getMonthName('2024-12-15')).toBe('Dezembro');
    });
  });

  describe('formatDateBR - Edge Cases', () => {
    it('retorna string vazia para Date com NaN time', () => {
      expect(formatDateBR(new Date('invalid'))).toBe('');
    });
  });

  describe('formatDateISO - Edge Cases', () => {
    it('retorna string vazia para Date com NaN time', () => {
      expect(formatDateISO(new Date('invalid'))).toBe('');
    });
  });

  describe('addDays - Edge Cases', () => {
    it('aceita string no formato brasileiro', () => {
      const result = addDays('15/01/2024', 5);
      expect(formatDateISO(result)).toBe('2024-01-20');
    });
  });

  describe('addMonths - Edge Cases', () => {
    it('aceita objeto Date', () => {
      const date = new Date(2024, 0, 15);
      const result = addMonths(date, 2);
      expect(formatDateISO(result)).toBe('2024-03-15');
    });
  });

  describe('startOfMonth - Edge Cases', () => {
    it('aceita objeto Date', () => {
      const result = startOfMonth(new Date(2024, 5, 15));
      expect(result.getDate()).toBe(1);
      expect(result.getMonth()).toBe(5);
    });
  });

  describe('endOfMonth - Edge Cases', () => {
    it('aceita objeto Date', () => {
      const result = endOfMonth(new Date(2024, 0, 15));
      expect(result.getDate()).toBe(31);
    });
  });

  describe('getDayOfWeekName - Edge Cases', () => {
    it('retorna nome curto para todos os dias', () => {
      expect(getDayOfWeekName('2024-01-07', true)).toBe('Dom');
      expect(getDayOfWeekName('2024-01-08', true)).toBe('Seg');
      expect(getDayOfWeekName('2024-01-09', true)).toBe('Ter');
      expect(getDayOfWeekName('2024-01-10', true)).toBe('Qua');
      expect(getDayOfWeekName('2024-01-11', true)).toBe('Qui');
      expect(getDayOfWeekName('2024-01-12', true)).toBe('Sex');
      expect(getDayOfWeekName('2024-01-13', true)).toBe('Sáb');
    });

    it('aceita objeto Date', () => {
      const monday = new Date(2024, 0, 8);
      expect(getDayOfWeekName(monday)).toBe('Segunda-feira');
    });
  });

  describe('getMonthName - Edge Cases', () => {
    it('retorna nome curto para todos os meses', () => {
      expect(getMonthName('2024-01-15', true)).toBe('Jan');
      expect(getMonthName('2024-02-15', true)).toBe('Fev');
      expect(getMonthName('2024-03-15', true)).toBe('Mar');
      expect(getMonthName('2024-04-15', true)).toBe('Abr');
      expect(getMonthName('2024-05-15', true)).toBe('Mai');
      expect(getMonthName('2024-06-15', true)).toBe('Jun');
      expect(getMonthName('2024-07-15', true)).toBe('Jul');
      expect(getMonthName('2024-08-15', true)).toBe('Ago');
      expect(getMonthName('2024-09-15', true)).toBe('Set');
      expect(getMonthName('2024-10-15', true)).toBe('Out');
      expect(getMonthName('2024-11-15', true)).toBe('Nov');
      expect(getMonthName('2024-12-15', true)).toBe('Dez');
    });

    it('aceita objeto Date', () => {
      const date = new Date(2024, 5, 15);
      expect(getMonthName(date)).toBe('Junho');
    });
  });

  describe('diffInDays - Edge Cases', () => {
    it('aceita objetos Date misturados com strings', () => {
      const result = diffInDays(new Date(2024, 0, 1), '2024-01-10');
      expect(result).toBe(9);
    });

    it('retorna 0 quando endDate é inválido', () => {
      expect(diffInDays('2024-01-01', 'invalid')).toBe(0);
    });
  });

  describe('isWeekend - Edge Cases', () => {
    it('testa quarta-feira (dia util)', () => {
      expect(isWeekend('2024-01-10')).toBe(false);
    });
  });

  describe('isHoliday - Edge Cases', () => {
    it('aceita objeto Date para feriado', () => {
      expect(isHoliday(new Date(2024, 0, 1))).toBe(true); // Ano Novo
    });
  });

  describe('isSameDay - Edge Cases', () => {
    it('compara objetos Date diretamente', () => {
      expect(isSameDay(new Date(2024, 0, 15), new Date(2024, 0, 15))).toBe(true);
    });

    it('retorna false quando segunda data é inválida', () => {
      expect(isSameDay('2024-01-15', 'invalid')).toBe(false);
    });
  });

  describe('isHoliday - Non-Holiday', () => {
    it('retorna false para dia comum não feriado', () => {
      expect(isHoliday('2024-03-15')).toBe(false);
      expect(isHoliday('2024-06-10')).toBe(false);
      expect(isHoliday('2024-08-20')).toBe(false);
    });
  });
});
