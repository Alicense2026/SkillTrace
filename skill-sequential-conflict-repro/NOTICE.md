# Third-party material

This package references the following Skill repositories at fixed commits:

- `o0000-code/paper-search-pro`
- `datawhalechina/easy-vibe`
- `ai-freer/fortune-skill`
- `2Tricky4u/Ritual`
- `liufeng1976/bossai-ecommerce-ai-team-skill`
- `AngeloDanducci/mellea`
- `freeasinbird/free-skills`
- `isjiamu/gzh-design-skill`

The complete third-party repositories are not included in this package. `scripts/fetch_repos.py`
downloads them only for local verification. Copyright and license terms remain with their
respective authors.

License excerpts in `inputs/license_evidence.json` are limited to short evidence snippets. The
complete license text in each upstream repository controls.

The canonical event schema and agent-log normalization logic in `scripts/skilltrace/event_schema.py`
are adapted from `qingxuantang/tar-engine` at commit
`ab5f50bfcc4728ccd9a02c96057ba8d12ea4139c`. TAR Engine is licensed under Apache-2.0; the full
license text is included at `licenses/TAR-ENGINE-APACHE-2.0.txt`.
