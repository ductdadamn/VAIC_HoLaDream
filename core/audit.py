"""core/audit.py — log_decision(): 1 điểm ghi log duy nhất cho Approve/Override,
để 2 nhánh UI (app.py) không tự lặp code ghi log và không thể phân kỳ ngầm.
"""
from datetime import datetime


def log_decision(train, date, policy_name, action, reason="-") -> dict:
    """→ {timestamp, train, date, policy, action, reason}. action ∈ {APPROVE, OVERRIDE}.
    Cột "policy" (không phải "policy_name") để khớp bảng Audit Log đang chạy trong app.py.
    """
    return {
        "timestamp": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "train": train,
        "date": date,
        "policy": policy_name,
        "action": action,
        "reason": reason,
    }
