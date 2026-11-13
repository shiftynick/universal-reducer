"""Does the pocket finder's result survive outside the elementary rules?

The 256 elementary rules are mostly simple. Here the two routes that need no
design (watching for a loop, and reuse) are run on rules where each cell
looks at two neighbours on each side instead of one:

  totalistic   the next colour depends only on how many of the five cells
               are black: all 64 such rules
  random       rule tables drawn at random from the roughly four billion
               possible: a sample

Run with: python3 wider.py   (takes a few minutes)
"""

import random
import sys
import time

from finder import find, measured, patch, ring_step
from reuse import reuse_line
from translators import jump

SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 300
FAR = 10**18
ONE_CELL = (0, 1)
random.seed(4)


# --- checks on the wider machinery, against independent brute force ---

def slow_step(rule, width, radius):
    """One step on a ring, cell by cell."""
    def step(cells):
        out = 0
        for i in range(width):
            index = 0
            for d in range(-radius, radius + 1):
                index = 2 * index + ((cells >> ((i + d) % width)) & 1)
            out |= ((rule >> index) & 1) << i
        return out
    return step


def line_rows(rule, radius, start, upto):
    """Rows 0 to `upto` on an endless white line, each as (offset, the cells
    that differ from the background), worked out on a ring too wide for the
    pattern to wrap round."""
    offset, bits = start
    home = radius * (upto + 4)  # where the start's first cell sits on the ring
    width = bits.bit_length() + 2 * home
    full = (1 << width) - 1
    all_black = (1 << (2 * radius + 1)) - 1
    step = ring_step(rule, width, radius)
    cells, background, rows = bits << home, 0, []
    for _ in range(upto + 1):
        differ = cells ^ (full if background else 0)
        if differ:
            shift = (differ & -differ).bit_length() - 1
            rows.append((offset + shift - home, differ >> shift))
        else:
            rows.append((0, 0))
        cells = step(cells)
        background = (rule >> (all_black * background)) & 1
    return rows


def check_reuse(rule, start, upto, every=1):
    whole, counting, _ = reuse_line(rule, radius=2)
    actual = line_rows(rule, 2, start, upto)
    for n in range(max(whole.lead, whole.period), upto + 1, whole.period * every):
        assert jump(whole, start, n)[0] == actual[n], f"rule {rule}: mismatch at step {n}"
        assert jump(counting, start, n)[0] == actual[n][1].bit_count()


def totalistic(code):
    """The rule table for: next colour = bit `number of black cells` of code."""
    return sum(((code >> index.bit_count()) & 1) << index for index in range(32))


def widened(elementary):
    """An elementary rule written as a wider rule that ignores the outer two cells."""
    return sum(((elementary >> ((index >> 1) & 7)) & 1) << index for index in range(32))


for _ in range(60):  # the fast ring stepper, against cell-by-cell stepping
    rule, cells = random.getrandbits(32), random.getrandbits(41)
    assert ring_step(rule, 41, 2)(cells) == slow_step(rule, 41, 2)(cells)

backgrounds = {"stays white": 0, "blinks": 0, "turns black": 0}
tested = [random.getrandbits(32) for _ in range(90)] + [totalistic(code) for code in range(64)]
for rule in tested:  # reuse on wider rules, against the wide ring
    kind = "stays white" if not rule & 1 else "blinks" if not rule >> 31 else "turns black"
    backgrounds[kind] += 1
    for start in (ONE_CELL, patch(random)):
        check_reuse(rule, start, 48)
assert min(backgrounds.values()) >= 15, "each kind of background should be well covered"

for elementary in (90, 110, 105, 129, 54, 184):  # the same rule, written both ways, must agree
    narrow, wide = reuse_line(elementary), reuse_line(widened(elementary), radius=2)
    for start in (ONE_CELL, patch(random)):
        for n in (2, 40, 1000, 12346):
            assert jump(narrow[0], start, n)[0] == jump(wide[0], start, n)[0]
        assert jump(narrow[1], start, FAR)[0] == jump(wide[1], start, FAR)[0]

# --- the census ---

families = {}
t0 = time.perf_counter()
rng = random.Random(2026)  # the same starts as run.py, so the elementary column matches it
families["elementary (all 256)"] = [find(rule, rng) for rule in range(256)]
rng = random.Random(2027)
families["totalistic, wider (all 64)"] = [measured(totalistic(code), rng, 2) for code in range(64)]
sample = [rng.getrandbits(32) for _ in range(SAMPLE)]
families[f"random, wider (sample of {SAMPLE})"] = [measured(rule, rng, 2) for rule in sample]
seconds = time.perf_counter() - t0

passed_far = []  # wider rules that reuse says are reducible from patches: confirm a long way out
for rule, found in zip(sample, families[f"random, wider (sample of {SAMPLE})"]):
    routes = {f.route for f in found}
    if "reuse, patches" in routes and "settles" not in routes:
        passed_far.append(rule)
for rule in passed_far[:8]:
    check_reuse(rule, patch(random), 1500, every=37)

columns = ("family", "settles into a loop", "restless, but reducible from every patch",
           "restless, reducible only from one cell", "nothing found")
table = [columns]
for name, results in families.items():
    split = [0, 0, 0, 0]
    for found in results:
        routes = {f.route for f in found}
        split["settles" not in routes and (1 if "reuse, patches" in routes else
                                             2 if "reuse, one cell" in routes else 3)] += 1
    table.append((name, *(f"{count} ({100 * count / len(results):.0f}%)" for count in split)))
widths = [max(len(row[i]) for row in table) for i in range(len(columns))]
print("The routes that need no design, on three families of rules")
print("(each rule is counted once, under the first heading that fits):")
for row in table:
    print("  " + "  ".join(cell.ljust(w) for cell, w in zip(row, widths)))
print(f"\nWider rules reducible from patches without settling, confirmed to step 1,500: "
      f"{min(len(passed_far), 8)} of {len(passed_far)} checked")
print(f"Census took {seconds:.0f} seconds. All checks passed.")
