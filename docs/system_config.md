# System Configuration

This document outlines the system configuration keys that are required to be present in the `system_config` table for the backend to function properly.

These keys represent values that we query dynamically, rather than hardcoding them in `.env` files. Ensure these exist in your database and are marked as `is_active = true`.

## Financial & Fee Configurations

| Key | Type | Description |
| --- | --- | --- |
| `registration_fee_amount` | string/number | The one-time registration fee charged to vendors when joining the platform. Used during checkout and approval flows. |
| `convenience_fee_percentage` | string/number | The additional platform fee percentage charged to the customer at booking checkout. |

## Third-Party Aggregation & Booking Rules

| Key | Type | Description |
| --- | --- | --- |
| `razorpay_key_id` | string | Used to initialize the Razorpay SDK to generate orders. |
| `razorpay_key_secret` | string | Used to validate signatures on incoming Razorpay payments. Changes take effect immediately on the next payment request. |
| `max_booking_advance_days` | string/number | Public configuration limits how many days in advance a user can book a service. |
| `cancellation_window_hours` | string/number | Public configuration determining the cutoff for allowing cancellations. |

## RM Scoring & Penalty 

| Key | Type | Description |
| --- | --- | --- |
| `rm_score_per_approval` | string/number | Points awarded to an RM when a joined vendor is approved. |
| `rm_score_penalty_rejection` | string/number | Points deducted from an RM's performance score when an admin rejects a vendor they onboarded. |


