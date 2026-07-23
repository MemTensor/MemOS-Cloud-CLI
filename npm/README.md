# npm Distribution

This directory is reserved for the downloaded binary payload used by the npm package.

- `npm/bin/` is populated by `scripts/postinstall.js`
- the supported target matrix is defined in `release-assets.json`
- every supported target must be built and uploaded before npm publication
- expected release asset pattern: `memos-<version>-<platform>-<arch>.tar.gz`
