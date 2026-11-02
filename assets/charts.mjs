// Chỉ trình bày số liệu Python gửi sang; không tính lại nghiệp vụ.
const colors = {ink: '#1E293B', muted: '#64748B', primary: '#00665C', good: '#15803D', bad: '#DC2626', warning: '#B45309'};
const number = (value) => new Intl.NumberFormat('vi-VN', {maximumFractionDigits: 3}).format(value);
const percent = (value) => `${number(value * 100)}%`;

export function buildConfig(kind, data) {
  if (!['bullet', 'scenarios', 'drift'].includes(kind)) throw new Error('Loại biểu đồ không hợp lệ.');
  const options = {
    responsive: true, maintainAspectRatio: false, animation: false,
    layout: {padding: {top: 30, right: 24}},
    plugins: {legend: {display: false}, tooltip: {enabled: true, titleFont: {size: 15}, bodyFont: {size: 15}}},
    scales: {
      x: {min: 0, grid: {color: '#E2E8F0'}, ticks: {color: colors.ink, font: {size: 14}}},
      y: {grid: {color: '#E2E8F0'}, ticks: {color: colors.ink, font: {size: 14}}}
    }
  };
  if (kind === 'bullet') {
    options.indexAxis = 'y';
    options.scales.x.max = Math.max(1, data.value, data.target) * 110;
    options.scales.x.title = {display: true, text: 'Năng suất (%)', color: colors.ink};
    options.plugins.tooltip.callbacks = {label: () => `Dự báo: ${percent(data.value)} · Mục tiêu: ${percent(data.target)}`};
    return {type: 'bar', data: {labels: ['Dự báo'], datasets: [{label: 'Năng suất dự báo', data: [data.value * 100], backgroundColor: data.status === 'Đạt' ? colors.good : colors.bad, barThickness: 34}]}, options};
  }
  if (kind === 'scenarios') {
    options.scales.x.title = {display: true, text: 'Điểm can thiệp (thấp hơn là ít thay đổi hơn)', color: colors.ink};
    options.scales.x.suggestedMax = 1;
    options.scales.y.min = 0;
    options.scales.y.suggestedMax = Math.max(1, data.target, ...data.points.map((p) => p.value)) * 110;
    options.scales.y.title = {display: true, text: 'Năng suất dự báo (%)', color: colors.ink};
    options.plugins.tooltip.callbacks = {label: (ctx) => {
      const point = data.points[ctx.datasetIndex];
      return `${point.name}: ${percent(point.value)} · Điểm ${number(point.effort)} · ${point.status}`;
    }};
    return {type: 'scatter', data: {datasets: data.points.map((p) => ({
      label: p.name, data: [{x: p.effort, y: p.value * 100}],
      backgroundColor: p.status === 'Đạt' ? colors.good : colors.bad,
      borderColor: p.name === data.best ? colors.primary : '#FFFFFF', borderWidth: p.name === data.best ? 3 : 1,
      pointStyle: p.name === data.best ? 'rectRot' : 'circle', pointRadius: p.name === data.best ? 10 : 7, pointHitRadius: 14
    }))}, options};
  }
  const finite = data.points.map((p) => p.score).filter((v) => v !== null);
  const limit = Math.max(1, data.threshold, ...finite) * 1.25;
  options.indexAxis = 'y';
  options.scales.x.max = limit;
  options.scales.x.title = {display: true, text: 'Độ lệch chuẩn hóa', color: colors.ink};
  options.plugins.tooltip.callbacks = {label: (ctx) => {
    const point = data.points[ctx.dataIndex];
    return `${point.unbounded ? 'Không giới hạn (độ lệch chuẩn gốc bằng 0)' : number(point.score)} · ${point.warning ? 'cảnh báo' : 'Bình thường'}`;
  }};
  return {type: 'bar', data: {labels: data.points.map((p) => p.name), datasets: [{
    label: 'Độ trôi dữ liệu', data: data.points.map((p) => p.unbounded ? limit : p.score),
    backgroundColor: data.points.map((p) => p.warning ? colors.warning : colors.primary), barThickness: 22
  }]}, options};
}

