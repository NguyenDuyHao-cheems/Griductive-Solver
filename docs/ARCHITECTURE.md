Kiến trúc hệ thống — Griductive Solver

Tài liệu này mô tả kiến trúc tổng thể, ranh giới dữ liệu và luồng tương tác giữa các module trong dự án Griductive-Solver (CSC14003 — Project 2). Toàn bộ mã nguồn đặt trong src/ và dùng chung hợp đồng dữ liệu từ src/models.py.

1. Sơ đồ kiến trúc và tương tác giữa các module

flowchart TB
    subgraph Shared["Lớp dữ liệu dùng chung (src/models.py)"]
        M["Shared Schemas (Puzzle, Clue, PublicState, CNFFormula, SolverResult, VerdictResponse, HintResponse, DeductionStep) & resolve_region()"]
    end

    subgraph Presentation["Tầng giao diện (src/main.py)"]
        GUI["GUI: Lưới N×N, Highlight vùng, Load / Restart / Hint / Auto Solve, Deduction Trace"]
    end

    subgraph Domain["Tầng quản lý trò chơi (src/game_engine.py)"]
        GE["GameEngine\n• Giữ Puzzle & hidden_status\n• Chỉ xuất PublicState\n• Lật thẻ & cập nhật KB_t"]
        DSE["Direct Semantic Evaluator\n• evaluate_clue(clue, assignment)\n• Kiểm chứng chéo không qua CNF"]
    end

    subgraph Reasoning["Tầng suy diễn logic (src/agent.py)"]
        AG["Deductive Logic Agent\n• Entailment (CRIMINAL / INNOCENT / UNKNOWN / INCONSISTENT)\n• No-Guess Deduction Loop & Trace\n• Hint & Uniqueness Check"]
    end

    subgraph LogicCore["Tầng mã hóa & giải SAT"]
        ENC["CNF Encoder & Validator (src/encoder.py)\n• Variable Map tất định (C_i & Aux)\n• Validate Clue/Region\n• Sinh KB_t (CNF) + thống kê"]
        DPLL["DPLL SAT Solver (src/dpll.py)\n• Unit Propagation & Conflict Detection\n• Deterministic Branch / Backtrack\n• Trả về SAT/UNSAT + Metrics"]
    end

    subgraph Benchmark["Tầng thực nghiệm (src/experiments/)"]
        EXP["run_experiments.py & plot_results.py\n• Chạy tập 3×3, 4×4, 5×5\n• Xuất CSV 6 chỉ số & vẽ biểu đồ"]
    end

    GUI -- "1. Verdict / Load / Hint / Auto Solve" --> GE
    GE -- "2. PublicState (chỉ thẻ đã mở)" --> GUI
    GUI -. "Highlight ô qua resolve_region()" .-> M

    GE -- "3. PublicState (KB_t)" --> AG
    AG -- "4. VerdictResponse / HintResponse / DeductionStep[]" --> GE
    GE -- "5. Clue + Complete Assignment" --> DSE

    AG -- "6. PublicState / Clue set" --> ENC
    ENC -- "7. CNFFormula (clauses + var_map)" --> AG
    AG -- "8. CNFFormula + Assumptions (±C_i)" --> DPLL
    DPLL -- "9. SolverResult (SAT/UNSAT + metrics)" --> AG

    EXP -- "Chạy tự động" --> GE
    EXP -- "Thu thập trace & metrics" --> AG

    GE -. "import" .-> M
    AG -. "import" .-> M
    ENC -. "import" .-> M
    DPLL -. "import" .-> M


2. Vai trò và trách nhiệm từng module

Module

Thành viên phụ trách

Trách nhiệm chính

Dữ liệu đầu vào / đầu ra

src/models.py

Hào

Định nghĩa toàn bộ Shared Schemas (dataclass) và hàm resolve_region(region, size) làm nguồn chân lý duy nhất.

Đầu vào: JSON dict / tham số vùng. Đầu ra: Object chuẩn hóa và danh sách tọa độ list[str].

src/game_engine.py

Hào

Nắm giữ Puzzle, hidden_status, manh mối chưa lật; xử lý load, restart, submit_verdict; cài đặt evaluate_clue().

Xuất ra PublicState (ẩn toàn bộ dữ liệu chưa mở); trả về VerdictResponse.

src/encoder.py

Tuân

Tạo var_map tất định (tách biệt biến chính C_i và biến phụ), kiểm tra hợp lệ manh mối/vùng, mã hóa tự động 6 mẫu cốt lõi + 2 mở rộng sang CNF.

Nhận PublicState (hoặc tập Clue); trả về CNFFormula kèm số biến và số mệnh đề.

src/dpll.py

Bảo

Cài đặt thuật toán DPLL bằng Python thuần: unit propagation, phát hiện xung đột, phân nhánh tất định, quay lui và hỗ trợ assumptions tạm thời.

