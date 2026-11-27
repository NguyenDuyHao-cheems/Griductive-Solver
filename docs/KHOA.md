# Nhật Ký Công Việc & Quyết Định Thiết Kế — Khoa

> **Thành viên:** Khoa  
> **Phạm vi trách nhiệm:** GUI (4.1), bảng/biểu đồ và nhận xét thực nghiệm (4.5, 4.6), Video Demo (4.7), References & AI Appendix (4.6).

---

## 1. Bảng Tổng Hợp Tiến Độ Các Task

| Task | Hạng mục | Mốc theo kế hoạch | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| **Task 1** | Tài nguyên hình ảnh và tiện ích GUI | 23/11 | **HOÀN THÀNH** | Đã thêm 50 avatar, widget Pygame, theme, text helper và hiệu ứng lật thẻ vào `src/`. |
| **Task 2** | GUI bàn chơi và chơi thủ công | 23/11–25/11 | **PHẦN UI HOÀN THÀNH; CHỜ AGENT** | Đã cài đặt `src/main.py`, `src/ui/app.py`, `src/ui/board_view.py`, `src/ui/clue_formatter.py`; hỗ trợ 3×3–5×5, Load, Restart, highlight và `CardFlipAnimation`. Xác nhận verdict thủ công đang bị vô hiệu hóa cho tới khi `src/agent.py` được cài đặt. |
| **Task 3** | Highlight, Hint, Auto Solve và trace | 25/11 | **SẴN SÀNG TÍCH HỢP AGENT** | Đã cài đặt `src/ui/agent_adapter.py`, hiển thị Hint (`hint_coord` + `relevant_clue_ids`), Auto Solve từng bước có chờ animation và bảng `DeductionStep` trace. Các nút phụ thuộc `LogicAgent` tự động ở trạng thái disabled kèm thông báo rõ cho tới khi Tuấn hoàn tất `src/agent.py`. |
| **Task 4** | Biểu đồ và nội dung thực nghiệm | 27/11 | **ĐÃ CÓ SCRIPT, CHỜ CSV** | Đã cài đặt `src/experiments/plot_results.py` xử lý đủ 6 nhóm chỉ số, giữ nguyên failure/timeout/missing-status và không vẽ số đo thiếu thành 0; xuất `benchmark_summary.md` + 4 biểu đồ PNG vào `assets/`. Chờ `benchmark_results.csv` từ Bảo để tạo biểu đồ thật và viết nhận xét. |
| **Task 5** | Video demo | 27/11 | **CHƯA BẮT ĐẦU** | Phụ thuộc bản GUI và solver tích hợp hoàn chỉnh của nhóm. |
| **Task 6** | References & AI Appendix | 27/11 | **CHƯA BẮT ĐẦU** | Cần tổng hợp nguồn và prompt từ cả nhóm. |

---

## 2. Phạm Vi & Mã Nguồn Đã Triển Khai

### 2.1. Tầng GUI (`src/main.py`, `src/ui/`)

GUI là tầng trình bày. Nó đọc trạng thái công khai từ `GameEngine.get_public_state()` và gửi thao tác qua API của `GameEngine` / `AgentAdapter`. GUI không đọc `hidden_status`, clue của thẻ úp, hay parse JSON puzzle trực tiếp.

Các chức năng đã cài đặt:

- Khởi chạy qua `python src/main.py` (hỗ trợ tùy chọn `--puzzle <path>` và `--puzzles-dir <dir>`), có xử lý lỗi gọn khi thiếu `pygame`.
- Màn chọn puzzle (`Load`) liệt kê file `*.json` trong `src/puzzles/` và tải độc quyền qua `GameEngine.load_puzzle()`.
- Hiển thị lưới 3×3 đến 5×5 co giãn theo kích thước cửa sổ (`pygame.RESIZABLE`), tọa độ hàng/cột dùng `models.rc_to_coord()` / `coord_to_rc()`, tên/nghề nghiệp và avatar từ `CharacterInfo`, thẻ úp/ngửa, nhãn `CRIMINAL`/`INNOCENT` và manh mối đã mở từ `PublicState`.
- Cho phép chọn ô chưa giải và gửi verdict `CRIMINAL`/`INNOCENT` tới `GameEngine.submit_verdict()` (kèm phím tắt `L`, `R`, `H`, `C`, `I`, `Esc` và cuộn chuột cho danh sách clue/trace).
- Thông báo rõ `ENTAILED`, `NOT_PROVABLE`, `CONTRADICTED`, `INCONSISTENT`; chỉ chạy `CardFlipAnimation` khi `VerdictResponse.accepted` là `True`.
- Click manh mối đã mở trên thẻ hoặc trong bảng `Revealed Clues` để tô sáng các ô tham chiếu qua `GameEngine.get_clue_highlight_cells()` (dùng chung `models.resolve_region()`).
- Nút `Load`, `Restart`, `Hint`, `Auto Solve` (chuyển sang `Stop` khi đang chạy, bước cách nhau `0.55s` sau khi lật thẻ xong) và bảng cuộn `Deduction Trace` hiển thị từng `DeductionStep`.
- Cô lập toàn bộ lời gọi tới `LogicAgent` trong `src/ui/agent_adapter.py`; khi `src/agent.py` chưa có implementation, nút verdict/`Hint`/`Auto Solve` ở trạng thái disabled kèm thông báo rõ thay vì giả lập logic hay đọc đáp án ẩn.

