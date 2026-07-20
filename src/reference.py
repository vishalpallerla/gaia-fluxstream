import csv
import gzip
import math
import os
import sys


def minmax_flux(raw):
    """Return (min, max) of finite values in a Gaia flux array string, or (None, None)."""
    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]

    minimum = None
    maximum = None
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
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
    """Return percentage change for one band, or None if undefined."""
    if minimum is None or maximum is None:
        return None
    if minimum == 0.0:
        # zero minimum makes the formula undefined; treat as invalid
        return None
    result = (maximum - minimum) / minimum * 100.0
    return result if math.isfinite(result) else None


def process_file(path):
    """Yield output rows for qualifying sources in one .csv.gz file."""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as gz:
        lines = (line for line in gz if not line.startswith("#"))
        reader = csv.reader(lines)
        header = next(reader)
        sid_i = header.index("source_id")
        bp_i = header.index("bp_flux")
        rp_i = header.index("rp_flux")

        for row in reader:
            bp_min, bp_max = minmax_flux(row[bp_i])
            rp_min, rp_max = minmax_flux(row[rp_i])

            bp_pct = band_pct(bp_min, bp_max)
            rp_pct = band_pct(rp_min, rp_max)

            candidates = [v for v in (bp_pct, rp_pct) if v is not None]
            if not candidates:
                continue

            pct = max(candidates)
            if pct > 100.0:
                yield (
                    row[sid_i],
                    "" if bp_min is None else bp_min,
                    "" if bp_max is None else bp_max,
                    "" if rp_min is None else rp_min,
                    "" if rp_max is None else rp_max,
                    pct,
                )


def run(in_dir, out_path):
    files = sorted(
        os.path.join(in_dir, f)
        for f in os.listdir(in_dir)
        if f.endswith(".csv.gz")
    )
    if len(files) != 20:
        raise RuntimeError(f"Expected exactly 20 benchmark files, found {len(files)}")

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    with open(out_path, "w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["source_id", "bp_min_flux", "bp_max_flux",
                         "rp_min_flux", "rp_max_flux", "percentage_change"])
        count = 0
        for path in files:
            for row in process_file(path):
                writer.writerow(row)
                count += 1

    return count


if __name__ == "__main__":
    in_dir = sys.argv[1] if len(sys.argv) > 1 else "data/in"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "data/out/result_reference.csv"
    count = run(in_dir, out_path)
    print(f"Done. Qualifying sources: {count}")
