# Email via Resend — Setup & Cutover

SMTP has been removed from the backend. All application email now goes out over the
Resend HTTP API.

There are **two independent email channels**. Both need to be pointed at Resend, in
two different places. Doing only one is the most common way to end up with "some
emails work, some don't".

| Channel | Sends | Configured where |
|---|---|---|
| **Backend** (`app/services/email.py`) | bookings, vendor approval/rejection, payment reminders, career, reviews, admin alerts | `RESEND_API_KEY` env var on Railway / DigitalOcean |
| **Supabase Auth** | signup confirmation, password reset, email change, magic link | Supabase **Dashboard** → Auth → SMTP Settings (per project) |

---

## 1. Verify the sending domain in Resend

Nothing works until this is done. Resend rejects any `from` address on an
unverified domain with **HTTP 422**.

1. Resend → **Domains** → *Add Domain* → enter your domain (e.g. `lubist.in`).
2. Add the DNS records Resend shows you (SPF `TXT`, DKIM `CNAME`/`TXT`, and the
   DMARC record if offered) at your DNS provider.
3. Wait for the status to flip to **Verified**.

Until then you can only send from `onboarding@resend.dev`, and only to the email
address on your own Resend account.

## 2. Create an API key

Resend → **API Keys** → *Create*. Scope it to **Sending access**. Use a **separate
key for staging and production** so you can revoke one without breaking the other.

## 3. Backend env vars

Set on **Railway (staging)** and **DigitalOcean (production)**:

```
RESEND_API_KEY=re_xxxxxxxxxxxx
EMAIL_FROM=noreply@lubist.in          # must be on the verified domain
EMAIL_FROM_NAME=Lubist
ADMIN_EMAIL=<real admin inbox>        # where admin notifications land
```

The old `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_TLS` /
`SMTP_SSL` vars are no longer read. Deleting them is tidy but not required —
unknown env vars are ignored, so the app will not crash if you leave them.

`RESEND_API_KEY` is **optional** in config. If it is blank the app still boots and
each send logs a warning (`RESEND_API_KEY is not set — email NOT sent to …`)
instead of crashing. That is the intended local-dev behaviour, so you never
accidentally mail real users from a laptop.

## 4. Supabase Auth SMTP (the signup-confirmation channel)

Do this for **staging and production projects separately**:

Supabase Dashboard → **Project Settings → Authentication → SMTP Settings** →
*Enable Custom SMTP*:

| Field | Value |
|---|---|
| Host | `smtp.resend.com` |
| Port | `465` |
| Username | `resend` |
| Password | your Resend API key |
| Sender email | `noreply@lubist.in` (verified domain) |
| Sender name | `Lubist` |

Then go to **Authentication → Rate Limits** and raise **"Emails per hour"**. The
built-in Supabase SMTP is capped at **2 emails/hour**, which silently drops signup
confirmations — a very common cause of "the confirmation email never arrived".

## 5. Verify the cutover

On boot the API logs a line you can check in the deploy logs:

```
Email (Resend): key=configured, from=noreply@lubist.in, admin=<admin inbox>
```

If it says `key=MISSING - sends disabled`, the env var did not reach the app.

Then, end to end:

1. **Backend channel** — submit the public *Partner with us* form. `ADMIN_EMAIL`
   should receive a "New Partner Request" alert.
2. **Supabase channel** — sign up a brand-new customer. The confirmation email
   should arrive.
3. Cross-check both in the **Resend dashboard → Emails**, which shows delivered /
   bounced / complained per message.

Failures are also recorded in-app as `email_failed` activity rows (visible on the
admin dashboard) with the HTTP status and Resend's error text.

---

## Who receives what

| Email | Recipient |
|---|---|
| Booking confirmed / cancelled / review request | Customer |
| New booking / booking cancelled / payment reminder | Vendor |
| Salon approved (registration link) | Vendor owner |
| Salon approved (points earned) / salon rejected | RM |
| Career application received | Applicant |
| **New career application** | **`ADMIN_EMAIL`** |
| **New vendor join request** (RM submitted a salon) | **`ADMIN_EMAIL`** |
| **New partner-with-us lead** | **`ADMIN_EMAIL`** |
| Signup confirmation / password reset | The user (via Supabase Auth) |

## Troubleshooting

| Symptom in logs | Cause |
|---|---|
| `HTTP 422` | `EMAIL_FROM` is not on a domain verified in Resend. Most common failure. |
| `HTTP 401` / `403` | Bad, revoked, or wrong-environment API key. |
| `HTTP 429` | Resend rate limit — retried automatically with backoff. |
| `RESEND_API_KEY is not set` | Env var missing on that deployment. |
| Backend mail fine, signup confirmation missing | Step 4 not done, or Supabase's 2/hour rate limit. |

`422`, `401`, `403`, `400` and `404` are treated as **permanent** and are not
retried — retrying a rejected sender domain just burns quota. Network errors,
`429` and `5xx` are retried up to 3 times with exponential backoff.