Danh sách file GUI của Khoa:

- `src/main.py`: entry point CLI khởi chạy GUI.
- `src/ui/app.py`: controller `GriductiveApp` điều phối vòng lặp Pygame, `GameEngine`, `AgentAdapter`, animation, phím tắt và xử lý ngoại lệ an toàn.
- `src/ui/board_view.py`: `BoardViewState`, `LayoutMetrics`, bố cục đáp ứng 3×3–5×5, vẽ thẻ úp/ngửa, highlight vùng/hint, bảng `Revealed Clues`, `Deduction Trace` và modal chọn puzzle.
- `src/ui/agent_adapter.py`: `AgentAdapter` & `AutoSolveStepResult`, tự kiểm tra năng lực thực (`classify_cell`/`check_entailment`, `get_hint`/`hint`/`suggest_hint`, `step`/`deduce_step`/`solve_step`/`next_step`) và **chỉ truyền `PublicState`** cho Agent.
- `src/ui/clue_formatter.py`: liệt kê file puzzle không đọc nội dung, ánh xạ clue đã mở theo `PublicState`, định dạng text fallback cho 6 mẫu cốt lõi + 2 mẫu mở rộng (`PARITY`, `COMPARE_COUNT`) và tiện ích highlight qua `GameEngine`.
- `src/ui/button.py`: nút Pygame dùng lại, mở rộng tùy chọn `fill_color`/`hover_color`/`text_color` tương thích ngược cho nút `CRIMINAL`/`INNOCENT`.
- `src/ui/avatar_manager.py`, `src/ui/animations.py`, `src/ui/text.py`, `src/ui/theme.py`, `src/ui/__init__.py`: tiện ích đồ họa Pygame; `__init__.py` giữ gọn nhẹ không eager-import `pygame`.
- `src/assets/generate_avatars.py` & `src/assets/sprites/avatars/`: 50 avatar PNG gốc (256×256 RGBA) do Khoa tự sinh bằng Pillow, không dùng tài nguyên bên thứ ba chưa cấp phép (chi tiết tại `src/assets/README.md`).

### 2.2. Biểu Đồ Thực Nghiệm (`src/experiments/plot_results.py`)

- CLI: `python src/experiments/plot_results.py --input benchmark_results.csv --output assets`.
- Chuẩn hóa các tên cột alias cho đủ **6 nhóm chỉ số**: primary/aux variables, CNF clauses, SAT calls, decisions/propagations/backtracks, deduction steps/reveal waves, runtime (ms/s).
- Không loại bỏ và không đánh đồng các ca lỗi thành thành công:
  - Dòng thiếu cột/giá trị trạng thái được gán `MISSING_STATUS` (nhóm `FAILED`), tuyệt đối không tự coi là `SOLVED`.
  - Số đo số bị thiếu được in là `-` trong bảng Markdown và dùng `NaN` (để trống, không vẽ thành `0`) trong biểu đồ.
  - Trung bình theo kích thước lưới chỉ tính trên nhóm `SOLVED`; `TIMEOUT`, `FAILED`, `UNKNOWN`, `MISSING_STATUS` được giữ đầy đủ trong bảng chi tiết, mục `Failure & Timeout Cases` và đánh dấu trực quan trên biểu đồ.
- Xuất 5 tệp vào thư mục output (mặc định `assets/`): `benchmark_summary.md`, `chart_1_cnf_size.png`, `chart_2_dpll_metrics.png`, `chart_3_deduction_runtime.png`, `chart_4_size_scaling.png`.

