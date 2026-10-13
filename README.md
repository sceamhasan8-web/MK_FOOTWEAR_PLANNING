# Footwear Manufacturing Production Planning ERP

A complete, functional, production-ready **Footwear Manufacturing Production Planning ERP** engineered for footwear manufacturers to manage buyers, customer orders, multi-step production departments, operation-level sub-processes, daily manual production entries, component-wise parts tracking, automatic working-calendar scheduling, deadline revisions, and automated Excel XLSX / CSV reporting.

Supports centralized data sharing between office Windows desktop workstations, shop-floor Android devices, and factory management web portals through an authoritative central database.

---

## 1. System Architecture & Tech Stack

```text
       ┌──────────────────────────────┐
       │   Office Desktop Planners    │  (Kotlin Compose Multiplatform / JVM)
       └──────────────┬───────────────┘
                      │
       ┌──────────────┴───────────────┐
       │  Shop-Floor Android Devices  │  (Kotlin Jetpack Compose Android)
       └──────────────┬───────────────┘
                      │
       ┌──────────────┴───────────────┐
       │  Web Management Portal       │  (Responsive HTML5 / CSS / Vanilla JS)
       └──────────────┬───────────────┘
                      │  REST API / HTTPS / JWT RBAC
                      ▼
       ┌──────────────────────────────┐
       │      FastAPI Backend         │  (Python 3.12, SQLAlchemy 2.x, Pydantic v2)
       │  - Calculation Engine        │
       │  - Working Calendar Engine   │
       │  - OpenPyXL 7-Sheet Export   │
       └──────────────┬───────────────┘
                      │
                      ▼
       ┌──────────────────────────────┐
       │ Central Production Database  │  (PostgreSQL / SQLite, Alembic Migrations)
       └──────────────────────────────┘
```

### Technology Highlights
* **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 ORM, Alembic Migrations, Pydantic v2, OpenPyXL, Bcrypt, Pytest, PyJWT.
* **Database**: PostgreSQL for multi-client centralized production deployments; SQLite supported for local testing/development.
* **Desktop Frontend**: Kotlin 2.0, Compose Multiplatform for Desktop (Windows `.exe` and `.msi`).
* **Mobile Frontend**: Kotlin 2.0, Jetpack Compose for Android (Shop-floor barcode & entry APK).
* **Shared Presentation**: Kotlin Multiplatform shared module with Ktor HTTP client, shared models, and token management.
* **Integrated Web Portal**: Responsive factory management portal mounted directly on the FastAPI server for immediate cross-platform browser access.

---

## 2. Project Directory Structure

