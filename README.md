> Bản demo môn học. Nhật ký và mô hình huấn luyện lại trên host miễn phí có thể mất khi máy chủ khởi tạo lại. Chỉ nhập dữ liệu minh họa.

# Hệ thống dự báo năng suất chuyền may

Tài liệu dành cho Giám đốc sản xuất, Trưởng xưởng và Trưởng chuyền.
Dùng ứng dụng để dự báo đầu ca, so sánh phương án và ghi nhận kết quả cuối ca.

## Chạy ứng dụng

Mở PowerShell và chạy:

```powershell
cd C:\codev2\chieut4\garment_app
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

Mở địa chỉ mà Streamlit hiển thị, thường là `http://127.0.0.1:8501`.
Các thư viện đã được cài trên máy hiện tại. Cài gói trên máy mới cần mạng.
Ứng dụng không gọi dịch vụ dự báo bên ngoài. Đã tắt thống kê sử dụng Streamlit.
Chỉ lắng nghe địa chỉ nội bộ khi dùng lệnh trên.

Repo đã kèm bản sao dataset trong `dataset/`. Khi có tệp gốc ở thư mục cha, ứng dụng ưu tiên tệp đó.
Ứng dụng đọc sheet đầu tiên bằng pandas và openpyxl, không sửa tệp nguồn.

## Dùng bốn bước

1. **Thiết lập đầu ca:** chọn sản phẩm và nhập thông số. Máy dừng mặc định 0 phút.
2. **Dự báo và cảnh báo:** bấm **Dự báo năng suất**. Đèn xanh nghĩa là dự báo đạt mục tiêu.
3. **Mô phỏng kịch bản:** kéo thanh trượt. Bảng năm phương án cập nhật ngay.
4. **Cuối ca và MLOps:** nhập số liệu thực tế, tên tổ và ngày ca rồi bấm **Lưu nhật ký**.

Năng suất dùng tỷ lệ: nhập `0.8` để biểu thị 80%.
Chênh lệch trên bước 2 dùng điểm phần trăm.
Số phút tăng ca là tổng của cả tổ, không phải số phút mỗi công nhân.
Số công nhân có thể là số thập phân vì dữ liệu gốc dùng lao động quy đổi.
Tên tổ chỉ dùng để ghi nhật ký và lọc lịch sử, không đưa vào mô hình.
Số liệu cuối ca được nhập riêng; không tự sao chép kế hoạch thành thực tế.
Mỗi lần bấm lưu tạo một bản ghi mới. Không bấm lại cho cùng một ca đã lưu.

Bước 1 chấp nhận miền vận hành đầy đủ trong `config.RANGES`.
What-If chỉ chạy nếu đầu ca cũng nằm trong giới hạn các thanh trượt.
Nếu đầu ca vượt giới hạn What-If, bước 2 vẫn dự báo được.

## Hiểu kết quả

Mô hình là `sklearn.linear_model.LinearRegression`, dùng sáu biến đã yêu cầu.
Chia dữ liệu gốc thành 80% học và 20% kiểm tra, `random_state=42`.
Lần đầu mở ứng dụng sẽ huấn luyện và lưu mô hình ban đầu nếu chưa có tệp.
Các lần huấn luyện lại chỉ chạy khi bấm nút.

Kết quả thực đo trên 1.197 dòng gốc:

- Tập học: 957 dòng. Tập kiểm tra: 240 dòng.
- R²: **0.1882157880997436**.
- MAE: **0.10713407084117196**, tương đương khoảng 10,71 điểm phần trăm.

R² dưới 0,5 sẽ hiện cảnh báo. Không làm tròn R² và MAE trong phần thông tin mô hình.
Dự báo âm được kẹp về 0 và ghi rõ. Không kẹp trên ở 100% vì dữ liệu có năng suất vượt 1.
Thay đổi một thông số trong hồi quy chỉ là mô phỏng, không chứng minh quan hệ nhân quả.
Các tên sản phẩm được tài liệu mô tả là tạo từ SMV; chưa phải danh mục đã xác minh tại xưởng.

