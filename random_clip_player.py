"""
Random Clip Player - A polished video clip player with random playback
Version 4.5 - Bugfix & Stability
"""

import sys
import os
import json
import random
import ctypes
import argparse
import logging
import traceback
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QSlider, QLabel, QFrame, QSizePolicy,
    QFileDialog, QMessageBox, QDialog, QListWidget, QListWidgetItem,
    QScrollArea
)
from PySide6.QtCore import Qt, QTimer, QMimeData, QPoint, QPropertyAnimation, QEasingCurve, Signal, QObject, QEvent
from PySide6.QtGui import QFont, QKeySequence, QIcon, QDrag, QPixmap, QPainter, QShortcut, QAction

# Session (Watch Together) support — imported lazily to keep solo mode clean
try:
    from session_client import SessionClient
    SESSION_AVAILABLE = True
except ImportError:
    SessionClient = None  # type: ignore[assignment,misc]
    SESSION_AVAILABLE = False

# Handle Nuitka MPV dll bundling so python-mpv can find mpv-1.dll
if "__compiled__" in globals():
    # Running as compiled Nuitka executable
    base_dir = os.path.dirname(sys.executable)
    os.environ["PATH"] = os.path.join(base_dir, "lib") + os.pathsep + os.environ.get("PATH", "")
else:
    # Running from source
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.environ["PATH"] = os.path.join(base_dir, "lib") + os.pathsep + os.environ.get("PATH", "")

import mpv

# ============================================================================
# MPV Player Signals (thread-safe communication from MPV to UI)
# ============================================================================

class PlayerSignals(QObject):
    """
    Signals used to route MPV property observers (which run on a background thread)
    safely back to the Qt main thread to update the GUI without crashing.
    """
    time_updated = Signal(float)
    duration_changed = Signal(float)
    eof_reached = Signal()
    playback_state_changed = Signal(bool) # True = playing, False = paused

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
        appdata = os.environ.get('APPDATA')
        if appdata:
            self.config_dir = Path(appdata) / "RandomClipPlayer"
            self.config_dir.mkdir(parents=True, exist_ok=True)
            self.config_file = self.config_dir / "config.json"
        else:
            self.config_file = Path("config.json")
        self.default_config = {
            "clips_folder": "",
            "volume": 80,
            "blocked_clips": [],
            "liked_clips": [],
            "autoplay": False,
            "favorites_only": False,
            "auto_hide_controls": False,
            "session": {
                "server_ip": "",
                "server_port": "8765",
                "username": "",
                "last_room_code": "",
            },
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
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._do_save)

    def load_config(self):
        """Load config from JSON file or return defaults (deep-merged)"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    saved = json.load(f)
                return self._deep_merge(self.default_config, saved)
            except Exception:
                return self.default_config.copy()
        return self.default_config.copy()

    @staticmethod
    def _deep_merge(defaults: dict, overrides: dict) -> dict:
        """Recursively merge overrides into defaults so nested dicts keep new default keys."""
        merged = defaults.copy()
        for key, value in overrides.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = ConfigManager._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged

    def save_config(self):
        """Debounce save requests"""
        self._save_timer.start(500)  # 500ms debounce

    def _do_save(self):
        """Actually save current config to JSON file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            logging.getLogger("rdm").warning(f"Failed to save config: {e}")

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
            item.setData(Qt.ItemDataRole.UserRole, clip)
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
            clip_path = item.data(Qt.ItemDataRole.UserRole)
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
        if event.button() == Qt.MouseButton.LeftButton:
            self.capturing = True
            self.setText("Press a key...")
            self.setStyleSheet(f"background-color: {COLORS['accent_blue']}; color: white; padding: 4px 8px; border-radius: 4px;")
        super().mousePressEvent(event)
        
    def keyPressEvent(self, event):
        if self.capturing:
            key = event.key()
            # Map Qt key to readable name
            key_map = {
                Qt.Key.Key_Space: "Space", Qt.Key.Key_Return: "Return", Qt.Key.Key_Escape: "Escape",
                Qt.Key.Key_Backspace: "Backspace", Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Tab: "Tab",
                Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right", Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
                Qt.Key.Key_Period: "Period", Qt.Key.Key_Comma: "Comma",
                Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "PageUp", Qt.Key.Key_PageDown: "PageDown",
            }
            
            new_key = None
            if key in key_map:
                new_key = key_map[key]
            elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
                new_key = chr(key)
            elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
                new_key = chr(key)
            elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F12:
                new_key = f"F{key - Qt.Key.Key_F1 + 1}"
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
        if event.button() == Qt.MouseButton.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.position().x()) / self.width()
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
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                    self._drag_start = event.pos()
                    return True  # Consume the event
            elif event.type() == QEvent.Type.MouseMove and self._drag_start:
                if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                    if (event.pos() - self._drag_start).manhattanLength() > 10:
                        self._start_drag(event.pos())
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
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
        pixmap.fill(Qt.GlobalColor.transparent)
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(pos)
        
        # Visual feedback - highlight draggable items
        parent = self.parent()
        if parent and hasattr(parent, 'set_rearrange_mode'):
            parent.set_rearrange_mode(True)
        
        drag.exec(Qt.DropAction.MoveAction)
        
        if parent and hasattr(parent, 'set_rearrange_mode'):
            parent.set_rearrange_mode(False)
            
        self._drag_start = None
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasText() and (event.keyboardModifiers() & Qt.KeyboardModifier.AltModifier):
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
        self._layout = QHBoxLayout(self)
        self._layout.setSpacing(self.BUTTON_SPACING)
        self._layout.setContentsMargins(0, 4, 0, 0)
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
        self._layout.addWidget(draggable, stretch)
        
    def add_spacing(self, size):
        """Add spacing to layout"""
        self._layout.addSpacing(size)
        
    def add_fixed_widget(self, widget, stretch=0):
        """Add a non-draggable widget"""
        self._layout.addWidget(widget, stretch)
        
    def swap_widgets(self, source_id, target_id):
        """Swap two widgets in the layout"""
        if source_id not in self.widget_map or target_id not in self.widget_map:
            return
            
        source = self.widget_map[source_id]
        target = self.widget_map[target_id]
        
        source_idx = self._layout.indexOf(source)
        target_idx = self._layout.indexOf(target)
        
        if source_idx >= 0 and target_idx >= 0:
            # Remove both
            self._layout.removeWidget(source)
            self._layout.removeWidget(target)
            
            # Re-insert in swapped positions
            if source_idx < target_idx:
                self._layout.insertWidget(source_idx, target)
                self._layout.insertWidget(target_idx, source)
            else:
                self._layout.insertWidget(target_idx, source)
                self._layout.insertWidget(source_idx, target)
                
            # Save order
            self._save_order()
            
    def _save_order(self):
        """Save current widget order to config"""
        order = []
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None and isinstance(w, DraggableWidget):
                order.append(w.widget_id)
        self.config_manager.set("button_order", order)
        
    def restore_order(self, order):
        """Restore widget order from saved config"""
        if not order:
            return
            
        # Get current positions
        widgets_by_id = {}
        for widget_id, draggable in self.widget_map.items():
            idx = self._layout.indexOf(draggable)
            if idx >= 0:
                widgets_by_id[widget_id] = (draggable, idx)
        
        # Temporarily remove all draggable widgets
        for widget_id, (draggable, _) in widgets_by_id.items():
            self._layout.removeWidget(draggable)
            
        # Re-add in order, then remaining ones
        added = set()
        insert_pos = 0
        for widget_id in order:
            if widget_id in widgets_by_id:
                draggable, _ = widgets_by_id[widget_id]
                self._layout.insertWidget(insert_pos, draggable)
                added.add(widget_id)
                insert_pos += 1
                
        # Add any that weren't in the saved order
        for widget_id, (draggable, _) in widgets_by_id.items():
            if widget_id not in added:
                self._layout.insertWidget(insert_pos, draggable)
                insert_pos += 1


