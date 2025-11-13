"""
PM Scheduling Module
Handles all preventive maintenance scheduling logic including:
- PM eligibility checking
- PM assignment generation
- PM scheduling optimization
- Priority-based assignment
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional, NamedTuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import os


class PMType(Enum):
    MONTHLY = "Monthly"
    ANNUAL = "Annual"


class PMStatus(Enum):
    DUE = "due"
    NOT_DUE = "not_due"
    RECENTLY_COMPLETED = "recently_completed"
    CONFLICTED = "conflicted"


@dataclass
class Equipment:
    bfm_no: str
    description: str
    has_monthly: bool
    has_annual: bool
    last_monthly_date: Optional[str]
    last_annual_date: Optional[str]
    status: str
    priority: int = 99  # Default priority for assets not in priority lists


@dataclass
class CompletionRecord:
    bfm_no: str
    pm_type: PMType
    completion_date: datetime
    technician: str


@dataclass
class PMAssignment:
    bfm_no: str
    pm_type: PMType
    description: str
    priority_score: int
    reason: str


class PMEligibilityResult(NamedTuple):
    status: PMStatus
    reason: str
    priority_score: int = 0
    days_overdue: int = 0


class DateParser:
    """Responsible for parsing and standardizing dates"""

    def __init__(self, conn):
        self.conn = conn

    def parse_flexible(self, date_string: Optional[str]) -> Optional[datetime]:
        """Parse date string with flexible format handling"""
        if not date_string:
            return None

        try:
            # Try standard format first
            return datetime.strptime(date_string, '%Y-%m-%d')
        except (ValueError, TypeError):
            pass

        # Try other common formats
        formats = ['%m/%d/%Y', '%d/%m/%Y', '%Y/%m/%d', '%m-%d-%Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_string, fmt)
            except (ValueError, TypeError):
                continue

        return None


class CompletionRecordRepository:
    """Responsible for retrieving completion records from database"""

    def __init__(self, conn):
        self.conn = conn
        self._completion_cache = None  # Cache for bulk loaded completions
        self._scheduled_cache = None   # Cache for scheduled PMs
        self._uncompleted_cache = None # Cache for uncompleted schedules (PERFORMANCE FIX)

    def get_recent_completions(self, bfm_no: str, days: int = 400) -> List[CompletionRecord]:
        """Get recent completion records for equipment - EXTENDED TO 400 DAYS FOR ANNUAL PMs"""
        # Use cache if available
        if self._completion_cache is not None:
            return self._completion_cache.get(bfm_no, [])

        # Fallback to individual query if cache not loaded
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT bfm_equipment_no, pm_type, completion_date, technician_name
            FROM pm_completions
            WHERE bfm_equipment_no = %s
            AND completion_date::DATE >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY completion_date DESC
        ''', (bfm_no, days))

        completions = []
        for row in cursor.fetchall():
            try:
                pm_type = PMType.MONTHLY if row[1] == "Monthly" else PMType.ANNUAL
                completion_date = datetime.strptime(row[2], '%Y-%m-%d')

                completions.append(CompletionRecord(
                    bfm_no=row[0],
                    pm_type=pm_type,
                    completion_date=completion_date,
                    technician=row[3]
                ))
            except Exception as e:
                print(f"Error parsing completion record: {e}")

        return completions

    def bulk_load_completions(self, days: int = 400) -> None:
        """Load ALL completion records for ALL equipment in one query - MASSIVE PERFORMANCE BOOST"""
        print(f"DEBUG: Bulk loading completion records...")
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT bfm_equipment_no, pm_type, completion_date, technician_name
            FROM pm_completions
            WHERE completion_date::DATE >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY bfm_equipment_no, completion_date DESC
        ''', (days,))

        # Group completions by equipment
        self._completion_cache = {}
        for row in cursor.fetchall():
            try:
                bfm_no = row[0]
                pm_type = PMType.MONTHLY if row[1] == "Monthly" else PMType.ANNUAL
                completion_date = datetime.strptime(row[2], '%Y-%m-%d')

                if bfm_no not in self._completion_cache:
                    self._completion_cache[bfm_no] = []

                self._completion_cache[bfm_no].append(CompletionRecord(
                    bfm_no=bfm_no,
                    pm_type=pm_type,
                    completion_date=completion_date,
                    technician=row[3]
                ))
            except Exception as e:
                print(f"Error parsing completion record: {e}")

        print(f"DEBUG: Loaded completion records for {len(self._completion_cache)} equipment items")

    def get_scheduled_pms(self, week_start: datetime, bfm_no: Optional[str] = None) -> List[Dict]:
        """Get currently scheduled PMs for the week"""
        # Use cache if available and no specific equipment requested
        if self._scheduled_cache is not None and bfm_no:
            return self._scheduled_cache.get(bfm_no, [])

        # Fallback to individual query
        cursor = self.conn.cursor()

        if bfm_no:
            cursor.execute('''
                SELECT bfm_equipment_no, pm_type, assigned_technician, status
                FROM weekly_pm_schedules
                WHERE week_start_date = %s AND bfm_equipment_no = %s
            ''', (week_start.strftime('%Y-%m-%d'), bfm_no))
        else:
            cursor.execute('''
                SELECT bfm_equipment_no, pm_type, assigned_technician, status
                FROM weekly_pm_schedules
                WHERE week_start_date = %s
            ''', (week_start.strftime('%Y-%m-%d'),))

        return [{'bfm_no': row[0], 'pm_type': row[1], 'technician': row[2], 'status': row[3]}
                for row in cursor.fetchall()]

    def bulk_load_scheduled(self, week_start: datetime) -> None:
        """Load ALL scheduled PMs for the week in one query"""
        print(f"DEBUG: Bulk loading scheduled PMs...")
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT bfm_equipment_no, pm_type, assigned_technician, status
            FROM weekly_pm_schedules
            WHERE week_start_date = %s
        ''', (week_start.strftime('%Y-%m-%d'),))

        # Group scheduled PMs by equipment
        self._scheduled_cache = {}
        for row in cursor.fetchall():
            bfm_no = row[0]
            if bfm_no not in self._scheduled_cache:
                self._scheduled_cache[bfm_no] = []

            self._scheduled_cache[bfm_no].append({
                'bfm_no': bfm_no,
                'pm_type': row[1],
                'technician': row[2],
                'status': row[3]
            })

        print(f"DEBUG: Loaded scheduled PMs for {len(self._scheduled_cache)} equipment items")

    def bulk_load_uncompleted_schedules(self, before_week: datetime) -> None:
        """Load ALL uncompleted schedules from PREVIOUS weeks in one query - CRITICAL PERFORMANCE FIX"""
        print(f"DEBUG: Bulk loading uncompleted schedules from previous weeks...")
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT bfm_equipment_no, pm_type, week_start_date, assigned_technician, status, scheduled_date
            FROM weekly_pm_schedules
            WHERE week_start_date < %s
            AND status = 'Scheduled'
            ORDER BY bfm_equipment_no, pm_type, week_start_date DESC
        ''', (before_week.strftime('%Y-%m-%d'),))

        # Group uncompleted schedules by equipment + PM type
        self._uncompleted_cache = {}
        for row in cursor.fetchall():
            bfm_no = row[0]
            pm_type = row[1]
            cache_key = f"{bfm_no}_{pm_type}"

            if cache_key not in self._uncompleted_cache:
                self._uncompleted_cache[cache_key] = []

            # Only keep the 5 most recent for each equipment+PM type combination
            if len(self._uncompleted_cache[cache_key]) < 5:
                self._uncompleted_cache[cache_key].append({
                    'week_start': row[2],
                    'technician': row[3],
                    'status': row[4],
                    'scheduled_date': row[5]
                })

        print(f"DEBUG: Loaded uncompleted schedules for {len(self._uncompleted_cache)} equipment+PM type combinations")

    def get_uncompleted_schedules(self, bfm_no: str, pm_type: PMType, before_week: datetime) -> List[Dict]:
        """Get uncompleted scheduled PMs for equipment from PREVIOUS weeks"""
        # Use cache if available
        if self._uncompleted_cache is not None:
            cache_key = f"{bfm_no}_{pm_type.value}"
            return self._uncompleted_cache.get(cache_key, [])

        # Fallback to individual query if cache not loaded
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT week_start_date, assigned_technician, status, scheduled_date
            FROM weekly_pm_schedules
            WHERE bfm_equipment_no = %s
            AND pm_type = %s
            AND week_start_date < %s
            AND status = 'Scheduled'
            ORDER BY week_start_date DESC
            LIMIT 5
        ''', (bfm_no, pm_type.value, before_week.strftime('%Y-%m-%d')))

        return [{'week_start': row[0], 'technician': row[1], 'status': row[2], 'scheduled_date': row[3]}
                for row in cursor.fetchall()]


class PMEligibilityChecker:
    """Responsible for determining if a PM is eligible for scheduling"""

    PM_FREQUENCIES = {
        PMType.MONTHLY: 30,
        PMType.ANNUAL: 365
    }

    def __init__(self, date_parser: DateParser, completion_repo: CompletionRecordRepository):
        self.date_parser = date_parser
        self.completion_repo = completion_repo
        self._next_annual_cache = None  # Cache for next annual PM dates

    def check_eligibility(self, equipment: Equipment, pm_type: PMType,
                         week_start: datetime) -> PMEligibilityResult:
        """Check if equipment is eligible for PM assignment"""

        # Check if equipment supports this PM type
        if pm_type == PMType.MONTHLY and not equipment.has_monthly:
            return PMEligibilityResult(PMStatus.NOT_DUE, "Equipment doesn't require Monthly PM")
        if pm_type == PMType.ANNUAL and not equipment.has_annual:
            return PMEligibilityResult(PMStatus.NOT_DUE, "Equipment doesn't require Annual PM")

        # Check for uncompleted schedules from PREVIOUS weeks
        uncompleted_schedules = self.completion_repo.get_uncompleted_schedules(
            equipment.bfm_no, pm_type, week_start
        )
        if uncompleted_schedules:
            oldest_uncompleted = uncompleted_schedules[-1]
            return PMEligibilityResult(
                PMStatus.CONFLICTED,
                f"Already scheduled for week {oldest_uncompleted['week_start']} (uncompleted) - assigned to {oldest_uncompleted['technician']}"
            )

        # For Annual PMs, check if there's a Next Annual PM Date specified
        if pm_type == PMType.ANNUAL:
            if self._next_annual_cache is not None:
                next_annual_str = self._next_annual_cache.get(equipment.bfm_no)
            else:
                cursor = self.completion_repo.conn.cursor()
                cursor.execute('SELECT next_annual_pm FROM equipment WHERE bfm_equipment_no = %s', (equipment.bfm_no,))
                result = cursor.fetchone()
                next_annual_str = result[0] if result and result[0] else None

            if next_annual_str:
                next_annual_date = self.date_parser.parse_flexible(next_annual_str)
                if next_annual_date:
                    days_until_next_annual = (next_annual_date - datetime.now()).days

                    if days_until_next_annual > 7:
                        return PMEligibilityResult(
                            PMStatus.NOT_DUE,
                            f"Annual PM scheduled for {next_annual_date.strftime('%Y-%m-%d')} ({days_until_next_annual} days from now)"
                        )
                    elif days_until_next_annual >= -30:
                        priority = 500 + abs(min(days_until_next_annual, 0)) * 10
                        return PMEligibilityResult(
                            PMStatus.DUE,
                            f"Annual PM due by Next Annual PM Date: {next_annual_date.strftime('%Y-%m-%d')}",
                            priority_score=priority,
                            days_overdue=abs(min(days_until_next_annual, 0))
                        )

        # Get recent completions
        recent_completions = self.completion_repo.get_recent_completions(equipment.bfm_no, days=400)

        # Check for recent completions of same type
        same_type_completions = [c for c in recent_completions if c.pm_type == pm_type]
        if same_type_completions:
            latest_completion = max(same_type_completions, key=lambda x: x.completion_date)
            days_since = (datetime.now() - latest_completion.completion_date).days

            min_interval = self._get_minimum_interval(pm_type)
            if days_since < min_interval:
                return PMEligibilityResult(
                    PMStatus.RECENTLY_COMPLETED,
                    f"{pm_type.value} PM completed {days_since} days ago (min interval: {min_interval})"
                )

        # Check for cross-PM conflicts
        conflict_result = self._check_cross_pm_conflicts(recent_completions, pm_type)
        if conflict_result.status == PMStatus.CONFLICTED:
            return conflict_result

        # Check if already scheduled
        scheduled_pms = self.completion_repo.get_scheduled_pms(week_start, equipment.bfm_no)
        if any(s['pm_type'] == pm_type.value for s in scheduled_pms):
            return PMEligibilityResult(PMStatus.CONFLICTED, f"Already scheduled for this week")

        # Check if due based on equipment table dates
        return self._check_due_date(equipment, pm_type, recent_completions)

    def _get_minimum_interval(self, pm_type: PMType) -> int:
        """Get minimum interval before rescheduling same PM type"""
        if pm_type == PMType.MONTHLY:
            return 30  # Monthly PMs: minimum 30 days between completions
        else:  # PMType.ANNUAL
            return 365  # Annual PMs: minimum 365 days between completions

    def _check_cross_pm_conflicts(self, recent_completions: List[CompletionRecord],
                                 pm_type: PMType) -> PMEligibilityResult:
        """Check for conflicts between Monthly and Annual PMs"""

        if pm_type == PMType.ANNUAL:
            monthly_completions = [c for c in recent_completions if c.pm_type == PMType.MONTHLY]
            if monthly_completions:
                latest_monthly = max(monthly_completions, key=lambda x: x.completion_date)
                days_since_monthly = (datetime.now() - latest_monthly.completion_date).days

                if days_since_monthly < 7:
                    return PMEligibilityResult(
                        PMStatus.CONFLICTED,
                        f"Annual blocked - Monthly PM completed {days_since_monthly} days ago"
                    )

        elif pm_type == PMType.MONTHLY:
            annual_completions = [c for c in recent_completions if c.pm_type == PMType.ANNUAL]
            if annual_completions:
                latest_annual = max(annual_completions, key=lambda x: x.completion_date)
                days_since_annual = (datetime.now() - latest_annual.completion_date).days

                if days_since_annual < 30:
                    return PMEligibilityResult(
                        PMStatus.CONFLICTED,
                        f"Monthly blocked - Annual PM completed {days_since_annual} days ago"
                    )

        return PMEligibilityResult(PMStatus.DUE, "No cross-PM conflicts")

    def _check_due_date(self, equipment: Equipment, pm_type: PMType,
                       recent_completions: List[CompletionRecord]) -> PMEligibilityResult:
        """Check if PM is due based on last completion date"""

        same_type_completions = [c for c in recent_completions if c.pm_type == pm_type]

        if same_type_completions:
            latest_completion = max(same_type_completions, key=lambda x: x.completion_date)
            last_completion_date = latest_completion.completion_date
            source = "pm_completions_table"
        else:
            last_date_str = (equipment.last_monthly_date if pm_type == PMType.MONTHLY
                            else equipment.last_annual_date)
            last_completion_date = self.date_parser.parse_flexible(last_date_str)
            source = "equipment_table"

        # Never completed = high priority
        if not last_completion_date:
            priority = 1000 if pm_type == PMType.MONTHLY else 900
            return PMEligibilityResult(
                PMStatus.DUE,
                f"{pm_type.value} PM never completed - HIGH PRIORITY",
                priority_score=priority
            )

        # Calculate days since last completion
        days_since_completion = (datetime.now() - last_completion_date).days

        if pm_type == PMType.MONTHLY:
            min_days = 30
            max_days = 35
            ideal_frequency = 30
        else:  # PMType.ANNUAL
            min_days = 365
            max_days = 370
            ideal_frequency = 365

        # PM is DUE if it's been at least min_days since completion
        if days_since_completion >= min_days:
            days_overdue = days_since_completion - ideal_frequency

            if days_overdue > 0:
                priority = min(500 + (days_overdue * 10), 999)
                return PMEligibilityResult(
                    PMStatus.DUE,
                    f"{pm_type.value} PM OVERDUE by {days_overdue} days (last: {last_completion_date.strftime('%Y-%m-%d')}, source: {source})",
                    priority_score=priority,
                    days_overdue=days_overdue
                )
            elif days_since_completion <= max_days:
                priority = 300 - abs(days_since_completion - ideal_frequency)
                return PMEligibilityResult(
                    PMStatus.DUE,
                    f"{pm_type.value} PM due now ({days_since_completion} days since last, last: {last_completion_date.strftime('%Y-%m-%d')}, source: {source})",
                    priority_score=priority
                )
            else:
                priority = 200
                return PMEligibilityResult(
                    PMStatus.DUE,
                    f"{pm_type.value} PM due ({days_since_completion} days since last, last: {last_completion_date.strftime('%Y-%m-%d')}, source: {source})",
                    priority_score=priority
                )
        else:
            days_until_due = min_days - days_since_completion
            return PMEligibilityResult(
                PMStatus.NOT_DUE,
                f"{pm_type.value} PM not due for {days_until_due} days (last: {last_completion_date.strftime('%Y-%m-%d')}, source: {source})"
            )

    def bulk_load_next_annual(self) -> None:
        """Load ALL next_annual_pm dates for ALL equipment in one query"""
        print(f"DEBUG: Bulk loading next annual PM dates...")
        cursor = self.completion_repo.conn.cursor()
        cursor.execute('''
            SELECT bfm_equipment_no, next_annual_pm
            FROM equipment
            WHERE next_annual_pm IS NOT NULL AND next_annual_pm != ''
        ''')

        self._next_annual_cache = {}
        for row in cursor.fetchall():
            bfm_no = row[0]
            next_annual_pm = row[1]
            if next_annual_pm:
                self._next_annual_cache[bfm_no] = next_annual_pm

        print(f"DEBUG: Loaded next annual PM dates for {len(self._next_annual_cache)} equipment items")

    def clear_cache(self):
        """Clear the cache"""
        self._next_annual_cache = None


class PMAssignmentGenerator:
    """Responsible for generating PM assignments"""

    def __init__(self, eligibility_checker: PMEligibilityChecker, root=None):
        self.eligibility_checker = eligibility_checker
        self.root = root  # Store root window for UI updates

    def generate_assignments(self, equipment_list: List[Equipment],
                           week_start: datetime, max_assignments: int) -> List[PMAssignment]:
        """Generate prioritized list of PM assignments"""

        potential_assignments = []
        equipment_priority_map = {}

        total_equipment = len(equipment_list)
        print(f"DEBUG: Processing {total_equipment} equipment items...")

        for idx, equipment in enumerate(equipment_list):
            if idx > 0 and idx % 200 == 0:
                print(f"DEBUG: Progress: {idx}/{total_equipment} equipment processed ({idx*100//total_equipment}%)")
                if self.root:
                    self.root.update_idletasks()

            # Skip inactive equipment
            if equipment.status not in ['Active']:
                continue

            equipment_priority_map[equipment.bfm_no] = equipment.priority

            # Check Monthly PM eligibility
            if equipment.has_monthly:
                monthly_result = self.eligibility_checker.check_eligibility(
                    equipment, PMType.MONTHLY, week_start
                )
                if monthly_result.status == PMStatus.DUE:
                    potential_assignments.append(PMAssignment(
                        equipment.bfm_no,
                        PMType.MONTHLY,
                        equipment.description,
                        monthly_result.priority_score,
                        monthly_result.reason
                    ))

            # Check Annual PM eligibility
            if equipment.has_annual:
                has_monthly_assignment = any(
                    a.bfm_no == equipment.bfm_no and a.pm_type == PMType.MONTHLY
                    for a in potential_assignments
                )

                if not has_monthly_assignment:
                    annual_result = self.eligibility_checker.check_eligibility(
                        equipment, PMType.ANNUAL, week_start
                    )
                    if annual_result.status == PMStatus.DUE:
                        potential_assignments.append(PMAssignment(
                            equipment.bfm_no,
                            PMType.ANNUAL,
                            equipment.description,
                            annual_result.priority_score,
                            annual_result.reason
                        ))

        print(f"DEBUG: Finished processing all {total_equipment} equipment items")
        print(f"DEBUG: Found {len(potential_assignments)} potential assignments")

        # Sort by priority level first, then by priority_score
        print(f"DEBUG: Sorting assignments by priority...")
        potential_assignments.sort(
            key=lambda x: (
                equipment_priority_map.get(x.bfm_no, 99),
                -x.priority_score
            )
        )

        return potential_assignments[:max_assignments]


class PMSchedulingService:
    """Main PM scheduling orchestrator"""

    def __init__(self, conn, technicians: List[str], root=None):
        self.conn = conn
        self.technicians = technicians
        self.root = root

        # Initialize components
        self.date_parser = DateParser(conn)
        self.completion_repo = CompletionRecordRepository(conn)
        self.eligibility_checker = PMEligibilityChecker(self.date_parser, self.completion_repo)
        self.assignment_generator = PMAssignmentGenerator(self.eligibility_checker, root)

        # Load priority assets from CSV files
        self.priority_map = self._load_priority_assets()

    def _load_priority_assets(self) -> Dict[str, int]:
        """Load priority assets from CSV files"""
        priority_map = {}

        priority_files = [
            ('PM_LIST_A220_1.csv', 1),  # P1 assets
            ('PM_LIST_A220_2.csv', 2),  # P2 assets
            ('PM_LIST_A220_3.csv', 3),  # P3 assets
        ]

        try:
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
            except NameError:
                script_dir = os.getcwd()

            for filename, priority in priority_files:
                filepath = os.path.join(script_dir, filename)

                if not os.path.exists(filepath):
                    print(f"Info: Priority file {filename} not found at {filepath}")
                    continue

                try:
                    df = pd.read_csv(filepath, encoding='utf-8-sig')

                    if 'BFM' not in df.columns:
                        print(f"Warning: BFM column not found in {filename}")
                        continue

                    for bfm in df['BFM'].dropna().unique():
                        try:
                            if pd.notna(bfm):
                                if isinstance(bfm, str):
                                    bfm_str = bfm.strip()
                                elif isinstance(bfm, (int, float)):
                                    bfm_str = str(int(float(bfm)))
                                else:
                                    bfm_str = str(bfm)

                                if bfm_str:
                                    priority_map[bfm_str] = priority
                        except (ValueError, TypeError) as e:
                            print(f"Warning: Could not convert BFM value '{bfm}' in {filename}: {e}")
                            continue

                    print(f"Loaded {len([b for b in df['BFM'].dropna() if pd.notna(b)])} priority {priority} assets from {filename}")

                except Exception as e:
                    print(f"Error loading {filename}: {e}")

        except Exception as e:
            print(f"Error loading priority files: {e}")

        return priority_map

    def generate_weekly_schedule(self, week_start: datetime, max_pms: int = 130) -> List[PMAssignment]:
        """Generate weekly PM schedule with optimized performance"""
        print(f"\n=== Generating PM Schedule for Week {week_start.strftime('%Y-%m-%d')} ===")

        # Bulk load all data upfront
        self.completion_repo.bulk_load_completions()
        self.completion_repo.bulk_load_scheduled(week_start)
        self.completion_repo.bulk_load_uncompleted_schedules(week_start)
        self.eligibility_checker.bulk_load_next_annual()

        # Load equipment from database
        equipment_list = self._load_equipment_with_priority()

        # Generate assignments
        assignments = self.assignment_generator.generate_assignments(
            equipment_list, week_start, max_pms
        )

        return assignments

    def _load_equipment_with_priority(self) -> List[Equipment]:
        """Load equipment from database with priority information"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT bfm_equipment_no, description, monthly_pm, annual_pm,
                   last_monthly_pm, last_annual_pm, status
            FROM equipment
            WHERE status = 'Active'
            ORDER BY bfm_equipment_no
        ''')

        equipment_list = []
        for row in cursor.fetchall():
            bfm_no = row[0]
            priority = self.priority_map.get(str(bfm_no), 99)

            equipment_list.append(Equipment(
                bfm_no=bfm_no,
                description=row[1],
                has_monthly=row[2] == 'X' if row[2] else False,
                has_annual=row[3] == 'X' if row[3] else False,
                last_monthly_date=row[4],
                last_annual_date=row[5],
                status=row[6],
                priority=priority
            ))

        return equipment_list
