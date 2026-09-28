# Bug batch 1 — what was fixed, and what to retest

Triage of the seven bugs reported on 2026-09-28. Six needed code changes; one did not.
Everything below is on the `dev` branch and needs a deploy before you can retest.

| # | Your report | Verdict | Where it was fixed |
|---|---|---|---|
| 1 | RM phone accepts more than 10 digits | Real | Admin panel + backend + RM profile page |
| 2 | Password still filled in after logout | **Not a bug** | — (see below) |
| 3 | Pincode not verified when creating a salon | Real | RM salon form now verifies against India Post |
| 4 | Salon can be created with the RM's own email | Real | Refused at submission and at approval |
| 5 | Two salons on one email fail late | Real | Same fix as #4 |
| 6 | Two salons on one email/phone should be blocked | Real | Same fix as #4 |
| 7 | "Complete Registration" link in the approval email 404s | Real | Link is now built so it cannot miss the page |

## #2 is not a bug — please don't re-file it

Neither app ever stores your password. Two separate things are happening:

- **The email** comes back because you ticked **"Remember me"**, which saves the email
  address (only the address) on purpose.
- **The password** is filled in by **your browser's own password manager**, which offers
  to save logins for any site.

To confirm: open the RM portal in a private/incognito window, log in, log out. The
password box will be empty. Logging out does properly end the session — that part was
checked.

## What to retest once this is deployed

**#1 — phone length.** In the admin panel, Users → Create User (role: Relationship
Manager). The phone box now refuses an 11th digit as you type, and a short or malformed
number is rejected on save with a message. Same on Edit User, and on the RM's own
Profile page. Numbers are stored as `+919876543210`, so the list may show that form —
that is correct, not a bug.

**#3 — pincode.** RM portal → Add New Salon → Basic Info. Type a full 6-digit pincode:

- A real PIN (e.g. `400001`) fills in City and State and shows "Mumbai, Maharashtra".
- A fake PIN (e.g. `999999`) is rejected — you cannot move to the next step.
- A city that doesn't match the PIN shows an amber warning but still lets you continue.
  This is deliberate: India Post's district name isn't always what a local would call
  the city, so it must not block a correct submission.
- If the pincode check can't reach India Post, it says so quietly and lets you carry on.
  Also deliberate — a third-party outage must not stop onboarding.
- A 7th digit can no longer be typed, and the backend now refuses anything but 6 digits
  (it used to accept a 10-digit "pincode" as well).

**#4, #5, #6 — one owner, one salon.** The rule is now:

- The **owner email** is refused if it already belongs to *any* account (including the
  RM's own login) or to another draft/pending/approved submission.
- The **owner phone** is refused if another draft/pending/approved submission uses it.
- A **rejected** submission does not block anything — an RM can resubmit the same owner
  after a rejection. Please check this case too.
- The error appears immediately on submit, names the clash ("… is already used by an
  approved salon, \"First Salon\""), and highlights the field.
- Admin side: approving such a request is refused with the same explanation, instead of
  creating a salon nobody can register.

**#7 — the approval email link.** Approve a salon and click "Complete Registration" in
the email. It must land on the registration form with the owner's email shown. The link
now always includes the `/vendor` segment, whatever the server is configured with.

## One thing to check with the team, not with us

Salons approved **before** this fix may already be stranded: created under an email that
already had an account, with no usable registration link. Admin → Salons → row menu →
**Resend Approval Email** is the recovery path for those, but if the owner email is
genuinely taken, the salon needs resubmitting under a different owner email.
