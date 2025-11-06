# Goldsmith ERP - Implementation Roadmap

## Document Overview

This roadmap defines the step-by-step implementation plan for Goldsmith ERP, transforming it from the current basic system into a fully-featured, template-driven, cross-platform ERP solution for goldsmiths.

---

## Current State (v0.1.0)

### ✅ What Exists
- Basic FastAPI backend with async support
- PostgreSQL database with SQLAlchemy ORM
- Redis integration for Pub/Sub
- Minimal React frontend (OrderList component)
- Docker Compose setup
- JWT authentication
- Basic Order CRUD API
- WebSocket endpoint for real-time updates

### ❌ What's Missing
- Template engine
- Tag system (NFC/QR)
- Dynamic form rendering
- Workflow engine
- Mobile apps
- Material management (backend exists, no UI)
- Customer management
- Reporting
- Production tracking
- Time tracking
- NFC integration
- OCR features

---

## Development Strategy

### Guiding Principles

1. **Incremental Value**: Each phase delivers usable functionality
2. **Foundation First**: Core systems before advanced features
3. **Backend Before Frontend**: API-first development
4. **Web Before Mobile**: Web app validates concept, mobile adds hardware access
5. **MVP Focus**: Get to usable system quickly, iterate based on feedback

### Target Timeline

- **Phase 1 (MVP)**: 6-8 weeks → Usable system for daily operations
- **Phase 2**: +4 weeks → Full CRM and customer workflows
- **Phase 3**: +6 weeks → Template engine and dynamic workflows
- **Phase 4**: +6 weeks → Mobile apps with NFC
- **Phase 5**: +4 weeks → Advanced features (OCR, ML)

**Total to v2.0**: ~26-28 weeks (~6-7 months)

---

## Phase 1: Foundation & MVP (6-8 Weeks)

**Goal**: Schnell einsetzbares System für Auftrags- und Materialverwaltung

### 1.1 Backend Cleanup & Enhancement (Week 1)

#### Tasks
- [ ] Remove duplicate models from `main.py`
- [ ] Clean up imports and structure
- [ ] Create initial Alembic migration
- [ ] Add seed data script for development
- [ ] Implement Repository Pattern for Orders and Materials
- [ ] Add proper error handling middleware
- [ ] Setup structured logging (JSON format)

#### Deliverables
```python
# Repository pattern example
class OrderRepository:
    async def get_by_id(self, order_id: int) -> Order | None
    async def get_all(self, filters: dict, pagination: Pagination) -> list[Order]
    async def create(self, order: OrderCreate) -> Order
    async def update(self, order_id: int, data: OrderUpdate) -> Order
    async def delete(self, order_id: int) -> bool
```

**Time Estimate**: 3-4 days

---

### 1.2 Material Management API (Week 1)

#### Tasks
- [ ] Extend Material model with proper fields (type, metadata JSONB)
- [ ] Create MaterialRepository
- [ ] Create MaterialService with business logic
- [ ] Create Material router with CRUD endpoints:
  - `GET /api/v1/materials` (list with filters)
  - `POST /api/v1/materials` (create)
  - `GET /api/v1/materials/{id}` (get one)
  - `PUT /api/v1/materials/{id}` (update)
  - `DELETE /api/v1/materials/{id}` (delete)
  - `PATCH /api/v1/materials/{id}/stock` (adjust stock)
- [ ] Add stock validation (prevent negative stock)
- [ ] Add stock-level warnings (low stock alerts)

#### Deliverables
```python
# Material model with JSONB metadata
class Material(Base):
    id: int
    name: str
    material_type: str  # gold, silver, stone, tool
    unit_price: Decimal
    stock: Decimal
    unit: str
    metadata: dict  # For type-specific fields (purity, size, color, etc.)
```

**Time Estimate**: 2-3 days

---

### 1.3 Customer Management (Week 2)

#### Tasks
- [ ] Create Customer model
- [ ] Create CustomerRepository & Service
- [ ] Create Customer router (CRUD + search)
- [ ] Add relationship: Order → Customer (update Order model)
- [ ] Migration: Add customer_id to orders table
- [ ] Update Order API to include customer selection

