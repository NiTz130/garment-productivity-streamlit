from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
import config
from data import load_data
from store import save_log

@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'MODEL',tmp_path/'model.joblib')
    monkeypatch.setattr(config,'DB',tmp_path/'logs.sqlite')
    return AppTest.from_file(str(Path(__file__).parents[1]/'app.py'),default_timeout=30).run()

def button(app,label):
    return next(b for b in app.button if b.label==label)

def test_app_flow(app):
    assert not app.exception
    assert len(app.tabs)==4
    assert len(app.selectbox(key='product').options)==70
    button(app,'Dự báo năng suất').click().run()
    assert len(app.metric)==4 and not app.exception
    app.slider[0].set_value(40.).run()
    assert len(app.dataframe[0].value)==5
    app.text_input(key='team').set_value('Tổ giao diện')
    button(app,'Lưu nhật ký').click().run()
    assert any('Đã lưu' in x.value for x in app.success)
    assert len(app.dataframe[-1].value)==6
    button(app,'Huấn luyện lại').click().run()
    assert any('ít nhất 30' in x.value for x in app.error)
    button(app,'Quay lại bản cũ').click().run()
    assert any('Chưa có' in x.value for x in app.error)
    app.number_input(key='base_workers').set_value(-1.).run()
    button(app,'Dự báo năng suất').click().run()
    assert not app.metric and any('phải từ' in x.value for x in app.error)
    app.number_input(key='base_workers').set_value(61.).run()
    button(app,'Dự báo năng suất').click().run()
    assert len(app.metric)==3
    assert any('thanh trượt' in x.value for x in app.info)

def test_app_log_errors(app):
    button(app,'Lưu nhật ký').click().run()
    assert any('Tên sản phẩm và tên tổ' in x.value for x in app.error)
    from datetime import date
    app.date_input[1].set_value(date(2026,12,1)).run()
    assert any('Từ ngày' in x.value for x in app.error)

def test_app_retrain(app):
    row=load_data().iloc[0].to_dict()
    for i in range(30):save_log({**row,'team':'Tổ mới','shift_date':'2026-11-02'},config.DB)
    app.run()
    button(app,'Huấn luyện lại').click().run()
    assert not app.exception
    assert any('1227' in x.value for x in app.markdown)
    button(app,'Quay lại bản cũ').click().run()
    assert not app.exception
    assert any('1197' in x.value for x in app.markdown)


def test_app_filter_and_recovery(app):
    from datetime import date
    app.text_input(key='team').set_value('Tổ lọc')
    button(app,'Lưu nhật ký').click().run()
    next(x for x in app.selectbox if x.label=='Lọc theo tổ').select('Tổ lọc').run()
    assert len(app.dataframe[1].value)==1
    app.date_input(key='filter_start').set_value(date(2026,12,1)).run()
    assert any('Từ ngày' in x.value for x in app.error)
    app.date_input(key='filter_end').set_value(date(2026,12,2)).run()
    assert app.dataframe[1].value.empty


def test_app_initialization_failure(tmp_path,monkeypatch):
    import data
    def fail(): raise ValueError('LỖI: tệp đầu vào hỏng')
    monkeypatch.setattr(data,'load_data',fail)
    app=AppTest.from_file(str(Path(__file__).parents[1]/'app.py')).run()
    assert not app.exception
    assert any('tệp đầu vào hỏng' in x.value for x in app.error)


@pytest.mark.parametrize('target', [None, 0., .8])
def test_no_streamlit_magic_output_in_all_tabs(app, target):
    if target is not None:
        app.number_input(key='base_target').set_value(target).run()
        button(app, 'Dự báo năng suất').click().run()
    assert not app.exception
    assert len(app.tabs) == 4
    # AppTest executes all tab bodies, including tabs not selected in a browser.
    displayed = []
    for tab in app.tabs:
        assert tab.header
    for element in app:
        proto = getattr(element, 'proto', None)
        if proto is not None:
            displayed.append(str(proto))
    text = '\n'.join(displayed)
    leaked = [marker for marker in ('DeltaGenerator', 'Creator of Delta') if marker in text]
    assert not leaked


def test_heading_css_has_no_serif_font():
    import ast
    import re
    tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text(encoding='utf-8'))
    css = next(node.args[0].value for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and isinstance(node.func.value, ast.Name) and node.func.value.id == 'st'
               and node.func.attr == 'markdown' and node.args
               and isinstance(node.args[0], ast.Constant) and '<style>' in str(node.args[0].value))
    assert 'Georgia' not in css
    headings = re.search(r'h1,h2,h3\s*\{([^}]+)\}', css).group(1)
    assert "Tahoma,'DejaVu Sans',sans-serif" in headings
    assert not re.search(r'(?<![-\w])serif(?![-\w])', headings)


