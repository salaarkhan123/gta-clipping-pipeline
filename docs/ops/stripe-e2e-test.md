# Stripe end-to-end payment test

This runbook tests the whole payment path with real money, at the smallest spend: one credit pack and one month of
Starter, both refunded. It proves five things:

- A purchase grants credits once.
- A resent webhook grants nothing more.
- A refund takes the credits back.
- A cancellation ends the plan.
- The ledger has exactly the rows listed in [Expected ledger rows](#expected-ledger-rows).

Do the test-mode rehearsal first. Do the live run only after it passes.

**Cost.** Refunds return the payment but not Stripe's processing fee (US cards: 2.9% + $0.30). The live run costs
about $1.20 in fees: about $0.44 on the $4.99 pack and $0.76 on the $15.99 Starter month.

**Which code.** This runbook is for the release that contains staging PRs #135 (plans `starter_v2` and the
others, with Stripe Price IDs) and #136, plus the Stripe validation PR. Production runs `main` at `dfbd2a6`
(legacy plans from `PLANS`) until that release is deployed. If you run the live test before then:

- The Starter plan is the legacy `starter`. Its price and credits come from `PLANS`, so read them from
  `GET /v1/billing/plans`.
- `scripts/admin.py stripe-check` does not exist yet. Skip that step.
- Do not resend `checkout.session.completed` for a subscription after you cancel it. On `dfbd2a6` a late copy of
  that event puts the account back on the plan. The validation PR fixes this.

## Values used below

