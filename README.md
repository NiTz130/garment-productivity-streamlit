# Năng suất chuyền may

Ứng dụng dùng Streamlit làm giao diện và gọi facade Python `services.py` trực tiếp. Không có HTTP API, CORS hay backend server riêng. Trang được dựng bằng component hai chiều `st.components.v2` có trong Streamlit 1.66.1.

## Cài đặt và kiểm thử

```powershell
Set-Location D:\garment-productivity-streamlit
python -m pip install -r requirements.txt
python -X utf8 -c "from data import load_data; import model; bundle = model.train(load_data()); model.activate(bundle); print(bundle['selected_model'])"
python -m streamlit run app.py --server.address 127.0.0.1
```

Mở `http://127.0.0.1:8501`. Component dùng CSS, HTML và JavaScript cục bộ trong `frontend/`; không cần lệnh build, Node runtime, Tailwind CDN hay Google Fonts để chạy.

Lệnh huấn luyện chỉ cần chạy khi cài mới hoặc thay dataset. Git không lưu thư mục `runtime/`; một bản clone mới cần tạo model VNĐ trước khi dự báo. Trang thống kê vẫn đọc được lịch sử khi chưa có model.

Frontend có hai trang theo bản thiết kế Stitch trong `docs/`: dự báo tự động sau 300 ms dừng gõ, và thống kê quản trị với bộ lọc sản phẩm, biểu đồ, bảng chín trường. Nhân công nhập người cả ca cùng lựa chọn thêm một người nửa ca. Khi chưa đạt mục tiêu, hệ thống so sánh ba hướng điều chỉnh; hướng kết hợp cho phép giữ nguyên một thông số đã chạm trần và thay đổi ít nhất hai thông số còn lại.

```powershell
python -X utf8 -m pytest -q --basetemp=.tmp/pytest-final
```

Coverage backend giữ ngưỡng tối thiểu 90%. Workbook nguồn được đọc ở sheet đầu tiên và không bị ghi lại. SQLite không được dùng. Dataset mặc định ở `dataset/`; một file cùng tên trong thư mục cha được ưu tiên nếu có.

Lần kiểm tra tích hợp gần nhất: **113 passed, 1 skipped**, coverage backend **95,17%**. Hai trang đã được kiểm tra trên Edge headless bằng dữ liệu thật: dự báo tự cập nhật, ba hướng điều chỉnh, lọc lịch sử và bố cục mobile 390 px. Test bị bỏ qua cần bộ tài liệu nguồn ngoài repo.

## Dùng facade từ frontend

```python
from services import get_catalog, predict_shift, recommend_options, get_management_dashboard

catalog = get_catalog()
item = next(row for row in catalog["items"] if row["product"] == "Áo thun - Mẫu 02")

inputs = {
    "target": 0.8,       # tỷ lệ, không phải 80
    "smv": item["smv"],
    "workers": 30.5,     # 30 người cả ca + 1 người nửa ca
    "overtime": 60,       # tổng phút của cả tổ
    "bonus": 10000,       # VNĐ nguyên
    "idle": 0,            # phút nguyên
}

prediction = predict_shift(inputs)
options = recommend_options(inputs)
dashboard = get_management_dashboard(product=item["product"])
```

`get_catalog()` trả `items` gồm SKU, tên sản phẩm, SMV trung vị, các giá trị SMV quan sát được và cờ `has_multiple_smv`. Một SKU/sản phẩm có nhiều SMV không bị chọn ngẫu nhiên. `input_limits` và `recommendation_limits` nêu giới hạn, bước và đơn vị.

Form có thể gửi trực tiếp `workers=30.5`, hoặc gửi `full_shift_workers=30` cùng `has_half_shift_worker=True`; facade quy đổi cặp trường đó thành 30,5. Số người cả ca phải là số nguyên không âm và cờ nửa ca phải là boolean. Catalog trả giới hạn riêng khi bật/tắt cờ này.

`predict_shift(inputs)` trả các trường đã kiểm tra `inputs`, `raw`, `value`, `clipped`, `achieved`, `status`, `difference_to_target`, `shortfall` và `surplus`. `value` là tỷ lệ; dự báo âm được kẹp về 0, không kẹp trên ở 1. Thiếu trường, chuỗi số, boolean, số không hữu hạn, workers ngoài bước 0,5, bonus không nguyên hoặc thời gian không nguyên đều phát sinh `ValueError`. Số 0 hợp lệ cho tăng ca, tiền thưởng và máy dừng.