#### Deliverables
```python
class Customer(Base):
    id: int
    customer_number: str  # Auto-generated: CU-2024-0001
    first_name: str
    last_name: str
    email: str
    phone: str
    address: dict  # JSONB
    notes: str
    tags: list[str]  # JSONB ["VIP", "Stammkunde"]
    created_at: datetime
```

**Time Estimate**: 3 days

---

### 1.4 Frontend Foundation (Week 2-3)

#### Tasks
- [ ] Setup state management (Zustand)
- [ ] Setup React Router
- [ ] Create API client with Axios
  - Auth interceptor
  - Error handling
  - Base URL configuration
- [ ] Create Layout components:
  - Header with user info
  - Sidebar navigation
  - MainLayout wrapper
- [ ] Implement Authentication flow:
  - Login page
  - Protected routes
  - Token refresh logic
  - Logout

#### Deliverables
```typescript
// Zustand store example
interface AuthStore {
  user: User | null;
  token: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshToken: () => Promise<void>;
}
```

**Time Estimate**: 4-5 days

---

### 1.5 Material Management UI (Week 3)

#### Tasks
- [ ] Create Material list page with:
  - Table view
  - Filters (type, low stock)
  - Search
  - Pagination
- [ ] Create Material form (Create/Edit):
  - Dynamic fields based on material_type
  - Stock input with validation
  - Image upload
- [ ] Create Material detail page
- [ ] Add stock adjustment modal
- [ ] Integrate with API

#### Deliverables
- Full Material CRUD UI
- Stock warnings (visual indicators for low stock)
- Material selection component (for use in Orders)

**Time Estimate**: 4-5 days

---

### 1.6 Customer Management UI (Week 4)

#### Tasks
- [ ] Create Customer list page
- [ ] Create Customer form (Create/Edit)
- [ ] Create Customer detail page with:
  - Customer info
  - Order history
  - Total revenue
- [ ] Customer search/autocomplete component
- [ ] Tag management UI

#### Deliverables
- Full Customer CRUD UI
- Customer selection component (autocomplete)
- Customer stats visualization

**Time Estimate**: 3-4 days

---

### 1.7 Enhanced Order Management (Week 4-5)

#### Tasks
- [ ] Update Order model:
  - Add customer_id FK
  - Add delivery_date
  - Add notes field
- [ ] Update Order form:
  - Customer selection (autocomplete)
  - Material selection (multi-select)
  - Service selection (checkboxes)
  - Price calculation
- [ ] Create Order detail page:
  - Customer info
  - Material list
  - Service list
  - Status history
  - Actions (change status)
- [ ] Implement Order-Material association:
  - Junction table
  - Stock reservation on order creation
  - Stock release on order cancellation

#### Deliverables
```typescript
interface OrderFormData {
  customer_id: number;
  title: string;
  description: string;
  materials: { id: number; quantity: number }[];
  services: string[];
  delivery_date: string;
  notes: string;
}
```

**Time Estimate**: 5-6 days

---

### 1.8 Basic Dashboard (Week 5)

#### Tasks
- [ ] Create Dashboard page with KPIs:
  - Total orders by status
  - Low stock materials
  - Revenue this month
  - Recent orders
- [ ] Add charts (Recharts):
  - Orders over time
  - Revenue over time
  - Material stock levels
- [ ] Real-time updates via WebSocket

#### Deliverables
- Interactive dashboard
- Key business metrics at-a-glance
- Real-time order status updates

**Time Estimate**: 3-4 days

---

### 1.9 WebSocket Enhancement (Week 6)

#### Tasks
- [ ] Create WebSocket service in backend:
  - Order status changes
  - New orders
  - Stock updates
  - System notifications
- [ ] Create useWebSocket hook in frontend:
  - Auto-reconnect
  - Event handling
  - State sync
- [ ] Integrate real-time updates in UI:
  - Dashboard
  - Order list
  - Material list

