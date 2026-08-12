(async function loadMonthlyPrices() {
  const style = document.createElement('style');
  style.textContent = `
    .live-status{margin:6px 0 18px;padding:11px 14px;border:1px solid var(--hw-border);border-left:4px solid var(--hw-orange);border-radius:8px;background:#fff;font-size:12px;color:var(--hw-ink-soft);line-height:1.6}
    .live-status b{color:var(--hw-ink)} .live-status.warn{border-left-color:#D69200;background:#FFF9E8}
    .complex-live-panel{background:#fff;border:1px solid var(--hw-border);border-radius:var(--radius);overflow:auto}
    .complex-live-table{width:100%;border-collapse:collapse;min-width:850px;font-size:12.5px}
    .complex-live-table th{padding:10px 12px;background:#F5F5F6;color:var(--hw-ink-soft);text-align:left;font-size:11px}
    .complex-live-table td{padding:11px 12px;border-top:1px solid var(--hw-border);vertical-align:middle}
    .complex-live-table .num{font-family:'IBM Plex Mono',monospace;text-align:right;font-weight:650}
    .complex-live-table a{color:#9A4400;text-decoration:none}.complex-live-table a:hover{text-decoration:underline}
    .quality{font-size:10px;font-weight:700;border-radius:999px;padding:3px 7px;white-space:nowrap}
    .quality.high{background:#E8F6EC;color:#1A8A3F}.quality.medium{background:#FFF3EA;color:#A64600}
    .quality.low,.quality.none{background:#F1F1F2;color:#6B6D72}.quality.review{background:#FFF0F0;color:#C93434}
  `;
  document.head.appendChild(style);

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const fmt = value => Number(value).toLocaleString('en-US');
  const safeUrl = value => /^https:\/\//i.test(value || '') ? value : '#';
  const qualityLabel = item => item.review_required ? ['review','변동 검토'] : ({high:['high','높음'],medium:['medium','보통'],low:['low','표본 부족'],none:['none','미확인']}[item.confidence] || ['none','미확인']);

  const page = document.querySelector('.page');
  const status = document.createElement('div');
  status.className = 'live-status';
  page.prepend(status);

  let data;
  try {
    const response = await fetch(`./data/latest.json?v=${Date.now()}`, {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = await response.json();
  } catch (error) {
    status.classList.add('warn');
    status.textContent = '자동 수집 데이터를 불러오지 못했습니다. 화면에는 기존 기준값과 예시값이 표시됩니다.';
    return;
  }

  if (!data.generated_at) {
    status.classList.add('warn');
    status.innerHTML = '<b>첫 자동 조사를 기다리는 중입니다.</b> 월간 수집이 완료되기 전까지 지도에는 기존 예시값이 표시됩니다.';
    return;
  }

  const generated = new Date(data.generated_at);
  const dateText = new Intl.DateTimeFormat('ko-KR', {timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(generated);
  const listingCount = data.collection?.listing_count || 0;
  const errorCount = data.collection?.request_error_count || 0;
  status.classList.toggle('warn', errorCount > 0 || listingCount === 0);
  status.innerHTML = `<b>${esc(data.period)} 월간 매물 호가 조사</b> · 유효 매물 ${fmt(listingCount)}건 · 요청 오류 ${fmt(errorCount)}건 · 실거래가가 아닌 공개 매물의 호가 기준입니다.`;
  const updated = document.querySelector('.updated');
  if (updated) updated.textContent = `LAST UPDATED · ${dateText.replace(/\. /g,'.').replace(/\.$/,'')}`;

  // Only samples that passed the minimum-count and anomaly gates replace map examples.
  Object.entries(data.districts || {}).forEach(([key, item]) => {
    const price = item.published_price_per_m2_iqd;
    if (!price || !districts[key]) return;
    const d = districts[key];
    d.iqd = price;
    d.verified = false;
    d.source = `자동수집 매물 호가 · ${item.sample_count}건 · ${data.period}`;

    const row = document.querySelector(`.district-row[data-key="${key}"]`);
    if (row) {
      const usd = row.querySelector('.district-price .usd');
      const iqd = row.querySelector('.district-price .iqd');
      const badge = row.querySelector('.district-badge');
      if (usd) usd.textContent = `$${fmt(Math.round(price / (data.iqd_per_usd || RATE)))}`;
      if (iqd) iqd.textContent = `${fmt(price)} IQD`;
      if (badge) badge.innerHTML = `<span class="badge verified">자동수집 · ${item.sample_count}건</span>`;
      const info = row.querySelector('.district-info');
      let meta = info?.querySelector('.meta-line');
      if (info && !meta) { meta = document.createElement('div'); meta.className = 'meta-line'; info.appendChild(meta); }
      if (meta) meta.textContent = d.source;
    }
    const usdValue = Math.round(price / (data.iqd_per_usd || RATE));
    const label = document.querySelector(`#lbl-${key} .price`);
    if (label) label.textContent = `$${fmt(usdValue)}`;
    if (polyLayers[key]) {
      const sources = (item.source_urls || []).slice(0,2).map(url => `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">출처</a>`).join(' · ');
      polyLayers[key].setTooltipContent(`<b>${esc(d.nameEn)}</b><br>${fmt(price)} IQD/m² · 표본 ${item.sample_count}건<br>${sources}`);
    }
  });

  // Refresh comparison bars after applying publishable monthly values.
  const chartRows = Array.from(document.querySelectorAll('#compare-panel .bar-row'));
  chartRows.forEach((row, index) => { if (orderedKeys[index]) row.dataset.key = orderedKeys[index]; });
  const currentMax = Math.max(...orderedKeys.map(key => districts[key]?.iqd || 0));
  orderedKeys.forEach(key => {
    const row = document.querySelector(`#compare-panel .bar-row[data-key="${key}"]`);
    if (!row) return;
    const d = districts[key];
    const priceUsd = Math.round(d.iqd / (data.iqd_per_usd || RATE));
    const fill = row.querySelector('.bar-fill');
    const value = row.querySelector('.bar-value');
    if (fill) fill.style.width = `${Math.round(d.iqd / currentMax * 100)}%`;
    if (value) value.textContent = `$${fmt(priceUsd)}`;
  });

  // Show every configured complex, including zero-result searches, so an
  // unconfirmed price is visible as "미확인" instead of silently disappearing.
  const complexes = Object.values(data.complexes || {});
  if (complexes.length) {
    const section = document.createElement('section');
    const rows = complexes.sort((a,b) => (b.observed_median_price_per_m2_iqd || 0) - (a.observed_median_price_per_m2_iqd || 0)).map(item => {
      const price = item.observed_median_price_per_m2_iqd;
      const [qualityClass, qualityText] = qualityLabel(item);
      const links = (item.source_urls || []).slice(0,3).map((url,i) => `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">매물 ${i+1}</a>`).join(' · ') || '—';
      return `<tr><td><b>${esc(item.name_kr)}</b></td><td class="num">${price ? fmt(price) : '—'} IQD</td><td class="num">${price ? '$'+fmt(Math.round(price/(data.iqd_per_usd || RATE))) : '—'}</td><td class="num">${fmt(item.sample_count)}건</td><td><span class="quality ${qualityClass}">${qualityText}</span></td><td>${links}</td></tr>`;
    }).join('');
    section.innerHTML = `<div class="section-head"><div class="section-title"><div class="bar"></div><h2>주요 아파트 단지 월간 호가</h2><span class="sub-en">AUTOMATED LISTING WATCH</span></div><div class="section-note">중앙값 · 이상치 제외 · 표본 3건 미만은 참고용</div></div><div class="complex-live-panel"><table class="complex-live-table"><thead><tr><th>단지</th><th style="text-align:right">IQD/m²</th><th style="text-align:right">USD/m²</th><th style="text-align:right">표본</th><th>신뢰도</th><th>근거 링크</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    const compareHeading = Array.from(document.querySelectorAll('.section-head')).find(node => node.querySelector('h2')?.textContent.includes('지역별 m²'));
    if (compareHeading) compareHeading.before(section); else page.appendChild(section);
  }
})();
