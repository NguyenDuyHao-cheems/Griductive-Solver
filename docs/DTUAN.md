# Nhật Ký Công Việc & Quyết Định Thiết Kế — Tuấn

> **Thành viên:** Tuấn  
> **Phạm vi trách nhiệm:** Deductive Logic Agent (Mục 4.4) trong `src/agent.py`: Entailment Classification, Uniqueness Check, No-Guess Deduction Loop, Deduction Trace, Hint. Báo cáo: phần *Algorithms* (entailment, uniqueness check, deduction loop).

---

## 1. Bảng Tổng Hợp Tiến Độ Các Task

| Task | Hạng mục | Deadline | Trạng thái | Ghi chú |
| :--- | :--- | :--- | :--- | :--- |
| **Task 1** | Entailment Classification (`classify_cell`, `classify_all`) | 23/11 | **HOÀN THÀNH** | 4 nhãn CRIMINAL / INNOCENT / UNKNOWN / INCONSISTENT, đúng Mục 3.4. |
| **Task 2** | Uniqueness Check (`check_uniqueness`) | 23/11 | **HOÀN THÀNH** | Trả về `UNIQUE` / `MULTIPLE` / `UNSAT`; Hào dùng để xác thực bộ puzzle. |
| **Task 3** | No-Guess Deduction Loop (`solve_puzzle`) | 24/11 | **HOÀN THÀNH** | Auto Solve theo row-major, dừng ở SOLVED / UNKNOWN / INCONSISTENT / TIMEOUT. |
| **Task 4** | Deduction Trace (`DeductionStep`, `SolveReport`) | 24/11 | **HOÀN THÀNH** | Ghi từng truy vấn SAT và cộng dồn metrics cho benchmark. |
| **Task 5** | Hint (`hint`) | 24/11 | **HOÀN THÀNH** | Ô bị bắt buộc đầu tiên + tập manh mối tối thiểu chứng minh nó. |
| **Task 6** | Báo cáo mục *Algorithms* (phần Agent) | 27/11 | Sắp tới | Chờ trace mẫu từ benchmark (26/11). |

---

## 2. Nền Tảng Chung

- **Biến chính `C_i`:** mỗi ô có một biến Boolean, `C_i = True` nghĩa là ô i là Criminal. Encoder đánh số theo row-major (lưới 3×3: A1=1, B1=2, C1=3, A2=4, …). Biến phụ của các clue đếm có số lớn hơn N².
- **`KB_t`:** CNF của các manh mối đã lật cộng với mệnh đề đơn (unit clause) cho mỗi phán quyết đã chứng minh. Agent chỉ dựng `KB_t` từ `PublicState`, không bao giờ đọc `hidden_status` hay manh mối chưa lật.
- **SAT / UNSAT:** DPLL trả lời "có cách gán nào làm mọi mệnh đề cùng đúng không". UNSAT nghĩa là các điều kiện mâu thuẫn nhau.

---

## 3. Các Quyết Định Thiết Kế Quan Trọng

### 3.1. Entailment Classification (Task 1)
- **Quyết định:** với ô i, hỏi hai truy vấn bằng *assumption* (`DPLLSolver.solve([±C_i])`), không sửa KB gốc:

| `KB_t ∧ ¬C_i` | `KB_t ∧ C_i` | Nhãn |
| :--- | :--- | :--- |
| UNSAT | SAT | CRIMINAL |
| SAT | UNSAT | INNOCENT |
| SAT | SAT | UNKNOWN |
| UNSAT | UNSAT | INCONSISTENT |

- **Lý do chỉ cần 2 lần gọi SAT:** `KB_t ≡ (KB_t ∧ C_i) ∨ (KB_t ∧ ¬C_i)`, nên "cả hai UNSAT" tương đương "`KB_t` UNSAT". Không cần gọi thêm lần thứ ba để kiểm tra KB.
- `classify_cell` là đúng interface `LogicAgentProtocol` mà `GameEngine.submit_verdict` gọi. Engine ánh xạ nhãn thành ENTAILED / CONTRADICTED / NOT_PROVABLE / INCONSISTENT.
- `classify_all` mã hóa KB một lần và dùng chung một solver cho mọi ô (các truy vấn độc lập vì assumption chỉ sống trong một lần `solve`).

