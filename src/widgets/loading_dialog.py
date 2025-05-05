"""
This file is part of Mod Manager Migrator
by Cutleast and falls under the license
Attribution-NonCommercial-NoDerivatives 4.0 International.
"""

import threading
import time
import queue
from typing import Callable, List, Dict
from collections import deque

import qtpy.QtCore as qtc
import qtpy.QtWidgets as qtw

import main
import utilities as utils


class LoadingDialog(qtw.QDialog):
    """
    QDialog designed for multiple progress bars and parallel operations.
    
    Shows a main progress bar for overall progress and information about
    current operations in a structured way.
    
    Parameters:
        parent: QWidget
        app: main.MainApp
        func: function or method that is run in a background thread
    """

    start_signal = qtc.Signal()
    stop_signal = qtc.Signal()
    progress_signal = qtc.Signal(dict)

    def __init__(self, parent: qtw.QWidget, app: main.MainApp, func: Callable):
        super().__init__(parent)

        # Force focus
        self.setModal(True)
        
        # Set up variables
        self.app = app
        self.success = True
        
        # Initialize scale factors for large progress values
        self._scale_factor = 1
        
        # Operation tracking
        self.last_operations = deque(maxlen=5)  # Store the last 5 operations
        self.total_operations = 0
        self.completed_operations = 0
        self.current_size_processed = 0
        self.total_size = 0
        self.start_time = None
        
        self.func = lambda: (
            self.start_signal.emit(),
            func(self),
            self.stop_signal.emit(),
        )
        self.dialog_thread = LoadingDialogThread(
            dialog=self, target=self.func, daemon=True, name="BackgroundThread"
        )
        self.starttime = None

        # Set up dialog layout
        self.layout = qtw.QVBoxLayout()
        self.layout.setAlignment(qtc.Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.layout)

        # Main progress section - always visible
        self.main_group = qtw.QGroupBox("Overall Progress")
        self.main_layout = qtw.QVBoxLayout()
        self.main_group.setLayout(self.main_layout)
        
        # Stats layout (contains file count and size processed)
        self.stats_layout = qtw.QHBoxLayout()
        
        # File counter
        self.files_label = qtw.QLabel("Files: 0 / 0")
        self.stats_layout.addWidget(self.files_label)
        
        # Size counter
        self.size_label = qtw.QLabel("Size: 0 B / 0 B")
        self.stats_layout.addWidget(self.size_label)
        
        # Elapsed time
        self.time_label = qtw.QLabel("Time: 00:00")
        self.stats_layout.addWidget(self.time_label)
        
        # Speed indicator
        self.speed_label = qtw.QLabel("Speed: -- MB/s")
        self.stats_layout.addWidget(self.speed_label)
        
        self.main_layout.addLayout(self.stats_layout)
        
        # Main progress bar
        self.main_progress_label = qtw.QLabel("Preparing operation...")
        self.main_layout.addWidget(self.main_progress_label)
        
        self.main_progress_bar = qtw.QProgressBar()
        self.main_progress_bar.setRange(0, 100)  # Always use percentage for main bar
        self.main_progress_bar.setValue(0)
        self.main_layout.addWidget(self.main_progress_bar)
        
        self.layout.addWidget(self.main_group)
        
        # Current operations group
        self.operations_group = qtw.QGroupBox("Current Operations")
        self.operations_layout = qtw.QVBoxLayout()
        self.operations_group.setLayout(self.operations_layout)
        
        # Current operation widgets
        self.current_op_label = qtw.QLabel("Waiting to start...")
        self.operations_layout.addWidget(self.current_op_label)
        
        # Recent operations list
        self.recent_ops_list = qtw.QListWidget()
        self.recent_ops_list.setAlternatingRowColors(True)
        self.recent_ops_list.setMaximumHeight(120)  # Limit height
        self.operations_layout.addWidget(self.recent_ops_list)
        
        self.layout.addWidget(self.operations_group)

        # Connect signals
        self.start_signal.connect(self.on_start)
        self.stop_signal.connect(self.on_finish)
        self.progress_signal.connect(self.on_progress)

        # Set minimum width and configure dialog
        self.setMinimumWidth(600)
        self.setWindowTitle("Operation in Progress")
        self.setWindowIcon(parent.windowIcon())
        self.setStyleSheet(parent.styleSheet())
        self.setWindowFlag(qtc.Qt.WindowType.WindowCloseButtonHint, False)
        
        # Start timer for elapsed time updates
        self.timer = qtc.QTimer(self)
        self.timer.timeout.connect(self.update_elapsed_time)
        self.timer.start(500)  # Update twice per second
    
    def __repr__(self):
        return "LoadingDialog"
    
    def update_elapsed_time(self):
        """
        Update the elapsed time display
        """
        if self.starttime is None:
            return
            
        elapsed = time.time() - self.starttime
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        # Calculate speed
        if elapsed > 0 and self.current_size_processed > 0:
            speed = self.current_size_processed / elapsed / (1024 * 1024)  # MB/s
            self.speed_label.setText(f"Speed: {speed:.2f} MB/s")
        
        self.time_label.setText(f"Time: {minutes:02d}:{seconds:02d}")
        
        # Update window title
        self.setWindowTitle(f"{self.app.name} - {self.app.loc.main.elapsed}: {minutes:02d}:{seconds:02d}")
        
    def on_start(self):
        """
        Called when the background thread starts
        """
        self.starttime = time.time()
        self.start_time = self.starttime
        self.current_op_label.setText("Starting operation...")
        self.main_progress_label.setText("Initializing...")
        
    def on_finish(self):
        """
        Called when the background thread completes
        """
        # Stop the timer
        self.timer.stop()
        
        # Final update of progress
        if self.total_operations > 0:
            self.main_progress_bar.setValue(100)
            self.files_label.setText(f"Files: {self.completed_operations} / {self.total_operations}")
            
        # Show completion message
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        self.main_progress_label.setText(f"Operation completed in {minutes:02d}:{seconds:02d}")
        self.current_op_label.setText("All operations completed successfully.")
        
        # Add final status to the list
        self.recent_ops_list.addItem(f"Completed {self.completed_operations} operations in {minutes:02d}:{seconds:02d}")
        
        # Close after a short delay
        qtc.QTimer.singleShot(500, self.accept)
    
    def on_progress(self, progress):
        """
        Process progress updates from the background thread
        """
        self.setProgress(progress)
        
    def add_operation_to_list(self, operation_text):
        """
        Add an operation to the recent operations list
        """
        # Only keep the last 5 operations to avoid overwhelming the UI
        self.last_operations.append(operation_text)
        
        # Update the list widget
        self.recent_ops_list.clear()
        for op in self.last_operations:
            self.recent_ops_list.addItem(op)
            
        # Scroll to the bottom to show the most recent operation
        self.recent_ops_list.scrollToBottom()

    def updateProgress(
        self,
        text1: str = None,
        value1: int = None,
        max1: int = None,
        show2: bool = None,
        text2: str = None,
        value2: int = None,
        max2: int = None,
        show3: bool = None,
        text3: str = None,
        value3: int = None,
        max3: int = None,
    ):
        """
        Updates progress of progressbars.
        This method is thread safe for usage with Qt.

        Parameters:
            text1: str (text displayed over first progressbar)
            value1: int (progress of first progressbar)
            max1: int (maximum value of first progressbar)

            show2: bool (True shows second progressbar; False hides it)
            text2: str (text displayed over second progressbar)
            value2: int (progress of second progressbar)
            max2: int (maximum value of second progressbar)

            show3: bool (True shows third progressbar; False hides it)
            text3: str (text displayed over third progressbar)
            value3: int (progress of third progressbar)
            max3: int (maximum value of third progressbar)
        """

        # Convert parameters to a centralized format for our new UI
        progress_data = {
            "text1": text1,
            "value1": value1,
            "max1": max1,
            "show2": show2,
            "text2": text2,
            "value2": value2,
            "max2": max2,
            "show3": show3,
            "text3": text3,
            "value3": value3,
            "max3": max3,
        }
        
        self.progress_signal.emit(progress_data)

    def setProgress(self, progress: dict):
        """
        Sets progress from <progress> and updates the centralized UI.
        
        Parameters:
            progress: dict containing the progress information
        """
        # Extract progress information
        text1 = progress.get("text1", None)
        value1 = progress.get("value1", None)
        max1 = progress.get("max1", None)
        
        text2 = progress.get("text2", None)  
        value2 = progress.get("value2", None)
        max2 = progress.get("max2", None)
        
        text3 = progress.get("text3", None)
        
        # For backward compatibility with legacy code
        if text1 is None:
            text1 = progress.get("text", None)
        if value1 is None:
            value1 = progress.get("value", None)
        if max1 is None:
            max1 = progress.get("max", None)
            
        # Handle overall progress updates
        if max1 is not None and value1 is not None:
            if self.total_size == 0 and max1 > 0:
                self.total_size = max1
                
            if max1 > 0:  # Avoid division by zero
                # Calculate percentage for the main progress bar
                percent = min(int((value1 / max1) * 100), 100)
                self.main_progress_bar.setValue(percent)
                
                # Update size information
                self.current_size_processed = value1
                self.size_label.setText(f"Size: {utils.scale_value(value1)} / {utils.scale_value(max1)}")
                
        # Update operation information
        if text1 is not None:
            self.main_progress_label.setText(text1)
            
        # Update file information if text2 contains file information
        if text2 is not None:
            # Check if text2 contains information about file count
            if " (" in text2 and ")" in text2:
                try:
                    # Extract file information if it's in the format "name (X/Y)"
                    parts = text2.split(" (")
                    count_part = parts[1].split(")")[0]
                    if "/" in count_part:
                        current, total = count_part.split("/")
                        self.completed_operations = int(current)
                        self.total_operations = int(total)
                        self.files_label.setText(f"Files: {current}/{total}")
                except:
                    # If we can't parse the file info, just use text2 as current operation
                    pass
                    
            # Update current operation label
            self.current_op_label.setText(text2)
            
            # Add operation to the list if it contains useful information
            if len(text2) > 5 and text2 not in self.last_operations:
                self.add_operation_to_list(text2)
                
        # If there's a third text item, add it to the operation list
        if text3 is not None and len(text3) > 5:
            # Only add if it's descriptive enough and not already in the list
            if text3 not in self.last_operations:
                self.add_operation_to_list(text3)
                
        # Center the dialog if needed
        utils.center(self, self.app.root)

    def exec(self):
        """
        Shows dialog and executes thread.
        Blocks code until thread is done and dialog is closed.
        """
        # Start the dialog thread
        self.dialog_thread.start()
        
        # Set the start time
        self.starttime = time.time()
        
        # Execute the dialog (blocks until closed)
        super().exec()
        
        # Propagate any exceptions from the thread
        if self.dialog_thread.exception is not None:
            raise self.dialog_thread.exception


class LoadingDialogThread(threading.Thread):
    """
    Thread for LoadingDialog.
    Passes exceptions from thread to MainThread.
    """

    exception = None

    def __init__(self, dialog: LoadingDialog, target: Callable, *args, **kwargs):
        super().__init__(target=target, *args, **kwargs)
        self.dialog = dialog

    def run(self):
        """
        Runs thread and raises errors that could occur.
        """
        try:
            super().run()
        except Exception as ex:
            self.exception = ex
            self.dialog.stop_signal.emit()
