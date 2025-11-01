# Project Restructuring Plan

## Executive Summary
Complete restructuring of Salon Management & Hiring Platform with 4 distinct roles:
- **Admin**: Full system control, approvals, fee management
- **Relationship Manager (RM)**: Add salon/spa details, earn scores
- **Vendor**: Manage own salon/spa services and bookings
- **Customer**: Browse and book services

## Key Clarifications Received
1. ✅ Registration fee amount is dynamic (set by admin)
2. ✅ Convenience fee is dynamic (set by admin)
3. ✅ RM scoring system is dynamic (set by admin)
4. ✅ Payment gateway: Razorpay
5. ✅ Free services allowed (price = 0)
6. ✅ Vendor can have unlimited staff (practically reasonable limits)
7. ✅ Same person CANNOT be both RM and Vendor
8. ✅ Vendor account created via secure email link after admin approval

## Implementation Phases

### Phase 1: Database Schema (CURRENT)
- Create new comprehensive schema with all tables
- Add role-based access control
- Add payment tracking tables
- Add RM scoring system

### Phase 2: Backend APIs
- Supabase for simple CRUD operations
- Custom backend for complex business logic
- Payment integration with Razorpay

### Phase 3: Admin Panel Migration
- Move from direct Supabase to API-based operations
- Add system configuration management
- Add approval workflows

### Phase 4: Frontend Updates
- Update role-based routing
- Add payment flows
- Add RM portal features

---
**Status**: Starting Phase 1 - Database Schema Creation
**Date**: October 31, 2025