### 2.3. Kiểm Thử & Dependencies

- `src/tests/test_ui.py`: kiểm thử `AgentAdapter` (cả trạng thái chưa có `src/agent.py` và Mock Agent), `clue_formatter`, information hiding và `GriductiveApp` headless với Pygame trên lưới 3×3, 4×4, 5×5.
- `src/tests/test_plot_results.py`: kiểm thử đọc CSV, giữ nguyên failure/timeout, loại trừ ca lỗi khỏi trung bình thành công, xuất bảng Markdown và 4 biểu đồ PNG qua CLI.
- `requirements.txt` & `src/requirements.txt`: đã bổ sung `pygame>=2.5.0` và `matplotlib>=3.8.0`.

---

## 3. Quyết Định Thiết Kế

### 3.1. Chỉ render PublicState

Nguồn dữ liệu để vẽ bàn là `PublicState`: `size`, `characters`, `proved_verdicts`, `revealed_clues`, `unsolved_coords`. Không truyền `PuzzleCell` hay đọc trực tiếp JSON trong view. `GameEngine` chịu trách nhiệm đọc JSON và giữ thông tin ẩn.

### 3.2. GameEngine sở hữu luật lật thẻ

GUI gửi verdict tới `submit_verdict(coord, verdict)` và hiển thị `VerdictResponse`. Chỉ response được chấp nhận mới bắt đầu `CardFlipAnimation` và đưa manh mối mới vào vùng hiển thị. Khi bị từ chối, giữ nguyên `PublicState` và không tiết lộ nội dung clue.

### 3.3. Highlight dùng chung quy tắc vùng

Không tự ánh xạ `A1` thành chỉ số lưới hoặc tự triển khai ROW/COL/NEIGHBORS/EXPLICIT. GUI gọi `GameEngine.get_clue_highlight_cells(clue_id)` (chỉ chấp nhận clue đã mở) và helper tọa độ trong `models.py`.

### 3.4. Không giả lập LogicAgent và chỉ truyền PublicState

`src/agent.py` hiện chưa có implementation. `AgentAdapter` tự động phát hiện và giữ trạng thái disabled cùng thông báo rõ cho Hint, Auto Solve và xác nhận verdict cho tới khi `LogicAgent` thật của Tuấn được tích hợp. Khi gọi Agent, adapter chỉ truyền `PublicState` và nộp verdict qua `GameEngine.submit_verdict()`.

### 3.5. Trung thực dữ liệu thực nghiệm

Bảo phụ trách chạy benchmark và xuất CSV. `src/experiments/plot_results.py` giữ toàn bộ dòng `TIMEOUT`/`FAILED`/`UNKNOWN`/`MISSING_STATUS`, tách trung bình của nhóm `SOLVED` và không biến số đo bị thiếu thành `0`.

---

## 4. Phụ Thuộc và Việc Cần Phối Hợp

- **Hào:** `GameEngine`, `PublicState`, bộ puzzle và vòng đời Load/Restart (đã tích hợp).
- **Tuấn:** API `LogicAgent` cho phân loại entailment, Hint, Auto Solve và `DeductionStep` trong `src/agent.py`.
- **Bảo:** `benchmark_results.csv` có sáu nhóm chỉ số, gồm cả failure/timeout.
- **Cả nhóm:** nguồn tham khảo, prompt AI, bản build cuối và nội dung video.

---

## 5. Tiêu Chí Hoàn Thành

- `python src/main.py` mở được GUI và hiển thị được puzzle 3×3, 4×4, 5×5.
- GUI dùng duy nhất trạng thái công khai; phán quyết sai/không chứng minh không làm lộ clue.
- Highlight, Load, Restart hoạt động ngay; Hint, Auto Solve và xác nhận verdict kích hoạt tự động khi `src/agent.py` hoàn tất.
- GUI hiển thị trace và cập nhật bàn kèm hiệu ứng lật thẻ sau mỗi bước.
- `python src/experiments/plot_results.py --input <csv> --output assets` xuất bảng Markdown và 4 biểu đồ PNG đủ 6 nhóm chỉ số, giữ nguyên failure/timeout/missing-status.
- Video demo 5–10 phút có thuyết minh/phụ đề, link Drive mở được theo quyền yêu cầu.
- References và AI Appendix được tổng hợp vào báo cáo.
