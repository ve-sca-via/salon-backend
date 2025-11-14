# Career Application System - Testing Guide

## Overview
Complete career application system for RM (Relationship Manager) positions with document upload functionality.

## System Components

### Backend (✅ Completed)
- **Database**: `career_applications` table in PostgreSQL
- **API Endpoint**: `POST /api/v1/careers/apply`
- **File Storage**: Supabase Storage bucket `career-documents`
- **Email Templates**:
  - `career_application_confirmation.html` (sent to applicant)
  - `new_career_application_admin.html` (sent to admin)
- **File**: `app/api/careers.py` (550+ lines)

### Frontend (✅ Completed)
- **Page**: `src/pages/public/Careers.jsx` (600+ lines)
- **Component**: `src/components/shared/FileUpload.jsx` (220 lines)
- **Route**: `/careers` (added to App.jsx)
- **Navigation**: Footer link with "Hiring" badge

### Database Migration (✅ Applied)
- **File**: `supabase/migrations/20251114003333_create_career_applications.sql`
- **Status**: Successfully applied with `supabase db reset`

## Document Requirements

### Required Documents (5)
1. **Resume/CV** - PDF/Word format
2. **Aadhaar Card** - PDF/JPG/PNG
3. **PAN Card** - PDF/JPG/PNG
4. **Passport Photo** - JPG/PNG (with preview)
5. **Address Proof** - PDF/JPG/PNG (utility bill, rent agreement, etc.)

### Optional Documents (3)
6. **Educational Certificates** - Multiple files supported
7. **Experience Letter** - Previous employment proof
8. **Salary Slip** - Latest salary slip or offer letter

### File Validation
- **Max Size**: 5MB per file
- **Allowed Types**: PDF, JPG, JPEG, PNG, WEBP
- **Storage**: Private Supabase Storage bucket
- **Security**: RLS policies enabled

## API Endpoints

### 1. Submit Application
```http
POST /api/v1/careers/apply
Content-Type: multipart/form-data

Body (FormData):
- full_name: string (required)
- email: string (required)
- phone: string (required)
- current_city: string
- current_address: string
- willing_to_relocate: boolean
- experience_years: integer
- previous_company: string
- current_salary: number
- expected_salary: number
- notice_period_days: integer
- highest_qualification: string
- university_name: string
- graduation_year: integer
- cover_letter: string
- linkedin_url: string
- portfolio_url: string
- resume: file (required)
- aadhaar_card: file (required)
- pan_card: file (required)
- photo: file (required)
- address_proof: file (required)
- educational_certificates: file[] (optional)
- experience_letter: file (optional)
- salary_slip: file (optional)

Response (201 Created):
{
  "message": "Application submitted successfully",
  "application_id": "uuid",
  "application_number": "CAREER-2024-00001"
}
```

### 2. List Applications (Admin)
```http
GET /api/v1/careers/applications?status=pending&position=Relationship%20Manager

Response (200 OK):
{
  "applications": [...],
  "total": 10
}
```

### 3. Get Application Detail (Admin)
```http
GET /api/v1/careers/applications/{application_id}

Response (200 OK):
{
  "id": "uuid",
  "full_name": "John Doe",
  "email": "john@example.com",
  ...
}
```

### 4. Update Application Status (Admin)
```http
PATCH /api/v1/careers/applications/{application_id}

Body:
{
  "status": "shortlisted",
  "admin_notes": "Good candidate for next round"
}

Response (200 OK):
{
  "message": "Application updated successfully"
}
```

### 5. Download Document (Admin)
```http
GET /api/v1/careers/applications/{application_id}/download/{document_type}

Response (200 OK):
{
  "url": "signed_supabase_storage_url",
  "expires_in": 3600
}
```

## Testing Steps

### 1. Start Backend Server
```bash
cd G:\vescavia\Projects\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Start Frontend Dev Server
```bash
cd G:\vescavia\Projects\salon-management-app
npm run dev
```

### 3. Test Application Submission
1. Navigate to `http://localhost:5173/careers`
2. Fill in all required fields:
   - Full name, email, phone
   - Experience details
   - Educational background
3. Upload all 5 required documents:
   - Resume (PDF/Word)
   - Aadhaar card
   - PAN card
   - Passport photo (should show preview)
   - Address proof