```text
d:\ErpPlanning\
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app initialization, middleware, routes
│   │   ├── config.py                  # Pydantic BaseSettings environment configuration
│   │   ├── database.py                # SQLAlchemy 2.x engine & sessionmaker
│   │   ├── models/                    # Normalized ORM entities
│   │   │   ├── user.py                # User & UserRole (admin, planning_manager, supervisor, viewer)
│   │   │   ├── buyer.py               # Buyer management & order relationships
│   │   │   ├── order.py               # Order, DeliveryDateRevision, OrderStatus, OrderPriority
│   │   │   ├── route.py               # Category, Section, ProcessTemplate, OrderRoute, OrderOperation, Component
│   │   │   ├── entry.py               # DailyProductionEntry, ProductionEntryCorrection (audit)
│   │   │   ├── calendar.py            # FactoryCalendar, CalendarException (holidays, closures)
│   │   │   └── audit.py               # AuditLog for full traceability
│   │   ├── schemas/                   # Pydantic validation and serialization models
│   │   │   ├── auth.py, buyer.py, order.py, route.py, entry.py, calendar.py, dashboard.py
│   │   ├── services/                  # Authoritative business logic & calculations
│   │   │   ├── calculation_engine.py  # Production balances, limiting components, schedules
│   │   │   ├── calendar_service.py    # Factory working days, cutoff hour, weekend evaluator
│   │   │   ├── order_service.py       # Order lifecycle, route building, date revisions
│   │   │   ├── production_service.py  # Single & bulk entries, duplicate protection, overrides
│   │   │   └── export_service.py      # OpenPyXL 7-sheet workbook & CSV generator
│   │   ├── api/                       # Documented REST API route handlers
│   │   │   ├── auth.py, buyers.py, orders.py, production.py, calendar.py, dashboard.py, exports.py, audit.py, departments.py
│   │   └── seed/
│   │       └── demo_data.py           # Demo seeding script (BATA, Apex, routes, entries)
│   ├── tests/                         # Automated test suite (Scenarios A through K)
│   │   ├── conftest.py                # In-memory SQLite fixture with isolated session
│   │   ├── test_buyers_orders.py      # Scenario A: Buyer and order creation
│   │   ├── test_optional_sections.py  # Scenario B: Optional production sections
│   │   ├── test_multiple_printing.py  # Scenario C: Three printing operations
│   │   ├── test_daily_targets.py      # Scenario D: Automatic daily target
│   │   ├── test_working_calendar.py   # Scenario E: Working calendar & holidays
│   │   ├── test_delivery_revision.py  # Scenario F: Delivery date revision
│   │   ├── test_production_reversal.py# Scenario G: Production correction & reversal
│   │   ├── test_component_tracking.py # Scenario H: Component pieces & limiting part
│   │   ├── test_exports.py            # Scenario I: XLSX (7 sheets) & CSV exports
│   │   ├── test_permissions.py        # Scenario J: Role-based permissions & RBAC
│   │   └── test_edge_cases.py         # Scenario K: Overproduction override, duplicates, negatives
│   ├── alembic/                       # Alembic migrations directory
│   ├── alembic.ini                    # Alembic configuration
│   ├── requirements.txt               # Python package dependencies
│   └── .env.example                   # Environment configuration template
│
├── frontend-kotlin/                   # Compose Multiplatform Project
│   ├── settings.gradle.kts            # Multi-project Gradle settings
│   ├── build.gradle.kts               # Root build script
│   ├── gradle.properties              # Memory & JVM options
│   ├── gradle/libs.versions.toml      # Version catalog (Kotlin 2.0, Compose 1.7, Ktor 3.0)
│   ├── shared/                        # Shared Multiplatform module
│   │   ├── build.gradle.kts
│   │   └── src/commonMain/kotlin/com/footwear/erp/
│   │       ├── api/ErpApiClient.kt    # Ktor REST client with JWT auth
│   │       └── models/Models.kt       # Kotlin serialization DTOs
│   ├── desktop/                       # Windows Desktop application
│   │   ├── build.gradle.kts           # Desktop packaging DSL (EXE & MSI)
│   │   └── src/jvmMain/kotlin/com/footwear/erp/desktop/Main.kt
│   └── android/                       # Android mobile application
│       ├── build.gradle.kts           # Android compile SDK 35
│       └── src/main/
│           ├── AndroidManifest.xml
│           └── kotlin/com/footwear/erp/android/MainActivity.kt
│
├── web-portal/                        # Responsive Factory Web Portal
│   ├── index.html                     # Semantic layout, modals, tables, KPI grids
│   ├── styles.css                     # Modern dark glassmorphic styling
│   └── app.js                         # Live API client & state management
│
├── docs/
│   ├── DEPLOYMENT.md                  # Central server & PostgreSQL guide
│   ├── BACKUP_RESTORE.md              # Disaster recovery & automated backup script
│   ├── DESKTOP_PACKAGING.md           # Instructions for packaging Windows EXE/MSI
│   └── ANDROID_BUILD.md               # Instructions for compiling Android APK
└── README.md
```

---

## 3. Production Department Structure

Configured with default footwear manufacturing categories and sections:

### Category 1: Cutting
1. **Lamination**
2. **Cutting**
3. **Skiving**

### Category 2: Preparation
1. **Printing** (Default sub-processes: *Operation 1*, *Operation 2*, *Operation 3*)
2. **Emboss**
3. **Sewing**

### Category 3: Lasting & Dip
1. **Lasting**
2. **Dip**

*Administrators can add, edit, reorder, activate, deactivate, or rename categories, sections, and operations via API/UI.
Every order maintains its own independent production route snapshot, ensuring changes to default factory templates do not alter existing orders.*

---

## 4. Production Calculation Engine Specifications

All calculations are executed server-side in Python:

1. **Operation Balance**:
   $$\text{Operation Balance} = \max(0, \text{Required Quantity} - \text{Cumulative Accepted})$$
2. **Operation Completion Percentage**:
   $$\text{Completion \%} = \min\left(100.0, \frac{\text{Cumulative Accepted}}{\text{Required Quantity}} \times 100.0\right)$$
