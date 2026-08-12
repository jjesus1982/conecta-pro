/**
 * Funções de cálculo financeiros e matemáticos
 */

/**
 * Calcula a idade baseada na data de nascimento
 * @param birthDate - Data de nascimento (Date ou string ISO)
 * @returns Idade em anos
 */
export const calculateAge = (birthDate: Date | string): number => {
  const birth = birthDate instanceof Date ? birthDate : new Date(birthDate);
  const today = new Date();
  
  let age = today.getFullYear() - birth.getFullYear();
  const monthDiff = today.getMonth() - birth.getMonth();
  
  // Se ainda não fez aniversário este ano, subtrai 1
  if (monthDiff < 0 || (monthDiff === 0 && today.getDate() < birth.getDate())) {
    age--;
  }
  
  return age;
};

/**
 * Calcula a diferença em dias entre duas datas
 * @param startDate - Data inicial
 * @param endDate - Data final
 * @returns Número de dias de diferença (positivo se endDate > startDate)
 */
export const calculateDiffDays = (
  startDate: Date | string,
  endDate: Date | string
): number => {
  const start = startDate instanceof Date ? startDate : new Date(startDate);
  const end = endDate instanceof Date ? endDate : new Date(endDate);
  
  // Reset horas para comparar apenas as datas
  const startUTC = Date.UTC(start.getFullYear(), start.getMonth(), start.getDate());
  const endUTC = Date.UTC(end.getFullYear(), end.getMonth(), end.getDate());
  
  const diffTime = endUTC - startUTC;
  const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));
  
  return diffDays;
};

/**
 * Calcula juros simples ou compostos
 * @param principal - Valor principal
 * @param rate - Taxa de juros (em decimal, ex: 0.05 para 5%)
 * @param time - Tempo na mesma unidade da taxa (ex: meses se taxa for mensal)
 * @param compound - Se true, calcula juros compostos; se false, juros simples
 * @returns Valor total com juros
 */
export const calculateInterest = (
  principal: number,
  rate: number,
  time: number,
  compound: boolean = false
): number => {
  if (compound) {
    // Juros compostos: M = P * (1 + i)^n
    return principal * Math.pow(1 + rate, time);
  } else {
    // Juros simples: M = P * (1 + i * n)
    return principal * (1 + rate * time);
  }
};

/**
 * Calcula o valor da parcela de um financiamento (Sistema Price)
 * @param principal - Valor financiado
 * @param rate - Taxa de juros por período (em decimal)
 * @param installments - Número de parcelas
 * @returns Valor da parcela
 */
export const calculateInstallmentValue = (
  principal: number,
  rate: number,
  installments: number
): number => {
  if (rate === 0) {
    return principal / installments;
  }
  
  // Fórmula de Price: PMT = PV * [i * (1 + i)^n] / [(1 + i)^n - 1]
  const factor = Math.pow(1 + rate, installments);
  const pmt = principal * ((rate * factor) / (factor - 1));
  
  return pmt;
};

/**
 * Arredonda um valor para o número especificado de casas decimais
 * @param value - Valor a ser arredondado
 * @param decimals - Número de casas decimais (padrão: 2)
 * @returns Valor arredondado
 */
export const roundValue = (value: number, decimals: number = 2): number => {
  const factor = Math.pow(10, decimals);
  return Math.round(value * factor) / factor;
};

/**
 * Calcula o valor dos juros de uma parcela
 * @param remainingBalance - Saldo devedor
 * @param rate - Taxa de juros do período
 * @returns Valor dos juros
 */
export const calculateInterestPortion = (
  remainingBalance: number,
  rate: number
): number => {
  return roundValue(remainingBalance * rate);
};

/**
 * Calcula o valor da amortização de uma parcela
 * @param installmentValue - Valor da parcela
 * @param interestPortion - Valor dos juros
 * @returns Valor da amortização
 */
export const calculateAmortization = (
  installmentValue: number,
  interestPortion: number
): number => {
  return roundValue(installmentValue - interestPortion);
};

/**
 * Calcula o valor futuro de uma série de pagamentos (renda)
 * @param payment - Valor do pagamento periódico
 * @param rate - Taxa de juros por período
 * @param periods - Número de períodos
 * @returns Valor futuro
 */
export const calculateFutureValue = (
  payment: number,
  rate: number,
  periods: number
): number => {
  if (rate === 0) {
    return payment * periods;
  }
  
  // FV = PMT * [(1 + i)^n - 1] / i
  const factor = Math.pow(1 + rate, periods);
  return payment * ((factor - 1) / rate);
};

/**
 * Calcula o valor presente de uma série de pagamentos
 * @param payment - Valor do pagamento periódico
 * @param rate - Taxa de juros por período
 * @param periods - Número de períodos
 * @returns Valor presente
 */
export const calculatePresentValue = (
  payment: number,
  rate: number,
  periods: number
): number => {
  if (rate === 0) {
    return payment * periods;
  }
  
  // PV = PMT * [1 - (1 + i)^-n] / i
  const factor = Math.pow(1 + rate, -periods);
  return payment * ((1 - factor) / rate);
};
