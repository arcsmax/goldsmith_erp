# Ultra-Detailed Implementation Plan: Phase 2-4
**Created:** 2025-11-10 (Post-Research)
**Research Sources:** React timer libraries, chart libraries, dashboard patterns, calendar UI
**Status:** Ready for Implementation

---

## Research Summary & Technology Decisions

### **Key Findings from 2025 Best Practices:**

#### 1. **Time Tracking Components**
**Winner: react-timer-hook**
- ✅ Most practical for functional components
- ✅ Provides hooks: `useTimer`, `useStopwatch`, `useTime`
- ✅ Built-in methods: start, pause, resume, restart
- ✅ Strong TypeScript support
- ✅ Lightweight bundle size
- ✅ Well-documented

**Alternative Considered:** use-timer, react-time-tracker-stopwatch
**Decision:** Use react-timer-hook for professional features and stability

#### 2. **Chart Library for Dashboard**
**Winner: Recharts**
- ✅ 24.8K+ GitHub stars (most popular)
- ✅ SVG-based rendering (responsive)
- ✅ Excellent React integration
- ✅ Easy to customize
- ✅ Great TypeScript support
- ✅ Perfect for small-medium datasets

**Alternative Considered:** Chart.js (canvas-based, harder to style), Tremor (pre-built components)
**Decision:** Use Recharts for flexibility and popularity

#### 3. **Calendar/Scheduling**
**Options:** FullCalendar, DayPilot, react-calendar
**Decision:** Build simple custom calendar component
- Simpler for our use case (just deadline visualization)
- No heavy dependencies
- Full control over styling
- Can upgrade to FullCalendar later if needed

#### 4. **Dashboard Design Principles (2025)**
Based on UXPin, Medium, DesignRush research:
- **5-10 KPIs max** (avoid cognitive overload)
- **F-Pattern layout** (top-left for most important info)
- **5-Second Rule** (user understands main message in 5 seconds)
- **Context for each KPI** (trend lines, comparisons: "+15% vs last month")
- **Single screen** (no scrolling for key metrics)
- **Whitespace** (generous spacing between elements)
- **Visual hierarchy** (larger cards for important metrics)
- **AI-ready** (personalization potential for future)

---

## Phase 2: Metal Inventory & Time Tracking UI (Days 4-6)

### **Day 4: MetalInventoryPage** (10-12 hours)

#### **Research-Based Design Decisions:**
- Use table with search/filter/sort (proven pattern from MaterialsPage)
- Colored badges for metal types (visual hierarchy)
- Summary cards at top (F-Pattern: most important info first)
- Responsive design for mobile

#### **Component Breakdown:**

##### **1. MetalInventoryPage.tsx** (Main Page - 400+ lines estimated)

**Features:**
```typescript
// State Management
- purchases: MetalPurchase[] (all purchases from API)
- filteredPurchases: MetalPurchase[] (after search/filter)
- searchQuery: string
- filterMetalType: MetalType | ''
- filterStatus: 'in_stock' | 'partially_used' | 'depleted' | ''
- sortBy: 'date' | 'price' | 'weight'
- page: number
- pageSize: number (25/50/100)
- isModalOpen: boolean
- selectedPurchase: MetalPurchase | null

// Functions
- fetchPurchases() - Get all from API
- filterAndSortPurchases() - Apply filters/search/sort
- handleCreatePurchase() - Create new purchase
- handleDeletePurchase() - Delete purchase (with confirmation)
- openCreateModal(), closeModal()
```

**UI Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ Header: "Metallbestand"                      [+ Kauf]   │
│ Summary: X Käufe • Gesamtwert: €XX,XXX                  │
├─────────────────────────────────────────────────────────┤
│                 SUMMARY CARDS (F-Pattern)               │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│ │Gold 24K  │ │Gold 18K  │ │Silber    │ │Platin    │   │
│ │XXX.XX g  │ │XXX.XX g  │ │XXX.XX g  │ │XX.XX g   │   │
│ │€XX,XXX   │ │€XX,XXX   │ │€XX,XXX   │ │€X,XXX    │   │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│ [Search...] [Metal Type ▼] [Status ▼] [Sort ▼] [25 ▼] │
├─────────────────────────────────────────────────────────┤
│ TABLE: ID | Date | Metal | Weight | Price/g | Total |  │
│        Status | Batch | Actions                         │
│ ─────────────────────────────────────────────────────  │
│ #1 | 2024-01-15 | 🥇Gold 24K | 50.0g | €60.00 | €3000 │
│    | 75% Used | #BATCH-001 | [Edit] [Delete]           │
│ ... (pagination)                                        │
├─────────────────────────────────────────────────────────┤
│ Page 1 of 5 • 120 Käufe     [<<] [<] [>] [>>]          │
└─────────────────────────────────────────────────────────┘
```

##### **2. MetalPurchaseFormModal.tsx** (Form Modal - 400+ lines estimated)

**Fields:**
```typescript
interface FormData {
  metal_type: MetalType                    // Dropdown with icons
  purchase_date: string                    // Date picker (default: today)
  weight_g: string                         // Number input
  price_per_gram: string                   // Number input, € currency
  supplier: string                         // Text input (optional)
  batch_number: string                     // Auto-generated or manual
  purity_percent: string                   // Number (e.g., 99.9)
  notes: string                            // Textarea (optional)
}
```

**Validation:**
- Required: metal_type, purchase_date, weight_g, price_per_gram
- weight_g > 0
- price_per_gram > 0
- purity_percent: 0-100
- Auto-calculate total_cost = weight_g * price_per_gram

**Auto-Generate Batch Number:**
```typescript
// Format: METAL-YYYYMMDD-NNN
// Example: GOLD24K-20241110-001
const generateBatchNumber = (metalType: MetalType, date: Date): string => {
  const metalPrefix = metalType.toUpperCase().replace('_', '');
  const dateStr = date.toISOString().slice(0, 10).replace(/-/g, '');
  const sequence = // Get count of purchases for this date + 1
  return `${metalPrefix}-${dateStr}-${sequence.toString().padStart(3, '0')}`;
};
```

##### **3. MetalSummaryCards.tsx** (Summary Component - 200+ lines estimated)

**Purpose:** Display aggregated metal inventory by type (F-Pattern top section)

**Layout:**
```typescript
interface MetalSummary {
  metal_type: MetalType;
  total_weight_g: number;
  total_value: number;
  average_price_per_gram: number;
  purchase_count: number;
}

