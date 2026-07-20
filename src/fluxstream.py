import csv
import io
import math
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor

# ISA-L's igzip is a drop-in for the stdlib gzip module but decompresses several
# times faster (Intel ISA-L). Installed at build time via the Dockerfile.
from isal import igzip as gzip

HEADER = b"source_id,bp_min_flux,bp_max_flux,rp_min_flux,rp_max_flux,percentage_change\n"


def minmax_flux(raw):
    """Return (min, max) of finite values in a Gaia flux array (bytes), or (None, None)."""
    text = raw.strip()
    if text[:1] == b"[" and text[-1:] == b"]":
        text = text[1:-1]

    minimum = None
    maximum = None
    for token in text.split(b","):
        # No per-token strip: Gaia flux arrays have no interior whitespace, and
        # float() tolerates any that appears. Empty tokens raise ValueError and
        # are caught below. 
        try:
            value = float(token)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        if minimum is None or value < minimum:
            minimum = value
        if maximum is None or value > maximum:
            maximum = value

    return minimum, maximum


def band_pct(minimum, maximum):
    if minimum is None or maximum is None:
        return None
    if minimum == 0.0:
        return None
    result = (maximum - minimum) / minimum * 100.0
    return result if math.isfinite(result) else None


def _extract3(line, sid_i, bp_i, rp_i, last_i):
    """
    Slice only three fields (by column index) from one Gaia CSV line (bytes).
    Quote-aware: array columns are double-quoted and contain no embedded
    quotes, so we jump the scanner past them. Stops after the last needed
    column instead of tokenising all 48. Returns (sid, bp, rp) as bytes.
    """
    i = 0
    n = len(line)
    idx = 0
    sid = bp = rp = b""
    while i < n and idx <= last_i:
        if line[i] == 0x22:  # b'"'
            j = line.index(0x22, i + 1)
            if idx == bp_i:
                bp = line[i + 1:j]
            elif idx == rp_i:
                rp = line[i + 1:j]
            i = j + 2  # skip closing quote and trailing comma
        else:
            j = line.find(b",", i)
            if j == -1:
                j = n
            if idx == sid_i:
                sid = line[i:j]
            i = j + 1
        idx += 1
    return sid, bp, rp


def _process_file(path):
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    count = 0

    with gzip.open(path, "rb") as gz:
        # ECSV metadata (#-prefixed) occurs only before the CSV header. Skip it
        # once, then never re-check startswith on data rows.
        for header_line in gz:
            if not header_line.startswith(b"#"):
                break
        else:
            raise RuntimeError(f"CSV header not found in {path}")

        header = header_line.rstrip(b"\r\n").split(b",")
        sid_i = header.index(b"source_id")
        bp_i = header.index(b"bp_flux")
        rp_i = header.index(b"rp_flux")
        last_i = max(sid_i, bp_i, rp_i)

        for line in gz:
            # Lines retain their trailing newline, but the extractor stops after
            # last_i (rp_flux, col 16 of 48) — well before the final column — so
            # the newline never lands in an extracted field. minmax_flux strips
            # its input regardless.
            sid, bp_raw, rp_raw = _extract3(line, sid_i, bp_i, rp_i, last_i)
            bp_min, bp_max = minmax_flux(bp_raw)
            rp_min, rp_max = minmax_flux(rp_raw)

            bp_pct = band_pct(bp_min, bp_max)
            rp_pct = band_pct(rp_min, rp_max)

            if bp_pct is None:
                pct = rp_pct
            elif rp_pct is None or bp_pct >= rp_pct:
                pct = bp_pct
            else:
                pct = rp_pct

            if pct is None or pct <= 100.0:
                continue

            writer.writerow((
                sid.decode("ascii"),
                "" if bp_min is None else bp_min,
                "" if bp_max is None else bp_max,
                "" if rp_min is None else rp_min,
                "" if rp_max is None else rp_max,
                pct,
            ))
            count += 1

    return os.path.basename(path), out.getvalue().encode("utf-8"), count


def run(in_dir, out_path):
    files = sorted(
        os.path.join(in_dir, f)
        for f in os.listdir(in_dir)
        if f.endswith(".csv.gz")
    )
    if len(files) != 20:
        raise RuntimeError(f"Expected exactly 20 benchmark files, found {len(files)}")

    files_by_size = sorted(files, key=os.path.getsize, reverse=True)

    try:
        available = len(os.sched_getaffinity(0))
    except AttributeError:
        available = os.cpu_count() or 4
    workers = min(len(files), available)

    ctx = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
        results_unordered = list(ex.map(_process_file, files_by_size))

    results_ordered = sorted(results_unordered, key=lambda r: r[0])

    with open(out_path, "wb") as out:
        out.write(HEADER)
        count = 0
        for _fname, body, file_count in results_ordered:
            out.write(body)
            count += file_count

    return count


if __name__ == "__main__":
    in_dir = sys.argv[1] if len(sys.argv) > 1 else "data/in"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "data/out/result.csv"
    count = run(in_dir, out_path)
    print(f"Done. Qualifying sources: {count}")
