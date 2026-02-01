"""
Random Clip Player - A polished video clip player with random playback
Version 2.2 - Shuffle Queue & Autoplay
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
    QFileDialog, QAction, QMessageBox, QDialog, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence, QIcon

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
            "autoplay": False
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

# ============================================================================
# Custom Widgets
# ============================================================================

class ClickableSlider(QSlider):
    """Custom slider that responds to clicks anywhere on the track"""
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            val = self.minimum() + ((self.maximum() - self.minimum()) * event.x()) / self.width()
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


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
        self.setWindowTitle("Random Clip Player v2.1")
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
        self.play_queue = [] # Shuffled list of clips
        self.queue_index = -1 # Current position in shuffled list
        
        # UI state
        self.is_slider_pressed = False
        self._last_volume = self.config_manager.get("volume")
        
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
        
        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

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
        # Main Controls Row
        # ==========================================
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)
        controls_layout.setContentsMargins(0, 4, 0, 0)
        
        # Previous clip
        self.prev_clip_btn = StyledButton("⏮ Prev", 'secondary')
        self.prev_clip_btn.setMinimumSize(75, 36)
        self.prev_clip_btn.clicked.connect(self.play_previous_clip)
        self.prev_clip_btn.setEnabled(False)
        self.prev_clip_btn.setToolTip("Previous (Backspace)")
        controls_layout.addWidget(self.prev_clip_btn, stretch=1)
        
        # Skip back
        self.skip_back_btn = StyledButton("−10s")
        self.skip_back_btn.setMinimumSize(50, 36)
        self.skip_back_btn.clicked.connect(lambda: self._skip(-10000))
        self.skip_back_btn.setToolTip("Skip back (←)")
        controls_layout.addWidget(self.skip_back_btn, stretch=1)
        
        # Play/Pause
        self.play_btn = StyledButton("▶ Play")
        self.play_btn.setMinimumSize(80, 36)
        self.play_btn.clicked.connect(self._toggle_play_pause)
        self.play_btn.setToolTip("Play/Pause (P)")
        controls_layout.addWidget(self.play_btn, stretch=1)
        
        # Skip forward
        self.skip_fwd_btn = StyledButton("+10s")
        self.skip_fwd_btn.setMinimumSize(50, 36)
        self.skip_fwd_btn.clicked.connect(lambda: self._skip(10000))
        self.skip_fwd_btn.setToolTip("Skip forward (→)")
        controls_layout.addWidget(self.skip_fwd_btn, stretch=1)
        
        controls_layout.addSpacing(8)
        
        # ★ RANDOM CLIP - PRIMARY ACTION ★
        self.random_btn = StyledButton("🎲 Random Clip", 'primary')
        self.random_btn.setMinimumSize(130, 40)
        self.random_btn.clicked.connect(self.play_random_clip)
        self.random_btn.setToolTip("Next random clip (Space)")
        controls_layout.addWidget(self.random_btn, stretch=3)
        
        controls_layout.addSpacing(8)
        
        # Like/Dislike
        self.like_btn = StyledButton("👍")
        self.like_btn.setMinimumSize(40, 36)
        self.like_btn.clicked.connect(self.toggle_like)
        self.like_btn.setToolTip("Like (L)")
        self.like_btn.setEnabled(False)
        controls_layout.addWidget(self.like_btn, stretch=1)
        
        self.block_btn = StyledButton("👎")
        self.block_btn.setMinimumSize(40, 36)
        self.block_btn.clicked.connect(self.block_current_clip)
        self.block_btn.setToolTip("Dislike & Block (Del)")
        self.block_btn.setEnabled(False)
        controls_layout.addWidget(self.block_btn, stretch=1)
        
        controls_layout.addSpacing(8)
        
        # Settings toggles
        self.autoplay_btn = StyledButton("Auto", 'toggle')
        self.autoplay_btn.setMinimumSize(50, 36)
        self.autoplay_btn.setCheckable(True)
        self.autoplay_btn.setChecked(self.autoplay_enabled)
        self.autoplay_btn.clicked.connect(self.toggle_autoplay)
        self.autoplay_btn.setToolTip("Autoplay (A)")
        controls_layout.addWidget(self.autoplay_btn, stretch=1)
        
        self.slow_mo_btn = StyledButton("0.5x", 'toggle')
        self.slow_mo_btn.setMinimumSize(45, 36)
        self.slow_mo_btn.setCheckable(True)
        self.slow_mo_btn.clicked.connect(self._toggle_slow_motion)
        self.slow_mo_btn.setToolTip("Slow motion (S)")
        controls_layout.addWidget(self.slow_mo_btn, stretch=1)
        
        controls_layout.addSpacing(8)
        
        # Volume
        self.volume_icon = QLabel("🔊")
        self.volume_icon.setFixedWidth(16)
        controls_layout.addWidget(self.volume_icon)
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self._last_volume)
        self.volume_slider.setMinimumWidth(50)
        self.volume_slider.setMaximumWidth(80)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.volume_slider.setToolTip("Volume (↑/↓)")
        controls_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel(f"{self._last_volume}%")
        self.volume_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        self.volume_label.setFixedWidth(30)
        controls_layout.addWidget(self.volume_label)
        
        # Clip Counter
        self.clip_counter = QLabel("0 / 0")
        self.clip_counter.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 11px; font-weight: bold;")
        self.clip_counter.setMinimumWidth(70)
        self.clip_counter.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.clip_counter.setToolTip("Position / Total clips")
        controls_layout.addWidget(self.clip_counter)
        
        main_layout.addLayout(controls_layout)
        
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
        """Configure keyboard shortcuts"""
        shortcuts = [
            (Qt.Key_Space, self.play_random_clip),
            (Qt.Key_P, self._toggle_play_pause),
            (Qt.Key_S, self._toggle_slow_motion_keyboard),
            (Qt.Key_Left, lambda: self._skip(-10000)),
            (Qt.Key_Right, lambda: self._skip(10000)),
            (Qt.Key_Backspace, self.play_previous_clip),
            (Qt.Key_Up, lambda: self.volume_slider.setValue(min(100, self.volume_slider.value() + 5))),
            (Qt.Key_Down, lambda: self.volume_slider.setValue(max(0, self.volume_slider.value() - 5))),
            (Qt.Key_M, self._toggle_mute),
            (Qt.Key_Escape, self._stop),
            (Qt.Key_R, self._reset_cycle),
            (Qt.Key_Delete, self.block_current_clip),
            (Qt.Key_L, self.toggle_like),
            (Qt.Key_E, self.open_current_in_explorer),
            (Qt.Key_A, self.toggle_autoplay),
        ]
        
        for key, callback in shortcuts:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)

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
        
        # Update UI with truncated filename
        filename = os.path.basename(filepath)
        display_name = filename if len(filename) <= 65 else filename[:62] + "..."
        self.video_label.setText(f"▶  {display_name}")
        self.video_label.setStyleSheet(f"color: {COLORS['text_primary']}; font-size: 13px; padding: 6px 4px;")
        self.play_btn.setText("⏸  Pause")
        
        # Apply current playback rate
        rate = 0.5 if self.slow_mo_btn.isChecked() else 1.0
        self.player.set_rate(rate)

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
            if self.slow_mo_btn.isChecked():
                self.player.set_rate(0.5)

    def _toggle_slow_motion(self):
        """Toggle slow motion playback"""
        if self.slow_mo_btn.isChecked():
            self.player.set_rate(0.5)
            self.slow_mo_btn.setText("🐢 0.5x")
        else:
            self.player.set_rate(1.0)
            self.slow_mo_btn.setText("🐢 1.0x")

    def _toggle_slow_motion_keyboard(self):
        """Toggle slow motion via keyboard"""
        self.slow_mo_btn.setChecked(not self.slow_mo_btn.isChecked())
        self._toggle_slow_motion()

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

    def closeEvent(self, event):
        """Clean up on window close"""
        self.player.stop()
        self.timer.stop()
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
