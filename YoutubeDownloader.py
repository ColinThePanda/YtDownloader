import os
import sys
import subprocess
import concurrent.futures
import glob
import re
import threading
from pathlib import Path

from pytubefix import Playlist
from pytubefix.cli import on_progress

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QComboBox, QPushButton, QTextEdit, QApplication, QFileDialog
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
    QLineEdit, QComboBox, QTextEdit, QPushButton {
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

def download_and_convert(video, fmt, idx, total, log_callback, dir_path):
    """
    Downloads and converts a video's audio stream.
    Logs messages with the video title and its position (idx/total).
    """
    try:
        target_file = os.path.join(dir_path, f"{sanitize_filename(video.title)}.{fmt}")
        if os.path.exists(target_file):
            log_callback(f"skipped {video.title} {idx}/{total}")
            return
        else:
            log_callback(f"Downloading {video.title} {idx}/{total}")
            audio_stream = video.streams.get_audio_only()
            downloaded_file = audio_stream.download(output_path=dir_path)
            # Use ffmpeg to convert the downloaded file to the desired format.
            command = ["ffmpeg", "-y", "-i", downloaded_file, target_file]
            subprocess.run(command, check=True)
            # Remove the original temporary file.
            os.remove(downloaded_file)
            log_callback(f"Downloaded {video.title} {idx}/{total}")
    except Exception as e:
        log_callback(f"Error processing {video.watch_url} ({idx}/{total}): {e}")

def download_playlist(url, fmt, log_callback, dir_path):
    print("Downloading playlist...")
    print(dir_path)
    # Ensure the destination directory exists.
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    else:
        # Delete all m4a files in the destination directory.
        for file in glob.glob(os.path.join(dir_path, "*.m4a")):
            try:
                os.remove(file)
                log_callback(f"Deleted temporary file: {file}")
            except Exception as e:
                log_callback(f"Error deleting {file}: {e}")

    log_callback("Loading playlist...")
    try:
        global pl 
        pl = Playlist(url, use_oauth=True)
        videos = pl.videos
        total = len(videos)
        log_callback(f"Found {total} videos in the playlist.")
    except Exception as e:
        log_callback(f"Error loading playlist: {e}")
        return

    # Process each video concurrently.
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(download_and_convert, video, fmt, idx, total, log_callback, dir_path)
            for idx, video in enumerate(videos, start=1)
        ]
        concurrent.futures.wait(futures)
    log_callback("Download and conversion complete.")

class DownloaderWidget(QWidget):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

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
        
        # Combo box to select desired format.
        self.format_combo = QComboBox()
        self.format_combo.addItems(["wav", "mp3"])
        layout.addWidget(self.format_combo)
        
        # Directory display and Browse button.
        self.destination_input = QLineEdit()
        self.destination_input.setPlaceholderText("Choose destination folder")
        self.destination_input.setText(self.selected_directory)
        layout.addWidget(self.destination_input)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.choose_destination)
        layout.addWidget(self.browse_button)
        
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
        directory = QFileDialog.getExistingDirectory(self, "Select Download Folder", get_music_folder())
        if directory:
            self.destination_input.setText(directory)
            self.selected_directory = directory

    def append_log(self, message):
        self.log_text.append(message)
    
    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            self.append_log("Please enter a valid URL.")
            return

        fmt = self.format_combo.currentText().lower()
        if fmt not in ["mp3", "wav"]:
            self.append_log("Invalid format selected. Defaulting to mp3.")
            fmt = "mp3"
        
        # Disable the download button while downloading.
        self.download_button.setEnabled(False)
        self.append_log("Starting download...")

        # Use the user-selected directory.
        dir_path = self.destination_input.text()
        
        # Start the download in a background thread.
        thread = threading.Thread(target=self.download_thread, args=(url, fmt, dir_path))
        thread.start()
    
    def download_thread(self, url, fmt, dir_path):
        def log_callback(msg):
            self.log_signal.emit(msg)
        download_playlist(url, fmt, log_callback, dir_path)
        self.log_signal.emit("Download thread finished.")
        self.finished_signal.emit()
    
    def on_finished(self):
        self.download_button.setEnabled(True)
        notification.notify(
            title="Download Done",
            message=f"The playlist {pl.title} was succesfully downloaded.",
            app_icon=None,  # You can specify an icon file (.ico on Windows)
            timeout=20      # Duration in seconds
            )

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)
    
    window = DownloaderWidget()
    window.setWindowTitle("YouTube Playlist Downloader")
    window.resize(600, 400)
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
