import json
import math
import re
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import pandas as pd
import pytest
import ui


def chart_data(html):
    raw = re.search(r'<script type="application/json" id="chart-data">(.*?)</script>', html, re.S).group(1)
    return json.loads(raw)


@pytest.mark.parametrize('kind,data', [
    ('bullet', {'value': 1.3, 'target': .8, 'status': 'Đạt'}),
    ('scenarios', {'target': .8, 'best': None, 'points': []}),
    ('drift', {'threshold': 1., 'points': []})])
def test_offline_chart_document(kind, data):
    html = ui.chart_html(kind, data)
    assert chart_data(html) == {'kind': kind, 'data': data}
    class Resources(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            assert tag != 'script' or 'src' not in attrs
            assert tag != 'link'
    Resources().feed(html)
    assert '<html lang="vi">' in html
    assert 'aria-live="polite"' in html and 'tabindex="0"' in html
    assert 'Chart.js v4.6.1' in html
    assert 'animation: false' in html


def test_chart_data_cannot_inject_html():
    attack = '</script><img src=x onerror=alert(1)>& ệ ữ ẫ ổ'
    html = ui.chart_html('scenarios', {'name': attack})
    assert attack not in html
    assert chart_data(html)['data']['name'] == attack
    assert '<img' not in html
    with pytest.raises(ValueError): ui.chart_html('unknown', {})
    with pytest.raises(ValueError): ui.chart_html('bullet', {'value': float('nan')})


def test_scenarios_are_passed_through_without_recalculation():
    row = {'name': 'Tăng ca', 'effort': .12, 'value': 1.4, 'status': 'Đạt', 'inputs': {}}
    payload = ui.scenario_payload([row], .8, 'Tăng ca')
    assert payload['points'][0] == {k: row[k] for k in ['name', 'effort', 'value', 'status']}
    assert payload['best'] == 'Tăng ca' and payload['target'] == .8
    assert ui.scenario_payload([], .8, None)['points'] == []


def test_drift_infinity_is_explicit_and_valid_json():
    frame = pd.DataFrame([{'Biến': 'Máy dừng', 'Mức lệch': float('inf'), 'Nhãn': 'cảnh báo'},
                          {'Biến': 'Công nhân', 'Mức lệch': 0., 'Nhãn': 'Bình thường'}])
    data = ui.drift_payload(frame, 2.)
    assert data['points'][0] == {'name': 'Máy dừng', 'score': None, 'unbounded': True, 'warning': True}
    assert data['points'][1]['score'] == 0
    assert data['threshold'] == 2
    assert chart_data(ui.chart_html('drift', data))['data'] == data
    assert ui.drift_payload(frame.iloc[:0], 1.)['points'] == []


def test_selection_badge_escapes_text_and_empty_state():
    assert 'Chưa có phương án' in ui.selection_badge(None, None)
    html = ui.selection_badge('<script>bad</script>', 0.)
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'Được chọn' in html and '0.000' in html


@pytest.mark.parametrize('base,position', [(2., 0), (31., 50), (60., 100)])
def test_slider_marks(base, position):
    html = ui.slider_marks(2., 60., base)
    assert f'left:{position:.6f}%' in html
    assert f'Đầu ca: {base:g}' in html and 'Tối đa: 60' in html


@pytest.mark.parametrize('low,high,base', [(2,60,1), (2,60,61), (2,2,2), (2,60,float('nan'))])
def test_invalid_slider_marks(low,high,base):
    with pytest.raises(ValueError): ui.slider_marks(low,high,base)


def test_protected_source_files_unchanged():
    root = Path(__file__).parents[1]
    manifest = json.loads((root / 'source_hashes.json').read_text(encoding='utf-8'))
    if not all((root.parent/name).is_file() for name in manifest):
        pytest.skip('NOT RUN: bộ tài liệu gốc ở thư mục cha không nằm trong bản clone; dataset đóng gói có test riêng.')
    for name, expected in manifest.items():
        assert hashlib.sha256((root.parent/name).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize('front,back', [('#1E293B','#F8F9FA'),('#64748B','#F8F9FA'),
    ('#64748B','#FFFFFF'),('#FFFFFF','#00665C'),('#166534','#DCFCE7'),
    ('#92400E','#F8F9FA'),('#15803D','#FFFFFF'),('#DC2626','#FFFFFF')])
def test_text_contrast(front,back):
    def luminance(color):
        rgb = [int(color[i:i+2],16)/255 for i in (1,3,5)]
        linear = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
        return sum(v*w for v,w in zip(linear,[.2126,.7152,.0722]))
    low,high = sorted([luminance(front),luminance(back)])
    assert (high+.05)/(low+.05) >= 4.5


@pytest.mark.parametrize('original_exists,bundled_exists', [(True,True),(False,True),(False,False)])
def test_dataset_path_for_local_and_clean_clone(tmp_path,original_exists,bundled_exists):
    import config
    project = tmp_path / 'project'
    project.mkdir()
    original = tmp_path / 'Bộ dữ liệu - Nhóm 6.xlsx'
    bundled = project / 'dataset' / original.name
    if original_exists:
        original.write_bytes(b'original')
    if bundled_exists:
        bundled.parent.mkdir()
        bundled.write_bytes(b'bundled')
    assert config.dataset_path(project) == (original if original_exists else bundled)
    if not original_exists and not bundled_exists:
        from data import load_data
        with pytest.raises(FileNotFoundError): load_data(config.dataset_path(project))


def test_bundled_dataset_matches_source_manifest():
    root = Path(__file__).parents[1]
    manifest = json.loads((root/'source_hashes.json').read_text(encoding='utf-8'))
    name = 'Bộ dữ liệu - Nhóm 6.xlsx'
    assert hashlib.sha256((root/'dataset'/name).read_bytes()).hexdigest() == manifest[name]
