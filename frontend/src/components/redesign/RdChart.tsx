'use client';

// Gráficos nativos do redesign (Recharts) — barras/pizza/donut/linha/área.
// Alimentado pelo campo `charts` das telas dash (builders backend emitem {type,title,data}).
// Tema Conecta: Sora Navy #16277D + Laranja #F26522.
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart,
  Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

const PALETTE = ['#16277D', '#F26522', '#16A34A', '#0EA5E9', '#C2410C', '#7C3AED', '#DC2626', '#0F1B3A', '#059669', '#D97706'];

const brl = (v: any) =>
  typeof v === 'number' ? v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 }) : v;
const brlFull = (v: any) =>
  typeof v === 'number' ? v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : v;

const tip = {
  contentStyle: { borderRadius: 10, border: '1px solid #E5E7EB', fontSize: 12, boxShadow: '0 4px 16px rgba(0,0,0,.08)' },
  formatter: (v: any) => brlFull(v),
};

export default function RdChart({ chart }: { chart: any }) {
  const data: any[] = Array.isArray(chart?.data) ? chart.data : [];
  const type = (chart?.type || 'bar').toLowerCase();
  const h = chart?.height || 240;
  if (!data.length) {
    return <div style={{ padding: 24, color: 'var(--ink-weak)', fontSize: 13, textAlign: 'center' }}>Sem dados</div>;
  }

  if (type === 'pie' || type === 'donut') {
    return (
      <ResponsiveContainer width="100%" height={h}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%"
            innerRadius={type === 'donut' ? 55 : 0} outerRadius={90} paddingAngle={2}
            label={(e: any) => e.name} labelLine={false} fontSize={11}>
            {data.map((d, i) => <Cell key={i} fill={d.color || PALETTE[i % PALETTE.length]} />)}
          </Pie>
          <Tooltip {...tip} />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  if (type === 'line' || type === 'area') {
    const C = type === 'area' ? AreaChart : LineChart;
    return (
      <ResponsiveContainer width="100%" height={h}>
        <C data={data} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#EEF1F6" vertical={false} />
          <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748B' }} tickLine={false} axisLine={{ stroke: '#E5E7EB' }} />
          <YAxis tick={{ fontSize: 11, fill: '#64748B' }} tickFormatter={brl} tickLine={false} axisLine={false} width={64} />
          <Tooltip {...tip} />
          {type === 'area'
            ? <Area type="monotone" dataKey="value" stroke="#16277D" fill="#16277D22" strokeWidth={2} />
            : <Line type="monotone" dataKey="value" stroke="#16277D" strokeWidth={2.5} dot={{ r: 3, fill: '#F26522' }} />}
        </C>
      </ResponsiveContainer>
    );
  }

  // default: barras (horizontal se muitas categorias, senão vertical)
  const horizontal = data.length > 6 || chart?.horizontal;
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#EEF1F6" horizontal={!horizontal} vertical={horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tick={{ fontSize: 11, fill: '#64748B' }} tickFormatter={brl} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: '#334155' }} width={130} axisLine={false} tickLine={false} />
          </>
        ) : (
          <>
            <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#64748B' }} axisLine={{ stroke: '#E5E7EB' }} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: '#64748B' }} tickFormatter={brl} width={64} axisLine={false} tickLine={false} />
          </>
        )}
        <Tooltip {...tip} cursor={{ fill: '#16277D0A' }} />
        <Bar dataKey="value" radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} maxBarSize={46}>
          {data.map((d, i) => <Cell key={i} fill={d.color || PALETTE[i % PALETTE.length]} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
