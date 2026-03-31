# Time Tracking Page Implementation Plan (Days 5-6)

## Overview
Implement comprehensive time tracking UI with stopwatch/timer functionality, manual time entry, summary statistics, and visual reports using Recharts.

**Estimated Time:** 16-20 hours
**Dependencies:** react-timer-hook, recharts, date-fns (already installed ✓)

---

## Architecture Overview

### Technology Stack
- **Timer Logic:** react-timer-hook's `useStopwatch` and `useTimer` hooks
- **Charts:** Recharts (LineChart, BarChart, PieChart)
- **Date Handling:** date-fns for formatting and calculations
- **State Persistence:** LocalStorage for active timer state
- **API:** TimeTracking endpoints (CRUD operations)

### Component Hierarchy
```
TimeTrackingPage (main container)
├── ActiveTimerWidget (running timer + controls)
├── TimeSummaryCards (weekly/monthly stats)
├── TimeReportsSection (charts + filters)
│   ├── WeeklyHoursChart (LineChart)
│   ├── ActivityBreakdownChart (PieChart)
│   └── DailyDistributionChart (BarChart)
├── TimeEntriesTable (list of entries)
└── TimeEntryFormModal (manual entry creation/edit)
```

---

## Implementation Steps

### Step 1: Create API Client (~30 min)
**File:** `frontend/src/api/time-tracking.ts`

**Endpoints to implement:**
```typescript
timeTrackingApi = {
  // Time Entries
  getAll(params?: { skip, limit, order_id, user_id, start_date, end_date })
  getById(id: string)
  create(entry: TimeEntryCreateInput)
  update(id: string, entry: TimeEntryUpdateInput)
  delete(id: string)

  // Analytics
  getSummary(params?: { start_date, end_date, user_id })
  getWeeklyReport(params?: { weeks, user_id })
  getActivityBreakdown(params?: { start_date, end_date })
}
```

**Type Definitions to add to `types.ts`:**
```typescript
interface TimeEntryType {
  id: string;
  order_id: number;
  user_id: number;
  activity_id: number;
  start_time: string;
  end_time: string | null;
  duration_minutes: number | null;
  location?: string;
  notes?: string;
  created_at: string;
  // Populated fields
  order?: OrderType;
  activity?: ActivityType;
}

interface TimeEntryCreateInput {
  order_id: number;
  activity_id: number;
  start_time: string;
  end_time?: string;
  duration_minutes?: number;
  location?: string;
  notes?: string;
}

interface ActivityType {
  id: number;
  name: string;
  category: string;
  icon?: string;
  color?: string;
}

interface TimeSummaryStats {
  total_hours: number;
  billable_hours: number;
  entries_count: number;
  average_session_minutes: number;
  most_used_activity: string;
}
```

---

### Step 2: Build ActiveTimerWidget (~3-4 hours)
**File:** `frontend/src/components/time-tracking/ActiveTimerWidget.tsx`
**Lines:** ~300-350

**Features:**
1. **Stopwatch Integration**
   - Use `useStopwatch` from react-timer-hook
   - Display: HH:MM:SS format
   - Start, Pause, Resume, Stop controls

2. **State Persistence**
   - Save to localStorage when timer starts
   - Restore on page load/refresh
   - Clear localStorage when stopped

3. **Order Selection**
   - Dropdown to select which order to track time for
   - Quick-access to recent orders

4. **Activity Selection**
   - Dropdown for activity type (fabrication, polishing, etc.)
   - Icons and colors from activity config

5. **Location Input**
   - Optional location field (workbench_1, vault, etc.)

6. **Notes Field**
   - Quick notes about the work session

7. **Action Buttons**
   - Start Timer → Creates time entry with start_time
   - Pause/Resume → Visual feedback
   - Stop & Save → Calls API to save entry with end_time

**State Structure:**
```typescript
interface TimerState {
  isRunning: boolean;
  isPaused: boolean;
  entryId: string | null; // Created when timer starts
  orderId: number | null;
  activityId: number | null;
  location: string;
  notes: string;
  startTime: Date | null;
}
```

**LocalStorage Key:** `goldsmith_active_timer`

