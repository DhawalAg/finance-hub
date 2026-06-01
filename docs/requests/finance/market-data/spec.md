# Finance Market Data — Working Spec

**Status:** Scaffold — migration and sharpening pending
**Updated:** 2026-05-31

This is the durable destination for the shared market-data contract. The existing working scaffold,
decision history, and provider comparison remain in:

- [`data-pipeline-spec.md`](../../../../notes/finance-corpus/00-inbox/data-pipeline-spec.md)
- [`data-pipeline-answers.md`](../../../../notes/finance-corpus/00-inbox/data-pipeline-answers.md)
- [`data-source-comparison.md`](../../../../notes/finance-corpus/00-inbox/data-source-comparison.md)

## Responsibility

This spec will define the narrow shared subsystem that:

- supplies grounded current prices to the deployment planner;
- persists price history and computed metrics when activated;
- exposes provider seams so vendor decisions remain reversible;
- supports research quantitative fields without making research depend on paid providers;
- supplies `fin_price_bars` to a later analytics slice for event-response metrics / simulations when
  [research event occurrences](../research/spec.md) are active;
- owns provider-specific operational logging and retry policy when each provider is activated.

The first implementation slice remains intentionally narrow: current prices behind a
`PriceProvider` seam with an explicit override path. Broader quantitative layers stay trigger-gated.
Event-response analytics remain deferred: the research layer stores event occurrences, this layer
stores price bars, and a later analytics slice joins them with trading-session-aware logic.

## Provider Activation Ownership

Consumer specs declare the grounded data they need. This market-data layer owns provider adapters,
configuration, secrets, caching, retries, and operational logging. Planner and research behavior read
stable provider seams rather than vendor-specific APIs.

Start with a free `PriceProvider`. Revisit the implementation when scheduled snapshot errors or empty
results exceed approximately 10% over a rolling two-week window, or when reporting / analytics needs
justify cleaner historical coverage earlier. Add other providers only when a named workflow fires a
trigger recorded in the [research provider-activation block](../research/spec.md): repeatable
filing-grounded extraction, earnings-calendar automation, analyst estimates, intraday backtesting,
real-time news / sentiment, or filing surveillance at scale.

Before activating an adapter, sharpen its current API shape and commercial terms, then define any
schema enrichment, migrations, configuration, secrets, cache policy, retry policy, and failure
reporting it requires.
