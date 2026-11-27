# Griductive Solver — Mã nguồn (Source)

Thư mục này chứa toàn bộ mã nguồn, dữ liệu câu đố (puzzles), bộ kiểm thử và tài nguyên giao diện đồ họa của dự án.

## Cấu trúc các module

- `main.py`: Điểm khởi chạy giao diện đồ họa desktop Pygame.
- `models.py`: Định nghĩa các schema dữ liệu dùng chung (dataclasses) và hàm phân giải tọa độ vùng `resolve_region()`.
- `game_engine.py`: Lớp `GameEngine`, quản lý vòng đời trạng thái trò chơi và bộ thẩm định ngữ nghĩa trực tiếp độc lập (`evaluate_clue`).
- `encoder.py`: Ánh xạ biến tất định, kiểm tra tính hợp lệ của manh mối và tự động mã hóa sang CNF.
- `dpll.py`: Bộ giải DPLL SAT Solver viết bằng Python thuần, hỗ trợ giả định (assumptions) và ghi nhận metrics hiệu năng.
- `agent.py`: Tác tử suy diễn logic (`LogicAgent`: phân loại hệ quả logic, kiểm tra tính duy nhất nghiệm, vòng lặp suy diễn không đoán và gợi ý).
- `solve.py`: Kịch bản CLI chạy vòng lặp suy diễn không đoán, in/xuất JSON vết suy diễn đầy đủ (`step`, `active_clue_ids`, `sat_queries`, phán quyết, manh mối mới) và kiểm tra tính duy nhất (`check_uniqueness`).
- `ui/`: Các thành phần giao diện Pygame, hiển thị bàn cờ, hộp thoại Trace Inspector, hiệu ứng lật thẻ và `AgentAdapter`.
- `assets/`: Ảnh avatar nhân vật và tài nguyên đồ họa cho giao diện.
- `puzzles/`: Tập dữ liệu câu đố chuẩn JSON cho các lưới kích thước 3×3, 4×4 và 5×5.
- `experiments/`: Kịch bản chạy benchmark thực nghiệm (`run_experiments.py`) và sinh biểu đồ (`plot_results.py`).
- `tests/`: Bộ kiểm thử đơn vị và tích hợp tự động (`pytest`).

## Cài đặt môi trường và thư viện

Yêu cầu Python 3.11 trở lên (ưu tiên bản 3.12). Khởi tạo môi trường ảo và cài đặt các thư viện phụ thuộc ngay tại thư mục này (`Source/` hoặc `src/`):

```bash
python -m venv .venv
source .venv/bin/activate        # Trên Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Khởi chạy giao diện đồ họa (GUI)

Đứng tại thư mục này (`Source/` hoặc `src/`):

```bash
python main.py
```

Có thể truyền thêm `--puzzle puzzles/sample_3x3.json` để mở trực tiếp một câu đố mẫu khi khởi động (hoặc chạy `python src/main.py --puzzle src/puzzles/sample_3x3.json` nếu đứng từ thư mục gốc của repository). Sau khi chạy `Auto Solve`, nhấn trực tiếp vào từng bước trong bảng **Deduction Trace** để xem chi tiết `Active Clues` và toàn bộ danh sách `SAT Queries`.

## Xuất vết suy diễn đầy đủ và kiểm tra tính duy nhất (CLI)

Đứng tại thư mục này (`Source/` hoặc `src/`):

```bash
python solve.py --puzzle puzzles/sample_3x3.json
python solve.py --puzzle puzzles/sample_4x4.json --json trace_4x4.json
python solve.py --all
```

Lệnh trên chạy vòng lặp suy diễn không đoán trên `PublicState` và kiểm tra tính duy nhất nghiệm riêng biệt trên toàn bộ tập manh mối (`UNIQUE` / `MULTIPLE` / `UNSAT`), đồng thời in đầy đủ `step`, `active_clue_ids`, toàn bộ `sat_queries`, phán quyết và manh mối mới tiết lộ.

## Chạy thực nghiệm Benchmark

Đứng tại thư mục này (`Source/` hoặc `src/`):

```bash
python experiments/run_experiments.py
```

Lệnh trên mặc định xuất tệp `benchmark_results.csv` (gồm đủ 6 nhóm chỉ số theo Mục 4.5, mỗi câu đố một dòng, giữ nguyên các trường hợp failure/timeout) tại thư mục gốc của repository (có thể chỉ định đường dẫn khác bằng `--output <path>`). Chạy kèm `--help` để xem các tùy chọn giới hạn thời gian mềm/cứng và số lần lặp lại.

## Vẽ biểu đồ kết quả thực nghiệm

Sau khi đã có tệp `benchmark_results.csv`:

```bash
python experiments/plot_results.py --input benchmark_results.csv --output assets
```

