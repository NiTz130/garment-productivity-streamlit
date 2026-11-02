from __future__ import annotations
from datetime import date
import sqlite3
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from ui import chart_html, scenario_payload, drift_payload, selection_badge, slider_marks
import config
from data import load_data, product_table, product_smv, validate
from model import initialize, predict, retrain, rollback
from scenarios import light, compare
from store import save_log, read_logs
from drift import report

st.set_page_config(page_title="Dự báo năng suất may mặc", layout="wide")
st.markdown("""<style>
@font-face {font-family:Tahoma; src:local('Tahoma');}
:root{--ink:#1E293B;--muted:#64748B;--accent:#00665C;--line:#E2E8F0;--surface:#FFFFFF;}
html,body,[class*="css"],.stApp,input,button,textarea,select {font-family:Tahoma,'DejaVu Sans',sans-serif;}
.stApp {background:#F8F9FA;color:var(--ink);}
.block-container{max-width:1440px;padding-top:2rem;padding-bottom:3rem;}
p,li,label,input,button,[data-testid="stWidgetLabel"] p {font-size:16px!important;color:var(--ink);}
h1,h2,h3 {font-family:Tahoma,'DejaVu Sans',sans-serif!important;font-weight:700;color:#1E293B;}
h1{font-size:clamp(28px,3vw,40px)!important;letter-spacing:-.6px;margin-bottom:.3rem;}
h2{font-size:26px!important;}h3{font-size:21px!important;}
small,[data-testid="stCaptionContainer"] p {font-size:14px!important;color:#64748B;line-height:1.6;}
input,button,[data-baseweb="select"]>div{min-height:44px;}
[data-testid="stNumberInput"] input,[data-testid="stTextInput"] input{background:white;font-size:18px!important;}
.stButton>button,.stFormSubmitButton>button{border-radius:5px;min-height:46px;padding:.5rem 1.1rem;font-weight:700;}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"] {background:#00665C;border-color:#00665C;color:white;}
.stButton>button[kind="primary"] p,.stFormSubmitButton>button[kind="primary"] p {color:white;}
button:focus-visible,input:focus-visible{outline:3px solid #00665C!important;outline-offset:3px;}
[data-baseweb="tab-list"]{gap:1rem;border-bottom:1px solid var(--line);overflow-x:auto;flex-wrap:nowrap;}
[data-baseweb="tab"]{font-size:16px;min-height:52px;padding:8px 12px;white-space:nowrap;color:var(--ink);}
[data-baseweb="tab"][aria-selected="true"]{color:#00665C;font-weight:700;}
[data-baseweb="tab-highlight"]{background:#00665C;}
[data-testid="stMetric"]{padding:20px;background:white;border:1px solid var(--line);border-radius:6px;}
[data-testid="stMetricValue"]{font-size:clamp(30px,3.3vw,48px);font-weight:700;letter-spacing:-1px;}
[data-testid="stMetricDelta"]{font-size:16px;}
[data-testid="stForm"]{border:0;padding:0;}
[data-testid="stAlert"]{border:0;border-radius:5px;}
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p{color:var(--ink);}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:5px;}
.selection{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:14px 0;margin:8px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);}
.selection strong{font-size:20px;}.selection span{font-size:16px;}.selection.empty{color:#92400E;}
.badge{display:inline-block;background:#DCFCE7;color:#166534;padding:6px 10px;border-radius:4px;font-size:14px!important;font-weight:700;}
.slider-ruler{position:relative;height:8px;border-top:1px solid #CBD5E1;margin:0 9px;}
.slider-ruler span{position:absolute;top:-4px;width:2px;height:8px;background:#1E293B;}
.slider-labels{display:flex;justify-content:space-between;gap:8px;font-size:14px;color:#475569;margin-bottom:18px;}
@media(max-width:760px){.block-container{padding:1rem;}[data-testid="stHorizontalBlock"]{flex-wrap:wrap;}
[data-testid="stColumn"]{min-width:min(100%,300px)!important;}[data-testid="stMetricValue"]{font-size:36px;}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important;}}
</style>""", unsafe_allow_html=True)
st.title("Dự báo năng suất chuyền may")
st.caption("Nhóm 6 · Khoa học dữ liệu và ứng dụng · Dành cho Giám đốc sản xuất, Trưởng xưởng và Trưởng chuyền.")
try:
    source = load_data()
    products = product_table(source)
    limits = config.slider_limits(source)
    bundle = initialize(source, config.MODEL)
except (ValueError, OSError) as exc:
    st.error(str(exc))
    st.stop()
meta = bundle["metadata"]
with st.expander("Thông tin mô hình và chất lượng dự báo"):
    st.write(f"Mô hình Hồi quy tuyến tính · Huấn luyện: {meta['trained_at']} · {meta['rows']} dòng")
    st.write(f"R² tập kiểm tra: {meta['r2']!r} | MAE tập kiểm tra: {meta['mae']!r}")
