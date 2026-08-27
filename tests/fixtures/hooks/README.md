# Sanitized Hook Fixture Corpus

This directory contains deterministic, sanitized representative payloads for the Agent/IDE hook integrations exercised by ExecWeave regression tests.

These files are **not live captures** and must not be cited as empirical evidence of a particular provider version. They are extracted from the payload shapes already represented by the repository's existing adapter and record tests, then normalized so the corpus can be reviewed and reused across integration tests.

## Provenance contract

`manifest.json` records, for every fixture:

- the provider;
- the fixture path;
- the existing regression tests from which the represented schema was derived;
- the number of payloads;
- a minimal set of semantic relations expected after conversion.

The manifest explicitly records `live_capture=false`, `contains_real_user_data=false`, and `contains_credentials=false`. A future real capture must not overwrite or silently relabel this corpus. It should be added as a separately identified fixture with capture tool/version, capture date, source environment class, and a documented sanitization review.

## Sanitization contract

Committed fixtures use only synthetic identifiers and the fixed workspace placeholder:

```text
/workspace/execweave-fixture
```

Personal identities are removed or replaced with `<redacted>`. Credentials, authorization headers, cookies, API keys, access tokens, private-key material, real home-directory paths, and real email addresses are prohibited.

`tests/test_hook_fixture_corpus.py` enforces these constraints and passes every payload through the corresponding production semantic adapter. The Claude fixture additionally exercises the production hook CLI and sidecar write path.

## What this corpus proves

The corpus proves that stable, reviewable representative hook payloads remain accepted by the current ExecWeave integration code and produce the expected semantic relations. It does not prove provider-side completeness, live capture fidelity, or compatibility with provider schema changes that are not represented here.