// Display 4 cards in a row:
// - Gold 24K
// - Gold 18K
// - Silver 925/999 (combined)
// - Platinum

// Each card shows:
- Icon (🥇 for gold, ⚪ for silver, ◻️ for platinum)
- Metal type name
- Total weight (XXX.XX g)
- Total value (€XX,XXX)
- Average price (€XX.XX/g)
- Number of purchases (X Käufe)
- Color-coded gradient background
```

**Calculation Logic:**
```typescript
const calculateSummary = (purchases: MetalPurchase[]): MetalSummary[] => {
  const summaryMap = new Map<MetalType, MetalSummary>();

  purchases.forEach(purchase => {
    if (!summaryMap.has(purchase.metal_type)) {
      summaryMap.set(purchase.metal_type, {
        metal_type: purchase.metal_type,
        total_weight_g: 0,
        total_value: 0,
        purchase_count: 0,
        average_price_per_gram: 0,
      });
    }

    const summary = summaryMap.get(purchase.metal_type)!;
    const remaining_weight = purchase.weight_g - (purchase.used_weight_g || 0);

    summary.total_weight_g += remaining_weight;
    summary.total_value += remaining_weight * purchase.price_per_gram;
    summary.purchase_count += 1;
  });

  // Calculate averages
  summaryMap.forEach(summary => {
    summary.average_price_per_gram = summary.total_value / summary.total_weight_g;
  });

  return Array.from(summaryMap.values());
};
```

##### **4. metal-inventory.css** (Styling - 400+ lines estimated)

**Key Styles:**
- `.metal-summary-cards` - Grid layout for summary cards
- `.metal-card` - Individual summary card with gradient
- `.metal-card-gold` - Gold gradient (#FFD700 to #FFA500)
- `.metal-card-silver` - Silver gradient (#C0C0C0 to #A8A8A8)
- `.metal-card-platinum` - Platinum gradient (#E5E4E2 to #C0C0C0)
- `.metal-purchase-table` - Table styling
- `.batch-number` - Monospace font, badge style
- `.status-indicator` - Progress bar showing used percentage
- `.metal-type-icon` - Large icon display

##### **5. api/metal-inventory.ts** (API Client - 100+ lines estimated)

**Endpoints:**
```typescript
export const metalInventoryApi = {
  // Get all purchases
  getAll: async (params?: { metal_type?: MetalType; skip?: number; limit?: number }) => {
    const response = await axios.get('/api/v1/metal-inventory', { params });
    return response.data;
  },

  // Get single purchase
  getById: async (id: number) => {
    const response = await axios.get(`/api/v1/metal-inventory/${id}`);
    return response.data;
  },

  // Create purchase
  create: async (data: MetalPurchaseCreateInput) => {
    const response = await axios.post('/api/v1/metal-inventory', data);
    return response.data;
  },

  // Get summary statistics
  getSummary: async () => {
    const response = await axios.get('/api/v1/metal-inventory/summary');
    return response.data;
  },

  // Delete purchase
  delete: async (id: number) => {
    const response = await axios.delete(`/api/v1/metal-inventory/${id}`);
    return response.data;
  },
};
```

#### **Implementation Steps:**

**Step 1: API Client** (30 min)
1. Create `frontend/src/api/metal-inventory.ts`
2. Define all API methods
3. Export metalInventoryApi

**Step 2: Summary Cards Component** (90 min)
1. Create `MetalSummaryCards.tsx`
2. Implement calculation logic
3. Add gradient styling for each metal type
4. Make responsive (2 cards per row on mobile)

**Step 3: Purchase Form Modal** (120 min)
1. Create `MetalPurchaseFormModal.tsx`
2. Implement form with all fields
3. Add validation
4. Implement batch number auto-generation
5. Add total cost calculation display

**Step 4: Main Page** (180 min)
1. Create `MetalInventoryPage.tsx`
2. Implement state management
3. Add search/filter/sort logic
4. Build table layout
5. Integrate summary cards
6. Wire up modal

**Step 5: Styling** (90 min)
1. Create `metal-inventory.css`
2. Style summary cards with gradients
3. Style table and badges
4. Add responsive breakpoints

**Step 6: Testing** (60 min)
1. Test CRUD operations
2. Test filters and search
3. Test batch number generation
4. Test summary calculations
5. Verify responsive design

**Total Day 4: 10-12 hours** ✅

---

### **Day 5-6: TimeTrackingPage** (16-20 hours)

#### **Research-Based Design Decisions:**
- Use react-timer-hook for timer widget (industry standard)
- Stopwatch pattern: start/pause/resume/stop
- Display running timer prominently
- Table for time entry history
- Reports with charts (using Recharts)

#### **Component Breakdown:**

##### **1. TimeTrackingPage.tsx** (Main Page - 500+ lines estimated)

**Features:**
```typescript
// State Management
- timeEntries: TimeEntry[] (all entries from API)
- filteredEntries: TimeEntry[] (after filters)
- filterDateRange: 'today' | 'week' | 'month' | 'custom'
- filterUser: number | ''
- filterOrder: number | ''
- groupBy: 'user' | 'order' | 'none'
- page: number
- pageSize: number
- isModalOpen: boolean
- selectedEntry: TimeEntry | null
- activeTimer: RunningTimer | null (if timer is running)

