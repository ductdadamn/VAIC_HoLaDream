"""Headless UI smoke test bằng Streamlit AppTest — mô phỏng luồng demo chính +
test tái hiện bug session_state PO báo (train switch / audit log / dialog leak)."""
from streamlit.testing.v1 import AppTest


def _reason_selectbox(at):
    """key giờ scope theo (train, depart_date, selected_name) nên đổi động —
    tìm theo label ổn định thay vì key cứng."""
    boxes = [s for s in at.selectbox if s.label == "Lý do (bắt buộc chọn)"]
    return boxes[0] if boxes else None


def _alert_button(at, train):
    btns = [b for b in at.button if b.key == f"alert_{train}"]
    return btns[0] if btns else None


# ============================================================ 1) LUỒNG DEMO CHÍNH ============================================================
at = AppTest.from_file("app.py", default_timeout=60)
at.run()
print("1) initial run exceptions:", list(at.exception))
print("   session train/date:", at.session_state["train"], at.session_state["depart_date"])

approve_buttons = [b for b in at.button if b.key == "approve_btn"]
assert approve_buttons, "khong tim thay nut Approve"
approve_buttons[0].click().run()
print("2) after APPROVE click, exceptions:", list(at.exception))
print("   audit_log:", at.session_state["audit_log"])
print("   last_toast:", at.session_state["last_toast"])

override_buttons = [b for b in at.button if b.key == "override_btn"]
assert override_buttons, "khong tim thay nut Override"
override_buttons[0].click().run()
print("3) after OVERRIDE click, exceptions:", list(at.exception))
print("   show_override_dialog:", at.session_state["show_override_dialog"])

select_buttons = [b for b in at.button if b.key == "select_Aggressive"]
if select_buttons:
    select_buttons[0].click().run()
    print("4) after select aggressive policy, exceptions:", list(at.exception))
    print("   selected_policy:", at.session_state["selected_policy"])

reason_box = _reason_selectbox(at)
assert reason_box, "khong tim thay selectbox ly do override"
reason_box.select("Nghi ngờ đầu cơ").run()
print("5) after choosing reason, exceptions:", list(at.exception))

confirm_buttons = [b for b in at.button if b.label == "Xác nhận Override"]
assert confirm_buttons, "khong tim thay nut Xac nhan Override"
print("   confirm button disabled?", confirm_buttons[0].disabled)
confirm_buttons[0].click().run()
print("6) after confirm override, exceptions:", list(at.exception))
print("   audit_log:", at.session_state["audit_log"])
print("   show_override_dialog:", at.session_state["show_override_dialog"])

print("\n=== LUONG DEMO CHINH: DONE ===\n")


# ============================================================ 2) TÁI HIỆN BUG PO BÁO ============================================================
# "Approve SE1 -> log; doi sang SE3 -> tu ghi them 1 log OVERRIDE ma, khong ai bam."
# "Audit log len ~10 roi RESET VE 0 khi chuyen tau."
# "Dialog Override ro trang thai qua lan doi tau."
at2 = AppTest.from_file("app.py", default_timeout=60)
at2.run()
assert not list(at2.exception), f"loi ngay lan chay dau: {list(at2.exception)}"

train_a = at2.session_state["train"]
all_trains = sorted({b.key.replace("alert_", "") for b in at2.button if b.key.startswith("alert_")})
train_b = [t for t in all_trains if t != train_a][0]
print(f"2.0) train_a={train_a} train_b={train_b}")

approve = [b for b in at2.button if b.key == "approve_btn"][0]
approve.click().run()
assert not list(at2.exception), f"loi khi Approve: {list(at2.exception)}"
n_after_approve = len(at2.session_state["audit_log"])
assert n_after_approve == 1, f"ky vong 1 ban ghi sau Approve, duoc {n_after_approve}"
print(f"2.1) sau APPROVE ({train_a}): audit_log = {n_after_approve} ban ghi")

# doi tau qua nut Exception Alert Feed (day la duong PO dung, khong phai qua selectbox)
switch_btn = _alert_button(at2, train_b)
assert switch_btn, f"khong tim thay nut alert_{train_b}"
switch_btn.click().run()
assert not list(at2.exception), f"CRASH khi doi tau qua alert button: {list(at2.exception)}"
assert at2.session_state["train"] == train_b, "doi tau khong thanh cong"
n_after_switch = len(at2.session_state["audit_log"])
assert n_after_switch == n_after_approve, (
    f"PHANTOM LOG: doi tau tu {train_a} sang {train_b} khong ai bam gi them, "
    f"nhung audit_log tu {n_after_approve} thanh {n_after_switch}"
)
print(f"2.2) sau doi tau sang {train_b} (khong bam gi khac): audit_log VAN = {n_after_switch} ban ghi (dung)")

# doi tau qua lai nhieu lan -> audit_log KHONG duoc reset ve 0, khong duoc phinh ra
for i in range(6):
    tgt = train_a if i % 2 == 0 else train_b
    btn = _alert_button(at2, tgt)
    assert btn, f"khong tim thay nut alert_{tgt} o vong {i}"
    btn.click().run()
    assert not list(at2.exception), f"CRASH o lan doi tau thu {i} (-> {tgt}): {list(at2.exception)}"
    n_now = len(at2.session_state["audit_log"])
    assert n_now == n_after_approve, (
        f"RESET/PHANTOM o lan doi tau thu {i} (-> {tgt}): audit_log = {n_now}, ky vong {n_after_approve}"
    )
print(f"2.3) doi tau qua lai 6 lan lien tiep: audit_log ON DINH = {len(at2.session_state['audit_log'])} ban ghi")

# dialog Override phai dong sach khi doi tau, khong ro trang thai sang chuyen moi
override_btn2 = [b for b in at2.button if b.key == "override_btn"][0]
override_btn2.click().run()
assert at2.session_state["show_override_dialog"] is True, "Override khong mo dialog"
reason_box2 = _reason_selectbox(at2)
assert reason_box2 is not None, "khong tim thay selectbox ly do (truoc khi doi tau)"
reason_box2.select("Thiên tai").run()

other_after_dialog = train_a if at2.session_state["train"] == train_b else train_b
btn2 = _alert_button(at2, other_after_dialog)
btn2.click().run()
assert not list(at2.exception), f"CRASH khi doi tau luc dialog dang mo: {list(at2.exception)}"
assert at2.session_state["show_override_dialog"] is False, (
    "RO TRANG THAI: dialog Override van con mo/dang-cho sau khi doi tau — "
    "quyet dinh do dang cua chuyen CU khong duoc dong sach"
)
n_final = len(at2.session_state["audit_log"])
assert n_final == n_after_approve, f"chon ly do roi doi tau (chua xac nhan) khong duoc tu ghi log: {n_final}"
print(f"2.4) mo dialog + chon ly do + doi tau (chua bam Xac nhan): dialog TU DONG (dung), "
      f"audit_log van = {n_final} ban ghi (dung, khong tu ghi)")

print("\n=== TAI HIEN BUG PO: TAT CA ASSERT PASS ===")