export function marker(kind, data) {
  return {axis: kind === 'scenarios' ? 'y' : 'x', value: kind === 'drift' ? data.threshold : data.target * 100,
    label: kind === 'drift' ? `Ngưỡng ${number(data.threshold)}` : `Mục tiêu ${percent(data.target)}`};
}

export function pointDetail(kind, data, index) {
  if (kind === 'bullet') return `Dự báo ${percent(data.value)} · Mục tiêu ${percent(data.target)} · ${data.status}`;
  const p = data.points[index];
  if (kind === 'scenarios') return `${p.name}: ${percent(p.value)} · Điểm can thiệp ${number(p.effort)} · ${p.status}${p.name === data.best ? ' · Được chọn' : ''}`;
  return `${p.name}: ${p.unbounded ? 'Không giới hạn (độ lệch chuẩn gốc bằng 0)' : number(p.score)} · ${p.warning ? 'cảnh báo' : 'Bình thường'}`;
}

export function mountChart(document, Chart) {
  const {kind, data} = JSON.parse(document.getElementById('chart-data').textContent);
  document.body.dataset.kind = kind;
  Chart.defaults.font.family = "Tahoma, 'DejaVu Sans', sans-serif";
  Chart.defaults.font.size = 14;
  Chart.defaults.color = colors.ink;
  const target = marker(kind, data);
  const guide = {
    id: 'targetGuide',
    beforeDraw(chart) {
      if (kind !== 'bullet') return;
      const {ctx, chartArea: area, scales} = chart;
      const cut = scales.x.getPixelForValue(data.target * 100);
      ctx.save(); ctx.fillStyle = '#FEE2E2'; ctx.fillRect(area.left, area.top, cut - area.left, area.bottom - area.top);
      ctx.fillStyle = '#DCFCE7'; ctx.fillRect(cut, area.top, area.right - cut, area.bottom - area.top); ctx.restore();
    },
    afterDraw(chart) {
      const {ctx, chartArea: area, scales} = chart;
      const pos = scales[target.axis].getPixelForValue(target.value);
      ctx.save(); ctx.strokeStyle = colors.ink; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); ctx.beginPath();
      if (target.axis === 'x') {ctx.moveTo(pos, area.top); ctx.lineTo(pos, area.bottom);}
      else {ctx.moveTo(area.left, pos); ctx.lineTo(area.right, pos);}
      ctx.stroke(); ctx.fillStyle = colors.ink; ctx.font = '14px Tahoma'; ctx.textAlign = 'right';
      ctx.fillText(target.label, area.right, area.top - 12); ctx.restore();
    }
  };
  const config = buildConfig(kind, data);
  config.plugins = [guide];
  const canvas = document.getElementById('chart');
  const chart = new Chart(canvas, config);
  const detail = document.getElementById('detail');
  const show = (index) => {
    const active = {datasetIndex: kind === 'scenarios' ? index : 0, index: kind === 'scenarios' ? 0 : index};
    chart.setActiveElements([active]);
    const point = chart.getDatasetMeta(active.datasetIndex).data[active.index];
    chart.tooltip.setActiveElements([active], {x: point.x, y: point.y});
    chart.update('none');
    detail.textContent = pointDetail(kind, data, index);
  };
  const names = kind === 'bullet' ? ['Xem dự báo và mục tiêu'] : data.points.map((p) => p.name);
  names.forEach((name, index) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = name + (kind === 'scenarios' && name === data.best ? ' · Được chọn' : '');
    button.addEventListener('click', () => show(index));
    button.addEventListener('focus', () => show(index));
    document.getElementById('controls').appendChild(button);
  });
  canvas.addEventListener('focus', () => show(0));
  detail.textContent = kind === 'bullet' ? pointDetail(kind, data, 0) : 'Chạm điểm trên biểu đồ hoặc chọn tên để xem số liệu.';
  return chart;
}

export function startChart(document, Chart) {
  try { return mountChart(document, Chart); }
  catch (error) {
    document.getElementById('detail').textContent = 'LỖI: Không thể vẽ biểu đồ. Xem số liệu ở bảng bên dưới.';
    return null;
  }
}

if (typeof document !== 'undefined') startChart(document, globalThis.Chart);
