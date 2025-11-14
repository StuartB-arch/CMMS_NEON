"""
Password Change Interface for All Users
Allows users to change their own passwords
"""

from PyQt5.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton, QFrame,
                             QVBoxLayout, QHBoxLayout, QGridLayout, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from database_utils import db_pool, UserManager, AuditLogger


class PasswordChangeDialog(QDialog):
    """Dialog for users to change their own password"""

    def __init__(self, parent, current_user, username):
        """
        Initialize the password change dialog

        Args:
            parent: Parent window
            current_user: Current user's full name (for audit logging)
            username: Current user's username
        """
        super().__init__(parent)
        self.parent_window = parent
        self.current_user = current_user
        self.username = username
        self.setup_ui()

    def setup_ui(self):
        """Setup the user interface"""
        self.setWindowTitle("Change Password")
        self.setFixedSize(450, 300)
        self.setModal(True)  # Make dialog modal

        # Center the dialog on parent window
        if self.parent_window:
            parent_geo = self.parent_window.geometry()
            x = parent_geo.x() + (parent_geo.width() - 450) // 2
            y = parent_geo.y() + (parent_geo.height() - 300) // 2
            self.move(x, y)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)
        self.setLayout(main_layout)

        # Header
        header_frame = QFrame()
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        header_frame.setLayout(header_layout)

        title_label = QLabel("Change Your Password")
        title_label.setFont(QFont('Arial', 14, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)

        user_label = QLabel(f"User: {self.username}")
        user_label.setFont(QFont('Arial', 10))
        user_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(user_label)

        main_layout.addWidget(header_frame)

        # Form frame
        form_frame = QFrame()
        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(10)
        form_layout.setHorizontalSpacing(10)
        form_frame.setLayout(form_layout)

        # Current Password
        form_layout.addWidget(QLabel("Current Password:"), 0, 0, Qt.AlignLeft)
        self.current_password_entry = QLineEdit()
        self.current_password_entry.setEchoMode(QLineEdit.Password)
        self.current_password_entry.setMinimumWidth(200)
        form_layout.addWidget(self.current_password_entry, 0, 1)

        # New Password
        form_layout.addWidget(QLabel("New Password:"), 1, 0, Qt.AlignLeft)
        self.new_password_entry = QLineEdit()
        self.new_password_entry.setEchoMode(QLineEdit.Password)
        self.new_password_entry.setMinimumWidth(200)
        form_layout.addWidget(self.new_password_entry, 1, 1)

        # Confirm New Password
        form_layout.addWidget(QLabel("Confirm New Password:"), 2, 0, Qt.AlignLeft)
        self.confirm_password_entry = QLineEdit()
        self.confirm_password_entry.setEchoMode(QLineEdit.Password)
        self.confirm_password_entry.setMinimumWidth(200)
        form_layout.addWidget(self.confirm_password_entry, 2, 1)

        main_layout.addWidget(form_frame)

        # Password requirements
        requirements_frame = QFrame()
        requirements_layout = QVBoxLayout()
        requirements_layout.setSpacing(2)
        requirements_frame.setLayout(requirements_layout)

        req_title = QLabel("Password Requirements:")
        req_title.setFont(QFont('Arial', 9, QFont.Bold))
        requirements_layout.addWidget(req_title)

        req1 = QLabel("• Minimum 4 characters")
        req1.setFont(QFont('Arial', 8))
        req1.setStyleSheet("color: gray")
        requirements_layout.addWidget(req1)

        req2 = QLabel("• Avoid using common passwords")
        req2.setFont(QFont('Arial', 8))
        req2.setStyleSheet("color: gray")
        requirements_layout.addWidget(req2)

        main_layout.addWidget(requirements_frame)

        # Buttons
        button_frame = QFrame()
        button_layout = QHBoxLayout()
        button_layout.setSpacing(5)
        button_frame.setLayout(button_layout)

        change_btn = QPushButton("Change Password")
        change_btn.clicked.connect(self.change_password)
        button_layout.addWidget(change_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        button_layout.addWidget(cancel_btn)

        button_layout.addStretch()

        main_layout.addWidget(button_frame)

        # Focus on current password field
        self.current_password_entry.setFocus()

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.change_password()
        elif event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def change_password(self):
        """Handle password change"""
        current_password = self.current_password_entry.text().strip()
        new_password = self.new_password_entry.text().strip()
        confirm_password = self.confirm_password_entry.text().strip()

        # Validate inputs
        if not current_password:
            QMessageBox.critical(self, "Validation Error", "Please enter your current password")
            self.current_password_entry.setFocus()
            return

        if not new_password:
            QMessageBox.critical(self, "Validation Error", "Please enter a new password")
            self.new_password_entry.setFocus()
            return

        if len(new_password) < 4:
            QMessageBox.critical(self, "Validation Error", "New password must be at least 4 characters long")
            self.new_password_entry.setFocus()
            return

        if new_password != confirm_password:
            QMessageBox.critical(self, "Validation Error", "New passwords do not match")
            self.confirm_password_entry.clear()
            self.confirm_password_entry.setFocus()
            return

        if current_password == new_password:
            QMessageBox.warning(self, "Validation Warning",
                               "New password must be different from current password")
            self.new_password_entry.setFocus()
            return

        # Attempt to change password
        try:
            with db_pool.get_cursor(commit=True) as cursor:
                success, message = UserManager.change_password(
                    cursor, self.username, current_password, new_password
                )

                if success:
                    # Log the password change to audit log
                    AuditLogger.log(
                        cursor,
                        self.current_user,
                        'UPDATE',
                        'users',
                        self.username,
                        notes="User changed their own password"
                    )

                    QMessageBox.information(self, "Success", message)
                    self.close()
                else:
                    QMessageBox.critical(self, "Error", message)
                    # Clear password fields if current password was wrong
                    if "incorrect" in message.lower():
                        self.current_password_entry.clear()
                        self.current_password_entry.setFocus()

        except Exception as e:
            QMessageBox.critical(self, "Database Error",
                               f"Failed to change password: {str(e)}")
            print(f"Password change error: {e}")


def show_password_change_dialog(parent, current_user, username):
    """
    Convenience function to show the password change dialog

    Args:
        parent: Parent window
        current_user: Current user's full name (for audit logging)
        username: Current user's username
    """
    dialog = PasswordChangeDialog(parent, current_user, username)
    dialog.exec_()
