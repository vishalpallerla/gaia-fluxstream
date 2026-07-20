# Gaia FluxStream

A parallel Gaia DR3 variability engine for the
[InterSystems Employee Programming Challenge #1](https://openexchange.intersystems.com/contest/47),
built on InterSystems IRIS with Embedded Python.

It processes the 20-file benchmark set through `do ^RunScript`, decompressing and
analysing the compressed archives entirely within the timed run — nothing is
precomputed. Speed comes from three deliberate, measured choices: a fast
decompressor (Intel ISA-L), a constant-memory streaming pipeline, and parsing
only the 3 of 48 columns the task actually needs.

## The Challenge

Process 20 gzip-compressed Gaia DR3 epoch-photometry files (ECSV format: a CSV
body behind a `#`-prefixed YAML header). For each astronomical object, decide
whether its BP (blue) or RP (red) flux varied by more than 100% across all valid
observations:

```
percentage_change = (max_flux − min_flux) / min_flux × 100      (per band)
result            = max(bp_percentage_change, rp_percentage_change)
```

Invalid samples (NaN, null, empty) are ignored. Every object whose
`percentage_change` exceeds 100% is written to the output, one row per object:

```
source_id, bp_min_flux, bp_max_flux, rp_min_flux, rp_max_flux, percentage_change
```

On the official 20-file benchmark set this scans 75,068 sources and reports
**57,099** variable ones.

## Quick start

Prerequisites: [Git](https://git-scm.com) and
[Docker Desktop](https://www.docker.com/products/docker-desktop).

```bash
git clone https://github.com/vishalpallerla/gaia-fluxstream.git
cd gaia-fluxstream
docker compose up --build -d      # builds the IRIS image, installs vendored ISA-L, compiles the routines
```

Run it:

```bash
docker compose exec iris iris session iris -U USER
```

At the `USER>` prompt:

```
do ^RunScript
```

Expected:

```
Qualifying sources: 57099
Elapsed time: X.XX seconds
```

Check the result file:

```bash
head -3 data/out/result.csv
wc -l  data/out/result.csv        # 57100 = 1 header + 57099 rows
```

## How it works

The pipeline is a straight line from the IRIS entry point down to Python:

```
do ^RunScript                          (src/RunScript.mac)   ── starts the $ZHOROLOG timer
      │
      ▼
##class(FluxStream).Run(in, out)       (src/FluxStream.cls)  ── Language=python entry method
      │
      ▼
fluxstream.run(in_dir, out_path)       (src/fluxstream.py)
      │
      ▼
ProcessPoolExecutor (spawn)            one worker per file, largest first
      ├─ worker: igzip stream-decompress → extract 3 of 48 columns → reduce BP/RP → CSV bytes
      ├─ worker: …
      └─ worker: …
      │
      ▼
Merge workers' byte fragments in canonical filename order → write result.csv
```

### Files

| File | Role |
|------|------|
| `src/RunScript.mac` | IRIS entry point. Times the call with `$ZHOROLOG`, invokes `FluxStream.Run()`, prints the row count and elapsed seconds. |
| `src/FluxStream.cls` | IRIS class with a `Language=python` method. Imports `fluxstream` (found via `PYTHONPATH`, set in the Dockerfile) and calls `run()`. |
| `src/fluxstream.py` | The engine — parallel decompression, parsing, reduction, and output. |
| `src/reference.py` | Single-threaded, spec-faithful correctness oracle. Not optimised; used only to verify output. |
| `vendor/` | The prebuilt ISA-L wheel, installed offline at build time. See `vendor/README.md`. |

### The four measured design choices

Each was chosen by measurement and verified byte-identical to the reference
oracle.

1. **ISA-L `igzip` decompression.** Decompression dominates the runtime, so the
   codec is the highest-leverage choice. ISA-L (Intel's SIMD-accelerated gzip)
   is a drop-in for the standard-library `gzip` module and was the fastest codec
   measured (beating stdlib gzip, zlib-ng, and cramjam). Used via
   `from isal import igzip as gzip`.

2. **Streaming decompression, not whole-file.** `gzip.open` yields lines one at
   a time, so a 115 MB decompressed file never lives in memory all at once. This
   keeps parallel workers from competing for RAM. Whole-file decompression is
   faster per-file in isolation but loses end-to-end at high concurrency, when
   many simultaneous 115 MB buffers saturate memory bandwidth.

3. **Targeted field extractor.** The Gaia files have **48 columns** but only
   **3** are needed (`source_id`, `bp_flux`, `rp_flux`). A quote-aware scanner
   (`_extract3`) walks each line, slices exactly those fields, and stops after
   the last one — skipping the other 45 huge array columns entirely, rather than
   letting `csv.reader` tokenise every column. Column positions are discovered
   from the header, not hardcoded.

4. **Raw bytes throughout.** Files are read in binary and parsed as bytes,
   skipping the UTF-8 decode of ~115 MB per file. `float()` accepts byte strings
   directly, so the flux parse never materialises a `str`.

### Parallelism: processes, not threads

The 20 files are independent, so each goes to its own worker via
`ProcessPoolExecutor` with the **`spawn`** start method:

- **`spawn`, not `fork`** — forking the IRIS process would inherit its file
  descriptors and memory mappings and is slow; `spawn` starts clean Python
  interpreters.
- **Processes, not threads** — a `ThreadPoolExecutor` measured ~6× slower here.
  The decompressor releases the GIL during `inflate`, but the per-row Python
  parsing is GIL-bound, so threads serialise on it. Separate processes give true
  multi-core parallelism, worth the interpreter-startup cost.
- **Auto-scaling** — `workers = min(20 files, available CPUs)` via
  `os.sched_getaffinity(0)`, so the engine uses exactly the cores the container
  is given, up to one per file. No hardcoded core count.
- **Largest files first** — better load balancing when workers handle more than
  one file.

### Correctness details

- **One-band qualification** — a source qualifies if *either* BP or RP exceeds
  100%, even when the other band has no valid data.
- **Strict `> 100`**, not `>= 100`.
- Zero and non-finite minima are treated as undefined (no percentage).

## Verify correctness

The engine's output is diffed (order-independent) against the reference oracle:

```bash
docker compose exec iris python3 -c "
import sys, csv
sys.path.insert(0, '/home/irisowner/dev/src')
import reference
reference.run('/home/irisowner/dev/data/in', '/home/irisowner/dev/data/out/result_reference.csv')
def load(p):
    with open(p) as f: return sorted(csv.reader(f))
print('Match:', load('/home/irisowner/dev/data/out/result.csv') == load('/home/irisowner/dev/data/out/result_reference.csv'))
"
```

## Performance

Decompression is ~82% of the runtime, so wall-clock scales with the number of
CPU cores the container is given. The engine auto-detects and uses whatever cores are available. 

## Dependencies

The only external dependency is [ISA-L](https://github.com/pycompression/python-isal)
(`isal==1.8.0`), the Intel ISA-L gzip decompressor. Its prebuilt manylinux wheel
is **vendored** under `vendor/` and installed offline during `docker build`
(`pip install --no-index --find-links=vendor`), so the build needs no network
access and pins the exact tested binary. License details are in
`THIRD_PARTY_NOTICES.md`.

## Feedback

IRIS Embedded Python provided a concise bridge from the supplied ObjectScript
benchmark routine to the Python engine — a `Language=python` class method calls
straight into `fluxstream.run()`. The main engineering challenge was validating
parallel behaviour inside Docker: discovering that `fork` inherits the IRIS
process state (hence `spawn`), that threads lose to processes because the parse
is GIL-bound, and that the real cost centre is decompression — which made codec
selection (ISA-L) the single highest-impact decision.
