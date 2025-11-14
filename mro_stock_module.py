"""
AIT CMMS - MRO Stock Management Module
Migrated to PyQt5 from tkinter
"""

from PyQt5.QtWidgets import (
    QWidget, QDialog, QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem,
    QTextEdit, QMessageBox, QFileDialog, QGroupBox, QScrollArea, QTabWidget,
    QHeaderView, QFrame, QSplitter, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap, QImage, QFont, QColor
from datetime import datetime
import os
from PIL import Image
import shutil
import csv
import io
from database_utils import db_pool

class MROStockManager:
    """MRO (Maintenance, Repair, Operations) Stock Management"""

    def __init__(self, parent_app):
        self.parent_app = parent_app
        self.conn = parent_app.conn
        self.root = parent_app.root
        self.init_mro_database()

    def init_mro_database(self):
        """Initialize MRO inventory table"""
        cursor = self.conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mro_inventory (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                part_number TEXT UNIQUE NOT NULL,
                model_number TEXT,
                equipment TEXT,
                engineering_system TEXT,
                unit_of_measure TEXT,
                quantity_in_stock REAL DEFAULT 0,
                unit_price REAL DEFAULT 0,
                minimum_stock REAL DEFAULT 0,
                supplier TEXT,
                location TEXT,
                rack TEXT,
                row TEXT,
                bin TEXT,
                picture_1_path TEXT,
                picture_2_path TEXT,
                picture_1_data BYTEA,
                picture_2_data BYTEA,
                notes TEXT,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Active'
            )
        ''')

        # Migrate existing tables to add new columns if they don't exist
        try:
            # Check if picture_1_data column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='mro_inventory' AND column_name='picture_1_data'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE mro_inventory ADD COLUMN picture_1_data BYTEA')
                self.conn.commit()
                print("Added picture_1_data column to mro_inventory table")
        except Exception as e:
            self.conn.rollback()
            print(f"Note: Could not add picture_1_data column: {e}")

        try:
            # Check if picture_2_data column exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='mro_inventory' AND column_name='picture_2_data'
            """)
            if not cursor.fetchone():
                cursor.execute('ALTER TABLE mro_inventory ADD COLUMN picture_2_data BYTEA')
                self.conn.commit()
                print("Added picture_2_data column to mro_inventory table")
        except Exception as e:
            self.conn.rollback()
            print(f"Note: Could not add picture_2_data column: {e}")

        # === PERFORMANCE OPTIMIZATION: Create comprehensive MRO indexes ===
        print("CHECK: Creating MRO inventory performance indexes...")

        # Basic indexes for unique lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_part_number
            ON mro_inventory(part_number)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_name
            ON mro_inventory(name)
        ''')

        # Functional indexes for case-insensitive searches (critical for filter performance)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_engineering_system_lower
            ON mro_inventory(LOWER(engineering_system))
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_status_lower
            ON mro_inventory(LOWER(status))
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_location_lower
            ON mro_inventory(LOWER(location))
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_equipment_lower
            ON mro_inventory(LOWER(equipment))
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_model_number_lower
            ON mro_inventory(LOWER(model_number))
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_part_number_lower
            ON mro_inventory(LOWER(part_number))
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_name_lower
            ON mro_inventory(LOWER(name))
        ''')

        # Partial index for low stock queries (most common filter)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_low_stock
            ON mro_inventory(status, quantity_in_stock, minimum_stock)
            WHERE quantity_in_stock < minimum_stock
        ''')

        # Covering index for statistics queries (eliminates table access)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_active_stock_value
            ON mro_inventory(status, quantity_in_stock, unit_price, minimum_stock)
            WHERE status = 'Active'
        ''')

        print("CHECK: MRO inventory indexes created successfully!")

        # Stock transactions table for tracking stock movements
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mro_stock_transactions (
                id SERIAL PRIMARY KEY,
                part_number TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                transaction_date TEXT DEFAULT CURRENT_TIMESTAMP,
                technician_name TEXT,
                work_order TEXT,
                notes TEXT,
                FOREIGN KEY (part_number) REFERENCES mro_inventory (part_number)
            )
        ''')

        # CM parts usage table for tracking parts used in corrective maintenance
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cm_parts_used (
                id SERIAL PRIMARY KEY,
                cm_number TEXT NOT NULL,
                part_number TEXT NOT NULL,
                quantity_used REAL NOT NULL,
                total_cost REAL DEFAULT 0,
                recorded_date TEXT DEFAULT CURRENT_TIMESTAMP,
                recorded_by TEXT,
                notes TEXT,
                FOREIGN KEY (part_number) REFERENCES mro_inventory (part_number)
            )
        ''')

        # Indexes for faster CM parts and transaction queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cm_parts_cm_number
            ON cm_parts_used(cm_number)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cm_parts_part_number
            ON cm_parts_used(part_number)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_cm_parts_used_date
            ON cm_parts_used(recorded_date)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_transactions_date
            ON mro_stock_transactions(transaction_date)
        ''')

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mro_transactions_part_number
            ON mro_stock_transactions(part_number)
        ''')

        self.conn.commit()
        print("MRO inventory database initialized with performance indexes")

    def create_mro_tab(self, notebook):
        """Create MRO Stock Management tab"""
        mro_frame = QWidget()
        main_layout = QVBoxLayout(mro_frame)

        # Top controls frame
        controls_group = QGroupBox("MRO Stock Controls")
        controls_layout = QVBoxLayout()

        # Buttons row 1
        btn_layout1 = QHBoxLayout()

        add_btn = QPushButton("Add New Part")
        add_btn.clicked.connect(self.add_part_dialog)
        btn_layout1.addWidget(add_btn)

        edit_btn = QPushButton("Edit Selected Part")
        edit_btn.clicked.connect(self.edit_selected_part)
        btn_layout1.addWidget(edit_btn)

        delete_btn = QPushButton("Delete Selected Part")
        delete_btn.clicked.connect(self.delete_selected_part)
        btn_layout1.addWidget(delete_btn)

        details_btn = QPushButton("View Full Details")
        details_btn.clicked.connect(self.view_part_details)
        btn_layout1.addWidget(details_btn)

        usage_btn = QPushButton("Parts Usage Report")
        usage_btn.clicked.connect(self.show_parts_usage_report)
        btn_layout1.addWidget(usage_btn)

        btn_layout1.addStretch()
        controls_layout.addLayout(btn_layout1)

        # Buttons row 2
        btn_layout2 = QHBoxLayout()

        import_btn = QPushButton("Import from File")
        import_btn.clicked.connect(self.import_from_file)
        btn_layout2.addWidget(import_btn)

        export_btn = QPushButton("Export to CSV")
        export_btn.clicked.connect(self.export_to_csv)
        btn_layout2.addWidget(export_btn)

        report_btn = QPushButton("Stock Report")
        report_btn.clicked.connect(self.generate_stock_report)
        btn_layout2.addWidget(report_btn)

        low_stock_btn = QPushButton("Low Stock Alert")
        low_stock_btn.clicked.connect(self.show_low_stock)
        btn_layout2.addWidget(low_stock_btn)

        migrate_btn = QPushButton("Migrate Photos to DB")
        migrate_btn.clicked.connect(self.migrate_photos_to_database)
        btn_layout2.addWidget(migrate_btn)

        btn_layout2.addStretch()
        controls_layout.addLayout(btn_layout2)

        controls_group.setLayout(controls_layout)
        main_layout.addWidget(controls_group)

        # Search and filter frame
        search_group = QGroupBox("Search & Filter")
        search_layout = QHBoxLayout()

        search_layout.addWidget(QLabel("Search:"))
        self.mro_search_entry = QLineEdit()
        self.mro_search_entry.textChanged.connect(self.filter_mro_list)
        search_layout.addWidget(self.mro_search_entry)

        search_layout.addWidget(QLabel("System:"))
        self.mro_system_filter = QComboBox()
        self.mro_system_filter.addItems(['All', 'Mechanical', 'Electrical', 'Pneumatic', 'Hydraulic'])
        self.mro_system_filter.currentTextChanged.connect(self.filter_mro_list)
        search_layout.addWidget(self.mro_system_filter)

        search_layout.addWidget(QLabel("Status:"))
        self.mro_status_filter = QComboBox()
        self.mro_status_filter.addItems(['Active', 'All', 'Inactive', 'Low Stock'])
        self.mro_status_filter.currentTextChanged.connect(self.filter_mro_list)
        search_layout.addWidget(self.mro_status_filter)

        search_layout.addWidget(QLabel("Location:"))
        self.mro_location_filter = QComboBox()
        self.mro_location_filter.addItems(['All'])
        self.mro_location_filter.currentTextChanged.connect(self.filter_mro_list)
        search_layout.addWidget(self.mro_location_filter)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_mro_list)
        search_layout.addWidget(refresh_btn)

        search_layout.addStretch()
        search_group.setLayout(search_layout)
        main_layout.addWidget(search_group)

        # Inventory list
        list_group = QGroupBox("MRO Inventory")
        list_layout = QVBoxLayout()

        # Create treeview
        self.mro_tree = QTreeWidget()
        columns = ['Part Number', 'Name', 'Model', 'Equipment', 'System', 'Qty',
                  'Min Stock', 'Unit', 'Price', 'Location', 'Status']
        self.mro_tree.setColumnCount(len(columns))
        self.mro_tree.setHeaderLabels(columns)

        # Configure columns
        column_widths = [120, 200, 100, 120, 100, 70, 80, 60, 80, 100, 80]
        for i, width in enumerate(column_widths):
            self.mro_tree.setColumnWidth(i, width)

        self.mro_tree.setSortingEnabled(True)
        self.mro_tree.setAlternatingRowColors(True)

        # Double-click to view details
        self.mro_tree.itemDoubleClicked.connect(lambda: self.view_part_details())

        list_layout.addWidget(self.mro_tree)
        list_group.setLayout(list_layout)
        main_layout.addWidget(list_group)

        # Statistics frame
        stats_group = QGroupBox("Inventory Statistics")
        stats_layout = QVBoxLayout()

        self.mro_stats_label = QLabel("Loading...")
        font = QFont('Arial', 10)
        self.mro_stats_label.setFont(font)
        stats_layout.addWidget(self.mro_stats_label)

        stats_group.setLayout(stats_layout)
        main_layout.addWidget(stats_group)

        # Load initial data
        self.refresh_mro_list()

        notebook.addTab(mro_frame, 'MRO Stock')
        return mro_frame

    def add_part_dialog(self):
        """Dialog to add new part"""
        dialog = QDialog(self.root)
        dialog.setWindowTitle("Add New MRO Part")
        dialog.resize(800, 900)
        dialog.setModal(True)

        # Main layout with scroll area
        main_layout = QVBoxLayout(dialog)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QGridLayout(scroll_widget)

        # Form fields
        fields = {}
        row = 0

        # Basic Information
        basic_label = QLabel("BASIC INFORMATION")
        font = QFont('Arial', 11, QFont.Bold)
        basic_label.setFont(font)
        scroll_layout.addWidget(basic_label, row, 0, 1, 2)
        row += 1

        field_configs = [
            ('Name*', 'name'),
            ('Part Number*', 'part_number'),
            ('Model Number', 'model_number'),
            ('Equipment', 'equipment'),
        ]

        for label, field_name in field_configs:
            scroll_layout.addWidget(QLabel(label), row, 0)
            fields[field_name] = QLineEdit()
            scroll_layout.addWidget(fields[field_name], row, 1)
            row += 1

        # Stock Information
        stock_label = QLabel("STOCK INFORMATION")
        stock_label.setFont(font)
        scroll_layout.addWidget(stock_label, row, 0, 1, 2)
        row += 1

        stock_fields = [
            ('Engineering System*', 'engineering_system'),
            ('Unit of Measure*', 'unit_of_measure'),
            ('Quantity in Stock*', 'quantity_in_stock'),
            ('Unit Price', 'unit_price'),
            ('Minimum Stock*', 'minimum_stock'),
            ('Supplier', 'supplier'),
        ]

        for label, field_name in stock_fields:
            scroll_layout.addWidget(QLabel(label), row, 0)
            fields[field_name] = QLineEdit()
            scroll_layout.addWidget(fields[field_name], row, 1)
            row += 1

        # Location Information
        location_label = QLabel("LOCATION INFORMATION")
        location_label.setFont(font)
        scroll_layout.addWidget(location_label, row, 0, 1, 2)
        row += 1

        location_fields = [
            ('Location*', 'location'),
            ('Rack', 'rack'),
            ('Row', 'row'),
            ('Bin', 'bin'),
        ]

        for label, field_name in location_fields:
            scroll_layout.addWidget(QLabel(label), row, 0)
            fields[field_name] = QLineEdit()
            scroll_layout.addWidget(fields[field_name], row, 1)
            row += 1

        # Pictures
        pictures_label = QLabel("PICTURES")
        pictures_label.setFont(font)
        scroll_layout.addWidget(pictures_label, row, 0, 1, 2)
        row += 1

        fields['picture_1'] = QLineEdit()
        fields['picture_2'] = QLineEdit()

        scroll_layout.addWidget(QLabel("Picture 1:"), row, 0)
        pic1_layout = QHBoxLayout()
        pic1_layout.addWidget(fields['picture_1'])
        pic1_browse_btn = QPushButton("Browse")
        pic1_browse_btn.clicked.connect(lambda: self.browse_image(fields['picture_1']))
        pic1_layout.addWidget(pic1_browse_btn)
        pic1_widget = QWidget()
        pic1_widget.setLayout(pic1_layout)
        scroll_layout.addWidget(pic1_widget, row, 1)
        row += 1

        scroll_layout.addWidget(QLabel("Picture 2:"), row, 0)
        pic2_layout = QHBoxLayout()
        pic2_layout.addWidget(fields['picture_2'])
        pic2_browse_btn = QPushButton("Browse")
        pic2_browse_btn.clicked.connect(lambda: self.browse_image(fields['picture_2']))
        pic2_layout.addWidget(pic2_browse_btn)
        pic2_widget = QWidget()
        pic2_widget.setLayout(pic2_layout)
        scroll_layout.addWidget(pic2_widget, row, 1)
        row += 1

        # Notes
        scroll_layout.addWidget(QLabel("Notes:"), row, 0, Qt.AlignTop)
        fields['notes'] = QTextEdit()
        fields['notes'].setMaximumHeight(100)
        scroll_layout.addWidget(fields['notes'], row, 1)
        row += 1

        # Buttons
        btn_layout = QHBoxLayout()

        def save_part():
            try:
                # Validate required fields
                required = ['name', 'part_number', 'engineering_system',
                        'unit_of_measure', 'quantity_in_stock', 'minimum_stock', 'location']

                for field in required:
                    if field in ['notes', 'picture_1', 'picture_2']:
                        continue
                    value = fields[field].text() if hasattr(fields[field], 'text') else ''
                    if not value:
                        QMessageBox.critical(dialog, "Error", f"Please fill in: {field.replace('_', ' ').title()}")
                        return

                # Read image files as binary data
                pic1_path = fields['picture_1'].text()
                pic2_path = fields['picture_2'].text()

                pic1_data = None
                pic2_data = None

                if pic1_path and os.path.exists(pic1_path):
                    with open(pic1_path, 'rb') as f:
                        pic1_data = f.read()

                if pic2_path and os.path.exists(pic2_path):
                    with open(pic2_path, 'rb') as f:
                        pic2_data = f.read()

                # Insert into database using connection pool
                notes_text = fields['notes'].toPlainText() if 'notes' in fields else ''

                # Use connection pool to avoid SSL timeout issues
                with db_pool.get_cursor(commit=True) as cursor:
                    cursor.execute('''
                        INSERT INTO mro_inventory (
                            name, part_number, model_number, equipment, engineering_system,
                            unit_of_measure, quantity_in_stock, unit_price, minimum_stock,
                            supplier, location, rack, row, bin, picture_1_path, picture_2_path,
                            picture_1_data, picture_2_data, notes
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        fields['name'].text(),
                        fields['part_number'].text(),
                        fields['model_number'].text(),
                        fields['equipment'].text(),
                        fields['engineering_system'].text(),
                        fields['unit_of_measure'].text(),
                        float(fields['quantity_in_stock'].text() or 0),
                        float(fields['unit_price'].text() or 0),
                        float(fields['minimum_stock'].text() or 0),
                        fields['supplier'].text(),
                        fields['location'].text(),
                        fields['rack'].text(),
                        fields['row'].text(),
                        fields['bin'].text(),
                        pic1_path,
                        pic2_path,
                        pic1_data,
                        pic2_data,
                        notes_text
                    ))

                QMessageBox.information(dialog, "Success", "Part added successfully!")
                dialog.accept()
                self.refresh_mro_list()

            except Exception as e:
                error_msg = str(e).lower()
                if 'unique constraint' in error_msg or 'duplicate' in error_msg or 'already exists' in error_msg:
                    QMessageBox.critical(dialog, "Error", "Part number already exists!")
                elif 'ssl' in error_msg or 'connection' in error_msg:
                    QMessageBox.critical(dialog, "Database Connection Error",
                        "Failed to connect to database. This may be due to:\n"
                        "• Network connectivity issues\n"
                        "• SSL certificate problems\n"
                        "• Database timeout\n\n"
                        f"Technical details: {str(e)}\n\n"
                        "Please try again. If the problem persists, contact IT support.")
                else:
                    QMessageBox.critical(dialog, "Error", f"Failed to add part: {str(e)}")

        save_btn = QPushButton("Save Part")
        save_btn.clicked.connect(save_part)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        scroll_layout.addLayout(btn_layout, row, 0, 1, 2)

        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

        dialog.exec_()

    def browse_image(self, line_edit):
        """Browse for image file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.root,
            "Select Image",
            "",
            "Image files (*.png *.jpg *.jpeg *.gif *.bmp);;All files (*.*)"
        )
        if file_path:
            line_edit.setText(file_path)

    def edit_selected_part(self):
        """Edit selected part"""
        selected_items = self.mro_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self.root, "Warning", "Please select a part to edit")
            return

        item = selected_items[0]
        part_number = str(item.text(0)).strip()

        try:
            # Get full part data - use explicit column list to ensure correct order
            with db_pool.get_cursor(commit=False) as cursor:
                cursor.execute('''
                    SELECT id, name, part_number, model_number, equipment, engineering_system,
                           unit_of_measure, quantity_in_stock, unit_price, minimum_stock,
                           supplier, location, rack, row, bin, picture_1_path,
                           picture_2_path, picture_1_data, picture_2_data, notes,
                           last_updated, created_date, status
                    FROM mro_inventory WHERE part_number = %s
                ''', (part_number,))
                part_data = cursor.fetchone()

                if not part_data:
                    QMessageBox.critical(self.root, "Error",
                        f"Part not found in database.\n\n"
                        f"Part number from tree: '{part_number}'\n"
                        f"Length: {len(part_number)} characters\n\n"
                        f"Try clicking the Refresh button and then edit again.")
                    return

                # Extract all data while cursor is still active
                part_dict = dict(part_data)
        except Exception as e:
            QMessageBox.critical(self.root, "Database Error",
                f"Error loading part data: {str(e)}\n\n"
                f"Part number: '{part_number}'")
            return

        # Create edit dialog
        dialog = QDialog(self.root)
        dialog.setWindowTitle(f"Edit Part: {part_number}")
        dialog.resize(800, 900)
        dialog.setModal(True)

        # Main layout with scroll area
        main_layout = QVBoxLayout(dialog)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QGridLayout(scroll_widget)

        # Form fields
        fields = {}
        row = 0

        # Basic Information
        basic_label = QLabel("BASIC INFORMATION")
        font = QFont('Arial', 11, QFont.Bold)
        basic_label.setFont(font)
        scroll_layout.addWidget(basic_label, row, 0, 1, 2)
        row += 1

        field_configs = [
            ('Name*', 'name'),
            ('Part Number*', 'part_number'),
            ('Model Number', 'model_number'),
            ('Equipment', 'equipment'),
        ]

        for label, field_name in field_configs:
            scroll_layout.addWidget(QLabel(label), row, 0)
            fields[field_name] = QLineEdit()
            fields[field_name].setText(part_dict.get(field_name) or '')
            if field_name == 'part_number':
                fields[field_name].setReadOnly(True)
            scroll_layout.addWidget(fields[field_name], row, 1)
            row += 1

        # Engineering System
        scroll_layout.addWidget(QLabel("Engineering System*"), row, 0)
        fields['engineering_system'] = QComboBox()
        fields['engineering_system'].addItems(['Mechanical', 'Electrical', 'Pneumatic', 'Hydraulic'])
        fields['engineering_system'].setCurrentText(part_dict.get('engineering_system') or '')
        scroll_layout.addWidget(fields['engineering_system'], row, 1)
        row += 1

        # Stock Information
        stock_label = QLabel("STOCK INFORMATION")
        stock_label.setFont(font)
        scroll_layout.addWidget(stock_label, row, 0, 1, 2)
        row += 1

        stock_fields = [
            ('Unit of Measure*', 'unit_of_measure'),
            ('Quantity in Stock*', 'quantity_in_stock'),
            ('Unit Price ($)', 'unit_price'),
            ('Minimum Stock*', 'minimum_stock'),
            ('Supplier', 'supplier'),
        ]

        for label, field_name in stock_fields:
            scroll_layout.addWidget(QLabel(label), row, 0)
            fields[field_name] = QLineEdit()
            fields[field_name].setText(str(part_dict.get(field_name) or ''))
            scroll_layout.addWidget(fields[field_name], row, 1)
            row += 1

        # Location Information
        location_label = QLabel("LOCATION INFORMATION")
        location_label.setFont(font)
        scroll_layout.addWidget(location_label, row, 0, 1, 2)
        row += 1

        location_fields = [
            ('Location*', 'location'),
            ('Rack', 'rack'),
            ('Row', 'row'),
            ('Bin', 'bin'),
        ]

        for label, field_name in location_fields:
            scroll_layout.addWidget(QLabel(label), row, 0)
            fields[field_name] = QLineEdit()
            fields[field_name].setText(part_dict.get(field_name) or '')
            scroll_layout.addWidget(fields[field_name], row, 1)
            row += 1

        # Status
        scroll_layout.addWidget(QLabel("Status*"), row, 0)
        fields['status'] = QComboBox()
        fields['status'].addItems(['Active', 'Inactive'])
        fields['status'].setCurrentText(part_dict.get('status') or 'Active')
        scroll_layout.addWidget(fields['status'], row, 1)
        row += 1

        # Pictures
        pictures_label = QLabel("PICTURES")
        pictures_label.setFont(font)
        scroll_layout.addWidget(pictures_label, row, 0, 1, 2)
        row += 1

        # Initialize photo fields
        fields['picture_1'] = QLineEdit()
        fields['picture_2'] = QLineEdit()

        # Show current photo status
        pic1_status = "Photo stored in database" if part_dict.get('picture_1_data') else "No photo"
        scroll_layout.addWidget(QLabel("Picture 1:"), row, 0)
        pic1_layout = QHBoxLayout()
        pic1_status_label = QLabel(pic1_status)
        pic1_status_label.setStyleSheet("color: green;" if part_dict.get('picture_1_data') else "color: gray;")
        pic1_layout.addWidget(pic1_status_label)
        pic1_layout.addWidget(fields['picture_1'])
        pic1_browse_btn = QPushButton("Browse New")
        pic1_browse_btn.clicked.connect(lambda: self.browse_image(fields['picture_1']))
        pic1_layout.addWidget(pic1_browse_btn)
        pic1_widget = QWidget()
        pic1_widget.setLayout(pic1_layout)
        scroll_layout.addWidget(pic1_widget, row, 1)
        row += 1

        pic2_status = "Photo stored in database" if part_dict.get('picture_2_data') else "No photo"
        scroll_layout.addWidget(QLabel("Picture 2:"), row, 0)
        pic2_layout = QHBoxLayout()
        pic2_status_label = QLabel(pic2_status)
        pic2_status_label.setStyleSheet("color: green;" if part_dict.get('picture_2_data') else "color: gray;")
        pic2_layout.addWidget(pic2_status_label)
        pic2_layout.addWidget(fields['picture_2'])
        pic2_browse_btn = QPushButton("Browse New")
        pic2_browse_btn.clicked.connect(lambda: self.browse_image(fields['picture_2']))
        pic2_layout.addWidget(pic2_browse_btn)
        pic2_widget = QWidget()
        pic2_widget.setLayout(pic2_layout)
        scroll_layout.addWidget(pic2_widget, row, 1)
        row += 1

        # Notes
        scroll_layout.addWidget(QLabel("Notes:"), row, 0, Qt.AlignTop)
        fields['notes'] = QTextEdit()
        fields['notes'].setPlainText(part_dict.get('notes') or '')
        fields['notes'].setMaximumHeight(100)
        scroll_layout.addWidget(fields['notes'], row, 1)
        row += 1

        # Buttons
        btn_layout = QHBoxLayout()

        def update_part():
            try:
                # Read image files as binary data
                pic1_path = fields['picture_1'].text()
                pic2_path = fields['picture_2'].text()

                # Get existing photo data and paths from database first
                with db_pool.get_cursor(commit=False) as cursor:
                    cursor.execute('SELECT picture_1_path, picture_2_path, picture_1_data, picture_2_data FROM mro_inventory WHERE part_number = %s', (part_number,))
                    existing_data = cursor.fetchone()
                    existing_pic1_path = existing_data['picture_1_path'] if existing_data else None
                    existing_pic2_path = existing_data['picture_2_path'] if existing_data else None
                    existing_pic1_data = existing_data['picture_1_data'] if existing_data else None
                    existing_pic2_data = existing_data['picture_2_data'] if existing_data else None

                # Only read new photo data if a NEW file is selected
                final_pic1_path = existing_pic1_path
                final_pic2_path = existing_pic2_path
                pic1_data = existing_pic1_data
                pic2_data = existing_pic2_data

                # Check if user selected a new file for picture 1
                if pic1_path and os.path.exists(pic1_path):
                    with open(pic1_path, 'rb') as f:
                        pic1_data = f.read()
                    final_pic1_path = pic1_path

                # Check if user selected a new file for picture 2
                if pic2_path and os.path.exists(pic2_path):
                    with open(pic2_path, 'rb') as f:
                        pic2_data = f.read()
                    final_pic2_path = pic2_path

                notes_text = fields['notes'].toPlainText()

                # Get engineering system value
                eng_system_value = fields['engineering_system'].currentText() if isinstance(fields['engineering_system'], QComboBox) else fields['engineering_system'].text()
                status_value = fields['status'].currentText() if isinstance(fields['status'], QComboBox) else fields['status'].text()

                with db_pool.get_cursor(commit=True) as cursor:
                    cursor.execute('''
                        UPDATE mro_inventory SET
                            name = %s, model_number = %s, equipment = %s, engineering_system = %s,
                            unit_of_measure = %s, quantity_in_stock = %s, unit_price = %s,
                            minimum_stock = %s, supplier = %s, location = %s, rack = %s,
                            row = %s, bin = %s, picture_1_path = %s, picture_2_path = %s,
                            picture_1_data = %s, picture_2_data = %s,
                            notes = %s, status = %s, last_updated = %s
                        WHERE part_number = %s
                    ''', (
                        fields['name'].text(),
                        fields['model_number'].text(),
                        fields['equipment'].text(),
                        eng_system_value,
                        fields['unit_of_measure'].text(),
                        float(fields['quantity_in_stock'].text() or 0),
                        float(fields['unit_price'].text() or 0),
                        float(fields['minimum_stock'].text() or 0),
                        fields['supplier'].text(),
                        fields['location'].text(),
                        fields['rack'].text(),
                        fields['row'].text(),
                        fields['bin'].text(),
                        final_pic1_path,
                        final_pic2_path,
                        pic1_data,
                        pic2_data,
                        notes_text,
                        status_value,
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        part_number
                    ))

                QMessageBox.information(dialog, "Success", "Part updated successfully!")
                dialog.accept()
                self.refresh_mro_list()

            except Exception as e:
                QMessageBox.critical(dialog, "Error", f"Failed to update part: {str(e)}")

        update_btn = QPushButton("Update Part")
        update_btn.clicked.connect(update_part)
        btn_layout.addWidget(update_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        scroll_layout.addLayout(btn_layout, row, 0, 1, 2)

        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

        dialog.exec_()

    def delete_selected_part(self):
        """Delete selected part"""
        selected_items = self.mro_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self.root, "Warning", "Please select a part to delete")
            return

        item = selected_items[0]
        part_number = str(item.text(0))
        part_name = item.text(1)

        result = QMessageBox.question(
            self.root,
            "Confirm Delete",
            f"Are you sure you want to delete:\n\n"
            f"Part Number: {part_number}\n"
            f"Name: {part_name}\n\n"
            f"This action cannot be undone!",
            QMessageBox.Yes | QMessageBox.No
        )

        if result == QMessageBox.Yes:
            try:
                with db_pool.get_cursor(commit=True) as cursor:
                    cursor.execute('DELETE FROM mro_inventory WHERE part_number = %s', (part_number,))
                QMessageBox.information(self.root, "Success", "Part deleted successfully!")
                self.refresh_mro_list()
            except Exception as e:
                QMessageBox.critical(self.root, "Error", f"Failed to delete part: {str(e)}")


    def view_part_details(self):
        """Enhanced part details view with CM history integration"""
        selected_items = self.mro_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self.root, "Warning", "Please select a part to view")
            return

        item = selected_items[0]
        part_number = str(item.text(0)).strip()

        try:
            # Get full part data
            with db_pool.get_cursor(commit=False) as cursor:
                cursor.execute('''
                    SELECT id, name, part_number, model_number, equipment, engineering_system,
                           unit_of_measure, quantity_in_stock, unit_price, minimum_stock,
                           supplier, location, rack, row, bin, picture_1_path,
                           picture_2_path, picture_1_data, picture_2_data, notes,
                           last_updated, created_date, status
                    FROM mro_inventory WHERE part_number = %s
                ''', (part_number,))
                part_data = cursor.fetchone()

                if not part_data:
                    QMessageBox.critical(self.root, "Error",
                        f"Part not found in database.\n\n"
                        f"Part number from tree: '{part_number}'\n"
                        f"Length: {len(part_number)} characters\n\n"
                        f"Try clicking the Refresh button and then try again.")
                    return

                # Extract all data
                part_dict = dict(part_data)
        except Exception as e:
            QMessageBox.critical(self.root, "Database Error",
                f"Error loading part details: {str(e)}\n\n"
                f"Part number: '{part_number}'")
            return

        # Create details dialog
        dialog = QDialog(self.root)
        dialog.setWindowTitle(f"Part Details - {part_number}")
        dialog.resize(900, 700)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        # Create tab widget
        tab_widget = QTabWidget()

        # ============================================================
        # TAB 1: Part Information
        # ============================================================
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QGridLayout(scroll_widget)

        row = 0

        # Display part information
        fields = [
            ("Part Number:", part_dict['part_number']),
            ("Part Name:", part_dict['name']),
            ("Model Number:", part_dict['model_number'] or 'N/A'),
            ("Equipment:", part_dict['equipment'] or 'N/A'),
            ("Engineering System:", part_dict['engineering_system'] or 'N/A'),
            ("", ""),  # Spacer
            ("Quantity in Stock:", f"{part_dict['quantity_in_stock']} {part_dict['unit_of_measure']}"),
            ("Minimum Stock:", f"{part_dict['minimum_stock']} {part_dict['unit_of_measure']}"),
            ("Unit of Measure:", part_dict['unit_of_measure']),
            ("Unit Price:", f"${part_dict['unit_price']:.2f}"),
            ("Total Value:", f"${part_dict['quantity_in_stock'] * part_dict['unit_price']:.2f}"),
            ("", ""),  # Spacer
            ("Supplier:", part_dict['supplier'] or 'N/A'),
            ("Location:", part_dict['location'] or 'N/A'),
            ("Rack:", part_dict['rack'] or 'N/A'),
            ("Row:", part_dict['row'] or 'N/A'),
            ("Bin:", part_dict['bin'] or 'N/A'),
            ("", ""),  # Spacer
            ("Status:", part_dict['status']),
            ("Created Date:", part_dict['created_date'][:10] if part_dict['created_date'] else 'N/A'),
            ("Last Updated:", part_dict['last_updated'][:10] if part_dict['last_updated'] else 'N/A'),
        ]

        for label, value in fields:
            if label:  # Not a spacer
                label_widget = QLabel(label)
                label_widget.setFont(QFont('Arial', 10, QFont.Bold))
                scroll_layout.addWidget(label_widget, row, 0, Qt.AlignTop)

                value_widget = QLabel(str(value))
                value_widget.setFont(QFont('Arial', 10))
                value_widget.setWordWrap(True)
                scroll_layout.addWidget(value_widget, row, 1, Qt.AlignTop)
            row += 1

        # Notes section
        if part_dict.get('notes'):
            label_widget = QLabel("Notes:")
            label_widget.setFont(QFont('Arial', 10, QFont.Bold))
            scroll_layout.addWidget(label_widget, row, 0, Qt.AlignTop)

            notes_display = QTextEdit()
            notes_display.setPlainText(part_dict['notes'])
            notes_display.setReadOnly(True)
            notes_display.setMaximumHeight(100)
            scroll_layout.addWidget(notes_display, row, 1)
            row += 1

        # Pictures section
        row += 1
        pic1_data = part_dict.get('picture_1_data')
        pic2_data = part_dict.get('picture_2_data')
        pic1_path = part_dict.get('picture_1_path')
        pic2_path = part_dict.get('picture_2_path')

        if pic1_data or pic2_data or pic1_path or pic2_path:
            label_widget = QLabel("Pictures:")
            label_widget.setFont(QFont('Arial', 10, QFont.Bold))
            scroll_layout.addWidget(label_widget, row, 0, Qt.AlignTop)

            pic_layout = QHBoxLayout()

            # Display Picture 1
            if pic1_data:
                try:
                    img1 = Image.open(io.BytesIO(pic1_data))
                    img1.thumbnail((200, 200))
                    img1 = img1.convert("RGBA")
                    data = img1.tobytes("raw", "RGBA")
                    qimage = QImage(data, img1.size[0], img1.size[1], QImage.Format_RGBA8888)
                    pixmap = QPixmap.fromImage(qimage)
                    label1 = QLabel()
                    label1.setPixmap(pixmap)
                    pic_layout.addWidget(label1)
                except Exception as e:
                    error_label = QLabel("Picture 1: Error loading")
                    error_label.setStyleSheet("color: red;")
                    pic_layout.addWidget(error_label)
            elif pic1_path and os.path.exists(pic1_path):
                try:
                    pixmap = QPixmap(pic1_path)
                    pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    label1 = QLabel()
                    label1.setPixmap(pixmap)
                    pic_layout.addWidget(label1)
                except Exception as e:
                    error_label = QLabel("Picture 1: Error loading")
                    error_label.setStyleSheet("color: red;")
                    pic_layout.addWidget(error_label)

            # Display Picture 2
            if pic2_data:
                try:
                    img2 = Image.open(io.BytesIO(pic2_data))
                    img2.thumbnail((200, 200))
                    img2 = img2.convert("RGBA")
                    data = img2.tobytes("raw", "RGBA")
                    qimage = QImage(data, img2.size[0], img2.size[1], QImage.Format_RGBA8888)
                    pixmap = QPixmap.fromImage(qimage)
                    label2 = QLabel()
                    label2.setPixmap(pixmap)
                    pic_layout.addWidget(label2)
                except Exception as e:
                    error_label = QLabel("Picture 2: Error loading")
                    error_label.setStyleSheet("color: red;")
                    pic_layout.addWidget(error_label)
            elif pic2_path and os.path.exists(pic2_path):
                try:
                    pixmap = QPixmap(pic2_path)
                    pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    label2 = QLabel()
                    label2.setPixmap(pixmap)
                    pic_layout.addWidget(label2)
                except Exception as e:
                    error_label = QLabel("Picture 2: Error loading")
                    error_label.setStyleSheet("color: red;")
                    pic_layout.addWidget(error_label)

            pic_widget = QWidget()
            pic_widget.setLayout(pic_layout)
            scroll_layout.addWidget(pic_widget, row, 1)
            row += 1

        # Stock status indicator
        row += 1
        qty_stock = part_dict['quantity_in_stock']
        min_stock = part_dict['minimum_stock']

        if qty_stock < min_stock:
            status_text = "LOW STOCK - Reorder Recommended"
            status_color = 'red'
        elif qty_stock < min_stock * 1.5:
            status_text = "Stock Getting Low"
            status_color = 'orange'
        else:
            status_text = "Stock Level OK"
            status_color = 'green'

        status_label = QLabel(status_text)
        status_label.setFont(QFont('Arial', 11, QFont.Bold))
        status_label.setStyleSheet(f"color: {status_color};")
        scroll_layout.addWidget(status_label, row, 0, 1, 2, Qt.AlignCenter)

        scroll_area.setWidget(scroll_widget)
        info_layout.addWidget(scroll_area)
        tab_widget.addTab(info_widget, "Part Information")

        # ============================================================
        # TAB 2: CM Usage History
        # ============================================================
        history_widget = QWidget()
        history_layout = QVBoxLayout(history_widget)

        header_label = QLabel(f"Corrective Maintenance History for {part_number}")
        header_label.setFont(QFont('Arial', 11, QFont.Bold))
        history_layout.addWidget(header_label)

        try:
            # Get CM usage data
            with db_pool.get_cursor(commit=False) as cursor:
                cursor.execute('''
                    SELECT
                        cp.cm_number,
                        cm.description,
                        cm.bfm_equipment_no,
                        cp.quantity_used,
                        cp.total_cost,
                        cp.recorded_date,
                        cp.recorded_by,
                        cm.status,
                        cp.notes
                    FROM cm_parts_used cp
                    LEFT JOIN corrective_maintenance cm ON cp.cm_number = cm.cm_number
                    WHERE cp.part_number = %s
                    ORDER BY cp.recorded_date DESC
                    LIMIT 50
                ''', (part_number,))

                cm_history = cursor.fetchall()

                # Statistics
                stats_group = QGroupBox("Usage Statistics")
                stats_layout = QVBoxLayout()

                if cm_history:
                    total_cms = len(cm_history)
                    total_qty_used = sum(row['quantity_used'] for row in cm_history)
                    total_cost = sum(row['total_cost'] or 0 for row in cm_history)

                    stats_text = (f"Total CMs: {total_cms} | "
                                f"Total Quantity Used: {total_qty_used:.2f} {part_dict['unit_of_measure']} | "
                                f"Total Cost: ${total_cost:.2f}")
                    stats_layout.addWidget(QLabel(stats_text))

                    # Recent usage (last 30 days)
                    cursor.execute('''
                        SELECT SUM(quantity_used)
                        FROM cm_parts_used
                        WHERE part_number = %s
                        AND recorded_date::timestamp >= CURRENT_DATE - INTERVAL '30 days'
                    ''', (part_number,))

                    recent_result = cursor.fetchone()
                    recent_usage = recent_result['sum'] if recent_result and recent_result['sum'] else 0
                    recent_label = QLabel(f"Usage Last 30 Days: {recent_usage:.2f} {part_dict['unit_of_measure']}")
                    recent_label.setFont(QFont('Arial', 9, QFont.StyleItalic))
                    stats_layout.addWidget(recent_label)
                else:
                    no_data_label = QLabel("No CM usage history available")
                    no_data_label.setFont(QFont('Arial', 10, QFont.StyleItalic))
                    stats_layout.addWidget(no_data_label)

                stats_group.setLayout(stats_layout)
                history_layout.addWidget(stats_group)
        except Exception as e:
            QMessageBox.critical(dialog, "Database Error", f"Error loading CM history: {str(e)}")
            return

        # History treeview
        history_tree = QTreeWidget()
        columns = ['CM #', 'Description', 'Equipment', 'Qty Used', 'Cost', 'Date', 'Technician', 'Status', 'Notes']
        history_tree.setColumnCount(len(columns))
        history_tree.setHeaderLabels(columns)

        for row in cm_history:
            desc = row['description']
            if desc and len(desc) > 30:
                desc = desc[:30] + '...'
            else:
                desc = desc or 'N/A'

            notes = row['notes']
            if notes and len(notes) > 20:
                notes = notes[:20] + '...'
            else:
                notes = notes or ''

            item = QTreeWidgetItem([
                row['cm_number'],
                desc,
                row['bfm_equipment_no'] or 'N/A',
                f"{row['quantity_used']:.2f}",
                f"${row['total_cost']:.2f}" if row['total_cost'] else '$0.00',
                row['recorded_date'][:10] if row['recorded_date'] else '',
                row['recorded_by'] or 'N/A',
                row['status'] or 'Unknown',
                notes
            ])
            history_tree.addTopLevelItem(item)

        history_layout.addWidget(history_tree)
        tab_widget.addTab(history_widget, "CM Usage History")

        # ============================================================
        # TAB 3: Transaction History
        # ============================================================
        trans_widget = QWidget()
        trans_layout = QVBoxLayout(trans_widget)

        trans_header = QLabel(f"All Stock Transactions for {part_number}")
        trans_header.setFont(QFont('Arial', 11, QFont.Bold))
        trans_layout.addWidget(trans_header)

        # Get all transactions
        with db_pool.get_cursor(commit=False) as cursor:
            cursor.execute('''
                SELECT
                    transaction_date,
                    transaction_type,
                    quantity,
                    technician_name,
                    work_order,
                    notes
                FROM mro_stock_transactions
                WHERE part_number = %s
                ORDER BY transaction_date DESC
                LIMIT 100
            ''', (part_number,))

            transactions = cursor.fetchall()

            # Transactions treeview
            trans_tree = QTreeWidget()
            trans_columns = ['Date', 'Type', 'Quantity', 'Technician', 'Work Order', 'Notes']
            trans_tree.setColumnCount(len(trans_columns))
            trans_tree.setHeaderLabels(trans_columns)

            for row in transactions:
                qty = row['quantity']
                qty_display = f"+{qty:.2f}" if qty > 0 else f"{qty:.2f}"

                item = QTreeWidgetItem([
                    row['transaction_date'][:19] if row['transaction_date'] else '',
                    row['transaction_type'] or 'N/A',
                    qty_display,
                    row['technician_name'] or 'N/A',
                    row['work_order'] or 'N/A',
                    row['notes'] or ''
                ])

                # Color code based on transaction type
                if qty > 0:
                    for i in range(item.columnCount()):
                        item.setForeground(i, QColor('green'))
                else:
                    for i in range(item.columnCount()):
                        item.setForeground(i, QColor('red'))

                trans_tree.addTopLevelItem(item)

        trans_layout.addWidget(trans_tree)
        tab_widget.addTab(trans_widget, "All Transactions")

        # Add tab widget to main layout
        main_layout.addWidget(tab_widget)

        # Bottom buttons
        button_layout = QHBoxLayout()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        button_layout.addStretch()
        button_layout.addWidget(close_btn)

        main_layout.addLayout(button_layout)

        dialog.exec_()


    def show_parts_usage_report(self):
        """Show comprehensive parts usage report"""
        dialog = QDialog(self.root)
        dialog.setWindowTitle("Parts Usage by CM Report")
        dialog.resize(900, 600)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        title_label = QLabel("Parts Consumption Analysis")
        title_label.setFont(QFont('Arial', 12, QFont.Bold))
        main_layout.addWidget(title_label)

        try:
            # Get summary data
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT
                    mi.part_number,
                    mi.name,
                    SUM(cp.quantity_used) as total_qty,
                    COUNT(DISTINCT cp.cm_number) as cm_count,
                    SUM(cp.total_cost) as total_cost
                FROM cm_parts_used cp
                JOIN mro_inventory mi ON cp.part_number = mi.part_number
                WHERE cp.recorded_date::timestamp >= CURRENT_DATE - INTERVAL '90 days'
                GROUP BY mi.part_number, mi.name
                ORDER BY total_cost DESC
                LIMIT 50
            ''')

            usage_data = cursor.fetchall()
        except Exception as e:
            self.conn.rollback()
            QMessageBox.critical(dialog, "Database Error", f"Error loading usage report: {str(e)}")
            dialog.reject()
            return

        # Display in treeview
        tree = QTreeWidget()
        columns = ['Part #', 'Part Name', 'Total Qty Used', 'CMs Used In', 'Total Cost']
        tree.setColumnCount(len(columns))
        tree.setHeaderLabels(columns)

        tree.setColumnWidth(0, 120)
        tree.setColumnWidth(1, 250)
        tree.setColumnWidth(2, 120)
        tree.setColumnWidth(3, 100)
        tree.setColumnWidth(4, 120)

        for row in usage_data:
            item = QTreeWidgetItem([
                row[0],
                row[1],
                f"{float(row[2]):.2f}",
                str(row[3]),
                f"${float(row[4]):.2f}"
            ])
            tree.addTopLevelItem(item)

        main_layout.addWidget(tree)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        main_layout.addWidget(close_btn)

        dialog.exec_()

    def import_from_file(self):
        """Import parts from inventory.txt or CSV file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self.root,
            "Select Inventory File",
            "",
            "Text files (*.txt);;CSV files (*.csv);;All files (*.*)"
        )

        if not file_path:
            return

        try:
            imported_count = 0
            skipped_count = 0

            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.endswith('.csv'):
                    reader = csv.DictReader(f)
                    for row in reader:
                        try:
                            self.import_part_from_dict(row)
                            imported_count += 1
                        except:
                            skipped_count += 1
                else:
                    # Parse text file format
                    QMessageBox.information(self.root, "Info",
                                      "Please use CSV format for bulk import.\n\n"
                                      "Required columns:\n"
                                      "Name, Part Number, Model Number, Equipment, "
                                      "Engineering System, Unit of Measure, Quantity in Stock, "
                                      "Unit Price, Minimum Stock, Supplier, Location, Rack, Row, Bin")
                    return

            self.conn.commit()
            QMessageBox.information(self.root, "Import Complete",
                              f"Successfully imported: {imported_count} parts\n"
                              f"Skipped (duplicates/errors): {skipped_count} parts")
            self.refresh_mro_list()

        except Exception as e:
            QMessageBox.critical(self.root, "Import Error", f"Failed to import file:\n{str(e)}")

    def import_part_from_dict(self, data):
        """Import a single part from dictionary"""
        cursor = self.conn.cursor()

        cursor.execute('''
            INSERT INTO mro_inventory (
                name, part_number, model_number, equipment, engineering_system,
                unit_of_measure, quantity_in_stock, unit_price, minimum_stock,
                supplier, location, rack, row, bin
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (part_number) DO NOTHING
        ''', (
            data.get('Name', ''),
            data.get('Part Number', ''),
            data.get('Model Number', ''),
            data.get('Equipment', ''),
            data.get('Engineering System', ''),
            data.get('Unit of Measure', ''),
            float(data.get('Quantity in Stock', 0) or 0),
            float(data.get('Unit Price', 0) or 0),
            float(data.get('Minimum Stock', 0) or 0),
            data.get('Supplier', ''),
            data.get('Location', ''),
            data.get('Rack', ''),
            data.get('Row', ''),
            data.get('Bin', '')
        ))

    def export_to_csv(self):
        """Export inventory to CSV"""
        file_path, _ = QFileDialog.getSaveFileName(
            self.root,
            "Export Inventory",
            "",
            "CSV files (*.csv);;All files (*.*)"
        )

        if not file_path:
            return

        try:
            cursor = self.conn.cursor()
            # Select specific columns for export (exclude binary picture data)
            cursor.execute('''
                SELECT id, name, part_number, model_number, equipment, engineering_system,
                       unit_of_measure, quantity_in_stock, unit_price, minimum_stock,
                       supplier, location, rack, row, bin, picture_1_path, picture_2_path,
                       notes, last_updated, created_date, status
                FROM mro_inventory ORDER BY part_number
            ''')
            rows = cursor.fetchall()

            columns = ['ID', 'Name', 'Part Number', 'Model Number', 'Equipment',
                      'Engineering System', 'Unit of Measure', 'Quantity in Stock',
                      'Unit Price', 'Minimum Stock', 'Supplier', 'Location', 'Rack',
                      'Row', 'Bin', 'Picture 1 Path', 'Picture 2 Path', 'Notes',
                      'Last Updated', 'Created Date', 'Status']

            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(columns)
                writer.writerows(rows)

            QMessageBox.information(self.root, "Success", f"Inventory exported to:\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self.root, "Export Error", f"Failed to export:\n{str(e)}")

    def generate_stock_report(self):
        """Generate comprehensive stock report"""
        dialog = QDialog(self.root)
        dialog.setWindowTitle("Stock Report")
        dialog.resize(900, 700)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        # Report text
        report_text = QTextEdit()
        report_text.setReadOnly(True)
        report_text.setFont(QFont('Courier', 10))

        # Generate report
        cursor = self.conn.cursor()

        report = []
        report.append("=" * 80)
        report.append("MRO INVENTORY STOCK REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 80)
        report.append("")

        # Summary statistics
        cursor.execute("SELECT COUNT(*) FROM mro_inventory WHERE status = 'Active'")
        total_parts = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(quantity_in_stock * unit_price) FROM mro_inventory WHERE status = 'Active'")
        total_value = cursor.fetchone()[0] or 0

        cursor.execute('''
            SELECT COUNT(*) FROM mro_inventory
            WHERE quantity_in_stock < minimum_stock AND status = 'Active'
        ''')
        low_stock_count = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(quantity_in_stock) FROM mro_inventory WHERE status = 'Active'")
        total_quantity = cursor.fetchone()[0] or 0

        report.append("SUMMARY")
        report.append("-" * 80)
        report.append(f"Total Active Parts: {total_parts}")
        report.append(f"Total Quantity in Stock: {total_quantity:,.1f}")
        report.append(f"Total Inventory Value: ${total_value:,.2f}")
        report.append(f"Low Stock Items: {low_stock_count}")
        report.append("")

        # Low stock items
        if low_stock_count > 0:
            report.append("LOW STOCK ALERTS")
            report.append("-" * 80)
            cursor.execute('''
                SELECT part_number, name, quantity_in_stock, minimum_stock,
                       unit_of_measure, location
                FROM mro_inventory
                WHERE quantity_in_stock < minimum_stock AND status = 'Active'
                ORDER BY (minimum_stock - quantity_in_stock) DESC
            ''')

            for row in cursor.fetchall():
                part_no, name, qty, min_qty, unit, loc = row
                deficit = min_qty - qty
                report.append(f"  Part: {part_no} - {name}")
                report.append(f"  Current: {qty} {unit} | Minimum: {min_qty} {unit} | Deficit: {deficit} {unit}")
                report.append(f"  Location: {loc}")
                report.append("")

        # Inventory by system
        report.append("INVENTORY BY ENGINEERING SYSTEM")
        report.append("-" * 80)
        cursor.execute('''
            SELECT engineering_system, COUNT(*), SUM(quantity_in_stock * unit_price)
            FROM mro_inventory
            WHERE status = 'Active'
            GROUP BY engineering_system
            ORDER BY engineering_system
        ''')

        for row in cursor.fetchall():
            system, count, value = row
            report.append(f"  {system or 'Unknown'}: {count} parts, ${value or 0:,.2f} value")

        report.append("")

        # CM Parts Usage by Month
        report.append("CM PARTS USAGE - MONTHLY BREAKDOWN")
        report.append("-" * 80)

        try:
            # Get monthly summary
            cursor.execute('''
                SELECT
                    TO_CHAR(recorded_date::timestamp, 'YYYY-MM') as month,
                    COUNT(DISTINCT cm_number) as cm_count,
                    COUNT(*) as parts_entries,
                    SUM(quantity_used) as total_quantity,
                    SUM(total_cost) as total_cost
                FROM cm_parts_used
                GROUP BY TO_CHAR(recorded_date::timestamp, 'YYYY-MM')
                ORDER BY month DESC
                LIMIT 12
            ''')

            monthly_data = cursor.fetchall()

            if monthly_data:
                report.append("")
                report.append(f"{'Month':<12} {'CMs':<8} {'Parts':<10} {'Qty Used':<15} {'Total Cost':<15}")
                report.append("-" * 80)

                grand_total_cost = 0
                for row in monthly_data:
                    month = row[0]
                    cm_count = row[1]
                    parts_entries = row[2]
                    total_qty = float(row[3]) if row[3] else 0
                    total_cost = float(row[4]) if row[4] else 0
                    grand_total_cost += total_cost

                    report.append(f"{month:<12} {cm_count:<8} {parts_entries:<10} {total_qty:<15.1f} ${total_cost:<14,.2f}")

                report.append("-" * 80)
                report.append(f"{'Total Cost (Last 12 Months):':<60} ${grand_total_cost:,.2f}")
            else:
                report.append("  No CM parts usage data available")

            report.append("")

            # Top 10 most used parts
            report.append("TOP 10 PARTS USED IN CMs (ALL TIME)")
            report.append("-" * 80)

            cursor.execute('''
                SELECT
                    cpu.part_number,
                    mi.name,
                    COUNT(DISTINCT cpu.cm_number) as cm_count,
                    SUM(cpu.quantity_used) as total_qty,
                    SUM(cpu.total_cost) as total_cost
                FROM cm_parts_used cpu
                LEFT JOIN mro_inventory mi ON cpu.part_number = mi.part_number
                GROUP BY cpu.part_number, mi.name
                ORDER BY total_qty DESC
                LIMIT 10
            ''')

            top_parts = cursor.fetchall()

            if top_parts:
                report.append("")
                report.append(f"{'Part Number':<15} {'Description':<30} {'CMs':<8} {'Qty':<12} {'Cost':<15}")
                report.append("-" * 80)

                for row in top_parts:
                    part_num = row[0]
                    name = (row[1] or 'N/A')[:28]
                    cm_count = row[2]
                    qty = float(row[3]) if row[3] else 0
                    cost = float(row[4]) if row[4] else 0

                    report.append(f"{part_num:<15} {name:<30} {cm_count:<8} {qty:<12.1f} ${cost:<14,.2f}")
            else:
                report.append("  No parts usage data available")

        except Exception as e:
            report.append(f"  Error loading CM parts data: {str(e)}")

        report.append("")
        report.append("=" * 80)
        report.append("END OF REPORT")
        report.append("=" * 80)

        report_text.setPlainText('\n'.join(report))
        main_layout.addWidget(report_text)

        # Export button
        def export_report():
            file_path, _ = QFileDialog.getSaveFileName(
                dialog,
                "Export Stock Report",
                "",
                "Text files (*.txt);;All files (*.*)"
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(report))
                QMessageBox.information(dialog, "Success", f"Report exported to:\n{file_path}")

        export_btn = QPushButton("Export Report")
        export_btn.clicked.connect(export_report)
        main_layout.addWidget(export_btn)

        dialog.exec_()

    def show_low_stock(self):
        """Show low stock alert dialog"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT part_number, name, quantity_in_stock, minimum_stock,
                   unit_of_measure, location, supplier
            FROM mro_inventory
            WHERE quantity_in_stock < minimum_stock AND status = 'Active'
            ORDER BY (minimum_stock - quantity_in_stock) DESC
        ''')

        low_stock_items = cursor.fetchall()

        if not low_stock_items:
            QMessageBox.information(self.root, "Stock Status", "All items are adequately stocked!")
            return

        # Create alert dialog
        dialog = QDialog(self.root)
        dialog.setWindowTitle(f"Low Stock Alert ({len(low_stock_items)} items)")
        dialog.resize(1000, 600)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        alert_label = QLabel(f"{len(low_stock_items)} items are below minimum stock level")
        alert_label.setFont(QFont('Arial', 12, QFont.Bold))
        alert_label.setStyleSheet("color: red;")
        main_layout.addWidget(alert_label)

        # Create treeview
        tree = QTreeWidget()
        columns = ['Part Number', 'Name', 'Current', 'Minimum', 'Deficit',
                  'Unit', 'Location', 'Supplier']
        tree.setColumnCount(len(columns))
        tree.setHeaderLabels(columns)

        for col_idx in range(len(columns)):
            tree.setColumnWidth(col_idx, 120)

        # Populate tree
        for item in low_stock_items:
            part_no, name, current, minimum, unit, location, supplier = item
            deficit = minimum - current
            tree_item = QTreeWidgetItem([
                part_no, name, f"{current:.1f}", f"{minimum:.1f}",
                f"{deficit:.1f}", unit, location or 'N/A', supplier or 'N/A'
            ])
            tree.addTopLevelItem(tree_item)

        main_layout.addWidget(tree)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        main_layout.addWidget(close_btn)

        dialog.exec_()

    def refresh_mro_list(self):
        """Refresh MRO inventory list"""
        self.update_location_filter()
        self.filter_mro_list()
        self.update_mro_statistics()

    def filter_mro_list(self, *args):
        """Filter MRO list based on search and filters - OPTIMIZED"""
        search_term = self.mro_search_entry.text().lower()
        system_filter = self.mro_system_filter.currentText()
        status_filter = self.mro_status_filter.currentText()
        location_filter = self.mro_location_filter.currentText()

        # Clear existing items
        self.mro_tree.clear()

        # OPTIMIZED: Only select columns needed for display
        query = '''SELECT part_number, name, model_number, equipment, engineering_system,
                          unit_of_measure, quantity_in_stock, unit_price, minimum_stock,
                          location, status
                   FROM mro_inventory WHERE 1=1'''
        params = []

        # OPTIMIZED: Use LOWER() which now has functional indexes
        if system_filter != 'All':
            query += ' AND LOWER(engineering_system) = LOWER(%s)'
            params.append(system_filter)

        if status_filter == 'Low Stock':
            query += ' AND quantity_in_stock < minimum_stock'
        elif status_filter != 'All':
            query += ' AND LOWER(status) = LOWER(%s)'
            params.append(status_filter)

        # Location filter
        if location_filter != 'All':
            query += ' AND LOWER(location) = LOWER(%s)'
            params.append(location_filter)

        if search_term:
            query += ''' AND (
                LOWER(name) LIKE %s OR
                LOWER(part_number) LIKE %s OR
                LOWER(model_number) LIKE %s OR
                LOWER(equipment) LIKE %s OR
                LOWER(location) LIKE %s
            )'''
            search_param = f'%{search_term}%'
            params.extend([search_param] * 5)

        query += ' ORDER BY part_number'

        with db_pool.get_cursor(commit=False) as cursor:
            cursor.execute(query, params)

            for idx, row in enumerate(cursor.fetchall()):
                part_number = row['part_number']
                name = row['name']
                model_number = row['model_number']
                equipment = row['equipment']
                engineering_system = row['engineering_system']
                unit_of_measure = row['unit_of_measure']
                qty = float(row['quantity_in_stock'])
                unit_price = float(row['unit_price'])
                min_stock = float(row['minimum_stock'])
                location = row['location']
                status = row['status']

                # Determine display status
                display_status = 'LOW' if qty < min_stock else status

                item = QTreeWidgetItem([
                    part_number,
                    name,
                    model_number or '',
                    equipment or '',
                    engineering_system or '',
                    f"{qty:.1f}",
                    f"{min_stock:.1f}",
                    unit_of_measure or '',
                    f"${unit_price:.2f}",
                    location or '',
                    display_status
                ])

                # Color low stock items
                if qty < min_stock:
                    for col_idx in range(item.columnCount()):
                        item.setBackground(col_idx, QColor(255, 204, 204))

                self.mro_tree.addTopLevelItem(item)

                # Process events to keep UI responsive
                if idx % 50 == 0:
                    QApplication.processEvents()

    def update_location_filter(self):
        """Update location filter dropdown with unique locations from database"""
        try:
            with db_pool.get_cursor(commit=False) as cursor:
                cursor.execute('''
                    SELECT DISTINCT location
                    FROM mro_inventory
                    WHERE location IS NOT NULL AND location != ''
                    ORDER BY location
                ''')

                locations = ['All'] + [row['location'] for row in cursor.fetchall()]

                # Update combobox values
                current_value = self.mro_location_filter.currentText()
                self.mro_location_filter.clear()
                self.mro_location_filter.addItems(locations)

                # Preserve current selection if it still exists
                if current_value in locations:
                    self.mro_location_filter.setCurrentText(current_value)
                else:
                    self.mro_location_filter.setCurrentText('All')
        except Exception as e:
            print(f"Error updating location filter: {e}")

    def update_mro_statistics(self):
        """Update inventory statistics - OPTIMIZED"""
        with db_pool.get_cursor(commit=False) as cursor:
            # OPTIMIZED: Combined query
            cursor.execute('''
                SELECT
                    COUNT(*) as total_parts,
                    COALESCE(SUM(quantity_in_stock * unit_price), 0) as total_value,
                    COUNT(*) FILTER (WHERE quantity_in_stock < minimum_stock) as low_stock_count
                FROM mro_inventory
                WHERE status = 'Active'
            ''')

            result = cursor.fetchone()
            total = result['total_parts']
            value = result['total_value']
            low_stock = result['low_stock_count']

            stats_text = (f"Total Parts: {total} | "
                         f"Total Value: ${value:,.2f} | "
                         f"Low Stock Items: {low_stock}")

            self.mro_stats_label.setText(stats_text)

    def sort_mro_column(self, col):
        """Sort MRO treeview by column"""
        # Sorting is handled automatically by QTreeWidget.setSortingEnabled(True)
        pass

    def migrate_photos_to_database(self):
        """Migrate existing photos from file paths to database binary storage"""
        try:
            cursor = self.conn.cursor()

            # Get all parts with photo paths but no binary data
            cursor.execute('''
                SELECT part_number, picture_1_path, picture_2_path
                FROM mro_inventory
                WHERE (picture_1_path IS NOT NULL AND picture_1_path != '' AND picture_1_data IS NULL)
                   OR (picture_2_path IS NOT NULL AND picture_2_path != '' AND picture_2_data IS NULL)
            ''')

            parts_to_migrate = cursor.fetchall()

            if not parts_to_migrate:
                QMessageBox.information(self.root, "Migration Complete", "No photos need migration. All photos are already in the database!")
                return

            migrated_count = 0
            skipped_count = 0
            error_count = 0

            for part_number, pic1_path, pic2_path in parts_to_migrate:
                pic1_data = None
                pic2_data = None

                # Try to read picture 1
                if pic1_path and os.path.exists(pic1_path):
                    try:
                        with open(pic1_path, 'rb') as f:
                            pic1_data = f.read()
                    except Exception as e:
                        error_count += 1
                        print(f"Error reading {pic1_path}: {e}")

                # Try to read picture 2
                if pic2_path and os.path.exists(pic2_path):
                    try:
                        with open(pic2_path, 'rb') as f:
                            pic2_data = f.read()
                    except Exception as e:
                        error_count += 1
                        print(f"Error reading {pic2_path}: {e}")

                # Update database with binary data
                if pic1_data or pic2_data:
                    try:
                        cursor.execute('''
                            UPDATE mro_inventory
                            SET picture_1_data = COALESCE(picture_1_data, %s),
                                picture_2_data = COALESCE(picture_2_data, %s)
                            WHERE part_number = %s
                        ''', (pic1_data, pic2_data, part_number))
                        migrated_count += 1
                    except Exception as e:
                        error_count += 1
                        print(f"Error updating database for {part_number}: {e}")
                else:
                    skipped_count += 1

            self.conn.commit()

            QMessageBox.information(
                self.root,
                "Migration Complete",
                f"Photo migration completed!\n\n"
                f"Successfully migrated: {migrated_count} parts\n"
                f"Skipped (files not found): {skipped_count} parts\n"
                f"Errors: {error_count} parts"
            )

        except Exception as e:
            self.conn.rollback()
            QMessageBox.critical(self.root, "Migration Error", f"Failed to migrate photos:\n{str(e)}")


# ============================================================================
# INTEGRATION INSTRUCTIONS
# ============================================================================
"""
To integrate this MRO Stock Management into your existing CMMS application:

1. Add this import at the top of your AIT_CMMS_REV3.py file:
   from mro_stock_module import MROStockManager

2. In your AIT_CMMS class __init__ method, add:
   self.mro_manager = MROStockManager(self)

3. In your create_all_manager_tabs() or create_gui() method, add:
   self.mro_manager.create_mro_tab(self.notebook)

4. The MRO Stock system will automatically use your existing SQLite database.

Example integration code:

    def create_all_manager_tabs(self):
        # ... your existing tabs ...

        # Add MRO Stock tab
        self.mro_manager.create_mro_tab(self.notebook)
"""