#### Deliverables
```typescript
// WebSocket hook
const useWebSocket = (channel: string) => {
  const [messages, setMessages] = useState([]);
  const [connected, setConnected] = useState(false);
  // ... connection logic with auto-reconnect
  return { messages, connected, send };
};
```

**Time Estimate**: 2-3 days

---

### 1.10 Testing & Polish (Week 6-7)

#### Tasks
- [ ] Write backend unit tests:
  - Repository tests
  - Service tests
  - API endpoint tests
- [ ] Write frontend tests:
  - Component tests (React Testing Library)
  - Integration tests
- [ ] E2E tests (Playwright):
  - User login
  - Create order
  - Create customer
  - Material management
- [ ] Performance optimization:
  - Database query optimization
  - Frontend bundle size
  - Image optimization
- [ ] Security audit:
  - Run Bandit (Python)
  - Check dependencies for vulnerabilities
  - CORS configuration review
- [ ] Documentation:
  - API documentation (OpenAPI)
  - User guide (basic)
  - Deployment guide

**Time Estimate**: 5-7 days

---

### 1.11 Deployment (Week 7-8)

#### Tasks
- [ ] Setup production environment:
  - Database (managed PostgreSQL)
  - Redis (managed)
  - S3 bucket
- [ ] Configure CI/CD:
  - Automated tests
  - Docker image build
  - Deployment pipeline
- [ ] Setup monitoring:
  - Application logs
  - Error tracking (Sentry)
  - Uptime monitoring
- [ ] Production deployment:
  - Deploy backend
  - Deploy frontend
  - Run migrations
  - Seed initial data
- [ ] User training:
  - Demo session
  - Documentation handoff

**Time Estimate**: 5-7 days

---

### Phase 1 Deliverables

✅ **Functional ERP system with**:
- User authentication
- Customer management (full CRUD)
- Material management (full CRUD with stock tracking)
- Order management (with customer and material linking)
- Real-time updates (WebSocket)
- Dashboard with KPIs
- Production-ready deployment

**Total Time: 6-8 weeks**

---

## Phase 2: Tag System Foundation (4 Weeks)

**Goal**: Implement QR-Code scanning (web-compatible) and tag registration system

### 2.1 Tag Data Model (Week 9)

#### Tasks
- [ ] Create Tag model:
  ```python
  class Tag(Base):
      id: str  # TG-2024-A1B2C3
      type: str  # entity, material, tool
      created_at: datetime
      registered: bool
      entity_id: int | None
      entity_type: str | None  # jewelry_order, material, tool
      metadata: dict  # JSONB
  ```
- [ ] Create TagRepository & Service
- [ ] Create Tag API endpoints:
  - `GET /api/v1/tags/{tag_id}` (lookup)
  - `POST /api/v1/tags/{tag_id}/register` (register tag to entity)
  - `DELETE /api/v1/tags/{tag_id}/unregister` (release tag)
- [ ] Tag ID generation service
- [ ] Create tag templates (printable labels)

**Time Estimate**: 3-4 days

---

### 2.2 QR Code Integration (Week 9-10)

#### Tasks
- [ ] Add QR code library (html5-qrcode)
- [ ] Create QR scanner component:
  - Camera access
  - Scanner UI
  - Result handling
- [ ] Generate QR codes:
  - For tags
  - For entities
  - For labels
- [ ] Implement scan flow:
  - Scan → Lookup → View/Register
- [ ] Add QR codes to:
  - Order detail page
  - Material labels
  - Job labels

**Time Estimate**: 4-5 days

---

### 2.3 Tag Registration Flow (Week 10)

#### Tasks
- [ ] Create tag registration UI:
  - Scan tag
  - If unregistered: Select entity type
  - Show template selection
  - Create entity
  - Link tag
- [ ] Tag management page:
  - List all tags
  - Filter by status (registered/unregistered)
  - Bulk tag generation
- [ ] Print tag labels:
  - Generate PDF with QR code
  - Include human-readable ID
  - Multiple tags per sheet

**Time Estimate**: 4-5 days

---