## Chọn kịch bản

Năm dòng gồm Giữ nguyên, Tăng ca, Thêm công nhân, Tăng thưởng và Kết hợp.
Mỗi phương án đơn chỉ thay đổi biến tương ứng theo thanh trượt.
Phương án kết hợp thay đổi cả ba biến.
Thanh trượt nhập mức tuyệt đối, không phải lượng cộng thêm.
Mặc định mỗi thanh trượt ở giữa giá trị đầu ca và giới hạn tối đa.
Khi mở mới, bảng đã có các phương án điều chỉnh để so sánh.
Nếu phương án không thay đổi thông số, bảng ghi “Chưa kéo thanh trượt”.
Dòng Giữ nguyên luôn dùng thông số đầu ca.

Điểm can thiệp bằng tổng `|giá trị mới − giá trị đầu ca| / khoảng thanh trượt`.
Chọn dòng đạt chỉ tiêu có điểm thấp nhất. Nếu bằng điểm, chọn dòng đứng trước trong bảng.
Giữ nguyên được chọn nếu đã đạt mục tiêu. Không tìm kiếm tối ưu ngoài năm phương án đã chọn.
Điểm này không quy đổi thành tiền hoặc chi phí lao động.
Thanh trượt cho phép giảm thông số; điểm can thiệp vẫn dùng độ thay đổi tuyệt đối.

Giới hạn được tính từ dataset gốc, không đổi theo nhật ký:

| Biến | Giới hạn |
| --- | --- |
| Công nhân | 2–60 người |
| Tăng ca | 0–phân vị 95, xấp xỉ 10.368 phút cả tổ |
| Tiền thưởng | 0–phân vị 95, bằng 88 BDT |

## Nhật ký, độ trôi và phiên bản mô hình

SQLite nằm tại `runtime/logs.sqlite`. Lọc lịch sử theo tên tổ chính xác và khoảng ngày gồm hai đầu.
Khoảng bộ lọc ngày là 2000–2100. Thời điểm ghi dùng UTC; ngày ca do người dùng chọn.
Dữ liệu thiếu, sai kiểu, không hữu hạn hoặc ngoài miền sẽ bị từ chối trước khi ghi.
Lỗi trong giao dịch SQLite không làm mất nhật ký đã có.

Độ trôi dữ liệu so sánh toàn bộ nhật ký với thống kê tập học của mô hình hiện tại.
Với mỗi biến, tính `|trung bình nhật ký − trung bình tập học| / độ lệch chuẩn tập học`.
Độ lệch chuẩn dùng `ddof=0`. Vượt ngưỡng mặc định 1 là **cảnh báo**.
Nếu độ lệch chuẩn bằng 0, trung bình khác nhau sẽ cảnh báo.
Dữ liệu không hợp lệ được ghi là **LỖI**, tách khỏi cảnh báo drift.
Chưa có nhật ký thì chưa tính drift. Đây là quy tắc đơn giản, không phải kiểm định thống kê.
Bộ lọc lịch sử không làm thay đổi tập nhật ký dùng cho drift hoặc huấn luyện.

Cần ít nhất 30 dòng mới so với mã nhật ký cuối cùng của mô hình hiện tại để huấn luyện lại.
Huấn luyện dùng tập học gốc cộng toàn bộ nhật ký hợp lệ; giữ nguyên tập kiểm tra gốc.
Tên tổ, tên sản phẩm và mã SKU không phải biến học.
Do dữ liệu không có ngày gốc, chưa đánh giá theo thời gian hoặc tại xưởng.
Chia ngẫu nhiên có thể để các bản ghi tương tự ở cả hai tập; đây là giới hạn đánh giá.

