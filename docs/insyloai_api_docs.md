# WhatsApp API reference — Insylo AI for developers | insylo ai
API reference

WhatsApp API
------------

Send and receive WhatsApp messages from your own website or app. You keep your product; Insylo handles the WhatsApp Business Platform, template approvals, delivery receipts and billing.

Base URL `https://www.insyloai.com`Auth `Bearer isk_live_…`

Quick start
-----------

Three steps from zero to a delivered message.

1.  **1.** The account owner creates a key in **Dashboard → Settings → API & webhooks**.
2.  **2.** Call `GET /api/v1/templates` to see what you're allowed to send.
3.  **3.** `POST /api/v1/messages` with one of those template names.

bash

```
curl https://www.insyloai.com/api/v1/templates \
  -H "Authorization: Bearer isk_live_XXXX"
```


Authentication
--------------

Every request needs an `Authorization: Bearer` header. Keys start with `isk_live_` and are scoped to one business — a key can never read or send on behalf of another account.

http

```
Authorization: Bearer isk_live_XXXX
```


The key is shown **exactly once**, at creation. We store only its SHA-256 hash, so it cannot be recovered — if it's lost, revoke it and mint another. Keep it server-side: never in browser JavaScript, a mobile app bundle, or a git repo. Use a separate key per environment so revoking staging doesn't take production down. Revocation takes effect immediately.

The 24-hour rule
----------------

This is WhatsApp's rule, not ours, and it decides which request you make. It is the single most common source of confusion when integrating.


|Situation                                    |What you may send                            |
|---------------------------------------------|---------------------------------------------|
|Customer messaged you in the last 24 hours   |Anything — text, images, buttons, lists, CTAs|
|Otherwise (you are starting the conversation)|Only a pre-approved template                 |


Send free-form outside the window and you get `409 outside_service_window` telling you to use a template. We never drop a message silently.

List your templates
-------------------

GET`/api/v1/templates`

Templates are approved by Meta before they can be sent. This returns the ones this account can actually use. Add `?status=all` to include drafts and rejected ones.

json

```
{
  "templates": [
    {
      "name": "order_shipped",
      "language": "en",
      "category": "utility",
      "status": "approved",
      "variables": 2,
      "body": "Hi {{1}}, your order {{2}} has shipped."
    }
  ]
}
```


`variables` is how many values you must pass, in order. Passing the wrong number is what produces Meta's unhelpful `#132000` parameter error — read the count from here instead of guessing.

Send a message
--------------

POST`/api/v1/messages`

`to` is a phone number including country code; the `+` is optional. On success you get `201` with the message id.

bash

```
curl -X POST https://www.insyloai.com/api/v1/messages \
  -H "Authorization: Bearer isk_live_XXXX" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: order-1042-shipped" \
  -d '{
    "to": "919812345678",
    "type": "template",
    "category": "utility",
    "template": {
      "name": "order_shipped",
      "language": "en",
      "variables": ["Priya", "#1042"]
    }
  }'

→ 201 { "ok": true, "message_id": "wamid.HBgM…" }
```


**Always send an `Idempotency-Key`.** Messages cost money. If your request times out and you retry with the same key, we replay the original result instead of sending and billing twice. Replayed responses carry `Idempotent-Replay: true`. Use something derived from your own domain, like `order-1042-shipped`.

`category` must match how the template was approved — `utility`, `marketing`,

`authentication` or `service`. It drives billing, so the wrong value costs real money. Defaults to `utility`.

Message types
-------------

All take `to` plus a `type`. Only `template` can open a conversation; everything else needs an open 24-hour window.

jsonc

```
// Any time
{ "type": "template", "template": { "name": "order_shipped",
                                    "language": "en",
                                    "variables": ["Priya", "#1042"] } }

// Inside the 24h window only
{ "type": "text",     "text": "Your order is out for delivery." }

{ "type": "image",    "media": { "url": "https://…/photo.jpg",
                                 "caption": "New arrivals" } }

{ "type": "document", "media": { "url": "https://…/invoice.pdf",
                                 "filename": "invoice.pdf" } }

{ "type": "buttons",  "body": "Did this solve your problem?",
                      "buttons": [ { "id": "yes", "title": "Yes" },
                                   { "id": "no",  "title": "No"  } ] }

{ "type": "list",     "body": "Pick a slot",
                      "button_text": "Choose",
                      "sections": [ { "title": "Today",
                                      "rows": [ { "id": "s1",
                                                  "title": "4–5 pm",
                                                  "description": "2 left" } ] } ] }

{ "type": "cta",      "body": "Track your order",
                      "cta": { "text": "Track",
                               "url": "https://shop.com/t/1042" } }

{ "type": "location", "location": { "lat": 28.61, "lng": 77.20,
                                    "name": "Store",
                                    "address": "Connaught Place" } }
```