### 2.4 Integration & Testing (Week 11-12)

#### Tasks
- [ ] Integrate tag scanning into workflows:
  - Order intake
  - Material receiving
  - Job tracking
- [ ] Create mobile-optimized scan page
- [ ] Test QR scanning on different devices
- [ ] Performance testing
- [ ] User acceptance testing

**Time Estimate**: 5-7 days

---

### Phase 2 Deliverables

✅ **Tag system with**:
- QR code generation and scanning
- Tag registration workflow
- Entity linking
- Printable labels
- Mobile-friendly scanning interface

**Total Time: +4 weeks (Week 9-12)**

---

## Phase 3: Template Engine & Dynamic Workflows (6 Weeks)

**Goal**: Implement core template engine for dynamic form generation and workflows

### 3.1 Template Data Model (Week 13)

#### Tasks
- [ ] Create Template model (see ARCHITECTURE.md)
- [ ] Create Entity model (generic entity storage)
- [ ] Create EntityHistory model (audit log)
- [ ] Create TemplateRepository
- [ ] Migration: Create template tables

**Time Estimate**: 2-3 days

---

### 3.2 Template Engine Backend (Week 13-14)

#### Tasks
- [ ] Implement TemplateEngine class:
  - Load template
  - Validate data against template
  - Resolve field dependencies
  - Evaluate conditions
  - Calculate computed fields
- [ ] Implement FormulaEngine:
  - Parse formulas
  - Evaluate expressions
  - Support functions (SUM, IF, LOOKUP, etc.)
- [ ] Create Template API:
  - `GET /api/v1/templates` (list)
  - `GET /api/v1/templates/{id}` (get definition)
  - `POST /api/v1/templates` (create - admin)
  - `PUT /api/v1/templates/{id}` (update - admin)

**Time Estimate**: 6-8 days

---

### 3.3 Entity API (Week 14-15)

#### Tasks
- [ ] Create Entity endpoints:
  - `POST /api/v1/entities` (create with template)
  - `GET /api/v1/entities/{id}` (get with computed fields)
  - `PUT /api/v1/entities/{id}` (update with validation)
  - `DELETE /api/v1/entities/{id}`
  - `GET /api/v1/entities?template_id=X` (list by template)
- [ ] Implement data validation:
  - Required fields
  - Type validation
  - Conditional validation
  - Custom validation scripts
- [ ] Implement computed fields:
  - Calculate on read
  - Cache when appropriate

**Time Estimate**: 5-6 days

---

### 3.4 Workflow Engine (Week 15-16)

#### Tasks
- [ ] Implement WorkflowEngine class:
  - State machine
  - Transition validation
  - Permission checks
  - Conditional transitions
  - Action execution
- [ ] Create Workflow API:
  - `GET /api/v1/entities/{id}/workflow` (get current state + available transitions)
  - `POST /api/v1/entities/{id}/workflow/transition` (execute transition)
  - `GET /api/v1/entities/{id}/history` (state history)
- [ ] Implement workflow actions:
  - Send notification
  - Create task
  - Update stock
  - Trigger webhook

**Time Estimate**: 6-7 days

---

### 3.5 Dynamic Form Renderer Frontend (Week 16-17)

#### Tasks
- [ ] Create DynamicForm component:
  - Render fields from template definition
  - Handle field types:
    - Text, number, date, select, etc.
    - Relation (autocomplete)
    - File upload
  - Conditional field visibility
  - Real-time validation
- [ ] Create FieldRenderer for each field type
- [ ] Implement formula evaluation (client-side)
- [ ] Create FormBuilder (for admins to create templates)

**Time Estimate**: 7-8 days

---

### 3.6 Workflow UI (Week 17-18)

#### Tasks
- [ ] Create WorkflowViewer component:
  - Show current state
  - Show state history
  - Show available transitions (as buttons)
- [ ] Create StateTransitionModal:
  - Confirm transition
  - Optional fields (notes, etc.)
  - Permission display
- [ ] Integrate workflow into Entity detail page
- [ ] Add workflow visualization (state diagram)

