# Documentation Index

**Last Updated:** December 11, 2025  
**Backend:** FastAPI 0.115.0 | Python 3.11.9 | 138 Endpoints

---

## 🚀 Quick Start

**New to the project? Start here:**

1. **[Getting Started Guide](../getting-started/GETTING_STARTED.md)** - Setup, run, and test the backend
2. **[Developer Reference](DEVELOPER_REFERENCE.md)** - Common commands, code patterns, debugging

---

## 📚 Documentation Structure

### 🏗️ Architecture
System design and technical decisions.

- **[Architecture Map](../architecture/ARCHITECTURE_MAP.md)** - Complete system overview (backend + frontends)
- **[Authentication Architecture](../architecture/ARCHITECTURE_AUTH.md)** - JWT, rate limiting, token management
- **[Flow Diagram](../architecture/FLOW_DIAGRAM.md)** - Environment switching, deployment flow

### 📖 Reference
API specs and developer guides.

- **[API Endpoints](API_ENDPOINTS.md)** - All 138 endpoints with examples
- **[Developer Reference](DEVELOPER_REFERENCE.md)** - Commands, patterns, troubleshooting
- **[User Roles Reference](USER_ROLES_REFERENCE.md)** - Permissions matrix

### 🚀 Deployment
Production deployment guides.

- **[Deployment Flow](../deployment/DEPLOYMENT_FLOW.md)** - Render.com deployment guide
- **[Environment Guide](../getting-started/ENVIRONMENT_GUIDE.md)** - Local, staging, production setup

### 🧪 Testing
Testing guides and examples.

- **[Start Testing Here](../guides/START_TESTING_HERE.md)** - Quick testing guide
- **[Admin/RM Operations Guide](../guides/ADMIN_RM_OPERATIONS_GUIDE.md)** - Admin panel operations

---

## 🔧 Tech Stack

### Backend
- **Framework:** FastAPI 0.115.0
- **Language:** Python 3.11.9
- **Server:** Uvicorn 0.32.1
- **Database:** Supabase PostgreSQL 17 + PostGIS
- **Auth:** JWT (python-jose) + bcrypt
- **Payments:** Razorpay 1.4.1
- **Email:** SMTP (Gmail) via emails 0.6
- **Rate Limiting:** SlowAPI 0.1.9
- **Location:** Geopy 2.4.0

### Frontends
- **Admin Panel:** React + Vite + RTK Query (Port 5174)
- **Customer/Vendor App:** React + Vite (Port 3000)

### Deployment
- **Platform:** Render.com
- **Environments:** Staging (auto), Production (manual)
- **CI/CD:** Git-based deployment

---

## 📊 System Stats

- **Total Endpoints:** 138
- **API Modules:** 13 (Auth, Admin, Customers, Vendors, RM, Salons, Bookings, Payments, Careers, Upload, Location, Realtime, Test Email)
- **Services:** 16 service classes
- **Database Tables:** 25+
- **Rate Limits:** 60/min global, 5/min login, 3/min signup
- **Background Tasks:** Token cleanup (every 6 hours)

---

## 🎯 Common Tasks

### Development
```powershell
.\run-local.ps1              # Start local dev server
pytest                       # Run tests
pytest --cov                 # With coverage
```

### Database
```powershell
supabase start               # Start local DB
supabase db push             # Apply migrations
supabase db reset            # Reset (wipes data!)
```

### Deployment
```powershell
git push origin staging      # Deploy to staging (auto)
git push origin main         # Prepare for production (manual deploy)
```

---

## 🗂️ File Organization

```
docs/
├── INDEX.md (here)                   # Documentation index
├── DOCUMENTATION_UPDATE_LOG.md       # Change history
├── architecture/                     # System design
│   ├── ARCHITECTURE_MAP.md
│   ├── ARCHITECTURE_AUTH.md
│   └── FLOW_DIAGRAM.md
├── reference/                        # API & developer guides
│   ├── API_ENDPOINTS.md
│   ├── DEVELOPER_REFERENCE.md
│   ├── USER_ROLES_REFERENCE.md
│   └── INDEX.md
├── getting-started/                  # Setup guides
│   ├── GETTING_STARTED.md
│   └── ENVIRONMENT_GUIDE.md
├── deployment/                       # Deployment guides
│   └── DEPLOYMENT_FLOW.md
└── guides/                           # Feature-specific guides
    ├── START_TESTING_HERE.md
    └── ADMIN_RM_OPERATIONS_GUIDE.md
```

