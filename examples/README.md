# Example inputs

Templates for the main gates. Copy and adapt them, then run them yourself:

```bash
bau email preflight --message examples/email-message.json \
    --recipients examples/email-recipients.json --sender examples/email-sender.json
bau subscription examples/subscription-offer.json --country US --region CA
bau disclosure examples/ai-video-artifact.json --context examples/ai-video-context.json
```

On a fresh install, expect REVIEW rather than PASS:
- No regulation has been signed off by counsel yet.
- The FCC wireless list has not been imported.
- No consent has been recorded for the example addresses.

The output lists exactly which gate stopped each recipient and why.
