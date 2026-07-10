'use client';

import { useState } from 'react';
import { CalendarDays, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useGerarAvisoPrevioFerias } from '@/hooks/useGerarAvisoPrevioFerias';
import { baixarArquivoAutenticado } from '@/utils/baixarArquivoAutenticado';

interface BotaoAvisoPrevioFeriasProps {
  employeeId: string;
  employeeName?: string;
  className?: string;
}

export function BotaoAvisoPrevioFerias({
  employeeId,
  employeeName,
  className,
}: BotaoAvisoPrevioFeriasProps) {
  const [open, setOpen] = useState(false);
  const [dataInicio, setDataInicio] = useState('');
  const [dias, setDias] = useState(30);

  const mutation = useGerarAvisoPrevioFerias();

  const handleGerar = async () => {
    if (!dataInicio) {
      toast.error('Informe a data de início das férias');
      return;
    }
    try {
      const result = await mutation.mutateAsync({
        employee_id: employeeId,
        data_inicio_ferias: dataInicio,
        dias,
      });
      toast.success(`Aviso gerado para ${result.employee_name}`, { duration: 4000 });
      setOpen(false);
      await baixarArquivoAutenticado(result.file_url);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Erro ao gerar aviso', {
        duration: 5000,
      });
    }
  };

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className={className}
      >
        <CalendarDays className="h-4 w-4 mr-1" />
        Aviso Prévio Férias
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Gerar Aviso Prévio de Férias</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {employeeName && (
              <p className="text-sm text-muted-foreground">
                Funcionário: <strong>{employeeName}</strong>
              </p>
            )}

            <div className="space-y-1">
              <Label htmlFor="data-inicio">Data de início das férias</Label>
              <Input
                id="data-inicio"
                type="date"
                value={dataInicio}
                onChange={(e) => setDataInicio(e.target.value)}
                min={new Date().toISOString().split('T')[0]}
              />
            </div>

            <div className="space-y-1">
              <Label htmlFor="dias">Dias de férias</Label>
              <Input
                id="dias"
                type="number"
                value={dias}
                onChange={(e) => setDias(Math.max(1, Math.min(30, Number(e.target.value))))}
                min={1}
                max={30}
              />
            </div>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={mutation.isPending}>
              Cancelar
            </Button>
            <Button onClick={handleGerar} disabled={mutation.isPending || !dataInicio}>
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  Gerando...
                </>
              ) : (
                'Gerar Aviso'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