if meta["r2"] < config.LOW_R2:
    st.warning("cảnh báo: R² thấp. Dự báo chỉ hỗ trợ cân nhắc, không bảo đảm đạt tiến độ.")
tabs = st.tabs(["1. Thiết lập đầu ca", "2. Dự báo và cảnh báo", "3. Mô phỏng kịch bản", "4. Cuối ca và MLOps"])
with tabs[0]:
    st.header("Thiết lập đầu ca")
    product = st.selectbox("Tên sản phẩm", products["product"], key="product")
    smv = product_smv(products, product)
    st.write(f"Định mức: {smv:g} phút/sản phẩm")
    if int(products.loc[products['product'] == product, 'variants'].iloc[0]) > 1:
        st.info("Sản phẩm có nhiều định mức; đang dùng trung vị.")
    base = {"smv": smv}
    fields = st.columns(2, gap="large")
    for index, (key, default) in enumerate([("target", .8), ("workers", 30.), ("overtime", 0.), ("bonus", 0.), ("idle", 0.)]):
        with fields[index % 2]:
            base[key] = st.number_input(config.LABELS[key], value=default, key="base_" + key)
    st.caption("Mục tiêu nhập theo tỷ lệ: 0,8 tương ứng 80%. Tăng ca tính cho cả tổ. Máy dừng mặc định 0.")
    valid = True
    try:
        validate(base)
    except ValueError as exc:
        valid = False
        st.error(str(exc))
with tabs[1]:
    st.header("Dự báo và cảnh báo")
    signature = (product, tuple(base.items()), meta['trained_at'])
    if st.button("Dự báo năng suất", type="primary") and valid:
        st.session_state['prediction'] = (signature, predict(bundle, base))
    saved = st.session_state.get('prediction')
    if saved and saved[0] == signature and valid:
        result = saved[1]
        status = light(result['value'], base['target'])
        metrics = st.columns(3)
        with metrics[0]:
            st.metric("Năng suất dự báo", f"{result['value']:.2%}", f"{(result['value'] - base['target']) * 100:+.2f} điểm phần trăm")
        with metrics[1]:
            st.metric("Mục tiêu đầu ca", f"{base['target']:.2%}")
        with metrics[2]:
            st.metric("Trạng thái", status)
        components.html(chart_html("bullet", {"value": result['value'], "target": base['target'], "status": status}), height=285)
        if status == "Đạt":
            st.success("Đèn xanh · Đạt chỉ tiêu")
        else:
            st.error("Đèn đỏ · Không đạt chỉ tiêu")
        if result['clipped']:
            st.warning(f"cảnh báo: Đã kẹp dự báo âm {result['raw']} về 0.")
    else:
        st.info("Nhập thông số hợp lệ ở bước 1 rồi bấm Dự báo năng suất.")
with tabs[2]:
    st.header("So sánh phương án hoàn thành kịp tiến độ")
    st.caption("Năng suất hiện tại là dự báo từ thông số đầu ca. Điểm can thiệp là tổng thay đổi chia cho khoảng thanh trượt; không phải chi phí.")
    scenario_valid = valid and all(low <= base[key] <= high for key, (low, high) in limits.items())
    if scenario_valid:
        controls, plot = st.columns([1, 2], gap="large")
        changes = {}
        with controls:
            st.subheader("Điều chỉnh phương án")
            for key in limits:
                low, high = limits[key]
                changes[key] = st.slider(config.LABELS[key], low, high, float((base[key] + high) / 2), format="%g", key=f"what_absolute_{key}_{base[key]}")
                st.markdown(slider_marks(low, high, base[key]), unsafe_allow_html=True)
        rows, best = compare(bundle, base, changes, limits)
        with plot:
            components.html(chart_html("scenarios", scenario_payload(rows, base['target'], best)), height=565)
        selected_effort = next((r['effort'] for r in rows if r['name'] == best), None)
        with controls:
            st.metric("Điểm can thiệp được chọn", f"{selected_effort:.3f}" if selected_effort is not None else "—")
        st.markdown(selection_badge(best, selected_effort), unsafe_allow_html=True)
        table = []
        for row in rows:
            changed = [f"{config.LABELS[k]}: {base[k]:g} → {row['inputs'][k]:g}" for k in limits if row['inputs'][k] != base[k]]
            table.append({"Kịch bản": row['name'], "Thông số thay đổi": "; ".join(changed) or ("Giữ nguyên" if row["name"] == "Giữ nguyên" else "Chưa kéo thanh trượt"),
                          "Năng suất dự báo": row['value'], "Kết quả": row['status'],
                          "Thay đổi so với hiện tại": row['delta'], "Điểm can thiệp": row['effort'],
                          "Đã kẹp về 0": "Có" if row['clipped'] else "Không",
                          "Can thiệp thấp nhất": "Được chọn" if row['name'] == best else ""})
        styled = pd.DataFrame(table).style.format({"Năng suất dự báo": "{:.2%}", "Thay đổi so với hiện tại": lambda value: f"{value * 100:+.2f} điểm phần trăm", "Điểm can thiệp": "{:.3f}"})
        styled = styled.map(lambda value: "color:#15803D;font-weight:700" if value == "Đạt" else "color:#DC2626;font-weight:700", subset=["Kết quả"])
        styled = styled.map(lambda value: "background-color:#DCFCE7;color:#166534;font-weight:700" if value else "", subset=["Can thiệp thấp nhất"])
        st.dataframe(styled, hide_index=True, height=260)
    else:
        st.info("Mô phỏng yêu cầu đầu ca trong giới hạn thanh trượt: công nhân 2–60; tăng ca và thưởng không vượt phân vị 95. Dự báo bước 2 vẫn dùng miền dữ liệu đầy đủ.")
