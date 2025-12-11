# Salon Management Backend

**FastAPI 0.115.0** | **Python 3.11.9** | **138 API Endpoints** | **PostgreSQL 17 + PostGIS**

Production-ready backend for a multi-role salon management platform with authentication, payments, booking system, and location services.

---

## 🚀 Quick Start

```powershell
# Clone and setup
git clone https://github.com/ve-sca-via/salon-backend.git
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Run local development server
.\run-local.ps1

# Access
# API: http://localhost:8000
# Docs: http://localhost:8000/docs
```

**New to the project?** Read [Getting Started Guide](docs/getting-started/GETTING_STARTED.md)

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| **[Getting Started](docs/getting-started/GETTING_STARTED.md)** | Setup, run, test the backend |
| **[API Endpoints](docs/reference/API_ENDPOINTS.md)** | All 138 endpoints documented |
| **[Developer Reference](docs/reference/DEVELOPER_REFERENCE.md)** | Commands, patterns, debugging |
| **[Architecture Map](docs/architecture/ARCHITECTURE_MAP.md)** | System overview |
| **[Documentation Index](docs/reference/INDEX.md)** | Complete doc listing |

---

## ✨ Features

### Core Functionality
- **Multi-role Authentication** - Admin, Relationship Manager, Vendor, Customer
- **JWT Auth** - 30min access tokens + 7 day refresh tokens
- **Rate Limiting** - 60/min global, 5/min login, 3/min signup
- **Token Blacklist** - Logout invalidates tokens
- **Background Tasks** - Auto-cleanup expired tokens (every 6 hours)

### Business Features
- **Salon Management** - CRUD operations with verification workflow
- **Service Catalog** - Dynamic services with categories and pricing
- **Booking System** - Real-time slot calculation and management
- **Payment Integration** - Razorpay with split payments
- **Review System** - Customer reviews with ratings
- **RM Scoring** - Performance tracking for relationship managers
- **Career Module** - Job applications with document uploads

### Technical Features
- **Email Service** - SMTP (Gmail) with retry logic
- **Geocoding** - Address to lat/lng conversion
- **Location Search** - PostGIS-powered nearby salon search
- **File Upload** - Supabase Storage for images/documents
- **Activity Logging** - Track all admin/RM actions
- **Real-time Updates** - WebSocket support (experimental)

---

## 🛠️ Tech Stack

**Backend:**
- FastAPI 0.115.0 (async/await)
- Python 3.11.9
- Uvicorn 0.32.1

**Database:**
- Supabase PostgreSQL 17
- PostGIS extension (location queries)
- 25+ tables

**Authentication:**
- JWT (python-jose 3.3.0)
- bcrypt 4.1.1
- SlowAPI 0.1.9 (rate limiting)

**Integrations:**
- Razorpay 1.4.1 (payments)
- SMTP/Gmail (emails 0.6)
- Geopy 2.4.0 (geocoding)

**Deployment:**
- Render.com
- Git-based CI/CD

---

## 📊 System Statistics

- **Total Endpoints:** 138
- **API Modules:** Auth, Admin, Customers, Vendors, RM, Salons, Bookings, Payments, Careers, Upload, Location, Realtime
- **Services:** 16 service classes
- **Database Tables:** 25+
- **Test Coverage:** Unit + integration tests
- **Rate Limits:** 60/min global, 5/min login, 3/min signup

---

## 🎯 User Roles

| Role | Permissions |
|------|-------------|
| **Admin** | Full system access - users, salons, config, analytics |
| **Relationship Manager** | Submit vendor requests, manage approved salons |
| **Vendor** | Manage own salon, services, staff, bookings |
| **Customer** | Browse salons, book services, write reviews |

---

## 🔧 Development

### Run Tests
```powershell
pytest                  # All tests
pytest --cov            # With coverage
pytest -k "auth"        # Tests matching "auth"
```

### Database Migrations
```powershell
supabase db push        # Apply migrations
supabase db reset       # Reset (wipes data!)
```

