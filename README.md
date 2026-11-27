# Griductive Solver
CSC14003 - Introduction to Artificial Intelligence, Project 2 - VNUHCM-US

## Giới thiệu tổng quan

Griductive là trò chơi suy luận logic suy diễn trên bảng lưới kích thước N x N. Mỗi ô trong bảng đại diện cho một nhân vật mang thân phận bí mật: CRIMINAL (kẻ phạm tội) hoặc INNOCENT (người vô tội). Trò chơi vận hành theo nguyên tắc suy diễn không đoán (no-guess deduction). Người chơi bắt đầu từ các manh mối ban đầu, suy luận logic để xác định danh tính từng ô mà không cần phỏng đoán ngẫu nhiên.

Hệ thống biểu diễn trạng thái bàn cờ bằng logic mệnh đề, tự động chuyển đổi các manh mối thành dạng chuẩn hội (Conjunctive Normal Form - CNF) và sử dụng bộ giải DPLL SAT Solver viết bằng Python thuần để thực hiện các truy vấn suy diễn logic.

## Các tính năng nổi bật

### Kiến trúc phân tách thông tin (Information Hiding)
Kiến trúc phân chia ranh giới rõ ràng giữa Game Engine và Logic Agent:
- **Game Engine** lưu trữ toàn bộ thông tin gốc của câu đố, bao gồm trạng thái bí mật (`hidden_status`) và các manh mối chưa mở. Game Engine chỉ cung cấp `PublicState` (chỉ gồm các ô đã mở và phán quyết đã chứng minh) cho giao diện người dùng và Logic Agent.
- **Logic Agent** và giao diện người dùng hoạt động hoàn toàn trên `PublicState`, tuyệt đối không truy cập dữ liệu ẩn của trò chơi.
- Khi người chơi gửi một phán quyết chưa thể chứng minh, Game Engine từ chối phán quyết (`NOT_PROVABLE` hoặc `CONTRADICTED`) và giữ nguyên trạng thái bàn cờ mà không làm lộ manh mối ẩn.

### Ngôn ngữ manh mối và phần mở rộng
Hệ thống hỗ trợ xác thực và mã hóa CNF cho toàn bộ ngôn ngữ manh mối quy định:
- **6 mẫu cốt lõi:** `FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST`, `AT_MOST`.
- **2 phần mở rộng:** `PARITY` (tính chẵn/lẻ số lượng ô CRIMINAL trong vùng) và `COMPARE_COUNT` (so sánh số lượng ô CRIMINAL giữa hai vùng theo các quan hệ `GT`, `LT`, `EQ`).
- **4 loại vùng không gian:** `ROW` (hàng), `COL` (cột), `NEIGHBORS` (8 ô lân cận xung quanh, không tính ô gốc) và `EXPLICIT` (danh sách tọa độ chỉ định).

### Direct Semantic Evaluator
Bộ thẩm định ngữ nghĩa trực tiếp (`evaluate_clue`) được tích hợp độc lập trong Game Engine. Mô-đun này kiểm tra tính thỏa mãn của một phép gán hoàn chỉnh đối với từng manh mối trực tiếp theo ngữ nghĩa bài toán mà không cần thông qua mã hóa CNF, đóng vai trò là nguồn chân lý độc lập (ground truth oracle) phục vụ kiểm chứng chéo bộ mã hóa.

### Bộ giải DPLL SAT Solver thuần Python
Bộ giải SAT được cài đặt từ đầu bằng Python thuần (`src/dpll.py`), không sử dụng bất kỳ thư viện SAT hoặc CSP bên ngoài nào trong runtime:
- Cài đặt đầy đủ các bước: lan truyền đơn vị (unit propagation), phát hiện xung đột (conflict detection), chọn biến phân nhánh tất định và quay lui theo thứ tự thời gian (chronological backtracking).
- Hỗ trợ cơ chế giả định (assumptions) tạm thời: cho phép kiểm tra tính thỏa mãn của các giả thiết (như $KB_t \wedge \neg C_i$) mà không làm biến đổi cấu trúc cơ sở tri thức gốc.
- Ghi nhận 4 chỉ số đo lường hiệu năng: số lần quyết định phân nhánh (`decisions`), số literal lan truyền (`propagations`), số lần quay lui (`backtracks`) và thời gian giải thực tế (`runtime_ms`).

