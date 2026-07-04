# Pending TPRM Intelligence API Keys

The TPRM intelligence satellite is implemented to use these optional free-tier keys when configured. Until a key is present, the related signal is skipped explicitly and the rest of the computation continues.

- `HIBP_API_KEY`: HaveIBeenPwned domain breach checks.
- `ALIENVAULT_OTX_API_KEY`: AlienVault OTX domain threat intelligence.
- `OPENCORPORATES_API_KEY`: OpenCorporates company search for KYB verification.
