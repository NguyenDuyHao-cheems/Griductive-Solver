# Griductive Solver
CSC14003 - Introduction to Artificial Intelligence, Project 2 - VNUHCM-US

## Giới thiệu tổng quan

Griductive là trò chơi suy luận logic suy diễn trên bảng lưới kích thước N x N. Mỗi ô trong bảng đại diện cho một nhân vật mang thân phận bí mật: CRIMINAL (kẻ phạm tội) hoặc INNOCENT (người vô tội). Trò chơi vận hành theo nguyên tắc suy diễn không đoán (no-guess deduction). Người chơi bắt đầu từ các manh mối ban đầu, suy luận logic để xác định danh tính từng ô mà không cần phỏng đoán ngẫu nhiên.

Hệ thống biểu diễn trạng thái bàn cờ bằng logic mệnh đề, tự động chuyển đổi các manh mối thành dạng chuẩn hội (Conjunctive Normal Form - CNF) và sử dụng bộ giải DPLL SAT Solver viết bằng Python thuần để thực hiện các truy vấn suy diễn logic.

## Các tính năng nổi bật

### Kiến trúc phân tách thông tin (Information Hiding)
Kiến trúc phân chia ranh giới rõ ràng giữa Game Engine và Logic Agent:
- Game Engine lưu trữ toàn bộ thông tin gốc của câu đố, bao gồm trạng thái bí mật (`hidden_status`) và các manh mối chưa mở. Game Engine chỉ cung cấp `PublicState` (chỉ gồm các ô đã mở và phán quyết đã chứng minh) cho giao diện người dùng và Logic Agent.
- Logic Agent và giao diện người dùng hoạt động hoàn toàn trên `PublicState`, không truy cập dữ liệu ẩn của trò chơi.

### Ngôn ngữ manh mối và phần mở rộng
Hệ thống hỗ trợ xác thực và mã hóa CNF cho toàn bộ ngôn ngữ manh mối quy định:
- 6 mẫu cốt lõi: FACT, SAME, DIFFERENT, EXACTLY, AT_LEAST, AT_MOST.
- 2 phần mở rộng: PARITY (tính chẵn lẻ số lượng ô CRIMINAL trong vùng) và COMPARE_COUNT (so sánh số lượng ô CRIMINAL giữa hai vùng theo các quan hệ GT, LT, EQ).
- 4 loại vùng không gian: ROW (hàng), COL (cột), NEIGHBORS (8 ô xung quanh, không tính ô gốc) và EXPLICIT (danh sách tọa độ chỉ định).

### Direct Semantic Evaluator
Bộ thẩm định ngữ nghĩa trực tiếp được tích hợp độc lập trong Game Engine. Mô-đun này kiểm tra tính thỏa mãn của một phép gán hoàn chỉnh đối với từng manh mối trực tiếp theo ngữ nghĩa bài toán mà không cần thông qua mã hóa CNF, phục vụ công tác đối chứng chéo kết quả của bộ giải.

### Bộ giải DPLL SAT Solver thuần Python
Bộ giải SAT được cài đặt từ đầu bằng Python thuần, không sử dụng thư viện SAT hoặc CSP bên ngoài trong quá trình thực thi:
- Cài đặt đầy đủ các bước: lan truyền đơn vị (unit propagation), phát hiện xung đột (conflict detection), chọn biến phân nhánh tất định và quay lui theo thứ tự thời gian (chronological backtracking).
- Hỗ trợ cơ chế giả định (assumptions) tạm thời: cho phép kiểm tra tính thỏa mãn của các giả thiết mà không làm biến đổi cấu trúc cơ sở tri thức gốc.
- Ghi nhận 4 chỉ số đo lường hiệu năng: số lần quyết định phân nhánh (`decisions`), số literal lan truyền (`propagations`), số lần quay lui (`backtracks`) và thời gian giải thực tế (`runtime_ms`).

### Deductive Logic Agent
Đại diện suy luận logic thực hiện các tác vụ:
- Phân loại hệ quả logic (entailment classification): xác định trạng thái của từng ô chưa mở thành CRIMINAL, INNOCENT, UNKNOWN hoặc INCONSISTENT.
- Vòng lặp suy diễn không đoán (No-Guess Deduction Loop): lần lượt tìm các ô có kết quả suy diễn bắt buộc, cập nhật bàn cờ và ghi nhận toàn bộ vết suy diễn (`deduction trace`).
- Gợi ý nước đi (hint): cung cấp tọa độ ô có thể suy luận kế tiếp kèm danh sách mã manh mối liên quan để hiển thị trên giao diện.
- Kiểm tra tính duy nhất nghiệm (uniqueness check): sử dụng mệnh đề chặn (blocking clause) để xác định câu đố có nghiệm duy nhất, vô nghiệm hay đa nghiệm.

### Giao diện người dùng
Giao diện trực quan hỗ trợ:
- Thao tác chơi thủ công (lật thẻ, gán phán quyết).
- Tô sáng trực quan các vùng liên quan đến manh mối trên lưới thông qua hàm chuẩn hóa tọa độ `resolve_region()`.
- Chế độ tự động giải (Auto Solve) và hiển thị chi tiết từng bước suy diễn logic.

## Cấu trúc thư mục dự án