**Time Estimate**: 4-5 days

---

### 3.7 Default Templates (Week 18)

#### Tasks
- [ ] Create template definitions (JSON):
  - Jewelry Repair (see ARCHITECTURE.md)
  - Material Intake
  - Custom Order
  - Tool Checkout
- [ ] Import templates via migration/seed script
- [ ] Test all templates end-to-end
- [ ] Refine based on testing

**Time Estimate**: 4-5 days

---

### Phase 3 Deliverables

✅ **Template-driven system with**:
- Template engine (backend)
- Dynamic form rendering (frontend)
- Workflow engine
- Multiple pre-built templates
- Admin interface for template management

**Total Time: +6 weeks (Week 13-18)**

---

## Phase 4: Mobile Apps & NFC Integration (6 Weeks)

**Goal**: Native mobile apps with full NFC support

### 4.1 Mobile App Foundation (Week 19-20)

#### Tasks
- [ ] Setup React Native project
- [ ] Setup navigation (React Navigation)
- [ ] Implement authentication flow (mobile)
- [ ] Create shared API client
- [ ] Implement token storage (secure storage)
- [ ] Create core screens:
  - Login
  - Home/Dashboard
  - Scan (placeholder)
- [ ] Style with mobile UI library (React Native Paper)

**Time Estimate**: 5-7 days

---

### 4.2 NFC Integration (Week 20-21)

#### Tasks
- [ ] Install react-native-nfc-manager
- [ ] Implement NFC reader service:
  - Check NFC availability
  - Enable NFC
  - Read NDEF tags
  - Write NDEF tags
- [ ] Create NFC scan screen:
  - "Hold phone near tag" UI
  - Success/error feedback
  - Vibration/sound feedback
- [ ] Implement tag write functionality:
  - Write tag ID to NFC chip
  - Validate write
- [ ] Test on Android device
- [ ] Test on iOS device (requires iPhone 7+)

**Time Estimate**: 5-6 days

---

### 4.3 Core Features Mobile (Week 21-22)

#### Tasks
- [ ] Implement Order management (mobile):
  - Order list
  - Order detail
  - Create order (simplified)
- [ ] Implement Material management (mobile):
  - Material list
  - Stock adjustment
- [ ] Implement Customer search
- [ ] Implement scan-to-view flow:
  - Scan NFC/QR
  - Lookup entity
  - Show entity detail

**Time Estimate**: 6-7 days

---

### 4.4 Offline Mode (Week 22-23)

#### Tasks
- [ ] Implement local database (WatermelonDB):
  - Sync schema
  - Offline-first architecture
- [ ] Implement sync service:
  - Download data when online
  - Queue changes when offline
  - Sync on reconnect
  - Conflict resolution
- [ ] Offline indicators in UI
- [ ] Test offline scenarios

**Time Estimate**: 6-7 days

---

### 4.5 Dynamic Forms Mobile (Week 23-24)

#### Tasks
- [ ] Port DynamicForm component to React Native
- [ ] Adapt field renderers for mobile:
  - Native pickers
  - Native date pickers
  - Camera integration (for image fields)
- [ ] Test template rendering on mobile
- [ ] Performance optimization (large forms)

**Time Estimate**: 5-6 days

---

### 4.6 Mobile Testing & Deployment (Week 24)

#### Tasks
- [ ] Comprehensive testing:
  - iOS devices
  - Android devices
  - Different screen sizes
- [ ] Performance profiling
- [ ] Setup app distribution:
  - TestFlight (iOS)
  - Internal testing (Android)
- [ ] Create app store assets:
  - Screenshots
  - Descriptions
  - Icons
- [ ] Beta testing with users
- [ ] Bug fixes based on feedback

**Time Estimate**: 5-7 days

---

### Phase 4 Deliverables

✅ **Mobile apps with**:
- Full NFC reading/writing (iOS + Android)
- QR code scanning
- Core ERP features
- Offline mode with sync
- Dynamic forms
- Beta release

**Total Time: +6 weeks (Week 19-24)**

---