// Functions
- fetchTimeEntries() - Get all from API
- filterEntries() - Apply date range, user, order filters
- groupEntries() - Group by user or order
- handleCreateEntry() - Create manual entry
- handleStartTimer() - Start new timer
- handleStopTimer() - Stop timer and save
```

**UI Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ Header: "Zeiterfassung"         [+ Manueller Eintrag]   │
├─────────────────────────────────────────────────────────┤
│              ACTIVE TIMER WIDGET (if running)           │
│ ┌───────────────────────────────────────────────────┐   │
│ │ ⏱️  Läuft: Auftrag #123 - Polieren                │   │
│ │                                                    │   │
│ │         ⏱️ 02:45:33                               │   │
│ │                                                    │   │
│ │  [⏸️ Pause] [⏹️ Stopp & Speichern]                │   │
│ └───────────────────────────────────────────────────┘   │
│                                                          │
│              START NEW TIMER (if not running)            │
│ ┌───────────────────────────────────────────────────┐   │
│ │ Auftrag: [Auftrag auswählen... ▼]                 │   │
│ │ Aufgabe: [Design ▼]                               │   │
│ │ [▶️ Timer starten]                                 │   │
│ └───────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│        WEEKLY SUMMARY (5-Second Rule: Key Info)         │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│ │Diese Wo. │ │Heute     │ │Monat     │ │Gesamt    │   │
│ │40.5 Std  │ │8.2 Std   │ │165 Std   │ │1,234 Std │   │
│ │+12%      │ │Normal    │ │-5%       │ │Alle Zeit │   │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│ [Date Range ▼] [User ▼] [Order ▼] [Group By ▼] [25 ▼] │
├─────────────────────────────────────────────────────────┤
│ TABLE: Date | Order | User | Task | Hours | Notes |    │
│        Actions                                           │
│ ──────────────────────────────────────────────────────  │
│ 2024-11-10 | #123 | Max | Polieren | 3.5h | ... | [❌]│
│ ... (pagination + grouping support)                     │
├─────────────────────────────────────────────────────────┤
│ Page 1 of 10 • Total: 42.5 Stunden   [<<] [<] [>] [>>] │
└─────────────────────────────────────────────────────────┘
```

##### **2. ActiveTimerWidget.tsx** (Timer Component - 300+ lines)

**Using react-timer-hook:**
```typescript
import { useStopwatch } from 'react-timer-hook';

interface ActiveTimerWidgetProps {
  onStop: (hours: number) => void;
  onPause: () => void;
  onResume: () => void;
  orderId?: number;
  orderTitle?: string;
  taskType?: string;
}

export const ActiveTimerWidget: React.FC<ActiveTimerWidgetProps> = ({
  onStop,
  onPause,
  onResume,
  orderId,
  orderTitle,
  taskType
}) => {
  const {
    totalSeconds,
    seconds,
    minutes,
    hours,
    isRunning,
    start,
    pause,
    reset,
  } = useStopwatch({ autoStart: true });

  const handleStop = () => {
    pause();
    const totalHours = totalSeconds / 3600;
    onStop(totalHours);
  };

  const handlePause = () => {
    pause();
    onPause();
  };

  const handleResume = () => {
    start();
    onResume();
  };

  return (
    <div className="active-timer-widget">
      <div className="timer-info">
        {orderId && (
          <div className="timer-order">
            ⚙️ Auftrag #{orderId}: {orderTitle}
          </div>
        )}
        {taskType && (
          <div className="timer-task">Aufgabe: {taskType}</div>
        )}
      </div>

      <div className="timer-display">
        <span className="timer-time">
          {String(hours).padStart(2, '0')}:
          {String(minutes).padStart(2, '0')}:
          {String(seconds).padStart(2, '0')}
        </span>
      </div>

      <div className="timer-controls">
        {isRunning ? (
          <button onClick={handlePause} className="btn-pause">
            ⏸️ Pause
          </button>
        ) : (
          <button onClick={handleResume} className="btn-resume">
            ▶️ Fortsetzen
          </button>
        )}
        <button onClick={handleStop} className="btn-stop">
          ⏹️ Stopp & Speichern
        </button>
      </div>
    </div>
  );
};
```

**Features:**
- Large, readable timer display (HH:MM:SS)
- Pause/Resume functionality
- Stop button saves entry to database
- Display current order and task
- Visual indicator when running (pulsing animation)
- Persist timer state in localStorage (survives page refresh!)

