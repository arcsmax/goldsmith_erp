# Dashboard Enhancement Plan (Day 8)

## Overview
Enhance DashboardPage with KPI cards, charts, alerts, and deadline widgets following 2025 best practices (F-Pattern layout, 5-Second Rule, responsive design).

**Time Estimate:** 6-8 hours

---

## Research Findings (2025 Best Practices)

### Layout & Visual Hierarchy
- **F-Pattern**: Users read in an F-shaped pattern (top-left is most important)
- **5-Second Rule**: Users should understand key metrics within 5 seconds
- **5-10 KPIs max**: Avoid overwhelming users with too many metrics
- **Whitespace**: Generous spacing reduces cognitive load

### KPI Card Design
- **Primary metric**: Large, bold number
- **Context**: Small trend line or comparison figure
- **Visual hierarchy**: Largest font for value, smaller for label
- **Associative colors**: Green for positive, red for negative

### 2025 Trends
- **AI-powered insights**: (Future enhancement)
- **Responsive design**: Mandatory for all screen sizes
- **Actionable metrics**: Focus on insights, not vanity metrics

---

## Dashboard Layout (F-Pattern)

```
┌─────────────────────────────────────────────────────────────┐
│  GOLDSMITH ERP DASHBOARD               [Last Updated: Now]  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐          │
│  │  📊  │  │  💰  │  │  📦  │  │  🔨  │  │  ⏱️  │          │
│  │ KPI1 │  │ KPI2 │  │ KPI3 │  │ KPI4 │  │ KPI5 │          │
│  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘          │
│                                                               │
├───────────────────────────┬─────────────────────────────────┤
│                           │                                 │
│  📈 REVENUE CHART        │  ⚠️  ALERTS & NOTIFICATIONS     │
│  (Last 30 Days)          │                                 │
│                           │  • Low stock materials          │
│  [LineChart]             │  • Pending quality checks       │
│                           │  • Delayed orders               │
│                           │                                 │
├───────────────────────────┼─────────────────────────────────┤
│                           │                                 │
│  📅 UPCOMING DEADLINES   │  📋 RECENT ORDERS               │
│                           │                                 │
│  • Wedding Ring (2 days) │  • Order #123 - In Progress     │
│  • Bracelet (5 days)     │  • Order #122 - Completed       │
│  • Necklace (7 days)     │  • Order #121 - New             │
│                           │                                 │
└───────────────────────────┴─────────────────────────────────┘
```

---

## Components to Build

### 1. KPI Cards (5 cards)

**KPICard.tsx** (150 lines)
- Reusable component for displaying metrics
- Props: title, value, icon, comparison, trend
- Color-coded based on trend (positive/negative)
- Responsive sizing

**KPI Metrics:**
1. **Active Orders** 📊
   - Count of orders with status in_progress
   - Comparison to last week
   - Click → Navigate to Orders page

2. **Total Revenue (Month)** 💰
   - Sum of completed order prices
   - Comparison to last month
   - Formatted as currency (EUR)

3. **Inventory Value** 📦
   - Total value of metal purchases (remaining)
   - Comparison to last month
   - Color-coded (low = red warning)

4. **Orders in Production** 🔨
   - Count of in_progress orders
   - Average completion time
   - Click → Filtered orders view

5. **Time Tracked (Week)** ⏱️
   - Total hours tracked this week
   - Comparison to last week
   - Click → Time Tracking page

### 2. Revenue Chart

**RevenueChart.tsx** (200 lines)
- LineChart showing revenue over last 30 days
- Uses Recharts library
- Daily revenue aggregation
- Tooltip with detailed breakdown
- Responsive container

**Data Source:**
- Orders with status = 'completed'
- Group by completion date
- Sum prices per day

### 3. Alerts Widget

**AlertsWidget.tsx** (180 lines)
- List of important notifications
- Color-coded by severity (warning, info, error)
- Dismissible alerts (localStorage)
- Click to navigate to relevant page