### 3.2. Uniqueness Check (Task 2)
- **Quy trình:**
  1. Mã hóa toàn bộ tập clue bằng `encode_clues(clues, size)`, giải lần 1. UNSAT thì trả `"UNSAT"`.
  2. Lấy nghiệm M, tạo **blocking clause** trên biến chính: mỗi ô lấy literal ngược với giá trị trong M, nối bằng OR. Mệnh đề này chỉ loại đúng bàn cờ M.
  3. Giải lần 2: UNSAT thì `"UNIQUE"`, SAT thì `"MULTIPLE"`.
- **Lý do chỉ chặn biến chính:** hai nghiệm chỉ khác nhau ở biến phụ vẫn là cùng một bàn cờ; chặn cả biến phụ có thể báo nhầm `MULTIPLE`.
- **Phạm vi:** chỉ xét tập clue, đúng yêu cầu đề. Trạng thái các thẻ mở sẵn không được tính; nếu muốn tính thì thêm chúng dưới dạng clue `FACT`.

### 3.3. No-Guess Deduction Loop (Task 3)
- **Mỗi bước t:**
  1. Lấy `PublicState` từ engine. Hết ô chưa giải thì **SOLVED**.
  2. Quét ô chưa giải theo row-major, phân loại như Task 1, dừng ở ô đầu tiên có nhãn khác UNKNOWN. Nhãn INCONSISTENT thì dừng **INCONSISTENT**; toàn UNKNOWN thì dừng **UNKNOWN** (không đoán).
  3. Gửi `engine.submit_verdict(coord, verdict)`; engine lật thẻ, tạo `KB_{t+1}`. Lặp lại.
- **Tính đúng (soundness):** ô được chọn đúng trong mọi mô hình của `KB_t`, trong đó có đáp án thật, nên phán quyết luôn trùng `hidden_status` dù agent không đọc nó.
- **Tất định:** thứ tự quét row-major cố định, DPLL chọn biến cố định, nên chạy lại cho trace y hệt.
- **Timeout:** `time_limit_ms` áp cho cả lượt chạy; mỗi lần `solve` nhận phần thời gian còn lại. Hết giờ thì trả **TIMEOUT**, giữ nguyên trace và metrics đã thu (đúng yêu cầu báo cáo ca thất bại ở Mục 4.5).
- **Bảo vệ:** nếu engine từ chối một phán quyết đã chứng minh, ném `RuntimeError` thay vì lặp vô hạn.
- Agent chỉ dùng `engine.get_public_state()` và `engine.submit_verdict()`.

### 3.4. Deduction Trace (Task 4)
Mỗi bước sinh một `DeductionStep` (schema trong `models.py`):

| Trường | Nội dung |
| :--- | :--- |
| `step` | Số thứ tự bước, từ 1 |
| `active_clue_ids` | Manh mối có trong `KB_t` lúc bắt đầu bước |
| `sat_queries` | Từng truy vấn, ví dụ `"KB_2 ^ ~C_B3: UNSAT"` |
| `sat_calls` | Số truy vấn của bước (luôn chẵn, mỗi ô quét một cặp) |
| `target_coord`, `verdict` | Ô được chọn và phán quyết |
| `newly_revealed_clue_id` | Manh mối vừa lật |

`SolveReport` (định nghĩa trong `agent.py` để không sửa `models.py` của Hào) gồm `status`, `steps` và tổng `sat_calls`, `decisions`, `propagations`, `backtracks`, `runtime_ms`.

### 3.5. Hint (Task 5)
- **Quy trình:**
  1. Tìm ô bị bắt buộc đầu tiên (row-major). Không có, hoặc KB mâu thuẫn, thì trả `HintResponse()` rỗng.
  2. **Rút gọn manh mối:** bắt đầu từ mọi manh mối đã lật; lần lượt (theo thứ tự lật) thử bỏ từng manh mối, nếu phán quyết vẫn bị bắt buộc thì bỏ hẳn.