**LocalStorage Persistence:**
```typescript
// Save timer state on every second
useEffect(() => {
  if (isRunning) {
    localStorage.setItem('activeTimer', JSON.stringify({
      orderId,
      taskType,
      startTime: Date.now() - (totalSeconds * 1000),
      totalSeconds,
    }));
  }
}, [totalSeconds]);

// Load timer state on mount
useEffect(() => {
  const saved = localStorage.getItem('activeTimer');
  if (saved) {
    const { startTime, orderId, taskType } = JSON.parse(saved);
    const elapsedSeconds = Math.floor((Date.now() - startTime) / 1000);
    // Resume stopwatch with elapsed time
    const offsetTimestamp = new Date();
    offsetTimestamp.setSeconds(offsetTimestamp.getSeconds() + elapsedSeconds);
    reset(offsetTimestamp, true);
  }
}, []);
```

##### **3. TimeEntryFormModal.tsx** (Manual Entry Form - 350+ lines)

**Fields:**
```typescript
interface FormData {
  order_id: string                    // Searchable dropdown
  task_type: string                   // Dropdown
  date: string                        // Date picker (default: today)
  start_time: string                  // Time picker (optional)
  end_time: string                    // Time picker (optional)
  hours: string                       // Number input OR auto-calc from times
  notes: string                       // Textarea
}

// Task Types
const TASK_TYPES = [
  'Design',
  'Manufacturing',
  'Polish',
  'Repair',
  'Stone Setting',
  'Quality Check',
  'Meeting',
  'Admin',
  'Other'
];
```

**Auto-Calculate Hours:**
```typescript
useEffect(() => {
  if (formData.start_time && formData.end_time) {
    const start = new Date(`${formData.date}T${formData.start_time}`);
    const end = new Date(`${formData.date}T${formData.end_time}`);
    const diffMs = end.getTime() - start.getTime();
    const hours = diffMs / (1000 * 60 * 60);

    if (hours > 0) {
      setFormData(prev => ({ ...prev, hours: hours.toFixed(2) }));
    }
  }
}, [formData.start_time, formData.end_time, formData.date]);
```

**Validation:**
- Required: order_id, task_type, date, hours
- hours > 0
- If start_time and end_time: end must be after start
- Date cannot be in future

##### **4. TimeSummaryCards.tsx** (Summary Component - 200+ lines)

**Purpose:** Display weekly/monthly summary (F-Pattern, 5-Second Rule)

**Cards:**
1. **This Week** - Total hours, % change vs last week
2. **Today** - Hours logged today, status (under/over target)
3. **This Month** - Total hours, % change vs last month
4. **All Time** - Total hours ever tracked

**Data Calculation:**
```typescript
interface TimeSummary {
  thisWeek: { hours: number; percentChange: number };
  today: { hours: number; status: 'under' | 'normal' | 'over' };
  thisMonth: { hours: number; percentChange: number };
  allTime: { hours: number };
}

const calculateSummary = (entries: TimeEntry[]): TimeSummary => {
  const now = new Date();
  const weekStart = startOfWeek(now);
  const monthStart = startOfMonth(now);
  const today = startOfDay(now);

  // Filter entries
  const thisWeekEntries = entries.filter(e => new Date(e.date) >= weekStart);
  const todayEntries = entries.filter(e => isSameDay(new Date(e.date), today));
  const thisMonthEntries = entries.filter(e => new Date(e.date) >= monthStart);

  // Sum hours
  const thisWeekHours = sumHours(thisWeekEntries);
  const todayHours = sumHours(todayEntries);
  const thisMonthHours = sumHours(thisMonthEntries);
  const allTimeHours = sumHours(entries);

  // Calculate % changes (compare with previous period)
  const lastWeekEntries = entries.filter(e => {
    const date = new Date(e.date);
    return date >= subWeeks(weekStart, 1) && date < weekStart;
  });
  const lastWeekHours = sumHours(lastWeekEntries);
  const weekPercentChange = ((thisWeekHours - lastWeekHours) / lastWeekHours) * 100;

  // Similar for month

  return {
    thisWeek: { hours: thisWeekHours, percentChange: weekPercentChange },
    today: {
      hours: todayHours,
      status: todayHours < 7 ? 'under' : todayHours > 9 ? 'over' : 'normal'
    },
    thisMonth: { hours: thisMonthHours, percentChange: monthPercentChange },
    allTime: { hours: allTimeHours },
  };
};
```

##### **5. TimeReportsSection.tsx** (Reports with Charts - 400+ lines)

**Using Recharts for visualization:**

**Report Types:**
1. **Weekly Bar Chart** - Hours per day of week
2. **Monthly Line Chart** - Hours trend over month
3. **By Project Pie Chart** - Hours distribution by order
4. **By Task Type Pie Chart** - Hours distribution by task

**Example - Weekly Bar Chart:**
```typescript
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface WeeklyData {
  day: string;
  hours: number;
}

export const WeeklyHoursChart: React.FC<{ entries: TimeEntry[] }> = ({ entries }) => {
  const data = calculateWeeklyData(entries);

  return (
    <div className="chart-container">
      <h3>Wochenstunden</h3>
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="day" />
          <YAxis label={{ value: 'Stunden', angle: -90, position: 'insideLeft' }} />
          <Tooltip />
          <Bar dataKey="hours" fill="#667eea" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

const calculateWeeklyData = (entries: TimeEntry[]): WeeklyData[] => {
  const weekStart = startOfWeek(new Date());
  const days = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

  return days.map((day, index) => {
    const date = addDays(weekStart, index);
    const dayEntries = entries.filter(e => isSameDay(new Date(e.date), date));
    const hours = sumHours(dayEntries);

    return { day, hours };
  });
};
```