Mô hình và metadata lưu chung trong `runtime/model.joblib`.
Metadata có ngày học, R², MAE, số dòng, số dòng học/kiểm tra và thống kê sáu biến.
Trước khi ghi bản mới, lưu bản cũ tại `runtime/model.previous.joblib`.
**Quay lại bản cũ** khôi phục phiên bản liền trước; không xóa nhật ký.
Chỉ giữ một bản trước đó. Sau khi quay lại, số dòng mới được tính theo bản đã khôi phục.
Khóa hệ điều hành ngăn hai lần cập nhật đồng thời và tự nhả khi tiến trình dừng.
Không tự ý thay tệp joblib bằng tệp từ nguồn không tin cậy.

## Cấu hình và các lựa chọn bổ sung

Sửa `config.py` để đổi đường dẫn, giới hạn, ngưỡng R², drift hoặc số dòng mới tối thiểu.
Ngoài các quyết định đã chốt, triển khai chọn:

- Seed 42; ngưỡng cảnh báo R² 0,5; ngưỡng drift 1.
- Thống kê drift theo tập học; giữ cố định tập kiểm tra gốc khi huấn luyện lại.
- Chuẩn hóa điểm can thiệp theo khoảng thanh trượt, trọng số bằng nhau và ưu tiên thứ tự khi hòa.
- Giới hạn đầu ca và cuối ca theo miền dữ liệu: công nhân 2–89, tăng ca 0–25.920, thưởng 0–3.600, máy dừng 0–300.
- SMV phải từ 0,01 đến 1.000; năng suất thực tế ghi nhận từ 0 đến 2. Các ngưỡng kiểm tra này ở `RANGES`.
- Tên tổ bắt buộc, tối đa 200 ký tự; có thể nhập tên tạm khi chưa định danh tổ.
- Lưu một bản mô hình trước đó; ghi tệp nguyên tử và khóa bằng thư viện chuẩn.
- Nút dự báo lưu kết quả theo thông số và phiên bản; đổi đầu vào phải dự báo lại.
- Dùng tab theo bốn bước; màu nhấn xanh dầu `#00665C`, tiêu đề và nội dung Tahoma cài sẵn trên Windows.
- Không tải font ngoài. Máy khác cần có font hỗ trợ tiếng Việt; có font dự phòng DejaVu.
- Bố cục dựa vào trình tự vận hành trong tài liệu, không thêm màn hình quảng bá.

Giao diện hiện dùng nền #F8F9FA, mặt phẳng trắng và chữ #1E293B.
Chữ phụ #64748B đạt 4,515:1 trên nền; chữ trắng/nút chính đạt 6,874:1.
Nhãn xanh đạt 5,016:1; nhãn đỏ đạt 4,829:1; badge xanh đạt 6,492:1.
Chưa xác minh hiển thị font và dấu tiếng Việt bằng trình duyệt thật do công cụ UI bị chặn.

## Khác biệt giữa tài liệu và dữ liệu

- Tài liệu ghi BDT; Excel ghi NDT. Giao diện dùng nhãn BDT theo yêu cầu mới; chỉ đổi nhãn, không quy đổi giá trị.
- Tiêu đề Excel ghi `(%)` nhưng giá trị là tỷ lệ. Mục tiêu từ 0,07–0,8; thực tế có giá trị trên 1.
- Excel ghi sai chính tả `Năng xuất`. Hàm `rename_columns` giữ đúng tên gốc khi ánh xạ.
- Tài liệu nêu chọn tổ đầu ca nhưng dataset không có cột tổ. Chỉ ghi tên tổ tự do cuối ca.
- Tài liệu gợi ý nhân sự nguyên; dữ liệu có lao động quy đổi như 30,5 người.
- Dataset có 89 công nhân, 25.920 phút tăng ca và thưởng 3.600; thanh trượt dùng giới hạn thấp hơn đã chốt.
- Tài liệu dùng các tên `định mức`, `máy dừng`; Excel ghi `tạo sản phẩm`, `máy nghỉ`. Mô hình coi chúng là SMV và idle time theo yêu cầu.
- Tất cả 70 tên sản phẩm hiện có một SMV. Không có trường hợp phải thay bằng trung vị; logic trung vị đã được kiểm thử.
- Tài liệu mô tả tìm phương án tối ưu; bản này chỉ so sánh năm phương án theo quyết định đã chốt.