class SpeedButton(QPushButton):
    """Custom button that changes playback speed on scroll"""
    
    SPEEDS = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.current_speed = 1.0
        self.speed_changed = None  # Callback set by VideoPlayer
        self.setMinimumHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
# Session Panel (Watch Together)
# ============================================================================

class SessionPanel(QFrame):
    """Collapsible right-side panel for Watch Together session management."""

    # Signal to safely pass test results from background thread to UI
    _test_result_signal = Signal(bool, str)

    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.session_client = None
        self._player = parent  # Reference to VideoPlayer
        self.setAcceptDrops(True)  # Enable drag & drop for video sharing

        # Pending sync state (set when joining mid-session)
        self._pending_sync_state: dict = {}
        self._pending_sync_video_id: str | None = None
        self._pending_prepare_video_id: str | None = None

        self.setFixedWidth(280)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_medium']};
                border-left: 1px solid {COLORS['border']};
            }}
        """)

        self._test_result_signal.connect(self._show_test_result)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header
        header = QLabel("🎬  Watch Together")
        header.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 14px; font-weight: bold; border: none;")
        layout.addWidget(header)

        # ---- Connection Section ----
        self.connect_section = QWidget()
        self.connect_section.setStyleSheet("border: none;")
        conn_layout = QVBoxLayout(self.connect_section)
        conn_layout.setContentsMargins(0, 0, 0, 0)
        conn_layout.setSpacing(6)

        # Server Address + Port
        conn_layout.addWidget(self._make_label("Server Address"))
        session_cfg = self.config_manager.get("session") or {}
        
        server_row = QHBoxLayout()
        server_row.setSpacing(4)
        self.server_ip_input = self._make_input(session_cfg.get("server_ip", ""), "IP / hostname")
        self.server_port_input = self._make_input(session_cfg.get("server_port", "8765"), "Port")
        self.server_port_input.setFixedWidth(60)
        server_row.addWidget(self.server_ip_input, stretch=1)
        colon_label = QLabel(":")
        colon_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px; font-weight: bold; border: none;")
        colon_label.setFixedWidth(8)
        server_row.addWidget(colon_label)
        server_row.addWidget(self.server_port_input)
        conn_layout.addLayout(server_row)

        # Test connection button
        self.test_btn = QPushButton("Test Connection")
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.test_btn.setStyleSheet(self._btn_style())
        self.test_btn.clicked.connect(self._test_connection)
        conn_layout.addWidget(self.test_btn)

        self.connection_status = QLabel("")
        self.connection_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; border: none;")
        self.connection_status.setWordWrap(True)
        conn_layout.addWidget(self.connection_status)

        conn_layout.addWidget(self._make_separator())

        # Username
        conn_layout.addWidget(self._make_label("Username"))
        self.username_input = self._make_input(session_cfg.get("username", ""), "Your display name")
        conn_layout.addWidget(self.username_input)

        conn_layout.addWidget(self._make_separator())

        # Create Room
        conn_layout.addWidget(self._make_label("Create Room"))
        self.create_pw_input = self._make_input("", "Room password", password=True)
        conn_layout.addWidget(self.create_pw_input)
        self.create_btn = QPushButton("🏠  Create Room")
        self.create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.create_btn.setStyleSheet(self._btn_style(COLORS['accent_green']))
        self.create_btn.clicked.connect(self._create_room)
        conn_layout.addWidget(self.create_btn)

        conn_layout.addWidget(self._make_separator())

        # Join Room
        conn_layout.addWidget(self._make_label("Join Room"))
        self.join_code_input = self._make_input(session_cfg.get("last_room_code", ""), "Room code")
        conn_layout.addWidget(self.join_code_input)
        self.join_pw_input = self._make_input("", "Room password", password=True)
        conn_layout.addWidget(self.join_pw_input)
        self.join_btn = QPushButton("🔗  Join Room")
        self.join_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.join_btn.setStyleSheet(self._btn_style(COLORS['accent_blue']))
        self.join_btn.clicked.connect(self._join_room)
        conn_layout.addWidget(self.join_btn)

        layout.addWidget(self.connect_section)

        # ---- Active Session Section (hidden until connected) ----
        self.session_section = QWidget()
        self.session_section.setStyleSheet("border: none;")
        self.session_section.setVisible(False)
        sess_layout = QVBoxLayout(self.session_section)
        sess_layout.setContentsMargins(0, 0, 0, 0)
        sess_layout.setSpacing(6)

        # Room info + copy button
        room_row = QHBoxLayout()
        room_row.setSpacing(4)
        self.room_info_label = QLabel("")
        self.room_info_label.setStyleSheet(f"color: {COLORS['accent_green']}; font-size: 12px; font-weight: bold; border: none;")
        room_row.addWidget(self.room_info_label, stretch=1)

        self.copy_code_btn = QPushButton("📋 Copy")
        self.copy_code_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_code_btn.setFixedWidth(70)
        self.copy_code_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['bg_light']};
                color: {COLORS['text_secondary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['border']};
                color: {COLORS['text_primary']};
            }}
        """)
        self.copy_code_btn.clicked.connect(self._copy_room_code)
        room_row.addWidget(self.copy_code_btn)
        sess_layout.addLayout(room_row)

        # Ping display
        self.ping_label = QLabel("📶 Ping: —")
        self.ping_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; border: none;")
        sess_layout.addWidget(self.ping_label)

        # Shared random pool toggle (host only)
        from PySide6.QtWidgets import QCheckBox
        self.shared_pool_cb = QCheckBox("🎲 Shared random pool")
        self.shared_pool_cb.setToolTip("When on, Random Clip picks from a random user's gallery")
        self.shared_pool_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {COLORS['text_secondary']};
                font-size: 11px;
                border: none;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {COLORS['border']};
                border-radius: 3px;
                background-color: {COLORS['bg_dark']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLORS['accent_blue']};
                border-color: {COLORS['accent_blue']};
            }}
        """)
        self.shared_pool_cb.toggled.connect(self._on_shared_pool_toggled)
        sess_layout.addWidget(self.shared_pool_cb)

        sess_layout.addWidget(self._make_separator())

        # Users list
        sess_layout.addWidget(self._make_label("Connected Users"))
        self.users_list = QListWidget()
        self.users_list.setMaximumHeight(120)
        self.users_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.users_list.customContextMenuRequested.connect(self._show_user_context_menu)
        self.users_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS['bg_dark']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_primary']};
                font-size: 11px;
            }}
            QListWidget::item {{ padding: 3px 6px; }}
        """)
        sess_layout.addWidget(self.users_list)

        sess_layout.addWidget(self._make_separator())

        # Activity feed
        sess_layout.addWidget(self._make_label("Activity"))
        self.activity_feed = QListWidget()
        self.activity_feed.setMaximumHeight(100)
        self.activity_feed.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.activity_feed.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.activity_feed.setSelectionMode(QListWidget.NoSelection)
        self.activity_feed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.activity_feed.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS['bg_dark']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_muted']};
                font-size: 10px;
            }}
            QListWidget::item {{
                padding: 2px 6px;
                border: none;
            }}
        """)
        sess_layout.addWidget(self.activity_feed)

        sess_layout.addWidget(self._make_separator())

        # Share clip button (also drop hint)
        self.share_btn = QPushButton("📤  Share Current Clip")
        self.share_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.share_btn.setStyleSheet(self._btn_style(COLORS['accent_orange']))
        self.share_btn.clicked.connect(self._share_current_clip)
        sess_layout.addWidget(self.share_btn)

        # Drop hint
        self.drop_hint = QLabel("📂  or drag && drop a video file here")
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drop_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 9px; border: none; font-style: italic;")
        sess_layout.addWidget(self.drop_hint)

        # Upload/download progress
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; border: none;")
        self.progress_label.setWordWrap(True)
        sess_layout.addWidget(self.progress_label)

        sess_layout.addWidget(self._make_separator())

        # Now playing
        self.now_playing_label = QLabel("Nothing playing")
        self.now_playing_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; border: none;")
        self.now_playing_label.setWordWrap(True)
        sess_layout.addWidget(self.now_playing_label)

        sess_layout.addWidget(self._make_separator())

        # Disconnect button
        self.disconnect_btn = QPushButton("❌  Disconnect")
        self.disconnect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.disconnect_btn.setStyleSheet(self._btn_style(COLORS['accent_red']))
        self.disconnect_btn.clicked.connect(self._disconnect)
        sess_layout.addWidget(self.disconnect_btn)

        sess_layout.addStretch()
        layout.addWidget(self.session_section)

        layout.addStretch()

    # ---- Helpers ----

    def _make_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 11px; border: none;")
        return lbl

    def _make_input(self, value, placeholder, password=False):
        from PySide6.QtWidgets import QLineEdit
        inp = QLineEdit(value)
        inp.setPlaceholderText(placeholder)
        if password:
            inp.setEchoMode(QLineEdit.Password)
        inp.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLORS['bg_dark']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                padding: 6px 8px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['accent_blue']};
            }}
        """)
        return inp

    def _make_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background-color: {COLORS['border']}; border: none; max-height: 1px;")
        return sep

    # ---- Activity Feed ----

    _VIDEO_EXTENSIONS = VIDEO_EXTENSIONS  # Reuse the module-level constant

    def add_activity(self, text):
        """Add an entry to the activity feed (max 50 items, auto-scrolls)."""
        if not hasattr(self, 'activity_feed'):
            return
        self.activity_feed.addItem(text)
        while self.activity_feed.count() > 50:
            self.activity_feed.takeItem(0)
        self.activity_feed.scrollToBottom()

    # ---- Drag & Drop ----

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in self._VIDEO_EXTENSIONS:
                        event.acceptProposedAction()
                        return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        for url in event.mimeData().urls():
            if url.isLocalFile():
                filepath = url.toLocalFile()
                ext = os.path.splitext(filepath)[1].lower()
                if ext in self._VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    self._share_dropped_file(filepath)
                    return
        event.ignore()

    def _share_dropped_file(self, filepath):
        """Upload a dropped video file to the session."""
        if not self.session_client or not self.session_client.is_connected:
            self.progress_label.setText("Not connected — can't share")
            return
        filename = os.path.basename(filepath)
        self.progress_label.setText(f"⏳ Uploading {filename}...")
        self.add_activity(f"📤 You shared {filename}")
        self.session_client.upload_and_play(filepath)

    def _btn_style(self, bg=None):
        bg = bg or COLORS['bg_light']
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {COLORS['text_primary']};
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
            QPushButton:pressed {{ opacity: 0.7; }}
        """

    # ---- Actions ----

    def _save_session_config(self):
        session_cfg = self.config_manager.get("session") or {}
        session_cfg["server_ip"] = self.server_ip_input.text().strip()
        session_cfg["server_port"] = self.server_port_input.text().strip() or "8765"
        session_cfg["username"] = self.username_input.text().strip()
        self.config_manager.set("session", session_cfg)

    def _get_server_url(self):
        """Build the full server URL from IP + Port fields."""
        ip = self.server_ip_input.text().strip()
        port = self.server_port_input.text().strip() or "8765"
        if not ip:
            return None
        return f"{ip}:{port}"

    def _test_connection(self):
        if not SESSION_AVAILABLE:
            self.connection_status.setText("❌ Session module not available (check dependencies)")
            return
        server = self._get_server_url()
        if not server:
            self.connection_status.setText("❌ Enter a server address")
            return
        self.connection_status.setText("⏳ Testing...")
        self.connection_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; border: none;")
        # Run test in background so UI doesn't freeze
        import threading
        def test():
            if SessionClient is None:
                self._test_result_signal.emit(False, "Session module not available")
                return
            client = SessionClient()
            ok, msg = client.test_connection(server)
            self._test_result_signal.emit(ok, msg)
        threading.Thread(target=test, daemon=True).start()

    def _show_test_result(self, ok, msg):
        color = COLORS['accent_green'] if ok else COLORS['accent_red']
        icon = "✅" if ok else "❌"
        self.connection_status.setText(f"{icon} {msg}")
        self.connection_status.setStyleSheet(f"color: {color}; font-size: 10px; border: none;")
        if ok:
            self._save_session_config()

    def _create_room(self):
        if not SESSION_AVAILABLE:
            self.connection_status.setText("❌ Session module not available")
            return
        server = self._get_server_url()
        username = self.username_input.text().strip()
        password = self.create_pw_input.text()
        if not server:
            self.connection_status.setText("❌ Enter a server address")
            return
        if not username:
            self.connection_status.setText("❌ Enter a username")
            return
        if not password or len(password) < 4:
            self.connection_status.setText("❌ Password must be at least 4 characters")
            return

        self._save_session_config()
        self.connection_status.setText("⏳ Creating room...")

        if SessionClient is None:
            self.connection_status.setText("❌ Session module not available")
            return
        self.session_client = SessionClient()
        self._connect_signals()
        self.session_client.create_room(server, username, password)

    def _join_room(self):
        if not SESSION_AVAILABLE:
            self.connection_status.setText("❌ Session module not available")
            return
        server = self._get_server_url()
        username = self.username_input.text().strip()
        room_code = self.join_code_input.text().strip().upper()
        password = self.join_pw_input.text()
        if not server:
            self.connection_status.setText("❌ Enter a server address")
            return
        if not username:
            self.connection_status.setText("❌ Enter a username")
            return
        if not room_code:
            self.connection_status.setText("❌ Enter a room code")
            return
        if not password:
            self.connection_status.setText("❌ Enter the room password")
            return

        self._save_session_config()
        session_cfg = self.config_manager.get("session") or {}
        session_cfg["last_room_code"] = room_code
        self.config_manager.set("session", session_cfg)

        self.connection_status.setText("⏳ Joining room...")

        if SessionClient is None:
            self.connection_status.setText("❌ Session module not available")
            return
        self.session_client = SessionClient()
        self._connect_signals()
        self.session_client.join_room(server, username, room_code, password)

    def _disconnect(self):
        if self.session_client:
            self.session_client.disconnect()
        self._show_disconnected("Disconnected")

    def _copy_room_code(self):
        """Copy the room code to clipboard."""
        if self.session_client and self.session_client.room_code:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(self.session_client.room_code)
            self.copy_code_btn.setText("✅ Copied!")
            copy_btn = self.copy_code_btn
            QTimer.singleShot(1500, lambda: copy_btn.setText("📋 Copy"))

    def _share_current_clip(self):
        if not self.session_client or not self.session_client.is_connected:
            self.progress_label.setText("Not connected")
            return
        player = self._player
        if player and player.current_video and os.path.exists(player.current_video):
            self.progress_label.setText("⏳ Uploading...")
            self.session_client.upload_and_play(player.current_video)
        else:
            self.progress_label.setText("No clip loaded")

    # ---- Signal Wiring ----

    def _connect_signals(self):
        assert self.session_client is not None
        c = self.session_client.signals
        c.connected.connect(self._on_connected)
        c.disconnected.connect(self._show_disconnected)
        c.connection_error.connect(self._on_error)
        c.room_created.connect(self._on_room_created)
        c.room_joined.connect(self._on_room_joined)
        c.room_error.connect(self._on_error)
        c.user_joined.connect(self._on_user_joined)
        c.user_left.connect(self._on_user_left)
        c.user_kicked.connect(self._on_user_kicked)
        c.kicked.connect(self._on_kicked)
        c.upload_progress.connect(self._on_upload_progress)
        c.download_progress.connect(self._on_download_progress)
        c.video_uploaded.connect(self._on_video_uploaded)
        c.video_ready.connect(self._on_video_ready)
        c.ping_result.connect(self._on_ping_result)
        c.sync_to_video.connect(self._on_sync_to_video)

        # Ready-sync signals
        c.prepare_video.connect(self._on_prepare_video)
        c.all_ready.connect(self._on_all_ready)
        c.ready_progress.connect(self._on_ready_progress)

        # Shared pool: server asks us to provide a random clip
        if self._player:
            c.random_clip_requested.connect(self._player._on_random_clip_requested)
        c.shared_pool_changed.connect(self._on_shared_pool_changed)

        # Playback signals → forwarded to VideoPlayer (and logged in activity)
        if self._player:
            c.remote_play.connect(self._on_activity_play)
            c.remote_pause.connect(self._on_activity_pause)
            c.remote_seek.connect(self._on_activity_seek)
            c.remote_speed.connect(self._on_activity_speed)
            c.remote_play_video.connect(self._on_activity_play_video)

    # ---- Handlers ----

    def _on_activity_play(self, position, username):
        self.add_activity(f"▶ {username} pressed play")
        if self._player:
            self._player._on_remote_play(position, username)

    def _on_activity_pause(self, position, username):
        self.add_activity(f"⏸ {username} paused")
        if self._player:
            self._player._on_remote_pause(position, username)

    def _on_activity_seek(self, position, username):
        self.add_activity(f"⏩ {username} seeked")
        if self._player:
            self._player._on_remote_seek(position, username)

    def _on_activity_speed(self, speed, username):
        self.add_activity(f"⚡ {username} set speed {speed}x")
        if self._player:
            self._player._on_remote_speed(speed, username)

    def _on_activity_play_video(self, video_id, filename, username):
        self.add_activity(f"🎬 {username} shared {filename}")
        if self._player:
            self._player._on_remote_play_video(video_id, filename, username)

    def _on_connected(self):
        self.connection_status.setText("✅ WebSocket connected")
        self.connection_status.setStyleSheet(f"color: {COLORS['accent_green']}; font-size: 10px; border: none;")

    def _on_room_created(self, room_code, user_id):
        self.room_info_label.setText(f"Room: {room_code}")
        self.connect_section.setVisible(False)
        self.session_section.setVisible(True)
        self.users_list.clear()
        self.activity_feed.clear()
        username = self.username_input.text().strip()
        self.users_list.addItem(f"👑 {username} (you)")
        self.add_activity(f"🏠 Room {room_code} created")
        # Update connection dot
        if self._player:
            self._player._update_session_dot(True)

    def _on_room_joined(self, data):
        if isinstance(data, dict):
            room_code = data.get("room_code", (self.session_client.room_code if self.session_client else "") or "")
            users = data.get("users", [])
        else:
            room_code = (self.session_client.room_code if self.session_client else "") or ""
            users = []
        self.room_info_label.setText(f"Room: {room_code}")
        self.connect_section.setVisible(False)
        self.session_section.setVisible(True)
        # Only clear activity if this is the first join (not a reconnect)
        was_reconnect = self.activity_feed.count() > 0
        self._update_users_list(users)
        if was_reconnect:
            self.add_activity("🔄 Reconnected")
        else:
            self.add_activity(f"🔗 Joined room {room_code}")
        # Update connection dot
        if self._player:
            self._player._update_session_dot(True)

    def _on_sync_to_video(self, video_id, filename, playback_state):
        """Sync to the video currently playing when joining mid-session."""
        self.add_activity(f"🔄 Syncing to: {filename}")
        self.now_playing_label.setText(f"▶ {filename}")
        self._pending_sync_state = playback_state  # Will be applied once video_ready fires
        self._pending_sync_video_id = video_id

    def _on_user_joined(self, username, users):
        self._update_users_list(users)
        self.add_activity(f"👋 {username} joined")
        self.progress_label.setText(f"👋 {username} joined")
        QTimer.singleShot(3000, lambda: self.progress_label.setText(""))

    def _on_user_left(self, username, users):
        self._update_users_list(users)
        self.add_activity(f"👋 {username} left")
        self.progress_label.setText(f"👋 {username} left")
        QTimer.singleShot(3000, lambda: self.progress_label.setText(""))

    def _on_user_kicked(self, username, kicked_by, users):
        self._update_users_list(users)
        self.add_activity(f"🚫 {username} was kicked by {kicked_by}")
        self.progress_label.setText(f"🚫 {username} was kicked")
        QTimer.singleShot(3000, lambda: self.progress_label.setText(""))

    def _on_kicked(self, message):
        """We were kicked from the room."""
        self.add_activity(f"🚫 {message}")
        self._show_disconnected(message)

    def _update_users_list(self, users):
        self.users_list.clear()
        self._users_data = users  # Store for kick context menu
        for u in users:
            uid = u.get("user_id", "")
            uname = u.get("username", "Unknown")
            prefix = "👑 " if self.session_client and uid == self.session_client._host_id else ""
            suffix = " (you)" if self.session_client and uid == self.session_client.user_id else ""
            self.users_list.addItem(f"{prefix}{uname}{suffix}")

    def _show_user_context_menu(self, pos):
        """Right-click context menu on users list — host can kick."""
        if not self.session_client or not self.session_client.is_host:
            return
        item = self.users_list.itemAt(pos)
        if not item:
            return
        row = self.users_list.row(item)
        if not hasattr(self, '_users_data') or row >= len(self._users_data):
            return
        user = self._users_data[row]
        uid = user.get("user_id", "")
        uname = user.get("username", "")
        # Can't kick yourself
        if uid == self.session_client.user_id:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {COLORS['bg_medium']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border']};
            }}
            QMenu::item {{ padding: 6px 24px; }}
            QMenu::item:selected {{ background-color: {COLORS['accent_red']}; }}
        """)
        kick_action = menu.addAction(f"🚫 Kick {uname}")
        viewport = self.users_list.viewport()
        assert viewport is not None
        action = menu.exec(viewport.mapToGlobal(pos))
        if action == kick_action:
            self.session_client.send_kick(uid)
            self.add_activity(f"🚫 You kicked {uname}")

    def _on_error(self, msg):
        self.connection_status.setText(f"❌ {msg}")
        self.connection_status.setStyleSheet(f"color: {COLORS['accent_red']}; font-size: 10px; border: none;")
        # Clear uploading flag on error so user can try again
        if self._player:
            self._player._session_uploading = False

    def _show_disconnected(self, reason=""):
        self.connect_section.setVisible(True)
        self.session_section.setVisible(False)
        self.connection_status.setText(f"Disconnected: {reason}" if reason else "Disconnected")
        self.connection_status.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; border: none;")
        self.session_client = None
        self.shared_pool_cb.setChecked(False)
        # Update connection dot and reset shared pool
        if self._player:
            self._player._update_session_dot(False)
            self._player._session_shared_pool = False
            self._player._session_uploading = False

    def _on_upload_progress(self, sent, total):
        if total > 0:
            pct = int(sent / total * 100)
            self.progress_label.setText(f"⬆ Uploading: {pct}% ({sent // 1024}KB / {total // 1024}KB)")

    def _on_download_progress(self, recv, total):
        if total > 0:
            pct = int(recv / total * 100)
            self.progress_label.setText(f"⬇ Downloading: {pct}%")
        else:
            self.progress_label.setText(f"⬇ Downloading: {recv // 1024}KB")

    def _on_video_uploaded(self, video_id, filename, size, uploader):
        self.progress_label.setText(f"📤 {uploader} shared: {filename}")
        QTimer.singleShot(5000, lambda: self.progress_label.setText(""))

    def _on_video_ready(self, video_id, local_path):
        self.progress_label.setText("✅ Video ready")
        self.now_playing_label.setText(f"▶ {os.path.basename(local_path)}")

        # If this was a join-in-progress sync, play immediately with sync state
        pending_id = getattr(self, '_pending_sync_video_id', None)
        if pending_id == video_id:
            if self._player:
                self._player._play_session_video(video_id, local_path)
                sync_state = getattr(self, '_pending_sync_state', {})
                position = sync_state.get('position', 0.0)
                speed = sync_state.get('speed', 1.0)
                is_playing = sync_state.get('playing', False)
                def _apply_sync():
                    if not self._player or not self._player.player:
                        return
                    self._player._ignore_remote = True
                    if position > 0.01:
                        self._player.player.seek(position, reference='absolute')
                    if speed != 1.0:
                        self._player.player.speed = speed
                        self._player.slow_mo_btn.set_speed(speed)
                    if not is_playing:
                        self._player.player.pause = True
                        self._player.play_btn.setText("▶  Play")
                    self._player._ignore_remote = False
                    self.add_activity("🔄 Synced to position")
                QTimer.singleShot(500, _apply_sync)
            self._pending_sync_video_id = None
            self._pending_sync_state = {}
            QTimer.singleShot(3000, lambda: self.progress_label.setText(""))
            return

        # Ready-sync (non-host): load video, pause, report ready, wait for all_ready
        pending_prepare = getattr(self, '_pending_prepare_video_id', None)
        if pending_prepare == video_id:
            if self._player:
                self._player._load_session_video(local_path)
                QTimer.singleShot(200, lambda: self._pause_and_report_ready(video_id))
            self._pending_prepare_video_id = None
            QTimer.singleShot(3000, lambda: self.progress_label.setText(""))
            return

        # Host uploaded this clip — load, pause, wait for all_ready
        if self.session_client and self.session_client.is_connected:
            if self._player:
                self._player._load_session_video(local_path)
                QTimer.singleShot(200, lambda: self._host_wait_for_ready(video_id))
            QTimer.singleShot(3000, lambda: self.progress_label.setText(""))
            return

        # Fallback: not in a session, just play
        if self._player:
            self._player._play_session_video(video_id, local_path)
        QTimer.singleShot(3000, lambda: self.progress_label.setText(""))

    def _host_wait_for_ready(self, video_id):
        """Host uploaded a clip — pause and wait for all users to be ready."""
        if self._player and self._player.player:
            self._player._ignore_remote = True
            self._player.player.pause = True
            self._player.play_btn.setText("▶  Play")
            self._player._ignore_remote = False
        self.progress_label.setText("⏳ Waiting for everyone to download...")

    def _pause_and_report_ready(self, video_id):
        """Pause video and tell server we're ready."""
        if self._player and self._player.player:
            self._player._ignore_remote = True
            self._player.player.pause = True
            self._player.play_btn.setText("▶  Play")
            self._player._ignore_remote = False
        self.progress_label.setText("⏳ Waiting for everyone...")
        if self.session_client and self.session_client.is_connected:
            self.session_client.send_ready(video_id)

    def _on_prepare_video(self, video_id, filename, username):
        """Server says a new video is coming — download it and wait."""
        self._pending_prepare_video_id = video_id
        self.add_activity(f"🎬 {username} shared {filename}")
        self.now_playing_label.setText(f"▶ {filename}")
        self.progress_label.setText(f"⬇ Downloading from {username}...")

    def _on_all_ready(self, video_id):
        """Everyone is ready — start playback from the beginning."""
        self.add_activity("✅ All synced — playing!")
        self.progress_label.setText("▶ Playing!")
        QTimer.singleShot(2000, lambda: self.progress_label.setText(""))
        if self._player and self._player.player:
            self._player._session_uploading = False
            self._player._playing_remote_clip = True  # Don't re-share when this clip ends
            self._player._ignore_remote = True
            self._player.player.seek(0, reference='absolute')
            self._player.player.pause = False
            self._player.play_btn.setText("⏸  Pause")
            self._player._apply_current_speed()
            self._player._ignore_remote = False

    def _on_ready_progress(self, ready_count, total):
        """Show how many users are ready."""
        self.progress_label.setText(f"⏳ Syncing: {ready_count}/{total} ready")

    def _on_ping_result(self, latency_ms):
        """Update ping display with color-coded latency."""
        if latency_ms < 80:
            color = COLORS['accent_green']
            icon = "📶"
        elif latency_ms < 200:
            color = COLORS['accent_orange']
            icon = "📶"
        else:
            color = COLORS['accent_red']
            icon = "📶"
        self.ping_label.setText(f"{icon} Ping: {latency_ms}ms")
        self.ping_label.setStyleSheet(f"color: {color}; font-size: 10px; border: none;")

    def _on_shared_pool_toggled(self, checked):
        """Host toggled the shared random pool."""
        if self.session_client and self.session_client.is_connected:
            self.session_client.send_set_shared_pool(checked)
        if self._player:
            self._player._session_shared_pool = checked
        self.add_activity(f"🎲 Shared pool {'ON' if checked else 'OFF'}")

    def _on_shared_pool_changed(self, enabled, changed_by):
        """Another user (host) toggled the shared pool."""
        self.shared_pool_cb.blockSignals(True)
        self.shared_pool_cb.setChecked(enabled)
        self.shared_pool_cb.blockSignals(False)
        if self._player:
            self._player._session_shared_pool = enabled
        self.add_activity(f"🎲 {changed_by} {'enabled' if enabled else 'disabled'} shared pool")

    def cleanup(self):
        if self.session_client:
            self.session_client.cleanup()


