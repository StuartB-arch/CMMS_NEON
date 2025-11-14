"""
CM Parts Integration Module
Handles parts consumption tracking for Corrective Maintenance work orders
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QTreeWidget, QTreeWidgetItem, QFrame, QScrollArea,
    QWidget, QMessageBox, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from datetime import datetime


class CMPartsIntegration:
    """Integration module for tracking parts consumption in CM work orders"""

    def __init__(self, parent):
        """Initialize with reference to parent CMMS application"""
        self.parent = parent
        self.conn = parent.conn

    def show_parts_consumption_dialog(self, cm_number, technician_name, callback=None):
        """
        Show dialog for recording parts consumed during corrective maintenance

        Args:
            cm_number: The CM work order number
            technician_name: Name of technician performing the work
            callback: Function to call when dialog is closed (receives success bool)
        """
        dialog = PartsConsumptionDialog(
            self.parent.root,
            self,
            cm_number,
            technician_name,
            callback
        )
        dialog.exec_()
        return dialog

    def show_cm_parts_details(self, cm_number):
        """
        Show read-only view of parts consumed for a specific CM

        Args:
            cm_number: The CM work order number to view parts for
        """
        dialog = CMPartsDetailsDialog(self.parent.root, self, cm_number)
        dialog.exec_()
        return dialog


class PartsConsumptionDialog(QDialog):
    """Dialog for recording parts consumption during corrective maintenance"""

    def __init__(self, parent, integration, cm_number, technician_name, callback=None):
        super().__init__(parent)
        self.integration = integration
        self.conn = integration.conn
        self.cm_number = cm_number
        self.technician_name = technician_name
        self.callback = callback
        self.consumed_parts = []
        self.all_parts_data = []

        self.setWindowTitle(f"Parts Consumption - CM {cm_number}")
        self.setGeometry(100, 100, 950, 750)
        self.setMinimumSize(850, 700)
        self.setModal(True)

        self.init_ui()
        self.load_parts_data()
        self.filter_parts()

    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(5)

        # Create scroll area for entire dialog
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(5)

        # Header
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(5, 5, 5, 5)

        title_label = QLabel(f"MRO Parts Consumption - CM {self.cm_number} - Technician: {self.technician_name}")
        title_font = QFont('Arial', 11, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)

        subtitle_label = QLabel("Select parts consumed from MRO stock during this corrective maintenance.")
        subtitle_font = QFont('Arial', 9)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setStyleSheet("color: gray;")
        subtitle_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(subtitle_label)

        scroll_layout.addWidget(header_frame)

        # Search frame
        search_frame = QFrame()
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(5, 0, 5, 0)

        search_label = QLabel("Search:")
        search_label.setFont(QFont('Arial', 10, QFont.Bold))
        search_layout.addWidget(search_label)

        self.search_entry = QLineEdit()
        self.search_entry.setMinimumWidth(400)
        self.search_entry.textChanged.connect(self.filter_parts)
        search_layout.addWidget(self.search_entry)

        hint_label = QLabel("(by part number or description)")
        hint_label.setFont(QFont('Arial', 9, QFont.StyleItalic))
        hint_label.setStyleSheet("color: gray;")
        search_layout.addWidget(hint_label)

        search_layout.addStretch()
        scroll_layout.addWidget(search_frame)

        # Parts list
        list_frame = QFrame()
        list_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(5, 5, 5, 5)

        list_title = QLabel("Available MRO Stock Parts")
        list_title.setFont(QFont('Arial', 10, QFont.Bold))
        list_layout.addWidget(list_title)

        # Legend
        legend_frame = QFrame()
        legend_layout = QHBoxLayout(legend_frame)
        legend_layout.setContentsMargins(5, 2, 5, 2)

        legend_title = QLabel("Legend:")
        legend_title.setFont(QFont('Arial', 9, QFont.Bold))
        legend_layout.addWidget(legend_title)

        in_stock_label = QLabel("● In Stock")
        in_stock_label.setStyleSheet("color: black;")
        legend_layout.addWidget(in_stock_label)

        low_stock_label = QLabel("● Low Stock")
        low_stock_label.setStyleSheet("color: orange;")
        legend_layout.addWidget(low_stock_label)

        out_stock_label = QLabel("● Out of Stock")
        out_stock_label.setFont(QFont('Arial', 9, QFont.StyleItalic))
        out_stock_label.setStyleSheet("color: gray;")
        legend_layout.addWidget(out_stock_label)

        legend_layout.addStretch()
        list_layout.addWidget(legend_frame)

        # Parts tree widget
        self.parts_tree = QTreeWidget()
        self.parts_tree.setHeaderLabels(['Part Number', 'Description', 'Location', 'Qty Available'])
        self.parts_tree.setColumnWidth(0, 150)
        self.parts_tree.setColumnWidth(1, 350)
        self.parts_tree.setColumnWidth(2, 150)
        self.parts_tree.setColumnWidth(3, 120)
        self.parts_tree.setAlternatingRowColors(True)
        self.parts_tree.itemSelectionChanged.connect(self.on_part_select)
        list_layout.addWidget(self.parts_tree)

        scroll_layout.addWidget(list_frame)

        # Consumption entry frame
        entry_frame = QFrame()
        entry_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        entry_layout = QGridLayout(entry_frame)
        entry_layout.setContentsMargins(5, 5, 5, 5)

        entry_title = QLabel("Add Parts Consumed")
        entry_title.setFont(QFont('Arial', 10, QFont.Bold))
        entry_layout.addWidget(entry_title, 0, 0, 1, 2)

        entry_layout.addWidget(QLabel("Selected Part:"), 1, 0, Qt.AlignLeft)
        self.selected_part_label = QLabel("(Select a part from list above)")
        self.selected_part_label.setStyleSheet("color: gray;")
        entry_layout.addWidget(self.selected_part_label, 1, 1, Qt.AlignLeft)

        entry_layout.addWidget(QLabel("Quantity Used:"), 2, 0, Qt.AlignLeft)
        self.qty_entry = QLineEdit("1")
        self.qty_entry.setMaximumWidth(200)
        entry_layout.addWidget(self.qty_entry, 2, 1, Qt.AlignLeft)

        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 10, 0, 0)

        add_button = QPushButton("Add to Consumed List")
        add_button.clicked.connect(self.add_consumed_part)
        buttons_layout.addWidget(add_button)

        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self.remove_consumed_part)
        buttons_layout.addWidget(remove_button)

        buttons_layout.addStretch()
        entry_layout.addLayout(buttons_layout, 3, 0, 1, 2)

        scroll_layout.addWidget(entry_frame)

        # Consumed parts list
        consumed_frame = QFrame()
        consumed_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        consumed_layout = QVBoxLayout(consumed_frame)
        consumed_layout.setContentsMargins(5, 5, 5, 5)

        consumed_title = QLabel("Parts to be Consumed")
        consumed_title.setFont(QFont('Arial', 10, QFont.Bold))
        consumed_layout.addWidget(consumed_title)

        self.consumed_tree = QTreeWidget()
        self.consumed_tree.setHeaderLabels(['Part Number', 'Description', 'Qty Used'])
        self.consumed_tree.setColumnWidth(0, 150)
        self.consumed_tree.setColumnWidth(1, 500)
        self.consumed_tree.setColumnWidth(2, 100)
        self.consumed_tree.setMaximumHeight(150)
        self.consumed_tree.setAlternatingRowColors(True)
        consumed_layout.addWidget(self.consumed_tree)

        scroll_layout.addWidget(consumed_frame)

        # Bottom buttons
        bottom_frame = QFrame()
        bottom_layout = QHBoxLayout(bottom_frame)
        bottom_layout.setContentsMargins(5, 10, 5, 10)

        save_button = QPushButton("Save and Complete")
        save_button.clicked.connect(self.save_and_close)
        bottom_layout.addWidget(save_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.cancel_dialog)
        bottom_layout.addWidget(cancel_button)

        bottom_layout.addStretch()
        scroll_layout.addWidget(bottom_frame)

        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)

    def load_parts_data(self):
        """Load available parts from MRO inventory"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT part_number, name, location, quantity_in_stock
                FROM mro_inventory
                WHERE status = 'Active'
                ORDER BY part_number
            ''')
            self.all_parts_data = cursor.fetchall()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load MRO inventory: {str(e)}")

    def filter_parts(self):
        """Filter parts list based on search term"""
        search_term = self.search_entry.text().lower().strip()

        # Clear current items
        self.parts_tree.clear()

        # Filter and display parts
        for part in self.all_parts_data:
            part_number = str(part[0]).lower()
            description = str(part[1]).lower()
            qty_available = float(part[3]) if part[3] else 0.0

            # Show part if search term is empty or matches
            if not search_term or search_term in part_number or search_term in description:
                item = QTreeWidgetItem(self.parts_tree)
                item.setText(0, str(part[0]))
                item.setText(1, str(part[1]))
                item.setText(2, str(part[2]))
                item.setText(3, str(part[3]))

                # Set color based on stock level
                if qty_available <= 0:
                    for i in range(4):
                        item.setForeground(i, QColor('gray'))
                    item.setFont(1, QFont('Arial', 9, QFont.StyleItalic))
                elif qty_available <= 5:
                    for i in range(4):
                        item.setForeground(i, QColor('orange'))
                else:
                    for i in range(4):
                        item.setForeground(i, QColor('black'))

    def on_part_select(self):
        """Update selected part label when user selects from available parts"""
        selected_items = self.parts_tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            part_num = item.text(0)
            desc = item.text(1)
            self.selected_part_label.setText(f"{part_num} - {desc}")
            self.selected_part_label.setStyleSheet("color: black;")

    def add_consumed_part(self):
        """Add selected part to consumed list"""
        selected_items = self.parts_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a part from the available parts list")
            return

        try:
            qty_used = float(self.qty_entry.text())
            if qty_used <= 0:
                QMessageBox.critical(self, "Error", "Quantity must be greater than 0")
                return
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid quantity value")
            return

        item = selected_items[0]
        part_num = item.text(0)
        desc = item.text(1)
        qty_available = float(item.text(3))

        if qty_available <= 0:
            QMessageBox.critical(self, "Part Out of Stock",
                               f"Part {part_num} is currently out of stock.\n\n"
                               f"Available quantity: {qty_available}\n"
                               f"Please replenish stock before recording consumption.")
            return

        if qty_used > qty_available:
            QMessageBox.critical(self, "Insufficient Stock",
                               f"Quantity used ({qty_used}) exceeds available quantity ({qty_available})\n\n"
                               f"Part: {part_num}\n"
                               f"Please adjust the quantity or replenish stock.")
            return

        # Check if part already added
        for existing in self.consumed_parts:
            if existing['part_number'] == part_num:
                QMessageBox.warning(self, "Warning",
                                  "This part is already in the consumed list. Remove it first if you need to change the quantity.")
                return

        # Add to consumed list
        self.consumed_parts.append({
            'part_number': part_num,
            'description': desc,
            'quantity': qty_used
        })

        consumed_item = QTreeWidgetItem(self.consumed_tree)
        consumed_item.setText(0, part_num)
        consumed_item.setText(1, desc)
        consumed_item.setText(2, str(qty_used))

        self.qty_entry.setText("1")  # Reset quantity
        QMessageBox.information(self, "Success", f"Added {part_num} to consumed parts list")

    def remove_consumed_part(self):
        """Remove selected part from consumed list"""
        selected_items = self.consumed_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Warning", "Please select a part to remove from the consumed list")
            return

        item = selected_items[0]
        part_num = item.text(0)

        # Remove from list
        self.consumed_parts = [p for p in self.consumed_parts if p['part_number'] != part_num]

        # Remove from tree
        index = self.consumed_tree.indexOfTopLevelItem(item)
        self.consumed_tree.takeTopLevelItem(index)

    def save_and_close(self):
        """Save consumed parts to database and close dialog"""
        if not self.consumed_parts:
            response = QMessageBox.question(self, "Confirm",
                                          "No parts were added to the consumed list. Continue without recording parts?",
                                          QMessageBox.Yes | QMessageBox.No)
            if response == QMessageBox.No:
                return
            self.accept()
            if self.callback:
                self.callback(True)
            return

        try:
            cursor = self.conn.cursor()

            # Record each consumed part
            for part in self.consumed_parts:
                # Get unit price for cost calculation
                cursor.execute('''
                    SELECT unit_price FROM mro_inventory WHERE part_number = %s
                ''', (part['part_number'],))
                result = cursor.fetchone()
                unit_price = float(result[0]) if result and result[0] else 0.0
                total_cost = unit_price * part['quantity']

                # Create transaction record
                cursor.execute('''
                    INSERT INTO mro_stock_transactions
                    (part_number, transaction_type, quantity, technician_name, notes, transaction_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', (
                    part['part_number'],
                    'Issue',
                    -part['quantity'],  # Negative for consumption
                    self.technician_name,
                    f"CM Work Order: {self.cm_number}",
                    datetime.now()
                ))

                # Record in cm_parts_used table for tracking and reporting
                cursor.execute('''
                    INSERT INTO cm_parts_used
                    (cm_number, part_number, quantity_used, total_cost, recorded_date, recorded_by, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    self.cm_number,
                    part['part_number'],
                    part['quantity'],
                    total_cost,
                    datetime.now(),
                    self.technician_name,
                    f"Parts consumed during CM {self.cm_number}"
                ))

                # Update inventory quantity
                cursor.execute('''
                    UPDATE mro_inventory
                    SET quantity_in_stock = quantity_in_stock - %s,
                        last_updated = %s
                    WHERE part_number = %s
                ''', (part['quantity'], datetime.now(), part['part_number']))

            self.conn.commit()

            QMessageBox.information(self, "Success",
                               f"Successfully recorded {len(self.consumed_parts)} part(s) consumed for CM {self.cm_number}")
            self.accept()

            if self.callback:
                self.callback(True)

        except Exception as e:
            self.conn.rollback()
            QMessageBox.critical(self, "Error", f"Failed to record parts consumption: {str(e)}")
            if self.callback:
                self.callback(False)

    def cancel_dialog(self):
        """Cancel without saving"""
        if self.consumed_parts:
            response = QMessageBox.question(self, "Confirm",
                                          "Parts have been added but not saved. Cancel without saving?",
                                          QMessageBox.Yes | QMessageBox.No)
            if response == QMessageBox.No:
                return

        self.reject()
        if self.callback:
            self.callback(False)

    def closeEvent(self, event):
        """Handle window close event"""
        if self.consumed_parts:
            response = QMessageBox.question(self, "Confirm",
                                          "Parts have been added but not saved. Close without saving?",
                                          QMessageBox.Yes | QMessageBox.No)
            if response == QMessageBox.No:
                event.ignore()
                return

        if self.callback:
            self.callback(False)
        event.accept()


class CMPartsDetailsDialog(QDialog):
    """Dialog for viewing parts consumed for a specific CM"""

    def __init__(self, parent, integration, cm_number):
        super().__init__(parent)
        self.integration = integration
        self.conn = integration.conn
        self.cm_number = cm_number

        self.setWindowTitle(f"Parts Used - CM {cm_number}")
        self.setGeometry(100, 100, 800, 500)
        self.setModal(True)

        self.init_ui()
        self.load_parts_data()

    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Header
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(5, 5, 5, 5)

        title_label = QLabel(f"Parts Consumed - CM {self.cm_number}")
        title_font = QFont('Arial', 12, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title_label)

        self.summary_label = QLabel()
        summary_font = QFont('Arial', 10)
        self.summary_label.setFont(summary_font)
        self.summary_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(self.summary_label)

        main_layout.addWidget(header_frame)

        # Parts list frame
        list_frame = QFrame()
        list_frame.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        list_layout = QVBoxLayout(list_frame)
        list_layout.setContentsMargins(5, 5, 5, 5)

        list_title = QLabel("Parts Details")
        list_title.setFont(QFont('Arial', 10, QFont.Bold))
        list_layout.addWidget(list_title)

        # Parts tree widget
        self.parts_tree = QTreeWidget()
        self.parts_tree.setHeaderLabels(['Part Number', 'Description', 'Qty Used', 'Cost', 'Date', 'Recorded By'])
        self.parts_tree.setColumnWidth(0, 120)
        self.parts_tree.setColumnWidth(1, 250)
        self.parts_tree.setColumnWidth(2, 80)
        self.parts_tree.setColumnWidth(3, 100)
        self.parts_tree.setColumnWidth(4, 150)
        self.parts_tree.setColumnWidth(5, 100)
        self.parts_tree.setAlternatingRowColors(True)
        list_layout.addWidget(self.parts_tree)

        main_layout.addWidget(list_frame)

        # Summary frame
        summary_frame = QFrame()
        summary_layout = QHBoxLayout(summary_frame)
        summary_layout.setContentsMargins(5, 5, 5, 5)

        self.total_cost_label = QLabel()
        self.total_cost_label.setFont(QFont('Arial', 11, QFont.Bold))
        summary_layout.addStretch()
        summary_layout.addWidget(self.total_cost_label)

        main_layout.addWidget(summary_frame)

        # Close button
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        main_layout.addWidget(close_button, alignment=Qt.AlignCenter)

    def load_parts_data(self):
        """Load parts data from database"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT
                    cp.part_number,
                    mi.name,
                    cp.quantity_used,
                    cp.total_cost,
                    cp.recorded_date,
                    cp.recorded_by,
                    cp.notes
                FROM cm_parts_used cp
                LEFT JOIN mro_inventory mi ON cp.part_number = mi.part_number
                WHERE cp.cm_number = %s
                ORDER BY cp.recorded_date DESC
            ''', (self.cm_number,))

            parts_data = cursor.fetchall()

            if not parts_data:
                self.summary_label.setText("No parts recorded for this CM")
                self.summary_label.setStyleSheet("color: gray;")
                return

            self.summary_label.setText(f"Total: {len(parts_data)} part(s)")
            self.summary_label.setStyleSheet("color: blue;")

            # Populate tree
            total_cost = 0.0
            for part in parts_data:
                part_number = part[0]
                description = part[1] if part[1] else "N/A"
                qty_used = f"{part[2]:.2f}" if part[2] else "0"
                cost = part[3] if part[3] else 0.0
                total_cost += cost
                date_recorded = str(part[4])[:19] if part[4] else "N/A"
                recorded_by = part[5] if part[5] else "N/A"

                item = QTreeWidgetItem(self.parts_tree)
                item.setText(0, part_number)
                item.setText(1, description)
                item.setText(2, qty_used)
                item.setText(3, f"${cost:.2f}")
                item.setText(4, date_recorded)
                item.setText(5, recorded_by)

            self.total_cost_label.setText(f"Total Cost: ${total_cost:.2f}")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load parts data: {str(e)}")
            self.reject()
