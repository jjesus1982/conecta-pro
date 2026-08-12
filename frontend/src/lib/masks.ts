/**
 * Funções de máscara para formatação de dados brasileiros
 */

/**
 * Remove todos os caracteres não numéricos
 */
export const removeMask = (value: string): string => {
  if (!value) return '';
  return value.replace(/\D/g, '');
};

/**
 * Aplica máscara de CPF (123.456.789-09)
 */
export const applyCPFMask = (value: string): string => {
  if (!value) return '';
  
  const cleaned = removeMask(value).slice(0, 11);
  
  return cleaned.replace(
    /(\d{3})(\d{1,3})?(\d{1,3})?(\d{1,2})?/,
    (match, p1, p2, p3, p4) => {
      let result = p1;
      if (p2) result += `.${p2}`;
      if (p3) result += `.${p3}`;
      if (p4) result += `-${p4}`;
      return result;
    }
  );
};

/**
 * Aplica máscara de CNPJ (11.222.333/0001-81)
 */
export const applyCNPJMask = (value: string): string => {
  if (!value) return '';
  
  const cleaned = removeMask(value).slice(0, 14);
  
  return cleaned.replace(
    /(\d{2})(\d{1,3})?(\d{1,3})?(\d{1,4})?(\d{1,2})?/,
    (match, p1, p2, p3, p4, p5) => {
      let result = p1;
      if (p2) result += `.${p2}`;
      if (p3) result += `.${p3}`;
      if (p4) result += `/${p4}`;
      if (p5) result += `-${p5}`;
      return result;
    }
  );
};

/**
 * Aplica máscara de telefone brasileiro
 * Celular: (11) 98765-4321
 * Fixo: (11) 3456-7890
 */
export const applyPhoneMask = (value: string): string => {
  if (!value) return '';
  
  const cleaned = removeMask(value).slice(0, 11);
  
  // Celular com 11 dígitos
  if (cleaned.length > 10) {
    return cleaned.replace(
      /(\d{2})(\d{5})(\d{4})/,
      '($1) $2-$3'
    );
  }
  
  // Fixo com 10 dígitos
  return cleaned.replace(
    /(\d{2})(\d{4})(\d{0,4})/,
    (match, p1, p2, p3) => {
      let result = `(${p1}) ${p2}`;
      if (p3) result += `-${p3}`;
      return result;
    }
  );
};

/**
 * Aplica máscara de CEP (12345-678)
 */
export const applyCEPMask = (value: string): string => {
  if (!value) return '';
  
  const cleaned = removeMask(value).slice(0, 8);
  
  return cleaned.replace(
    /(\d{5})(\d{0,3})/,
    (match, p1, p2) => {
      let result = p1;
      if (p2) result += `-${p2}`;
      return result;
    }
  );
};

/**
 * Aplica máscara de moeda brasileira (R$ 1.234,56)
 * Mantém o valor em centavos durante a digitação
 */
export const applyCurrencyMask = (value: string | number): string => {
  if (value === '' || value === null || value === undefined) return '';
  
  let numericValue: number;
  
  if (typeof value === 'string') {
    // Remove tudo exceto números
    const cleaned = removeMask(value);
    // Converte para centavos
    numericValue = parseInt(cleaned, 10) / 100;
  } else {
    numericValue = value;
  }
  
  if (isNaN(numericValue)) return '';
  
  // Formata como moeda brasileira
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(numericValue);
};

/**
 * Converte valor com máscara de moeda para número
 */
export const currencyToNumber = (value: string): number => {
  if (!value) return 0;
  
  // Remove R$, pontos e substitui vírgula por ponto
  const cleaned = value
    .replace(/R\$\s?/g, '')
    .replace(/\./g, '')
    .replace(',', '.');
  
  const number = parseFloat(cleaned);
  return isNaN(number) ? 0 : number;
};
