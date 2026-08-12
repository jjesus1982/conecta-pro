import { describe, it, expect } from 'vitest';
import {
  calculateAge,
  calculateDiffDays,
  calculateInterest,
  calculateInstallmentValue,
  roundValue,
  calculateInterestPortion,
  calculateAmortization,
  calculateFutureValue,
  calculatePresentValue,
} from '../calculations';

describe('Calculations', () => {
  describe('calculateAge', () => {
    it('calcula idade corretamente', () => {
      const birthDate = new Date(1990, 0, 15); // 15/01/1990
      const today = new Date();
      const expectedAge = today.getFullYear() - 1990;
      
      // Ajusta se ainda não fez aniversário este ano
      const hasBirthdayPassed = today.getMonth() > 0 || 
        (today.getMonth() === 0 && today.getDate() >= 15);
      
      expect(calculateAge(birthDate)).toBe(hasBirthdayPassed ? expectedAge : expectedAge - 1);
    });

    it('calcula idade a partir de string ISO', () => {
      const birthDate = '1990-01-15';
      const today = new Date();
      const expectedAge = today.getFullYear() - 1990;
      
      const hasBirthdayPassed = today.getMonth() > 0 || 
        (today.getMonth() === 0 && today.getDate() >= 15);
      
      expect(calculateAge(birthDate)).toBe(hasBirthdayPassed ? expectedAge : expectedAge - 1);
    });

    it('calcula idade para bebê', () => {
      const today = new Date();
      const birthDate = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
      expect(calculateAge(birthDate)).toBe(1);
    });

    it('calcula idade quando aniversário ainda não passou', () => {
      const today = new Date();
      const nextMonth = (today.getMonth() + 1) % 12;
      const nextYear = nextMonth < today.getMonth() ? today.getFullYear() + 1 : today.getFullYear();
      const birthDate = new Date(nextYear - 25, nextMonth, 15);
      
      expect(calculateAge(birthDate)).toBe(24);
    });

    it('calcula idade quando aniversário já passou', () => {
      const today = new Date();
      const lastMonth = today.getMonth() === 0 ? 11 : today.getMonth() - 1;
      const birthDate = new Date(today.getFullYear() - 30, lastMonth, 15);
      
      expect(calculateAge(birthDate)).toBe(30);
    });
  });

  describe('calculateDiffDays', () => {
    it('calcula diferença de dias positiva', () => {
      const start = new Date('2024-01-01');
      const end = new Date('2024-01-10');
      expect(calculateDiffDays(start, end)).toBe(9);
    });

    it('calcula diferença de dias negativa', () => {
      const start = new Date('2024-01-10');
      const end = new Date('2024-01-01');
      expect(calculateDiffDays(start, end)).toBe(-9);
    });

    it('retorna zero para mesma data', () => {
      const date = new Date('2024-01-15');
      expect(calculateDiffDays(date, date)).toBe(0);
    });

    it('calcula diferença entre datas em anos diferentes', () => {
      const start = new Date('2023-12-30');
      const end = new Date('2024-01-02');
      expect(calculateDiffDays(start, end)).toBe(3);
    });

    it('calcula diferença a partir de strings', () => {
      expect(calculateDiffDays('2024-01-01', '2024-01-15')).toBe(14);
    });

    it('calcula diferença para ano bissexto', () => {
      const start = new Date('2024-02-28');
      const end = new Date('2024-03-01');
      expect(calculateDiffDays(start, end)).toBe(2);
    });
  });

  describe('calculateInterest', () => {
    it('calcula juros simples', () => {
      // 1000 * (1 + 0.05 * 12) = 1600
      expect(calculateInterest(1000, 0.05, 12, false)).toBe(1600);
    });

    it('calcula juros compostos', () => {
      // 1000 * (1 + 0.05)^12 = 1795.86
      const result = calculateInterest(1000, 0.05, 12, true);
      expect(result).toBeCloseTo(1795.86, 2);
    });

    it('calcula juros zero quando taxa é zero', () => {
      expect(calculateInterest(1000, 0, 12, false)).toBe(1000);
      expect(calculateInterest(1000, 0, 12, true)).toBe(1000);
    });

    it('calcula juros zero quando tempo é zero', () => {
      expect(calculateInterest(1000, 0.05, 0, false)).toBe(1000);
      expect(calculateInterest(1000, 0.05, 0, true)).toBe(1000);
    });

    it('calcula juros para valor principal zero', () => {
      expect(calculateInterest(0, 0.05, 12, false)).toBe(0);
    });

    it('calcula juros simples para um período', () => {
      // 1000 * (1 + 0.1 * 1) = 1100
      expect(calculateInterest(1000, 0.1, 1, false)).toBe(1100);
    });

    it('calcula juros compostos para um período', () => {
      // 1000 * (1 + 0.1)^1 = 1100
      expect(calculateInterest(1000, 0.1, 1, true)).toBe(1100);
    });
  });

  describe('calculateInstallmentValue', () => {
    it('calcula parcela do sistema Price', () => {
      // PV = 10000, i = 0.02, n = 12
      // PMT = 10000 * [0.02 * (1.02)^12] / [(1.02)^12 - 1]
      const result = calculateInstallmentValue(10000, 0.02, 12);
      expect(result).toBeCloseTo(945.60, 2);
    });

    it('calcula parcela quando taxa é zero', () => {
      expect(calculateInstallmentValue(12000, 0, 12)).toBe(1000);
    });

    it('calcula parcela para uma única parcela', () => {
      expect(calculateInstallmentValue(1000, 0.05, 1)).toBeCloseTo(1000 * 1.05, 2);
    });

    it('calcula parcela para valor zero', () => {
      expect(calculateInstallmentValue(0, 0.05, 12)).toBe(0);
    });

    it('calcula parcela para muitas parcelas', () => {
      const result = calculateInstallmentValue(50000, 0.015, 360);
      expect(result).toBeGreaterThan(0);
      expect(result).toBeCloseTo(753.54, 0); // Valor aproximado
    });
  });

  describe('roundValue', () => {
    it('arredonda para 2 casas decimais (padrão)', () => {
      expect(roundValue(1.234)).toBe(1.23);
      expect(roundValue(1.235)).toBe(1.24);
    });

    it('arredonda para número específico de casas', () => {
      expect(roundValue(1.23456, 3)).toBe(1.235);
      expect(roundValue(1.23456, 4)).toBe(1.2346);
    });

    it('arredonda para 0 casas decimais', () => {
      expect(roundValue(1.4, 0)).toBe(1);
      expect(roundValue(1.5, 0)).toBe(2);
    });

    it('mantém inteiro quando não há decimais', () => {
      expect(roundValue(100)).toBe(100);
    });

    it('arredonda valores negativos', () => {
      expect(roundValue(-1.234)).toBe(-1.23);
      expect(roundValue(-1.235)).toBe(-1.24);
    });

    it('arredonda zero', () => {
      expect(roundValue(0)).toBe(0);
    });
  });

  describe('calculateInterestPortion', () => {
    it('calcula porção de juros da parcela', () => {
      // Saldo 10000, taxa 2%
      expect(calculateInterestPortion(10000, 0.02)).toBe(200);
    });

    it('calcula porção de juros com saldo zero', () => {
      expect(calculateInterestPortion(0, 0.02)).toBe(0);
    });

    it('calcula porção de juros com taxa zero', () => {
      expect(calculateInterestPortion(10000, 0)).toBe(0);
    });

    it('arredonda resultado corretamente', () => {
      expect(calculateInterestPortion(3333.33, 0.0333)).toBe(111);
    });
  });

  describe('calculateAmortization', () => {
    it('calcula amortização da parcela', () => {
      // Parcela 945.60, juros 200
      expect(calculateAmortization(945.60, 200)).toBe(745.60);
    });

    it('calcula amortização quando juros igual à parcela', () => {
      expect(calculateAmortization(1000, 1000)).toBe(0);
    });

    it('calcula amortização com arredondamento', () => {
      expect(calculateAmortization(945.555, 200.444)).toBe(745.11);
    });
  });

  describe('calculateFutureValue', () => {
    it('calcula valor futuro de série uniforme', () => {
      // PMT = 100, i = 0.05, n = 12
      // FV = 100 * [(1.05)^12 - 1] / 0.05
      const result = calculateFutureValue(100, 0.05, 12);
      expect(result).toBeCloseTo(1591.71, 2);
    });

    it('calcula valor futuro quando taxa é zero', () => {
      expect(calculateFutureValue(100, 0, 12)).toBe(1200);
    });

    it('calcula valor futuro para uma parcela', () => {
      expect(calculateFutureValue(100, 0.05, 1)).toBeCloseTo(100, 10);
    });

    it('calcula valor futuro para pagamento zero', () => {
      expect(calculateFutureValue(0, 0.05, 12)).toBe(0);
    });
  });

  describe('calculatePresentValue', () => {
    it('calcula valor presente de série uniforme', () => {
      // PMT = 100, i = 0.05, n = 12
      // PV = 100 * [1 - (1.05)^-12] / 0.05
      const result = calculatePresentValue(100, 0.05, 12);
      expect(result).toBeCloseTo(886.33, 1); // Valor aproximado
    });

    it('calcula valor presente quando taxa é zero', () => {
      expect(calculatePresentValue(100, 0, 12)).toBe(1200);
    });

    it('calcula valor presente para uma parcela', () => {
      // PV = 100 / 1.05 = 95.24
      const result = calculatePresentValue(100, 0.05, 1);
      expect(result).toBeCloseTo(95.24, 2);
    });

    it('calcula valor presente para pagamento zero', () => {
      expect(calculatePresentValue(0, 0.05, 12)).toBe(0);
    });
  });
});
