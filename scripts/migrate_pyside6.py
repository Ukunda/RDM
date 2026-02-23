import re
import os

filepath = r"d:\Hobbies\RDM\random_clip_player.py"
with open(filepath, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Imports
text = text.replace("PyQt5", "PySide6")
text = text.replace("pyqtSignal", "Signal")
text = text.replace("pyqtSlot", "Slot")

# 2. Exec
text = text.replace("app.exec_()", "app.exec()")
text = text.replace("exec_()", "exec()")

# 3. Enums
replacements = {
    # Mouse
    r"Qt\.LeftButton": "Qt.MouseButton.LeftButton",
    r"Qt\.RightButton": "Qt.MouseButton.RightButton",
    r"Qt\.MiddleButton": "Qt.MouseButton.MiddleButton",
    # Keys
    r"Qt\.Key_([A-Za-z0-9_]+)": r"Qt.Key.Key_\1",
    # Modifiers
    r"Qt\.AltModifier": "Qt.KeyboardModifier.AltModifier",
    r"Qt\.ControlModifier": "Qt.KeyboardModifier.ControlModifier",
    r"Qt\.ShiftModifier": "Qt.KeyboardModifier.ShiftModifier",
    # Roles
    r"Qt\.UserRole": "Qt.ItemDataRole.UserRole",
    r"Qt\.DisplayRole": "Qt.ItemDataRole.DisplayRole",
    r"Qt\.ToolTipRole": "Qt.ItemDataRole.ToolTipRole",
    # Colors
    r"Qt\.transparent": "Qt.GlobalColor.transparent",
    r"Qt\.white": "Qt.GlobalColor.white",
    r"Qt\.black": "Qt.GlobalColor.black",
    r"Qt\.red": "Qt.GlobalColor.red",
    r"Qt\.green": "Qt.GlobalColor.green",
    r"Qt\.blue": "Qt.GlobalColor.blue",
    r"Qt\.yellow": "Qt.GlobalColor.yellow",
    # Window types
    r"Qt\.WindowStaysOnTopHint": "Qt.WindowType.WindowStaysOnTopHint",
    r"Qt\.FramelessWindowHint": "Qt.WindowType.FramelessWindowHint",
    r"Qt\.SubWindow": "Qt.WindowType.SubWindow",
    r"Qt\.Tool": "Qt.WindowType.Tool",
    # Alignment
    r"Qt\.Align(Center|Left|Right|Top|Bottom|VCenter|HCenter)": r"Qt.AlignmentFlag.Align\1",
    # Cursors
    r"Qt\.([A-Za-z0-9_]+Cursor)": r"Qt.CursorShape.\1",
    # Match flags
    r"Qt\.Match(Exactly|Contains|StartsWith|EndsWith)": r"Qt.MatchFlag.Match\1",
    # Focus
    r"Qt\.(No|Strong|Tab|Click)Focus": r"Qt.FocusPolicy.\1Focus",
    # Drop actions
    r"Qt\.(Move|Copy|Link)Action": r"Qt.DropAction.\1Action",
    # ScrollBar
    r"Qt\.ScrollBarAlways(On|Off)": r"Qt.ScrollBarPolicy.ScrollBarAlways\1",
    r"Qt\.ScrollBarAsNeeded": r"Qt.ScrollBarPolicy.ScrollBarAsNeeded",
    # Orientation
    r"Qt\.Horizontal": "Qt.Orientation.Horizontal",
    r"Qt\.Vertical": "Qt.Orientation.Vertical"
}

for pattern, repl in replacements.items():
    text = re.sub(pattern, repl, text)

# Just in case we double match some things, fix them back
text = text.replace("Qt.Key.Key.Key_", "Qt.Key.Key_")
text = text.replace("Qt.MouseButton.MouseButton.", "Qt.MouseButton.")

with open(filepath, "w", encoding="utf-8") as f:
    f.write(text)

print("Migration script completed.")
