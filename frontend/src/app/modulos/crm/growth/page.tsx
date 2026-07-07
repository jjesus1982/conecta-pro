'use client';

/**
 * Hub "Growth" do CRM — 9 features HubSpot-like:
 * catálogo de produtos, sequências, workflows, formulários, agendamento,
 * segmentos, propriedades custom, scoring configurável e forecast.
 */
import { useEffect, useState } from 'react';
import { customInstance } from '@/lib/api-client';
import { toast } from 'sonner';
import {
  Package, Mail, Zap, FileInput, CalendarClock, Filter, SlidersHorizontal, Star, TrendingUp,
} from 'lucide-react';

const API = '/api/v1/crm';
const api = {
  get: (u: string) => customInstance<any>({ url: `${API}${u}`, method: 'GET' }),
  post: (u: string, data: any) => customInstance<any>({ url: `${API}${u}`, method: 'POST', data }),
  put: (u: string, data: any) => customInstance<any>({ url: `${API}${u}`, method: 'PUT', data }),
  del: (u: string) => customInstance<any>({ url: `${API}${u}`, method: 'DELETE' }),
};
const brl = (v: any) => (Number(v) || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
const PUBLIC_BASE = typeof window !== 'undefined' ? window.location.origin : '';

const TABS = [
  { id: 'products', label: 'Catálogo', icon: Package },
  { id: 'sequences', label: 'Sequências', icon: Mail },
  { id: 'workflows', label: 'Automação', icon: Zap },
  { id: 'forms', label: 'Formulários', icon: FileInput },
  { id: 'booking', label: 'Agendamento', icon: CalendarClock },
  { id: 'segments', label: 'Segmentos', icon: Filter },
  { id: 'properties', label: 'Propriedades', icon: SlidersHorizontal },
  { id: 'scoring', label: 'Scoring', icon: Star },
  { id: 'forecast', label: 'Forecast', icon: TrendingUp },
];

const inp = 'border border-slate-300 rounded-lg px-3 py-2 text-sm w-full';
const btn = 'bg-blue-800 hover:bg-blue-900 text-white rounded-lg px-4 py-2 text-sm font-medium disabled:opacity-50';
const btnX = 'text-red-600 hover:text-red-800 text-xs';
const card = 'bg-white border border-slate-200 rounded-xl p-4';

export default function GrowthPage() {
  const [tab, setTab] = useState('products');
  return (
    <div className="p-6 max-w-6xl mx-auto">
      <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] mb-1">Growth — CRM avançado</h1>
      <p className="text-slate-500 mb-5 text-sm">Catálogo, sequências, automação, formulários, agendamento, segmentos, propriedades, scoring e forecast.</p>
      <div className="flex flex-wrap gap-2 mb-6">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm border ${tab === t.id ? 'bg-blue-800 text-white border-blue-800' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}>
              <Icon className="h-4 w-4" />{t.label}
            </button>
          );
        })}
      </div>
      {tab === 'products' && <Products />}
      {tab === 'sequences' && <Sequences />}
      {tab === 'workflows' && <Workflows />}
      {tab === 'forms' && <Forms />}
      {tab === 'booking' && <Booking />}
      {tab === 'segments' && <Segments />}
      {tab === 'properties' && <Properties />}
      {tab === 'scoring' && <Scoring />}
      {tab === 'forecast' && <Forecast />}
    </div>
  );
}

function useList(url: string) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const reload = () => { setLoading(true); api.get(url).then((d) => setItems(Array.isArray(d) ? d : d.items || [])).catch(() => setItems([])).finally(() => setLoading(false)); };
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [url]);
  return { items, loading, reload };
}

