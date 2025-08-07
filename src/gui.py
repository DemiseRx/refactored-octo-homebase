import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QProgressBar, QLabel, QTextEdit, QFrame, QFileDialog
)
from PySide6.QtGui import QIcon, QDesktopServices
import os
import logging
from datetime import datetime
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from text_processor import process_file
from llm_interface import identify_speakers
from higgs_formatter import format_for_higgs
from higgs_interface import generate_audio

class LlmWorker(QThread):
    progress = Signal(int)
    chunk_processed = Signal(int, str)
    finished = Signal(list)

    def __init__(self, chunks):
        super().__init__()
        self.chunks = chunks
        self.tagged_chunks = []

    def run(self):
        total_chunks = len(self.chunks)
        for i, chunk in enumerate(self.chunks):
            tagged_chunk = identify_speakers(chunk)
            if tagged_chunk:
                self.tagged_chunks.append(tagged_chunk)
                self.chunk_processed.emit(i + 1, tagged_chunk)
            else:
                # Handle error: maybe retry or use the original chunk
                self.tagged_chunks.append(f"[narrator] {chunk}")
                self.chunk_processed.emit(i + 1, "Error processing chunk.")

            self.progress.emit(int(((i + 1) / total_chunks) * 100))

        self.finished.emit(self.tagged_chunks)

class QLogHandler(logging.Handler):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent

    def emit(self, record):
        msg = self.format(record)
        self.parent.log_message.emit(msg)

class HiggsWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, text_to_speak, output_path):
        super().__init__()
        self.text_to_speak = text_to_speak
        self.output_path = output_path

    def run(self):
        success = generate_audio(self.text_to_speak, self.output_path)
        self.finished.emit(success, self.output_path)


class MainWindow(QMainWindow):
    log_message = Signal(str)

    def __init__(self):
        super().__init__()

        # Logging setup
        self.log_message.connect(self.append_log_message)
        self.log_handler = QLogHandler(self)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.log_handler.setFormatter(formatter)
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.final_text_for_higgs = None
        self.speaker_list = []
        self.source_file_path = None

        self.setWindowTitle("Audiobook Generator Using Higgs Audio V2")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        header_label = QLabel("Audiobook Generator")
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(header_label)

        self.file_select_button = QPushButton("Browse for .txt or .docx file")
        main_layout.addWidget(self.file_select_button)

        progress_frame = QFrame()
        progress_layout = QVBoxLayout(progress_frame)
        main_layout.addWidget(progress_frame)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        status_layout = QHBoxLayout()
        self.chunk_status_label = QLabel("Processing chunk 0 of 0")
        self.voices_detected_label = QLabel("Voices detected: 0")
        self.audio_output_status_label = QLabel("Status: Idle")
        status_layout.addWidget(self.chunk_status_label)
        status_layout.addWidget(self.voices_detected_label)
        status_layout.addWidget(self.audio_output_status_label)
        progress_layout.addLayout(status_layout)

        action_layout = QHBoxLayout()
        self.generate_audio_button = QPushButton("Generate Audio")
        self.generate_audio_button.setEnabled(False)
        self.output_folder_button = QPushButton("Open Output Folder")
        self.toggle_console_button = QPushButton("Toggle Console")
        action_layout.addWidget(self.generate_audio_button)
        action_layout.addWidget(self.output_folder_button)
        action_layout.addWidget(self.toggle_console_button)
        main_layout.addLayout(action_layout)

        self.console_pane = QTextEdit()
        self.console_pane.setReadOnly(True)
        self.console_pane.setVisible(False)
        main_layout.addWidget(self.console_pane)

        self.toggle_console_button.clicked.connect(self.toggle_console)
        self.output_folder_button.clicked.connect(self.open_output_folder)
        self.file_select_button.clicked.connect(self.open_file_dialog)
        self.generate_audio_button.clicked.connect(self.start_audio_generation)

        logging.info("Application initialized.")

    def append_log_message(self, message):
        self.console_pane.append(message)

    def toggle_console(self):
        self.console_pane.setVisible(not self.console_pane.isVisible())

    def open_output_folder(self):
        output_dir = "output"
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"Created output directory at: {os.path.abspath(output_dir)}")

        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(output_dir)))

    def open_file_dialog(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Open Text or Document File", "", "All Files (*);;Text Files (*.txt);;Word Documents (*.docx)")
        if file_name:
            self.source_file_path = file_name
            self.file_select_button.setEnabled(False)
            self.generate_audio_button.setEnabled(False)
            logging.info(f"Selected file: {file_name}")
            logging.info("Processing file...")
            QApplication.processEvents()
            chunks = process_file(file_name)
            if chunks:
                logging.info(f"File successfully processed into {len(chunks)} chunks.")
                logging.info("Starting speaker identification...")
                self.start_speaker_identification(chunks)
            else:
                logging.error("Failed to process file.")
                self.file_select_button.setEnabled(True)

    def start_speaker_identification(self, chunks):
        self.llm_worker = LlmWorker(chunks)
        self.llm_worker.progress.connect(self.update_progress)
        self.llm_worker.chunk_processed.connect(self.log_chunk_processing)
        self.llm_worker.finished.connect(self.speaker_identification_finished)
        self.llm_worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def log_chunk_processing(self, chunk_num, tagged_chunk):
        self.chunk_status_label.setText(f"Processing chunk {chunk_num} of {len(self.llm_worker.chunks)}")
        # This is very verbose, maybe just log the first 50 chars
        logging.info(f"Tagged chunk {chunk_num}: {tagged_chunk[:50]}...")

    def speaker_identification_finished(self, tagged_chunks):
        logging.info("Speaker identification complete.")
        logging.info("Formatting text for Higgs Audio V2...")

        self.final_text_for_higgs, self.speaker_list = format_for_higgs(tagged_chunks)

        logging.info(f"Final script contains {len(self.final_text_for_higgs)} characters.")

        num_speakers = len(self.speaker_list)
        self.voices_detected_label.setText(f"Voices detected: {num_speakers}")
        logging.info(f"Found {num_speakers} unique speakers: {self.speaker_list}")

        if num_speakers > 10:
            logging.warning("More than 10 unique speakers detected. Higgs may have issues.")

        self.audio_output_status_label.setText("Status: Ready for audio generation")
        self.file_select_button.setEnabled(True)
        self.generate_audio_button.setEnabled(True)

    def start_audio_generation(self):
        logging.info("--- Starting Audio Generation ---")
        self.audio_output_status_label.setText("Status: Generating audio...")
        self.file_select_button.setEnabled(False)
        self.generate_audio_button.setEnabled(False)

        base_name = os.path.splitext(os.path.basename(self.source_file_path))[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{base_name}_{timestamp}.wav"
        output_path = os.path.join("output", output_filename)

        self.higgs_worker = HiggsWorker(self.final_text_for_higgs, output_path)
        self.higgs_worker.finished.connect(self.audio_generation_finished)
        self.higgs_worker.start()

    def audio_generation_finished(self, success, output_path):
        if success:
            logging.info(f"✅ Audio generation complete! File saved to {output_path}")
            self.audio_output_status_label.setText("✅ Audio generation complete!")
        else:
            logging.error("❌ Audio generation failed. Check logs for details.")
            self.audio_output_status_label.setText("❌ Audio generation failed.")

        self.file_select_button.setEnabled(True)
        self.generate_audio_button.setEnabled(True)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