`recommend_options(inputs)` trả baseline và ba hướng: nhân lực, tăng ca, kết hợp. Mỗi hướng có `available`, dự báo, đủ/chưa đủ mục tiêu, thay đổi sáu đầu vào, chênh lệch năng suất và lý do. Tập tìm kiếm hữu hạn, dựa trên phân vị 95% của lịch sử hợp lệ và giới hạn cấu hình; các ứng viên được dự báo theo lô. Kết quả được gọi là phương án tốt nhất trong phạm vi đã tìm. Đây không phải tối ưu toàn cục hay khẳng định quan hệ nhân quả. Hướng không cải thiện hoặc hết khoảng điều chỉnh trả `available=False` cùng lý do.

`get_management_dashboard(product=None)` trả `kpis`, `charts`, `history` và chất lượng dữ liệu trong cùng phạm vi bộ lọc. KPI gồm số ca hợp lệ, actual trung bình không trọng số, tỷ lệ actual >= target và tổng phút máy dừng. Biểu đồ so sánh target/actual theo sản phẩm kèm số quan sát và scatter tiền thưởng VNĐ/actual kèm target, sản phẩm, dòng nguồn. Bảng giữ đủ chín trường đã chuẩn hóa cùng `source_row`; ngày ca không được thêm vì workbook không có ngày gốc. Lọc rỗng trả count 0, các KPI không xác định là `None` và các mảng rỗng.

Các hàm facade không phụ thuộc Streamlit. Dataset và model đã nạp được giữ trong cache theo đường dẫn, kích thước và thời điểm sửa file. Mỗi dự báo chỉ kiểm tra metadata file và dùng model trong bộ nhớ; không mở Excel, quét toàn bộ dataset hoặc huấn luyện lại.

## Hợp đồng dữ liệu và đơn vị

Thứ tự estimator giữ nguyên: `target`, `smv`, `workers`, `overtime`, `bonus`, `idle`; biến đích là `actual`. Tỷ lệ `0.8` tương ứng 80%, SMV là phút/sản phẩm, workers là lao động quy đổi theo ca, overtime là tổng phút tăng ca của tổ, idle là phút máy dừng, bonus là VNĐ. SKU và tên sản phẩm chỉ thuộc catalog/dashboard, không đi vào estimator.

| Cột Excel | Trường nội bộ |
| --- | --- |
| Mã SKU (Sản phẩm) | `sku` |
| Tên sản phẩm (Đề xuất) | `product` |
| Năng suất mục tiêu(%) | `target` |
| Thời gian tạo sản phẩm (Phút) | `smv` |
| Thời gian tăng ca (Phút) | `overtime` |
| Tiền thưởng năng suất (VNĐ) | `bonus` |
| Thời gian máy nghỉ(Phút) | `idle` |
| Số công nhân(Người) | `workers` |
| Năng xuất thực tế (%) | `actual` |

Miền lịch sử và miền nhập ca mới là hai kiểm tra riêng. Lịch sử giữ nguyên các bonus VNĐ dạng thập phân trong workbook; không chuyển đổi hoặc làm tròn lại. Bản hiện tại không có workers lệch bước 0,5; nếu có, quality report sẽ liệt kê dòng đó nhưng không tự sửa dữ liệu. Input ca mới cần bonus VNĐ nguyên không âm, phút tăng ca/máy dừng nguyên không âm, và workers theo bước 0,5. Bonus intake tối đa được giới hạn theo giá trị lớn nhất trong lịch sử hợp lệ và cấu hình.

`source_hashes.json` giữ checksum nguồn ban đầu, không được thay bằng checksum vận hành. `dataset/operational_manifest.json` ghi riêng hai checksum. Bản nguồn ban đầu có SHA-256 `27a73111854ce55870811bbd12c49733576fec57b240c98c585aef356446466c`; workbook vận hành VNĐ hiện tại có SHA-256 `ace6233930cc623fe5abb20d0747fad068b6ae931480df2fe2f507fb73337bcd`. Đối chiếu với workbook trong Git cho thấy chỉ header/giá trị tiền thưởng đổi; tám cột còn lại giữ nguyên. Backend không nhân tỷ giá.

## Huấn luyện và tương thích model

`model.train(frame)` so sánh Linear Regression, Decision Tree và Random Forest. Chia nhóm đầu vào bằng GroupShuffleSplit 80/20, seed 42; GroupKFold năm phần chỉ trên tập học. Mô hình thắng được chọn theo RMSE kiểm định chéo trung bình; test chỉ báo cáo đánh giá cuối. `model.activate(bundle)` ghi nguyên tử và giữ model trước tại `runtime/model.previous.joblib`.

