(async function loadMonthlyPrices() {
  const style = document.createElement('style');
  style.textContent = `
    .live-status{margin:6px 0 14px;padding:11px 14px;border:1px solid var(--hw-border);border-left:4px solid var(--hw-orange);border-radius:8px;background:#fff;font-size:12px;color:var(--hw-ink-soft);line-height:1.6}
    .live-status b{color:var(--hw-ink)} .live-status.warn{border-left-color:#D69200;background:#FFF9E8}
    .price-basis-guide{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px}
    .price-basis-card{padding:13px 15px;border:1px solid var(--hw-border);border-radius:9px;background:#fff}
    .price-basis-card.official{border-left:4px solid #777A80}.price-basis-card.market{border-left:4px solid var(--hw-orange)}
    .price-basis-card b{display:block;font-size:13px;margin-bottom:4px}.price-basis-card span{display:block;font-size:11.5px;line-height:1.55;color:var(--hw-ink-soft)}
    .complex-live-panel{background:#fff;border:1px solid var(--hw-border);border-radius:var(--radius);overflow:auto}
    .complex-live-table{width:100%;border-collapse:collapse;min-width:850px;font-size:12.5px}
    .complex-live-table th{padding:10px 12px;background:#F5F5F6;color:var(--hw-ink-soft);text-align:left;font-size:11px}
    .complex-live-table td{padding:11px 12px;border-top:1px solid var(--hw-border);vertical-align:middle}
    .complex-live-table .num{font-family:'IBM Plex Mono',monospace;text-align:right;font-weight:650}
    .complex-live-table a,.official-source-link{color:#9A4400;text-decoration:none}.complex-live-table a:hover,.official-source-link:hover{text-decoration:underline}
    .quality{font-size:10px;font-weight:700;border-radius:999px;padding:3px 7px;white-space:nowrap}
    .quality.high{background:#E8F6EC;color:#1A8A3F}.quality.medium{background:#FFF3EA;color:#A64600}
    .quality.low,.quality.none{background:#F1F1F2;color:#6B6D72}.quality.review{background:#FFF0F0;color:#C93434}
    .history-panel{background:#fff;border:1px solid var(--hw-border);border-radius:var(--radius);padding:18px 20px}
    .history-controls{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
    .history-controls label{font-size:11px;font-weight:700;color:var(--hw-ink-soft)}
    .history-controls select{min-width:250px;border:1px solid var(--hw-border);border-radius:7px;background:#fff;padding:8px 34px 8px 10px;font:600 12px 'Pretendard',sans-serif;color:var(--hw-ink)}
    .history-legend{display:flex;align-items:center;gap:16px;flex-wrap:wrap;margin-left:auto;font-size:10.5px;color:var(--hw-ink-soft)}
    .history-legend i{display:inline-block;width:24px;height:3px;margin-right:5px;vertical-align:2px;border-radius:2px;background:var(--hw-orange)}
    .history-legend i.official{height:0;border-top:2px dashed #777A80;background:none}
    .history-chart-wrap{width:100%;min-height:320px;overflow-x:auto;border-top:1px solid var(--hw-border);padding-top:8px}
    .history-chart{display:block;width:100%;min-width:680px;height:auto}
    .history-empty{min-height:260px;display:flex;align-items:center;justify-content:center;text-align:center;color:var(--hw-ink-soft);font-size:12px;line-height:1.7}
    .history-summary{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
    .history-chip{padding:6px 8px;border-radius:6px;background:#F5F5F6;font:10.5px 'IBM Plex Mono',monospace;color:var(--hw-ink-soft)}
    .history-chip b{color:var(--hw-ink)}.history-note{margin-top:10px;font-size:10.8px;line-height:1.6;color:var(--hw-ink-soft)}
    @media(max-width:760px){.price-basis-guide{grid-template-columns:1fr}.history-legend{width:100%;margin-left:0}.history-controls select{width:100%;min-width:0}}
  `;
  document.head.appendChild(style);

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const fmt = value => Number(value).toLocaleString('en-US');
  const safeUrl = value => /^https:\/\//i.test(value || '') ? value : '#';
  const qualityLabel = item => item.review_required ? ['review','변동 검토'] : ({high:['high','높음'],medium:['medium','보통'],low:['low','표본 부족'],none:['none','미확인']}[item.confidence] || ['none','미확인']);
  const page = document.querySelector('.page');
  if (!page) return;

  function relabelPriceBasis() {
    const disclaimer = document.querySelector('.disclaimer');
    if (disclaimer) disclaimer.innerHTML = '※ <b>비스마야 NIC 직접분양 기준가격</b>과 <b>민간 중고·전매시장 매물 호가</b>는 서로 다른 가격입니다. 공식 분양가는 별도 회색 기준가로, 시장 호가는 월간 자동 수집값으로 분리 표시합니다. 시장 호가는 계약 체결가가 아닙니다.';
    const headings = Array.from(document.querySelectorAll('.section-head'));
    const officialHead = headings.find(node => node.querySelector('h2')?.textContent.includes('비스마야'));
    if (officialHead) {
      officialHead.querySelector('h2').textContent = '비스마야 NIC 직접분양 기준가격';
      const sub = officialHead.querySelector('.sub-en');
      if (sub) sub.textContent = 'OFFICIAL ALLOCATION PRICE · NOT MARKET PRICE';
      const badge = officialHead.querySelector('.badge');
      if (badge) badge.textContent = 'NIC 협의·은행 고지 가격';
    }
    const officialRow = document.querySelector('.bismayah-row');
    const note = officialRow?.nextElementSibling;
    if (note?.classList.contains('section-note')) note.textContent = '직접분양 등록 연도별 기준가격: 기존 $630/m² → 2024년 등록자 $714/m² → 2025년 등록자 $750/m². 민간 중고·전매시장 시세가 아닙니다.';
  }

  function renderBasisGuide(anchor) {
    const guide = document.createElement('div');
    guide.className = 'price-basis-guide';
    guide.innerHTML = `
      <div class="price-basis-card official"><b>NIC 직접분양 기준가격</b><span>NIC와 금융기관이 신규 등록자에게 정한 공급·대출 기준가격입니다. 시장에서 매월 형성되는 가격이 아니며 공식 변경 고지가 있을 때만 갱신합니다.</span></div>
      <div class="price-basis-card market"><b>민간시장 매물 호가</b><span>중고·전매 매도자가 공개한 가격을 정제한 월별 중앙값입니다. 실제 계약 체결가와 차이가 날 수 있으며 표본 수와 출처를 함께 확인해야 합니다.</span></div>`;
    anchor.after(guide);
  }

  function renderOfficialCards(official) {
    const reference = official?.current_reference;
    if (!reference) return;
    document.querySelectorAll('.bismayah-row .unit-card').forEach((card, index) => {
      const size = reference.sizes_m2?.[index];
      if (!size) return;
      const usd = card.querySelector('.price-primary .usd');
      const iqd = card.querySelector('.price-secondary .iqd');
      const meta = card.querySelector('.unit-meta');
      const source = card.querySelector('.unit-source');
      if (usd) usd.textContent = fmt(reference.price_per_m2_usd);
      if (iqd) iqd.textContent = fmt(reference.price_per_m2_iqd);
      if (meta) meta.innerHTML = `<span>공식 총액 <b>$${fmt(reference.price_per_m2_usd * size)}</b> · ${fmt(reference.price_per_m2_iqd * size)} IQD</span>`;
      if (source) source.innerHTML = `출처: ${esc(reference.source_label)} · <a class="official-source-link" href="${esc(safeUrl(reference.source_url))}" target="_blank" rel="noopener">원문</a>`;
    });
  }

  function normalizedPeriod(entry) {
    return entry?.period || (typeof entry?.date === 'string' ? entry.date.slice(0, 7) : null);
  }

  function seriesValue(entry, target) {
    const [kind, key, size] = target.split(':');
    if (kind === 'bismayah') {
      const complex = entry.complexes?.bismayah;
      if (size) return complex?.by_size_m2?.[size] || null;
      if (complex) return complex;
      if (entry.districts?.bismayah) return entry.districts.bismayah;
      const legacy = entry.by_district?.bismayah;
      return legacy ? {observed_median_price_per_m2_iqd:legacy.avg_price_per_m2_iqd,sample_count:legacy.sample_count,confidence:'legacy',legacy:true} : null;
    }
    if (kind === 'complex') return entry.complexes?.[key] || null;
    if (kind === 'district') {
      if (entry.districts?.[key]) return entry.districts[key];
      const legacy = entry.by_district?.[key];
      return legacy ? {observed_median_price_per_m2_iqd:legacy.avg_price_per_m2_iqd,sample_count:legacy.sample_count,confidence:'legacy',legacy:true} : null;
    }
    return null;
  }

  function collectTargets(entries, latest) {
    const complexes = new Map();
    const districtKeys = new Set();
    [...entries, latest].filter(Boolean).forEach(entry => {
      Object.entries(entry.complexes || {}).forEach(([key, value]) => complexes.set(key, value.name_kr || key));
      Object.keys(entry.districts || entry.by_district || {}).forEach(key => districtKeys.add(key));
    });
    const options = [
      {value:'bismayah:all',label:'비스마야 민간시장 · 전체'},
      {value:'bismayah:all:100',label:'비스마야 민간시장 · 100㎡'},
      {value:'bismayah:all:120',label:'비스마야 민간시장 · 120㎡'},
      {value:'bismayah:all:140',label:'비스마야 민간시장 · 140㎡'},
    ];
    [...complexes.entries()].filter(([key]) => key !== 'bismayah').sort((a,b) => a[1].localeCompare(b[1], 'ko')).forEach(([key,name]) => options.push({value:`complex:${key}`,label:`${name} · 민간시장`}));
    [...districtKeys].filter(key => key !== 'bismayah').sort().forEach(key => options.push({value:`district:${key}`,label:`${districts?.[key]?.nameKr || key} · 지역시장`}));
    return options;
  }

  function axisLabel(value) {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
    return `${Math.round(value / 1_000)}K`;
  }

  function renderHistoryChart(entries, latest, official) {
    const officialRow = document.querySelector('.bismayah-row');
    const officialNote = officialRow?.nextElementSibling;
    if (!officialRow) return;
    const section = document.createElement('section');
    section.innerHTML = `<div class="section-head"><div class="section-title"><div class="bar"></div><h2>월별 민간시장 호가 추이</h2><span class="sub-en">MONTHLY PRIVATE-MARKET TREND</span></div><div class="section-note">월별 중앙값 · IQD/m²</div></div><div class="history-panel"><div class="history-controls"><label for="history-target">조회 대상</label><select id="history-target"></select><div class="history-legend"><span><i></i>민간시장 호가</span><span><i class="official"></i>NIC 직접분양 기준가</span></div></div><div id="history-chart-wrap" class="history-chart-wrap"></div><div id="history-summary" class="history-summary"></div><div class="history-note">민간시장 값은 공개 매물의 중앙 호가이며 실거래가가 아닙니다. 기존 2026년 8월 자료는 검증 전 참고값으로 표시되고, 첫 자동 수집이 완료되면 같은 달의 검증 수집값으로 교체됩니다. 표본이 적은 달은 추세 판단에 주의하십시오.</div></div>`;
    (officialNote || officialRow).after(section);

    const select = section.querySelector('#history-target');
    const wrap = section.querySelector('#history-chart-wrap');
    const summary = section.querySelector('#history-summary');
    const historyEntries = [...entries];
    if (latest?.generated_at && !historyEntries.some(entry => normalizedPeriod(entry) === latest.period && entry.generated_at === latest.generated_at)) historyEntries.push(latest);
    const options = collectTargets(historyEntries, latest);
    select.innerHTML = options.map(option => `<option value="${esc(option.value)}">${esc(option.label)}</option>`).join('');

    function draw() {
      const target = select.value;
      const byPeriod = new Map();
      historyEntries.forEach(entry => {
        const period = normalizedPeriod(entry);
        const value = seriesValue(entry, target);
        const price = value?.observed_median_price_per_m2_iqd ?? value?.published_price_per_m2_iqd;
        if (!period || !price) return;
        const point = {period,price:Number(price),sampleCount:value.sample_count || 0,legacy:Boolean(value.legacy),schema:entry.schema_version || 0};
        const previous = byPeriod.get(period);
        if (!previous || point.schema >= previous.schema) byPeriod.set(period, point);
      });
      const points = [...byPeriod.values()].sort((a,b) => a.period.localeCompare(b.period));
      if (!points.length) {
        wrap.innerHTML = '<div class="history-empty">아직 이 대상의 유효한 월간 가격이 없습니다.<br>자동 수집에서 표본이 확인되면 이곳에 월별로 누적됩니다.</div>';
        summary.innerHTML = '';
        return;
      }
      const width=900,height=320,left=76,right=28,top=30,bottom=55;
      const officialPrice = target.startsWith('bismayah:') ? Number(official?.current_reference?.price_per_m2_iqd || 0) : 0;
      const values = points.map(point => point.price).concat(officialPrice ? [officialPrice] : []);
      let min=Math.min(...values),max=Math.max(...values);
      const pad=Math.max((max-min)*0.18,max*0.08,50_000);
      min=Math.max(0,min-pad);max+=pad;
      const x=index => points.length===1 ? (left+width-right)/2 : left+index*(width-left-right)/(points.length-1);
      const y=value => top+(max-value)*(height-top-bottom)/(max-min);
      const grid=Array.from({length:5},(_,index)=>{const value=min+(max-min)*index/4;const yy=y(value);return `<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" stroke="#E7E7E9"/><text x="${left-10}" y="${yy+4}" text-anchor="end" font-size="10" fill="#6B6D72">${axisLabel(value)}</text>`;}).join('');
      const path=points.map((point,index)=>`${index?'L':'M'} ${x(index)} ${y(point.price)}`).join(' ');
      const market=points.length>1?`<path d="${path}" fill="none" stroke="#FF6100" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`:'';
      const officialLine=officialPrice?`<line x1="${left}" y1="${y(officialPrice)}" x2="${width-right}" y2="${y(officialPrice)}" stroke="#777A80" stroke-width="2" stroke-dasharray="7 6"/><text x="${width-right}" y="${y(officialPrice)-7}" text-anchor="end" font-size="10.5" font-weight="700" fill="#5F6267">NIC 기준 ${fmt(officialPrice)} IQD/m²</text>`:'';
      const pointNodes=points.map((point,index)=>`<g><circle cx="${x(index)}" cy="${y(point.price)}" r="5" fill="${point.legacy?'#fff':'#FF6100'}" stroke="#FF6100" stroke-width="2"><title>${point.period} · ${fmt(point.price)} IQD/m² · 표본 ${point.sampleCount}건${point.legacy?' · 기존 참고값':''}</title></circle><text x="${x(index)}" y="${height-bottom+23}" text-anchor="middle" font-size="10.5" fill="#6B6D72">${point.period.replace('-','.')}</text><text x="${x(index)}" y="${y(point.price)-11}" text-anchor="middle" font-size="10" font-weight="700" fill="#A64600">${axisLabel(point.price)}</text></g>`).join('');
      wrap.innerHTML=`<svg class="history-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="월별 민간시장 호가 추이">${grid}${officialLine}${market}${pointNodes}<text x="12" y="18" font-size="10" fill="#6B6D72">IQD/m²</text></svg>`;
      summary.innerHTML=points.slice(-12).map(point=>`<span class="history-chip"><b>${esc(point.period)}</b> ${fmt(point.price)} · ${point.sampleCount}건${point.legacy?' · 기존 참고':''}</span>`).join('');
    }
    select.addEventListener('change', draw);
    draw();
  }

  relabelPriceBasis();
  const status = document.createElement('div');
  status.className = 'live-status';
  page.prepend(status);
  renderBasisGuide(status);

  async function fetchJson(path, fallback) {
    try {
      const response = await fetch(`${path}?v=${Date.now()}`, {cache:'no-store'});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (_) { return fallback; }
  }

  const [data, history, official] = await Promise.all([
    fetchJson('./data/latest.json', null),
    fetchJson('./data/history.json', []),
    fetchJson('./data/official-prices.json', null),
  ]);
  renderOfficialCards(official);
  renderHistoryChart(Array.isArray(history) ? history : [], data, official);

  if (!data) {
    status.classList.add('warn');
    status.textContent = '자동 수집 데이터를 불러오지 못했습니다. 기존 기준가격과 저장된 월별 이력만 표시합니다.';
    return;
  }
  if (!data.generated_at) {
    status.classList.add('warn');
    status.innerHTML = '<b>첫 자동 조사를 기다리는 중입니다.</b> 기존 2026년 8월 참고값은 그래프에 남기되, 지도에는 조사 전 예시값이 표시됩니다.';
    return;
  }

  const generated=new Date(data.generated_at);
  const dateText=new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(generated);
  const listingCount=data.collection?.listing_count||0;
  const errorCount=data.collection?.request_error_count||0;
  status.classList.toggle('warn',errorCount>0||listingCount===0);
  status.innerHTML=`<b>${esc(data.period)} 민간시장 월간 매물 호가 조사</b> · 유효 매물 ${fmt(listingCount)}건 · 요청 오류 ${fmt(errorCount)}건 · NIC 직접분양 기준가격과 분리된 값입니다.`;
  const updated=document.querySelector('.updated');
  if(updated) updated.textContent=`LAST UPDATED · ${dateText.replace(/\. /g,'.').replace(/\.$/,'')}`;

  Object.entries(data.districts||{}).forEach(([key,item])=>{
    const price=item.published_price_per_m2_iqd;
    if(!price||!districts[key]) return;
    const d=districts[key];d.iqd=price;d.verified=false;d.source=`민간시장 자동수집 호가 · ${item.sample_count}건 · ${data.period}`;
    const row=document.querySelector(`.district-row[data-key="${key}"]`);
    if(row){
      const usd=row.querySelector('.district-price .usd');const iqd=row.querySelector('.district-price .iqd');const badge=row.querySelector('.district-badge');
      if(usd)usd.textContent=`$${fmt(Math.round(price/(data.iqd_per_usd||RATE)))}`;if(iqd)iqd.textContent=`${fmt(price)} IQD`;if(badge)badge.innerHTML=`<span class="badge verified">시장호가 · ${item.sample_count}건</span>`;
      const info=row.querySelector('.district-info');let meta=info?.querySelector('.meta-line');if(info&&!meta){meta=document.createElement('div');meta.className='meta-line';info.appendChild(meta);}if(meta)meta.textContent=d.source;
    }
    const label=document.querySelector(`#lbl-${key} .price`);if(label)label.textContent=`$${fmt(Math.round(price/(data.iqd_per_usd||RATE)))}`;
    if(polyLayers[key]){const sources=(item.source_urls||[]).slice(0,2).map(url=>`<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">출처</a>`).join(' · ');polyLayers[key].setTooltipContent(`<b>${esc(d.nameEn)}</b><br>${fmt(price)} IQD/m² · 민간 호가 표본 ${item.sample_count}건<br>${sources}`);}
  });

  const chartRows=Array.from(document.querySelectorAll('#compare-panel .bar-row'));
  chartRows.forEach((row,index)=>{if(orderedKeys[index])row.dataset.key=orderedKeys[index];});
  const currentMax=Math.max(...orderedKeys.map(key=>districts[key]?.iqd||0));
  orderedKeys.forEach(key=>{const row=document.querySelector(`#compare-panel .bar-row[data-key="${key}"]`);if(!row)return;const d=districts[key];const priceUsd=Math.round(d.iqd/(data.iqd_per_usd||RATE));const fill=row.querySelector('.bar-fill');const value=row.querySelector('.bar-value');if(fill)fill.style.width=`${Math.round(d.iqd/currentMax*100)}%`;if(value)value.textContent=`$${fmt(priceUsd)}`;});

  const complexes=Object.values(data.complexes||{});
  if(complexes.length){
    const section=document.createElement('section');
    const rows=complexes.sort((a,b)=>(b.observed_median_price_per_m2_iqd||0)-(a.observed_median_price_per_m2_iqd||0)).map(item=>{const price=item.observed_median_price_per_m2_iqd;const[qualityClass,qualityText]=qualityLabel(item);const links=(item.source_urls||[]).slice(0,3).map((url,i)=>`<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">매물 ${i+1}</a>`).join(' · ')||'—';return `<tr><td><b>${esc(item.name_kr)}</b></td><td class="num">${price?fmt(price):'—'} IQD</td><td class="num">${price?'$'+fmt(Math.round(price/(data.iqd_per_usd||RATE))):'—'}</td><td class="num">${fmt(item.sample_count)}건</td><td><span class="quality ${qualityClass}">${qualityText}</span></td><td>${links}</td></tr>`;}).join('');
    section.innerHTML=`<div class="section-head"><div class="section-title"><div class="bar"></div><h2>주요 아파트 단지 민간시장 월간 호가</h2><span class="sub-en">PRIVATE-MARKET LISTING WATCH</span></div><div class="section-note">중앙값 · 이상치 제외 · 표본 3건 미만은 참고용</div></div><div class="complex-live-panel"><table class="complex-live-table"><thead><tr><th>단지</th><th style="text-align:right">IQD/m²</th><th style="text-align:right">USD/m²</th><th style="text-align:right">표본</th><th>신뢰도</th><th>근거 링크</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    const compareHeading=Array.from(document.querySelectorAll('.section-head')).find(node=>node.querySelector('h2')?.textContent.includes('지역별 m²'));
    if(compareHeading)compareHeading.before(section);else page.appendChild(section);
  }
})();