*   **buttons** — max 3; titles are truncated by WhatsApp around 20 characters.
*   **list** — WhatsApp allows **10 rows in total across all sections**, not 10 per section. We enforce a shared budget so you get a usable list instead of Meta's `#131009`.
*   **media** — URLs must be publicly reachable over HTTPS; we hand the URL to Meta rather than uploading bytes.

Message status
--------------

GET`/api/v1/messages/{message_id}`

Look up anything you sent, using the id we returned. Use this to reconcile after a missed webhook, so our callbacks aren't your only source of truth.

json

```
{
  "message_id": "wamid.HBgM…",
  "direction": "outbound",
  "status": "delivered",
  "template": "order_shipped",
  "body": null,
  "error": null,
  "created_at": "2026-08-31T09:12:44Z"
}
```


Webhooks
--------

Without these the API is write-only: you could send, but never learn that a message was delivered or that a customer replied. Set an `https` endpoint and copy the signing secret in **Settings → API & webhooks**.


|Event              |Fires when                                             |
|-------------------|-------------------------------------------------------|
|message.status     |A sent / delivered / read / failed receipt arrives     |
|message.received   |A customer sends you a message                         |
|flow.submitted     |A customer completes a WhatsApp Flow (answers included)|
|broadcast.completed|A bulk batch finishes draining, with final counts      |


json

```
{
  "event": "message.received",
  "created_at": "2026-08-31T09:13:02Z",
  "data": {
    "message_id": "wamid.…",
    "from": "919812345678",
    "name": "Priya",
    "text": "where is my order?",
    "type": "text",
    "conversation_id": "…",
    "intent": "order_status"
  }
}
```


### Verifying the signature — required

Every request carries `X-Insylo-Signature: sha256=<hmac>`, an HMAC-SHA256 of the _raw_ body keyed with your secret. Verify it against the raw bytes **before parsing JSON** — otherwise anyone who discovers your URL can forge events.

javascript

```
const crypto = require("crypto");

app.post("/insylo/webhook",
  express.raw({ type: "application/json" }),   // raw body, not express.json()
  (req, res) => {
    const expected = "sha256=" + crypto
      .createHmac("sha256", process.env.INSYLO_WEBHOOK_SECRET)
      .update(req.body, "utf8")
      .digest("hex");

    const a = Buffer.from(expected);
    const b = Buffer.from(req.get("X-Insylo-Signature") || "");
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
      return res.sendStatus(401);
    }

    res.sendStatus(200);                        // ack fast…
    handle(JSON.parse(req.body.toString()));    // …then do the slow work
  });
```


*   **Return 2xx quickly.** Anything else counts as a failed delivery.
*   **Be idempotent** — key off `data.message_id`. An event may be redelivered.
*   Every attempt is logged on our side, so a missing callback can be answered with evidence.

Bulk sending
------------

POST`/api/v1/messages/bulk`

One template to many recipients — up to **5,000 per batch**. Templates only, since bulk sending is by definition business-initiated.

json

```
{
  "template": { "name": "diwali_offer", "language": "en" },
  "category": "marketing",
  "throttle_per_minute": 60,
  "recipients": [
    { "to": "919812345678", "variables": ["Priya"] },
    { "to": "919812345679", "variables": ["Amit"],
      "header": { "kind": "image", "link": "https://…/banner.jpg" } }
  ]
}
```


This **queues and returns immediately** — it does not send inline. You get

`202` with a `batch_id`; the send drains in the background under your throttle. Poll the status URL for progress.

json

```
→ 202 {
  "ok": true,
  "batch_id": "…",
  "status": "queued",
  "requested": 2,
  "enqueued": 2,
  "duplicates": 0,
  "invalid": 0,
  "invalid_recipients": [],
  "throttle_per_minute": 60,
  "estimated_minutes": 1,
  "status_url": "/api/v1/messages/bulk/…"
}
```


### Track and cancel a batch

GET`/api/v1/messages/bulk/{batch_id}`

GET`/api/v1/messages/bulk/{batch_id}?failures=1`

