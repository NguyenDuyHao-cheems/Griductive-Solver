# Nhật Ký Công Việc & Quyết Định Thiết Kế — Hào

> **Thành viên:** Hào  
> **Phạm vi trách nhiệm:** Game Engine (4.1), Direct Semantic Evaluator (4.2), Dữ liệu Puzzle (3x3, 4x4, 5x5), Quản lý Schema dùng chung, Đóng gói dự án & Báo cáo (Project Planning, Problem Formulation).

---

## 1. Bảng Tổng Hợp Tiến Độ Các Task

| Task | Hạng mục | Deadline | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| **Task 1** | Shared Schemas (`models.py`) & `resolve_region()` | 19/11 | **HOÀN THÀNH** | Single Source of Truth cho toàn nhóm, tránh lệch schema/tọa độ. |
| **Task 2** | Puzzle mẫu sớm (`sample_3x3.json`, `sample_4x4.json`) | 20/11 | **HOÀN THÀNH** | Dữ liệu kiểm thử sớm cho Encoder, Engine, Agent và GUI. |
| **Task 3** | Game Engine (`src/game_engine.py`) | 22/11 | **HOÀN THÀNH** | Quản lý puzzle, thông tin ẩn, vòng đời, submit phán quyết no-guess. |
| **Task 4** | Direct Semantic Evaluator (`evaluate_clue`) | 22/11 | **HOÀN THÀNH** | Bộ thẩm định ngữ nghĩa độc lập không qua CNF (Ground Truth Oracle). |
| **Task 5** | Bộ dữ liệu Benchmark đầy đủ (3x3, 4x4, 5x5) | 24/11 | Sắp tới | Phối hợp với `check_uniqueness` của Tuấn để xác thực nghiệm duy nhất. |
| **Task 6** | Báo cáo, README.md, requirements.txt, đóng gói nộp bài | 28/11 | Sắp tới | Hoàn thiện tài liệu theo quy chuẩn nộp bài của môn học. |

---

## 2. Các Quyết Định Thiết Kế Quan Trọng (Key Architectural Decisions)

### 2.1. Quyết định về Information Hiding (Task 3 — Mục 4.1)
- **Quyết định:** `GameEngine` nắm giữ toàn bộ `Puzzle` (bao gồm `hidden_status` và toàn bộ manh mối ẩn), nhưng hàm `get_public_state()` chỉ trả về một bản snapshot độc lập (defensive copy) của `PublicState`.
- **Lý do & Nguyên tắc:**
  - Logic Agent và GUI tuyệt đối không được truy cập vào thông tin ẩn dưới mọi hình thức.
  - Phán quyết của người chơi (`submit_verdict`) **KHÔNG** được kiểm tra bằng cách so sánh với `hidden_status`. Vì Griductive là trò chơi suy diễn *không đoán* (no-guess), việc đoán đúng đáp án bí mật khi KB chưa đủ điều kiện chứng minh vẫn bị từ chối với lý do `NOT_PROVABLE`.
  - Nếu phán quyết bị từ chối (`NOT_PROVABLE`, `CONTRADICTED`, `INCONSISTENT`), trạng thái bàn chơi được giữ nguyên 100% không làm lộ bất kỳ manh mối ẩn nào.

### 2.2. Quyết định về Giao Thức Tách Rời Tác Tử Logic (`LogicAgentProtocol`) (Task 3)
- **Quyết định:** Định nghĩa `LogicAgentProtocol` linh hoạt trong `game_engine.py`:
  - Hỗ trợ phương thức `classify_cell(public_state, coord) -> EntailmentStatus`.
  - Hỗ trợ fallback sang `check_entailment` hoặc callable trực tiếp `(public_state, coord)`.
- **Lý do:** Cho phép nhóm làm việc song song (Hào hoàn thành Game Engine và bộ Unit Test độc lập với `MockLogicAgent` đạt 100% pass trước ngày 22/11 mà không bị nghẽn do chờ Agent hay SAT solver của Tuấn & Bảo).

### 2.3. Quyết định về Direct Semantic Evaluator (`evaluate_clue`) (Task 4 — Mục 4.2)
- **Quyết định:**
  - Hàm `evaluate_clue(clue, assignment, size=None) -> bool` được cài đặt thuần túy bằng Python, tính toán trực tiếp giá trị chân lý dựa trên logic mệnh đề cho 6 mẫu cốt lõi (`FACT`, `SAME`, `DIFFERENT`, `EXACTLY`, `AT_LEAST`, `AT_MOST`) và 2 mẫu mở rộng (`PARITY`, `COMPARE_COUNT`).
  - Tuyệt đối không import hay phụ thuộc vào `encoder.py` hay bất kỳ thư viện SAT nào.
  - Hỗ trợ tự suy luận kích thước bàn cờ (`size = isqrt(len(assignment))`) nếu không truyền tường minh, giúp tương thích hoàn hảo với chữ ký `evaluate_clue(clue, assignment) -> bool` trong phân công đồ án.
- **Lý do & Vai trò:**
  - **Ground Truth Oracle:** Đóng vai trò là nguồn chân lý độc lập để kiểm chứng puzzle.
  - **Kiểm chứng chéo (Cross-Validation):** Tuân (Task 4.2 - CNF Encoder) sử dụng trực tiếp `evaluate_clue` để viết unit test đối chiếu chéo 100% giữa công thức CNF sinh ra và ngữ nghĩa gốc của manh mối.

### 2.4. Quyết định về Quản Lý Môi Trường & Dependency
- Đã thiết lập môi trường ảo `.venv` chuẩn Python 3.12.
- Đồng bộ hóa [src/requirements.txt](file:///F:/H%C3%A0o_Folder/Hao_folder/Projects/Griductive-Solver/src/requirements.txt) và [requirements.txt](file:///F:/H%C3%A0o_Folder/Hao_folder/Projects/Griductive-Solver/requirements.txt) (`fastapi`, `uvicorn[standard]`, `pydantic`, `pytest`).
- Bộ unit test chạy ổn định thông qua cả `unittest` tích hợp sẵn và `pytest`.