| Name | Value |
|---|---|
| API | `https://api.clutchclips.io` (test mode: your staging or local API) |
| Webhook endpoint | `https://api.clutchclips.io/webhooks/stripe`, 8 events (see [Events](#events-and-handlers)) |
| Test account | a new account used only for this test, for example `ops+stripe-e2e-YYYYMMDD@clutchclips.io` |
| Smallest pack | `pack_300`: 300 credits, $4.99. Check with `curl -s $API/v1/billing/packs`. `CREDIT_PACKS` can change it. |
| Starter monthly | `starter_v2`: 500 credits a month, $15.99. Check with `curl -s $API/v1/billing/plans`. |

Run the commands on the server, from `clip-api/`. Set these once per shell:

```bash
API=https://api.clutchclips.io
E=ops+stripe-e2e-YYYYMMDD@clutchclips.io       # the test account
q() { docker compose exec -T db psql -U clip -d clip -c "$1"; }
ledger() { q "select l.id, l.created_at, l.kind, l.delta, l.idempotency_key, l.note from credit_ledger l
             join accounts a on a.id = l.account_id where a.email = '$E' order by l.id"; }
payments() { q "select p.id, p.kind, p.stripe_ref, p.payment_intent, p.amount_cents, p.credits, p.credits_removed,
               p.status from payments p join accounts a on a.id = p.account_id where a.email = '$E' order by p.id"; }
account() { q "select plan, subscription_status, stripe_customer_id, stripe_subscription_id, subscription_cancel_at
              from accounts where email = '$E'"; }
billing_log() { docker compose logs --since 20m api | grep -E 'clipapi.billing|/webhooks/stripe'; }
```

For the rehearsal on a local stack without Docker, run the same SQL with `psql "$DATABASE_URL"`, and run the
admin commands as `python scripts/admin.py ...` inside `clip-api/`.

## Before you start (both modes)

1. In Stripe, open **Workbench, Webhooks**, then open the endpoint.
   a. Check that the URL is the API's `/webhooks/stripe` and that it lists exactly the 8 events in
      [Events](#events-and-handlers).
   b. Write down the endpoint's **API version** and the account's default API version (Workbench, Overview).
      The handler reads both the older payload shape and the shape used since `2025-03-31.basil`; see
      [API version notes](#api-version-notes).
2. In **Settings, Billing, Customer portal**, check that plan switching is off. Only cancelling and updating
   the card are allowed. The reason is in `clip-api/DEPLOY.md`, "Customer portal": a mid-period plan change
   with proration would grant a full month of credits for part of a payment. Leave **pausing** off too.
3. Check the Stripe settings on the server:

   ```bash
   docker compose exec -T api python scripts/admin.py stripe-check
   ```

   Expected: `key mode: live` (or `test` for the rehearsal), `OK key accepted`, one `OK` line for each of the
   six plan Prices, `OK STRIPE_WEBHOOK_SECRET is set`, then `ALL OK`. The command prints no secret.
4. Check that no job is running, so a restart during the test cannot cut one off:
   `docker compose exec -T api python scripts/admin.py stuck`.
5. Create the test account. It starts with 0 credits (no signup grant), which makes the ledger easy to read:

   ```bash
   docker compose exec -T api python scripts/admin.py create-account "$E" '<a password you keep in your password manager>'
   ```

## Test-mode rehearsal

Rehearse against staging or a local stack that uses Stripe **test mode** keys. Never use live keys here.

1. Put the test-mode values in that stack's environment, not in the production `.env`:
   - `STRIPE_SECRET_KEY` set to an `sk_test_...` or `rk_test_...` key.
   - The six `STRIPE_PRICE_*` IDs of the test-mode Prices (`clip-api/DEPLOY.md`, "Plans and Stripe Prices").
2. For a local stack, forward events with the Stripe CLI. The CLI prints a `whsec_...` value. Set it as
   `STRIPE_WEBHOOK_SECRET` for the local API, then restart the API:

   ```bash
   stripe listen --forward-to http://localhost:8000/webhooks/stripe --events \
     checkout.session.completed,checkout.session.async_payment_succeeded,invoice.paid,invoice.payment_failed,customer.subscription.updated,customer.subscription.deleted,charge.refunded,charge.dispute.created
   ```

   A staging API with its own test-mode webhook endpoint needs no CLI. Use that endpoint's signing secret.
3. Check that Stripe accepts every Checkout Session the API creates. This makes no charge:
   `RUN_STRIPE_LIVE=1 STRIPE_SECRET_KEY=sk_test_... pytest -q tests/test_stripe_live.py`.
4. Do steps 1 to 7 of the live run below, using the test card `4242 4242 4242 4242` (any future date, any CVC).
5. Also try these, which you cannot safely do in live mode:
   - **Dispute.** Buy a second pack with card `4000 0000 0000 0259`. Stripe opens a dispute on the payment, and
     the API takes the pack's credits back (`adjust`, key `stripe-dispute:dp_...`). Payment status: `disputed`.
   - **Renewal and failed renewal.** These need a [test clock](https://docs.stripe.com/billing/testing/test-clocks),
     which works only for a customer created with that clock.
     a. Create the customer with a test clock in the Dashboard.
     b. Set its id as `stripe_customer_id` on a test account, then subscribe with `4242 4242 4242 4242`.
     c. Advance the clock one month. Expected: a second `invoice.paid` and a second `grant +500` with a new
        `stripe-inv:` key.
     d. In the Dashboard, add card `4000 0000 0000 0341` to the customer and make it the default. That card
        attaches but every charge fails.
     e. Advance the clock one more month. Expected: `invoice.payment_failed` sets
        `subscription_status = past_due`, the plan stays, and no credits move.
6. The rehearsal passes when every expected row and state below matches.

## Live run

Use a real card that belongs to the owner. Do the steps in order.

### 1. Buy the smallest pack

1. Sign in to the website as the test account. Open **Pricing** and buy the 300-credit pack.
2. In Stripe, open **Payments**. You see one $4.99 payment, status Succeeded. Write down its `pi_...` id and
   charge id (`ch_...`).
3. In **Workbench, Webhooks, (endpoint), Event deliveries**, `checkout.session.completed` was delivered with
   HTTP 200.
4. In the app:

   ```bash
   docker compose exec -T api python scripts/admin.py balance "$E"     # 300 credits, one topup +300 row
   ledger; payments
   ```

   Expected: one ledger row `topup +300`, key `stripe:cs_...`, note "Purchased 300 credits". One payments row
   `pack`, `stripe_ref = cs_...`, `payment_intent = pi_...`, `credits = 300`, `credits_removed = 0`,
   `status = paid`.

### 2. Subscribe to Starter monthly

1. On the website, open **Pricing**, choose Starter, monthly, and pay $15.99.
2. In Stripe:
   - **Subscriptions** shows one Starter subscription (`sub_...`), Active, at the Starter monthly Price.
   - **Invoices** shows one paid invoice (`in_...`), billing reason "Subscription creation".
   - **Event deliveries** shows `checkout.session.completed`, `invoice.paid` and possibly
     `customer.subscription.updated`, each with HTTP 200, in any order.

### 3. Check the credits once

Credits come from `invoice.paid` only, keyed on the invoice. `checkout.session.completed` for a subscription
grants nothing, so the two events cannot grant twice.

```bash
docker compose exec -T api python scripts/admin.py balance "$E"     # 800 credits
ledger; payments; account
billing_log                                                          # "invoice paid account=... plan=starter_v2 granted=True"
```

Expected:

- A new ledger row `grant +500`, key `stripe-inv:in_...`, note "Starter plan credits".
- A payments row `plan`, `stripe_ref = in_...`, `credits = 500`. On API versions since `2025-03-31.basil`,
  `payment_intent` is empty until a refund fills it.
- The account has `plan = starter_v2`, `subscription_status = active`, `stripe_subscription_id = sub_...`, and
  an empty `subscription_cancel_at`.
- The website billing page shows Starter.

### 4. Resend the webhooks to prove idempotency

1. In **Workbench, Events**, open the `invoice.paid` event from step 2 and click **Resend** to the endpoint.
   Then do the same for the pack's `checkout.session.completed` event from step 1. With the Stripe CLI:
   `stripe events resend evt_... --webhook-endpoint we_... --live`.
2. Both deliveries return HTTP 200.
3. Run `ledger` again. There are no new rows, and the balance is still 800. `billing_log` shows a second
   "invoice paid ... granted=False" line.

Do not resend the subscription's `checkout.session.completed` after step 6 on a release older than the
validation PR (see "Which code" at the top).

### 5. Refund, and check that the credits go back

Refund the pack in two parts. This also tests a partial refund, at no extra cost.

1. In **Payments**, open the $4.99 payment and refund **$2.00**.
   - `charge.refunded` is delivered with HTTP 200.
   - `ledger` shows `adjust -120` (300 × 200 / 499, rounded down), key `stripe-refund:ch_...:200`, note
     "Refund of cs_...". The balance is 680, and the pack payment has `status = partial`, `credits_removed = 120`.
2. Refund the rest of the pack ($2.99).
   - `ledger` shows `adjust -180`, key `stripe-refund:ch_...:499`. The balance is 500, and the pack payment has
     `status = refunded`, `credits_removed = 300`.
3. In **Payments**, open the $15.99 Starter payment and refund all of it.
   - `ledger` shows `adjust -500`, key `stripe-refund:ch_...:1599`, note "Refund of in_...". The balance is 0.
   - The plan payment now has `status = refunded`, `credits_removed = 500`, and its `payment_intent` filled in.
     The API found the invoice through Stripe's Invoice Payments API, so `STRIPE_SECRET_KEY` must be allowed
     to read invoice payments.
   - A refund does not end the subscription: the account is still `starter_v2`, `active`.
   - `billing_log` shows "took back ... credits from account=... for ..." once for each refund.
4. Resend one `charge.refunded` event. There are no new rows.

A refund never takes the balance below zero: credits already spent are written off.

### 6. Cancel

1. In **Subscriptions**, open the Starter subscription, choose **Cancel subscription**, then **Immediately**.
   Choose no refund and no proration, because the invoice is already refunded.
2. `customer.subscription.deleted` is delivered with HTTP 200.
3. `account` shows `plan = free`, `subscription_status = canceled`, an empty `stripe_subscription_id` and an
   empty `subscription_cancel_at`. `ledger` has no new rows: cancelling moves no credits.

Optional, before step 1: cancel at period end from the website's billing portal instead. Expected:
`customer.subscription.updated`, the plan stays `starter_v2`, and `subscription_cancel_at` shows the period end
on the billing page. Then cancel immediately in the Dashboard as above.

### 7. Finish

1. Check that the sums add up: `q "select sum(delta) from credit_ledger l join accounts a on a.id = l.account_id where a.email = '$E'"` returns `0`.
2. Suspend the test account: `docker compose exec -T api python scripts/admin.py suspend "$E"`.
3. Keep the printed output of `ledger`, `payments` and `account` with the release notes. They contain ids, not
   secrets.

## Expected ledger rows

Ledger rows are append-only: a refund adds a row, it never changes one.

| Step | kind | delta | idempotency key | note | balance |
|---|---|---|---|---|---|
| 1. pack paid | `topup` | +300 | `stripe:cs_...` | Purchased 300 credits | 300 |
| 2. Starter invoice paid | `grant` | +500 | `stripe-inv:in_...` | Starter plan credits | 800 |
| 4. resends | none | | | | 800 |
| 5.1 refund $2.00 of the pack | `adjust` | -120 | `stripe-refund:ch_pack:200` | Refund of cs_... | 680 |
| 5.2 refund the rest of the pack | `adjust` | -180 | `stripe-refund:ch_pack:499` | Refund of cs_... | 500 |
| 5.3 refund the Starter invoice | `adjust` | -500 | `stripe-refund:ch_sub:1599` | Refund of in_... | 0 |
| 6. cancel | none | | | | 0 |

For a legacy `starter` subscriber (on `dfbd2a6`), step 2 grants that plan's `monthly_credits` and step 5.3 takes
back the same amount.

Yearly plans (not part of this test) grant one month on `invoice.paid`. The worker's minute sweep grants each
later month, with keys `grant:<sub>:<period start>:<month>`.

## If something does not match

- **A delivery returned 400 `bad_signature`.** `STRIPE_WEBHOOK_SECRET` is not this endpoint's signing secret,
  or the server clock is more than 5 minutes off. Stripe retries for up to 3 days. Fix the secret
  ([credential rotation](credential-rotation.md)), then resend the event.
- **A delivery returned 503.** Either `STRIPE_WEBHOOK_SECRET` is empty, or a refund could not be matched because
  Stripe was unreachable. Stripe retries. Nothing was changed.
- **No credits after `invoice.paid`.** Run `billing_log`.
  - "could not be matched to an account": the invoice has no `account_id` metadata and an unknown customer.
  - "is not for a subscription": it was a one-off invoice.
  - Otherwise, check that the line's Price is one of the six `STRIPE_PRICE_*` values (`stripe-check`).
- **Credits granted twice.** Stop and keep the two ledger rows. That is a bug; open an issue with both
  idempotency keys. Do not delete or edit rows. Correct the balance with
  `admin.py grant "$E" -<n> --note "..."`, which appends an `adjust` row.

## Events and handlers

The live endpoint is subscribed to 8 events. `app/routes_billing.py` handles exactly those 8 and acknowledges
anything else with 200 and no change.

| Event | What the API does |
|---|---|
| `checkout.session.completed` | Pack with `payment_status = paid`: grants the pack's credits from server config (key `stripe:<session>`). Subscription: records the customer, subscription and plan. Grants no credits. |
| `checkout.session.async_payment_succeeded` | Same as above, for bank debits that settle later. Same key, so a pack is never granted twice. |
| `invoice.paid` | Grants the plan's credits for the Price on the invoice: monthly per invoice (`stripe-inv:<invoice>`), yearly one month now and the rest from the worker. Clears `past_due`. Ignores invoices that are not for a subscription. |
| `invoice.payment_failed` | Sets `past_due`. No credits move. |
| `customer.subscription.updated` | Status, plan (from the Price), cancel date. `paused`, `unpaid` and `incomplete` drop to the free plan. `canceled` ends the subscription. Older events never overwrite newer ones. |
| `customer.subscription.deleted` | Free plan, status `canceled`. Yearly grants stop. |
| `charge.refunded` | Takes back the paid credits in proportion to the amount refunded so far, never below zero (`stripe-refund:<charge>:<refunded>`). |
| `charge.dispute.created` | Takes back everything that payment granted (`stripe-dispute:<dispute>`). Yearly grants stop. |

Handled but not subscribed: none. Subscribed but not handled: none.

These events are not subscribed. None is needed today:

- `customer.subscription.created`: `checkout.session.completed` and `customer.subscription.updated` cover it.
- `customer.subscription.paused` and `customer.subscription.resumed`: Stripe also sends
  `customer.subscription.updated` with the new status, which the API handles. Add them only if pausing is
  turned on in the portal (Endive, 2026-10-28) and the updated event turns out not to arrive.
- `checkout.session.async_payment_failed` and `checkout.session.expired`: nothing was granted.
- `charge.dispute.closed`: a dispute you win does not give the credits back automatically. Grant them by hand
  with `admin.py grant`.
- `refund.failed`: a refund that fails after `charge.refunded` leaves the credits taken. This is rare; grant
  them back by hand.

## API version notes

- **Library.** `requirements.txt` pins `stripe==17.0.0`. That library sends API version `2026-10-28.endive` on
  the calls the API makes (Checkout Session create, Price retrieve, billing portal session, Invoice Payments
  list). Before this pin it was `stripe>=10.0`, so each image rebuild could change the API version. Upgrade the
  library in its own PR and run the test-mode rehearsal. To see the version a running container uses:
  `docker compose exec -T api python -c "import stripe; print(stripe.VERSION, stripe.api_version)"`.
- **Webhooks.** Event payloads use the **endpoint's** API version, not the library's. The handler reads both
  shapes:
  - [2025-03-31.basil: invoice `parent`](https://docs.stripe.com/changelog/basil/2025-03-31/adds-new-parent-field-to-invoicing-objects).
    `invoice.subscription` and `invoice.subscription_details` moved to `invoice.parent.subscription_details`.
    Read in `_invoice_subscription` and `_invoice_meta`.
  - [2025-03-31.basil: multiple payments on invoices](https://docs.stripe.com/changelog/basil/2025-03-31/add-support-for-multiple-partial-payments-on-invoices).
    `invoice.payment_intent` and `charge.invoice` were removed. A refund or dispute on a plan invoice is
    matched through `GET /v1/invoice_payments` (`_invoice_of`).
  - [2025-03-31.basil: invoice line pricing](https://docs.stripe.com/changelog/basil/2025-03-31/invoice-pricing-configurations).
    The line's `price` moved to `pricing.price_details.price`. Read in `_price_ids`.
  - [2025-03-31.basil: item-level billing periods](https://docs.stripe.com/changelog/basil/2025-03-31/deprecate-subscription-current-period-start-and-end).
    `subscription.current_period_end` was removed and is now on each item. The validation PR fixed the cancel
    date ("cancel at period end") to read it from the items; before, it could come out empty.
  - [2025-09-30.clover](https://docs.stripe.com/changelog/clover): flexible billing mode became the default
    for new subscriptions, and `discount.coupon` was replaced. The API reads neither.
  - [2026-03-25.dahlia](https://docs.stripe.com/changelog/dahlia): Checkout `ui_mode` values changed. The API
    does not set `ui_mode`.
  - [2026-09-30.endive](https://docs.stripe.com/changelog/endive):
    - `payment_method_types` was removed from Checkout Sessions. The API does not send it.
    - [Pausing subscriptions](https://docs.stripe.com/changelog/endive/2026-09-30/pause-subscription) added the
      `paused` status and `status_details`. The API handles `paused` as no service: free plan, no yearly grants
      until it resumes. It does not read `status_details`.
    - [Automatic pause after payment failures](https://docs.stripe.com/changelog/endive/2026-09-30/pause-on-payment-failure)
      leads to the same `paused` status.
  - [2026-10-28.endive: subscription pausing in the customer portal](https://docs.stripe.com/changelog/endive/2026-10-28/customer-portal-subscription-pausing).
    Keep it off (see [Before you start](#before-you-start-both-modes)) until pausing is tested in test mode.
- **Upgrading the endpoint's API version.** Create a second endpoint at the new version in test mode, run the
  rehearsal, then switch the live endpoint ([Stripe: webhook versioning](https://docs.stripe.com/webhooks/versioning)).