**Report Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ Reports & Analytics                                      │
├─────────────────────────────────────────────────────────┤
│ ┌──────────────────────┐ ┌──────────────────────┐       │
│ │ Weekly Bar Chart     │ │ Monthly Line Chart   │       │
│ │ (Hours per day)      │ │ (Trend over time)    │       │
│ │   [Chart]            │ │   [Chart]            │       │
│ └──────────────────────┘ └──────────────────────┘       │
│                                                          │
│ ┌──────────────────────┐ ┌──────────────────────┐       │
│ │ By Project Pie       │ │ By Task Type Pie     │       │
│ │ (Hours distribution) │ │ (Hours distribution) │       │
│ │   [Chart]            │ │   [Chart]            │       │
│ └──────────────────────┘ └──────────────────────┘       │
└─────────────────────────────────────────────────────────┘
```

##### **6. time-tracking.css** (Styling - 500+ lines estimated)

**Key Styles:**
- `.active-timer-widget` - Large, prominent timer display
- `.timer-display` - Huge font size (3rem+), monospace
- `.timer-running` - Pulsing animation
- `.time-summary-cards` - Grid layout
- `.summary-card-positive` - Green for positive % change
- `.summary-card-negative` - Red for negative % change
- `.chart-container` - Chart wrapper with padding
- `.time-entry-table` - Table styling with grouping support

##### **7. api/time-tracking.ts** (API Client - 150+ lines)

**Endpoints:**
```typescript
export const timeTrackingApi = {
  getAll: async (params?: {
    user_id?: number;
    order_id?: number;
    date_from?: string;
    date_to?: string;
    skip?: number;
    limit?: number;
  }) => {
    const response = await axios.get('/api/v1/time-tracking', { params });
    return response.data;
  },

  create: async (data: TimeEntryCreateInput) => {
    const response = await axios.post('/api/v1/time-tracking', data);
    return response.data;
  },

  delete: async (id: number) => {
    const response = await axios.delete(`/api/v1/time-tracking/${id}`);
    return response.data;
  },

  getSummary: async (params?: { user_id?: number; date_from?: string; date_to?: string }) => {
    const response = await axios.get('/api/v1/time-tracking/summary', { params });
    return response.data;
  },
};
```

#### **Implementation Steps:**

**Step 1: Install Dependencies** (15 min)
```bash
npm install react-timer-hook recharts date-fns
npm install --save-dev @types/recharts
```

**Step 2: API Client** (45 min)
1. Create `api/time-tracking.ts`
2. Define all endpoints
3. Test with backend

**Step 3: Active Timer Widget** (180 min)
1. Create `ActiveTimerWidget.tsx`
2. Integrate react-timer-hook
3. Implement localStorage persistence
4. Add pause/resume/stop functionality
5. Style prominently

**Step 4: Time Entry Form** (150 min)
1. Create `TimeEntryFormModal.tsx`
2. Build form with all fields
3. Implement auto-calculate hours from times
4. Add order search dropdown
5. Add validation

**Step 5: Summary Cards** (120 min)
1. Create `TimeSummaryCards.tsx`
2. Implement calculation logic (week, month, all time)
3. Add % change indicators
4. Style with colors (green/red)

**Step 6: Reports with Charts** (240 min)
1. Create `TimeReportsSection.tsx`
2. Implement weekly bar chart (Recharts)
3. Implement monthly line chart
4. Implement pie charts (by project, by task)
5. Make responsive

**Step 7: Main Page** (240 min)
1. Create `TimeTrackingPage.tsx`
2. Integrate timer widget
3. Add summary cards
4. Build time entry table
5. Implement filters (date range, user, order)
6. Add grouping functionality
7. Wire up modal and timer

**Step 8: Styling** (120 min)
1. Create `time-tracking.css`
2. Style timer widget (large, prominent)
3. Style summary cards
4. Style charts
5. Add responsive breakpoints

**Step 9: Testing** (90 min)
1. Test timer start/pause/resume/stop
2. Test timer persistence (refresh page)
3. Test manual entry creation
4. Test filters and grouping
5. Verify chart data accuracy
6. Test responsive design

**Total Day 5-6: 16-20 hours** ✅

---

## Phase 3: TimeTrackingService Tests (Day 7)

### **Test Plan** (8-10 hours)

#### **File: tests/unit/test_time_tracking_service.py** (20-25 tests)

**Test Categories:**

1. **Time Entry Creation** (5 tests)
   - Create with all fields
   - Create with minimal fields
   - Auto-calculate hours from start/end times
   - Validate order_id exists
   - Validate positive hours
   - Reject future dates

2. **Time Entry Retrieval** (4 tests)
   - Get by ID
   - List all with pagination
   - Filter by user
   - Filter by order
   - Filter by date range

3. **Time Entry Updates** (3 tests)
   - Update hours
   - Update task type
   - Update notes

4. **Time Entry Deletion** (2 tests)
   - Delete success
   - Not found handling

5. **Time Calculations** (3 tests)
   - Calculate total hours for user
   - Calculate total hours for order
   - Calculate total hours for date range

6. **Time Reports** (3 tests)
   - Weekly summary
   - Monthly summary
   - Billable vs non-billable hours

**Example Test:**
```python
async def test_create_time_entry_success(self, db_session, sample_order):
    """Test creating a time entry with all fields"""
    entry_data = TimeEntryCreate(
        order_id=sample_order.id,
        task_type="Manufacturing",
        date=date.today(),
        hours=3.5,
        notes="Worked on ring setting"
    )

    entry = await TimeTrackingService.create_entry(db_session, entry_data)

    assert entry.id is not None
    assert entry.order_id == sample_order.id
    assert entry.task_type == "Manufacturing"
    assert float(entry.hours) == 3.5

