"""Headless UI smoke test bằng Streamlit AppTest — mô phỏng luồng demo chính."""
from streamlit.testing.v1 import AppTest

at = AppTest.from_file("app.py", default_timeout=60)
at.run()
print("1) initial run exceptions:", list(at.exception))
print("   session train/date:", at.session_state["train"], at.session_state["depart_date"])

# tìm nút Approve và click
approve_buttons = [b for b in at.button if b.key == "approve_btn"]
assert approve_buttons, "khong tim thay nut Approve"
approve_buttons[0].click().run()
print("2) after APPROVE click, exceptions:", list(at.exception))
print("   audit_log:", at.session_state["audit_log"])
print("   last_toast:", at.session_state["last_toast"])

# click Override -> mo dialog
override_buttons = [b for b in at.button if b.key == "override_btn"]
assert override_buttons, "khong tim thay nut Override"
override_buttons[0].click().run()
print("3) after OVERRIDE click, exceptions:", list(at.exception))
print("   show_override_dialog:", at.session_state["show_override_dialog"])

# chon 1 policy card khac
select_buttons = [b for b in at.button if b.key == "select_aggressive"]
if select_buttons:
    select_buttons[0].click().run()
    print("4) after select aggressive policy, exceptions:", list(at.exception))
    print("   selected_policy:", at.session_state["selected_policy"])


# chon ly do trong dialog Override roi xac nhan
selectboxes = [s for s in at.selectbox if s.key == "override_reason"]
assert selectboxes, "khong tim thay selectbox ly do override"
selectboxes[0].select("Nghi ngờ đầu cơ").run()
print("5) after choosing reason, exceptions:", list(at.exception))

confirm_buttons = [b for b in at.button if b.label == "Xác nhận Override"]
assert confirm_buttons, "khong tim thay nut Xac nhan Override"
print("   confirm button disabled?", confirm_buttons[0].disabled)
confirm_buttons[0].click().run()
print("6) after confirm override, exceptions:", list(at.exception))
print("   audit_log:", at.session_state["audit_log"])
print("   show_override_dialog:", at.session_state["show_override_dialog"])

print("\n=== APPTEST DONE ===")