## Kiểm thử và bằng chứng

```powershell
cd C:\codev2\chieut4\garment_app
python -m pytest --cov
```

Cấu hình yêu cầu ít nhất 90% dòng mã ứng dụng. Không đưa mã test vào mẫu số độ phủ.
Báo cáo HTML tại `htmlcov/index.html`.
Test gồm đầu vào chính/biên/lỗi, mô hình, SMV, đèn, kịch bản, SQLite,
drift, huấn luyện, khôi phục, lỗi ghi tệp và tiến trình bị dừng.
AppTest chạy bốn bước, lọc nhật ký và thao tác huấn luyện/khôi phục trên thư mục tạm.
Nhật ký kiểm thử không đưa vào cơ sở dữ liệu chạy thật.

Máy chủ thật đã chạy bằng `python -m streamlit run app.py`; health trả HTTP 200, nội dung `ok`.
Chưa thao tác bốn bước trên trình duyệt thật. Browser host không khả dụng;
kênh Windows bị dừng vì chưa hỗ trợ thực thi chính sách URL của trình duyệt.
Do đó chưa xác minh bố cục desktop/điện thoại và dấu tiếng Việt bằng hình ảnh.
Không coi AppTest là bằng chứng kiểm tra trực quan.
Rà soát mã độc lập đã kiểm tra các sửa đổi và không còn blocker/major trong phạm vi đã rà soát.

`source_hashes.json` lưu SHA-256 của chín tệp gốc để đối chiếu tính nguyên vẹn.
Không sửa tệp gốc, không commit, không push và không gọi dịch vụ mô hình bên ngoài.
Chỉ tải hai gói kiểm thử pytest-cov và coverage theo sự cho phép riêng của người dùng.


## Kết quả xác minh lần bàn giao ban đầu

- Lệnh: `python -m pytest --cov -q`.
- Pytest: chạy 92 / đạt 92 / lỗi 0 / NOT RUN 0.
- Độ phủ mã ứng dụng: **98,29%**, 344/350 dòng; mỗi mô-đun trên 90%.
- AppTest: 5 bài kiểm thử giao diện, đã nằm trong tổng 92 bài.
- Máy chủ và health: chạy 1 / đạt 1 / lỗi 0 / NOT RUN 0.
- Kiểm tra trực quan: chạy 0 / đạt 0 / lỗi 0 / NOT RUN 7.
  Bảy kiểm tra gồm bốn bước trên trình duyệt, bố cục desktop, bố cục điện thoại và font/dấu tiếng Việt.
  Lý do: công cụ truy cập trình duyệt bị chặn như mô tả ở trên.
- Biên dịch bảy mô-đun bằng compileall: đạt.
- Tính nguyên vẹn nguồn: 9/9 SHA-256 khớp.
- Canny: không có phiên ghi nhận cho thư mục mới; không dùng làm bằng chứng kiểm thử.
- Hai warning từ môi trường/test được giữ nguyên theo yêu cầu, không phải test thất bại.
- Chưa hoàn thành điều kiện nghiệm thu bằng trình duyệt thật. R² thấp là giới hạn dự báo hiện có.


## Sửa ba lỗi giao diện sau kiểm tra trình duyệt

Phạm vi thay đổi: `app.py`, `tests/test_app.py` và tài liệu này.
Không sửa mô hình, cấu trúc dữ liệu, giới hạn cấu hình hoặc tệp nguồn.
Giữ nguyên CSS tiêu đề Tahoma đã được người dùng sửa.
Bỏ khai báo Georgia không còn dùng để tránh tái sử dụng nhầm.