async def test_calculate_hours_from_start_end_times(self, db_session):
    """Test auto-calculating hours from start/end times"""
    entry_data = TimeEntryCreate(
        order_id=1,
        task_type="Design",
        date=date.today(),
        start_time=time(9, 0),    # 9:00 AM
        end_time=time(12, 30),    # 12:30 PM
        # hours will be auto-calculated: 3.5
    )

    entry = await TimeTrackingService.create_entry(db_session, entry_data)

    assert float(entry.hours) == 3.5
```

#### **Implementation:** (8-10 hours)
- Read TimeTrackingService implementation
- Write 20-25 unit tests following MaterialService pattern
- Write 8-10 integration tests for API endpoints
- Run tests and verify coverage
- Document findings

---

## Phase 4: Dashboard Enhancement (Day 8)

### **Dashboard Design** (8-10 hours)

#### **Research-Based Design:**
Based on 2025 best practices:
- **5-10 KPIs max** ✅
- **F-Pattern layout** (top-left = most important) ✅
- **5-Second Rule** (understand in 5 seconds) ✅
- **Single screen** (no scrolling) ✅
- **Context for each KPI** (trends, comparisons) ✅

#### **Component Breakdown:**

##### **1. DashboardPage.tsx** (Enhanced - 600+ lines)

**Layout (F-Pattern):**
```
┌─────────────────────────────────────────────────────────┐
│ Dashboard                                                │
├─────────────────────────────────────────────────────────┤
│             KPI CARDS (F-Pattern: Top Priority)         │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│ │Aufträge  │ │Umsatz    │ │Aktive    │ │Deadlines │   │
│ │Monat     │ │Monat     │ │Aufträge  │ │7 Tage    │   │
│ │          │ │          │ │          │ │          │   │
│ │   42     │ │€45,230   │ │   12     │ │    5     │   │
│ │ +15% ↗   │ │ +8% ↗    │ │ Normal   │ │ ⚠️ 2 Red │   │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
│                                                          │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│ │Zeit      │ │Kunden    │ │Material  │ │Metall    │   │
│ │Woche     │ │Neu       │ │Niedrig   │ │Bestand   │   │
│ │          │ │          │ │          │ │          │   │
│ │ 40.5 Std │ │    3     │ │    8     │ │€125,000  │   │
│ │ +12% ↗   │ │ Normal   │ │ ⚠️ Alert │ │ Stable   │   │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│              REVENUE CHART (Left) | ALERTS (Right)      │
│ ┌────────────────────┐ ┌──────────────────────────┐    │
│ │ Revenue 6 Months   │ │ Low Stock Alerts         │    │
│ │ [Line Chart]       │ │ • Gold 18K: 45.5g        │    │
│ │                    │ │ • Silber: 120g           │    │
│ │                    │ │ • Ring Clasp: 5 Stück    │    │
│ └────────────────────┘ │                          │    │
│                        │ Upcoming Deadlines       │    │
│                        │ • Order #123: Tomorrow   │    │
│                        │ • Order #145: 2 days     │    │
│                        │ • Order #156: 5 days     │    │
│                        └──────────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│              RECENT ORDERS (Bottom)                      │
│ ┌───────────────────────────────────────────────────┐   │
│ │ #123 | Gold Ring | In Progress | €1,950 | 2 days  │   │
│ │ #145 | Repair   | New         | €450   | 5 days  │   │
│ │ #156 | Necklace | Completed   | €3,200 | Done    │   │
│ │ ... (5 most recent)           [Alle anzeigen →]  │   │
│ └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

##### **2. KPICard.tsx** (Reusable Component - 150+ lines)

**Props:**
```typescript
interface KPICardProps {
  title: string;
  value: number | string;
  icon: string;
  change?: {
    value: number;     // Percentage change
    direction: 'up' | 'down' | 'neutral';
    label: string;     // "vs. letzter Monat"
  };
  status?: 'good' | 'warning' | 'alert' | 'neutral';
  subtitle?: string;
  onClick?: () => void;
}
```

**Example:**
```typescript
<KPICard
  title="Umsatz Monat"
  value="€45,230"
  icon="💰"
  change={{
    value: 8,
    direction: 'up',
    label: 'vs. letzter Monat'
  }}
  status="good"
/>
```

**Styling:**
- Gradient background based on status
- Large value display (2.5rem)
- Small trend arrow (↗ ↘)
- Hover effect (lift on hover)
- Click to drill down

##### **3. RevenueChart.tsx** (Chart Component - 200+ lines)