**Alert Types:**
1. **Low Stock Materials** ⚠️
   - Materials with stock < 10 units
   - Shows count and top 3 items

2. **Low Metal Inventory** 🥇
   - Metal purchases < 50g remaining
   - Shows metal type and remaining weight

3. **Overdue Orders** ⏰
   - Orders past deadline
   - Shows count and oldest order

4. **Pending Quality Checks** ✅
   - Time entries with rework_required = true
   - Shows count and affected orders

### 4. Deadlines Widget

**DeadlinesWidget.tsx** (150 lines)
- Upcoming order deadlines (next 14 days)
- Sorted by urgency (closest first)
- Color-coded (red < 2 days, yellow < 7 days, green > 7 days)
- Shows customer name and order title
- Click → Order detail page

**Features:**
- Filters active orders only (not completed/delivered)
- Groups by urgency
- Shows days remaining
- Quick action button to view order

### 5. Recent Orders Widget

**RecentOrdersWidget.tsx** (120 lines)
- Last 5 orders (any status)
- Shows order ID, title, status, customer
- Status badges (color-coded)
- Click → Order detail page

---

## Implementation Steps

### Step 1: Create KPICard Component (1 hour)

**File:** `frontend/src/components/dashboard/KPICard.tsx`

```typescript
interface KPICardProps {
  title: string;
  value: string | number;
  icon: string;
  comparison?: number; // % change
  trend?: 'up' | 'down' | 'neutral';
  onClick?: () => void;
  loading?: boolean;
}

export const KPICard: React.FC<KPICardProps> = ({ ... }) => {
  // Implementation
};
```

**Styling:**
- Gradient background
- Large value display (3rem font)
- Comparison indicator with arrow
- Hover effect (lift + shadow)
- Skeleton loader for loading state

### Step 2: Build All KPI Cards (2 hours)

**File:** `frontend/src/components/dashboard/DashboardKPIs.tsx`

Fetch data for all 5 KPIs:
- Active orders count
- Monthly revenue
- Inventory value
- In-production orders
- Weekly tracked time

Use parallel API calls for performance.

### Step 3: Create RevenueChart (1.5 hours)

**File:** `frontend/src/components/dashboard/RevenueChart.tsx`

- Fetch completed orders from last 30 days
- Group by completion date
- Aggregate prices
- Render LineChart with Recharts

### Step 4: Build AlertsWidget (1.5 hours)

**File:** `frontend/src/components/dashboard/AlertsWidget.tsx`

- Fetch low stock materials
- Fetch low metal inventory
- Fetch overdue orders
- Fetch pending quality checks
- Render alert list with severity colors

### Step 5: Build DeadlinesWidget (1 hour)

**File:** `frontend/src/components/dashboard/DeadlinesWidget.tsx`

- Fetch orders with deadlines in next 14 days
- Sort by deadline (closest first)
- Calculate days remaining
- Color-code by urgency

### Step 6: Build RecentOrdersWidget (45 min)

**File:** `frontend/src/components/dashboard/RecentOrdersWidget.tsx`

- Fetch last 5 orders
- Display with status badges
- Add click handlers

### Step 7: Update DashboardPage (1 hour)

**File:** `frontend/src/pages/DashboardPage.tsx`

- Import all components
- Arrange in F-Pattern layout
- Add responsive CSS Grid
- Add loading states
- Add error handling

### Step 8: Create Dashboard Styling (45 min)

**File:** `frontend/src/styles/dashboard.css`

- KPI card styles
- Grid layouts (responsive)
- Chart containers
- Widget styles
- Animations (fade-in, slide-up)

---

## API Endpoints Needed

Most endpoints already exist, but we'll need:

1. **Dashboard Analytics Endpoint** (optional optimization)
   - GET `/api/analytics/dashboard`
   - Returns all KPIs in one call
   - Reduces round trips

