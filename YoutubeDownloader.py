import os
import sys
import subprocess
import multiprocessing
import threading
import re
from pathlib import Path

import yt_dlp

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTextEdit,
    QApplication,
    QFileDialog,
    QSpinBox,
    QLabel,
    QHBoxLayout,
)

from plyer import notification

# Dark theme style
DARK_THEME = """
    QWidget {
        background-color: #111111;
        color: #ffffff;
    }
    QListWidget {
        background-color: #1a1a1a;
        border: 2px solid #2281c9;
        border-radius: 5px;
        font-size: 24px;
        outline: none;
    }
    QListWidget::item {
        height: 40px;
        padding: 8px;
        border: none;
        margin: 2px;
    }
    QListWidget::item:selected {
        background-color: #1c5785;
        color: white;
        border: none;
        outline: none;
        border-radius: 5px;
    }
    QPushButton {
        background-color: #1c5785;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 14px;
    }
    QPushButton:hover {
        background-color: #1a6aa3;
    }
    QScrollBar:vertical {
        background: #1a1a1a;
        width: 12px;
        border: none;
    }
    QScrollBar::handle:vertical {
        background: #2281c9;
        min-height: 20px;
        border-radius: 6px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        background: none;
        border: none;
    }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
        background: transparent;
    }
    QLineEdit, QComboBox, QTextEdit, QPushButton, QSpinBox {
        background-color: #1a1a1a;
        color: #ffffff;
        border: 2px solid #2281c9;
        border-radius: 5px;
        font-size: 16px;
        padding: 8px;
    }
    QPushButton {
        background-color: #1c5785;
        border: none;
        padding: 8px 16px;
    }
    QPushButton:hover {
        background-color: #1a6aa3;
    }
    QTextEdit {
        border: 2px solid #2281c9;
        border-radius: 5px;
    }
"""


def get_music_folder():
    return os.path.join(Path.home(), "Music")


def get_download_folder():
    return os.path.join(Path.home(), "Downloads")


def sanitize_filename(name):
    # Remove characters that are unsafe for filenames.
    return re.sub(r'[\\/*?:"<>|]', "", name)


def download_video(args):
    """
    Downloads a video's audio stream using yt-dlp.
    Args should be a tuple of (video_url, fmt, output_path, idx, total)
    """
    video_url, fmt, output_path, idx, total = args
    
    try:
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': fmt,
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }
        
        # Get info first to check if file exists
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(video_url, download=False)
            title = info.get('title', 'video')
            sanitized_title = sanitize_filename(title)
            target_file = os.path.join(output_path, f"{sanitized_title}.{fmt}")
            
            if os.path.exists(target_file):
                return f"Skipped {title} {idx}/{total}"
            
            # Download the video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
                
            return f"Downloaded {title} {idx}/{total}"
    except Exception as e:
        return f"Error processing {video_url} ({idx}/{total}): {e}"


def get_playlist_videos(playlist_url):
    """
    Gets all video URLs from a playlist.
    """
    try:
        # Configure yt-dlp options for playlist extraction
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # Don't download videos, just get info
            'ignoreerrors': True,  # Skip unavailable videos
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
            
            if 'entries' not in playlist_info:
                return [], ""
            
            videos = []
            for entry in playlist_info['entries']:
                if entry:
                    videos.append(f"https://www.youtube.com/watch?v={entry['id']}")
            
            playlist_title = playlist_info.get('title', 'YouTube Playlist')
            return videos, playlist_title
    except Exception as e:
        return [], ""