```
Griductive-Solver/
├── docs/
│   ├── ARCHITECTURE.md          # Tài liệu thiết kế kiến trúc và luồng dữ liệu
│   └── Project2-Griductive-Solver.md # Đặc tả yêu cầu đồ án chi tiết
├── src/
│   ├── main.py                  # Điểm khởi chạy giao diện và máy chủ web
│   ├── models.py                # Schema dữ liệu dùng chung và hàm resolve_region
│   ├── game_engine.py           # Quản lý trạng thái trò chơi và Direct Semantic Evaluator
│   ├── encoder.py               # Bộ mã hóa CNF và kiểm tra hợp lệ manh mối
│   ├── dpll.py                  # Bộ giải DPLL SAT Solver và thu thập chỉ số
│   ├── agent.py                 # Logic Agent suy diễn, hint và uniqueness check
│   ├── puzzles/                 # Tập hợp câu đố mẫu định dạng JSON (3x3, 4x4, 5x5)
│   ├── experiments/             # Kịch bản thực nghiệm benchmark và trực quan hóa
│   └── tests/                   # Bộ kiểm thử tự động pytest
├── requirements.txt             # Danh sách thư viện phụ thuộc
├── REPORT.md                    # Bản nháp báo cáo kỹ thuật của đồ án
└── README.md                    # Tài liệu hướng dẫn sử dụng dự án
```

## Yêu cầu môi trường và cài đặt

Dự án yêu cầu phiên bản Python 3.11 trở lên.

### Thiết lập môi trường ảo

Khởi tạo và kích hoạt môi trường ảo:

Trên Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Trên Windows:
```bash
python -m venv .venv
.venv\Scripts\activate
```

### Cài đặt thư viện phụ thuộc

Cài đặt các gói thư viện được chỉ định trong `requirements.txt`:
```bash
pip install -r requirements.txt
```

Các thư viện chính bao gồm:
- `fastapi` và `uvicorn`: xây dựng máy chủ backend và phục vụ giao diện web.
- `pydantic`: chuẩn hóa và kiểm tra hợp lệ cấu trúc dữ liệu.
- `pytest`: thực thi bộ kiểm thử tự động.

## Hướng dẫn sử dụng và khởi chạy

### Khởi chạy ứng dụng và giao diện người dùng
Khởi động máy chủ backend và giao diện web:
```bash
uvicorn src.main:app --reload --port 8000
```
Sau khi máy chủ khởi động, mở trình duyệt web và truy cập địa chỉ:
```
http://localhost:8000
```

### Chạy bộ kiểm thử tự động
Thực thi toàn bộ các ca kiểm thử đơn vị và tích hợp:
```bash
pytest src/tests
```
Để xem chi tiết kết quả từng bài kiểm tra:
```bash
pytest src/tests -v
```

### Chạy thực nghiệm Benchmark
Thực hiện đo đạc hiệu năng tự động trên tập câu đố 3x3, 4x4 và 5x5:
```bash
python3 src/experiments/run_experiments.py
```
Dữ liệu kết quả thực nghiệm sẽ được xuất ra tệp `src/experiments/benchmark_results.csv` phục vụ thống kê và vẽ biểu đồ.

## Phân công nhiệm vụ nhóm

| Thành viên | Vai trò và trách nhiệm chính | Phần đóng góp trong báo cáo |
| :--- | :--- | :--- |
| **Hào** | **Game Engine, Puzzle Data & Đóng gói**<br>- Định nghĩa schemas dùng chung trong `models.py` và hàm `resolve_region()`.<br>- Xây dựng `GameEngine` và bộ thẩm định ngữ nghĩa `Direct Semantic Evaluator`.<br>- Chuẩn bị tập dữ liệu puzzle 3x3, 4x4, 5x5 chuẩn JSON.<br>- Tích hợp hệ thống và đóng gói sản phẩm nộp bài. | Mục 1 (Kế hoạch dự án), Mục 2 (Phát biểu bài toán) và tài liệu `README.md`. |
| **Tuân** | **Logical Representation & CNF Encoding**<br>- Thiết lập bảng ánh xạ biến tất định `VariableMap`.<br>- Xây dựng bộ kiểm tra hợp lệ manh mối và vùng không gian.<br>- Cài đặt bộ mã hóa CNF cho 6 mẫu cốt lõi và 2 mẫu mở rộng.<br>- Thu thập thống kê số lượng biến và mệnh đề logic. | Mục 3 (Mã hóa CNF, suy dẫn chi tiết binary clue và counting clue). |
| **Bảo** | **DPLL SAT Solver & Thực nghiệm**<br>- Cài đặt thuật toán DPLL bằng Python thuần (lan truyền đơn vị, quay lui, phát hiện xung đột).<br>- Hỗ trợ cơ chế giả định assumptions và đo đạc 4 metrics hiệu năng.<br>- Viết kịch bản chạy Benchmark tự động trên tập puzzle xuất tệp CSV. | Mục 4.1 (Thuật toán DPLL SAT Solver). |
| **Tuấn** | **Deductive Logic Agent**<br>- Cài đặt phân loại hệ quả logic (entailment classification).<br>- Xây dựng vòng lặp suy diễn không đoán và ghi nhận deduction trace.<br>- Cài đặt cơ chế kiểm tra tính duy nhất nghiệm (uniqueness check) và gợi ý nước đi (hint). | Mục 4.2 - 4.4 (Phân loại entailment, uniqueness check và deduction loop). |
| **Khoa** | **Giao diện GUI, Biểu đồ & Video Demo**<br>- Xây dựng giao diện tương tác người dùng (lưới ô, thẻ úp/ngửa, tô sáng vùng manh mối, hiển thị trace).<br>- Tích hợp các chức năng chơi thủ công, Hint và Auto Solve.<br>- Lập bảng, vẽ biểu đồ phân tích kết quả thực nghiệm từ dữ liệu CSV.<br>- Thực hiện video demo giới thiệu dự án. | Mục 5 (Thực nghiệm & Phân tích kết quả), Video Demo, Tài liệu tham khảo và Phụ lục. |