// ---------------- 4) CATÁLOGO ----------------
function Products() {
  const { items, reload } = useList('/products');
  const [f, setF] = useState({ name: '', sku: '', unit: 'un', unit_price: 0, is_recurring: false, service_type: '' });
  const save = async () => {
    if (!f.name) return toast.error('Informe o nome');
    try { await api.post('/products', f); toast.success('Produto criado'); setF({ name: '', sku: '', unit: 'un', unit_price: 0, is_recurring: false, service_type: '' }); reload(); }
    catch { toast.error('Erro ao criar'); }
  };
  return (
    <div className="grid md:grid-cols-3 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Novo produto/serviço</h3>
        <div className="grid gap-2">
          <input className={inp} placeholder="Nome *" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
          <input className={inp} placeholder="SKU" value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })} />
          <div className="flex gap-2">
            <input className={inp} placeholder="Unidade" value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })} />
            <input className={inp} type="number" placeholder="Preço" value={f.unit_price} onChange={(e) => setF({ ...f, unit_price: Number(e.target.value) })} />
          </div>
          <input className={inp} placeholder="Tipo de serviço (ex: cerca_eletrica)" value={f.service_type} onChange={(e) => setF({ ...f, service_type: e.target.value })} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_recurring} onChange={(e) => setF({ ...f, is_recurring: e.target.checked })} /> Recorrente (mensal)</label>
          <button className={btn} onClick={save}>Adicionar ao catálogo</button>
        </div>
      </div>
      <div className={`${card} md:col-span-2`}>
        <h3 className="font-semibold mb-3">Catálogo ({items.length})</h3>
        <table className="w-full text-sm">
          <thead><tr className="text-left text-slate-500 border-b"><th className="py-1">Nome</th><th>SKU</th><th>Preço</th><th>Tipo</th><th></th></tr></thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id} className="border-b border-slate-100">
                <td className="py-1.5">{p.name}{p.is_recurring ? ' 🔁' : ''}</td><td>{p.sku || '-'}</td>
                <td>{brl(p.unit_price)}/{p.unit}</td><td className="text-xs">{p.service_type || '-'}</td>
                <td><button className={btnX} onClick={async () => { await api.del(`/products/${p.id}`); reload(); }}>remover</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------- 1) SEQUÊNCIAS ----------------
function Sequences() {
  const { items, reload } = useList('/sequences');
  const [name, setName] = useState('');
  const [steps, setSteps] = useState<any[]>([{ delay_days: 0, channel: 'email', subject: '', body: '' }]);
  const [enrollLead, setEnrollLead] = useState<Record<string, string>>({});
  const save = async () => {
    if (!name) return toast.error('Informe o nome');
    try { await api.post('/sequences', { name, channel: 'email', steps }); toast.success('Sequência criada'); setName(''); setSteps([{ delay_days: 0, channel: 'email', subject: '', body: '' }]); reload(); }
    catch { toast.error('Erro'); }
  };
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Nova sequência (cadência)</h3>
        <input className={inp} placeholder="Nome (ex: Follow-up Cerca)" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="mt-3 space-y-2">
          {steps.map((s, i) => (
            <div key={i} className="border border-slate-200 rounded-lg p-2 space-y-1">
              <div className="flex gap-2 items-center text-xs text-slate-500">Passo {i + 1} · após
                <input className="border rounded px-2 py-0.5 w-16" type="number" value={s.delay_days} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, delay_days: Number(e.target.value) } : x))} /> dias
                <select className="border rounded px-1 py-0.5" value={s.channel} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, channel: e.target.value } : x))}><option value="email">email</option><option value="whatsapp">whatsapp</option></select>
              </div>
              <input className={inp} placeholder="Assunto" value={s.subject} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, subject: e.target.value } : x))} />
              <textarea className={inp} placeholder="Mensagem (use {{name}})" value={s.body} onChange={(e) => setSteps(steps.map((x, j) => j === i ? { ...x, body: e.target.value } : x))} />
            </div>
          ))}
          <button className="text-blue-700 text-sm" onClick={() => setSteps([...steps, { delay_days: 1, channel: 'email', subject: '', body: '' }])}>+ passo</button>
        </div>
        <button className={`${btn} mt-3`} onClick={save}>Criar sequência</button>
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Sequências ({items.length})</h3>
        {items.map((s) => (
          <div key={s.id} className="border-b border-slate-100 py-2">
            <div className="font-medium text-sm">{s.name} <span className="text-xs text-slate-400">· {(s.steps || []).length} passos · {s.channel}</span></div>
            <div className="flex gap-2 mt-1">
              <input className="border rounded px-2 py-1 text-xs flex-1" placeholder="lead_id p/ inscrever" value={enrollLead[s.id] || ''} onChange={(e) => setEnrollLead({ ...enrollLead, [s.id]: e.target.value })} />
              <button className="text-blue-700 text-xs" onClick={async () => { try { const r = await api.post(`/sequences/${s.id}/enroll`, { lead_id: enrollLead[s.id] }); toast.success(r.enrolled ? 'Lead inscrito' : 'Não inscrito'); } catch { toast.error('Erro'); } }}>inscrever</button>
              <button className={btnX} onClick={async () => { await api.del(`/sequences/${s.id}`); reload(); }}>remover</button>
            </div>
          </div>
        ))}
        <button className={`${btn} mt-3`} onClick={async () => { const r = await api.post('/sequences/process-due', {}); toast.success(`Processados: ${r.processed}, enviados: ${r.sent}`); }}>Processar passos vencidos agora</button>
      </div>
    </div>
  );
}