**Implementation Details:**
```typescript
const {
  seconds,
  minutes,
  hours,
  isRunning,
  start,
  pause,
  reset,
} = useStopwatch({ autoStart: false });

// On component mount: check localStorage and restore timer
useEffect(() => {
  const savedTimer = localStorage.getItem('goldsmith_active_timer');
  if (savedTimer) {
    const timerState = JSON.parse(savedTimer);
    // Calculate elapsed time and resume
    const elapsed = Date.now() - new Date(timerState.startTime).getTime();
    const offsetTimestamp = new Date(Date.now() - elapsed);
    start(offsetTimestamp);
  }
}, []);

// Save to localStorage when timer changes
useEffect(() => {
  if (isRunning && timerState.entryId) {
    localStorage.setItem('goldsmith_active_timer', JSON.stringify(timerState));
  }
}, [isRunning, timerState]);
```

---

### Step 3: Build TimeEntryFormModal (~3-4 hours)
**File:** `frontend/src/components/time-tracking/TimeEntryFormModal.tsx`
**Lines:** ~350-400

**Features:**
1. **Manual Time Entry**
   - Order selection (required)
   - Activity selection (required)
   - Start date/time picker
   - End date/time picker
   - Auto-calculate duration from start/end
   - Or: manual duration input (converts to end_time)

2. **Validation**
   - End time must be after start time
   - Duration must be positive
   - Order and activity required

3. **Form Fields:**
   - Order (dropdown with search)
   - Activity (dropdown with icons)
   - Start Date + Time (datetime-local input)
   - End Date + Time (datetime-local input)
   - Duration (read-only, calculated)
   - Location (optional text)
   - Notes (optional textarea)

4. **Edit Mode**
   - Pre-populate all fields
   - Allow modifications
   - Update existing entry

**Duration Calculation:**
```typescript
const calculateDuration = (start: string, end: string): number => {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const diffMs = endDate.getTime() - startDate.getTime();
  return Math.floor(diffMs / 1000 / 60); // minutes
};

const formatDuration = (minutes: number): string => {
  const hrs = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hrs}h ${mins}m`;
};
```

---

### Step 4: Build TimeSummaryCards (~2-3 hours)
**File:** `frontend/src/components/time-tracking/TimeSummaryCards.tsx`
**Lines:** ~200-250

**Features:**
1. **4 Summary Cards:**
   - **Total Hours (This Week)**
     - Large number display
     - Comparison to last week (+15% or -5%)
     - Icon: ⏱️

   - **Billable Hours**
     - Total billable time
     - Percentage of total
     - Icon: 💰

   - **Active Sessions**
     - Number of time entries
     - Average session length
     - Icon: 📊

   - **Most Used Activity**
     - Top activity name
     - Hours spent
     - Icon: 🔧

2. **Time Period Selector**
   - This Week (default)
   - This Month
   - Last 7 Days
   - Last 30 Days
   - Custom Range

3. **API Call:**
   - Fetch summary data on mount
   - Refresh when period changes

**Card Layout:**
```typescript
<div className="time-summary-cards">
  <div className="summary-card">
    <div className="card-header">
      <span className="card-icon">⏱️</span>
      <h3>Total Hours</h3>
    </div>
    <div className="card-value">
      <span className="main-value">{totalHours.toFixed(1)}h</span>
      <span className="comparison positive">+15% vs last week</span>
    </div>
  </div>
  {/* ...other cards */}
</div>
```

---

### Step 5: Build TimeReportsSection (~4-5 hours)
**File:** `frontend/src/components/time-tracking/TimeReportsSection.tsx`
**Lines:** ~400-450

**Features:**
1. **Weekly Hours Trend (LineChart)**
   - X-axis: Days of the week or weeks
   - Y-axis: Hours worked
   - Line showing trend over time
   - Data points on hover

2. **Activity Breakdown (PieChart)**
   - Show time distribution by activity
   - Color-coded by activity type
   - Percentage labels
   - Legend with activity names

3. **Daily Distribution (BarChart)**
   - X-axis: Days (Mon-Sun)
   - Y-axis: Hours
   - Bars showing hours per day
   - Tooltip with exact time

4. **Filters:**
   - Date range selector
   - Activity filter (all, specific activity)
   - Order filter (all, specific order)

**Recharts Implementation:**
```typescript
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const WeeklyHoursChart = ({ data }) => (
  <ResponsiveContainer width="100%" height={300}>
    <LineChart data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="date" />
      <YAxis label={{ value: 'Hours', angle: -90, position: 'insideLeft' }} />
      <Tooltip />
      <Line
        type="monotone"
        dataKey="hours"
        stroke="#3498db"
        strokeWidth={2}
        dot={{ fill: '#3498db', r: 4 }}
      />
    </LineChart>
  </ResponsiveContainer>
);
```

**Data Format:**
```typescript
// Weekly hours data
[
  { date: 'Mon', hours: 8.5 },
  { date: 'Tue', hours: 7.2 },
  { date: 'Wed', hours: 9.1 },
  // ...
]

