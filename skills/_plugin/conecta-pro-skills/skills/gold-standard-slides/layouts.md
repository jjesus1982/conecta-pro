# Layouts prontos — Conecta Mais

Receitas HTML dos slides. Classes vêm de `brand.css`. Fontes no `<head>`:

```html
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@700;800;900&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
```

Logo: embutir base64 dos assets da skill (`base64 -w0 <skill>/assets/<arquivo>.png` → `<img src="data:image/png;base64,...">`).
REGRA: em slide dark, logo SEMPRE dentro do `.logo-badge` branco usando `assets/logo-clara-fundo.png` (a completa: ícones + CONECTA MAIS + tagline). `assets/logo-sem-fundo.png` tem o "CONECTA" BRANCO — some em fundo claro/badge; só serve solta sobre fundo dark. Em slide claro, `logo-clara-fundo.png` direto.

Nota: as fontes vêm do Google Fonts — apresentação ao vivo precisa de internet (sem rede cai em fonte de sistema). Se o local for sem sinal, exportar o PDF antes.

## 1. CAPA (dark, sem rodapé; `<div class="atmosfera">` = anel da marca)
```html
<section class="slide dark active" style="display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:28px">
    <div class="atmosfera"></div>
    <div class="reveal logo-badge"><img src="data:image/png;base64,LOGO_CLARA" style="height:150px" alt="Conecta Mais"></div>
    <div class="reveal eyebrow">Segurança Patrimonial &amp; Eletrônica</div>
    <h1 class="reveal" style="font-family:var(--font-display);font-weight:900;font-size:var(--title-capa);line-height:1.04;max-width:1500px">
        Título com <span style="color:var(--laranja)">destaque laranja</span></h1>
    <p class="reveal" style="font-size:var(--subtitle);color:var(--texto-secundario-dark);max-width:1100px">Subtítulo — cliente/ocasião — Manaus/AM</p>
</section>
```

## 2. SLIDE INTERNO (claro, base de todos)
```html
<section class="slide">
    <div class="reveal eyebrow">Rótulo da seção</div>
    <div class="reveal titulo-slide"><h2>Título do slide</h2></div>
    <!-- conteúdo -->
    <footer class="rodape-marca"><span>Conecta Mais — Tecnologia para quem protege</span><span class="num">2 / 7</span></footer>
</section>
```

## 3. KPI (máx 4 cartões; número em 1 LINHA: "R$ 272k", nunca "R$ 272 mil" quebrado)
```html
<div class="kpi-grid" style="margin-top:48px">
    <div class="reveal kpi-card"><div class="valor">56</div><div class="rotulo">Colaboradores</div></div>
    <div class="reveal kpi-card"><div class="valor">12</div><div class="rotulo">Postos ativos</div></div>
    <div class="reveal kpi-card"><div class="valor">19</div><div class="rotulo">Clientes</div></div>
    <div class="reveal kpi-card"><div class="valor"><span class="unidade">R$</span> 272<span class="unidade">k</span></div><div class="rotulo">Receita mensal</div></div>
</div>
```

## 4. COMPARATIVO (2 opções + coluna destacada = a que recomendamos)
```html
<table class="comparativo reveal" style="margin-top:40px">
    <tr><th></th><th>Portaria presencial</th><th class="col-destaque">Portaria remota</th></tr>
    <tr><td>Custo mensal</td><td>Equipe 24h no posto</td><td class="col-destaque"><strong>Redução de até 60%</strong></td></tr>
    <!-- máx 5 linhas; célula máx 8 palavras -->
</table>
```

## 5. PROPOSTA (preço + entregáveis)
```html
<div style="display:grid;grid-template-columns:1.1fr .9fr;gap:56px;margin-top:40px;align-items:start">
    <div class="reveal proposta-card">
        <header>Plano Portaria Remota</header>
        <div style="padding:36px 40px">
            <div class="preco">R$ 8.900<span style="font-size:34px;color:var(--azul-medio)">/mês</span></div>
            <ul style="margin-top:24px"><li>Central 24h dedicada</li><li>CFTV integrado</li></ul>
        </div>
    </div>
    <div class="reveal"><!-- condições, validade, observações --></div>
</div>
```

## 6. CONTATO (dark, fecha o deck)
```html
<section class="slide dark" style="display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;gap:32px">
    <div class="atmosfera"></div>
    <div class="reveal logo-badge"><img src="data:image/png;base64,LOGO_CLARA" style="height:110px" alt="Conecta Mais"></div>
    <h2 class="reveal" style="font-family:var(--font-display);font-weight:800;font-size:72px">Vamos proteger o seu condomínio?</h2>
    <div class="reveal cta">comercial@conectapro.com.br</div>
    <p class="reveal" style="font-size:26px;color:var(--texto-secundario-dark)">Manaus/AM — Tecnologia para quem protege</p>
</section>
```

## 7. GRÁFICO (quando houver série/percentual)
SVG inline seguindo a skill `dataviz` (invocá-la antes). Cores: série principal `var(--azul-medio)`, destaque `var(--laranja)`, grid `#E2E8F0`. Sem gráfico de pizza >4 fatias; rótulo direto na barra (sem legenda quando <4 séries).

## Controller JS (colar em todo deck)
```html
<script>
class Deck{constructor(){this.s=[...document.querySelectorAll('.slide')];this.i=0;this.st=document.getElementById('deckStage');
this.scale();addEventListener('resize',()=>this.scale());
addEventListener('keydown',e=>{if(['ArrowRight','PageDown',' '].includes(e.key)){e.preventDefault();this.go(this.i+1)}
if(['ArrowLeft','PageUp'].includes(e.key)){e.preventDefault();this.go(this.i-1)}});
let x0=null;addEventListener('touchstart',e=>x0=e.touches[0].clientX);
addEventListener('touchend',e=>{if(x0==null)return;const d=e.changedTouches[0].clientX-x0;
if(Math.abs(d)>60)this.go(this.i+(d<0?1:-1));x0=null});this.go(0)}
scale(){const f=Math.min(innerWidth/1920,innerHeight/1080);
this.st.style.transform=`translate(${(innerWidth-1920*f)/2}px,${(innerHeight-1080*f)/2}px) scale(${f})`}
go(n){this.i=Math.max(0,Math.min(n,this.s.length-1));
this.s.forEach((s,j)=>{s.classList.toggle('active',j===this.i);s.classList.toggle('visible',j===this.i)});
document.querySelectorAll('.nav-dots span').forEach((d,j)=>d.classList.toggle('on',j===this.i))}}
new Deck();
</script>
```