class DownloaderWidget(QWidget):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str, int)

    def __init__(self):
        super().__init__()
        self.selected_directory = get_download_folder()
        self.init_ui()
        self.log_signal.connect(self.append_log)
        self.finished_signal.connect(self.on_finished)

    def init_ui(self):
        layout = QVBoxLayout()

        # Input for the playlist URL.
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter playlist URL")
        layout.addWidget(self.url_input)

        # Format and processes selection
        format_layout = QHBoxLayout()
        
        # Combo box to select desired format.
        format_label = QLabel("Format:")
        self.format_combo = QComboBox()
        self.format_combo.addItems(["mp3", "wav", "m4a", "opus"])
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        
        # Number of processes to use
        processes_label = QLabel("Processes:")
        self.processes_spin = QSpinBox()
        self.processes_spin.setRange(1, multiprocessing.cpu_count())
        self.processes_spin.setValue(min(8, multiprocessing.cpu_count()))
        format_layout.addWidget(processes_label)
        format_layout.addWidget(self.processes_spin)
        
        layout.addLayout(format_layout)

        # Directory display and Browse button.
        dir_layout = QHBoxLayout()
        self.destination_input = QLineEdit()
        self.destination_input.setPlaceholderText("Choose destination folder")
        self.destination_input.setText(self.selected_directory)
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.choose_destination)
        dir_layout.addWidget(self.destination_input)
        dir_layout.addWidget(self.browse_button)
        layout.addLayout(dir_layout)

        # Button to start the download.
        self.download_button = QPushButton("Download Playlist")
        self.download_button.clicked.connect(self.start_download)
        layout.addWidget(self.download_button)

        # Text area to display log messages.
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        self.setLayout(layout)

    def choose_destination(self):
        # Open a dialog to choose a directory. Defaults to the Music folder.
        directory = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", get_music_folder()
        )
        if directory:
            self.destination_input.setText(directory)
            self.selected_directory = directory

    def append_log(self, message):
        self.log_text.append(message)
        # Auto-scroll to the bottom
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.End)
        self.log_text.setTextCursor(cursor)

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self.append_log("Please enter a valid URL.")
            return

        fmt = self.format_combo.currentText().lower()
        processes = self.processes_spin.value()

        # Disable the download button while downloading.
        self.download_button.setEnabled(False)
        self.append_log("Starting download...")

        # Use the user-selected directory.
        dir_path = self.destination_input.text()
        
        # Ensure directory exists
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)

        # Start the download in a background thread.
        thread = threading.Thread(
            target=self.download_thread, args=(url, fmt, dir_path, processes)
        )
        thread.daemon = True
        thread.start()

    def download_thread(self, url, fmt, dir_path, processes):
        # Get videos from playlist
        self.log_signal.emit("Loading playlist...")
        videos, playlist_title = get_playlist_videos(url)
        
        if not videos:
            self.log_signal.emit("No videos found in playlist.")
            self.finished_signal.emit("", 0)
            return
        
        total = len(videos)
        self.log_signal.emit(f"Found {total} videos in playlist: {playlist_title}")
        
        # Prepare arguments for multiprocessing
        args_list = [
            (video_url, fmt, dir_path, idx, total)
            for idx, video_url in enumerate(videos, start=1)
        ]
        
        # Use multiprocessing to download videos
        self.log_signal.emit(f"Starting download with {processes} processes...")
        
        with multiprocessing.Pool(processes=processes) as pool:
            # Process results as they arrive
            for result in pool.imap_unordered(download_video, args_list):
                self.log_signal.emit(result)
        
        self.log_signal.emit("Download thread finished.")
        self.finished_signal.emit(playlist_title, total)

    def on_finished(self, playlist_title, total_videos):
        self.download_button.setEnabled(True)
        if playlist_title and total_videos > 0:
            notification.notify(
                title="Download Complete",
                message=f"The playlist '{playlist_title}' with {total_videos} videos was successfully downloaded.",
                timeout=20,  # Duration in seconds
            )
        else:
            notification.notify(
                title="Download Failed",
                message="Failed to download playlist. Check log for details.",
                timeout=20,
            )


def main():
    # Required for multiprocessing to work properly on Windows
    if sys.platform.startswith('win'):
        multiprocessing.freeze_support()
    
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)

    window = DownloaderWidget()
    window.setWindowTitle("YouTube Playlist Downloader")
    window.resize(600, 400)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()