### Deductive Logic Agent
Tác tử suy luận logic (`src/agent.py`) vận hành theo nguyên tắc không đoán:
- **Phân loại hệ quả logic (entailment classification):** phân loại trạng thái của từng ô chưa mở thành `CRIMINAL`, `INNOCENT`, `UNKNOWN` hoặc `INCONSISTENT` thông qua 2 truy vấn giả định phản chứng.
- **Vòng lặp suy diễn không đoán (No-Guess Deduction Loop):** quét các ô theo thứ tự hàng (row-major), gửi phán quyết bị bắt buộc đầu tiên tới Game Engine, nhận manh mối mới và lặp lại cho tới khi hoàn tất (`SOLVED`) hoặc dừng lại khi không còn phán quyết bị ép buộc (`UNKNOWN`).
- **Gợi ý nước đi (Hint):** tìm ô bị bắt buộc kế tiếp và rút gọn thành tập manh mối tối thiểu không thể lược bớt (`relevant_clue_ids`) để giao diện tô sáng trực quan.
- **Kiểm tra tính duy nhất nghiệm (uniqueness check):** sử dụng mệnh đề chặn (blocking clause) trên biến chính để phân định câu đố có nghiệm duy nhất (`UNIQUE`), vô nghiệm (`UNSAT`) hay đa nghiệm (`MULTIPLE`).

### Giao diện đồ họa Pygame Desktop GUI
Giao diện trực quan viết bằng Pygame (`src/ui/`):
- Bàn cờ co giãn đáp ứng linh hoạt cho lưới 3×3, 4×4 và 5×5.
- Bộ chọn câu đố (Puzzle Picker) hỗ trợ tải nhiều câu đố khác nhau và nút khởi động lại (Restart).
- Thao tác chơi thủ công (chọn ô gán phán quyết CRIMINAL / INNOCENT) kèm hiệu ứng lật thẻ 3D mượt mà (`CardFlipAnimation`).
- Nhấn chọn manh mối để tô sáng các ô tham chiếu trên bàn cờ.
- Nút **Hint** chỉ dẫn ô và manh mối liên quan; nút **Auto Solve** tự động giải từng bước kết nối trực tiếp với DPLL Logic Agent và hiển thị bảng vết suy diễn (`Deduction Trace`, đánh số nhất quán từ `#1`).
- Nhấn trực tiếp vào từng bước trong bảng **Deduction Trace** để mở hộp thoại **Trace Inspector** xem trọn vẹn `Active Clues`, toàn bộ danh sách `SAT Queries` (tô nổi truy vấn `UNSAT` phản chứng) và manh mối vừa tiết lộ.

## Cấu trúc thư mục dự án