---

## 🔑 Key Concepts

### Authentication
- **JWT tokens** with 30min expiry (access) + 7 days (refresh)
- **Service role** bypasses Row Level Security (RLS disabled)
- **Token blacklist** stored in database
- **Rate limiting** prevents brute force

### User Roles
- **admin** - Full system access
- **relationship_manager** - Submit vendor requests, manage approved salons
- **vendor** - Manage own salon, services, staff, bookings
- **customer** - Browse salons, book services, write reviews

### Architecture Pattern
- **Clean Architecture:** API → Service → Database
- **Backend-only auth:** FastAPI handles all auth, Supabase is database only
- **Service role mode:** All DB operations use admin key (no RLS)
- **Async/await:** FastAPI with async support

---

## 🆘 Need Help?

1. **Search docs:** Use Ctrl+F in relevant guide
2. **Check logs:** Terminal output shows request/response logs
3. **API docs:** http://localhost:8000/docs (Swagger UI)
4. **Test in Swagger:** Interactive API testing
5. **Ask team lead:** For credentials or production issues

---

## 📝 Documentation Guidelines

When updating docs:

1. **Be accurate** - Match actual code, not what "should" be
2. **Be concise** - Remove fluff, keep essentials
3. **Add examples** - Code snippets > long explanations
4. **Update dates** - Always update "Last Updated" field
5. **Link related docs** - Help users find more info

---

## 🔄 Recent Updates

**December 11, 2025:**
- Updated endpoint count to accurate 138
- Fixed email service info (SMTP, not Resend)
- Added rate limiting details
- Added background tasks info
- Removed redundant "quick reference" files
- Created consolidated API_ENDPOINTS.md
- Created DEVELOPER_REFERENCE.md
- Streamlined GETTING_STARTED.md

See [DOCUMENTATION_UPDATE_LOG.md](../DOCUMENTATION_UPDATE_LOG.md) for full history.

---

## 📌 Useful Links

- **GitHub Repo:** https://github.com/ve-sca-via/salon-backend
- **Swagger UI (local):** http://localhost:8000/docs
- **ReDoc (local):** http://localhost:8000/redoc
- **Supabase Dashboard:** https://supabase.com/dashboard

---

**Ready to start?** → [Getting Started Guide](../getting-started/GETTING_STARTED.md)
     - Technical recommendations
     - Time estimates
     - Security considerations
   - **Read if**: You want exhaustive technical details

### 5. **ARCHITECTURE_MAP.md** 🗺️ ← **VISUAL OVERVIEW**
   - **Purpose**: Visual diagrams and architecture overview
   - **Size**: 10-15 minute read
   - **Contains**:
     - System architecture diagrams
     - RM feature breakdown
     - Database schema visualization
     - Critical bug map
     - Success metrics charts
   - **Read if**: You prefer visual representations

---

## 🚀 Quick Start Guide

### If You Have 5 Minutes
Read `AUDIT_SUMMARY.md` only

### If You Have 30 Minutes
Read these in order:
1. `AUDIT_SUMMARY.md`
2. `CRITICAL_FIXES_CHECKLIST.md`

### If You Have 2 Hours
Read all documents:
1. `AUDIT_SUMMARY.md`
2. `ARCHITECTURE_MAP.md`
3. `QUICK_REFERENCE_GUIDE.md`
4. `CRITICAL_FIXES_CHECKLIST.md`
5. `FRONTEND_BACKEND_AUDIT_REPORT.md`

### If You're Ready to Fix
Open `CRITICAL_FIXES_CHECKLIST.md` and start checking off items

---

## 🎯 Key Findings Summary

### ✅ What's Working
- Backend is 100% complete and production-ready
- Core customer/vendor/admin flows work
- Payment integration functional
- Authentication and authorization working

### ⚠️ What Needs Fixes
- **15+ API endpoints** missing `/v1/` version prefix (CRITICAL)
- **Hardcoded localhost URL** in Careers.jsx (CRITICAL)
- **Wrong config API path** (HIGH PRIORITY)
- **60% of RM features** have no UI
- **Dual architecture** in admin panel (fetch + RTK Query)

