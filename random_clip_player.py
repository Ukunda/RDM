"""
Random Clip Player - A polished video clip player with random playback
Version 3.0 - Settings & Customization
"""

import sys
import os
import json
import random
import ctypes
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QSlider, QLabel, QFrame, QSizePolicy, QShortcut,
    QFileDialog, QAction, QMessageBox, QDialog, QListWidget, QListWidgetItem,
    QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QMimeData, QPoint, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QKeySequence, QIcon, QDrag, QPixmap, QPainter

# ============================================================================
# VLC Detection and Setup
# ============================================================================

def setup_vlc():
    """Attempt to find VLC and configure paths before importing"""
    if sys.platform != "win32":
        return True
        
    import winreg
    
    def check_vlc_path(path):
        if path and os.path.exists(os.path.join(path, "libvlc.dll")):
            return path
        return None
    
    vlc_path = None
    
    # Try registry locations
    registry_paths = [
        "SOFTWARE\\VideoLAN\\VLC",
        "SOFTWARE\\WOW6432Node\\VideoLAN\\VLC"
    ]
    
    for reg_path in registry_paths:
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path)
            path, _ = winreg.QueryValueEx(key, "InstallDir")
            winreg.CloseKey(key)
            vlc_path = check_vlc_path(path)
            if vlc_path:
                break
        except OSError:
            continue
    
    # Try standard installation paths
    if not vlc_path:
        standard_paths = [
            r"C:\Program Files\VideoLAN\VLC",
            r"C:\Program Files (x86)\VideoLAN\VLC"
        ]
        for path in standard_paths:
            vlc_path = check_vlc_path(path)
            if vlc_path:
                break
    
    if vlc_path:
        os.environ["PATH"] = vlc_path + ";" + os.environ.get("PATH", "")
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(vlc_path)
            except Exception:
                pass
        os.environ["PYTHON_VLC_LIB_PATH"] = os.path.join(vlc_path, "libvlc.dll")
        return True
    
    return False

# Setup VLC before importing
vlc_found = setup_vlc()

if sys.platform == "win32" and not vlc_found:
    ctypes.windll.user32.MessageBoxW(
        0, 
        "VLC Media Player not found.\n\nPlease install VLC from videolan.org", 
        "Random Clip Player - Error", 
        0x10
    )
    sys.exit(1)

import vlc

# ============================================================================
# Constants
# ============================================================================

VIDEO_EXTENSIONS = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', 
    '.webm', '.m4v', '.mpeg', '.mpg', '.3gp', '.ts', '.mts'
}

# Modern Dark Color Palette
COLORS = {
    'bg_dark': '#0d1117',
    'bg_medium': '#161b22',
    'bg_light': '#21262d',
    'accent_green': '#238636',
    'accent_green_hover': '#2ea043',
    'accent_orange': '#d29922',
    'accent_orange_hover': '#e3b341',
    'accent_blue': '#388bfd',
    'accent_blue_hover': '#58a6ff',
    'accent_red': '#f85149',
    'text_primary': '#f0f6fc',
    'text_secondary': '#8b949e',
    'text_muted': '#484f58',
    'border': '#30363d',
}

# ============================================================================
# Configuration Management
# ============================================================================

class ConfigManager:
    """Handles loading and saving of application settings"""
    
    def __init__(self):
        self.config_file = Path("config.json")
        self.default_config = {
            "clips_folder": "",
            "volume": 80,
            "blocked_clips": [],
            "liked_clips": [],
            "autoplay": False,
            "favorites_only": False,
            "auto_hide_controls": False,
            "keybinds": {
                "play_random": "Space",
                "play_pause": "P",
                "toggle_speed": "S",
                "skip_back": "Left",
                "skip_forward": "Right",
                "previous_clip": "Backspace",
                "volume_up": "Up",
                "volume_down": "Down",
                "mute": "M",
                "stop": "Escape",
                "reshuffle": "R",
                "block_clip": "Delete",
                "like_clip": "L",
                "open_explorer": "E",
                "toggle_autoplay": "A",
                "frame_forward": "Period",
                "frame_backward": "Comma"
            }
        }
        self.config = self.load_config()

    def load_config(self):
        """Load config from JSON file or return defaults"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return {**self.default_config, **json.load(f)}
            except Exception:
                return self.default_config.copy()
        return self.default_config.copy()

    def save_config(self):
        """Save current config to JSON file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def get(self, key):
        return self.config.get(key)

    def set(self, key, value):
        self.config[key] = value
        self.save_config()