```
Griductive-Solver/
├── docs/
│   ├── ARCHITECTURE.md          # Tài liệu thiết kế kiến trúc và luồng dữ liệu
│   ├── HAO.md                   # Nhật ký công việc và quyết định thiết kế của Hào
│   ├── DTUAN.md                 # Nhật ký công việc của Tuấn (Logic Agent)
│   ├── KHOA.md                  # Nhật ký công việc của Khoa (GUI & Biểu đồ)
│   └── Project2-Griductive-Solver.md # Đặc tả yêu cầu đồ án chi tiết
├── src/
│   ├── main.py                  # Điểm khởi chạy giao diện Pygame desktop
│   ├── models.py                # Schema dữ liệu dùng chung và hàm resolve_region
│   ├── game_engine.py           # Quản lý trạng thái trò chơi và Direct Semantic Evaluator
│   ├── encoder.py               # Bộ mã hóa CNF và kiểm tra hợp lệ manh mối
│   ├── dpll.py                  # Bộ giải DPLL SAT Solver thuần Python và đo metrics
│   ├── agent.py                 # Deductive Logic Agent, hint và uniqueness check
│   ├── solve.py                 # CLI xuất vết suy diễn đầy đủ (trace/JSON) và kiểm tra tính duy nhất
│   ├── ui/                      # Bộ điều khiển GUI Pygame, view bàn cờ và animations
│   ├── assets/                  # Sprite nhân vật avatar cho giao diện
│   ├── puzzles/                 # Bộ câu đố benchmark chuẩn JSON (3x3, 4x4, 5x5)
│   ├── experiments/             # Kịch bản thực nghiệm benchmark và vẽ biểu đồ
│   └── tests/                   # Toàn bộ kiểm thử tự động pytest
├── assets/                      # Biểu đồ và tệp tóm tắt Markdown từ thực nghiệm
├── requirements.txt             # Danh sách thư viện phụ thuộc
├── REPORT.md                    # Báo cáo kỹ thuật của đồ án
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
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### Cài đặt thư viện phụ thuộc

Cài đặt các gói thư viện được chỉ định trong `requirements.txt`:
```bash
pip install -r requirements.txt
```

Các thư viện chính bao gồm:
- `pygame`: giao diện đồ họa desktop GUI, rendering và quản lý animation.
- `matplotlib`: trực quan hóa biểu đồ phân tích thực nghiệm benchmark.
- `pytest`: thực thi bộ kiểm thử tự động.

## Hướng dẫn sử dụng và khởi chạy

### Khởi chạy giao diện Pygame Desktop GUI
Khởi động giao diện trò chơi từ thư mục gốc của repository:
```powershell
python src/main.py
```

Bạn cũng có thể chỉ định mở trực tiếp một câu đố cụ thể hoặc thư mục câu đố tùy chọn:
```powershell
python src/main.py --puzzle src/puzzles/sample_3x3.json
python src/main.py --puzzles-dir src/puzzles
```

**Các phím tắt điều khiển nhanh trên giao diện:**
- `L`: Mở bảng chọn câu đố (Load puzzle picker).
- `R`: Khởi động lại bàn chơi hiện tại (Restart).
- `H`: Nhận gợi ý nước đi tiếp theo (Hint).
- `C`: Gán phán quyết CRIMINAL cho ô đang chọn.
- `I`: Gán phán quyết INNOCENT cho ô đang chọn.
- `←` / `→`: Chuyển bước trước/sau khi mở hộp thoại xem chi tiết vết suy diễn (Trace Inspector).
- `Esc`: Đóng hộp thoại Trace Inspector / bảng chọn câu đố, hoặc hủy tô sáng manh mối.

### Xuất vết suy diễn đầy đủ và kiểm tra tính duy nhất (CLI — Mục 4.4)
Chạy bộ giải không đoán (`LogicAgent.solve_puzzle()`) kèm kiểm tra tính duy nhất nghiệm riêng biệt (`check_uniqueness()`) và in đầy đủ từng bước suy diễn (`step`, `active_clue_ids`, toàn bộ `sat_queries`, phán quyết và manh mối mới được tiết lộ):
```powershell
python src/solve.py --puzzle src/puzzles/sample_3x3.json
python src/solve.py --puzzle src/puzzles/sample_4x4.json --json trace_4x4.json
python src/solve.py --all
```
Tùy chọn hỗ trợ: `--json <file>` (xuất toàn bộ trace và kết quả uniqueness ra JSON), `--time-limit-ms <ms>` (giới hạn mềm cho vòng suy diễn), `--skip-uniqueness` (bỏ qua bước kiểm tra tính duy nhất), `--quiet` (chỉ ghi JSON, không in ra terminal).

### Chạy bộ kiểm thử tự động
Thực thi toàn bộ các ca kiểm thử đơn vị và tích hợp:
```powershell
pytest src/tests
```
Để xem chi tiết kết quả từng bài kiểm tra:
```powershell
pytest src/tests -v
```

### Chạy benchmark thực nghiệm (Mục 4.5)
Chạy agent trên toàn bộ bộ puzzle 3x3, 4x4, 5x5 trong `src/puzzles/` và xuất `benchmark_results.csv` ở thư mục gốc:
```powershell
python src/experiments/run_experiments.py
```
Tùy chọn: `--time-limit-ms 60000` (giới hạn mềm cho vòng suy diễn), `--hard-timeout 180` (giây; tiến trình con bị dừng nếu vượt), `--repeats 3` (`runtime_ms` là trung vị), `--output <csv>`. Ca `TIMEOUT`/`FAILED`/`UNKNOWN` vẫn được ghi vào CSV, không bị loại bỏ.

### Vẽ biểu đồ và bảng phân tích thực nghiệm
Sau khi có tệp dữ liệu `benchmark_results.csv` từ bộ đo benchmark:
```powershell
python src/experiments/plot_results.py --input benchmark_results.csv --output assets
```
Lệnh trên sẽ tự động xuất tệp `assets/benchmark_summary.md` và 4 biểu đồ phân tích dạng PNG vào thư mục `assets/` bao phủ đầy đủ 6 nhóm chỉ số và giữ nguyên các trường hợp failure/timeout.

### Thực nghiệm 3-SAT ngẫu nhiên (giới hạn của DPLL)
Sinh 3-SAT ngẫu nhiên theo seed cố định, giải bằng `DPLLSolver` và xuất `random_3sat_results.csv`:
```powershell
python src/experiments/random_3sat.py --vars 150 --ratio 4.2 --seeds 0 1 2 3 4 --hard-timeout 600
```
Mỗi seed chạy trong tiến trình con riêng; seed vượt `--hard-timeout` (giây) được ghi là `TIMEOUT`.

## Phân công nhiệm vụ nhóm

| Thành viên | Vai trò và trách nhiệm chính | Phần đóng góp trong báo cáo |
| :--- | :--- | :--- |
| **Hào** | **Game Engine, Puzzle Data & Đóng gói**<br>- Định nghĩa schemas dùng chung trong `models.py` và hàm `resolve_region()`.<br>- Xây dựng `GameEngine` và bộ thẩm định ngữ nghĩa `Direct Semantic Evaluator`.<br>- Chuẩn bị tập dữ liệu puzzle 3x3, 4x4, 5x5 chuẩn JSON.<br>- Tích hợp hệ thống và đóng gói sản phẩm nộp bài. | Mục 1 (Kế hoạch dự án), Mục 2 (Phát biểu bài toán) và tài liệu `README.md`. |
| **Tuân** | **Logical Representation & CNF Encoding**<br>- Thiết lập bảng ánh xạ biến tất định `VariableMap`.<br>- Xây dựng bộ kiểm tra hợp lệ manh mối và vùng không gian.<br>- Cài đặt bộ mã hóa CNF cho 6 mẫu cốt lõi và 2 mẫu mở rộng.<br>- Thu thập thống kê số lượng biến và mệnh đề logic. | Mục 3 (Mã hóa CNF, suy dẫn chi tiết binary clue và counting clue). |
| **Bảo** | **DPLL SAT Solver & Thực nghiệm**<br>- Cài đặt thuật toán DPLL bằng Python thuần (lan truyền đơn vị, quay lui, phát hiện xung đột).<br>- Hỗ trợ cơ chế giả định assumptions và đo đạc 4 metrics hiệu năng.<br>- Viết kịch bản chạy Benchmark tự động trên tập puzzle xuất tệp CSV. | Mục 4.1 (Thuật toán DPLL SAT Solver). |
| **Tuấn** | **Deductive Logic Agent**<br>- Cài đặt phân loại hệ quả logic (entailment classification).<br>- Xây dựng vòng lặp suy diễn không đoán và ghi nhận deduction trace.<br>- Cài đặt cơ chế kiểm tra tính duy nhất nghiệm (uniqueness check) và gợi ý nước đi (hint). | Mục 4.2 - 4.4 (Phân loại entailment, uniqueness check và deduction loop). |
| **Khoa** | **Giao diện GUI, Biểu đồ & Video Demo**<br>- Xây dựng giao diện desktop Pygame (lưới ô, thẻ úp/ngửa, tô sáng vùng manh mối, hiển thị trace).<br>- Tích hợp các chức năng chơi thủ công, Hint và Auto Solve kết nối Agent.<br>- Lập bảng, vẽ biểu đồ phân tích kết quả thực nghiệm từ dữ liệu CSV.<br>- Thực hiện video demo giới thiệu dự án. | Mục 5 (Thực nghiệm & Phân tích kết quả), Video Demo, Tài liệu tham khảo và Phụ lục. |
