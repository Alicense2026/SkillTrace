# Security policy

## Credentials

`collect_github.py` reads credentials only from environment variables:

- `GITHUB_TOKEN`
- `GITHUB_API` (optional; defaults to `https://api.github.com`)

`collect_hf.py` reads:

- `HF_TOKEN`
- `HF_ENDPOINT` (optional)

Never commit `.env` files, tokens, authenticated URLs, or terminal transcripts containing tokens.

## Compromised token checklist

If a token appears in a committed file or public log:

1. Revoke it immediately in the GitHub account settings.
2. Create a replacement token with the minimum required scopes.
3. Remove the credential from the source and Git history before publishing.
4. Re-run `python scripts/validate_dataset.py` to check for common token patterns.

The packaged repository intentionally contains no hard-coded GitHub token.

## Reporting

Report accidental credential exposure or private data in a public issue only after the credential
has been revoked. Do not reproduce the secret itself in the report.