class BlockedListDialog(QDialog):
    """Dialog to manage blocked clips"""
    
    def __init__(self, blocked_clips, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Blocked Clips")
        self.setMinimumSize(500, 400)
        self.blocked_clips = sorted(list(blocked_clips))
        self.removed_clips = set()
        
        layout = QVBoxLayout(self)
        
        # Info label
        layout.addWidget(QLabel("Select clips to unblock:"))
        
        # List widget
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        
        for clip in self.blocked_clips:
            item = QListWidgetItem(os.path.basename(clip))
            item.setData(Qt.UserRole, clip)
            self.list_widget.addItem(item)
            
        layout.addWidget(self.list_widget)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        unblock_btn = QPushButton("Unblock Selected")
        unblock_btn.clicked.connect(self.unblock_selected)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(unblock_btn)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        
        self.apply_styles()
        
    def unblock_selected(self):
        selected_items = self.list_widget.selectedItems()
        for item in selected_items:
            clip_path = item.data(Qt.UserRole)
            self.removed_clips.add(clip_path)
            self.list_widget.takeItem(self.list_widget.row(item))
            
    def get_removed_clips(self):
        return self.removed_clips

    def apply_styles(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
            }}
            QListWidget {{
                background-color: {COLORS['bg_medium']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_primary']};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['accent_blue']};
                color: {COLORS['text_primary']};
            }}
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_medium']};
                border-color: {COLORS['text_muted']};
            }}
            QLabel {{
                color: {COLORS['text_primary']};
            }}
        """)


class KeybindButton(QPushButton):
    """Button that captures key presses for keybind assignment"""
    
    def __init__(self, key_name, action_id, settings_dialog, parent=None):
        super().__init__(key_name, parent)
        self.key_name = key_name
        self.action_id = action_id
        self.settings_dialog = settings_dialog
        self.capturing = False
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.capturing = True
            self.setText("Press a key...")
            self.setStyleSheet(f"background-color: {COLORS['accent_blue']}; color: white; padding: 4px 8px; border-radius: 4px;")
        super().mousePressEvent(event)
        
    def keyPressEvent(self, event):
        if self.capturing:
            key = event.key()
            # Map Qt key to readable name
            key_map = {
                Qt.Key_Space: "Space", Qt.Key_Return: "Return", Qt.Key_Escape: "Escape",
                Qt.Key_Backspace: "Backspace", Qt.Key_Delete: "Delete", Qt.Key_Tab: "Tab",
                Qt.Key_Left: "Left", Qt.Key_Right: "Right", Qt.Key_Up: "Up", Qt.Key_Down: "Down",
                Qt.Key_Period: "Period", Qt.Key_Comma: "Comma",
                Qt.Key_Home: "Home", Qt.Key_End: "End", Qt.Key_PageUp: "PageUp", Qt.Key_PageDown: "PageDown",
            }
            
            new_key = None
            if key in key_map:
                new_key = key_map[key]
            elif Qt.Key_A <= key <= Qt.Key_Z:
                new_key = chr(key)
            elif Qt.Key_0 <= key <= Qt.Key_9:
                new_key = chr(key)
            elif Qt.Key_F1 <= key <= Qt.Key_F12:
                new_key = f"F{key - Qt.Key_F1 + 1}"
            else:
                new_key = QKeySequence(key).toString()
            
            if new_key:
                # Check for conflicts and swap if needed
                old_key = self.key_name
                self.settings_dialog.handle_keybind_change(self.action_id, new_key, old_key)
                
            self.capturing = False
            self.setStyleSheet(f"background-color: {COLORS['bg_light']}; color: {COLORS['text_primary']}; padding: 4px 8px; border-radius: 4px; border: 1px solid {COLORS['border']};")
        else:
            super().keyPressEvent(event)
            
    def focusOutEvent(self, event):
        if self.capturing:
            self.capturing = False
            self.setText(self.key_name)
            self.setStyleSheet(f"background-color: {COLORS['bg_light']}; color: {COLORS['text_primary']}; padding: 4px 8px; border-radius: 4px; border: 1px solid {COLORS['border']};")
        super().focusOutEvent(event)


class SettingsDialog(QDialog):
    """Settings dialog with keybind configuration"""
    
    KEYBIND_LABELS = {
        "play_random": "Play Random Clip",
        "play_pause": "Play / Pause",
        "toggle_speed": "Toggle Speed",
        "skip_back": "Skip Back 10s",
        "skip_forward": "Skip Forward 10s",
        "previous_clip": "Previous Clip",
        "volume_up": "Volume Up",
        "volume_down": "Volume Down",
        "mute": "Mute",
        "stop": "Stop",
        "reshuffle": "Reshuffle Queue",
        "block_clip": "Block Clip",
        "like_clip": "Like Clip",
        "open_explorer": "Open in Explorer",
        "toggle_autoplay": "Toggle Autoplay",
        "frame_forward": "Frame Forward",
        "frame_backward": "Frame Backward",
    }
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 550)
        self.keybind_buttons = {}
        
        self._setup_ui()
        self._apply_styles()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # Auto-hide controls toggle
        controls_group = QFrame()
        controls_group.setStyleSheet(f"background-color: {COLORS['bg_medium']}; border-radius: 6px; padding: 8px;")
        controls_layout = QVBoxLayout(controls_group)
        
        self.auto_hide_cb = QPushButton("Auto-hide Controls Bar")
        self.auto_hide_cb.setCheckable(True)
        self.auto_hide_cb.setChecked(self.config_manager.get("auto_hide_controls") or False)
        self.auto_hide_cb.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px;
                text-align: left;
            }}
            QPushButton:checked {{
                background-color: {COLORS['accent_blue']};
                border-color: {COLORS['accent_blue']};
            }}
        """)
        controls_layout.addWidget(self.auto_hide_cb)
        
        auto_hide_info = QLabel("Hide the button bar when mouse leaves the window")
        auto_hide_info.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        controls_layout.addWidget(auto_hide_info)
        
        layout.addWidget(controls_group)
        
        # Keybinds section
        keybind_label = QLabel("Keyboard Shortcuts")
        keybind_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px; font-weight: bold;")
        layout.addWidget(keybind_label)
        
        keybind_info = QLabel("Click a key button to change the shortcut")
        keybind_info.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        layout.addWidget(keybind_info)
        
        # Scrollable keybind list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea {{ border: none; background-color: transparent; }}")
        
        keybind_widget = QWidget()
        keybind_layout = QVBoxLayout(keybind_widget)
        keybind_layout.setSpacing(4)
        
        current_keybinds = self.config_manager.get("keybinds") or {}
        
        for action_id, label in self.KEYBIND_LABELS.items():
            row = QHBoxLayout()
            
            action_label = QLabel(label)
            action_label.setStyleSheet(f"color: {COLORS['text_secondary']}; min-width: 150px;")
            action_label.setFixedWidth(180)
            
            current_key = current_keybinds.get(action_id, "")
            key_btn = KeybindButton(current_key, action_id, self)
            key_btn.setFixedWidth(100)
            key_btn.setStyleSheet(f"background-color: {COLORS['bg_light']}; color: {COLORS['text_primary']}; padding: 4px 8px; border-radius: 4px; border: 1px solid {COLORS['border']};")
            self.keybind_buttons[action_id] = key_btn
            
            row.addWidget(action_label)
            row.addWidget(key_btn)
            row.addStretch()
            
            keybind_layout.addLayout(row)
            
        keybind_layout.addStretch()
        scroll.setWidget(keybind_widget)
        layout.addWidget(scroll, stretch=1)
        
        # Reset to defaults button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        layout.addWidget(reset_btn)
        
        # Dialog buttons
        btn_layout = QHBoxLayout()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_and_close)
        save_btn.setStyleSheet(f"background-color: {COLORS['accent_green']}; color: white; font-weight: bold;")
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def handle_keybind_change(self, action_id, new_key, old_key):
        """Handle keybind change with conflict resolution (swap keys)"""
        # Find if new_key is already used by another action
        conflicting_action = None
        for other_action_id, btn in self.keybind_buttons.items():
            if other_action_id != action_id and btn.key_name == new_key:
                conflicting_action = other_action_id
                break
        
        # Update this action's button
        self.keybind_buttons[action_id].key_name = new_key
        self.keybind_buttons[action_id].setText(new_key)
        
        # If there was a conflict, swap: give the conflicting action our old key
        if conflicting_action:
            self.keybind_buttons[conflicting_action].key_name = old_key
            self.keybind_buttons[conflicting_action].setText(old_key)
            # Brief visual feedback for swap
            self.keybind_buttons[conflicting_action].setStyleSheet(
                f"background-color: {COLORS['accent_orange']}; color: {COLORS['bg_dark']}; padding: 4px 8px; border-radius: 4px;"
            )
            # Reset style after delay
            QTimer.singleShot(500, lambda: self.keybind_buttons[conflicting_action].setStyleSheet(
                f"background-color: {COLORS['bg_light']}; color: {COLORS['text_primary']}; padding: 4px 8px; border-radius: 4px; border: 1px solid {COLORS['border']};"
            ) if conflicting_action in self.keybind_buttons else None)
        
    def _reset_defaults(self):
        """Reset keybinds to defaults"""
        defaults = {
            "play_random": "Space", "play_pause": "P", "toggle_speed": "S",
            "skip_back": "Left", "skip_forward": "Right", "previous_clip": "Backspace",
            "volume_up": "Up", "volume_down": "Down", "mute": "M",
            "stop": "Escape", "reshuffle": "R", "block_clip": "Delete",
            "like_clip": "L", "open_explorer": "E", "toggle_autoplay": "A",
            "frame_forward": "Period", "frame_backward": "Comma"
        }
        for action_id, key in defaults.items():
            if action_id in self.keybind_buttons:
                self.keybind_buttons[action_id].key_name = key
                self.keybind_buttons[action_id].setText(key)
                
    def _save_and_close(self):
        """Save settings and close dialog"""
        # Save auto-hide setting
        self.config_manager.set("auto_hide_controls", self.auto_hide_cb.isChecked())
        
        # Save keybinds
        keybinds = {action_id: btn.key_name for action_id, btn in self.keybind_buttons.items()}
        self.config_manager.set("keybinds", keybinds)
        
        self.accept()
        
    def _apply_styles(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
            }}
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['bg_medium']};
                border-color: {COLORS['text_muted']};
            }}
            QLabel {{
                color: {COLORS['text_primary']};
            }}
        """)


# ============================================================================
# Custom Widgets
# ============================================================================

class ClickableSlider(QSlider):
    """Custom slider that responds to clicks anywhere on the track"""
    __slots__ = ()  # Memory optimization
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


class DraggableWidget(QWidget):
    """A widget container that can be dragged to reorder (only when Alt is held)"""
    
    def __init__(self, widget, widget_id, parent=None):
        super().__init__(parent)
        self.widget_id = widget_id
        self.inner_widget = widget
        self._drag_start = None
        self._original_enabled = True
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)
        
        self.setAcceptDrops(True)
        
        # Install event filter on the inner widget to intercept Alt+drag
        widget.installEventFilter(self)
        
    def eventFilter(self, obj, event):
        """Intercept mouse events on the button when Alt is held"""
        if obj == self.inner_widget:
            if event.type() == event.MouseButtonPress and event.button() == Qt.LeftButton:
                if event.modifiers() & Qt.AltModifier:
                    self._drag_start = event.pos()
                    return True  # Consume the event
            elif event.type() == event.MouseMove and self._drag_start:
                if event.modifiers() & Qt.AltModifier:
                    if (event.pos() - self._drag_start).manhattanLength() > 10:
                        self._start_drag(event.pos())
                    return True
            elif event.type() == event.MouseButtonRelease:
                self._drag_start = None
        return super().eventFilter(obj, event)
    
    def _start_drag(self, pos):
        """Initiate the drag operation"""
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self.widget_id)
        drag.setMimeData(mime)
        
        # Create pixmap of widget for visual drag
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        self.render(painter)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(pos)
        
        # Visual feedback - highlight draggable items
        parent = self.parent()
        if parent and hasattr(parent, 'set_rearrange_mode'):
            parent.set_rearrange_mode(True)
        
        drag.exec_(Qt.MoveAction)
        
        if parent and hasattr(parent, 'set_rearrange_mode'):
            parent.set_rearrange_mode(False)
            
        self._drag_start = None
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and (event.keyboardModifiers() & Qt.AltModifier):
            event.acceptProposedAction()
            # Highlight drop target
            self.setStyleSheet(f"background-color: {COLORS['accent_blue']}; border-radius: 4px;")
        else:
            event.ignore()
            
    def dragLeaveEvent(self, event):
        self.setStyleSheet("")
        super().dragLeaveEvent(event)
            
    def dropEvent(self, event):
        self.setStyleSheet("")
        source_id = event.mimeData().text()
        if source_id != self.widget_id:
            # Find parent layout and swap positions
            parent = self.parent()
            if parent and hasattr(parent, 'swap_widgets'):
                parent.swap_widgets(source_id, self.widget_id)
        event.acceptProposedAction()


class DraggableButtonBar(QWidget):
    """A container for draggable buttons with persistence"""
    
    BUTTON_SPACING = 4  # Consistent spacing between buttons
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.widget_map = {}  # widget_id -> DraggableWidget
        self.layout = QHBoxLayout(self)
        self.layout.setSpacing(self.BUTTON_SPACING)
        self.layout.setContentsMargins(0, 4, 0, 0)
        self.setAcceptDrops(True)
        self._rearrange_mode = False
        
    def set_rearrange_mode(self, enabled):
        """Enable/disable rearrange mode with visual feedback"""
        self._rearrange_mode = enabled
        for widget_id, draggable in self.widget_map.items():
            if enabled:
                # Show rearrange mode - add border, disable buttons
                draggable.setStyleSheet(f"border: 2px dashed {COLORS['accent_orange']}; border-radius: 6px; padding: 2px;")
                draggable.inner_widget.setEnabled(False)
            else:
                # Exit rearrange mode - restore normal state
                draggable.setStyleSheet("")
                draggable.inner_widget.setEnabled(True)
        
    def add_widget(self, widget, widget_id, stretch=0):
        """Add a widget with an ID for persistence"""
        draggable = DraggableWidget(widget, widget_id, self)
        self.widget_map[widget_id] = draggable
        self.layout.addWidget(draggable, stretch)
        
    def add_spacing(self, size):
        """Add spacing to layout"""
        self.layout.addSpacing(size)
        
    def add_fixed_widget(self, widget, stretch=0):
        """Add a non-draggable widget"""
        self.layout.addWidget(widget, stretch)
        
    def swap_widgets(self, source_id, target_id):
        """Swap two widgets in the layout"""
        if source_id not in self.widget_map or target_id not in self.widget_map:
            return
            
        source = self.widget_map[source_id]
        target = self.widget_map[target_id]
        
        source_idx = self.layout.indexOf(source)
        target_idx = self.layout.indexOf(target)
        
        if source_idx >= 0 and target_idx >= 0:
            # Remove both
            self.layout.removeWidget(source)
            self.layout.removeWidget(target)
            
            # Re-insert in swapped positions
            if source_idx < target_idx:
                self.layout.insertWidget(source_idx, target)
                self.layout.insertWidget(target_idx, source)
            else:
                self.layout.insertWidget(target_idx, source)
                self.layout.insertWidget(source_idx, target)
                
            # Save order
            self._save_order()
            
    def _save_order(self):
        """Save current widget order to config"""
        order = []
        for i in range(self.layout.count()):
            item = self.layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), DraggableWidget):
                order.append(item.widget().widget_id)
        self.config_manager.set("button_order", order)
        
    def restore_order(self, order):
        """Restore widget order from saved config"""
        if not order:
            return
            
        # Get current positions
        widgets_by_id = {}
        for widget_id, draggable in self.widget_map.items():
            idx = self.layout.indexOf(draggable)
            if idx >= 0:
                widgets_by_id[widget_id] = (draggable, idx)
        
        # Temporarily remove all draggable widgets
        for widget_id, (draggable, _) in widgets_by_id.items():
            self.layout.removeWidget(draggable)
            
        # Re-add in order, then remaining ones
        added = set()
        insert_pos = 0
        for widget_id in order:
            if widget_id in widgets_by_id:
                draggable, _ = widgets_by_id[widget_id]
                self.layout.insertWidget(insert_pos, draggable)
                added.add(widget_id)
                insert_pos += 1
                
        # Add any that weren't in the saved order
        for widget_id, (draggable, _) in widgets_by_id.items():
            if widget_id not in added:
                self.layout.insertWidget(insert_pos, draggable)
                insert_pos += 1


class SpeedButton(QPushButton):
    """Custom button that changes playback speed on scroll"""
    
    SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    
    speed_changed = None  # Will be connected in VideoPlayer
    
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.current_speed = 1.0
        self.setMinimumHeight(36)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()
        
    def _apply_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                font-size: 12px;
                font-weight: 500;
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 10px 14px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['border']};
                border-color: {COLORS['text_muted']};
            }}
            QPushButton:pressed {{ background-color: {COLORS['bg_medium']}; }}
            QPushButton:checked {{
                background-color: {COLORS['accent_blue']};
                border-color: {COLORS['accent_blue']};
            }}
            QPushButton:checked:hover {{ background-color: {COLORS['accent_blue_hover']}; }}
        """)
        
    def wheelEvent(self, event):
        """Handle mouse wheel to change speed"""
        try:
            idx = self.SPEEDS.index(self.current_speed)
        except ValueError:
            idx = 3  # Default to 1.0x
            
        if event.angleDelta().y() > 0:
            # Scroll up = faster
            idx = min(idx + 1, len(self.SPEEDS) - 1)
        else:
            # Scroll down = slower
            idx = max(idx - 1, 0)
            
        self.current_speed = self.SPEEDS[idx]
        self._update_text()
        
        # Emit signal if connected
        if self.speed_changed:
            self.speed_changed(self.current_speed)
            
    def _update_text(self):
        if self.current_speed == 1.0:
            self.setText("1.0x")
            self.setChecked(False)
        else:
            self.setText(f"{self.current_speed}x")
            self.setChecked(True)
            
    def set_speed(self, speed):
        """Externally set speed"""
        if speed in self.SPEEDS:
            self.current_speed = speed
            self._update_text()