DELETE`/api/v1/messages/bulk/{batch_id}`

json

```
{
  "status": "sending",
  "counts": { "pending": 120, "in_flight": 4, "sent": 876,
              "failed": 3, "skipped": 11, "cancelled": 0 },
  "estimated_minutes_remaining": 2
}
```


Duplicates inside one batch are collapsed automatically. `?failures=1` returns the per-recipient reason for anything failed or skipped. `DELETE` cancels whatever is still queued.

`sent` means **accepted by WhatsApp**, not delivered — delivery and read receipts arrive later via `message.status`. And only send `marketing` to recipients who opted in: unsolicited marketing downgrades the number's quality rating and eventually gets it blocked by Meta. That is the fastest way to lose a WhatsApp number.

Journeys — multi-step sequences
-------------------------------

A journey is an automation the merchant builds once in the dashboard: send now, wait 24 hours, send a reminder, stop if the customer cancels. Starting one from your system means you don't build a scheduler, store due-dates or run your own cron — you make **one call at the moment the event happens** and we handle the timing, quiet hours and frequency caps.

GET`/api/v1/journeys`

Lists the account's automations so you can find the id to trigger. `triggerable` is true only when a journey is both `active` and set to the `API` trigger.

json

```
{
  "journeys": [
    { "id": "…", "name": "Booking reminders", "status": "active",
      "trigger": "api", "steps": 3, "triggerable": true,
      "entered": 412, "sent": 1180 }
  ]
}
```


POST`/api/v1/journeys/{id}/trigger`

Enrols one customer. Anything in `context` is available to the journey's steps, so a later reminder can quote the booking back to the customer.

bash

```
curl -X POST https://www.insyloai.com/api/v1/journeys/JOURNEY_ID/trigger \
  -H "Authorization: Bearer isk_live_XXXX" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: booking-8842" \
  -d '{
    "to": "919812345678",
    "name": "Priya",
    "context": { "booking_id": "8842",
                 "service": "Hair spa",
                 "salon": "Glow Salon",
                 "time": "Sat 12 Aug, 4:00 PM" }
  }'

→ 202 { "ok": true, "enrolled": true, "enrollment_id": "…",
        "journey": { "id": "…", "name": "Booking reminders", "steps": 3 } }
```


The contact is created automatically if they're new, so a first-time customer still gets the sequence. A `200` with `enrolled: false` means the journey's own re-entry or frequency-cap rules declined — that is the cap working, not an error, so don't retry it. `409` tells you the journey is paused or isn't set to the API trigger.

Use the booking or order id as the `Idempotency-Key`. Enrolling twice runs the whole sequence twice, so this matters even more here than on a single send.

Errors
------

Errors always carry a human-readable `message` alongside the machine-readable `error`. Log it — it usually names the exact fix.


|Status|error                 |Meaning                                             |
|------|----------------------|----------------------------------------------------|
|400   |bad_request           |Malformed body or missing field — message says which|
|401   |unauthorized          |Missing, invalid or revoked key                     |
|402   |insufficient_wallet   |Wallet balance too low — top up to resume sending   |
|409   |outside_service_window|No open 24h window — send a template instead        |
|409   |not_connected         |No WhatsApp number connected to this account        |
|409   |blocked_*             |Blocked by consent / opt-out rules                  |
|429   |rate_limited          |Over the per-key limit — back off and retry         |
|502   |send_failed           |Meta rejected it; message carries the real reason   |


Retry `429` and `5xx` with exponential backoff. Never blindly retry `400`, `402` or `409` — they will fail identically until something changes.

Rate limits
-----------

**600 requests per minute per key.** Over that you get `429 rate_limited`. The cap exists so a runaway loop can't drain the wallet or damage the number's quality rating. For anything high-volume use the bulk endpoint, which is queued and throttled for you.

Go-live checklist
-----------------

1.  1A WhatsApp number is connected and approved on the account.
2.  2The templates you depend on are approved — check GET /api/v1/templates.
3.  3Wallet is funded; sends fail with 402 at zero balance.
4.  4Key is stored server-side only, with separate keys per environment.
5.  5Webhook URL is set, the signature is verified, and the handler is fast and idempotent.
6.  6Every send carries an Idempotency-Key.
7.  7Retries use backoff on 429/5xx and never repeat 400/402/409 unchanged.

Need a number, or stuck on approvals?

Template review and number onboarding are handled by our team.

[Talk to us](https://www.insyloai.com/contact-sales)