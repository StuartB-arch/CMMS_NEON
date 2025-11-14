"""
User Management Interface for Managers
Allows managers to create, edit, and deactivate users
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QTreeWidget, QTreeWidgetItem, QComboBox,
    QCheckBox, QTextEdit, QMessageBox, QWidget, QHeaderView
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from database_utils import db_pool, UserManager, AuditLogger


class UserManagementDialog:
    """Dialog for managing users (Manager access only)"""

    def __init__(self, parent, current_user):
        self.parent = parent
        self.current_user = current_user
        self.dialog = None
        self.tree = None

    def show(self):
        """Show the user management dialog"""
        self.dialog = QDialog(self.parent)
        self.dialog.setWindowTitle("User Management")
        self.dialog.setMinimumSize(800, 600)
        self.dialog.setModal(True)

        # Main layout
        main_layout = QVBoxLayout(self.dialog)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_label = QLabel("User Management")
        title_font = QFont('Arial', 14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # Buttons
        view_sessions_btn = QPushButton("View Sessions")
        view_sessions_btn.clicked.connect(self.view_sessions)
        header_layout.addWidget(view_sessions_btn)

        delete_btn = QPushButton("Delete User")
        delete_btn.clicked.connect(self.delete_user)
        header_layout.addWidget(delete_btn)

        edit_btn = QPushButton("Edit User")
        edit_btn.clicked.connect(self.edit_user)
        header_layout.addWidget(edit_btn)

        add_btn = QPushButton("Add User")
        add_btn.clicked.connect(self.add_user)
        header_layout.addWidget(add_btn)

        main_layout.addWidget(header_widget)

        # User list (QTreeWidget with built-in scrollbars)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(7)
        self.tree.setHeaderLabels(['ID', 'Username', 'Full Name', 'Role', 'Active', 'Last Login', 'Created'])

        # Column widths
        self.tree.setColumnWidth(0, 50)
        self.tree.setColumnWidth(1, 120)
        self.tree.setColumnWidth(2, 150)
        self.tree.setColumnWidth(3, 100)
        self.tree.setColumnWidth(4, 60)
        self.tree.setColumnWidth(5, 150)
        self.tree.setColumnWidth(6, 150)

        # Enable sorting
        self.tree.setSortingEnabled(True)

        main_layout.addWidget(self.tree)

        # Load users
        self.load_users()

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.dialog.close)
        main_layout.addWidget(close_btn)

        self.dialog.exec_()

    def load_users(self):
        """Load all users from database"""
        # Clear existing items
        self.tree.clear()

        try:
            with db_pool.get_cursor() as cursor:
                cursor.execute("""
                    SELECT id, username, full_name, role, is_active,
                           last_login, created_date
                    FROM users
                    ORDER BY created_date DESC
                """)

                for row in cursor.fetchall():
                    item = QTreeWidgetItem([
                        str(row['id']),
                        row['username'],
                        row['full_name'],
                        row['role'],
                        'Yes' if row['is_active'] else 'No',
                        str(row['last_login']) if row['last_login'] else 'Never',
                        str(row['created_date'])
                    ])
                    self.tree.addTopLevelItem(item)

        except Exception as e:
            QMessageBox.critical(self.dialog, "Error", f"Failed to load users: {e}")

    def add_user(self):
        """Show dialog to add a new user"""
        dialog = QDialog(self.dialog)
        dialog.setWindowTitle("Add User")
        dialog.setMinimumSize(400, 350)
        dialog.setModal(True)

        # Main layout
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Form
        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(10)

        # Username
        form_layout.addWidget(QLabel("Username:"), 0, 0, Qt.AlignLeft)
        username_entry = QLineEdit()
        username_entry.setMinimumWidth(250)
        form_layout.addWidget(username_entry, 0, 1)

        # Full Name
        form_layout.addWidget(QLabel("Full Name:"), 1, 0, Qt.AlignLeft)
        fullname_entry = QLineEdit()
        fullname_entry.setMinimumWidth(250)
        form_layout.addWidget(fullname_entry, 1, 1)

        # Email
        form_layout.addWidget(QLabel("Email:"), 2, 0, Qt.AlignLeft)
        email_entry = QLineEdit()
        email_entry.setMinimumWidth(250)
        form_layout.addWidget(email_entry, 2, 1)

        # Role
        form_layout.addWidget(QLabel("Role:"), 3, 0, Qt.AlignLeft)
        role_combo = QComboBox()
        role_combo.addItems(['Technician', 'Manager'])
        role_combo.setMinimumWidth(250)
        form_layout.addWidget(role_combo, 3, 1)

        # Password
        form_layout.addWidget(QLabel("Password:"), 4, 0, Qt.AlignLeft)
        password_entry = QLineEdit()
        password_entry.setEchoMode(QLineEdit.Password)
        password_entry.setMinimumWidth(250)
        form_layout.addWidget(password_entry, 4, 1)

        # Confirm Password
        form_layout.addWidget(QLabel("Confirm Password:"), 5, 0, Qt.AlignLeft)
        confirm_entry = QLineEdit()
        confirm_entry.setEchoMode(QLineEdit.Password)
        confirm_entry.setMinimumWidth(250)
        form_layout.addWidget(confirm_entry, 5, 1)

        # Notes
        form_layout.addWidget(QLabel("Notes:"), 6, 0, Qt.AlignTop | Qt.AlignLeft)
        notes_text = QTextEdit()
        notes_text.setMinimumHeight(60)
        notes_text.setMaximumHeight(80)
        form_layout.addWidget(notes_text, 6, 1)

        main_layout.addLayout(form_layout)
        main_layout.addStretch()

        def save_user():
            username = username_entry.text().strip()
            fullname = fullname_entry.text().strip()
            email = email_entry.text().strip()
            role = role_combo.currentText()
            password = password_entry.text()
            confirm = confirm_entry.text()
            notes = notes_text.toPlainText().strip()

            # Validation
            if not username or not fullname or not password:
                QMessageBox.critical(dialog, "Error", "Username, full name, and password are required")
                return

            if password != confirm:
                QMessageBox.critical(dialog, "Error", "Passwords do not match")
                return

            if len(password) < 4:
                QMessageBox.critical(dialog, "Error", "Password must be at least 4 characters")
                return

            try:
                with db_pool.get_cursor() as cursor:
                    # Check if username exists
                    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
                    if cursor.fetchone():
                        QMessageBox.critical(dialog, "Error", "Username already exists")
                        return

                    # Create user
                    password_hash = UserManager.hash_password(password)
                    cursor.execute("""
                        INSERT INTO users
                        (username, password_hash, full_name, email, role, created_by, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (username, password_hash, fullname, email, role, self.current_user, notes))

                    # Log the action
                    AuditLogger.log(cursor, self.current_user, 'INSERT', 'users', username,
                                notes=f"Created new {role} user: {fullname}")

                QMessageBox.information(dialog, "Success", f"User '{username}' created successfully")
                dialog.accept()
                self.load_users()

            except Exception as e:
                QMessageBox.critical(dialog, "Error", f"Failed to create user: {e}")

        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(save_user)
        button_layout.addWidget(save_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        main_layout.addLayout(button_layout)

        dialog.exec_()

    def edit_user(self):
        """Edit selected user"""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self.dialog, "Warning", "Please select a user to edit")
            return

        user_id = selected_items[0].text(0)

        # Fetch user details
        try:
            with db_pool.get_cursor() as cursor:
                cursor.execute("""
                    SELECT username, full_name, email, role, is_active, notes
                    FROM users
                    WHERE id = %s
                """, (user_id,))
                user = cursor.fetchone()

                if not user:
                    QMessageBox.critical(self.dialog, "Error", "User not found")
                    return

        except Exception as e:
            QMessageBox.critical(self.dialog, "Error", f"Failed to load user: {e}")
            return

        # Edit dialog
        dialog = QDialog(self.dialog)
        dialog.setWindowTitle("Edit User")
        dialog.setMinimumSize(400, 400)
        dialog.setModal(True)

        # Main layout
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Form
        form_layout = QGridLayout()
        form_layout.setVerticalSpacing(10)

        # Username (read-only)
        form_layout.addWidget(QLabel("Username:"), 0, 0, Qt.AlignLeft)
        username_label = QLabel(user['username'])
        username_font = QFont('Arial', 10)
        username_font.setBold(True)
        username_label.setFont(username_font)
        form_layout.addWidget(username_label, 0, 1, Qt.AlignLeft)

        # Full Name
        form_layout.addWidget(QLabel("Full Name:"), 1, 0, Qt.AlignLeft)
        fullname_entry = QLineEdit(user['full_name'])
        fullname_entry.setMinimumWidth(250)
        form_layout.addWidget(fullname_entry, 1, 1)

        # Email
        form_layout.addWidget(QLabel("Email:"), 2, 0, Qt.AlignLeft)
        email_entry = QLineEdit(user['email'] or '')
        email_entry.setMinimumWidth(250)
        form_layout.addWidget(email_entry, 2, 1)

        # Role
        form_layout.addWidget(QLabel("Role:"), 3, 0, Qt.AlignLeft)
        role_combo = QComboBox()
        role_combo.addItems(['Manager', 'Technician'])
        role_combo.setCurrentText(user['role'])
        role_combo.setMinimumWidth(250)
        form_layout.addWidget(role_combo, 3, 1)

        # Active
        form_layout.addWidget(QLabel("Active:"), 4, 0, Qt.AlignLeft)
        active_checkbox = QCheckBox()
        active_checkbox.setChecked(user['is_active'])
        form_layout.addWidget(active_checkbox, 4, 1, Qt.AlignLeft)

        # Reset Password
        form_layout.addWidget(QLabel("New Password:"), 5, 0, Qt.AlignLeft)
        password_entry = QLineEdit()
        password_entry.setEchoMode(QLineEdit.Password)
        password_entry.setMinimumWidth(250)
        form_layout.addWidget(password_entry, 5, 1)

        hint_label = QLabel("(leave blank to keep current)")
        hint_font = QFont('Arial', 8)
        hint_label.setFont(hint_font)
        form_layout.addWidget(hint_label, 6, 1, Qt.AlignLeft)

        # Notes
        form_layout.addWidget(QLabel("Notes:"), 7, 0, Qt.AlignTop | Qt.AlignLeft)
        notes_text = QTextEdit()
        notes_text.setPlainText(user['notes'] or '')
        notes_text.setMinimumHeight(60)
        notes_text.setMaximumHeight(80)
        form_layout.addWidget(notes_text, 7, 1)

        main_layout.addLayout(form_layout)
        main_layout.addStretch()

        def save_changes():
            try:
                with db_pool.get_cursor() as cursor:
                    # Update user
                    updates = []
                    params = []

                    updates.append("full_name = %s")
                    params.append(fullname_entry.text().strip())

                    updates.append("email = %s")
                    params.append(email_entry.text().strip())

                    updates.append("role = %s")
                    params.append(role_combo.currentText())

                    updates.append("is_active = %s")
                    params.append(active_checkbox.isChecked())

                    updates.append("notes = %s")
                    params.append(notes_text.toPlainText().strip())

                    # Update password if provided
                    new_password = password_entry.text()
                    if new_password:
                        updates.append("password_hash = %s")
                        params.append(UserManager.hash_password(new_password))

                    updates.append("updated_date = CURRENT_TIMESTAMP")
                    params.append(user_id)

                    query = f"UPDATE users SET {', '.join(updates)} WHERE id = %s"
                    cursor.execute(query, params)

                    # Log the action
                    AuditLogger.log(cursor, self.current_user, 'UPDATE', 'users', str(user_id),
                                notes=f"Updated user: {user['username']}")

                QMessageBox.information(dialog, "Success", "User updated successfully")
                dialog.accept()
                self.load_users()

            except Exception as e:
                QMessageBox.critical(dialog, "Error", f"Failed to update user: {e}")

        # Buttons
        button_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(save_changes)
        button_layout.addWidget(save_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_btn)

        main_layout.addLayout(button_layout)

        dialog.exec_()

    def delete_user(self):
        """Delete selected user"""
        selected_items = self.tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self.dialog, "Warning", "Please select a user to delete")
            return

        user_id = selected_items[0].text(0)
        username = selected_items[0].text(1)
        role = selected_items[0].text(3)

        # Confirm deletion
        msg = QMessageBox(self.dialog)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Confirm Deletion")
        msg.setText(f"Are you sure you want to delete user '{username}' ({role})?")
        msg.setInformativeText(
            "This action cannot be undone and will:\n"
            "- Remove the user from the system\n"
            "- End any active sessions\n"
            "- Preserve audit trail entries\n\n"
            "Note: For safety, consider deactivating the user instead "
            "(via Edit User)."
        )
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)

        result = msg.exec_()

        if result != QMessageBox.Yes:
            return

        # Prevent self-deletion
        if username == self.current_user:
            QMessageBox.critical(self.dialog, "Error", "You cannot delete your own account")
            return

        try:
            with db_pool.get_cursor() as cursor:
                # Log the deletion before deleting the user
                AuditLogger.log(cursor, self.current_user, 'DELETE', 'users', str(user_id),
                            notes=f"Deleted user: {username} ({role})")

                # Delete all sessions for this user first (to avoid foreign key constraint)
                cursor.execute("DELETE FROM user_sessions WHERE user_id = %s", (user_id,))

                # Now delete the user
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))

                # Check if deletion was successful
                if cursor.rowcount == 0:
                    QMessageBox.critical(self.dialog, "Error", "User not found or already deleted")
                    return

            QMessageBox.information(self.dialog, "Success", f"User '{username}' has been deleted successfully")
            self.load_users()

        except Exception as e:
            QMessageBox.critical(self.dialog, "Error", f"Failed to delete user: {e}")

    def view_sessions(self):
        """View active user sessions"""
        dialog = QDialog(self.dialog)
        dialog.setWindowTitle("Active User Sessions")
        dialog.setMinimumSize(800, 400)
        dialog.setModal(True)

        # Main layout
        main_layout = QVBoxLayout(dialog)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Header
        title_label = QLabel("Active User Sessions")
        title_font = QFont('Arial', 12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        main_layout.addWidget(title_label)

        # Session list
        tree = QTreeWidget()
        tree.setColumnCount(6)
        tree.setHeaderLabels(['Session ID', 'User', 'Full Name', 'Role', 'Login Time', 'Last Activity'])

        # Set all columns to same width
        for i in range(6):
            tree.setColumnWidth(i, 130)

        # Enable sorting
        tree.setSortingEnabled(True)

        main_layout.addWidget(tree)

        # Load sessions
        try:
            with db_pool.get_cursor() as cursor:
                sessions = UserManager.get_active_sessions(cursor)

                for session in sessions:
                    item = QTreeWidgetItem([
                        str(session['id']),
                        session['username'],
                        session['full_name'],
                        session['role'],
                        str(session['login_time']),
                        str(session['last_activity'])
                    ])
                    tree.addTopLevelItem(item)

        except Exception as e:
            QMessageBox.critical(dialog, "Error", f"Failed to load sessions: {e}")

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        main_layout.addWidget(close_btn)

        dialog.exec_()