3. **Section Completion Rule**:
   * A section marked `NOT_REQUIRED` never blocks order completion and never adds to the required balance.
   * A section marked `REQUIRED` is complete **only** when *every* required operation has balance $= 0$ and *all* required components are met.
   * **Outputs from separate operations are never added together to calculate finished pairs.**
4. **Component Tracking & Conversion Factor**:
   * For piece-based parts (e.g., Side part, Toe cap with factor $K = 2\text{ pcs/pair}$):
     $$\text{Pair Equivalent} = \frac{\text{Accepted Pieces}}{K}$$
   * The operation's pair-equivalent completion reflects the **limiting component** rather than the sum of pieces.
5. **Remaining Working Days**:
   * Evaluated from planning date up to revised delivery deadline against the `FactoryCalendar` (default: Saturday–Thursday work, Friday off in Bangladesh) and `CalendarException` entries (factory holidays and closures).
   * Includes today only when it is a configured workday and current time is prior to cutoff hour (18:00).
6. **Required Daily Production**:
   $$\text{Daily Target} = \lceil \frac{\text{Remaining Accepted Quantity}}{\text{Remaining Working Days}} \rceil$$
   *(If remaining days is 0, full balance is alerted as overdue without division-by-zero).*
7. **Balanced Daily Schedule**:
   * Distributes remaining balance evenly across remaining working days, guaranteeing the exact sum of planned quantities equals the outstanding balance.
8. **Delivery Date Replanning**:
   * Changing an order delivery date records the revision history (old date, new date, user, reason), retains the original date, and automatically recalculates remaining workdays, daily targets, and delivery risks without altering saved production history.

---

## 5. Setup & Launch Instructions

### A. Environment Configuration
Copy `.env.example` to `.env`:
```bash
cd backend
cp .env.example .env
```
Key `.env` variables:
```ini
DATABASE_URL=sqlite:///./footwear_erp.db
# For PostgreSQL:
# DATABASE_URL=postgresql://postgres:postgres@localhost:5432/footwear_erp
SECRET_KEY=footwear-erp-production-planning-secret-key-change-in-prod-2026
DEFAULT_TIMEZONE=Asia/Dhaka
DEFAULT_CUTOFF_HOUR=18
DEFAULT_CUTOFF_MINUTE=0
```

### B. Installing Python Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### C. Seed Demo Database
Populates standard Bangladesh factory calendar, demo accounts, footwear categories/sections, buyers (BATA, Apex), and sample orders:
```bash
python -m app.seed.demo_data
```

### D. Start Backend & Web Management Portal
You can run using `npm`:
```bash
npm run dev
```
Or directly with Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend
```
Once started:
* **Interactive Web Management Portal**: [http://localhost:8000/portal](http://localhost:8000/portal) (or [http://localhost:8000/](http://localhost:8000/))
* **Interactive OpenAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
* **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 6. Demo User Credentials

| Username | Password | Role | Permissions |
| :--- | :--- | :--- | :--- |
| **admin** | `admin123` | Administrator | Full access: users, buyers, orders, routes, overrides, audit logs |
| **planner** | `planner123` | Planning Manager | Planning, orders, section routing, delivery revisions, reports |
| **supervisor** | `supervisor123` | Section Supervisor | Enter daily production, view targets, request entry corrections |
| **viewer** | `viewer123` | Management Viewer | Read-only access to dashboards and permitted planning screens |

---

## 7. Automated Test Suite & Acceptance Results

Run the complete test suite with verbose output:
```bash
cd backend
pytest -v
```

### Test Results Summary:
```text
tests/test_buyers_orders.py::test_scenario_a_buyer_and_order_creation PASSED       [ 9%]
tests/test_component_tracking.py::test_scenario_h_component_tracking PASSED       [18%]
tests/test_daily_targets.py::test_scenario_d_automatic_daily_target PASSED       [27%]
tests/test_delivery_revision.py::test_scenario_f_delivery_date_revision PASSED   [36%]
tests/test_edge_cases.py::test_scenario_k_edge_cases PASSED                        [45%]
tests/test_exports.py::test_scenario_i_export_xlsx_and_csv PASSED                  [54%]
tests/test_multiple_printing.py::test_scenario_c_three_printing_operations PASSED [63%]
tests/test_optional_sections.py::test_scenario_b_optional_production_sections PASSED [72%]
tests/test_permissions.py::test_scenario_j_permissions_and_rbac PASSED             [81%]
tests/test_production_reversal.py::test_scenario_g_production_correction_and_reversal PASSED [90%]
tests/test_working_calendar.py::test_scenario_e_working_calendar PASSED           [100%]