2. **Use Existing Endpoints:**
   - GET `/api/orders/` (for counts, revenue)
   - GET `/api/metal-inventory/` (for inventory value)
   - GET `/api/time-entries/analytics/summary` (for time stats)
   - GET `/api/materials/low-stock/alert` (for alerts)

---

## Responsive Design Breakpoints

```css
/* Desktop: 5 KPI cards in a row */
@media (min-width: 1200px) {
  .kpi-grid {
    grid-template-columns: repeat(5, 1fr);
  }
}

/* Tablet: 3 cards per row */
@media (max-width: 1199px) and (min-width: 768px) {
  .kpi-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Mobile: 1 card per row */
@media (max-width: 767px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }

  /* Stack charts and widgets vertically */
  .dashboard-layout {
    grid-template-columns: 1fr;
  }
}
```

---

## Performance Optimization

### Parallel Data Fetching
```typescript
useEffect(() => {
  const fetchAllData = async () => {
    try {
      const [orders, revenue, inventory, time] = await Promise.all([
        ordersApi.getAll(),
        analyticsApi.getRevenue(),
        metalInventoryApi.getTotalValue(),
        timeTrackingApi.getSummary()
      ]);
      // Process data
    } catch (error) {
      // Handle error
    }
  };

  fetchAllData();
}, []);
```

### Caching
- Use React Query (optional future enhancement)
- Refresh interval: 60 seconds
- Manual refresh button

### Loading States
- Skeleton loaders for KPI cards
- Spinner for charts
- Progressive loading (show KPIs first, then charts)

---

## Color Scheme

```css
:root {
  --kpi-positive: #27ae60;
  --kpi-negative: #e74c3c;
  --kpi-neutral: #95a5a6;

  --alert-error: #e74c3c;
  --alert-warning: #f39c12;
  --alert-info: #3498db;
  --alert-success: #27ae60;

  --deadline-urgent: #e74c3c;    /* < 2 days */
  --deadline-soon: #f39c12;      /* 2-7 days */
  --deadline-ok: #27ae60;        /* > 7 days */
}
```

---

## Success Criteria

✅ **5-Second Rule**: Users understand key metrics within 5 seconds
✅ **F-Pattern Layout**: Most important KPIs in top-left
✅ **5 KPI Cards**: Active orders, revenue, inventory, production, time
✅ **Revenue Chart**: Visual trend over 30 days
✅ **Alerts Widget**: 4 types of notifications
✅ **Deadlines Widget**: Next 14 days, color-coded
✅ **Recent Orders**: Last 5 orders
✅ **Responsive**: Works on mobile, tablet, desktop
✅ **Fast Loading**: Parallel data fetching, < 2s total
✅ **Error Handling**: Graceful degradation if API fails

---

## Implementation Order

**Priority 1: Core KPIs** (3 hours)
1. KPICard component
2. DashboardKPIs with data fetching
3. Basic styling

**Priority 2: Visualizations** (2 hours)
4. RevenueChart with Recharts
5. Chart styling

**Priority 3: Widgets** (2.5 hours)
6. AlertsWidget
7. DeadlinesWidget
8. RecentOrdersWidget

**Priority 4: Integration** (1 hour)
9. Update DashboardPage
10. Responsive CSS Grid
11. Testing & refinement

**Total Time:** 6-8 hours

---

## Future Enhancements (Out of Scope)

- **Real-time Updates**: WebSocket for live data
- **Customizable Dashboard**: User can choose which KPIs to show
- **Export to PDF**: Generate dashboard report
- **Time Range Selector**: View data for custom date ranges
- **Comparison Mode**: Compare current period to previous period
- **AI Insights**: Automatic insights and recommendations
- **Drill-down**: Click KPI to see detailed breakdown

---

## Notes

- Use German labels throughout (Aktive Aufträge, Umsatz, etc.)
- Follow existing code patterns from TimeTrackingPage
- Use Recharts for all charts (already installed)
- Ensure all components are type-safe (TypeScript)
- Add proper error boundaries
- Use skeleton loaders for better UX
- Keep dashboard simple and focused (avoid feature creep)