def test_default_scenarios_are_useful_and_bounded(app):
    import config
    from data import product_table, product_smv
    from model import load, predict
    from scenarios import compare
    source = load_data()
    limits = config.slider_limits(source)
    base = {key: app.number_input(key='base_' + key).value for key in config.FEATURES if key != 'smv'}
    base['smv'] = product_smv(product_table(source), app.selectbox(key='product').value)
    changes = {key: next(s.value for s in app.slider if s.label == config.LABELS[key]) for key in limits}
    assert changes == {key: (base[key] + high) / 2 for key, (low, high) in limits.items()}
    rows, _ = compare(load(config.MODEL), base, changes, limits)
    table = app.dataframe[0].value
    assert len(table) == 5
    assert table['Thông số thay đổi'].nunique() == 5
    assert table['Năng suất dự báo'].nunique() >= 2
    for row in rows:
        assert all(low <= row['inputs'][key] <= high for key, (low, high) in limits.items())
    button(app, 'Dự báo năng suất').click().run()
    unchanged = table.loc[table['Kịch bản'] == 'Giữ nguyên', 'Năng suất dự báo'].item()
    assert unchanged == predict(load(config.MODEL), base)['value']
    assert unchanged == app.session_state['prediction'][1]['value']
    assert app.metric[0].value == f"{unchanged:.2%}"


def test_unchanged_scenarios_explain_why_and_preserve_selection(app):
    for slider in app.slider:
        key = next(key for key in config.slider_limits(load_data()) if config.LABELS[key] == slider.label)
        slider.set_value(app.number_input(key='base_' + key).value)
    app.run()
    table = app.dataframe[0].value
    assert table.loc[table['Kịch bản'] == 'Giữ nguyên', 'Thông số thay đổi'].item() == 'Giữ nguyên'
    assert (table.loc[table['Kịch bản'] != 'Giữ nguyên', 'Thông số thay đổi'] == 'Chưa kéo thanh trượt').all()
    assert table['Năng suất dự báo'].nunique() == 1
    app.run()
    assert (app.dataframe[0].value['Năng suất dự báo'] == table['Năng suất dự báo']).all()


def test_no_bare_magic_expressions_in_app():
    import ast
    tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr):
            assert isinstance(node.value, ast.Call)


@pytest.mark.parametrize('bound', [0, 1])
def test_scenario_defaults_at_slider_bounds(app, bound):
    limits = config.slider_limits(load_data())
    for key, interval in limits.items():
        app.number_input(key='base_' + key).set_value(interval[bound])
    app.run()
    assert not app.exception
    for key, (low, high) in limits.items():
        slider = next(s for s in app.slider if s.label == config.LABELS[key])
        assert low <= slider.value <= high
        assert slider.value == (limits[key][bound] + high) / 2
    button(app, 'Dự báo năng suất').click().run()
    unchanged = app.dataframe[0].value.iloc[0]['Năng suất dự báo']
    assert unchanged == app.session_state['prediction'][1]['value']


def test_redesign_has_offline_interactive_charts(app):
    button(app, 'Dự báo năng suất').click().run()
    assert len(app.get('iframe')) >= 2
    row = load_data().iloc[0].to_dict()
    save_log({**row, 'team': 'Tổ biểu đồ', 'shift_date': '2026-11-02'}, config.DB)
    app.run()
    assert len(app.get('iframe')) == 3
    html = '\n'.join(frame.proto.srcdoc for frame in app.get('iframe'))
    for kind in ['bullet', 'scenarios', 'drift']:
        assert f'"kind": "{kind}"' in html
    assert '<script src=' not in html


@pytest.mark.parametrize('value,clipped', [(0., True), (1.4, False)])
def test_bullet_chart_keeps_prediction_boundaries(app,monkeypatch,value,clipped):
    import json
    import re
    import model
    monkeypatch.setattr(model, 'predict', lambda bundle, row: {'value': value, 'raw': -.2 if clipped else value, 'clipped': clipped})
    button(app, 'Dự báo năng suất').click().run()
    assert not app.exception
    documents = [frame.proto.srcdoc for frame in app.get('iframe')]
    payloads = [json.loads(re.search(r'id="chart-data">(.*?)</script>', html, re.S).group(1)) for html in documents]
    bullet = next(p['data'] for p in payloads if p['kind'] == 'bullet')
    assert bullet['value'] == value
    assert bullet['status'] == ('Đạt' if value >= .8 else 'Không đạt')
    assert any('Đã kẹp' in w.value for w in app.warning) == clipped
    assert app.metric[0].value == f'{value:.2%}'


def test_interactive_chart_payloads_update_with_controls(app):
    import json
    import re
    def payload(kind):
        packets = [json.loads(re.search(r'id="chart-data">(.*?)</script>', f.proto.srcdoc, re.S).group(1)) for f in app.get('iframe')]
        return next(p['data'] for p in packets if p['kind'] == kind)
    original = payload('scenarios')
    app.slider[1].set_value(app.slider[1].max).run()
    updated = payload('scenarios')
    assert updated != original
    assert [p['value'] for p in updated['points']] == app.dataframe[0].value['Năng suất dự báo'].tolist()
    row = load_data().iloc[0].to_dict()
    save_log({**row, 'team': 'Tổ ngưỡng', 'shift_date': '2026-11-02'}, config.DB)
    app.run()
    next(n for n in app.number_input if n.label == 'Ngưỡng cảnh báo độ trôi').set_value(2.).run()
    assert payload('drift')['threshold'] == 2.
