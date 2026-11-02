import math
import sqlite3
from pathlib import Path
import joblib
import pandas as pd
import pytest
import config
import model
from data import load_data, rename_columns, product_table, product_smv, validate
from model import train, predict, atomic_save, load, initialize, retrain, rollback
from scenarios import light, compare
from store import save_log, read_logs
from drift import report

@pytest.fixture(scope="module")
def df():
    return load_data()

@pytest.fixture(scope="module")
def bundle(df):
    return train(df)

@pytest.fixture
def row(df):
    return {**df.iloc[0].to_dict(), "workers": 30., "team": "Tổ 1", "shift_date": "2026-11-02"}

def test_source(df):
    assert df.shape == (1197, 9)
    assert not df.isna().any().any()
    table = product_table(df)
    assert len(table) == 70
    assert (table.variants == 1).all()
    for r in table.itertuples():
        assert product_smv(table, r.product) == r.smv
    with pytest.raises(ValueError, match="Tên sản phẩm"):
        product_smv(table, "Không có")
    duplicate = pd.DataFrame({"product": ["A"] * 3, "smv": [1., 3., 9.]})
    assert product_smv(product_table(duplicate), "A") == 3

def test_source_errors(tmp_path):
    with pytest.raises(ValueError, match="thiếu cột"):
        rename_columns(pd.DataFrame({"bad": [1]}))
    raw = pd.read_excel(config.SOURCE)
    for content in [raw.iloc[:0], raw.assign(**{raw.columns[2]: None})]:
        file = tmp_path / "bad.xlsx"
        content.to_excel(file, index=False)
        with pytest.raises(ValueError, match="rỗng|trống"):
            load_data(file)

@pytest.mark.parametrize("key", config.FEATURES + ["actual"])
@pytest.mark.parametrize("bad", [None, "1", True, float("nan"), float("inf"), -1, 999999])
def test_validation_invalid(row, key, bad):
    row[key] = bad
    with pytest.raises(ValueError, match="LỖI"):
        validate(row, actual=True)

@pytest.mark.parametrize("key", config.FEATURES + ["actual"])
def test_validation_bounds(row, key):
    for bound in config.RANGES[key]:
        assert validate({**row, key: bound}, actual=True)[key] == bound
    row.pop(key)
    with pytest.raises(ValueError):
        validate(row, actual=True)

def test_model(df, bundle, row, tmp_path):
    assert bundle['metadata']['rows'] == 1197
    assert bundle['metadata']['test_rows'] == 240
    assert bundle['metadata']['train_rows'] == 957
    assert set(bundle['metadata']['stats']) == set(config.FEATURES)
    result = predict(bundle, row)
    assert math.isfinite(result['value'])
    path = tmp_path / "model.joblib"
    atomic_save(bundle, path)
    assert predict(load(path), row) == result
    assert initialize(df, path)['metadata'] == bundle['metadata']
    assert initialize(df, tmp_path / "first.joblib")['metadata']['rows'] == 1197
    with pytest.raises(ValueError, match="Thiếu cột"):
        train(df.drop(columns='smv'))
    with pytest.raises(ValueError):
        predict(bundle, {})

@pytest.mark.parametrize("raw,expected,clipped", [(-1.,0.,True),(0.,0.,False),(1.3,1.3,False)])
def test_prediction_clipping(bundle,row,monkeypatch,raw,expected,clipped):
    monkeypatch.setattr(bundle['model'], 'predict', lambda _: [raw])
    assert predict(bundle,row) == {'raw':raw,'value':expected,'clipped':clipped}

@pytest.mark.parametrize('raw',[float('inf'),float('nan')])
def test_prediction_invalid(bundle,row,monkeypatch,raw):
    monkeypatch.setattr(bundle['model'], 'predict', lambda _: [raw])
    with pytest.raises(ValueError,match='hữu hạn'):
        predict(bundle,row)

@pytest.mark.parametrize('value,target,expected',[(.8,.8,'Đạt'),(.79999,.8,'Không đạt'),(0,0,'Đạt'),(2,1,'Đạt')])
def test_light(value,target,expected):
    assert light(value,target) == expected

@pytest.mark.parametrize('value,target',[(-1,.8),(float('nan'),.8),(.8,2),(.8,float('inf'))])
def test_light_invalid(value,target):
    with pytest.raises(ValueError): light(value,target)

def test_scenarios(df,bundle,row,monkeypatch):
    limits=config.slider_limits(df)
    assert limits['workers']==(2,60)
    assert limits['overtime'][1]==df.overtime.quantile(.95)
    row.update(target=.8,overtime=0.,bonus=0.,workers=30.)
    changes={k:hi for k,(lo,hi) in limits.items()}
    monkeypatch.setattr('scenarios.predict',lambda b,r:{'value': .7+r['bonus']*.01, 'clipped':False})
    rows,best=compare(bundle,row,changes,limits)
    assert len(rows)==5 and best=='Tăng thưởng'
    for r in rows:
        assert all(lo<=r['inputs'][k]<=hi for k,(lo,hi) in limits.items())
    monkeypatch.setattr('scenarios.predict',lambda b,r:{'value': .1, 'clipped':False})
    assert compare(bundle,row,changes,limits)[1] is None
    row['target']=0
    assert compare(bundle,row,changes,limits)[1]=='Giữ nguyên'
    for key in limits:
        with pytest.raises(ValueError): compare(bundle,row,{**changes,key:limits[key][1]+1},limits)
        with pytest.raises(ValueError): compare(bundle,{**row,key:-1},changes,limits)
    with pytest.raises(ValueError): compare(bundle,row,{},limits)