class StyledButton(QPushButton):
    """Custom styled button with hover effects"""
    
    def __init__(self, text, color='default', parent=None):
        super().__init__(text, parent)
        self.color_scheme = color
        self.setMinimumHeight(44)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()
        
    def _apply_style(self):
        styles = {
            'primary': f"""
                QPushButton {{
                    background-color: {COLORS['accent_green']};
                    color: {COLORS['text_primary']};
                    font-size: 14px;
                    font-weight: 600;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 20px;
                }}
                QPushButton:hover {{ background-color: {COLORS['accent_green_hover']}; }}
                QPushButton:pressed {{ background-color: #196c2e; }}
                QPushButton:disabled {{
                    background-color: {COLORS['bg_light']};
                    color: {COLORS['text_muted']};
                }}
            """,
            'secondary': f"""
                QPushButton {{
                    background-color: {COLORS['accent_orange']};
                    color: {COLORS['bg_dark']};
                    font-size: 12px;
                    font-weight: 600;
                    border: none;
                    border-radius: 8px;
                    padding: 10px 14px;
                }}
                QPushButton:hover {{ background-color: {COLORS['accent_orange_hover']}; }}
                QPushButton:pressed {{ background-color: #b87d14; }}
                QPushButton:disabled {{
                    background-color: {COLORS['bg_light']};
                    color: {COLORS['text_muted']};
                }}
            """,
            'toggle': f"""
                QPushButton {{
                    background-color: {COLORS['bg_light']};
                    color: {COLORS['text_primary']};
                    font-size: 12px;
                    font-weight: 500;
                    border: 1px solid {COLORS['border']};
                    border-radius: 8px;
                    padding: 10px 14px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['border']};
                    border-color: {COLORS['text_muted']};
                }}
                QPushButton:pressed {{ background-color: {COLORS['bg_medium']}; }}
                QPushButton:checked {{
                    background-color: {COLORS['accent_blue']};
                    border-color: {COLORS['accent_blue']};
                }}
                QPushButton:checked:hover {{ background-color: {COLORS['accent_blue_hover']}; }}
            """,
            'default': f"""
                QPushButton {{
                    background-color: {COLORS['bg_light']};
                    color: {COLORS['text_primary']};
                    font-size: 12px;
                    font-weight: 500;
                    border: 1px solid {COLORS['border']};
                    border-radius: 8px;
                    padding: 10px 14px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['border']};
                    border-color: {COLORS['text_muted']};
                }}
                QPushButton:pressed {{ background-color: {COLORS['bg_medium']}; }}
                QPushButton:disabled {{
                    background-color: {COLORS['bg_medium']};
                    color: {COLORS['text_muted']};
                    border-color: {COLORS['bg_light']};
                }}
            """
        }
        self.setStyleSheet(styles.get(self.color_scheme, styles['default']))