Nhận CNFFormula + assumptions; trả về SolverResult (SAT/UNSAT, assignment, decisions, propagations, backtracks, runtime_ms).

src/agent.py

Tuấn

Phân loại hệ quả logic cho từng ô chưa giải, chạy vòng lặp suy diễn không đoán, ghi DeductionStep, cung cấp HintResponse và check_uniqueness().

Giao tiếp với GameEngine qua PublicState; gọi encoder.py và dpll.py để kiểm tra KB_t ∧ ¬C_i và KB_t ∧ C_i.

src/main.py

Khoa

Hiển thị lưới N×N, thẻ úp/ngửa, gán phán quyết thủ công, tô sáng vùng khi chọn manh mối, điều khiển Load, Restart, Hint, Auto Solve và bảng trace.

Gọi API của GameEngine và LogicAgent; dùng resolve_region() để highlight ô trên lưới.

src/experiments/

Bảo & Khoa

Chạy benchmark tự động trên bộ puzzle 3×3, 4×4, 5×5 (có timeout guard), xuất CSV 6 nhóm chỉ số và vẽ biểu đồ cho báo cáo.

Đọc src/puzzles/*.json; xuất benchmark_results.csv và các hình biểu đồ.

3. Luồng tương tác chính

3.1. Luồng người chơi gán phán quyết thủ công

Người dùng chọn một ô chưa mở trên GUI và gán CRIMINAL hoặc INNOCENT.

GUI gửi yêu cầu tới GameEngine.submit_verdict(coord, verdict).

GameEngine lấy PublicState hiện tại (chỉ gồm manh mối đã lật và phán quyết đã chứng minh) và nhờ LogicAgent kiểm tra entailment cho coord.

LogicAgent gọi Encoder sinh KB_t, sau đó gọi DPLL kiểm tra hai truy vấn KB_t ∧ ¬C_i và KB_t ∧ C_i:

Nếu phán quyết khớp với trạng thái bị bắt buộc (ENTAILED): GameEngine chấp nhận, lật thẻ coord, thêm manh mối mới vào PublicState và trả về VerdictResponse(accepted=True, reason="ENTAILED", revealed_clue=...).

Nếu không trạng thái nào bị bắt buộc: trả về VerdictResponse(accepted=False, reason="NOT_PROVABLE"), giữ nguyên bàn chơi.

Nếu trạng thái ngược lại bị bắt buộc: trả về VerdictResponse(accepted=False, reason="CONTRADICTED"), giữ nguyên bàn chơi.

3.2. Luồng suy diễn tự động (Auto Solve) và Gợi ý (Hint)

Tại bước t, LogicAgent nhận PublicState từ GameEngine.

LogicAgent duyệt các ô chưa giải theo thứ tự tất định (row-major) và phân loại từng ô thành CRIMINAL, INNOCENT, UNKNOWN hoặc INCONSISTENT.

Với Hint: chọn ô đầu tiên bị bắt buộc và trả về HintResponse gồm hint_coord, verdict và relevant_clue_ids để GUI tô sáng.

Với Auto Solve: gửi phán quyết bị bắt buộc đầu tiên tới GameEngine, nhận manh mối mới, ghi lại một DeductionStep (số bước, active clues, các truy vấn SAT, kết quả) và lặp lại cho đến khi giải xong toàn bộ bàn chơi hoặc dừng ở UNKNOWN / INCONSISTENT.

3.3. Luồng kiểm tra tính duy nhất của Puzzle (Uniqueness Check)

LogicAgent.check_uniqueness(puzzle_clues) mã hóa toàn bộ tập manh mối của puzzle thành CNFFormula.

Gọi DPLL lần 1: nếu UNSAT, trả về "UNSAT".

Nếu SAT với nghiệm M, thêm một mệnh đề phủ định phép gán của các biến chính trong M (blocking clause) và gọi DPLL lần 2:

Nếu lần 2 trả về UNSAT: puzzle có nghiệm duy nhất ("UNIQUE").

Nếu lần 2 trả về SAT: puzzle có nhiều nghiệm ("MULTIPLE").

4. Ràng buộc ranh giới dữ liệu (Architectural Boundaries)

Cách ly tri thức ẩn: LogicAgent và GUI tuyệt đối không được đọc trực tiếp file JSON puzzle, hidden_status hay clue của các thẻ đang úp. Mọi giao tiếp dữ liệu đi qua PublicState.

Thuật toán thuần Python: encoder.py và dpll.py không được import thư viện SAT/CSP bên ngoài; thư viện đối chiếu chỉ được phép dùng trong src/tests/.

Đồng bộ tọa độ: Mọi logic ánh xạ tọa độ (A1, C2) và mở rộng vùng (ROW, COL, NEIGHBORS, EXPLICIT) phải gọi chung resolve_region() từ models.py để đảm bảo kết quả khớp nhau giữa Validator, Semantic Evaluator và GUI Highlight.