def test_store(row,tmp_path):
    db=tmp_path/'logs.sqlite'
    assert read_logs(db).empty
    assert save_log(row,db)==1
    saved=read_logs(db).iloc[0]
    for key in config.FEATURES+['actual']:
        assert saved[key]==row[key]
    save_log({**row,'team':"x' OR 1=1 --",'shift_date':'2026-11-01'},db)
    assert len(read_logs(db,team='Tổ 1'))==1
    assert len(read_logs(db,start='2026-11-02',end='2026-11-02'))==1
    assert read_logs(db,team='missing').empty
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON logs BEGIN SELECT RAISE(ABORT,'forced'); END")
    with pytest.raises(sqlite3.IntegrityError): save_log(row,db)
    assert len(read_logs(db))==2

@pytest.mark.parametrize('patch',[{'actual':'bad'},{'team':''},{'team':None},{'team':'x'*201},{'product':''},{'shift_date':'bad'},{'shift_date':None}])
def test_store_invalid(row,tmp_path,patch):
    db=tmp_path/'logs.sqlite'
    with pytest.raises(ValueError): save_log({**row,**patch},db)
    assert read_logs(db).empty

def test_drift(df,bundle):
    stats=bundle['metadata']['stats']
    same=pd.DataFrame([{k:v['mean'] for k,v in stats.items()}])
    assert (report(same,stats)['Nhãn']=='Bình thường').all()
    shifted=same.copy();shifted['idle']=300
    assert 'cảnh báo' in report(shifted,stats)['Nhãn'].tolist()
    assert report(pd.DataFrame(),stats).empty
    constant={k:{**v,'std':0} for k,v in stats.items()}
    assert (report(same,constant)['Nhãn']=='Bình thường').all()
    assert 'cảnh báo' in report(shifted,constant)['Nhãn'].tolist()
    for threshold in [0,-1,float('nan')]:
        with pytest.raises(ValueError): report(same,stats,threshold)
    with pytest.raises(ValueError): report(pd.DataFrame({'idle':['bad']}),stats)

def test_retrain_and_rollback(df,bundle,row,tmp_path):
    path=tmp_path/'model.joblib';db=tmp_path/'logs.sqlite'
    atomic_save(bundle,path)
    with pytest.raises(ValueError,match='Chưa có'): rollback(path)
    with pytest.raises(ValueError,match='0'): retrain(df,read_logs(db),path)
    for i in range(29): save_log(row,db)
    with pytest.raises(ValueError,match='29'): retrain(df,read_logs(db),path)
    save_log(row,db)
    updated=retrain(df,read_logs(db),path)
    assert updated['metadata']['rows']==1227 and updated['metadata']['log_id']==30
    assert updated['metadata']['test_rows']==240
    assert load(path.with_suffix('.previous.joblib'))['metadata']==bundle['metadata']
    with pytest.raises(ValueError,match='hiện có 0'): retrain(df,read_logs(db),path)
    assert rollback(path)['metadata']==bundle['metadata']
    assert predict(load(path),row)==predict(bundle,row)

def test_atomic_failure(df,bundle,row,tmp_path,monkeypatch):
    path=tmp_path/'model.joblib';atomic_save(bundle,path)
    original=path.read_bytes()
    def fail(*args): raise OSError('disk full')
    monkeypatch.setattr(model.joblib,'dump',fail)
    with pytest.raises(OSError): atomic_save(bundle,path)
    assert path.read_bytes()==original
    assert not list(tmp_path.glob('*.tmp'))
    monkeypatch.undo()
    with model.model_lock(path):
        with pytest.raises(ValueError,match='đang được'): initialize(df,path)

def test_integration(df,row,tmp_path):
    row.update(bonus=50.)
    bundle=train(df);limits=config.slider_limits(df)
    value=predict(bundle,validate(row))['value']
    assert math.isfinite(value)
    rows,best=compare(bundle,row,{k:limits[k][1] for k in limits},limits)
    assert len(rows)==5
    db=tmp_path/'logs.sqlite';path=tmp_path/'model.joblib'
    atomic_save(bundle,path)
    for _ in range(30):save_log(row,db)
    logs=read_logs(db)
    assert len(report(logs,bundle['metadata']['stats']))==6
    assert retrain(df,logs,path)['metadata']['rows']==1227


def test_lock_recovers_after_process_death(tmp_path):
    import subprocess
    import sys
    path=tmp_path/'model.joblib'
    script="from model import model_lock; import time; from pathlib import Path; " + "\nwith model_lock(Path("+repr(str(path))+")):\n print('ready',flush=True)\n time.sleep(30)"
    process=subprocess.Popen([sys.executable,'-c',script],stdout=subprocess.PIPE,text=True)
    try:
        assert process.stdout.readline().strip()=='ready'
        process.kill()
        process.wait(timeout=10)
        with model.model_lock(path):
            pass
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.stdout.close()


def test_retrain_write_failure_keeps_current(df,bundle,row,tmp_path,monkeypatch):
    path=tmp_path/'model.joblib'
    atomic_save(bundle,path)
    before=path.read_bytes()
    logs=pd.DataFrame([{**row,'id':i+1} for i in range(30)])
    original=model.atomic_save
    def fail_current(value,target):
        if Path(target)==path: raise OSError('disk full')
        return original(value,target)
    monkeypatch.setattr(model,'atomic_save',fail_current)
    with pytest.raises(OSError): retrain(df,logs,path)
    assert path.read_bytes()==before
    assert load(path.with_suffix('.previous.joblib'))['metadata']==bundle['metadata']
    assert not path.with_suffix('.lock').is_dir()