Hai câu lệnh ba ngôi gọi Streamlit ở tab 2 và tab 3 đã đổi thành `if/else`.
Kiểm tra AST không còn biểu thức ba ngôi đứng riêng hoặc giá trị trần khác.
Các biểu thức chọn giá trị bên trong phép gán và ô bảng vẫn được giữ.
Chúng không phải câu lệnh trần để Streamlit magic hiển thị.

Thanh trượt vẫn là giá trị tuyệt đối.
Mặc định mới bằng `(giá trị đầu ca + giới hạn tối đa) / 2`.
Với đầu ca mặc định, các mức là 45 công nhân, khoảng 5.184 phút tăng ca và 44 BDT thưởng.
Đổi tiền tố khóa widget thành `what_absolute` để phiên đang mở không giữ mặc định cũ.
Lần tải lại sau cập nhật sẽ khởi tạo lại ba thanh trượt theo quy tắc mới.
Sau đó lựa chọn của người dùng được giữ khi ứng dụng chạy lại.
Không thêm thuật toán tối ưu hoặc thay đổi cách dự báo.

Thêm 9 ca kiểm thử:

- Ba ca AppTest thu toàn bộ nội dung hiển thị của ứng dụng, gồm bốn tab và tài liệu magic.
  Trước sửa: cả ba FAIL, tìm thấy cả `DeltaGenerator` và `Creator of Delta`.
  Sau sửa: cả ba PASS, gồm lúc mới mở và sau dự báo với mục tiêu 0 hoặc 0,8.
- CSS không có Georgia hoặc font serif cho h1/h2/h3; giữ chuỗi font Tahoma.
- Mặc định có năm dòng thông số khác nhau và ít nhất hai năng suất khác nhau.
  Không vượt giới hạn; Giữ nguyên bằng đúng dự báo tab 2.
- Phương án không thay đổi có lý do “Chưa kéo thanh trượt”; giữ lựa chọn sau chạy lại.
- AST không có câu lệnh giá trị trần ngoài lời gọi hàm.
- Hai ca kiểm tra mặc định khi đầu ca nằm ở biên dưới hoặc biên trên thanh trượt.

Lệnh xác minh: `python -m pytest -q --cov=. --cov-report=term-missing`.
Kết quả: chạy 101 / đạt 101 / lỗi 0 / NOT RUN 0; độ phủ mã ứng dụng 98,59%.
Máy chủ thật đang chạy `python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501`.
Health `http://127.0.0.1:8501/_stcore/health` trả HTTP 200, nội dung `ok`.
Kiểm tra trình duyệt thật sau lần sửa này: NOT RUN; chỉ dùng AppTest và health.
Giữ nguyên giờ huấn luyện, độ chính xác R²/MAE và warning pytest. Nhãn tiền thưởng hiện dùng BDT theo yêu cầu mới.
Chín tệp nguồn có SHA-256 khớp bản ghi trước triển khai.


## Giao diện công nghiệp và biểu đồ JavaScript

Phần này dành cho người vận hành và người bảo trì giao diện.
Mục đích là đọc nhanh dự báo, so sánh phương án và nhận biết độ trôi dữ liệu.

Bản thiết kế giữ Streamlit. Không tách backend, không thêm thư viện Python.
Dùng nền sáng #F8F9FA, mặt phẳng trắng và màu nhấn xanh dầu #00665C.
Tahoma dùng cho cả tiêu đề và nội dung để giữ dấu tiếng Việt.
Nội dung từ 16 px, chú thích từ 14 px; vùng bấm chính cao ít nhất 44 px.
KPI dự báo, mục tiêu, trạng thái và điểm can thiệp dùng chữ lớn.
Các ô nhập chia hai cột; bố cục thu về một cột khi thiếu chiều rộng.
Không dùng gradient, animation hoặc thẻ lồng nhau.

### Ba biểu đồ

- **Bước 2:** thước năng suất có dải đỏ/xanh và vạch mục tiêu.
  Trục tự mở rộng khi dự báo vượt 100%; số liệu gốc không bị kẹp trên.