## Phase 5: Advanced Features (4 Weeks)

**Goal**: OCR, ML features, advanced reporting

### 5.1 OCR Integration (Week 25-26)

#### Tasks
- [ ] Setup OCR service:
  - Tesseract installation
  - pytesseract wrapper
  - Image preprocessing
- [ ] Create OCR API endpoint:
  - Upload invoice image
  - Extract text
  - Parse structured data (amount, date, supplier)
  - Return JSON
- [ ] Create OCR UI:
  - Camera capture (mobile)
  - File upload (web)
  - Field mapping (extracted → form fields)
  - Manual correction
- [ ] Integrate into Material Intake workflow
- [ ] Train/tune for invoice types

**Time Estimate**: 7-10 days

---

### 5.2 Predictive Analytics (Week 26-27)

#### Tasks
- [ ] Collect historical data:
  - Order duration
  - Material usage
  - Features (complexity, material, services)
- [ ] Train lead time prediction model:
  - Feature engineering
  - Model selection (XGBoost, Linear Regression)
  - Training pipeline
  - Model evaluation
- [ ] Create ML API endpoint:
  - Input: Order features
  - Output: Estimated lead time
- [ ] Integrate into Order creation:
  - Show estimated completion date
  - Display confidence
- [ ] Background: Retrain model periodically

**Time Estimate**: 7-10 days

---

### 5.3 Advanced Reporting (Week 27-28)

#### Tasks
- [ ] Create Report API:
  - Inventory report (with valuation)
  - Sales report (revenue, margins)
  - Production report (lead times, bottlenecks)
  - Financial report (profit/loss)
- [ ] Create Report UI:
  - Report selector
  - Date range filters
  - Category filters
  - Export to PDF
  - Export to Excel
- [ ] Implement scheduled reports:
  - Weekly/monthly email reports
  - Configurable recipients
- [ ] Add advanced charts:
  - Trend analysis
  - Forecasting
  - Comparison (YoY, MoM)

**Time Estimate**: 6-8 days

---

### 5.4 Production Planning (Week 28)

#### Tasks
- [ ] Create Production Board (Kanban):
  - Columns by state
  - Drag-and-drop to change state
  - Assignee avatars
  - Due date indicators
- [ ] Create Capacity Planning:
  - Goldsmith availability
  - Workload distribution
  - Overload warnings
- [ ] Create Time Tracking:
  - Start/stop timer
  - Manual time entries
  - Time reports by user/order

**Time Estimate**: 5-7 days

---

### Phase 5 Deliverables

✅ **Advanced features**:
- OCR for invoice processing
- ML-based lead time prediction
- Comprehensive reporting
- Production planning tools
- Time tracking

**Total Time: +4 weeks (Week 25-28)**

---

## Phase 6: Polish & Optimization (Ongoing)

**Goal**: Production hardening, performance, security

### 6.1 Performance Optimization

#### Tasks
- [ ] Database optimization:
  - Index optimization
  - Query optimization
  - Materialized views for reports
- [ ] Backend optimization:
  - Caching (Redis)
  - Async optimization
  - Connection pooling
- [ ] Frontend optimization:
  - Code splitting
  - Lazy loading
  - Image optimization
  - Bundle size reduction
- [ ] Load testing:
  - Simulate 100+ concurrent users
  - Identify bottlenecks
  - Optimize

**Ongoing**

---

### 6.2 Security Hardening

#### Tasks
- [ ] Security audit:
  - Penetration testing
  - Dependency scanning
  - Code review
- [ ] Implement rate limiting
- [ ] Implement API key auth (for integrations)
- [ ] GDPR compliance:
  - Data export
  - Data deletion
  - Privacy policy
  - Cookie consent
- [ ] Audit logging:
  - All critical actions
  - User activity tracking
  - Admin actions

**Ongoing**

---

### 6.3 Testing & Quality

#### Tasks
- [ ] Increase test coverage:
  - Target: 80%+ backend
  - Target: 70%+ frontend
- [ ] E2E test suite:
  - Critical user journeys
  - Cross-browser testing
  - Mobile testing
