# Third-Party Notices

This project bundles the following third-party component, installed offline from
`vendor/` during the Docker build.

## isal (python-isal)

- **Version:** 1.8.0
- **License:** PSF-2.0 (Python Software Foundation License v2)
- **Upstream:** https://github.com/pycompression/python-isal
- **Reason included:** Provides `isal.igzip`, a drop-in replacement for the
  standard-library `gzip` module backed by Intel's ISA-L. Used to accelerate the
  decompression-bound hot path. Vendored as a prebuilt wheel for reproducible,
  network-free Docker builds.

python-isal is distributed under the PSF-2.0 license and statically links the
ISA-L library (BSD-3-Clause). See the upstream repository for full license text.
