'use client';

import { FileDown, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useGerarContratoTrabalho } from '@/hooks/useGerarContratoTrabalho';
import { baixarArquivoAutenticado } from '@/utils/baixarArquivoAutenticado';

interface BotaoGerarContratoProps {
  employeeId: string;
  employeeName?: string;
  className?: string;
}

export function BotaoGerarContrato({ employeeId, employeeName, className }: BotaoGerarContratoProps) {
  const mutation = useGerarContratoTrabalho();

  const handleClick = async () => {
    try {
      const result = await mutation.mutateAsync({ employee_id: employeeId });
      toast.success(`Contrato gerado para ${result.employee_name}`, { duration: 4000 });
      await baixarArquivoAutenticado(result.file_url);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro ao gerar contrato';
      toast.error(msg, { duration: 5000 });
    }
  };

  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={handleClick}
      disabled={mutation.isPending}
      className={className}
    >
      {mutation.isPending ? (
        <Loader2 className="h-4 w-4 mr-1 animate-spin" />
      ) : (
        <FileDown className="h-4 w-4 mr-1" />
      )}
      {mutation.isPending ? 'Gerando...' : 'Gerar Contrato CLT'}
    </Button>
  );
}