**Using Recharts:**
```typescript
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

interface RevenueData {
  month: string;
  revenue: number;
}

export const RevenueChart: React.FC = () => {
  const [data, setData] = useState<RevenueData[]>([]);

  useEffect(() => {
    fetchRevenueData();
  }, []);

  const fetchRevenueData = async () => {
    // Get orders from last 6 months
    // Group by month
    // Sum revenue per month
    const revenueData = await dashboardApi.getRevenueByMonth(6);
    setData(revenueData);
  };

  return (
    <div className="revenue-chart">
      <h3>Umsatz (6 Monate)</h3>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="month" />
          <YAxis
            label={{ value: 'Umsatz (€)', angle: -90, position: 'insideLeft' }}
            tickFormatter={(value) => `€${(value / 1000).toFixed(0)}K`}
          />
          <Tooltip formatter={(value: number) => `€${value.toFixed(2)}`} />
          <Line
            type="monotone"
            dataKey="revenue"
            stroke="#667eea"
            strokeWidth={2}
            dot={{ fill: '#667eea', r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};
```

##### **4. StockAlertsWidget.tsx** (Alerts Component - 150+ lines)

**Display:**
- Low stock materials (< 10 units)
- Low metal inventory (< threshold)
- Grouped and color-coded

```typescript
interface StockAlert {
  type: 'material' | 'metal';
  name: string;
  current: number;
  threshold: number;
  unit: string;
  severity: 'warning' | 'critical';
}

export const StockAlertsWidget: React.FC = () => {
  const [alerts, setAlerts] = useState<StockAlert[]>([]);

  useEffect(() => {
    fetchAlerts();
  }, []);

  const fetchAlerts = async () => {
    // Get low stock materials
    const materials = await materialsApi.getLowStock(10);
    const metals = await metalInventoryApi.getSummary();

    // Combine and format
    const allAlerts = [
      ...materials.map(m => ({
        type: 'material',
        name: m.name,
        current: m.stock,
        threshold: 10,
        unit: m.unit,
        severity: m.stock < 5 ? 'critical' : 'warning'
      })),
      // ... metals
    ];

    setAlerts(allAlerts);
  };

  return (
    <div className="stock-alerts-widget">
      <h3>⚠️ Bestandswarnungen</h3>
      {alerts.length === 0 ? (
        <p className="no-alerts">✅ Alle Bestände normal</p>
      ) : (
        <ul className="alerts-list">
          {alerts.map((alert, i) => (
            <li key={i} className={`alert-item alert-${alert.severity}`}>
              <span className="alert-icon">
                {alert.severity === 'critical' ? '🔴' : '🟡'}
              </span>
              <span className="alert-name">{alert.name}</span>
              <span className="alert-value">
                {alert.current} {alert.unit}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
```

##### **5. DeadlinesWidget.tsx** (Upcoming Deadlines - 150+ lines)

**Display:**
- Orders with deadlines in next 7 days
- Color-coded by urgency (red < 2 days, yellow < 5 days)

```typescript
interface UpcomingDeadline {
  orderId: number;
  title: string;
  deadline: Date;
  daysRemaining: number;
  status: OrderStatus;
}

export const DeadlinesWidget: React.FC = () => {
  const [deadlines, setDeadlines] = useState<UpcomingDeadline[]>([]);

  useEffect(() => {
    fetchDeadlines();
  }, []);

  const fetchDeadlines = async () => {
    const now = new Date();
    const sevenDaysFromNow = addDays(now, 7);

    const orders = await ordersApi.getAll();
    const upcoming = orders
      .filter(o => o.deadline && new Date(o.deadline) <= sevenDaysFromNow)
      .map(o => ({
        orderId: o.id,
        title: o.title,
        deadline: new Date(o.deadline!),
        daysRemaining: differenceInDays(new Date(o.deadline!), now),
        status: o.status,
      }))
      .sort((a, b) => a.daysRemaining - b.daysRemaining);

    setDeadlines(upcoming);
  };

  return (
    <div className="deadlines-widget">
      <h3>📅 Anstehende Deadlines</h3>
      {deadlines.length === 0 ? (
        <p className="no-deadlines">✅ Keine Deadlines in 7 Tagen</p>
      ) : (
        <ul className="deadlines-list">
          {deadlines.map(d => (
            <li key={d.orderId} className={`deadline-item ${
              d.daysRemaining < 2 ? 'critical' :
              d.daysRemaining < 5 ? 'warning' : 'normal'
            }`}>
              <span className="deadline-icon">
                {d.daysRemaining < 2 ? '🔴' :
                 d.daysRemaining < 5 ? '🟡' : '🟢'}
              </span>
              <a href={`/orders/${d.orderId}`}>
                Auftrag #{d.orderId}: {d.title}
              </a>
              <span className="deadline-time">
                {d.daysRemaining === 0 ? 'Heute!' :
                 d.daysRemaining === 1 ? 'Morgen' :
                 `${d.daysRemaining} Tage`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
```

##### **6. RecentOrdersWidget.tsx** (Recent Orders - 150+ lines)

**Display:**
- Last 5 orders
- Status, price, deadline
- Link to order detail

##### **7. dashboard.css** (Enhanced Styling - 400+ lines)

**Key Styles:**
- `.kpi-cards-grid` - 4-column grid (responsive to 2, then 1)
- `.kpi-card` - Card with gradient, shadow, hover effect
- `.kpi-card-good` - Green gradient
- `.kpi-card-warning` - Yellow gradient
- `.kpi-card-alert` - Red gradient
- `.dashboard-sections` - Two-column layout (chart + alerts)
- `.alerts-list` - Styled list with color indicators
- Responsive breakpoints

#### **Implementation Steps:**

**Step 1: Install Recharts** (if not already)
```bash
npm install recharts date-fns
```

