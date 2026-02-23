import re

filepath = r"d:\Hobbies\RDM\random_clip_player.py"
with open(filepath, "r", encoding="utf-8") as f:
    text = f.read()

# Replace VLC instance creation with MPV
# Old: 
# self.vlc_instance = vlc.Instance('--no-xlib', '--quiet')
# self.player = self.vlc_instance.media_player_new()
pattern_vlc_init = r"self\.vlc_instance\s*=\s*vlc\.Instance\('.*?'\)\s*\n\s*self\.player\s*=\s*self\.vlc_instance\.media_player_new\(\)"
text = re.sub(pattern_vlc_init, r"self.player = mpv.MPV(wid=int(self.video_frame.winId()), vo='gpu', hwdec='auto', keep_open=True)\n        self.player_signals = PlayerSignals()\n        self._setup_mpv_callbacks()", text)

# Old set_hwnd:
# if sys.platform == "win32":
#     self.player.set_hwnd(self.video_frame.winId())
# ...
pattern_hwnd = r"if sys\.platform == \"win32\":\s*\n\s*self\.player\.set_hwnd\(self\.video_frame\.winId\(\)\)\s*\n\s*elif sys\.platform == \"darwin\":\s*\n\s*self\.player\.set_nsobject\(int\(self\.video_frame\.winId\(\)\)\)\s*\n\s*else:\s*\n\s*self\.player\.set_xwindow\(self\.video_frame\.winId\(\)\)"
text = re.sub(pattern_hwnd, r"# HWND bindings are handled in mpv.MPV(wid=...)", text)

# Play video
# Old:
# media = self.vlc_instance.media_new(filepath)
# self.player.set_media(media)
# self.player.play()
pattern_play = r"media\s*=\s*self\.vlc_instance\.media_new\(filepath\)\s*\n\s*self\.player\.set_media\(media\)\s*\n\s*self\.player\.play\(\)"
text = re.sub(pattern_play, r"self.player.play(filepath)\n        self.player.pause = False", text)

# Stop
# Old:
# self.player.stop()
pattern_stop = r"self\.player\.stop\(\)"
text = re.sub(pattern_stop, r"self.player.command('stop')", text)


# Speed
# Old:
# self.player.set_rate(speed)
pattern_speed = r"self\.player\.set_rate\((.*?)\)"
text = re.sub(pattern_speed, r"self.player.speed = \1", text)

# Getting Speed
# self.player.get_rate()
pattern_get_speed = r"self\.player\.get_rate\(\)"
text = re.sub(pattern_get_speed, r"getattr(self.player, 'speed', 1.0)", text)

# Volume
# Old:
# self.player.audio_set_volume(int)
pattern_volume = r"self\.player\.audio_set_volume\((.*?)\)"
text = re.sub(pattern_volume, r"self.player.volume = \1", text)


with open(filepath, "w", encoding="utf-8") as f:
    f.write(text)

print("Migration script completed.")