# ============================================================================
# Main Application
# ============================================================================

class VideoPlayer(QMainWindow):
    """Main video player window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Random Clip Player v3.0")
        self.setGeometry(100, 100, 1100, 700)
        self.setMinimumSize(800, 550)
        
        # Initialize Configuration
        self.config_manager = ConfigManager()
        
        # VLC instance and player
        self.instance = vlc.Instance('--no-xlib')
        self.player = self.instance.media_player_new()
        
        # Folder path from config
        self.clips_folder = self.config_manager.get("clips_folder")
        self.blocked_clips = set(self.config_manager.get("blocked_clips") or [])
        self.liked_clips = set(self.config_manager.get("liked_clips") or [])
        self.video_files = []
        self.current_video = ""
        
        # History tracking
        self.autoplay_enabled = self.config_manager.get("autoplay")
        self.favorites_only = self.config_manager.get("favorites_only") or False
        self.auto_hide_controls = self.config_manager.get("auto_hide_controls") or False
        self.play_queue = []  # Shuffled list of clips
        self.queue_index = -1  # Current position in shuffled list
        
        # UI state
        self.is_slider_pressed = False
        self._last_volume = self.config_manager.get("volume")
        self._cached_fps = 0  # Cache FPS to avoid repeated VLC calls
        
        # Setup UI
        self._setup_ui()
        self._create_menu_bar()
        self._apply_global_styles()
        self._setup_keyboard_shortcuts()
        
        # Initial folder check
        if not self.clips_folder or not os.path.exists(self.clips_folder):
            self.video_label.setText("⚠  Please select a clips folder to begin")
            QTimer.singleShot(500, self.select_folder) # Delay slightly to let UI render
        else:
            self.scan_folder()
            self._update_status_bar()
        
        # Timer for updating slider and time (smoother at 20fps)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._update_playback_ui)
        
        # Auto-hide timer for controls
        self.hide_controls_timer = QTimer(self)
        self.hide_controls_timer.setInterval(2000)  # 2 seconds
        self.hide_controls_timer.setSingleShot(True)
        self.hide_controls_timer.timeout.connect(self._hide_controls)
        
        # Enable mouse tracking for auto-hide
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)

    def _create_menu_bar(self):
        """Create the application menu bar"""
        navbar = self.menuBar()
        navbar.setStyleSheet(f"""
            QMenuBar {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_primary']};
                border-bottom: 1px solid {COLORS['border']};
            }}
            QMenuBar::item {{
                padding: 8px 12px;
                background-color: transparent;
            }}
            QMenuBar::item:selected {{
                background-color: {COLORS['accent_blue']};
            }}
            QMenu {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
            }}
            QMenu::item {{
                padding: 6px 24px;
            }}
            QMenu::item:selected {{
                background-color: {COLORS['accent_blue']};
            }}
        """)
        
        # File Menu
        file_menu = navbar.addMenu("File")
        
        open_action = QAction("Open Folder...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.select_folder)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()

        open_explorer_action = QAction("Open in Explorer", self)
        open_explorer_action.setShortcut("Ctrl+E")
        open_explorer_action.triggered.connect(self.open_current_in_explorer)
        file_menu.addAction(open_explorer_action)

        manage_blocked_action = QAction("Manage Blocked Clips...", self)
        manage_blocked_action.triggered.connect(self.show_blocked_dialog)
        file_menu.addAction(manage_blocked_action)
        
        file_menu.addSeparator()
        
        self.favorites_action = QAction("Show Only Favorites", self)
        self.favorites_action.setCheckable(True)
        self.favorites_action.setChecked(self.favorites_only)
        self.favorites_action.triggered.connect(self.toggle_favorites_only)
        file_menu.addAction(self.favorites_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Settings Menu
        settings_menu = navbar.addMenu("Settings")
        
        settings_action = QAction("Preferences...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings_dialog)
        settings_menu.addAction(settings_action)

    def show_settings_dialog(self):
        """Show the settings dialog"""
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec_():
            # Reload keybinds after saving
            self._setup_keyboard_shortcuts()
            # Update auto-hide state
            old_auto_hide = self.auto_hide_controls
            self.auto_hide_controls = self.config_manager.get("auto_hide_controls") or False
            
            if self.auto_hide_controls:
                self.status_label.setText("Auto-hide enabled")
            else:
                # If auto-hide was just disabled, make sure controls are visible!
                self._show_controls()
                if old_auto_hide:
                    self.status_label.setText("Auto-hide disabled")
            QTimer.singleShot(1500, self._update_status_bar)

    def select_folder(self):
        """Open dialog to select clips folder"""
        folder = QFileDialog.getExistingDirectory(self, "Select Clips Folder")
        if folder:
            self.clips_folder = folder
            self.config_manager.set("clips_folder", folder)
            self.scan_folder()
            self._update_status_bar()

    def show_blocked_dialog(self):
        """Show dialog to manage blocked clips"""
        dialog = BlockedListDialog(self.blocked_clips, self)
        if dialog.exec_():
            removed = dialog.get_removed_clips()
            if removed:
                self.blocked_clips -= removed
                self.config_manager.set("blocked_clips", list(self.blocked_clips))
                self.video_label.setText(f"✅ Unblocked {len(removed)} clips")
                QTimer.singleShot(2000, lambda: self._update_status_bar() if not self.current_video else None)

    def _setup_ui(self):
        """Initialize all UI components"""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)
        
        # Video container
        video_container = QFrame()
        video_container.setStyleSheet(f"""
            QFrame {{
                background-color: #000000;
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
            }}
        """)
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(1, 1, 1, 1)
        
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: #000000; border-radius: 4px;")
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout.addWidget(self.video_frame)
        
        main_layout.addWidget(video_container, stretch=1)
        
        # Info bar (filename left, status right)
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(2, 2, 2, 2)
        info_layout.setSpacing(8)
        
        self.video_label = QLabel("Ready — Press Space to start")
        self.video_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px;")
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        self.status_label.setAlignment(Qt.AlignRight)
        
        info_layout.addWidget(self.video_label, stretch=1)
        info_layout.addWidget(self.status_label)
        main_layout.addLayout(info_layout)
        
        # Progress bar section
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(8)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        self.time_label = QLabel("0:00")
        self.time_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 11px; font-family: 'Consolas', monospace;")
        self.time_label.setFixedWidth(40)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.time_slider = ClickableSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.sliderMoved.connect(self._set_position)
        self.time_slider.sliderPressed.connect(self._slider_pressed)
        self.time_slider.sliderReleased.connect(self._slider_released)
        
        self.duration_label = QLabel("0:00")
        self.duration_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px; font-family: 'Consolas', monospace;")
        self.duration_label.setFixedWidth(40)
        
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.time_slider, stretch=1)
        progress_layout.addWidget(self.duration_label)
        main_layout.addLayout(progress_layout)
        
        # ==========================================
        # Main Controls Row (in container for auto-hide)
        # ==========================================
        self.controls_container = QWidget()
        container_layout = QHBoxLayout(self.controls_container)
        container_layout.setSpacing(0)
        container_layout.setContentsMargins(0, 4, 0, 0)
        
        # Draggable button bar
        self.button_bar = DraggableButtonBar(self.config_manager, self)
        
        # Previous clip
        self.prev_clip_btn = StyledButton("⏮ Prev", 'secondary')
        self.prev_clip_btn.setMinimumSize(75, 36)
        self.prev_clip_btn.clicked.connect(self.play_previous_clip)
        self.prev_clip_btn.setEnabled(False)
        self.prev_clip_btn.setToolTip("Previous (Backspace)")
        self.button_bar.add_widget(self.prev_clip_btn, "prev", stretch=1)
        
        # Skip back
        self.skip_back_btn = StyledButton("−10s")
        self.skip_back_btn.setMinimumSize(50, 36)
        self.skip_back_btn.clicked.connect(lambda: self._skip(-10000))
        self.skip_back_btn.setToolTip("Skip back (←)")
        self.button_bar.add_widget(self.skip_back_btn, "skip_back", stretch=1)
        
        # Play/Pause
        self.play_btn = StyledButton("▶ Play")
        self.play_btn.setMinimumSize(80, 36)
        self.play_btn.clicked.connect(self._toggle_play_pause)
        self.play_btn.setToolTip("Play/Pause (P)")
        self.button_bar.add_widget(self.play_btn, "play", stretch=1)
        
        # Skip forward
        self.skip_fwd_btn = StyledButton("+10s")
        self.skip_fwd_btn.setMinimumSize(50, 36)
        self.skip_fwd_btn.clicked.connect(lambda: self._skip(10000))
        self.skip_fwd_btn.setToolTip("Skip forward (→)")
        self.button_bar.add_widget(self.skip_fwd_btn, "skip_fwd", stretch=1)
        
        self.button_bar.add_spacing(8)
        
        # ★ RANDOM CLIP - PRIMARY ACTION ★
        self.random_btn = StyledButton("🎲 Random Clip", 'primary')
        self.random_btn.setMinimumSize(130, 40)
        self.random_btn.clicked.connect(self.play_random_clip)
        self.random_btn.setToolTip("Next random clip (Space)")
        self.button_bar.add_widget(self.random_btn, "random", stretch=3)
        
        self.button_bar.add_spacing(8)
        
        # Like/Dislike
        self.like_btn = StyledButton("👍")
        self.like_btn.setMinimumSize(40, 36)
        self.like_btn.clicked.connect(self.toggle_like)
        self.like_btn.setToolTip("Like (L)")
        self.like_btn.setEnabled(False)
        self.button_bar.add_widget(self.like_btn, "like", stretch=1)
        
        self.block_btn = StyledButton("👎")
        self.block_btn.setMinimumSize(40, 36)
        self.block_btn.clicked.connect(self.block_current_clip)
        self.block_btn.setToolTip("Dislike & Block (Del)")
        self.block_btn.setEnabled(False)
        self.button_bar.add_widget(self.block_btn, "block", stretch=1)
        
        self.button_bar.add_spacing(8)
        
        # Settings toggles
        self.autoplay_btn = StyledButton("Auto", 'toggle')
        self.autoplay_btn.setMinimumSize(50, 36)
        self.autoplay_btn.setCheckable(True)
        self.autoplay_btn.setChecked(self.autoplay_enabled)
        self.autoplay_btn.clicked.connect(self.toggle_autoplay)
        self.autoplay_btn.setToolTip("Autoplay (A)")
        self.button_bar.add_widget(self.autoplay_btn, "autoplay", stretch=1)
        
        self.slow_mo_btn = SpeedButton("1.0x")
        self.slow_mo_btn.setMinimumSize(50, 36)
        self.slow_mo_btn.setCheckable(True)
        self.slow_mo_btn.clicked.connect(self._toggle_slow_motion)
        self.slow_mo_btn.speed_changed = self._set_playback_speed
        self.slow_mo_btn.setToolTip("Speed (S) — Scroll to change")
        self.button_bar.add_widget(self.slow_mo_btn, "speed", stretch=1)
        
        # Restore saved button order
        saved_order = self.config_manager.get("button_order")
        if saved_order:
            self.button_bar.restore_order(saved_order)
        
        container_layout.addWidget(self.button_bar, stretch=1)
        
        container_layout.addSpacing(8)
        
        # Fixed widgets (not draggable) - Volume section
        volume_widget = QWidget()
        volume_layout = QHBoxLayout(volume_widget)
        volume_layout.setContentsMargins(0, 0, 0, 0)
        volume_layout.setSpacing(4)
        
        self.volume_icon = QLabel("🔊")
        self.volume_icon.setFixedWidth(16)
        volume_layout.addWidget(self.volume_icon)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self._last_volume)
        self.volume_slider.setMinimumWidth(50)
        self.volume_slider.setMaximumWidth(80)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.volume_slider.setToolTip("Volume (↑/↓)")
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel(f"{self._last_volume}%")
        self.volume_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        self.volume_label.setFixedWidth(30)
        volume_layout.addWidget(self.volume_label)
        
        # Clip Counter
        self.clip_counter = QLabel("0 / 0")
        self.clip_counter.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 11px; font-weight: bold;")
        self.clip_counter.setMinimumWidth(70)
        self.clip_counter.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.clip_counter.setToolTip("Position / Total clips")
        volume_layout.addWidget(self.clip_counter)
        
        container_layout.addWidget(volume_widget)
        
        main_layout.addWidget(self.controls_container)
        
        # Set initial volume
        self.player.audio_set_volume(self._last_volume)

    def _apply_global_styles(self):
        """Apply global application styles"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['bg_dark']};
            }}
            QWidget {{
                background-color: transparent;
                color: {COLORS['text_primary']};
                font-family: 'Segoe UI', sans-serif;
            }}
            QMainWindow > QWidget {{
                background-color: {COLORS['bg_dark']};
            }}
            QToolTip {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {COLORS['bg_light']};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['text_primary']};
                border: none;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {COLORS['accent_green']};
            }}
            QSlider::sub-page:horizontal {{
                background: {COLORS['accent_green']};
                border-radius: 3px;
            }}
        """)

    def _setup_keyboard_shortcuts(self):
        """Configure keyboard shortcuts from config"""
        # Clear existing shortcuts
        if hasattr(self, '_shortcuts'):
            for shortcut in self._shortcuts:
                shortcut.setEnabled(False)
                shortcut.deleteLater()
        self._shortcuts = []
        
        # Key name to Qt key mapping
        key_map = {
            "Space": Qt.Key_Space, "Return": Qt.Key_Return, "Escape": Qt.Key_Escape,
            "Backspace": Qt.Key_Backspace, "Delete": Qt.Key_Delete, "Tab": Qt.Key_Tab,
            "Left": Qt.Key_Left, "Right": Qt.Key_Right, "Up": Qt.Key_Up, "Down": Qt.Key_Down,
            "Period": Qt.Key_Period, "Comma": Qt.Key_Comma,
            "Home": Qt.Key_Home, "End": Qt.Key_End, "PageUp": Qt.Key_PageUp, "PageDown": Qt.Key_PageDown,
        }
        # Add letter keys A-Z
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            key_map[c] = getattr(Qt, f"Key_{c}")
        # Add number keys 0-9
        for n in "0123456789":
            key_map[n] = getattr(Qt, f"Key_{n}")
        # Add function keys F1-F12
        for i in range(1, 13):
            key_map[f"F{i}"] = getattr(Qt, f"Key_F{i}")
        
        # Action name to callback mapping
        action_map = {
            "play_random": self.play_random_clip,
            "play_pause": self._toggle_play_pause,
            "toggle_speed": self._toggle_slow_motion_keyboard,
            "skip_back": lambda: self._skip(-10000),
            "skip_forward": lambda: self._skip(10000),
            "previous_clip": self.play_previous_clip,
            "volume_up": lambda: self.volume_slider.setValue(min(100, self.volume_slider.value() + 5)),
            "volume_down": lambda: self.volume_slider.setValue(max(0, self.volume_slider.value() - 5)),
            "mute": self._toggle_mute,
            "stop": self._stop,
            "reshuffle": self._reset_cycle,
            "block_clip": self.block_current_clip,
            "like_clip": self.toggle_like,
            "open_explorer": self.open_current_in_explorer,
            "toggle_autoplay": self.toggle_autoplay,
            "frame_forward": self._frame_step_forward,
            "frame_backward": self._frame_step_backward,
        }
        
        # Get keybinds from config
        keybinds = self.config_manager.get("keybinds") or {}
        
        for action_name, callback in action_map.items():
            key_name = keybinds.get(action_name, "")
            if key_name and key_name in key_map:
                shortcut = QShortcut(QKeySequence(key_map[key_name]), self)
                shortcut.activated.connect(callback)
                self._shortcuts.append(shortcut)

    # ========================================================================
    # Folder and Clip Management
    # ========================================================================

    def scan_folder(self):
        """Scan the clips folder for video files"""
        self.video_files = []
        
        if not self.clips_folder or not os.path.exists(self.clips_folder):
            self.video_label.setText(f"⚠  Folder not found: {self.clips_folder}")
            self.video_label.setStyleSheet(f"color: {COLORS['accent_red']}; font-size: 13px; padding: 6px 4px;")
            return
            
        for file in Path(self.clips_folder).rglob("*"):
            if file.suffix.lower() in VIDEO_EXTENSIONS:
                self.video_files.append(str(file))
        
        # Prepare shuffled queue
        self._refresh_queue()
        
        count = len(self.video_files)
        self.video_label.setText(f"📁  Found {count:,} clips — Ready to play")
        self.video_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; padding: 6px 4px;")
        self._update_clip_counter()

    def _refresh_queue(self):
        """Create a new shuffled queue of available clips"""
        available_clips = [
            f for f in self.video_files 
            if f not in self.blocked_clips
        ]
        
        # Filter by favorites if enabled
        if self.favorites_only:
            available_clips = [f for f in available_clips if f in self.liked_clips]
        
        if not available_clips:
            self.play_queue = []
            self.queue_index = -1
            return

        random.shuffle(available_clips)
        self.play_queue = available_clips
        self.queue_index = -1

    def _update_navigation_state(self):
        """Update state of navigation and rating buttons"""
        self.prev_clip_btn.setEnabled(self.queue_index > 0)
        
        has_video = bool(self.current_video)
        self.block_btn.setEnabled(has_video)
        self.like_btn.setEnabled(has_video)
        
        # Update Like button visual state (green when liked)
        if has_video and self.current_video in self.liked_clips:
            self.like_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['accent_green']};
                    color: {COLORS['text_primary']};
                    font-size: 14px;
                    border: none;
                    border-radius: 4px;
                }}
            """)
        else:
            self.like_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_light']};
                    color: {COLORS['text_muted']};
                    font-size: 14px;
                    border: 1px solid {COLORS['border']};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['bg_medium']};
                    border-color: {COLORS['accent_green']};
                    color: {COLORS['accent_green']};
                }}
                QPushButton:disabled {{
                    background-color: {COLORS['bg_medium']};
                    color: {COLORS['text_muted']};
                }}
            """)
        
        self._update_clip_counter()
        self._update_status_bar()

    def play_random_clip(self):
        """Play next random clip from shuffled queue"""
        if not self.play_queue:
            # Try to refresh if empty (maybe files were added or blocks removed)
            self._refresh_queue()
            
            if not self.play_queue:
                self.video_label.setText("⚠  No playable clips found (check blocked list)")
                self.video_label.setStyleSheet(f"color: {COLORS['accent_orange']}; font-size: 13px; padding: 6px 4px;")
                return

        # Advance index
        self.queue_index += 1
        
        # If we reached the end, reshuffle and start over
        if self.queue_index >= len(self.play_queue):
            self.video_label.setText("🔄  All clips played! Reshuffling...")
            random.shuffle(self.play_queue)
            self.queue_index = 0
            
        self.current_video = self.play_queue[self.queue_index]
        self._update_navigation_state()
        self._play_video(self.current_video)

    def play_previous_clip(self):
        """Navigate to the previous clip in queue"""
        if self.queue_index > 0:
            self.queue_index -= 1
            self.current_video = self.play_queue[self.queue_index]
            self._update_navigation_state()
            self._play_video(self.current_video)

    def toggle_autoplay(self):
        self.autoplay_enabled = self.autoplay_btn.isChecked()
        self.config_manager.set("autoplay", self.autoplay_enabled)
        state = "enabled" if self.autoplay_enabled else "disabled"
        self.status_label.setText(f"Autoplay {state}")
        QTimer.singleShot(1500, self._update_status_bar)

    def toggle_favorites_only(self):
        """Toggle favorites-only mode"""
        self.favorites_only = self.favorites_action.isChecked()
        self.config_manager.set("favorites_only", self.favorites_only)
        self._refresh_queue()
        self._update_clip_counter()
        
        if self.favorites_only:
            if not self.play_queue:
                self.video_label.setText("⭐ No favorites yet! Like some clips first (L)")
                self.video_label.setStyleSheet(f"color: {COLORS['accent_orange']}; font-size: 13px;")
            else:
                self.video_label.setText(f"⭐ Favorites mode: {len(self.play_queue)} clips")
            self.status_label.setText("Favorites ON")
        else:
            self.video_label.setText(f"📁  {len(self.play_queue)} clips ready")
            self.status_label.setText("Showing all clips")
        
        QTimer.singleShot(2000, self._update_status_bar)

    def open_current_in_explorer(self):
        """Open the folder containing the current clip"""
        if self.current_video and os.path.exists(self.current_video):
            # Select the file in explorer
            subprocess_args = f'/select,"{self.current_video}"'
            try:
                # Use standard Windows command
                ctypes.windll.shell32.ShellExecuteW(
                    None, "open", "explorer.exe", subprocess_args, None, 1
                )
            except Exception as e:
                self.status_label.setText("⚠ Failed to open explorer")
                print(f"Explorer error: {e}")

    def toggle_like(self):
        """Toggle like status for current clip"""
        if not self.current_video:
            return
            
        if self.current_video in self.liked_clips:
            self.liked_clips.remove(self.current_video)
            self.status_label.setText("💔 Like removed")
        else:
            self.liked_clips.add(self.current_video)
            self.status_label.setText("♥ Liked!")
            
        self.config_manager.set("liked_clips", list(self.liked_clips))
        self._update_navigation_state()
        QTimer.singleShot(1500, self._update_status_bar)

    def block_current_clip(self):
        """Add current clip to blocked list and skip to next"""
        if not self.current_video:
            return
            
        # Confirm blocking (Dislike)
        reply = QMessageBox.question(
            self, 
            "Dislike Clip", 
            "Dislike this clip?\nIt won't be shown in random playback again.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.blocked_clips.add(self.current_video)
            self.config_manager.set("blocked_clips", list(self.blocked_clips))
            
            # Remove from likes if present
            if self.current_video in self.liked_clips:
                self.liked_clips.remove(self.current_video)
                self.config_manager.set("liked_clips", list(self.liked_clips))
            
            self.status_label.setText("👎 Clip disliked")
            QTimer.singleShot(2000, self._update_status_bar)
            
            # Immediately play next random clip
            self.play_random_clip()

    def _reset_cycle(self):
        """Reshuffle the queue"""
        self._refresh_queue()
        self.video_label.setText("🔀  Queue reshuffled")
        self._update_clip_counter()
        self._update_status_bar()

    # ========================================================================
    # Playback Control
    # ========================================================================

    def _play_video(self, filepath):
        """Play a specific video file"""
        media = self.instance.media_new(filepath)
        self.player.set_media(media)
        
        # Set video output based on platform
        if sys.platform.startswith('linux'):
            self.player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
            self.player.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":
            self.player.set_nsobject(int(self.video_frame.winId()))
        
        self.player.play()
        self.timer.start()
        
        # Cache FPS after a short delay (VLC needs time to read metadata)
        QTimer.singleShot(200, self._cache_fps)
        
        # Update UI with truncated filename
        filename = os.path.basename(filepath)
        display_name = filename if len(filename) <= 65 else filename[:62] + "..."
        self.video_label.setText(f"▶  {display_name}")
        self.video_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px; padding: 6px 4px;")
        self.play_btn.setText("⏸  Pause")
        
        # Apply current playback rate from speed button
        self._apply_current_speed()

    def _toggle_play_pause(self):
        """Toggle between play and pause states"""
        state = self.player.get_state()
        
        if state == vlc.State.Ended:
            self.player.stop()
            self.player.play()
            self.play_btn.setText("⏸  Pause")
            self.timer.start()
            if self.slow_mo_btn.isChecked():
                self.player.set_rate(0.5)
        elif self.player.is_playing():
            self.player.pause()
            self.play_btn.setText("▶  Play")
        else:
            self.player.play()
            self.play_btn.setText("⏸  Pause")
            self.timer.start()
            self._apply_current_speed()

    def _toggle_slow_motion(self):
        """Toggle between 0.5x and 1.0x speed"""
        if self.slow_mo_btn.isChecked():
            self.slow_mo_btn.set_speed(0.5)
            self.player.set_rate(0.5)
        else:
            self.slow_mo_btn.set_speed(1.0)
            self.player.set_rate(1.0)

    def _toggle_slow_motion_keyboard(self):
        """Toggle slow motion via keyboard"""
        self.slow_mo_btn.setChecked(not self.slow_mo_btn.isChecked())
        self._toggle_slow_motion()
        
    def _set_playback_speed(self, speed):
        """Set playback speed from scroll wheel"""
        self.player.set_rate(speed)
        self.status_label.setText(f"Speed: {speed}x")
        QTimer.singleShot(1500, self._update_status_bar)
        
    def _apply_current_speed(self):
        """Apply the current speed setting from the button"""
        speed = self.slow_mo_btn.current_speed
        self.player.set_rate(speed)

    def _stop(self):
        """Stop playback completely"""
        self.player.stop()
        self.timer.stop()
        self.play_btn.setText("▶  Play")
        self.time_slider.setValue(0)
        self.time_label.setText("0:00")
        self.video_label.setText("⏹  Stopped — Press Space to play next clip")
        self.video_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; padding: 6px 4px;")

    def _skip(self, ms):
        """Skip forward or backward by milliseconds"""
        current = self.player.get_time()
        duration = self.player.get_length()
        new_time = max(0, min(duration, current + ms))
        self.player.set_time(int(new_time))

    def _cache_fps(self):
        """Cache the FPS of current video"""
        fps = self.player.get_fps()
        self._cached_fps = fps if fps and fps > 0 else 0

    def _get_frame_duration_ms(self):
        """Get the duration of one frame in milliseconds based on cached fps"""
        if self._cached_fps > 0:
            return max(1, int(1000 / self._cached_fps))  # e.g., 60fps -> 16ms, 120fps -> 8ms
        return 33  # Default to ~30fps if unknown

    def _frame_step_forward(self):
        """Advance one frame forward based on video fps"""
        if self.player.is_playing():
            self.player.pause()
            self.play_btn.setText("▶  Play")
        frame_ms = self._get_frame_duration_ms()
        current = self.player.get_time()
        self.player.set_time(current + frame_ms)
        fps = self._cached_fps or 30
        self.status_label.setText(f"⏭ +1 frame ({fps:.0f}fps)")
        QTimer.singleShot(1000, self._update_status_bar)

    def _frame_step_backward(self):
        """Step backward one frame based on video fps"""
        if self.player.is_playing():
            self.player.pause()
            self.play_btn.setText("▶  Play")
        frame_ms = self._get_frame_duration_ms()
        current = self.player.get_time()
        self.player.set_time(max(0, current - frame_ms))
        fps = self._cached_fps or 30
        self.status_label.setText(f"⏮ -1 frame ({fps:.0f}fps)")
        QTimer.singleShot(1000, self._update_status_bar)

    def _set_position(self, position):
        """Set video position from slider"""
        self.player.set_position(position / 1000.0)

    def _slider_pressed(self):
        """Handle slider press"""
        self.is_slider_pressed = True

    def _slider_released(self):
        """Handle slider release"""
        self.is_slider_pressed = False
        self._set_position(self.time_slider.value())

    def _set_volume(self, volume):
        """Set audio volume"""
        self.player.audio_set_volume(volume)
        self.volume_label.setText(f"{volume}%")
        
        # Save volume preference
        self.config_manager.set("volume", volume)
        
        # Update icon based on volume level
        if volume == 0:
            self.volume_icon.setText("🔇")
        elif volume < 33:
            self.volume_icon.setText("🔈")
        elif volume < 66:
            self.volume_icon.setText("🔉")
        else:
            self.volume_icon.setText("🔊")

    def _toggle_mute(self):
        """Toggle mute state"""
        if self.volume_slider.value() > 0:
            self._last_volume = self.volume_slider.value()
            self.volume_slider.setValue(0)
        else:
            self.volume_slider.setValue(self._last_volume)

    # ========================================================================
    # UI Updates
    # ========================================================================

    def _update_playback_ui(self):
        """Update playback-related UI elements"""
        if not self.is_slider_pressed:
            position = self.player.get_position()
            self.time_slider.setValue(int(position * 1000))
        
        current_time = self.player.get_time()
        duration = self.player.get_length()
        
        self.time_label.setText(self._format_time(current_time))
        self.duration_label.setText(self._format_time(duration))
        
        # Handle video end
        state = self.player.get_state()
        if state == vlc.State.Ended:
            if self.autoplay_enabled:
                QTimer.singleShot(50, self.play_random_clip)
            else:
                self.timer.stop()
                self.play_btn.setText("▶  Play")

    def _update_clip_counter(self):
        """Update the clip counter display"""
        if not self.play_queue:
             self.clip_counter.setText("0 / 0")
             return
             
        current = self.queue_index + 1
        total = len(self.play_queue)
        self.clip_counter.setText(f"{current} / {total}")

    def _update_status_bar(self):
        """Update the status bar with current state info"""
        if not self.play_queue:
            self.status_label.setText("Ready")
            return
            
        remaining = len(self.play_queue) - (self.queue_index + 1)
        
        parts = [f"{remaining:,} remaining"]
        
        if self.autoplay_enabled:
            parts.append("Autoplay ON")
        
        self.status_label.setText("  •  ".join(parts))

    @staticmethod
    def _format_time(ms):
        """Format milliseconds to M:SS or H:MM:SS"""
        if ms < 0:
            return "0:00"
        
        total_seconds = ms // 1000
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    # ========================================================================
    # Event Handlers
    # ========================================================================

    def mouseMoveEvent(self, event):
        """Handle mouse movement for auto-hide controls"""
        if self.auto_hide_controls:
            self._show_controls()
            # Only start hide timer if mouse is over video area
            if self._is_mouse_over_video(event.pos()):
                self.hide_controls_timer.start()
            else:
                self.hide_controls_timer.stop()
        super().mouseMoveEvent(event)
        
    def _is_mouse_over_video(self, pos):
        """Check if mouse position is over the video frame area"""
        if hasattr(self, 'video_frame'):
            video_rect = self.video_frame.geometry()
            # Map to parent coordinates
            video_global = self.video_frame.parent().mapToParent(video_rect.topLeft())
            video_rect.moveTopLeft(video_global)
            return video_rect.contains(pos)
        return True
        
    def enterEvent(self, event):
        """Show controls when mouse enters window"""
        if self.auto_hide_controls:
            self._show_controls()
            self.hide_controls_timer.stop()
        super().enterEvent(event)
        
    def leaveEvent(self, event):
        """Start hide timer when mouse leaves window"""
        if self.auto_hide_controls:
            self.hide_controls_timer.start()
        super().leaveEvent(event)
        
    def _show_controls(self):
        """Show the controls bar with slide animation"""
        if hasattr(self, 'controls_container'):
            self.controls_container.setVisible(True)
            # Animate opacity/position
            if hasattr(self, '_controls_animation'):
                self._controls_animation.stop()
            self.controls_container.setMaximumHeight(60)
            
    def _hide_controls(self):
        """Hide the controls bar with slide animation if auto-hide is enabled"""
        if self.auto_hide_controls and hasattr(self, 'controls_container'):
            # Animate slide out by reducing max height
            self._controls_animation = QPropertyAnimation(self.controls_container, b"maximumHeight")
            self._controls_animation.setDuration(200)
            self._controls_animation.setStartValue(self.controls_container.height())
            self._controls_animation.setEndValue(0)
            self._controls_animation.setEasingCurve(QEasingCurve.OutQuad)
            self._controls_animation.finished.connect(lambda: self.controls_container.setVisible(False) if self.auto_hide_controls else None)
            self._controls_animation.start()

    def closeEvent(self, event):
        """Clean up on window close"""
        self.timer.stop()
        self.hide_controls_timer.stop()
        if hasattr(self, '_controls_animation'):
            self._controls_animation.stop()
        self.player.stop()
        self.player.release()
        self.instance.release()
        event.accept()


# ============================================================================
# Application Entry Point
# ============================================================================

def main():
    # Enable high DPI scaling for crisp UI on 4K displays
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("Random Clip Player")
    app.setStyle('Fusion')
    
    # Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    player = VideoPlayer()
    player.show()
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