with tabs[3]:
    st.header("Ghi nhật ký cuối ca")
    with st.form("end_shift", clear_on_submit=False):
        end_product = st.selectbox("Sản phẩm cuối ca", products['product'], key="end_product")
        team = st.text_input("Tên tổ ghi nhật ký", key="team")
        shift_date = st.date_input("Ngày ca", value=date.today())
        end_row = {}
        end_fields = st.columns(2, gap="large")
        for index, (key, default) in enumerate([("target", .8), ("workers", 30.), ("overtime", 0.), ("bonus", 0.), ("idle", 0.), ("actual", .8)]):
            with end_fields[index % 2]:
                end_row[key] = st.number_input(config.LABELS[key] + " cuối ca", value=default, key="end_" + key)
        if st.form_submit_button("Lưu nhật ký", type="primary"):
            try:
                end_row.update(smv=product_smv(products, end_product), product=end_product, team=team, shift_date=shift_date.isoformat())
                saved_id = save_log(end_row, config.DB)
                st.success(f"Đã lưu nhật ký số {saved_id}.")
            except (ValueError, sqlite3.Error, OSError) as exc:
                st.error(str(exc))
    try:
        logs = read_logs(config.DB)
        st.subheader("Lịch sử nhật ký")
        filter_team = st.selectbox("Lọc theo tổ", ["Tất cả"] + sorted(logs['team'].unique().tolist()))
        start = st.date_input("Từ ngày", value=date(2000, 1, 1), min_value=date(2000, 1, 1), max_value=date(2100, 12, 31), key="filter_start")
        end = st.date_input("Đến ngày", value=date.today(), min_value=date(2000, 1, 1), max_value=date(2100, 12, 31), key="filter_end")
        if start > end:
            st.error("LỖI: Từ ngày phải trước hoặc bằng Đến ngày.")
        else:
            history = read_logs(config.DB, "" if filter_team == "Tất cả" else filter_team, start.isoformat(), end.isoformat())
            st.dataframe(history.rename(columns={**config.LABELS, "id": "Mã nhật ký", "created_at": "Thời điểm ghi (UTC)",
                         "shift_date": "Ngày ca", "product": "Sản phẩm", "team": "Tên tổ"}), hide_index=True)
        st.subheader("Độ trôi dữ liệu (Data Drift)")
        threshold = st.number_input("Ngưỡng cảnh báo độ trôi", min_value=.01, value=config.DRIFT_THRESHOLD)
        st.caption("So toàn bộ nhật ký với tập học: |trung bình nhật ký − trung bình tập học| / độ lệch chuẩn tập học. Vượt ngưỡng là cảnh báo. Độ lệch chuẩn bằng 0: khác trung bình sẽ cảnh báo. Dữ liệu sai là LỖI.")
        if logs.empty:
            st.info("Chưa có nhật ký để tính độ trôi dữ liệu.")
        else:
            drift_result = report(logs, meta['stats'], threshold)
            components.html(chart_html("drift", drift_payload(drift_result, threshold)), height=615)
            st.dataframe(drift_result, hide_index=True)
        st.subheader("Huấn luyện lại thủ công")
        new_count = int((logs['id'] > meta['log_id']).sum())
        st.write(f"Có {new_count} dòng mới; cần ít nhất {config.MIN_NEW_LOGS}. Tên tổ không đưa vào mô hình.")
        st.caption("Giữ cố định tập kiểm tra 20% của dữ liệu gốc. Nhật ký chỉ thêm vào tập học. Mỗi lần huấn luyện giữ một bản trước đó.")
        if st.button("Huấn luyện lại"):
            try:
                retrain(source, logs, config.MODEL, config.MIN_NEW_LOGS)
                st.success("Đã huấn luyện và lưu bản cũ.")
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
        if st.button("Quay lại bản cũ"):
            try:
                rollback(config.MODEL)
                st.success("Đã khôi phục bản cũ.")
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    except (ValueError, sqlite3.Error, OSError) as exc:
        st.error(str(exc))
