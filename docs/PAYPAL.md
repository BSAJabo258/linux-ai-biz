# PayPal: the business's payments

Your PayPal business account is BAU's way to get paid for everything except the creator's
Fanvue content: invoices, checkout links, refunds, paying people, and each payment counted
in the books once. Every fact below was read on PayPal's own pages on 2026-11-24.

## What it does

| You want to | Command | Who |
|---|---|---|
| Bill someone | `bau paypal invoice their@email.com --item "Clip edit=25" --send` | you (`--send` emails it) |
| See your invoices | `bau paypal invoices` (or `--status PAID`) | anyone |
| Mark an invoice paid in cash or check | `bau paypal invoice-paid INVOICE-ID 25 --method CHECK` | you |
| Cancel a sent invoice | `bau paypal invoice-cancel INVOICE-ID` | you |
| A payment link for one amount | `bau paypal checkout 25 --description "Clip edit"` | BAU |
| Take the money once the buyer approved | `bau paypal capture ORDER-ID` | BAU |
| Give money back | `bau paypal prepare-refund CAPTURE-ID` then `bau paypal send FILE --approval SIG` | you sign |
| Pay someone | `bau paypal prepare-payout them@email.com 40` then `bau paypal send FILE --approval SIG` | you sign |
| Count payments in the books | `bau paypal sync` (Jarvis's money tool does it once an hour) | BAU |

**Money going out needs your signature.** A refund or payout is first written to a request
file. You read it, sign exactly that file, and send it:

```
bau approve --capability move.money --request-id THE-ID --requester bau \
  --bind THE-FILE --out THE-FILE.sig.json
bau paypal send THE-FILE --approval THE-FILE.sig.json
```

Change one character of the file and the signature no longer fits. Each request is sent once:
its id is PayPal's own "send this only once" key.

**The books.** `bau paypal sync` reads PayPal's transaction report and writes each settled
payment into `economics/revenue.jsonl` once, with PayPal's fee. Refunds, reversals and
chargebacks are counted back out. Pending payments wait until they settle, and money moved to
your bank is not counted as a sale. PayPal lists a payment up to three hours after it happens.

**Not for adult content.** PayPal's Acceptable Use Policy (updated November 4, 2026) bars
"certain sexually oriented materials or services", and adult content delivered digitally needs
PayPal's approval first. Her Fanvue content is paid on Fanvue. BAU refuses an invoice or
checkout whose words name adult content.

**No open door.** PayPal never calls your computer. BAU asks PayPal for the status instead, so
no port is opened.

## Set it up

### 1. Sandbox first (play money)

1. Sign in on **developer.paypal.com** with your PayPal business login.
2. **Apps & Credentials**, the **Sandbox** tab: open the default app (or create one) and copy
   its **Client ID** and **Secret**.
3. **Testing Tools → Sandbox Accounts**: PayPal made two for you, a personal (buyer) and a
   business (seller). Note the personal account's email and password.
4. On the laptop:
   ```
   sudo bau keys set PAYPAL_SANDBOX_CLIENT_ID PAYPAL_SANDBOX_CLIENT_SECRET
   bau paypal check
   ```
   `connected: true` only appears when PayPal really answered the three requests.

### 2. Test every method

```
bau paypal test --buyer THE-SANDBOX-PERSONAL-EMAIL
```

Each line says PASS or FAIL. It makes three invoices: it reads one and deletes it, sends one
and records a payment on it, and sends one and cancels it. Then it makes a checkout and gives
you its approve link. Open the link, sign in as the sandbox **personal** account, approve,
then:

```
bau paypal test --buyer THE-SANDBOX-PERSONAL-EMAIL --order THE-ORDER-ID
```

That takes the payment, reads it, refunds it in full, pays $1.00 out to the sandbox buyer and
reads the transaction report. It is all play money. If the payout line fails, the sandbox
business account does not have Payouts switched on yet: the error says so.

### 3. Live

When every line passes:

1. On developer.paypal.com, the **Live** tab of Apps & Credentials: copy that app's Client ID
   and Secret.
2. ```
   sudo bau keys set PAYPAL_CLIENT_ID PAYPAL_CLIENT_SECRET
   bau paypal mode live
   bau paypal check
   ```

`bau paypal status` says which mode you are on and whether the last check connected. Payouts
on a live account work only after PayPal enables Payouts for it; PayPal decides that, not BAU.

## Good to know

- Sandbox and live use different keys. `bau paypal mode sandbox` goes back to play money.
- A request file made in the sandbox cannot be sent live, and the other way round.
- Facts and their pages: the top of `src/bau/paypal.py` and `examples/platform-paypal.yaml`.