- [ ] Performance regression tests
- [ ] Accessibility audit (WCAG 2.1)

**Ongoing**

---

### 6.4 Documentation

#### Tasks
- [ ] User documentation:
  - Getting started guide
  - Feature tutorials
  - Video walkthroughs
- [ ] Developer documentation:
  - API reference
  - Architecture guide
  - Contribution guide
- [ ] Admin documentation:
  - Template creation guide
  - System configuration
  - Backup/restore procedures

**Ongoing**

---

## Summary Timeline

| Phase | Duration | Cumulative | Key Deliverable |
|-------|----------|------------|-----------------|
| Phase 1: MVP | 6-8 weeks | Week 8 | Usable ERP system |
| Phase 2: Tags | 4 weeks | Week 12 | QR code scanning |
| Phase 3: Templates | 6 weeks | Week 18 | Dynamic workflows |
| Phase 4: Mobile | 6 weeks | Week 24 | NFC apps |
| Phase 5: Advanced | 4 weeks | Week 28 | OCR, ML, Reports |
| Phase 6: Polish | Ongoing | - | Production-ready |

**Total to v2.0**: ~28 weeks (~7 months)

---

## Resource Requirements

### Team Composition (Recommended)

- **1x Backend Developer** (Python, FastAPI, PostgreSQL)
- **1x Frontend Developer** (React, TypeScript, React Native)
- **1x DevOps Engineer** (part-time, Docker, CI/CD, monitoring)
- **1x QA Engineer** (part-time, testing, user acceptance)
- **1x Product Owner** (goldsmith domain expert)

### Infrastructure Costs (Estimated Monthly)

- **Database** (PostgreSQL): $50-100
- **Redis**: $20-40
- **Object Storage** (S3): $10-30
- **Compute** (Backend instances): $100-200
- **Frontend Hosting** (CDN): $10-20
- **Monitoring** (Sentry, etc.): $29-99
- **Total**: ~$220-500/month

---

## Risk Management

### High-Risk Items

1. **Template Engine Complexity**
   - Risk: Underestimating complexity
   - Mitigation: Prototype early, iterate, consider no-code platform (Directus, Strapi)

2. **NFC Hardware Compatibility**
   - Risk: Inconsistent NFC behavior across devices
   - Mitigation: Test on many devices, have QR fallback

3. **Mobile App Development**
   - Risk: React Native learning curve, platform-specific issues
   - Mitigation: Consider Flutter, use Expo for React Native, test continuously

4. **Performance with JSONB Queries**
   - Risk: Slow queries on entity.data field
   - Mitigation: Proper indexes, query optimization, denormalization if needed

5. **User Adoption**
   - Risk: Users resist new system
   - Mitigation: Extensive training, gradual rollout, gather feedback

---

## Success Criteria

### Phase 1 (MVP)
- [ ] All core features functional
- [ ] 5+ real orders processed through system
- [ ] User feedback collected
- [ ] System uptime > 99%

### Phase 2 (Tags)
- [ ] 100+ tags printed and registered
- [ ] Users can scan tags reliably
- [ ] Tag-to-entity linking works consistently

### Phase 3 (Templates)
- [ ] 3+ templates in production use
- [ ] Users can complete workflows without confusion
- [ ] Form validation prevents errors

### Phase 4 (Mobile)
- [ ] Mobile apps deployed to 10+ devices
- [ ] NFC scanning success rate > 95%
- [ ] Offline mode tested and working

### Phase 5 (Advanced)
- [ ] OCR accuracy > 90% for invoices
- [ ] Lead time predictions within 20% of actual
- [ ] Reports generated weekly

---

## Next Steps

1. **Review & Approve**: Team reviews this roadmap
2. **Prioritize**: Confirm phase priorities
3. **Resource Allocation**: Assign team members
4. **Sprint Planning**: Break Phase 1 into 2-week sprints
5. **Kickoff**: Start development!

---

**Document Version**: 1.0
**Last Updated**: 2024-01-15
**Status**: Ready for Review
