# Temmo: provider conditions (checked 2026-10-21)

Scope: which AI providers Temmo may call from **its own server** (users never enter a key),
under the project rules: free only (M79), no new accounts, and the project owner is under 18
without guardian consent for 18+ services.

All prices are list prices read from the provider pages on 2026-10-21. "Per game" assumes the
Temmo pipeline budget: design about 3,000 input + 2,500 output tokens, levels retry 1,200 output,
mod about 1,500 input + 700 output, repair rounds up to 3 x 2,200 -> roughly **10k input + 10k output
tokens per game**, plus 5 sprites if an image model is used.

| Provider / model | Free tier on the API? | Limits | Minimum age (Terms) | Public app, server-side key? | Approx. cost per game |
|---|---|---|---|---|---|
| Claude API (Sonnet 5.5, Haiku 5.5) | No. Pay per token. | n/a | 18+ (or local age of majority) | Allowed on paid Commercial Terms | Sonnet 5.5: $2 in / $10 out per MTok -> about $0.12. Haiku 5.5: $0.10 in / $0.50 out -> about $0.006 |
| OpenAI API (gpt-6-luna, gpt-6.1-sol) | No. Pay per token. | n/a | 13+, under 18 needs parent or guardian permission (search summary of openai.com terms; page blocked our fetch) | Allowed on paid Business terms | gpt-6-luna: $0.10 in / $0.50 out -> about $0.006. gpt-6.1-sol: $2 / $10 -> about $0.12 |
| DeepSeek API (deepseek-flash = V4.1-Flash) | No free tier on the pricing page; only a "granted balance" if one was given | Concurrency 2,500 | Terms address minors: "minors under the age of 18 shall read in the presence of a legal guardian" | Paid only | Peak $0.30 in / $1.20 out per MTok (off-peak half) -> about $0.015 |
| Nano Banana (gemini-2.5-flash-image) | **No**: free tier input and output "Not available" | n/a | 18+ (Gemini API Additional Terms) | Paid only | $0.039 per image -> 5 sprites about $0.20. Deprecated: pricing page says shutdown 2026-10-02, deprecations page says 2027-03-15 (pages disagree) |
| Nano Banana 2.1 (gemini-nano-banana-2.1) | No (free tier "Not available") | n/a | 18+ | Paid only | $0.0336 per 1K image -> 5 sprites about $0.17 |
| Gemini chat (gemini-3.6-flash) | **Yes**: input and output "Free of charge" on the free tier | Per project, not per key; RPM / TPM / RPD; RPD resets at midnight Pacific. Google no longer publishes a fixed table; the live limit is in AI Studio (community estimate about 10 RPM / 1,500 RPD, not official) | **18+**, and the API must not be used in an app "directed towards or likely to be accessed by individuals under the age of 18" | Free tier data is "Used to improve our products"; Terms say do not send personal or sensitive data to Unpaid Services | $0 on free tier. Paid: $0.75 in / $3.75 out per MTok until 2026-12-31 -> about $0.045 |
| Local Gemma 4 E2B (already on the VM) | Free, no key | CPU only on this VM: p50 24.2 s per SANKPUP image, one job at a time is safe on 8 GB | Apache 2.0, no age gate | Yes, it is our own server | $0 (server CPU time only) |

## What this means for Temmo server mode

- **The only cloud API that is free is Gemini (gemini-3.6-flash).** Its Additional Terms require
  the developer to be 18+ and forbid apps likely to be used by under-18s. Bogus is under 18 and has no
  guardian consent, so the project **cannot ship a Gemini server key today**. The server code supports
  it, but it is off unless an operator sets `TEMMO_FREE_TIER=gemini` and `TEMMO_OPERATOR_TERMS_OK=1`
  (meaning an adult operator accepted the Terms for an 18+ audience).
- **Claude, OpenAI, DeepSeek and Nano Banana have no free API tier.** They stay BYOK-only (an optional
  advanced setting); the server never pays for them.
- **Default server engine = local Gemma 4** (no key, no cost, no age gate), with `mock` as the fallback
  when no model is installed. Every user gets a per-day quota and requests go through a single queue,
  because the VM can run one local generation at a time.

## Model ID check

`gemini-2.0-flash` and `gemini-2.0-flash-001` were shut down on **2026-06-01**; the recommended
replacement is `gemini-3.6-flash` (Gemini deprecations page). `gemini-2.5-flash` has "No shutdown
date announced" on the same page. The pricing page calls 3.6 Flash "our previous generation Flash
model", so a newer Flash exists; Temmo keeps 3.6 as the default until it is tested.

## Domain

`temmo.gg`: RDAP lookup via rdap.org returned 404 "No RDAP service is available for this resource"
(the .gg registry has no RDAP), so availability is **not verified**. Nothing was bought.

## Sources

- Gemini pricing: https://ai.google.dev/gemini-api/docs/pricing
- Gemini rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Gemini deprecations: https://ai.google.dev/gemini-api/docs/deprecations
- Gemini API Additional Terms (age 18, Unpaid Services): https://ai.google.dev/gemini-api/terms
- Claude pricing: https://docs.claude.com/en/docs/about-claude/pricing
- Anthropic terms (minimum age 18): https://www.anthropic.com/legal/consumer-terms
- Anthropic Commercial Terms: https://www.anthropic.com/legal/commercial-terms
- OpenAI pricing: https://developers.openai.com/api/docs/pricing
- OpenAI terms of use: https://openai.com/policies/terms-of-use/
- DeepSeek pricing: https://api-docs.deepseek.com/quick_start/pricing
- DeepSeek Open Platform terms: https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html
- RDAP: https://rdap.org/domain/temmo.gg