- **Bước 3:** năm phương án đặt trên trục điểm can thiệp và năng suất.
  Vạch ngang là mục tiêu. Điểm hình thoi và badge chỉ phương án Python đã chọn.
  Bảng số liệu giữ đủ năm dòng; chênh lệch ghi bằng điểm phần trăm.
- **Bước 4:** sáu thanh độ trôi dữ liệu và vạch ngưỡng đang chọn.
  Trường hợp vô hạn dùng thanh ở mép thang đo; nút chi tiết ghi rõ “Không giới hạn”.
  Biểu đồ không đổi vô hạn thành 0. Bảng giữ nguyên giá trị drift.

Di chuột hoặc chạm điểm để xem tooltip. Các nút tên điểm hỗ trợ chạm và bàn phím.
Khi chưa có nhật ký, ứng dụng báo thiếu dữ liệu, không vẽ sáu số 0 giả.
Nếu biểu đồ không khởi tạo được, có thông báo tiếng Việt và số liệu đối chiếu bên ngoài biểu đồ.

Thanh trượt vẫn là mức tuyệt đối và giữ công thức mặc định đã chốt.
Vạch đen đánh dấu mức đầu ca; nhãn ghi đầu ca và tối đa.
Tooltip của thanh trượt hiện giá trị khi kéo. Sau khi thả thanh trượt,
Streamlit chạy lại để cập nhật bảng và biểu đồ từ kết quả Python.
Không chạy thêm mô hình dự báo trong JavaScript.
Điểm can thiệp chưa có phương án đạt được hiển thị bằng dấu “—”.

### Tệp và vận hành ngoại tuyến

- `app.py`: bố cục, KPI, form và nối các biểu đồ với kết quả nghiệp vụ.
- `ui.py`: mã hóa dữ liệu an toàn, tạo HTML biểu đồ, badge và mốc thanh trượt.
- `assets/charts.mjs`: cấu hình Chart.js, vạch mục tiêu, tooltip và điều khiển bàn phím.
- `assets/chart.umd.min.js`: Chart.js 4.6.1, đã tải một lần từ npm theo sự cho phép của người dùng.
- `assets/Chart.js-LICENSE.md`: giấy phép MIT của thư viện.

Giữ thư mục `assets` cạnh `app.py` khi sao chép ứng dụng.
Biểu đồ nhúng thư viện cục bộ; không cần CDN hoặc API khi vận hành.
SHA-256 thư viện: `87364cc2b2a76a6684929e7d6b80b18a897794db38400caff1fcf1791c6925d2`.
Sáu mô-đun backend và `source_hashes.json` không thay đổi.

### Kiểm thử bản giao diện này

```powershell
python -m pytest -q --cov=. --cov-report=term-missing
node --experimental-test-coverage --test-coverage-include=assets/charts.mjs --test-coverage-lines=90 --test tests/charts.test.mjs
```

Node.js chỉ dùng cho kiểm thử JavaScript, không cần khi vận hành ứng dụng.
Bản kiểm thử này dùng Node.js 24.18.0.

- Python: chạy 128 / đạt 128 / lỗi 0 / NOT RUN 0; độ phủ dòng 98,78%.
- JavaScript: chạy 8 / đạt 8 / lỗi 0 / NOT RUN 0; độ phủ dòng 100%, nhánh 98,80%.
- Không đưa mã thư viện bên thứ ba vào tỷ lệ độ phủ mã tự viết.
- Các test Chart.js dùng Canvas giả lập trong Node; không phải bằng chứng hiển thị trình duyệt thật.
- Kiểm thử mới về component biểu đồ đã FAIL trước triển khai do không có iframe; hiện PASS.
- AppTest kiểm tra ba iframe, dữ liệu đổi theo thanh trượt/ngưỡng, dự báo trên 100%, kẹp âm và bốn bước cũ.
- Test bảo mật kiểm tra chuỗi đóng thẻ script không thoát khỏi payload JSON.
- Các test tương phản chữ đều đạt ít nhất 4,5:1.
- Máy chủ Streamlit thật trên cổng 8501: health HTTP 200, nội dung `ok`.
- Đối chiếu baseline: 15/15 hash giữ nguyên, gồm sáu mô-đun backend, XLSX/DOCX và manifest nguồn.
- Rà soát độc lập không phát hiện blocker/major trong phạm vi mã giao diện.
- Không dọn warning pytest, không commit hoặc push.

