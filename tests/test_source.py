import hashlib
import json
from pathlib import Path

import pytest


def test_protected_source_files_unchanged():
    root = Path(__file__).parents[1]
    manifest = json.loads((root / 'source_hashes.json').read_text(encoding='utf-8'))
    if not all((root.parent/name).is_file() for name in manifest):
        pytest.skip('NOT RUN: bộ tài liệu gốc ở thư mục cha không nằm trong bản clone; dataset đóng gói có test riêng.')
    for name, expected in manifest.items():
        assert hashlib.sha256((root.parent/name).read_bytes()).hexdigest() == expected



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
    manifest = json.loads((root/'dataset'/'operational_manifest.json').read_text(encoding='utf-8'))
    name = 'Bộ dữ liệu - Nhóm 6.xlsx'
    original = json.loads((root/'source_hashes.json').read_text(encoding='utf-8'))
    assert original[name] == manifest['original_source_sha256']
    assert manifest['operational_dataset_sha256'] != manifest['original_source_sha256']
    assert hashlib.sha256((root/'dataset'/name).read_bytes()).hexdigest() == manifest['operational_dataset_sha256']


def test_operational_dataset_records_vnd_values_and_new_header():
    import pandas as pd
    import config
    from data import read_workbook

    frame = pd.read_excel(config.SOURCE, engine='openpyxl')
    assert 'Tiền thưởng năng suất (VNĐ)' in frame.columns
    bonus = frame['Tiền thưởng năng suất (VNĐ)']
    assert bonus.notna().all()
    assert bonus.min() == 0
    assert bonus.max() > 3600
    assert bonus.max() == 746708.4
    normalized = read_workbook(config.SOURCE)
    assert normalized['bonus'].tolist() == bonus.tolist()