// Activity breakdown
[
  { name: 'Fabrication', hours: 25, color: '#3498db' },
  { name: 'Polishing', hours: 10, color: '#2ecc71' },
  { name: 'Setting', hours: 8, color: '#e74c3c' },
  // ...
]
```

---

### Step 6: Build TimeTrackingPage (~3-4 hours)
**File:** `frontend/src/pages/TimeTrackingPage.tsx`
**Lines:** ~500-550

**Layout Structure:**
```
┌─────────────────────────────────────────────────────┐
│ Active Timer Widget                                 │
│ (if timer is running, show prominent widget)       │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ Time Summary Cards (4 cards in a row)              │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ Time Reports Section (3 charts)                    │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ Controls: [+ Manual Entry] [Filters] [Export CSV]  │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ Time Entries Table                                  │
│ - Date/Time | Order | Activity | Duration | Actions │
│ - Pagination                                        │
└─────────────────────────────────────────────────────┘
```

**Features:**
1. **Active Timer Widget**
   - Prominent display when timer is running
   - Collapsed/hidden when no active timer

2. **Summary Cards**
   - Period selector affecting all data

3. **Reports Section**
   - Tabbed interface (Weekly Trend | Activity Breakdown | Daily Distribution)
   - Date range filter

4. **Time Entries Table**
   - List all time entries with pagination
   - Search by order number or notes
   - Filter by activity, date range
   - Sort by date, duration
   - Actions: Edit, Delete
   - Click row to view details

5. **Manual Entry Button**
   - Opens TimeEntryFormModal
   - Create mode by default

**State Management:**
```typescript
const [entries, setEntries] = useState<TimeEntryType[]>([]);
const [filteredEntries, setFilteredEntries] = useState<TimeEntryType[]>([]);
const [isModalOpen, setIsModalOpen] = useState(false);
const [selectedEntry, setSelectedEntry] = useState<TimeEntryType | null>(null);
const [summaryStats, setSummaryStats] = useState<TimeSummaryStats | null>(null);
const [timePeriod, setTimePeriod] = useState<'week' | 'month' | '7days' | '30days'>('week');
```

---

### Step 7: Create Styling (~2-3 hours)
**File:** `frontend/src/styles/time-tracking.css`
**Lines:** ~500-600

**Key Styles:**

1. **Active Timer Widget**
   - Large, prominent display with gradient background
   - Pulsing animation when running
   - Timer display: 72px font size, monospace
   - Control buttons with icons

2. **Summary Cards**
   - Grid layout (4 columns)
   - Gradient backgrounds
   - Large value displays
   - Comparison indicators (green up arrow, red down arrow)

3. **Charts Section**
   - White background cards
   - Box shadows
   - Responsive containers

4. **Time Entries Table**
   - Zebra striping
   - Hover effects
   - Activity badges with colors
   - Duration badges

**Color Scheme:**
```css
:root {
  --timer-running: #27ae60;
  --timer-paused: #f39c12;
  --timer-stopped: #95a5a6;
  --chart-primary: #3498db;
  --chart-secondary: #2ecc71;
  --chart-tertiary: #e74c3c;
}
```

---

### Step 8: Add Routing (~15 min)
**Files to modify:**
- `frontend/src/pages/index.ts` - Export TimeTrackingPage
- `frontend/src/App.tsx` - Add route `/time-tracking`
- `frontend/src/layouts/MainLayout.tsx` - Add nav link

**Navigation:**
- Icon: ⏱️
- Label: "Zeiterfassung"
- Route: `/time-tracking`

---

## Testing Checklist

### Timer Widget
- [ ] Timer starts from 00:00:00
- [ ] Timer continues counting when page refreshes
- [ ] Timer stops and saves entry correctly
- [ ] Pause/resume works properly
- [ ] LocalStorage is cleared on stop
- [ ] Can't start timer without order/activity selected

### Manual Entry
- [ ] Create new time entry manually
- [ ] Edit existing time entry
- [ ] Delete time entry
- [ ] Duration auto-calculates from start/end times
- [ ] Validation shows errors for invalid data
- [ ] End time must be after start time

### Summary Cards
- [ ] Stats update when period changes
- [ ] Comparison percentages calculate correctly
- [ ] Shows "No data" when no entries exist

### Charts
- [ ] Charts render with sample data
- [ ] Tooltips show on hover
- [ ] Date range filter updates charts
- [ ] Responsive on mobile (scales down)

### Table
- [ ] Pagination works correctly
- [ ] Search filters entries
- [ ] Sort by date/duration works
- [ ] Edit/Delete actions work

---

## Risk Assessment

### High Risk
1. **Timer State Persistence**
   - Risk: Timer resets on page refresh
   - Mitigation: Use localStorage with timestamp calculation
   - Fallback: Show warning before refresh

2. **Time Zone Issues**
   - Risk: Start/end times in different time zones
   - Mitigation: Always use ISO strings, convert on backend
   - Testing: Test across time zones

### Medium Risk
1. **Chart Performance**
   - Risk: Slow rendering with large datasets
   - Mitigation: Limit data points, use pagination
   - Optimization: Memoize chart data

2. **LocalStorage Conflicts**
   - Risk: Multiple tabs with different timers
   - Mitigation: Use single active timer model
   - Warning: Show alert if timer active in another tab

### Low Risk
1. **Browser Compatibility**
   - Risk: datetime-local input not supported in older browsers
   - Mitigation: Use date-fns polyfill if needed
   - Fallback: Separate date and time inputs

---

## Success Criteria

✅ **Functional Requirements:**
- [ ] Can start/stop timer for an order
- [ ] Timer persists across page refreshes
- [ ] Can create manual time entries
- [ ] Can edit/delete time entries
- [ ] Summary cards show accurate statistics
- [ ] Charts display time data visually
- [ ] Table lists all entries with pagination

✅ **UX Requirements:**
- [ ] Timer is prominent and easy to use
- [ ] Forms validate input properly
- [ ] Charts are clear and readable
- [ ] Mobile responsive (all components)
- [ ] Loading states for all API calls
- [ ] Error messages are helpful

✅ **Technical Requirements:**
- [ ] Uses react-timer-hook correctly
- [ ] Uses Recharts for all visualizations
- [ ] LocalStorage managed properly
- [ ] API client follows existing patterns
- [ ] TypeScript types are complete
- [ ] CSS is organized and maintainable

---

## Implementation Order

**Priority 1 (Core Functionality - Day 5):**
1. API Client + Type Definitions (30 min)
2. ActiveTimerWidget (3-4 hours)
3. TimeEntryFormModal (3-4 hours)
4. Basic TimeTrackingPage layout (1 hour)
5. Routing + Navigation (15 min)

**Priority 2 (Analytics & Polish - Day 6):**
6. TimeSummaryCards (2-3 hours)
7. TimeReportsSection with Charts (4-5 hours)
8. Time Entries Table (2 hours)
9. Comprehensive Styling (2-3 hours)
10. Testing & Bug Fixes (2 hours)

**Total Estimated Time:** 16-20 hours

---

## Notes

- **react-timer-hook documentation:** https://www.npmjs.com/package/react-timer-hook
- **Recharts documentation:** https://recharts.org/
- **date-fns documentation:** https://date-fns.org/

- Use German labels throughout (Zeiterfassung, Stunden, Minuten, etc.)
- Follow existing code patterns from MaterialsPage/OrdersPage
- Maintain consistent styling with rest of application
- Use existing modal patterns for forms
- Ensure all times are stored in ISO 8601 format