# ============================================================================
# Main Application
# ============================================================================

class VideoPlayer(QMainWindow):
    """Main video player window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Random Clip Player v4.5")
        self.setGeometry(100, 100, 1100, 700)
        self.setMinimumSize(800, 550)
        
        # Initialize Configuration
        self.config_manager = ConfigManager()
        
        self.player = None
        self.player_signals = PlayerSignals()
        self._cached_duration = 0.0
        
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
        self._cached_fps = 0  # Cache FPS to avoid repeated property queries
        
        # Session (Watch Together) state
        self._session_active = False
        self._ignore_remote = False  # Prevent echo loops
        self._session_panel = None
        self._session_shared_pool = False  # Shared random pool mode
        self._playing_remote_clip = False  # True when current clip came from another user
        self._session_uploading = False    # True while uploading a clip to session
        
        # Setup UI (must come before MPV init so video_frame exists)
        self._setup_ui()
        self._create_menu_bar()
        self._apply_global_styles()

        # MPV instance and player — create AFTER UI is fully styled
        self.player = mpv.MPV(wid=int(self.video_frame.winId()), vo='gpu', hwdec='auto', keep_open=True)
        self._setup_mpv_callbacks()
        
        # Set initial volume
        self.player.volume = int(self._last_volume or 80)

        self._setup_keyboard_shortcuts()
        
        # Initial folder check
        if not self.clips_folder or not os.path.exists(self.clips_folder):
            self.video_label.setText("⚠  Please select a clips folder to begin")
            QTimer.singleShot(500, self.select_folder) # Delay slightly to let UI render
        else:
            self.scan_folder()
            self._update_status_bar()
        

        # Auto-hide timer for controls
        self.hide_controls_timer = QTimer(self)
        self.hide_controls_timer.setInterval(2000)  # 2 seconds
        self.hide_controls_timer.setSingleShot(True)
        self.hide_controls_timer.timeout.connect(self._hide_controls)
        
        # Enable mouse tracking for auto-hide
        self.setMouseTracking(True)
        cw = self.centralWidget()
        if cw:
            cw.setMouseTracking(True)

    def _create_menu_bar(self):
        """Create the application menu bar"""
        navbar = self.menuBar()
        assert navbar is not None
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
        assert file_menu is not None
        
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
        assert settings_menu is not None
        
        settings_action = QAction("Preferences...", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.show_settings_dialog)
        settings_menu.addAction(settings_action)
        
        # Session Menu (Watch Together)
        if SESSION_AVAILABLE:
            self._session_dot = "⚫"  # Disconnected
            self._session_menu_label = f"{self._session_dot} Session"
            session_menu = navbar.addMenu(self._session_menu_label)
            assert session_menu is not None
            self._session_menu = session_menu

            self.toggle_session_action = QAction("Toggle Session Panel", self)
            self.toggle_session_action.setShortcut("Ctrl+T")
            self.toggle_session_action.setCheckable(True)
            self.toggle_session_action.triggered.connect(self._toggle_session_panel)
            session_menu.addAction(self.toggle_session_action)

    def show_settings_dialog(self):
        """Show the settings dialog"""
        dialog = SettingsDialog(self.config_manager, self)
        if dialog.exec():
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
        if dialog.exec():
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
        
        # Top-level horizontal layout: [main content | session panel]
        top_layout = QHBoxLayout(central_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)
        
        # Main content container
        main_container = QWidget()
        main_layout = QVBoxLayout(main_container)
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
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        
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
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        self.time_slider = ClickableSlider(Qt.Orientation.Horizontal)
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
        self.autoplay_btn.setChecked(bool(self.autoplay_enabled))
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
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(self._last_volume or 80))
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
        self.clip_counter.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.clip_counter.setToolTip("Position / Total clips")
        volume_layout.addWidget(self.clip_counter)
        
        container_layout.addWidget(volume_widget)
        
        main_layout.addWidget(self.controls_container)
        
        # Add main content to top layout
        top_layout.addWidget(main_container, stretch=1)
        
        # Session panel (hidden by default)
        if SESSION_AVAILABLE:
            self._session_panel = SessionPanel(self.config_manager, self)
            self._session_panel.setVisible(False)
            top_layout.addWidget(self._session_panel)

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
            "Space": Qt.Key.Key_Space, "Return": Qt.Key.Key_Return, "Escape": Qt.Key.Key_Escape,
            "Backspace": Qt.Key.Key_Backspace, "Delete": Qt.Key.Key_Delete, "Tab": Qt.Key.Key_Tab,
            "Left": Qt.Key.Key_Left, "Right": Qt.Key.Key_Right, "Up": Qt.Key.Key_Up, "Down": Qt.Key.Key_Down,
            "Period": Qt.Key.Key_Period, "Comma": Qt.Key.Key_Comma,
            "Home": Qt.Key.Key_Home, "End": Qt.Key.Key_End, "PageUp": Qt.Key.Key_PageUp, "PageDown": Qt.Key.Key_PageDown,
        }
        # Add letter keys A-Z
        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            key_map[c] = getattr(Qt.Key, f"Key_{c}")
        # Add number keys 0-9
        for n in "0123456789":
            key_map[n] = getattr(Qt.Key, f"Key_{n}")
        # Add function keys F1-F12
        for i in range(1, 13):
            key_map[f"F{i}"] = getattr(Qt.Key, f"Key_F{i}")
        
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
        in_session = self._get_session_client() is not None

        # Disable like/dislike in session mode (remote clips can't be favorited)
        self.block_btn.setEnabled(has_video and not in_session)
        self.like_btn.setEnabled(has_video and not in_session)
        
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
        # Block if we're already uploading a clip to the session
        if self._session_uploading:
            self.status_label.setText("⏳ Upload in progress...")
            return

        self._playing_remote_clip = False

        client = self._get_session_client()
        if DEBUG_MODE:
            logging.getLogger("rdm").debug(f"play_random_clip: queue_len={len(self.play_queue)}, idx={self.queue_index}, shared_pool={self._session_shared_pool}, in_session={client is not None}")

        # In session with shared pool: ask server to pick a random user
        if client and self._session_shared_pool:
            client.send_request_random()
            self.status_label.setText("🎲 Requesting random clip from pool...")
            return

        if not self.play_queue:
            self._refresh_queue()
            if not self.play_queue:
                self.video_label.setText("⚠  No playable clips found (check blocked list)")
                self.video_label.setStyleSheet(f"color: {COLORS['accent_orange']}; font-size: 13px; padding: 6px 4px;")
                return

        # Advance index
        self.queue_index += 1
        if self.queue_index >= len(self.play_queue):
            self.video_label.setText("🔄  All clips played! Reshuffling...")
            random.shuffle(self.play_queue)
            self.queue_index = 0

        self.current_video = self.play_queue[self.queue_index]
        self._update_navigation_state()

        # In session mode: DON'T play locally — upload first, wait for all_ready
        if client:
            filename = os.path.basename(self.current_video)
            self.video_label.setText(f"⏳ Uploading: {filename}")
            self.video_label.setStyleSheet(f"color: {COLORS['accent_orange']}; font-size: 13px; padding: 6px 4px;")
            self.status_label.setText("⏳ Syncing with session...")
            self._session_auto_share()
            return

        # Not in session — play locally immediately
        self._play_video(self.current_video)

    def play_previous_clip(self):
        """Navigate to the previous clip in queue"""
        if self._session_uploading:
            self.status_label.setText("⏳ Upload in progress...")
            return
        self._playing_remote_clip = False
        if self.queue_index > 0:
            self.queue_index -= 1
            self.current_video = self.play_queue[self.queue_index]
            self._update_navigation_state()

            # In session mode: upload first, don't play locally
            client = self._get_session_client()
            if client:
                filename = os.path.basename(self.current_video)
                self.video_label.setText(f"⏳ Uploading: {filename}")
                self.status_label.setText("⏳ Syncing with session...")
                self._session_auto_share()
                return

            # Not in session — play locally
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
                logging.getLogger("rdm").warning(f"Explorer error: {e}")

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

    def _setup_mpv_callbacks(self):
        """Connect MPV property observers to Qt Signals to safely bridge threads"""
        if self.player is None:
            return
        player = self.player  # local ref for type narrowing
        # MPV runs these callbacks on its own background thread
        @player.property_observer('time-pos')
        def time_observer(_name, value):
            if value is not None:
                self.player_signals.time_updated.emit(value)
                
        @player.property_observer('duration')
        def duration_observer(_name, value):
            if value is not None:
                self.player_signals.duration_changed.emit(value)
                
        @player.property_observer('eof-reached')
        def eof_observer(_name, value):
            if value:
                self.player_signals.eof_reached.emit()
                
        @player.property_observer('pause')
        def pause_observer(_name, value):
            if value is not None:
                self.player_signals.playback_state_changed.emit(not value)
                
        # Connect Qt Signals to slots (this runs on the main thread)
        self.player_signals.time_updated.connect(self._on_mpv_time)
        self.player_signals.duration_changed.connect(self._on_mpv_duration)
        self.player_signals.eof_reached.connect(self._on_video_finished)
        self.player_signals.playback_state_changed.connect(self._on_mpv_pause_changed)

    def _on_mpv_time(self, current_time):
        if self._cached_duration > 0 and not self.is_slider_pressed:
            val = int((current_time / self._cached_duration) * 1000)
            self.time_slider.setValue(val)
        self.time_label.setText(self._format_time(int(current_time * 1000)))
        
    def _on_mpv_duration(self, duration):
        self._cached_duration = duration
        self.duration_label.setText(self._format_time(int(duration * 1000)))
        
    def _on_video_finished(self):
        if self.autoplay_enabled:
            # In a session, only the host triggers autoplay
            client = self._get_session_client()
            if client and not client.is_host:
                self.play_btn.setText("▶  Play")
                self.status_label.setText("⏳ Waiting for host...")
            else:
                QTimer.singleShot(50, self.play_random_clip)
        else:
            self.play_btn.setText("▶  Play")
            
    def _on_mpv_pause_changed(self, is_playing):
        if is_playing:
            self.play_btn.setText("⏸  Pause")
            self._apply_current_speed()
        else:
            self.play_btn.setText("▶  Play")

    def _play_video(self, filepath):
        """Play a specific video file"""
        if not self.player:
            return
        if DEBUG_MODE:
            logging.getLogger("rdm").debug(f"_play_video: {filepath}")
            
        self.player.play(filepath)
        
        # Cache FPS after a short delay
        QTimer.singleShot(200, self._cache_fps)
        
        # Update UI with truncated filename
        filename = os.path.basename(filepath)
        display_name = filename if len(filename) <= 65 else filename[:62] + "..."
        self.video_label.setText(f"▶  {display_name}")
        self.video_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px; padding: 6px 4px;")
        
        # Apply current playback rate from speed button
        self._apply_current_speed()

    def _toggle_play_pause(self):
        """Toggle between play and pause states"""
        if not self.player:
            return
        self.player.pause = not self.player.pause
        if not self.player.pause:
            self._session_send_play()
        else:
            self._session_send_pause()

    def _toggle_slow_motion(self):
        """Toggle between 0.5x and 1.0x speed"""
        if not self.player:
            return
        if self.slow_mo_btn.isChecked():
            self.slow_mo_btn.set_speed(0.5)
            self.player.speed = 0.5
        else:
            self.slow_mo_btn.set_speed(1.0)
            self.player.speed = 1.0

    def _toggle_slow_motion_keyboard(self):
        """Toggle slow motion via keyboard"""
        self.slow_mo_btn.setChecked(not self.slow_mo_btn.isChecked())
        self._toggle_slow_motion()
        
    def _set_playback_speed(self, speed):
        """Set playback speed from scroll wheel"""
        if not self.player:
            return
        self.player.speed = speed
        self.status_label.setText(f"Speed: {speed}x")
        QTimer.singleShot(1500, self._update_status_bar)
        self._session_send_speed(speed)
        
    def _apply_current_speed(self):
        """Apply the current speed setting from the button"""
        if not self.player:
            return
        speed = self.slow_mo_btn.current_speed
        self.player.speed = speed

    def _stop(self):
        """Stop playback completely"""
        if not self.player:
            return
        self.player.stop()
        self.play_btn.setText("▶  Play")
        self.time_slider.setValue(0)
        self.time_label.setText("0:00")
        self.video_label.setText("⏹  Stopped — Press Space to play next clip")
        self.video_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; padding: 6px 4px;")

    def _skip(self, ms):
        """Skip forward or backward by milliseconds"""
        if not self.player:
            return
        current = self.player.time_pos or 0.0
        duration = self.player.duration or 0.0
        new_time = max(0, min(duration, current + (ms / 1000.0)))
        self.player.seek(new_time, reference='absolute')

    def _cache_fps(self):
        """Cache the FPS of current video"""
        if not self.player:
            return
        fps = self.player.estimated_vf_fps or self.player.container_fps
        try:
            fps_val = float(fps) if fps else 0.0
            self._cached_fps = fps_val if fps_val > 0 else 0.0
        except (TypeError, ValueError):
            self._cached_fps = 0.0

    def _get_frame_duration_ms(self):
        """Get the duration of one frame in milliseconds based on cached fps"""
        if self._cached_fps > 0:
            return max(1, int(1000 / self._cached_fps))  # e.g., 60fps -> 16ms, 120fps -> 8ms
        return 33  # Default to ~30fps if unknown

    def _frame_step_forward(self):
        """Advance one frame forward"""
        if not self.player:
            return
        self.player.pause = True
        self.player.command('frame-step')
        fps = self._cached_fps or 30
        self.status_label.setText(f"⏭ +1 frame ({fps:.0f}fps)")
        QTimer.singleShot(1000, self._update_status_bar)

    def _frame_step_backward(self):
        """Step backward one frame"""
        if not self.player:
            return
        self.player.pause = True
        self.player.command('frame-back-step')
        fps = self._cached_fps or 30
        self.status_label.setText(f"⏮ -1 frame ({fps:.0f}fps)")
        QTimer.singleShot(1000, self._update_status_bar)

    def _set_position(self, position):
        """Set video position from slider"""
        if not self.player:
            return
        if self._cached_duration > 0:
            pos_sec = (position / 1000.0) * self._cached_duration
            self.player.seek(pos_sec, reference='absolute')
            self._session_send_seek(pos_sec)

    def _slider_pressed(self):
        """Handle slider press"""
        self.is_slider_pressed = True

    def _slider_released(self):
        """Handle slider release"""
        self.is_slider_pressed = False
        self._set_position(self.time_slider.value())

    def _set_volume(self, volume):
        """Set audio volume"""
        if self.player:
            self.player.volume = volume
        self.volume_label.setText(f"{volume}%")
        
        # Save volume preference (but don't persist 0 from muting)
        if volume > 0:
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
            self._unmute_volume = self.volume_slider.value()  # Remember for unmute only
            self.volume_slider.setValue(0)
        else:
            self.volume_slider.setValue(int(getattr(self, '_unmute_volume', None) or self._last_volume or 80))

    # ========================================================================
    # UI Updates
    # ========================================================================

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
            parent = self.video_frame.parent()
            if parent is None:
                return True
            video_global = parent.mapToParent(video_rect.topLeft())
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
            self.controls_container.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX — remove constraint
            
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

    # ========================================================================
    # Session (Watch Together) Integration
    # ========================================================================

    def _toggle_session_panel(self):
        """Show/hide the session panel."""
        if self._session_panel:
            visible = not self._session_panel.isVisible()
            self._session_panel.setVisible(visible)
            self._session_active = visible
            if hasattr(self, 'toggle_session_action'):
                self.toggle_session_action.setChecked(visible)

    def _session_auto_share(self):
        """Upload + share the current clip to the session."""
        client = self._get_session_client()
        if client and self.current_video and os.path.exists(self.current_video):
            self._session_uploading = True
            if DEBUG_MODE:
                logging.getLogger("rdm").debug(f"Auto-sharing: {self.current_video}")
            if self._session_panel:
                self._session_panel.progress_label.setText("⏳ Sharing clip...")
                self._session_panel.add_activity(f"📤 You shared {os.path.basename(self.current_video)}")
            client.upload_and_play(self.current_video)

    def _on_random_clip_requested(self):
        """Server picked us to provide a random clip for the shared pool."""
        if not self.play_queue:
            self._refresh_queue()
        if not self.play_queue:
            self.status_label.setText("⚠ No clips to share")
            return
        # Pick a random clip and share it (don't play locally — wait for all_ready)
        self.queue_index += 1
        if self.queue_index >= len(self.play_queue):
            random.shuffle(self.play_queue)
            self.queue_index = 0
        self.current_video = self.play_queue[self.queue_index]
        self._update_navigation_state()
        filename = os.path.basename(self.current_video)
        self.video_label.setText(f"⏳ Uploading: {filename}")
        self.status_label.setText("⏳ Syncing with session...")
        self._session_auto_share()

    def _update_session_dot(self, connected):
        """Update the session menu title with a green/grey dot."""
        if not hasattr(self, '_session_menu') or self._session_menu is None:
            return
        dot = "🟢" if connected else "⚫"
        self._session_menu.setTitle(f"{dot} Session")

    def _get_session_client(self):
        """Get the active session client, or None."""
        if self._session_panel and self._session_panel.session_client:
            client = self._session_panel.session_client
            if client.is_connected:
                return client
        return None

    def _session_send_play(self):
        """Notify the session that we pressed play."""
        if self._ignore_remote:
            return
        client = self._get_session_client()
        if client and self.player:
            pos = float(self.player.time_pos or 0.0)
            client.send_play(pos)

    def _session_send_pause(self):
        """Notify the session that we pressed pause."""
        if self._ignore_remote:
            return
        client = self._get_session_client()
        if client and self.player:
            pos = float(self.player.time_pos or 0.0)
            client.send_pause(pos)

    def _session_send_seek(self, position):
        """Notify the session that we seeked."""
        if self._ignore_remote:
            return
        client = self._get_session_client()
        if client:
            client.send_seek(position)

    def _session_send_speed(self, speed):
        """Notify the session of speed change."""
        if self._ignore_remote:
            return
        client = self._get_session_client()
        if client:
            client.send_speed(speed)

    # ---- Remote event handlers (called by SessionPanel signals) ----

    def _on_remote_play(self, position, username):
        """Another user pressed play."""
        if DEBUG_MODE:
            logging.getLogger("rdm").debug(f"Remote PLAY from {username} at pos={position:.4f}")
        if not self.player:
            return
        self._ignore_remote = True
        self.player.seek(position, reference='absolute')
        if self.player.pause:
            self.player.pause = False
            self.play_btn.setText("⏸  Pause")
            self._apply_current_speed()
        self.status_label.setText(f"▶ {username} pressed play")
        QTimer.singleShot(2000, self._update_status_bar)
        self._ignore_remote = False

    def _on_remote_pause(self, position, username):
        """Another user pressed pause."""
        if not self.player:
            return
        self._ignore_remote = True
        if not self.player.pause:
            self.player.pause = True
            self.play_btn.setText("▶  Play")
        self.player.seek(position, reference='absolute')
        self.status_label.setText(f"⏸ {username} paused")
        QTimer.singleShot(2000, self._update_status_bar)
        self._ignore_remote = False

    def _on_remote_seek(self, position, username):
        """Another user seeked."""
        if not self.player:
            return
        self._ignore_remote = True
        self.player.seek(position, reference='absolute')
        self.status_label.setText(f"⏩ {username} seeked")
        QTimer.singleShot(2000, self._update_status_bar)
        self._ignore_remote = False

    def _on_remote_speed(self, speed, username):
        """Another user changed speed."""
        if not self.player:
            return
        self._ignore_remote = True
        self.player.speed = speed
        self.slow_mo_btn.set_speed(speed)
        self.status_label.setText(f"Speed: {speed}x by {username}")
        QTimer.singleShot(2000, self._update_status_bar)
        self._ignore_remote = False

    def _on_remote_play_video(self, video_id, filename, username):
        """Another user wants to play a video — download it."""
        if DEBUG_MODE:
            logging.getLogger("rdm").debug(f"Remote PLAY_VIDEO from {username}: {filename} (id={video_id})")
        self.status_label.setText(f"📥 {username} is sharing: {filename}")
        client = self._get_session_client()
        if client:
            # Check if we already have it locally
            local = client.get_local_video_path(video_id)
            if local:
                self._play_session_video(video_id, local)
            # Otherwise download_video was already triggered by session_client

    def _play_session_video(self, video_id, local_path):
        """Play a session video that has been downloaded locally."""
        if os.path.exists(local_path):
            self._ignore_remote = True
            self._playing_remote_clip = True  # Don't re-share when this clip ends
            self.current_video = local_path
            self._play_video(local_path)
            self._ignore_remote = False

    def _load_session_video(self, local_path):
        """Load a session video into the player but don't start playback.
        Used for ready-sync: load the video, pause, then wait for all_ready."""
        if os.path.exists(local_path):
            self._ignore_remote = True
            self.current_video = local_path
            self._play_video(local_path)
            self._ignore_remote = False

    def closeEvent(self, event):
        """Clean up on window close"""
        self.hide_controls_timer.stop()
        if hasattr(self, '_controls_animation'):
            self._controls_animation.stop()
        # Clean up session
        if self._session_panel:
            self._session_panel.cleanup()
        if self.player:
            try:
                self.player.terminate()
            except:
                pass
        event.accept()


# ============================================================================
# Debug Mode
# ============================================================================

DEBUG_MODE = False

def _setup_debug():
    """Configure verbose logging and exception hooks for debug mode."""
    global DEBUG_MODE
    DEBUG_MODE = True

    # Verbose logging to console
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("rdm")
    log.info("Debug mode enabled")

    # Also crank up session_client logging
    logging.getLogger("rdm-session").setLevel(logging.DEBUG)

    # Global exception hook — print to console instead of silently crashing
    def _exception_hook(exc_type, exc_value, exc_tb):
        log.critical("Unhandled exception:", exc_info=(exc_type, exc_value, exc_tb))
        traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.excepthook = _exception_hook


# ============================================================================
# Application Entry Point
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Random Clip Player")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode (verbose logging, console output)")
    args = parser.parse_args()

    if args.debug:
        _setup_debug()

    # Note: High DPI scaling is always enabled in Qt6/PySide6
    app = QApplication(sys.argv)
    app.setApplicationName("Random Clip Player")
    app.setStyle('Fusion')
    
    # Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)
    
    player = VideoPlayer()

    # Debug overlay: show a small label in the title bar
    if DEBUG_MODE:
        player.setWindowTitle("Random Clip Player v4.5 [DEBUG]")
        if player.player is not None:
            try:
                logging.getLogger("rdm").info(f"MPV version: {player.player.mpv_version}")
            except Exception:
                pass
        logging.getLogger("rdm").info(f"Python: {sys.version}")
        logging.getLogger("rdm").info(f"Session module: {'available' if SESSION_AVAILABLE else 'NOT available'}")

    player.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
