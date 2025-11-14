# Career Applications - Admin Panel Integration

## Overview
The Career Applications system is now fully integrated into the Salon Admin Panel, allowing administrators to view, manage, and update job applications for RM positions.

## Features Implemented

### 1. **Career Applications Page** (`/career-applications`)

#### View Features:
- **Applications Table**: Displays all career applications with key details
- **Filtering**: Filter by status (pending, under_review, shortlisted, etc.)
- **Statistics Cards**: Quick overview of total, pending, shortlisted, and hired applications
- **Real-time Updates**: Automatic refresh capability

#### Application Details:
- **Personal Information**: Name, email, phone, address, relocation preference
- **Job Details**: Position, experience, previous company, salary expectations, notice period
- **Education**: Qualification, university, graduation year
- **Documents**: Download links for all uploaded documents (Resume, Aadhaar, PAN, Photo, etc.)
- **Additional Info**: Cover letter, LinkedIn, portfolio URLs
- **Review Info**: Admin notes and rejection reasons

#### Status Management:
- Update application status through modal
- Status options:
  - Pending
  - Under Review
  - Shortlisted
  - Interview Scheduled (with date/time and location)
  - Rejected (with reason)
  - Hired
- Add admin notes to applications
- Schedule interviews with location details

### 2. **Backend Integration**

#### RTK Query API (`careerApi.js`):
```javascript
// Available hooks:
useGetCareerApplicationsQuery({ status, position, skip, limit })
useGetCareerApplicationQuery(applicationId)
useUpdateCareerApplicationMutation()
useLazyGetDocumentDownloadUrlQuery()
```

#### Endpoints:
- `GET /careers/applications` - List applications with filters
- `GET /careers/applications/:id` - Get single application
- `PATCH /careers/applications/:id` - Update application status
- `GET /careers/applications/:id/download/:type` - Get document download URL

### 3. **Navigation**

#### Sidebar Menu:
- Added "Career Applications" menu item
- Icon: Briefcase
- Location: Between "Appointments" and "Services"

#### Route:
- Path: `/career-applications`
- Protected: Yes (requires authentication)
- Layout: MainLayout

## Files Modified/Created

### New Files:
1. `salon-admin-panel/src/pages/CareerApplications.jsx` (660+ lines)
   - Main page component with table, modals, and stats
   
2. `salon-admin-panel/src/services/api/careerApi.js` (60 lines)
   - RTK Query API slice for career endpoints

### Modified Files:
1. `salon-admin-panel/src/store/store.js`
   - Registered careerApi reducer and middleware

2. `salon-admin-panel/src/App.jsx`
   - Added lazy-loaded CareerApplications route

3. `salon-admin-panel/src/components/layout/Sidebar.jsx`
   - Added "Career Applications" navigation item

## Usage

### Viewing Applications:
1. Navigate to "Career Applications" from sidebar
2. Use status filter to narrow down results
3. Click "View" to see full application details
4. Click "Download" icons to download documents

### Updating Status:
1. Click "Update" button on any application
2. Select new status from dropdown
3. Add admin notes (optional)
4. For rejection: Add rejection reason (required)
5. For interview: Add date/time and location
6. Click "Update Status"

### Document Management:
- All documents use signed URLs for secure downloads
- Documents expire after 1 hour (configurable)
- Click document button to open in new tab

## Status Colors:
- **Pending**: Yellow/Orange
- **Under Review**: Blue
- **Shortlisted**: Green
- **Interview Scheduled**: Purple
- **Rejected**: Red
- **Hired**: Emerald

## Next Steps (Optional Enhancements):

### High Priority:
- [ ] Add career stats to main Dashboard
- [ ] Real-time notifications for new applications
- [ ] Email notifications when status changes

### Medium Priority:
- [ ] Search by name/email
- [ ] Export applications to CSV
- [ ] Bulk status updates
- [ ] Document preview (PDF viewer)

### Low Priority:
- [ ] Application timeline (status change history)
- [ ] Interview calendar view
- [ ] Applicant communication system
- [ ] Resume parsing/AI screening

## Testing Checklist:

### Basic Functionality:
- [x] Page loads without errors
- [ ] Applications display correctly
- [ ] Status filter works
- [ ] View details modal opens
- [ ] Update status modal works
- [ ] Document downloads work

### Edge Cases:
- [ ] No applications scenario
- [ ] Large number of applications
- [ ] Network error handling
- [ ] Invalid document type
- [ ] Expired signed URLs

### Integration:
- [ ] RTK Query cache invalidation
- [ ] Toast notifications
- [ ] Navigation between pages
- [ ] Logout maintains state

## API Response Examples:

### Get Applications:
```json
{
  "applications": [
    {
      "id": "uuid",
      "full_name": "John Doe",
      "email": "john@example.com",
      "phone": "+919876543210",
      "position": "Relationship Manager",
      "experience_years": 5,
      "current_city": "Mumbai",
      "status": "pending",
      "created_at": "2024-01-15T10:30:00Z",
      "resume_url": "https://...",
      "aadhaar_url": "https://...",
      "pan_url": "https://...",
      ...
    }
  ],
  "total": 25,
  "page": 1,
  "total_pages": 3
}
```

### Update Status:
```json
{
  "status": "shortlisted",
  "admin_notes": "Good candidate, schedule interview",
  "interview_scheduled_at": "2024-01-20T14:00:00Z",
  "interview_location": "Mumbai Office, 3rd Floor"
}
```

## Error Handling:

The application handles these error scenarios:
- Network failures (RTK Query auto-retry)
- Invalid application ID (404 error)
- Permission denied (401/403)
- Document not found
- Signed URL expiration

All errors show toast notifications to the user.

## Performance Considerations:

- **Lazy Loading**: Page component is lazy loaded
- **Cache Management**: RTK Query caches responses
- **Optimistic Updates**: Status changes are optimistic
- **Pagination**: Backend supports pagination (not yet implemented in UI)

## Security:

- All routes protected with authentication
- Document downloads use signed URLs (expiring)
- Sensitive data (Aadhaar, PAN) only accessible to admins
- Status updates logged (future enhancement)

---

**Status**: ✅ Fully Implemented and Ready for Testing
**Last Updated**: 2024
**Documentation**: This file