Kiểm tra trực quan desktop, tablet, canvas khi đổi tab ẩn và tooltip cảm ứng vẫn cần trình duyệt thật.
Không dùng AppTest hoặc Canvas giả lập để khẳng định các kiểm tra đó đã đạt.

Lần kiểm tra kênh trình duyệt sau redesign: browser host không khả dụng.
Do đó desktop/tablet, resize khi đổi tab và tooltip cảm ứng là NOT RUN về kiểm tra trực quan.
Các bài AppTest vẫn PASS; chúng không thay thế kiểm tra trực quan này.


## GitHub và triển khai demo miễn phí

Dành cho người trình bày và người quản lý repo.
Không cần mua ổ đĩa hoặc đăng ký gói trả phí để dùng bản demo.

Repo: `NiTz130/garment-productivity-streamlit` (private).
Nhánh triển khai: `feat/initial-release`. Tệp chạy: `app.py`. Python: `3.13`.
Dùng Streamlit Community Cloud tại https://share.streamlit.io/.
Chọn repo, nhánh và tệp trên; trong Advanced settings chọn Python 3.13 rồi Deploy.
Lần đầu có thể cần đăng nhập và cấp quyền đọc repo private cho Streamlit.
Không nhập khóa API; ứng dụng này không cần dịch vụ dự báo bên ngoài.

Giữ nguyên thư mục `dataset/` và `assets/` khi triển khai.
Bản Excel đóng gói có SHA-256 bằng tệp gốc; không kèm các đề bài DOCX hoặc RAR.
Phiên bản thư viện Python được khóa trong `requirements.txt`.
`runtime/`, cơ sở dữ liệu, mô hình đã học, cache và secrets không đưa lên GitHub.
Trên host mới, mô hình ban đầu được huấn luyện từ dataset gốc và nhật ký bắt đầu rỗng.

Đây là demo dùng chung; chỉ nhập dữ liệu giả lập cho tên tổ và số liệu cuối ca.
Không dùng host miễn phí làm nơi lưu nhật ký chính thức.
Máy chủ khởi tạo lại có thể làm mất nhật ký và bản huấn luyện mới.

Trong bản clone không có bộ tài liệu gốc ở thư mục cha, test hash toàn bộ tài liệu là NOT RUN.
Test hash dataset đóng gói vẫn bắt buộc chạy. Trên máy gốc, test bảo vệ đủ chín tệp vẫn chạy.


### Bằng chứng đóng gói để xuất bản

- Máy nguồn: chạy 132 / đạt 132 / lỗi 0 / NOT RUN 0; độ phủ 98,79%.
- Bản xuất sạch: đạt 131 / lỗi 0 / NOT RUN 1; thiếu bộ đề bài gốc ngoài repo.
- JavaScript: chạy 8 / đạt 8 / lỗi 0; độ phủ dòng 100%.
- Giữ nguyên hash chín tệp gốc và manifest ở máy nguồn.
- `.gitattributes` tắt đổi dòng cho manifest để bản Git giữ nguyên byte.
- Không đưa runtime, dữ liệu nhật ký, mô hình đã học hoặc secrets lên repo.
- Repo private đã được tạo và push. Chưa có bằng chứng deploy cloud thành công.
- Deploy Community Cloud cần đăng nhập và cấp quyền đọc repo; không dùng dịch vụ trả phí.