Gói mới mang schema version, đơn vị `VND`, fingerprint dataset, thứ tự feature, thuật toán, cấu hình chia tập và chỉ số đánh giá. Model cũ thiếu bằng chứng schema/đơn vị vẫn được giữ và đọc để kiểm tra, nhưng dự báo bị chặn với thông báo cần huấn luyện model mới. Chỉ nạp joblib từ nguồn tin cậy.

## Kết quả đo

Huấn luyện trên 1.197 dòng hợp lệ, 957 dòng train và 240 dòng test. Mô hình thắng là **Random Forest**, chọn theo CV RMSE thấp nhất. MAE/RMSE dùng tỷ lệ năng suất; R² không có đơn vị.

| Mô hình | CV RMSE TB | CV MAE TB | CV R² TB | Test MAE | Test RMSE | Test R² |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Linear Regression | 0,15344 | 0,10899 | 0,21037 | 0,12109 | 0,16569 | 0,11398 |
| Decision Tree | 0,14124 | 0,08651 | 0,33254 | 0,10444 | 0,16140 | 0,15927 |
| Random Forest | **0,12499** | 0,07635 | 0,47772 | **0,09738** | **0,15297** | **0,24473** |

Test R² của model được chọn là 0,24473; sai số test RMSE tương đương khoảng 15,30 điểm phần trăm năng suất. Kết quả này mô tả độ khớp trên split đã ghi trong metadata, không chứng minh quan hệ nhân quả.

| Đo sau khi nạp model | Median | Trung bình |
| --- | ---: | ---: |
| Một dự báo `predict_shift` | 16,62 ms | 16,86 ms |
| Sinh ba phương án `recommend_options` | 83,33 ms | 83,69 ms |

Huấn luyện cả ba mô hình và CV mất **3,31 giây**. Các thời gian dự báo lấy trên cùng một máy, sau một lần warm-up; 100 dự báo đơn và 10 lần sinh phương án. Kiểm thử: **101 passed, 1 skipped**, coverage backend **94,71%** (ngưỡng 90%). Test bị skip kiểm tra các tài liệu nguồn ngoài thư mục repo không có trong clone này.

## Giao diện Streamlit

`app.py` điều phối hai trang và state theo `st.session_state`. `frontend_component.py` nạp các tài sản tĩnh và mount `st.components.v2.component` với một key ổn định. JavaScript chỉ quản lý tương tác, chuỗi đang gõ, debounce 300 ms và cách vẽ dữ liệu backend; mọi dự báo, phương án và thống kê đều do `ui_adapter.py` gọi qua `services.py`. Khi nhập liệu sai hoặc chưa đủ, adapter không gọi dự báo. Component giữ catalog ở phía trình duyệt sau lần truyền đầu; lịch sử dashboard chỉ được đưa vào payload khi đang xem trang quản trị.

Mục tiêu trên form nhập theo phần trăm (ví dụ `80`) và adapter đổi thành tỷ lệ `0.8`. SMV lấy từ catalog. Người dùng nhập nhân công cả ca bằng số nguyên và chọn riêng người nửa ca; facade nhận cặp `full_shift_workers`/`has_half_shift_worker` để quy đổi sang `workers` theo bước 0,5. Tăng ca và máy dừng là phút nguyên; tiền thưởng là VNĐ nguyên. Chuỗi rỗng được giữ riêng, không biến thành 0; parser hỗ trợ dấu phẩy thập phân và dấu chấm phân cách hàng nghìn theo cách nhập Việt Nam.

Trang dự báo không huấn luyện model khi mở. `services.predict_shift` chỉ chạy khi mọi trường hợp lệ. Nếu model thiếu, sai schema/đơn vị VNĐ hoặc dataset không khớp fingerprint, giao diện báo model/dữ liệu chưa sẵn sàng; không thay bằng số giả hay model cũ. Khi dự báo chưa đạt mục tiêu, component gửi sự kiện revision hiện tại để Python gọi `services.recommend_options` ở lượt riêng. Kết quả cũ bị bỏ qua nếu thông số đã đổi.

Không cần dependency frontend bổ sung; phiên bản `streamlit==1.66.1` trong `requirements.txt` cung cấp component API hai chiều. Kiểm thử adapter và nghiệp vụ bằng `python -X utf8 -m pytest -q --basetemp=.tmp/pytest-final` (coverage backend tối thiểu 90%); kiểm tra cú pháp JavaScript bằng `node --check frontend/app.js` với Node hỗ trợ ES modules.