**Step 2: KPI Card Component** (90 min)
1. Create `KPICard.tsx`
2. Add props interface
3. Implement trend arrows
4. Style with gradients
5. Add hover effects

**Step 3: Fetch Dashboard Data** (60 min)
1. Create `api/dashboard.ts`
2. Add endpoints for:
   - getKPIStats()
   - getRevenueByMonth()
   - getLowStockAlerts()
   - getUpcomingDeadlines()
   - getRecentOrders()

**Step 4: Revenue Chart** (90 min)
1. Create `RevenueChart.tsx`
2. Integrate Recharts LineChart
3. Format data for last 6 months
4. Add tooltips and axis labels

**Step 5: Alerts Widget** (90 min)
1. Create `StockAlertsWidget.tsx`
2. Fetch low stock items
3. Color-code by severity
4. Make clickable to relevant pages

**Step 6: Deadlines Widget** (90 min)
1. Create `DeadlinesWidget.tsx`
2. Calculate days remaining
3. Color-code by urgency
4. Link to orders

**Step 7: Recent Orders Widget** (60 min)
1. Create `RecentOrdersWidget.tsx`
2. Display last 5 orders
3. Show status badges
4. Add "View All" link

**Step 8: Main Dashboard** (150 min)
1. Update `DashboardPage.tsx`
2. Integrate all KPI cards (8 cards)
3. Add chart section
4. Add alerts/deadlines section
5. Add recent orders section
6. Implement F-Pattern layout

**Step 9: Styling** (120 min)
1. Update `dashboard.css`
2. Style KPI cards with gradients
3. Style chart containers
4. Style alerts and deadlines
5. Add responsive breakpoints
6. Polish animations

**Step 10: Testing** (60 min)
1. Test all KPI calculations
2. Verify chart displays correctly
3. Test alerts and deadlines
4. Verify responsive design
5. Check performance

**Total Day 8: 8-10 hours** ✅

---

## Success Criteria

### **Phase 2 Complete:**
- [ ] MetalInventoryPage displays purchases with search/filter
- [ ] Can add new metal purchases with auto-generated batch numbers
- [ ] Summary cards show aggregated metal inventory
- [ ] TimeTrackingPage displays time entries with filters
- [ ] Active timer widget works (start/pause/resume/stop)
- [ ] Timer persists across page refreshes
- [ ] Can create manual time entries
- [ ] Time reports display with charts (Recharts)
- [ ] All components responsive

### **Phase 3 Complete:**
- [ ] TimeTrackingService has 20+ unit tests
- [ ] All tests pass
- [ ] Test coverage 75%+

### **Phase 4 Complete:**
- [ ] Dashboard displays 8 KPI cards
- [ ] Revenue chart shows 6-month trend
- [ ] Stock alerts widget displays low items
- [ ] Deadlines widget shows upcoming deadlines
- [ ] Recent orders widget displays last 5 orders
- [ ] F-Pattern layout implemented
- [ ] All KPIs have context (trends, comparisons)
- [ ] Dashboard loads in < 2 seconds

---

## Dependencies to Install

```bash
# For Time Tracking
npm install react-timer-hook

# For Charts
npm install recharts

# For Date Handling
npm install date-fns

# TypeScript Definitions
npm install --save-dev @types/recharts
```

---

## Timeline Summary

| Day | Phase | Focus | Est. Hours |
|-----|-------|-------|------------|
| 4 | Phase 2 | MetalInventoryPage | 10-12h |
| 5-6 | Phase 2 | TimeTrackingPage | 16-20h |
| 7 | Phase 3 | TimeTrackingService Tests | 8-10h |
| 8 | Phase 4 | Dashboard Enhancement | 8-10h |
| **Total** | | | **42-52 hours (5-7 days)** |

---

## Risk Assessment & Mitigation

### **Potential Risks:**

1. **react-timer-hook Learning Curve**
   - **Mitigation:** Follow official docs, use simple examples first
   - **Backup:** Implement custom timer with setInterval if needed

2. **Recharts Performance with Large Datasets**
   - **Mitigation:** Limit data points (6 months max), implement data aggregation
   - **Backup:** Use simpler chart library or custom SVG if performance issues

3. **Timer State Persistence**
   - **Mitigation:** Use localStorage with fallback to sessionStorage
   - **Backup:** Warn user to keep tab open while timer running

4. **Dashboard Data Load Time**
   - **Mitigation:** Fetch KPIs in parallel, implement loading skeletons
   - **Backup:** Cache data for 5 minutes, lazy load charts

### **Quality Assurance:**

- [ ] All components have TypeScript types
- [ ] All forms have validation
- [ ] All API calls have error handling
- [ ] All pages are responsive (mobile, tablet, desktop)
- [ ] All text is in German
- [ ] All styling is consistent with existing pages
- [ ] All charts are accessible (proper labels, ARIA)

---

## Next Immediate Action

**START: Day 4 - MetalInventoryPage**

**First Step:** Install dependencies and create API client

```bash
cd frontend
npm install recharts react-timer-hook date-fns
npm install --save-dev @types/recharts
```

Then create:
1. `frontend/src/api/metal-inventory.ts` (API client)
2. `frontend/src/components/metal/MetalSummaryCards.tsx` (Summary cards)
3. `frontend/src/components/metal/MetalPurchaseFormModal.tsx` (Form)
4. `frontend/src/pages/MetalInventoryPage.tsx` (Main page)
5. `frontend/src/styles/metal-inventory.css` (Styling)

**Ready to implement!** 🚀
