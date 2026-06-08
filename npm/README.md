# npm Distribution

This directory is reserved for the downloaded binary payload used by the npm package.

- `npm/bin/` is populated by `scripts/postinstall.js`
- the published npm package should distribute platform binaries for runtime use
- expected release asset pattern: `memos-<version>-<platform>-<arch>.tar.gz`