### Code Quality
```powershell
black app/              # Format code
flake8 app/             # Lint
mypy app/               # Type check
```

---

## 🌍 Environments

| Environment | Command | Database | Purpose |
|-------------|---------|----------|---------|
| **Local** | `.\run-local.ps1` | Local/Remote | Daily development |
| **Staging** | `.\run-staging.ps1` | Staging DB | Online testing |
| **Production** | `.\run-production.ps1` | Production DB | Live system |

---

## 📁 Project Structure

```
backend/
├── app/
│   ├── api/          # 138 API endpoints
│   ├── core/         # Config, database, auth
│   ├── services/     # Business logic (16 services)
│   └── schemas/      # Pydantic models
├── supabase/
│   └── migrations/   # SQL migrations
├── tests/            # Unit & integration tests
├── docs/             # Documentation
├── main.py           # FastAPI app entry point
├── requirements.txt  # Dependencies
├── pytest.ini        # Test config
└── render.yaml       # Deployment config
```

---

## 🔐 Security

- **JWT Tokens** - HS256 signed with secret key
- **Password Hashing** - bcrypt with salt
- **Service Role** - Bypasses RLS for admin operations
- **Rate Limiting** - Prevents brute force attacks
- **Token Blacklist** - Logout invalidates tokens
- **CORS** - Configured for specific origins only
- **HTTPS** - Enforced in production
- **Input Validation** - Pydantic models

---

## 🚀 Deployment

**Platform:** Render.com

**Staging (Auto):**
```bash
git push origin staging  # Auto-deploys to staging environment
```

**Production (Manual):**
1. Merge to `main` branch
2. Deploy manually from Render dashboard

See [Deployment Guide](docs/deployment/DEPLOYMENT_FLOW.md) for details.

---

## 🆘 Support

- **Documentation:** [docs/](docs/) folder
- **API Docs:** http://localhost:8000/docs (Swagger UI)
- **Issues:** GitHub Issues
- **Team Lead:** For production credentials

---

## 📝 License

Proprietary - All rights reserved

---

## 🔄 Recent Updates

**December 11, 2025:**
- Documentation overhaul - brutally analyzed and updated
- Accurate endpoint count: 138 (verified from code)
- Removed redundant documentation
- Created comprehensive API reference
- Streamlined getting started guide

See [DOCUMENTATION_UPDATE_LOG.md](docs/DOCUMENTATION_UPDATE_LOG.md) for details.

---

**Ready to build?** → [Getting Started Guide](docs/getting-started/GETTING_STARTED.md)
- **Testing**: pytest with comprehensive test coverage
- **Documentation**: OpenAPI/Swagger UI

## 📋 Prerequisites

- Python 3.10+
- Docker Desktop
- Supabase CLI
- Node.js (for frontend development)

## 🏁 Quick Start

### 1. Environment Setup

```bash
# Clone the repository
git clone <repository-url>
cd salon-backend

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 2. Environment Configuration

Copy the environment template and configure your settings:

```bash
cp .env.example .env
# Edit .env with your configuration
```

Required environment variables:
- `SUPABASE_URL`: Your Supabase project URL
- `SUPABASE_ANON_KEY`: Supabase anonymous key
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase service role key
- `JWT_SECRET_KEY`: Secret key for JWT tokens
- `RAZORPAY_KEY_ID`: Razorpay API key
- `RAZORPAY_KEY_SECRET`: Razorpay API secret
- `SMTP_SERVER`: SMTP server address
- `GOOGLE_MAPS_API_KEY`: Google Maps API key

### 3. Database Setup

```bash
# Start Supabase locally
supabase start

# Run migrations
supabase db push

# Seed initial data
supabase seed
```

### 4. Run the Application

```bash
# Development mode
python main.py

# Production mode
python run-production.ps1
```

The API will be available at `http://localhost:8000`
- API Documentation: `http://localhost:8000/api/v1/docs`
- Health Check: `http://localhost:8000/api/v1/health`

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html

