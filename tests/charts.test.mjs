import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {buildConfig, marker, pointDetail, mountChart, startChart} from '../assets/charts.mjs';

const bullet = {value: 1.3, target: .8, status: 'Đạt'};
const scenarios = {target: .8, best: 'Kết hợp', points: [
  {name: 'Giữ nguyên', effort: 0, value: .6, status: 'Không đạt'},
  {name: 'Kết hợp', effort: .5, value: .9, status: 'Đạt'}]};
const drift = {threshold: 2, points: [
  {name: 'Máy dừng', score: null, unbounded: true, warning: true},
  {name: 'Công nhân', score: 0, unbounded: false, warning: false}]};

function documentFor(kind, data) {
  const elements = {};
  for (const id of ['chart', 'chart-data', 'controls', 'detail']) {
    elements[id] = {events: {}, children: [], textContent: '',
      addEventListener(name, fn) {this.events[name] = fn;},
      appendChild(child) {this.children.push(child);}};
  }
  elements['chart-data'].textContent = JSON.stringify({kind, data});
  return {elements, body: {dataset: {}},
    getElementById(id) {return elements[id];},
    createElement() {return {events: {}, addEventListener(name, fn) {this.events[name] = fn;}};}};
}

class FakeChart {
  static defaults = {font: {}};
  constructor(canvas, config) {
    this.config = config;
    this.ctx = {save() {}, restore() {}, fillRect() {}, setLineDash() {}, beginPath() {}, moveTo() {}, lineTo() {}, stroke() {}, fillText() {}};
    this.chartArea = {left: 10, top: 40, bottom: 260, right: 500};
    this.scales = {x: {getPixelForValue(v) {return v;}}, y: {getPixelForValue(v) {return v;}}};
    this.tooltip = {setActiveElements() {}};
    for (const plugin of config.plugins) {plugin.beforeDraw(this); plugin.afterDraw(this);}
  }
  setActiveElements(elements) {this.active = elements;}
  getDatasetMeta() {return {data: [{x: 10, y: 10}, {x: 20, y: 20}]};}
  update() {}
}

test('Thước dự báo giữ giá trị vượt 100%, đèn và vạch mục tiêu', () => {
  const config = buildConfig('bullet', bullet);
  assert.equal(config.data.datasets[0].data[0], 130);
  assert.ok(config.options.scales.x.max > 130);
  assert.equal(config.options.animation, false);
  assert.equal(marker('bullet', bullet).value, 80);
  assert.match(config.options.plugins.tooltip.callbacks.label(), /130/);
  assert.equal(buildConfig('bullet', {...bullet, status: 'Không đạt'}).data.datasets[0].backgroundColor, '#DC2626');
  assert.equal(buildConfig('bullet', {...bullet, value: 0}).data.datasets[0].data[0], 0);
});

test('Đồ thị phương án chỉ trình bày điểm, trạng thái và phương án Python chọn', () => {
  const config = buildConfig('scenarios', scenarios);
  assert.equal(config.data.datasets.length, 2);
  assert.equal(config.data.datasets[0].data[0].x, 0);
  assert.equal(config.data.datasets[1].data[0].y, 90);
  assert.equal(config.data.datasets[1].pointStyle, 'rectRot');
  assert.equal(marker('scenarios', scenarios).axis, 'y');
  assert.match(config.options.plugins.tooltip.callbacks.label({datasetIndex: 1}), /Kết hợp/);
  assert.match(pointDetail('scenarios', scenarios, 1), /Được chọn/);
  assert.doesNotMatch(pointDetail('scenarios', scenarios, 0), /Được chọn/);
  assert.equal(buildConfig('scenarios', {...scenarios, points: [], best: null}).data.datasets.length, 0);
});

test('Drift giữ ngưỡng tùy chỉnh, phân biệt vô hạn với 0', () => {
  const config = buildConfig('drift', drift);
  assert.equal(marker('drift', drift).value, 2);
  assert.equal(config.data.datasets[0].data[0], config.options.scales.x.max);
  assert.equal(config.data.datasets[0].data[1], 0);
  assert.match(config.options.plugins.tooltip.callbacks.label({dataIndex: 0}), /Không giới hạn/);
  assert.match(config.options.plugins.tooltip.callbacks.label({dataIndex: 1}), /Bình thường/);
  assert.match(pointDetail('drift', drift, 0), /Không giới hạn/);
  assert.match(pointDetail('drift', drift, 1), /Bình thường/);
  assert.equal(buildConfig('drift', {threshold: 1, points: []}).data.datasets[0].data.length, 0);
  assert.throws(() => buildConfig('unknown', {}));
});

for (const [kind, data] of [['bullet', bullet], ['scenarios', scenarios], ['drift', drift]]) {
  test(`Tương tác chạm/bàn phím và plugin vạch ngưỡng: ${kind}`, () => {
    const document = documentFor(kind, data);
    const chart = mountChart(document, FakeChart);
    const buttons = document.elements.controls.children;
    assert.ok(buttons.length > 0);
    for (const button of buttons) {button.events.focus(); button.events.click();}
    document.elements.chart.events.focus();
    assert.equal(document.body.dataset.kind, kind);
    assert.ok(chart.active.length);
    assert.match(document.elements.detail.textContent, /Dự báo|Giữ nguyên|Máy dừng/);
  });
}

test('Khởi tạo và lỗi hiển thị đều có phản hồi tiếng Việt', () => {
  const successDocument = documentFor('bullet', bullet);
  assert.ok(startChart(successDocument, FakeChart));
  assert.equal(successDocument.body.dataset.kind, 'bullet');
  const failureDocument = documentFor('bullet', bullet);
  assert.equal(startChart(failureDocument, undefined), null);
  assert.match(failureDocument.elements.detail.textContent, /LỖI: Không thể vẽ biểu đồ/);
});

test('Cấu hình tương thích Chart.js 4.6.1 cục bộ bằng Canvas giả lập', () => {
  const require = createRequire(import.meta.url);
  const Chart = require('../assets/chart.umd.min.js');
  assert.equal(Chart.version, '4.6.1');
  for (const [kind, data] of [['bullet', bullet], ['scenarios', scenarios], ['drift', drift]]) {
    const canvas = {width: 800, height: 400, getContext() {return context;}};
    const context = new Proxy({canvas, measureText(text) {return {width: String(text).length * 8};},
      getLineDash() {return [];}}, {get(target, name) {return target[name] ?? (() => {});}});
    const config = buildConfig(kind, data);
    config.options.responsive = false;
    const chart = new Chart(canvas, config);
    assert.ok(chart.chartArea.width > 0);
    chart.destroy();
  }
});
