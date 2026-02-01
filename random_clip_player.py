"""
Random Clip Player - A polished video clip player with random playback
Version 2.0 - Production Ready
"""

import sys
import os
import random
import ctypes
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QSlider, QLabel, QFrame, QSizePolicy, QShortcut
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QKeySequence

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
        self.setWindowTitle("Random Clip Player")
        self.setGeometry(100, 100, 1100, 700)
        self.setMinimumSize(800, 550)
        
        # VLC instance and player
        self.instance = vlc.Instance('--no-xlib')
        self.player = self.instance.media_player_new()
        
        # Folder path for clips
        self.clips_folder = r"C:\Medal\Clips\Tom Clancys Rainbow Six Siege"
        self.video_files = []
        self.current_video = ""
        
        # History tracking for clip navigation
        self.clip_history = []
        self.history_index = -1
        self.played_clips = set()
        
        # UI state
        self.is_slider_pressed = False
        self._last_volume = 80
        
        # Setup UI
        self._setup_ui()
        self._apply_global_styles()
        self._setup_keyboard_shortcuts()
        
        # Scan folder and update UI
        self.scan_folder()
        self._update_status_bar()
        
        # Timer for updating slider and time (smoother at 20fps)
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._update_playback_ui)

    def _setup_ui(self):
        """Initialize all UI components"""
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)
        
        # Video container with subtle border
        video_container = QFrame()
        video_container.setStyleSheet(f"""
            QFrame {{
                background-color: #000000;
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(2, 2, 2, 2)
        
        self.video_frame = QFrame()
        self.video_frame.setStyleSheet("background-color: #000000; border-radius: 10px;")
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        video_layout.addWidget(self.video_frame)
        
        main_layout.addWidget(video_container, stretch=1)
        
        # Info bar
        info_layout = QHBoxLayout()
        info_layout.setContentsMargins(4, 0, 4, 0)
        
        self.video_label = QLabel("Ready — Press Space or click Random Clip to start")
        self.video_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 13px;
            padding: 6px 4px;
        """)
        
        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 12px;
            padding: 6px 4px;
        """)
        self.status_label.setAlignment(Qt.AlignRight)
        
        info_layout.addWidget(self.video_label, stretch=1)
        info_layout.addWidget(self.status_label)
        main_layout.addLayout(info_layout)
        
        # Progress bar section
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(14)
        
        self.time_label = QLabel("0:00")
        self.time_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 13px;
            font-weight: 500;
            font-family: 'Consolas', 'SF Mono', monospace;
        """)
        self.time_label.setMinimumWidth(50)
        self.time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        
        self.time_slider = ClickableSlider(Qt.Horizontal)
        self.time_slider.setRange(0, 1000)
        self.time_slider.sliderMoved.connect(self._set_position)
        self.time_slider.sliderPressed.connect(self._slider_pressed)
        self.time_slider.sliderReleased.connect(self._slider_released)
        
        self.duration_label = QLabel("0:00")
        self.duration_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 13px;
            font-family: 'Consolas', 'SF Mono', monospace;
        """)
        self.duration_label.setMinimumWidth(50)
        
        progress_layout.addWidget(self.time_label)
        progress_layout.addWidget(self.time_slider, stretch=1)
        progress_layout.addWidget(self.duration_label)
        main_layout.addLayout(progress_layout)
        
        # Main controls row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)
        
        # Previous clip button
        self.prev_clip_btn = StyledButton("⏮  Previous", 'secondary')
        self.prev_clip_btn.clicked.connect(self.play_previous_clip)
        self.prev_clip_btn.setEnabled(False)
        self.prev_clip_btn.setToolTip("Previous clip (Backspace)")
        controls_layout.addWidget(self.prev_clip_btn)
        
        # Main random button
        self.random_btn = StyledButton("🎲  Random Clip", 'primary')
        self.random_btn.clicked.connect(self.play_random_clip)
        self.random_btn.setToolTip("Play random clip (Space)")
        self.random_btn.setMinimumWidth(180)
        controls_layout.addWidget(self.random_btn, stretch=2)
        
        controls_layout.addSpacing(12)
        
        # Playback controls
        self.skip_back_btn = StyledButton("⏪ 10s")
        self.skip_back_btn.clicked.connect(lambda: self._skip(-10000))
        self.skip_back_btn.setToolTip("Skip back 10s (←)")
        controls_layout.addWidget(self.skip_back_btn)
        
        self.play_btn = StyledButton("▶  Play")
        self.play_btn.clicked.connect(self._toggle_play_pause)
        self.play_btn.setToolTip("Play/Pause (P)")
        self.play_btn.setMinimumWidth(100)
        controls_layout.addWidget(self.play_btn)
        
        self.skip_fwd_btn = StyledButton("10s ⏩")
        self.skip_fwd_btn.clicked.connect(lambda: self._skip(10000))
        self.skip_fwd_btn.setToolTip("Skip forward 10s (→)")
        controls_layout.addWidget(self.skip_fwd_btn)
        
        controls_layout.addSpacing(12)
        
        # Speed toggle
        self.slow_mo_btn = StyledButton("🐢 0.5x", 'toggle')
        self.slow_mo_btn.setCheckable(True)
        self.slow_mo_btn.clicked.connect(self._toggle_slow_motion)
        self.slow_mo_btn.setToolTip("Slow motion (S)")
        controls_layout.addWidget(self.slow_mo_btn)
        
        # Volume section
        volume_widget = QWidget()
        volume_layout = QHBoxLayout(volume_widget)
        volume_layout.setContentsMargins(12, 0, 0, 0)
        volume_layout.setSpacing(8)
        
        self.volume_icon = QLabel("🔊")
        self.volume_icon.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 16px;")
        
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(80)
        self.volume_slider.setFixedWidth(90)
        self.volume_slider.valueChanged.connect(self._set_volume)
        self.volume_slider.setToolTip("Volume (↑/↓)")
        
        self.volume_label = QLabel("80%")
        self.volume_label.setStyleSheet(f"""
            color: {COLORS['text_muted']};
            font-size: 12px;
            min-width: 36px;
        """)
        
        volume_layout.addWidget(self.volume_icon)
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_label)
        controls_layout.addWidget(volume_widget)
        
        # Clip counter badge
        counter_frame = QFrame()
        counter_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_light']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        counter_layout = QHBoxLayout(counter_frame)
        counter_layout.setContentsMargins(12, 6, 12, 6)
        
        self.clip_counter = QLabel("0 / 0")
        self.clip_counter.setStyleSheet(f"""
            color: {COLORS['accent_green']};
            font-size: 14px;
            font-weight: 700;
        """)
        self.clip_counter.setAlignment(Qt.AlignCenter)
        self.clip_counter.setToolTip("Clips played / Total clips")
        counter_layout.addWidget(self.clip_counter)
        
        controls_layout.addWidget(counter_frame)
        
        main_layout.addLayout(controls_layout)
        
        # Set initial volume
        self.player.audio_set_volume(80)

    def _apply_global_styles(self):
        """Apply global application styles"""
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['bg_dark']};
            }}
            QWidget {{
                background-color: transparent;
                color: {COLORS['text_primary']};
                font-family: 'Segoe UI', 'SF Pro Display', -apple-system, sans-serif;
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
                height: 8px;
                background: {COLORS['bg_light']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {COLORS['text_primary']};
                border: none;
                width: 16px;
                height: 16px;
                margin: -4px 0;
                border-radius: 8px;
            }}
            QSlider::handle:horizontal:hover {{
                background: {COLORS['accent_green']};
                transform: scale(1.1);
            }}
            QSlider::sub-page:horizontal {{
                background: {COLORS['accent_green']};
                border-radius: 4px;
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
        
        count = len(self.video_files)
        self.video_label.setText(f"📁  Found {count:,} clips — Ready to play")
        self.video_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px; padding: 6px 4px;")
        self._update_clip_counter()

    def play_random_clip(self):
        """Play a random clip that hasn't been played yet"""
        if not self.video_files:
            self.video_label.setText("⚠  No video files found in folder")
            self.video_label.setStyleSheet(f"color: {COLORS['accent_red']}; font-size: 13px; padding: 6px 4px;")
            return
        
        # Get available clips (not yet played)
        available_clips = [f for f in self.video_files if f not in self.played_clips]
        
        # Reset if all clips have been played
        if not available_clips:
            self.played_clips.clear()
            available_clips = self.video_files.copy()
            self.video_label.setText("🔄  All clips played! Starting fresh cycle...")
        
        # Select random clip
        self.current_video = random.choice(available_clips)
        self.played_clips.add(self.current_video)
        
        # Manage history - truncate if navigating back
        if self.history_index >= 0 and self.history_index < len(self.clip_history) - 1:
            self.clip_history = self.clip_history[:self.history_index + 1]
        
        self.clip_history.append(self.current_video)
        self.history_index = len(self.clip_history) - 1
        
        self._update_navigation_state()
        self._play_video(self.current_video)

    def play_previous_clip(self):
        """Navigate to the previous clip in history"""
        if self.history_index > 0:
            self.history_index -= 1
            self.current_video = self.clip_history[self.history_index]
            self._update_navigation_state()
            self._play_video(self.current_video)

    def _reset_cycle(self):
        """Reset the played clips to start fresh"""
        self.played_clips.clear()
        self.video_label.setText("🔄  Cycle reset — All clips available again")
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
            self.timer.stop()
            self.play_btn.setText("▶  Play")

    def _update_navigation_state(self):
        """Update navigation buttons and related UI"""
        self.prev_clip_btn.setEnabled(self.history_index > 0)
        self._update_clip_counter()
        self._update_status_bar()

    def _update_clip_counter(self):
        """Update the clip counter display"""
        played = len(self.played_clips)
        total = len(self.video_files)
        self.clip_counter.setText(f"{played} / {total}")

    def _update_status_bar(self):
        """Update the status bar with current state info"""
        remaining = len(self.video_files) - len(self.played_clips)
        
        parts = [f"{remaining:,} remaining"]
        
        if self.history_index >= 0 and len(self.clip_history) > 1:
            parts.append(f"History {self.history_index + 1}/{len(self.clip_history)}")
        
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
