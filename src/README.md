# Griductive Solver — Mã nguồn (Source)

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

Yêu cầu Python 3.11 trở lên (ưu tiên bản 3.12). Khởi tạo môi trường ảo và cài đặt các thư viện phụ thuộc ngay tại thư mục này:

```bash
python -m venv .venv
source .venv/bin/activate        # Trên Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Khởi chạy giao diện đồ họa (GUI)

Đứng tại thư mục này:
```bash
python main.py
```

Sau khi chạy `Auto Solve`, nhấn trực tiếp vào từng bước trong bảng **Deduction Trace** để xem chi tiết `Active Clues` và toàn bộ danh sách `SAT Queries`.

Phím tắt trên giao diện:
- `L`: Mở bảng chọn câu đố (Load).
- `R`: Khởi động lại bàn chơi hiện tại (Restart).
- `H`: Nhận gợi ý nước đi tiếp theo (Hint).
- `C` / `I`: Gán phán quyết CRIMINAL / INNOCENT cho ô đang chọn.
- `←` / `→`: Chuyển bước trước/sau trong hộp thoại Trace Inspector.
- `Esc`: Đóng hộp thoại hoặc bảng chọn câu đố, hoặc hủy tô sáng manh mối.

## Xuất vết suy diễn đầy đủ và kiểm tra tính duy nhất (CLI)

Đứng tại thư mục này:

```bash
python solve.py --puzzle puzzles/sample_3x3.json
python solve.py --puzzle puzzles/sample_4x4.json --json trace_4x4.json
python solve.py --all
```

Lệnh trên chạy vòng lặp suy diễn không đoán trên `PublicState` và kiểm tra tính duy nhất nghiệm riêng biệt trên toàn bộ tập manh mối (`UNIQUE` / `MULTIPLE` / `UNSAT`), đồng thời in đầy đủ `step`, `active_clue_ids`, toàn bộ `sat_queries`, phán quyết và manh mối mới tiết lộ.

## Chạy thực nghiệm Benchmark

Đứng tại thư mục này:

```bash
python experiments/run_experiments.py
```

Lệnh trên mặc định xuất tệp `benchmark_results.csv` (gồm đủ 6 nhóm chỉ số theo Mục 4.5, mỗi câu đố một dòng, giữ nguyên các trường hợp failure/timeout) tại thư mục cha của thư mục này (gốc repository, tức `Source/` trong bài nộp; có thể chỉ định đường dẫn khác bằng `--output <path>`). Chạy kèm `--help` để xem các tùy chọn giới hạn thời gian và số lần lặp lại.

Thực nghiệm 3-SAT ngẫu nhiên (giới hạn của DPLL), xuất `random_3sat_results.csv` cũng tại thư mục cha:

```bash
python experiments/random_3sat.py --vars 150 --ratio 4.2 --seeds 0 1 2 3 4 --hard-timeout 600
```

## Vẽ biểu đồ kết quả thực nghiệm

Sau khi đã có tệp `benchmark_results.csv` (nằm ở thư mục cha):

```bash
python experiments/plot_results.py --input ../benchmark_results.csv --output ../assets
```

