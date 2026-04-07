# Environment Keys Guide

This is a quick reference for keys in `.env.example`.

Source of truth for loading env vars: `app/core/config.py` (Pydantic `Settings`).

## Important: All Keys Are Required

**No defaults are provided.** Every key must be explicitly set in your `.env` file. The application will fail to start if any required key is missing.

---

## 1) Application Settings

| Key | Meaning | Used in |
|---|---|---|
| `APP_NAME` | Application display/name label. | `main.py` (FastAPI title), `app/core/config.py` |
| `APP_VERSION` | App version label. | `main.py` (FastAPI version), `app/core/config.py` |
| `APP_DESCRIPTION` | FastAPI description text. | `main.py`, `app/core/config.py` |
| `ENVIRONMENT` | Runtime mode (`development`, `staging`, `production`). | `main.py`, `app/core/database.py` |
| `DEBUG` | Debug mode flag (true/false). | `app/core/config.py` |
| `API_PREFIX` | Base prefix for API routes (example: `/api/v1`). | `main.py` |

## 2) Server Configuration

| Key | Meaning | Used in |
|---|---|---|
| `HOST` | Host to bind server to. | `main.py` (`uvicorn.run`) |
| `PORT` | Port to bind server to. | `main.py` (`uvicorn.run`) |
| `WORKERS` | Number of worker processes. | `app/core/config.py` |
| `TOKEN_CLEANUP_INTERVAL_SECONDS` | Interval between token cleanup runs. | `main.py` background cleanup task |
| `BACKGROUND_SHUTDOWN_TIMEOUT_SECONDS` | Graceful shutdown wait time for background tasks. | `main.py` lifespan shutdown |
| `ALLOWED_ORIGINS` | Comma-separated CORS allowlist. | `main.py` via `settings.allowed_origins_list` |

## 3) Supabase / Database

| Key | Meaning | Used in |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL. | `app/core/database.py`, `app/api/auth.py`, `app/services/user_service.py`, `main.py` |
| `SUPABASE_ANON_KEY` | Supabase anon key (client-level operations). | `app/core/database.py`, `app/api/auth.py` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (privileged operations). | `app/core/database.py`, `app/api/auth.py`, `app/services/user_service.py` |
| `DATABASE_URL` | Database connection URL. | loaded/validated in `app/core/config.py` (required setting) |

## 4) JWT / Authentication

| Key | Meaning | Used in |
|---|---|---|
| `JWT_SECRET_KEY` | Secret for signing/verifying JWTs. Must be strong. | `app/core/auth.py` |
| `JWT_ALGORITHM` | JWT algorithm (default HS256). | `app/core/auth.py` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access token lifetime in minutes. | `app/core/auth.py` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh token lifetime in days. | `app/core/auth.py` |

## 5) Email / SMTP

| Key | Meaning | Used in |
|---|---|---|
| `EMAIL_FROM` | Sender email address used in outgoing emails. | `app/services/email.py` |
| `EMAIL_FROM_NAME` | Sender display name. | `app/services/email.py` |
| `SMTP_HOST` | SMTP server host. | `app/services/email.py`, `main.py` (health/logging) |
| `SMTP_PORT` | SMTP server port. | `app/services/email.py`, `main.py` (health/logging) |
| `SMTP_USER` | SMTP username. | `app/services/email.py` |
| `SMTP_PASSWORD` | SMTP password/app password. | `app/services/email.py` |
| `SMTP_TLS` | Enable STARTTLS mode. | `app/services/email.py` |
| `SMTP_SSL` | Use SSL SMTP mode. | `app/services/email.py` |

## 6) Frontend URLs

| Key | Meaning | Used in |
|---|---|---|
| `FRONTEND_URL` | Main frontend URL (password reset/email redirects). | `app/services/auth_service.py` |
| `ADMIN_PANEL_URL` | Admin panel URL for links in notifications/emails. | `app/services/email.py` |
| `VENDOR_PORTAL_URL` | Vendor portal URL used in email links. | `app/services/email.py` |
| `RM_PORTAL_URL` | Relationship manager portal URL. | `app/core/config.py` |

## 7) Logging

| Key | Meaning | Used in |
|---|---|---|
| `LOG_LEVEL` | Logging verbosity level. | `main.py` |
| `LOG_FILE` | Optional log file path. | `main.py` |

## 8) OTP Service (MessageCentral)

| Key | Meaning | Used in |
|---|---|---|
| `MESSAGECENTRAL_CUSTOMER_ID` | MessageCentral customer identifier. | `app/services/otp_service.py` |
| `MESSAGECENTRAL_KEY` | MessageCentral API key. | `app/services/otp_service.py` |
| `MESSAGECENTRAL_EMAIL` | Registered email for MessageCentral calls. | `app/services/otp_service.py` |
| `MESSAGECENTRAL_BASE_URL` | MessageCentral base URL. | `app/services/otp_service.py`, `app/core/config.py` |
| `MESSAGECENTRAL_DEFAULT_COUNTRY_CODE` | Default country code for OTP requests. | `app/services/otp_service.py` |
| `MESSAGECENTRAL_OTP_LENGTH` | OTP length. | `app/services/otp_service.py` |
| `MESSAGECENTRAL_OTP_EXPIRY_SECONDS` | OTP expiry duration in seconds. | `app/services/otp_service.py` |

## 9) Cloudinary (Careers Files)

| Key | Meaning | Used in |
|---|---|---|
| `CLOUDINARY_CLOUD_NAME` | Cloudinary cloud name. | `app/services/cloudinary_service.py`, validated in `app/core/config.py` |
| `CLOUDINARY_API_KEY` | Cloudinary API key. | `app/services/cloudinary_service.py`, validated in `app/core/config.py` |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret. | `app/services/cloudinary_service.py`, validated in `app/core/config.py` |
| `CAREER_CLOUDINARY_UPLOAD_TYPE` | Upload visibility mode (`private` or `public`). | `app/services/cloudinary_service.py`, validated in `app/core/config.py` |
| `CAREER_CLOUDINARY_SIGNED_URL_TTL` | Signed URL expiration time in seconds. | `app/services/cloudinary_service.py`, `app/services/career_service.py` |

---

## Notes

- **All keys are REQUIRED.** No defaults are provided—the application will not start without every key explicitly set in `.env`.
- All keys are loaded from environment through `Settings` in `app/core/config.py`.
- Keep secrets (`JWT_SECRET_KEY`, SMTP password, Supabase keys, Cloudinary secret, Razorpay keys, MessageCentral credentials) out of git and only in real `.env`/deployment secret manager.