4. Optional: Add experience letter, salary slip
5. Click "Submit Application"
6. Verify success page displays with application number
7. Check Mailpit (http://127.0.0.1:54324) for 2 emails:
   - Confirmation email to applicant
   - Notification email to admin

### 4. Verify Database Entry
```bash
cd G:\vescavia\Projects\backend
supabase db inspect tables career_applications

# Or query directly:
supabase db psql -c "SELECT id, full_name, email, status, created_at FROM career_applications ORDER BY created_at DESC LIMIT 5;"
```

### 5. Verify File Storage
1. Open Supabase Studio: `supabase dashboard`
2. Navigate to Storage → Buckets → career-documents
3. Verify uploaded files are present with proper naming:
   - `{application_id}_resume.{ext}`
   - `{application_id}_aadhaar.{ext}`
   - `{application_id}_pan.{ext}`
   - etc.

### 6. Test Admin API Endpoints
```bash
# List all applications
curl http://localhost:8000/api/v1/careers/applications

# Get specific application
curl http://localhost:8000/api/v1/careers/applications/{APPLICATION_ID}

# Update status
curl -X PATCH http://localhost:8000/api/v1/careers/applications/{APPLICATION_ID} \
  -H "Content-Type: application/json" \
  -d '{"status": "shortlisted", "admin_notes": "Test note"}'

# Get download URL
curl http://localhost:8000/api/v1/careers/applications/{APPLICATION_ID}/download/resume
```

## Email Templates

### Applicant Confirmation Email
- **Subject**: "Application Received - Relationship Manager"
- **Template**: `app/templates/email/career_application_confirmation.html`
- **Content**:
  - Orange gradient header
  - Application number
  - Position applied for
  - "What Happens Next" checklist
  - Support contact information

### Admin Notification Email
- **Subject**: "🔔 New Career Application - Relationship Manager"
- **Template**: `app/templates/email/new_career_application_admin.html`
- **To**: admin@salonplatform.com
- **Content**:
  - Applicant details table
  - Submitted documents checklist
  - Review Application button (links to admin panel)

## Application Statuses
- `pending` - Initial status after submission
- `under_review` - Application being reviewed
- `shortlisted` - Selected for next round
- `interview_scheduled` - Interview date set
- `rejected` - Application rejected
- `hired` - Candidate hired

## Known Issues / TODOs
- [ ] Admin panel UI not yet created (see PENDING section below)
- [ ] Email admin recipient hardcoded (should move to settings)
- [ ] Educational certificates array handling (currently accepts one file)
- [ ] Application number generation could be improved with better sequence
- [ ] Add phone validation on backend
- [ ] Add duplicate email check (prevent multiple applications)

## PENDING: Admin Panel Implementation
Create admin view to review applications in `salon-admin-panel/src/pages/Careers.jsx`:

**Features Needed**:
1. Table view of all applications with filters (status, position, date range)
2. Applicant details modal with all information
3. Document viewer/download functionality
4. Status update dropdown (pending → shortlisted → hired)
5. Add notes/comments section
6. Interview scheduling interface
7. Export to CSV functionality
8. Email applicant directly from panel

## File Structure
```
backend/
├── app/
│   ├── api/
│   │   └── careers.py (550 lines)
│   ├── templates/
│   │   └── email/
│   │       ├── career_application_confirmation.html
│   │       └── new_career_application_admin.html
│   └── services/
│       └── email.py (modified with 2 new methods)
├── supabase/
│   └── migrations/
│       └── 20251114003333_create_career_applications.sql
└── main.py (router added)

salon-management-app/
├── src/
│   ├── components/
│   │   ├── layout/
│   │   │   └── Footer.jsx (careers link added)
│   │   └── shared/
│   │       └── FileUpload.jsx (220 lines)
│   ├── pages/
│   │   └── public/
│   │       └── Careers.jsx (600+ lines)
│   └── App.jsx (route added)
```

## Success Criteria
✅ User can access `/careers` page from footer
✅ User can fill application form with validation
✅ User can upload 5 required documents
✅ File validation works (size, type)
✅ Image preview works for photo
✅ Form submits to backend API
✅ Files upload to Supabase Storage
✅ Database record created in career_applications
✅ Confirmation email sent to applicant
✅ Admin notification email sent
✅ Success page displays with application number
✅ User can return to home page

## Environment Variables Required
```env
# Backend .env
EMAIL_ENABLED=True
EMAIL_FROM=noreply@salonplatform.com
SMTP_SERVER=127.0.0.1
SMTP_PORT=54325
EMAIL_USERNAME=
EMAIL_PASSWORD=
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=your_anon_key
```

## Troubleshooting

### Issue: Files not uploading
- Check Supabase is running: `supabase status`
- Verify bucket exists: `supabase storage list`
- Check RLS policies allow public insert

### Issue: Emails not sending
- Verify Mailpit is running on port 54325
- Check `EMAIL_ENABLED=True` in `.env`
- View Mailpit UI: http://127.0.0.1:54324
- Check backend logs for SMTP errors

### Issue: Form validation errors
- Open browser console for detailed errors
- Check network tab for API response
- Verify all required fields are filled
- Check file size < 5MB

### Issue: Database errors
- Run: `supabase db reset` to reapply migrations
- Check migration applied: `supabase migration list`
- View database: `supabase dashboard` → Database

## Next Steps (Future Enhancements)
1. Build admin panel career review interface
2. Add SMS notifications for interview scheduling
3. Add application tracking for applicants (login to view status)
4. Add resume parsing (extract details automatically)
5. Add interview feedback forms
6. Add bulk actions (reject multiple, export selected)
7. Add analytics dashboard (applications by month, source, etc.)
8. Add automated screening based on qualifications
9. Add video interview integration
10. Add employee referral tracking