# Run specific test file
pytest tests/test_auth.py -v
```

## 📁 Project Structure

```
backend/
├── app/
│   ├── api/              # API route handlers
│   │   ├── admin.py      # Admin endpoints
│   │   ├── auth.py       # Authentication endpoints
│   │   ├── bookings.py   # Booking management
│   │   ├── customers.py  # Customer endpoints
│   │   ├── location.py   # Location/geocoding services
│   │   ├── salons.py     # Salon management
│   │   └── vendors.py    # Vendor endpoints
│   ├── core/             # Core functionality
│   │   ├── auth.py       # Authentication & authorization
│   │   ├── config.py     # Configuration management
│   │   ├── database.py   # Database connection
│   │   └── logging.py    # Logging configuration
│   ├── schemas/          # Pydantic models
│   │   ├── domain/       # Domain models
│   │   ├── request/      # Request schemas
│   │   └── response/     # Response schemas
│   └── services/         # Business logic
│       ├── admin_service.py
│       ├── booking_service.py
│       ├── email.py
│       ├── geocoding.py
│       ├── vendor_service.py
│       └── vendor_approval_service.py
├── docs/                 # Documentation
├── supabase/             # Database migrations
├── tests/                # Test suite
├── main.py              # Application entry point
├── pytest.ini           # Test configuration
└── requirements.txt     # Python dependencies
```

## 🔒 Security Features

- JWT token authentication with expiration
- Role-based access control (RBAC)
- Password hashing with bcrypt
- Rate limiting and request throttling
- Input validation with Pydantic
- SQL injection prevention
- CORS configuration
- Security headers middleware
- Token revocation system

## 📊 API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - User registration
- `POST /api/v1/auth/refresh` - Refresh access token
- `POST /api/v1/auth/logout` - User logout

### Salons
- `GET /api/v1/salons/search/nearby` - Find nearby salons
- `GET /api/v1/salons/{salon_id}` - Get salon details
- `GET /api/v1/salons/{salon_id}/slots` - Get available booking slots
- `POST /api/v1/salons/{salon_id}/book` - Create booking

### Admin
- `GET /api/v1/admin/dashboard` - Admin dashboard data
- `GET /api/v1/admin/staff` - List staff members
- `POST /api/v1/admin/staff` - Create staff member
- `PUT /api/v1/admin/staff/{staff_id}` - Update staff member

### Vendor
- `GET /api/v1/vendor/salon` - Get vendor's salon
- `POST /api/v1/vendor/services` - Create service
- `PUT /api/v1/vendor/services/{service_id}` - Update service
- `DELETE /api/v1/vendor/services/{service_id}` - Delete service

## 🚀 Deployment

### Production Checklist

- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] SSL certificates installed
- [ ] Domain configured
- [ ] Monitoring tools set up
- [ ] Backup strategy implemented
- [ ] Security audit completed

### Docker Deployment

```bash
# Build the image
docker build -t salon-backend .

# Run with environment file
docker run -p 8000:8000 --env-file .env salon-backend
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For support and questions:
- Create an issue in the repository
- Contact the development team
- Check the documentation in the `docs/` folder

## 🔄 Recent Updates

### Phase 4 (Maintenance) - Completed
- ✅ Removed TODOs and legacy code
- ✅ Added comprehensive tests (auth module coverage: 24% → 85%+)
- ✅ Improved documentation (added README.md)
- ✅ Performance optimizations (slot calculation, database queries)
- ✅ Code consistency refactoring (removed print statements, improved error handling)

### Phase 3 (Production Improvements) - Completed
- ✅ Health checks for all dependencies
- ✅ Request/response logging middleware
- ✅ API versioning strategy (/api/v1/)
- ✅ Email retry logic with exponential backoff
- ✅ Transaction management for multi-step operations

### Phase 2 (Database Thread Safety) - Completed
- ✅ Database connection thread safety
- ✅ Dependency injection improvements
- ✅ Import error resolution

### Phase 1 (Security Fixes) - Completed
- ✅ JWT authentication hardening
- ✅ Rate limiting implementation
- ✅ HTTPS enforcement
- ✅ Input validation enhancement