"""
KPI Auto Collector Module
Automatically collects and calculates KPI data from existing database records
Reduces manual data entry and improves accuracy
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import calendar
from decimal import Decimal


class KPIAutoCollector:
    """Automatically collects KPI data from database"""

    def __init__(self, conn):
        """
        Initialize auto collector

        Args:
            conn: Database connection
        """
        self.conn = conn

    def auto_collect_all_kpis(self, period: str) -> Dict[str, Dict]:
        """
        Auto-collect all possible KPIs for a given period

        Args:
            period: Period string (e.g., "2025-01" for January 2025)

        Returns:
            Dictionary of KPI results
        """
        results = {}

        # Parse period
        year, month = map(int, period.split('-'))
        start_date, end_date = self._get_period_dates(year, month)

        print(f"Auto-collecting KPIs for period {period} ({start_date} to {end_date})")

        # Collect each KPI
        results['pm_adherence'] = self._collect_pm_adherence(start_date, end_date, period)
        results['work_orders_opened'] = self._collect_work_orders_opened(start_date, end_date, period)
        results['work_orders_closed'] = self._collect_work_orders_closed(start_date, end_date, period)
        results['work_order_backlog'] = self._collect_work_order_backlog(end_date, period)
        results['technical_availability'] = self._collect_technical_availability(start_date, end_date, period)
        results['mtbf'] = self._collect_mtbf(start_date, end_date, period)
        results['mttr'] = self._collect_mttr(start_date, end_date, period)
        results['maintenance_labor_hours'] = self._collect_labor_hours(start_date, end_date, period)

        return results

    def _get_period_dates(self, year: int, month: int) -> Tuple[str, str]:
        """Get start and end dates for a period"""
        start_date = f"{year}-{month:02d}-01"

        # Get last day of month
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day}"

        return start_date, end_date

    def _collect_pm_adherence(self, start_date: str, end_date: str, period: str) -> Dict:
        """
        Calculate PM Adherence (F2.2)
        Formula: (Completed PMs / Scheduled PMs) * 100

        Args:
            start_date: Period start date
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        # Count scheduled PMs
        cursor.execute('''
            SELECT COUNT(DISTINCT bfm_equipment_no || pm_type)
            FROM weekly_pm_schedules
            WHERE week_start_date >= %s
            AND week_start_date <= %s
        ''', (start_date, end_date))
        scheduled_pms = cursor.fetchone()[0] or 0

        # Count completed PMs
        cursor.execute('''
            SELECT COUNT(*)
            FROM pm_completions
            WHERE completion_date >= %s
            AND completion_date <= %s
        ''', (start_date, end_date))
        completed_pms = cursor.fetchone()[0] or 0

        # Calculate adherence
        if scheduled_pms > 0:
            adherence = (completed_pms / scheduled_pms) * 100
        else:
            adherence = 0

        return {
            'kpi_name': 'PM Adherence',
            'period': period,
            'value': round(adherence, 2),
            'unit': '%',
            'scheduled_pms': scheduled_pms,
            'completed_pms': completed_pms,
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _collect_work_orders_opened(self, start_date: str, end_date: str, period: str) -> Dict:
        """
        Count Work Orders Opened (F2.2)

        Args:
            start_date: Period start date
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT COUNT(*)
            FROM corrective_maintenance
            WHERE reported_date >= %s
            AND reported_date <= %s
        ''', (start_date, end_date))

        wo_opened = cursor.fetchone()[0] or 0

        return {
            'kpi_name': 'Work Orders Opened',
            'period': period,
            'value': wo_opened,
            'unit': 'count',
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _collect_work_orders_closed(self, start_date: str, end_date: str, period: str) -> Dict:
        """
        Count Work Orders Closed (F2.2)

        Args:
            start_date: Period start date
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT COUNT(*)
            FROM corrective_maintenance
            WHERE closed_date >= %s
            AND closed_date <= %s
        ''', (start_date, end_date))

        wo_closed = cursor.fetchone()[0] or 0

        return {
            'kpi_name': 'Work Orders Closed',
            'period': period,
            'value': wo_closed,
            'unit': 'count',
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _collect_work_order_backlog(self, end_date: str, period: str) -> Dict:
        """
        Count Open Work Orders (Backlog) at end of period (F2.2)

        Args:
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        cursor.execute('''
            SELECT COUNT(*)
            FROM corrective_maintenance
            WHERE reported_date <= %s
            AND (closed_date IS NULL OR closed_date > %s)
        ''', (end_date, end_date))

        backlog = cursor.fetchone()[0] or 0

        # Also get age profile
        cursor.execute('''
            SELECT
                COUNT(CASE WHEN %s::date - reported_date::date <= 7 THEN 1 END) as week_0_7,
                COUNT(CASE WHEN %s::date - reported_date::date BETWEEN 8 AND 30 THEN 1 END) as week_8_30,
                COUNT(CASE WHEN %s::date - reported_date::date BETWEEN 31 AND 60 THEN 1 END) as days_31_60,
                COUNT(CASE WHEN %s::date - reported_date::date > 60 THEN 1 END) as days_over_60
            FROM corrective_maintenance
            WHERE reported_date <= %s
            AND (closed_date IS NULL OR closed_date > %s)
        ''', (end_date, end_date, end_date, end_date, end_date, end_date))

        age_profile = cursor.fetchone()

        return {
            'kpi_name': 'Work Order Backlog',
            'period': period,
            'value': backlog,
            'unit': 'count',
            'age_0_7_days': age_profile[0],
            'age_8_30_days': age_profile[1],
            'age_31_60_days': age_profile[2],
            'age_over_60_days': age_profile[3],
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _collect_technical_availability(self, start_date: str, end_date: str, period: str) -> Dict:
        """
        Calculate Technical Availability (F2.1)
        Formula: (Operating Time / (Operating Time + Downtime)) * 100

        Note: Requires downtime tracking data

        Args:
            start_date: Period start date
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        # Calculate total downtime from CM records
        cursor.execute('''
            SELECT COALESCE(SUM(
                CASE
                    WHEN closed_date IS NOT NULL THEN
                        closed_date::date - reported_date::date
                    ELSE
                        %s::date - reported_date::date
                END
            ), 0)
            FROM corrective_maintenance
            WHERE reported_date >= %s
            AND reported_date <= %s
        ''', (end_date, start_date, end_date))

        total_downtime_days = cursor.fetchone()[0] or 0

        # Calculate period days
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        period_days = (end - start).days + 1

        # Count active equipment
        cursor.execute('''
            SELECT COUNT(*)
            FROM equipment
            WHERE status = 'Active'
        ''')
        active_equipment = cursor.fetchone()[0] or 1

        # Calculate potential operating days
        potential_operating_days = period_days * active_equipment

        # Calculate availability
        if potential_operating_days > 0:
            operating_days = potential_operating_days - total_downtime_days
            availability = (operating_days / potential_operating_days) * 100
        else:
            availability = 0

        return {
            'kpi_name': 'Technical Availability',
            'period': period,
            'value': round(availability, 2),
            'unit': '%',
            'potential_operating_days': potential_operating_days,
            'downtime_days': total_downtime_days,
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': 'Calculated from CM downtime data'
        }

    def _collect_mtbf(self, start_date: str, end_date: str, period: str) -> Dict:
        """
        Calculate Mean Time Between Failures (F2.1)
        Formula: Operating Time / Number of Failures

        Args:
            start_date: Period start date
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        # Count failures (CMs opened)
        cursor.execute('''
            SELECT COUNT(*)
            FROM corrective_maintenance
            WHERE reported_date >= %s
            AND reported_date <= %s
        ''', (start_date, end_date))

        failure_count = cursor.fetchone()[0] or 0

        # Calculate period hours (assuming 24/7 operation)
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        period_hours = ((end - start).days + 1) * 24

        # Calculate MTBF
        if failure_count > 0:
            mtbf = period_hours / failure_count
        else:
            mtbf = period_hours  # No failures means MTBF = total operating time

        return {
            'kpi_name': 'Mean Time Between Failures (MTBF)',
            'period': period,
            'value': round(mtbf, 2),
            'unit': 'hours',
            'failure_count': failure_count,
            'operating_hours': period_hours,
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _collect_mttr(self, start_date: str, end_date: str, period: str) -> Dict:
        """
        Calculate Mean Time To Repair (F2.1)
        Formula: Total Repair Time / Number of Repairs

        Args:
            start_date: Period start date
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        # Get repair times for closed CMs
        cursor.execute('''
            SELECT
                COUNT(*) as repair_count,
                COALESCE(AVG(
                    EXTRACT(EPOCH FROM (closed_date::timestamp - reported_date::timestamp)) / 3600
                ), 0) as avg_repair_hours
            FROM corrective_maintenance
            WHERE closed_date IS NOT NULL
            AND closed_date >= %s
            AND closed_date <= %s
        ''', (start_date, end_date))

        row = cursor.fetchone()
        repair_count = row[0] or 0
        avg_repair_hours = float(row[1]) if row[1] else 0

        return {
            'kpi_name': 'Mean Time To Repair (MTTR)',
            'period': period,
            'value': round(avg_repair_hours, 2),
            'unit': 'hours',
            'repair_count': repair_count,
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def _collect_labor_hours(self, start_date: str, end_date: str, period: str) -> Dict:
        """
        Calculate Total Maintenance Labor Hours

        Args:
            start_date: Period start date
            end_date: Period end date
            period: Period string

        Returns:
            Dictionary with KPI data
        """
        cursor = self.conn.cursor()

        # PM labor hours
        cursor.execute('''
            SELECT COALESCE(SUM(labor_hours), 0)
            FROM pm_completions
            WHERE completion_date >= %s
            AND completion_date <= %s
        ''', (start_date, end_date))
        pm_hours = float(cursor.fetchone()[0] or 0)

        # CM labor hours
        cursor.execute('''
            SELECT COALESCE(SUM(labor_hours), 0)
            FROM corrective_maintenance
            WHERE reported_date >= %s
            AND reported_date <= %s
        ''', (start_date, end_date))
        cm_hours = float(cursor.fetchone()[0] or 0)

        total_hours = pm_hours + cm_hours

        return {
            'kpi_name': 'Total Maintenance Labor Hours',
            'period': period,
            'value': round(total_hours, 2),
            'unit': 'hours',
            'pm_hours': round(pm_hours, 2),
            'cm_hours': round(cm_hours, 2),
            'auto_calculated': True,
            'calculation_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    def save_auto_collected_kpis(self, period: str, user_id: str = 'system') -> Dict:
        """
        Auto-collect and save all KPIs to database

        Args:
            period: Period string (e.g., "2025-01")
            user_id: User ID for audit trail

        Returns:
            Dictionary with results
        """
        try:
            # Auto-collect all KPIs
            kpi_results = self.auto_collect_all_kpis(period)

            saved_count = 0
            errors = []

            cursor = self.conn.cursor()

            # Save each KPI to kpi_manual_data table
            for kpi_name, kpi_data in kpi_results.items():
                try:
                    # Save main value
                    cursor.execute('''
                        INSERT INTO kpi_manual_data
                        (kpi_name, measurement_period, data_field, data_value, notes, entered_by)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (kpi_name, measurement_period, data_field)
                        DO UPDATE SET
                            data_value = EXCLUDED.data_value,
                            notes = EXCLUDED.notes,
                            entered_by = EXCLUDED.entered_by,
                            entered_date = CURRENT_TIMESTAMP
                    ''', (
                        kpi_data['kpi_name'],
                        period,
                        'value',
                        kpi_data['value'],
                        f"Auto-calculated on {kpi_data['calculation_date']}",
                        user_id
                    ))

                    saved_count += 1

                except Exception as e:
                    errors.append(f"Error saving {kpi_name}: {str(e)}")

            self.conn.commit()

            return {
                'success': True,
                'period': period,
                'saved_count': saved_count,
                'total_kpis': len(kpi_results),
                'errors': errors
            }

        except Exception as e:
            self.conn.rollback()
            return {
                'success': False,
                'error': str(e)
            }

    def get_auto_collectable_kpis(self) -> List[str]:
        """
        Get list of KPIs that can be auto-collected

        Returns:
            List of KPI names
        """
        return [
            'PM Adherence',
            'Work Orders Opened',
            'Work Orders Closed',
            'Work Order Backlog',
            'Technical Availability',
            'Mean Time Between Failures (MTBF)',
            'Mean Time To Repair (MTTR)',
            'Total Maintenance Labor Hours'
        ]

    def preview_auto_collection(self, period: str) -> Dict:
        """
        Preview what would be auto-collected without saving

        Args:
            period: Period string

        Returns:
            Dictionary with preview data
        """
        try:
            kpi_results = self.auto_collect_all_kpis(period)

            preview = {
                'period': period,
                'kpis': []
            }

            for kpi_name, kpi_data in kpi_results.items():
                preview['kpis'].append({
                    'name': kpi_data['kpi_name'],
                    'value': kpi_data['value'],
                    'unit': kpi_data['unit'],
                    'details': {k: v for k, v in kpi_data.items()
                               if k not in ['kpi_name', 'period', 'value', 'unit']}
                })

            return preview

        except Exception as e:
            return {
                'error': str(e)
            }


def test_auto_collector(conn):
    """Test function for auto collector"""
    collector = KPIAutoCollector(conn)

    # Test for current month
    current_period = datetime.now().strftime('%Y-%m')
    print(f"\n=== Testing Auto Collector for {current_period} ===\n")

    # Preview
    preview = collector.preview_auto_collection(current_period)

    if 'error' in preview:
        print(f"Error: {preview['error']}")
    else:
        print(f"Period: {preview['period']}")
        print(f"\nAuto-Collectible KPIs:")
        for kpi in preview['kpis']:
            print(f"\n{kpi['name']}: {kpi['value']} {kpi['unit']}")
            print(f"  Details: {kpi['details']}")