// ---------------- 2) WORKFLOWS ----------------
const TRIGGERS = ['lead_created', 'form_submitted', 'meeting_booked', 'opportunity_won'];
const ACTION_TYPES = ['create_task', 'send_email', 'send_whatsapp', 'assign_owner', 'enroll_sequence'];
function Workflows() {
  const { items, reload } = useList('/workflows');
  const [f, setF] = useState<any>({ name: '', trigger_event: 'lead_created', conditions: [], actions: [{ type: 'create_task', params: { title: 'Ligar para {{name}}', due_in_days: 1 } }] });
  const [testLead, setTestLead] = useState<Record<string, string>>({});
  const save = async () => {
    if (!f.name) return toast.error('Informe o nome');
    let actions = f.actions; let conditions = f.conditions;
    try { if (typeof actions === 'string') actions = JSON.parse(actions); if (typeof conditions === 'string') conditions = JSON.parse(conditions); } catch { return toast.error('JSON inválido em condições/ações'); }
    try { await api.post('/workflows', { ...f, actions, conditions }); toast.success('Workflow criado'); reload(); }
    catch { toast.error('Erro'); }
  };
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Novo workflow</h3>
        <input className={inp} placeholder="Nome" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <label className="text-xs text-slate-500 mt-2 block">Quando (gatilho)</label>
        <select className={inp} value={f.trigger_event} onChange={(e) => setF({ ...f, trigger_event: e.target.value })}>{TRIGGERS.map((t) => <option key={t}>{t}</option>)}</select>
        <label className="text-xs text-slate-500 mt-2 block">Condições (JSON) — ex: [{'{'}"field":"source","operator":"eq","value":"website"{'}'}]</label>
        <textarea className={inp} rows={2} defaultValue="[]" onChange={(e) => setF({ ...f, conditions: e.target.value })} />
        <label className="text-xs text-slate-500 mt-2 block">Ações (JSON) — tipos: {ACTION_TYPES.join(', ')}</label>
        <textarea className={inp} rows={4} defaultValue={JSON.stringify(f.actions, null, 1)} onChange={(e) => setF({ ...f, actions: e.target.value })} />
        <button className={`${btn} mt-3`} onClick={save}>Criar workflow</button>
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Workflows ({items.length})</h3>
        {items.map((w) => (
          <div key={w.id} className="border-b border-slate-100 py-2">
            <div className="font-medium text-sm">{w.name} <span className="text-xs text-slate-400">· {w.trigger_event} · {w.run_count}x</span></div>
            <div className="flex gap-2 mt-1">
              <input className="border rounded px-2 py-1 text-xs flex-1" placeholder="lead_id p/ testar" value={testLead[w.id] || ''} onChange={(e) => setTestLead({ ...testLead, [w.id]: e.target.value })} />
              <button className="text-blue-700 text-xs" onClick={async () => { try { const r = await api.post(`/workflows/${w.id}/test`, { lead_id: testLead[w.id] }); toast.success(`Disparou: ${r.fired}`); reload(); } catch { toast.error('Erro'); } }}>testar</button>
              <button className={btnX} onClick={async () => { await api.del(`/workflows/${w.id}`); reload(); }}>remover</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------- 3) FORMULÁRIOS ----------------
function Forms() {
  const { items, reload } = useList('/forms');
  const [f, setF] = useState({ name: '', slug: '', source: 'website' });
  const save = async () => {
    if (!f.name || !f.slug) return toast.error('Nome e slug obrigatórios');
    try { await api.post('/forms', { ...f, fields: [{ key: 'name', label: 'Nome' }, { key: 'email', label: 'E-mail' }, { key: 'phone', label: 'Telefone' }] }); toast.success('Formulário criado'); setF({ name: '', slug: '', source: 'website' }); reload(); }
    catch { toast.error('Erro (slug duplicado?)'); }
  };
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Novo formulário</h3>
        <input className={inp} placeholder="Nome" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input className={`${inp} mt-2`} placeholder="slug (ex: orcamento-cerca)" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value.replace(/[^a-z0-9-]/g, '') })} />
        <p className="text-xs text-slate-400 mt-1">Campos padrão: Nome, E-mail, Telefone. Cada envio cria um lead (source={f.source}).</p>
        <button className={`${btn} mt-3`} onClick={save}>Criar formulário</button>
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Formulários ({items.length})</h3>
        {items.map((x) => (
          <div key={x.id} className="border-b border-slate-100 py-2">
            <div className="font-medium text-sm">{x.name} <span className="text-xs text-slate-400">· {x.submit_count} envios</span></div>
            <a className="text-blue-700 text-xs break-all" href={`/form/${x.slug}`} target="_blank" rel="noreferrer">{PUBLIC_BASE}/form/{x.slug}</a>
            <button className={`${btnX} ml-2`} onClick={async () => { await api.del(`/forms/${x.id}`); reload(); }}>remover</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------- 5) AGENDAMENTO ----------------
function Booking() {
  const { items, reload } = useList('/booking-links');
  const [f, setF] = useState({ name: '', slug: '', duration_min: 60 });
  const save = async () => {
    if (!f.name || !f.slug) return toast.error('Nome e slug obrigatórios');
    try { await api.post('/booking-links', { ...f, weekly_availability: { mon: ['09:00', '14:00'], tue: ['09:00', '14:00'], wed: ['09:00', '14:00'], thu: ['09:00', '14:00'], fri: ['09:00', '14:00'] } }); toast.success('Link criado'); setF({ name: '', slug: '', duration_min: 60 }); reload(); }
    catch { toast.error('Erro (slug duplicado?)'); }
  };
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Novo link de agendamento</h3>
        <input className={inp} placeholder="Nome (ex: Vistoria Técnica)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input className={`${inp} mt-2`} placeholder="slug (ex: vistoria)" value={f.slug} onChange={(e) => setF({ ...f, slug: e.target.value.replace(/[^a-z0-9-]/g, '') })} />
        <input className={`${inp} mt-2`} type="number" placeholder="Duração (min)" value={f.duration_min} onChange={(e) => setF({ ...f, duration_min: Number(e.target.value) })} />
        <button className={`${btn} mt-3`} onClick={save}>Criar link</button>
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Links ({items.length})</h3>
        {items.map((x) => (
          <div key={x.id} className="border-b border-slate-100 py-2">
            <div className="font-medium text-sm">{x.name} <span className="text-xs text-slate-400">· {x.duration_min}min</span></div>
            <a className="text-blue-700 text-xs break-all" href={`/agendar/${x.slug}`} target="_blank" rel="noreferrer">{PUBLIC_BASE}/agendar/{x.slug}</a>
            <button className={`${btnX} ml-2`} onClick={async () => { await api.del(`/booking-links/${x.id}`); reload(); }}>remover</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------- 6) SEGMENTOS ----------------
const SEG_FIELDS = ['source', 'status', 'score', 'company', 'email', 'industry'];
function Segments() {
  const { items, reload } = useList('/segments');
  const [f, setF] = useState<any>({ name: '', entity: 'lead', filters: [{ field: 'source', operator: 'eq', value: 'website' }] });
  const [results, setResults] = useState<Record<string, number>>({});
  const save = async () => {
    if (!f.name) return toast.error('Informe o nome');
    try { await api.post('/segments', f); toast.success('Segmento criado'); reload(); } catch { toast.error('Erro'); }
  };
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Novo segmento (lista dinâmica)</h3>
        <input className={inp} placeholder="Nome" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        {f.filters.map((flt: any, i: number) => (
          <div key={i} className="flex gap-1 mt-2">
            <select className="border rounded px-1 text-xs" value={flt.field} onChange={(e) => setF({ ...f, filters: f.filters.map((x: any, j: number) => j === i ? { ...x, field: e.target.value } : x) })}>{SEG_FIELDS.map((s) => <option key={s}>{s}</option>)}</select>
            <select className="border rounded px-1 text-xs" value={flt.operator} onChange={(e) => setF({ ...f, filters: f.filters.map((x: any, j: number) => j === i ? { ...x, operator: e.target.value } : x) })}>{['eq', 'ne', 'contains', 'gt', 'lt', 'not_empty', 'empty'].map((o) => <option key={o}>{o}</option>)}</select>
            <input className="border rounded px-2 text-xs flex-1" placeholder="valor" value={flt.value || ''} onChange={(e) => setF({ ...f, filters: f.filters.map((x: any, j: number) => j === i ? { ...x, value: e.target.value } : x) })} />
          </div>
        ))}
        <button className="text-blue-700 text-sm mt-1" onClick={() => setF({ ...f, filters: [...f.filters, { field: 'status', operator: 'eq', value: '' }] })}>+ filtro</button>
        <div className="flex gap-2 mt-3">
          <button className={btn} onClick={save}>Salvar segmento</button>
          <button className="border rounded-lg px-4 py-2 text-sm" onClick={async () => { const r = await api.post('/segments/preview', { entity: f.entity, filters: f.filters }); toast.success(`${r.count} registros`); }}>Pré-visualizar</button>
        </div>
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Segmentos ({items.length})</h3>
        {items.map((s) => (
          <div key={s.id} className="border-b border-slate-100 py-2 flex items-center justify-between">
            <div><span className="font-medium text-sm">{s.name}</span> <span className="text-xs text-slate-400">· {s.entity}{results[s.id] != null ? ` · ${results[s.id]} itens` : ''}</span></div>
            <div className="flex gap-2">
              <button className="text-blue-700 text-xs" onClick={async () => { const r = await api.get(`/segments/${s.id}/results`); setResults({ ...results, [s.id]: r.count }); }}>ver</button>
              <button className={btnX} onClick={async () => { await api.del(`/segments/${s.id}`); reload(); }}>remover</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------- 7) PROPRIEDADES ----------------
function Properties() {
  const { items, reload } = useList('/properties');
  const [f, setF] = useState({ entity: 'lead', key: '', label: '', field_type: 'text' });
  const save = async () => {
    if (!f.key || !f.label) return toast.error('Chave e rótulo obrigatórios');
    try { await api.post('/properties', f); toast.success('Propriedade criada'); setF({ entity: 'lead', key: '', label: '', field_type: 'text' }); reload(); }
    catch { toast.error('Erro (chave duplicada?)'); }
  };
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Nova propriedade customizada</h3>
        <select className={inp} value={f.entity} onChange={(e) => setF({ ...f, entity: e.target.value })}><option value="lead">Lead</option><option value="opportunity">Oportunidade</option></select>
        <input className={`${inp} mt-2`} placeholder="chave (ex: num_unidades)" value={f.key} onChange={(e) => setF({ ...f, key: e.target.value.replace(/[^a-z0-9_]/g, '') })} />
        <input className={`${inp} mt-2`} placeholder="Rótulo (ex: Nº de unidades)" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} />
        <select className={`${inp} mt-2`} value={f.field_type} onChange={(e) => setF({ ...f, field_type: e.target.value })}>{['text', 'number', 'date', 'select', 'boolean'].map((t) => <option key={t}>{t}</option>)}</select>
        <button className={`${btn} mt-3`} onClick={save}>Criar propriedade</button>
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Propriedades ({items.length})</h3>
        {items.map((p) => (
          <div key={p.id} className="border-b border-slate-100 py-2 flex justify-between">
            <span className="text-sm">{p.label} <span className="text-xs text-slate-400">· {p.entity}.{p.key} · {p.field_type}</span></span>
            <button className={btnX} onClick={async () => { await api.del(`/properties/${p.id}`); reload(); }}>remover</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------- 8) SCORING ----------------
function Scoring() {
  const { items, reload } = useList('/scoring/rules');
  const [f, setF] = useState({ name: '', field: 'email', operator: 'not_empty', value: '', points: 10 });
  const save = async () => {
    if (!f.name) return toast.error('Informe o nome');
    try { await api.post('/scoring/rules', f); toast.success('Regra criada'); setF({ name: '', field: 'email', operator: 'not_empty', value: '', points: 10 }); reload(); }
    catch { toast.error('Erro'); }
  };
  return (
    <div className="grid md:grid-cols-2 gap-5">
      <div className={card}>
        <h3 className="font-semibold mb-3">Nova regra de pontuação</h3>
        <input className={inp} placeholder="Nome (ex: Tem e-mail)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <div className="flex gap-1 mt-2">
          <select className="border rounded px-1 text-xs" value={f.field} onChange={(e) => setF({ ...f, field: e.target.value })}>{SEG_FIELDS.map((s) => <option key={s}>{s}</option>)}</select>
          <select className="border rounded px-1 text-xs" value={f.operator} onChange={(e) => setF({ ...f, operator: e.target.value })}>{['eq', 'ne', 'contains', 'gt', 'lt', 'not_empty', 'empty'].map((o) => <option key={o}>{o}</option>)}</select>
          <input className="border rounded px-2 text-xs flex-1" placeholder="valor" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} />
          <input className="border rounded px-2 text-xs w-16" type="number" placeholder="pts" value={f.points} onChange={(e) => setF({ ...f, points: Number(e.target.value) })} />
        </div>
        <div className="flex gap-2 mt-3">
          <button className={btn} onClick={save}>Criar regra</button>
          <button className="border rounded-lg px-4 py-2 text-sm" onClick={async () => { const r = await api.post('/scoring/recompute', {}); toast.success(`${r.updated} leads recalculados`); }}>Recalcular todos os leads</button>
        </div>
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Regras ({items.length})</h3>
        {items.map((r) => (
          <div key={r.id} className="border-b border-slate-100 py-2 flex justify-between">
            <span className="text-sm">{r.name} <span className="text-xs text-slate-400">· {r.field} {r.operator} {r.value} → +{r.points}</span></span>
            <button className={btnX} onClick={async () => { await api.del(`/scoring/rules/${r.id}`); reload(); }}>remover</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------- 9) FORECAST ----------------
function Forecast() {
  const [data, setData] = useState<any>(null);
  const [q, setQ] = useState({ seller_name: '', period_year: 2026, period_month: 6, target_value: 0 });
  const load = () => api.get('/forecast').then(setData).catch(() => setData(null));
  useEffect(() => { load(); }, []);
  return (
    <div className="grid md:grid-cols-3 gap-5">
      <div className={`${card} md:col-span-2`}>
        <h3 className="font-semibold mb-3">Previsão do pipeline</h3>
        {!data ? <p className="text-slate-400 text-sm">Carregando…</p> : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
              <KPI label="Pipeline aberto" value={brl(data.open_total)} />
              <KPI label="Previsão ponderada" value={brl(data.weighted_forecast)} />
              <KPI label="Ganho no mês" value={brl(data.won_this_month)} />
              <KPI label="Meta do mês" value={brl(data.month_target)} />
            </div>
            {data.attainment_pct != null && <p className="text-sm text-slate-600 mb-3">Atingimento da meta: <b>{data.attainment_pct}%</b></p>}
            <table className="w-full text-sm">
              <thead><tr className="text-left text-slate-500 border-b"><th className="py-1">Estágio</th><th>Deals</th><th>Valor</th><th>Prob.</th><th>Ponderado</th></tr></thead>
              <tbody>
                {(data.by_stage || []).map((s: any) => (
                  <tr key={s.stage} className="border-b border-slate-100"><td className="py-1.5">{s.stage}</td><td>{s.deals}</td><td>{brl(s.total_value)}</td><td>{Math.round(s.probability * 100)}%</td><td>{brl(s.weighted)}</td></tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
      <div className={card}>
        <h3 className="font-semibold mb-3">Definir meta (mês)</h3>
        <input className={inp} placeholder="Vendedor/equipe" value={q.seller_name} onChange={(e) => setQ({ ...q, seller_name: e.target.value })} />
        <div className="flex gap-2 mt-2">
          <input className={inp} type="number" placeholder="Ano" value={q.period_year} onChange={(e) => setQ({ ...q, period_year: Number(e.target.value) })} />
          <input className={inp} type="number" placeholder="Mês" value={q.period_month} onChange={(e) => setQ({ ...q, period_month: Number(e.target.value) })} />
        </div>
        <input className={`${inp} mt-2`} type="number" placeholder="Meta (R$)" value={q.target_value} onChange={(e) => setQ({ ...q, target_value: Number(e.target.value) })} />
        <button className={`${btn} mt-3`} onClick={async () => { await api.post('/quotas', q); toast.success('Meta salva'); load(); }}>Salvar meta</button>
      </div>
    </div>
  );
}

function KPI({ label, value }: { label: string; value: string }) {
  return <div className="bg-slate-50 rounded-lg p-3"><div className="text-xs text-slate-500">{label}</div><div className="text-lg font-bold text-slate-800">{value}</div></div>;
}
