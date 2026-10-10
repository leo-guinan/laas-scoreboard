# LAAS experiment scoreboard

A zero-build, static scoreboard for `laas_three_way_v1`.

It compares three landing-page termination points:

- `essay` — essay.leoasaservice.com
- `jay` — jay.leoasaservice.com
- `sales` — www.leoasaservice.com

The dashboard aggregates a small appendable list of `leafNodes` from `data/scoreboard.json`. Each leaf node is one video, LinkedIn/X post, or other network entry point.

## Data contract

Each leaf node can contain:

```json
{
  "id": "video-01",
  "title": "Video title",
  "kind": "youtube_video",
  "source": "YouTube",
  "publishedAt": "2026-10-09T14:00:00Z",
  "variant": "essay",
  "traffic": 0,
  "ctaClicks": 0,
  "bookings": 0,
  "paidConversions": 0,
  "revenue": 0
}
```

Use Fathom for traffic and CTA counts. Reconcile paid conversions and revenue independently from Stripe succeeded PaymentIntents. The updater only assigns a payment to a variant when Stripe metadata contains the declared experiment and variant; otherwise it remains unattributed. Do not put API keys in this repository.

## Starting the experiment

1. Set `experiment.startAt` to the agreed ISO timestamp when traffic begins.
2. Add the 14 video nodes and 21 LinkedIn/X post nodes to `leafNodes`.
3. Update counts from reconciled source exports.
4. Commit and deploy the JSON update.

The initial data file intentionally says `UNMEASURED` and `NOT_STARTED`. It contains no invented traffic or revenue.

## Scheduled updater

`.github/workflows/update.yml` runs every 15 minutes and can also be started manually. It calls the Fathom aggregation API for the shared site `XERIAWTA`, reads succeeded Stripe PaymentIntents, joins payments using `experiment=laas_three_way_v1` and `landing_variant`, and commits the resulting aggregate metrics back to `data/scoreboard.json`.

The repository secrets are:

- `FATHOM_API_KEY` — the protected Fathom key file value; pipe-delimited values are parsed safely.
- `STRIPE_SECRET_KEY` — the protected Stripe server-side key.

The updater does nothing except mark the data as not started until `experiment.startAt` is set. It does not infer a variant from a payment that lacks explicit attribution.

## GitHub Pages

The included workflow deploys the repository root to GitHub Pages. Configure the custom domain as `dashboard.leoasaservice.com` in repository Pages settings and add the DNS record at the domain provider.