============================== 11 passed in 11.19s ==============================
```

All 11 acceptance criteria scenarios are verified:
* **Scenario A**: Buyer BATA and order for 70,000 pairs created with configured routes.
* **Scenario B**: Lasting required and Dip not required; completing Lasting completes order without Dip blocking.
* **Scenario C**: Three Printing operations (38k each). With Op1=38k, Op2=38k, Op3=25k, Printing is In Progress, balance is 13k, completed pairs is 25k (not 101k sum).
* **Scenario D**: 24,000 pairs with 12 working days produces 2,000 pairs/day target; entry updates upcoming targets.
* **Scenario E**: Factory holidays and non-working weekdays (Fridays) excluded from production-day counts.
* **Scenario F**: Delivery date revision preserves original date, records revision reason, and recalculates targets.
* **Scenario G**: Production entry edit and reversal preserves audit trail and restores balances.
* **Scenario H**: Component conversion factor (pieces-per-pair) converts to pair-equivalents; short component blocks section completion.
* **Scenario I**: 7-sheet XLSX workbook and CSV export files match database figures.
* **Scenario J**: RBAC enforces role permissions; viewers rejected from editing orders or entering production.
* **Scenario K**: Edge cases (zero balance, zero workdays, duplicate detection, overproduction override, quantity change).

---

## 8. Frontend Native Application Builds

### A. Windows Desktop Application (Kotlin Compose Multiplatform)
```powershell
cd frontend-kotlin
# Run in development mode:
./gradlew :desktop:run

# Package standalone native Windows application (.exe):
./gradlew :desktop:packageAppImage

# Package Windows MSI installer:
./gradlew :desktop:packageMsi
```
*See [docs/DESKTOP_PACKAGING.md](file:///d:/ErpPlanning/docs/DESKTOP_PACKAGING.md) for full packaging guidance.*

### B. Android Mobile Application (Kotlin Jetpack Compose Android)
```bash
cd frontend-kotlin
# Assemble debug APK for line testing:
./gradlew :android:assembleDebug

# Assemble release APK:
./gradlew :android:assembleRelease
```
*See [docs/ANDROID_BUILD.md](file:///d:/ErpPlanning/docs/ANDROID_BUILD.md) for signing and shop-floor Wi-Fi setup.*

---

## 9. Excel XLSX 7-Sheet Workbook Structure

When downloading the Order Planning Workbook (`/api/v1/exports/orders/{order_id}/xlsx`):

1. **Order Summary**: Order ID, Buyer, Reference, PO, Style Model, Total Pairs, Dates, Priority, Status, Remaining Days, Completed Pairs, Outstanding Pairs.
2. **Daily Production Plan**: Date, Day, Working Day Status, Operation, Opening Balance, Planned Qty, Daily Target, Cumulative Plan.
3. **Section Summary**: Section Name, Category, Routing Status (Required / Not Required), Operation Count, Completion Status.
4. **Operation Details**: Section, Operation Name, Unit, Required Qty, Cumulative Accepted, Cumulative Rejected, Balance, Completion %, Daily Target, Status.
5. **Component Details**: Component Name, Unit, Pieces/Pair, Required Pieces, Accepted Pieces, Balance Pieces, Pair-Equivalent Accepted.
6. **Production Entry History**: Entry ID, Date, Section, Operation, Component, Quantity, Accepted, Rejected, Unit, Entered By, Reversed Status, Remarks.
7. **Delivery Date History**: Revision ID, Previous Delivery Date, Revised Delivery Date, Reason for Change, Revised By, Timestamp.

---

## 10. Centralized Production Deployment & Backup

* **Production Deployment Guide**: [docs/DEPLOYMENT.md](file:///d:/ErpPlanning/docs/DEPLOYMENT.md) explains central server installation, PostgreSQL configuration, systemd services, and Nginx reverse proxy.
* **Backup & Disaster Recovery Guide**: [docs/BACKUP_RESTORE.md](file:///d:/ErpPlanning/docs/BACKUP_RESTORE.md) provides automated `pg_dump` cron scripts, retention rules, and full recovery commands.