- **Tính chất:** `relevant_clue_ids` *đủ* để chứng minh phán quyết và *không bỏ thêm được* manh mối nào. Đây là tập tối thiểu theo nghĩa không rút gọn được, chưa chắc là tập ít phần tử nhất.
- Hint chỉ đọc `PublicState`, không đọc lời giải ẩn (Mục 4.4).

---

## 4. Hướng Dẫn Sử Dụng Cho Các Thành Viên

```python
from agent import LogicAgent
from game_engine import GameEngine

agent = LogicAgent()
engine = GameEngine("puzzles/sample_3x3.json", agent=agent)  # engine cần có agent để kiểm tra phán quyết

# Khoa — nút Hint và Auto Solve
hint = agent.hint(engine.get_public_state())      # HintResponse(hint_coord, verdict, relevant_clue_ids)
report = agent.solve_puzzle(engine)                # SolveReport: status, steps (DeductionStep[]), metrics

# Hào — xác thực bộ puzzle
agent.check_uniqueness([cell.clue for cell in puzzle.cells], puzzle.size)  # "UNIQUE" | "MULTIPLE" | "UNSAT"

# Bảo — benchmark có timeout
report = agent.solve_puzzle(engine, time_limit_ms=60_000)
report.sat_calls, report.decisions, report.propagations, report.backtracks, report.runtime_ms, len(report.steps)
```

Kết quả mẫu trên `sample_3x3.json`:
```
Hint: A2 = CRIMINAL, relevant_clue_ids = ['clue_B2']
step=1, active=[clue_A1, clue_B2], sat_calls=6
  KB_1 ^ ~C_B1: SAT, KB_1 ^ C_B1: SAT, KB_1 ^ ~C_C1: SAT, KB_1 ^ C_C1: SAT,
  KB_1 ^ ~C_A2: UNSAT, KB_1 ^ C_A2: SAT   → A2 = CRIMINAL, lật clue_A2
...
SOLVED: 7 bước, 38 lần gọi SAT
```

**Lưu ý cho benchmark:**
- `sat_calls` chỉ đếm truy vấn của agent. Mỗi lần `submit_verdict`, engine tự kiểm tra lại bằng 2 truy vấn nữa, không được đếm.
- `time_limit_ms` không giới hạn bước kiểm tra lại đó của engine.
- Số biến chính/phụ và số mệnh đề không có trong `SolveReport`; lấy bằng `encode_clues` hoặc `encode_public_state` (`num_primary_vars`, `num_aux_vars`, `num_clauses`).

---

## 5. Kiểm Thử (`src/tests/test_agent.py`)

Chạy: `pytest src/tests/test_agent.py` từ thư mục gốc. Toàn bộ `src/tests` pass (512 test, trong đó 184 test của agent).

- **Oracle độc lập:** liệt kê đủ 512 cách gán lưới 3×3, chấm clue bằng `evaluate_clue` của Hào (không đi qua encoder), rồi đối chiếu với agent trên 60 trạng thái ngẫu nhiên (phân loại), 60 tập clue ngẫu nhiên (uniqueness) và 40 trạng thái ngẫu nhiên (hint). Đủ cả 8 loại clue.
- **Ví dụ Mục 3.4 của đề:** B ra CRIMINAL, A ra UNKNOWN.
- **Tích hợp GameEngine:** 2 puzzle mẫu đều `UNIQUE`, giải hết bằng phán quyết bị bắt buộc và khớp lời giải ẩn; engine trả đúng `NOT_PROVABLE` / `CONTRADICTED`.
- **Trace:** phát lại từng bước, kiểm tra ô chọn đúng row-major, khớp Hint, manh mối mở khớp engine; chạy hai lần cho trace giống hệt.
- **Trạng thái dừng:** UNKNOWN (bàn chơi không đổi), INCONSISTENT, TIMEOUT, và engine từ chối phán quyết.
- **Hint:** kiểm tra tập manh mối đủ để chứng minh và bỏ bất kỳ manh mối nào cũng mất chứng minh.
