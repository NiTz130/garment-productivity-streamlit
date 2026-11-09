"""Frontend phải dùng tối thiểu 3 họ font khác nhau, đóng gói sẵn, có đủ subset tiếng Việt."""
import base64
import json
import re
from pathlib import Path

import pytest

import frontend_component

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
FONTS = ROOT / "static" / "fonts"
MANIFEST = json.loads((FONTS / "fonts.json").read_text(encoding="utf-8"))
CSS = (FRONTEND / "styles.css").read_text(encoding="utf-8")


def _families():
    return sorted({face["family"] for face in MANIFEST})


def _first_family(variable):
    declaration = re.search(rf"--{variable}:\s*([^;]+);", CSS)
    assert declaration, f"thiếu biến --{variable}"
    return declaration.group(1).split(",")[0].strip().strip("\"'")


def _covers(unicode_range, codepoint):
    for part in unicode_range.split(","):
        bounds = part.strip().removeprefix("U+").split("-")
        low, high = int(bounds[0], 16), int(bounds[-1], 16)
        if low <= codepoint <= high:
            return True
    return False


def test_manifest_has_at_least_three_distinct_families():
    assert len(_families()) >= 3


@pytest.mark.parametrize("family", _families())
def test_each_family_ships_latin_and_vietnamese_subsets(family):
    subsets = {face["subset"] for face in MANIFEST if face["family"] == family}
    assert {"latin", "vietnamese"} <= subsets


@pytest.mark.parametrize("face", MANIFEST, ids=lambda face: face["file"])
def test_font_files_are_valid_woff2(face):
    data = (FONTS / face["file"]).read_bytes()
    assert data[:4] == b"wOF2"
    assert len(data) > 1000


@pytest.mark.parametrize("family", _families())
def test_vietnamese_subset_covers_stacked_marks(family):
    vietnamese = [face for face in MANIFEST if face["family"] == family and face["subset"] == "vietnamese"]
    for char in "ăơưđệữẫổ":
        assert any(_covers(face["unicode_range"], ord(char)) for face in vietnamese), (family, char)


@pytest.mark.parametrize("family", _families())
def test_every_family_has_license_text(family):
    slug = family.lower().replace(" ", "")
    slug = {"sourceserif4": "sourceserif4", "bevietnampro": "bevietnampro", "jetbrainsmono": "jetbrainsmono"}[slug]
    text = (FONTS / f"OFL-{slug}.txt").read_text(encoding="utf-8")
    assert "SIL OPEN FONT LICENSE" in text.upper()


def test_css_roles_use_three_different_bundled_families():
    roles = {name: _first_family(name) for name in ("font-body", "font-display", "numeric")}
    assert len(set(roles.values())) == 3
    assert set(roles.values()) <= set(_families())


def test_css_has_no_hardcoded_family_outside_variables():
    declared = re.findall(r"font-family:\s*([^;]+);", CSS)
    for value in declared:
        assert value.strip().startswith("var(") or value.strip() == "inherit", value


def test_script_lists_fonts_by_url_without_embedding_bytes():
    # Streamlit gửi lại chuỗi JS của component mỗi lần chạy lại; nhúng base64 làm mỗi lần gõ nặng thêm ~320 KB.
    script = frontend_component.build_script()
    match = re.search(r"const FONT_FACES = (\[.*?\]);\n", script, re.S)
    assert match
    faces = json.loads(match.group(1))
    assert [face["file"] for face in faces] == [face["file"] for face in MANIFEST]
    assert all("data" not in face and (FONTS / face["file"]).is_file() for face in faces)
    assert len(script) < 120_000
    assert "document.fonts.add" in script
    assert "export default function garmentProductivityComponent" in script


def test_script_registers_fonts_only_once_per_page():
    script = frontend_component.build_script()
    assert script.count("document.fonts.add") == 1
    assert "__garmentFontsLoaded" in script


def test_streamlit_serves_the_static_folder_holding_the_fonts():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert re.search(r"enableStaticServing\s*=\s*true", config)
