# Vendored wheels

This directory holds prebuilt Python wheels installed **offline** during the
Docker build (`pip install --no-index --find-links=vendor`). Vendoring keeps the
build reproducible and network-independent, and pins the exact tested binary.

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| `isal`  | 1.8.0   | PSF-2.0 | ISA-L `igzip` — faster drop-in gzip decompressor ([python-isal](https://github.com/pycompression/python-isal)) |

The wheel is `cp312` (CPython 3.12) for `manylinux2014_x86_64`, matching the
`intersystems/iris-community:latest-em` Embedded Python runtime. It was
downloaded from inside that container with:

```bash
pip3 download --only-binary=:all: --no-deps isal==1.8.0 -d vendor
```

python-isal bundles a statically linked ISA-L, so no separate system library is
required at runtime.