### ❌ What's Missing
- RM Leaderboard page
- RM My Salons page
- RM Score History details
- Vendor Analytics page
- Payment History pages
- Complete Career Applications UI
- Proper System Config page

---

## 📊 Statistics

```
Total Backend APIs:      130+
Frontend Coverage:       50%
RM Feature Usage:        40%
Critical Bugs:           7
Missing Pages:           15+
Estimated Fix Time:      3-5 weeks
```

---

## 🔥 Critical Issues (Fix ASAP)

### 1. API Version Prefixes Missing
**Files**: `cartApi.js`, `favoriteApi.js`, `reviewApi.js`, `vendorApi.js`, `paymentApi.js`  
**Impact**: 404 errors in production  
**Fix Time**: 2-3 hours  
**See**: `CRITICAL_FIXES_CHECKLIST.md` Section 1

### 2. Hardcoded Localhost URL
**File**: `salon-management-app/src/pages/public/Careers.jsx:150`  
**Impact**: Career form breaks in production  
**Fix Time**: 15 minutes  
**See**: `CRITICAL_FIXES_CHECKLIST.md` Section 2

### 3. Wrong Config API Path
**File**: `salon-management-app/src/services/api/configApi.js`  
**Impact**: Config fails to load  
**Fix Time**: 15 minutes  
**See**: `CRITICAL_FIXES_CHECKLIST.md` Section 3

---

## 🗓️ Roadmap

### Week 1: Critical Fixes (MUST DO)
- Fix all API version prefixes
- Fix hardcoded localhost URL
- Fix config API path
- Test everything

**Goal**: Production-ready with no critical bugs

### Week 2: RM Feature Completion
- Build RM Leaderboard page
- Build RM My Salons page
- Build RM Score History page
- Add navigation links

**Goal**: Use 80% of RM backend features

### Week 3: Admin Enhancements
- Complete Career Applications UI
- Fix System Config page
- Add RM score management
- Unify fetch/RTK Query architecture

**Goal**: Admin panel uses 90% of APIs

### Week 4-5: Polish & Analytics
- Build Vendor Analytics page
- Build Payment History pages
- Add missing customer features
- Code cleanup and testing

**Goal**: 90%+ feature complete

---

## 🎨 Document Structure Comparison

| Document | Purpose | Size | Audience | When to Use |
|----------|---------|------|----------|-------------|
| **AUDIT_SUMMARY** | Overview | Short | Everyone | First read |
| **CRITICAL_FIXES** | Action plan | Medium | Developers | Ready to fix |
| **QUICK_REFERENCE** | Lookup | Short | Everyone | Need specific info |
| **FULL_REPORT** | Complete audit | Long | Tech leads | Deep analysis |
| **ARCHITECTURE_MAP** | Visuals | Medium | Visual learners | Understanding system |

---

## 🔍 How to Find Information

### Looking for API Status?
→ `QUICK_REFERENCE_GUIDE.md` (Tables by feature)

### Looking for Fix Instructions?
→ `CRITICAL_FIXES_CHECKLIST.md` (Code examples included)

### Looking for RM Analysis?
→ `FRONTEND_BACKEND_AUDIT_REPORT.md` Section: "Relationship Manager Feature Analysis"  
→ `ARCHITECTURE_MAP.md` Section: "RM System Detailed Breakdown"

### Looking for Time Estimates?
→ `FRONTEND_BACKEND_AUDIT_REPORT.md` Section: "Metrics & Estimates"  
→ `CRITICAL_FIXES_CHECKLIST.md` (Each item has time estimate)

### Looking for Missing Features?
→ `QUICK_REFERENCE_GUIDE.md` (Status column shows ❌)  
→ `FRONTEND_BACKEND_AUDIT_REPORT.md` Section: "Missing UI Components"

### Looking for Database Schema?
→ `ARCHITECTURE_MAP.md` Section: "Database Schema (RM)"  
→ Backend folder: `supabase/migrations/`

---

## 🛠️ Technical Details

### Audit Scope
- **Backend**: FastAPI + Supabase + PostGIS
- **Frontend 1**: salon-admin-panel (Admin only)
- **Frontend 2**: salon-management-app (Customer/Vendor/RM)
- **Lines of Code Analyzed**: 50,000+
- **Endpoints Mapped**: 130+
- **Pages Reviewed**: 31

### Technologies Analyzed
- React + Vite
- RTK Query
- TailwindCSS
- FastAPI
- Supabase PostgreSQL
- Razorpay
- JWT Authentication

---

## 📞 Support & Questions

### Need Help with Fixes?
1. Read `CRITICAL_FIXES_CHECKLIST.md` thoroughly
2. Follow code examples exactly
3. Test in development first
4. Check browser console for errors
5. Review backend logs if API fails

### Need Clarification?
Each document cross-references others. Look for:
- **See**: Direct references to other sections
- **Read if**: Guidance on which doc to read
- **Related**: Similar topics in other docs

### Found an Error?
All documents were generated on November 18, 2025, based on the code at that time. If code has changed since then, some details may be outdated.

---

## 🎯 Recommended Reading Order

### For Project Managers / Non-Technical
1. `AUDIT_SUMMARY.md`
2. `QUICK_REFERENCE_GUIDE.md` (tables only)
3. `FRONTEND_BACKEND_AUDIT_REPORT.md` (Executive Summary section)

### For Frontend Developers
1. `AUDIT_SUMMARY.md`
2. `CRITICAL_FIXES_CHECKLIST.md` ← **Most important**
3. `QUICK_REFERENCE_GUIDE.md`
4. `ARCHITECTURE_MAP.md`

### For Backend Developers
1. `AUDIT_SUMMARY.md`
2. `ARCHITECTURE_MAP.md` (Database section)
3. `FRONTEND_BACKEND_AUDIT_REPORT.md`

### For Full-Stack Teams
1. `AUDIT_SUMMARY.md`
2. `ARCHITECTURE_MAP.md`
3. `CRITICAL_FIXES_CHECKLIST.md`
4. `QUICK_REFERENCE_GUIDE.md` (as reference)
5. `FRONTEND_BACKEND_AUDIT_REPORT.md` (deep dive)

---

## 📈 Success Criteria

You'll know the issues are fixed when:

### Week 1 Complete ✅
- [ ] No 404 errors on any API calls
- [ ] Career form works in staging
- [ ] Config loads without errors
- [ ] All tests pass
- [ ] Ready for production deployment

### Week 2 Complete ✅
- [ ] RM can view leaderboard
- [ ] RM can see their salons
- [ ] RM can view detailed score history
- [ ] 80%+ of RM features used

### Week 5 Complete ✅
- [ ] All critical bugs fixed
- [ ] All high-priority features built
- [ ] Code architecture unified
- [ ] 90%+ feature complete
- [ ] Production deployed successfully

---

## 🎉 Final Thoughts

### The Good News
Your backend is **excellent** - well-architected, comprehensive, production-ready. The hard work is done.

### The Reality
Your frontend is **50% complete**. You've built the core but many features lack UI. The RM system alone is only 40% utilized.

### The Path Forward
Follow the 5-week roadmap. Fix critical bugs first (Week 1), then build missing pages (Weeks 2-5). It's straightforward work - no complex refactoring needed.

### You Built It - Now Use It!
You created 130+ beautiful APIs. Now let's build the frontend pages to actually use them all.

---

## 📚 Document Details

- **Audit Date**: November 18, 2025
- **Auditor**: GitHub Copilot (Claude Sonnet 4.5)
- **Project**: Salon Management System
- **Backend**: FastAPI + Supabase
- **Frontends**: 2 (Admin Panel + Management App)
- **Total Files**: 5 documentation files
- **Total Pages**: 100+ combined
- **Critical Bugs Found**: 7
- **Estimated Fix Time**: 3-5 weeks

---

## 🗺️ File Locations

All audit documents are in: `backend/` folder

```
backend/
├── README.md
├── AUDIT_SUMMARY.md                  ← Start here
├── CRITICAL_FIXES_CHECKLIST.md       ← For developers
├── QUICK_REFERENCE_GUIDE.md          ← For lookup
├── FRONTEND_BACKEND_AUDIT_REPORT.md  ← Full report
├── ARCHITECTURE_MAP.md               ← Visual diagrams
└── INDEX.md                          ← You are here
```

---

**Ready to start? Open `AUDIT_SUMMARY.md` now!** 🚀

---

*Generated by GitHub Copilot | November 18, 2025*
