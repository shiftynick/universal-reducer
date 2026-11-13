"""Check every pocket against brute force, then print the scoreboard.

Run with: python3 run.py
"""

import random
import time
from collections import Counter

from clever import Meter, fast, one_step, repeated_addition, school
from engine import fast_forward
from finder import GROUPS, ROUTES, find, group, mirror, ring_step, twin
from reuse import reuse_line
from translators import (
    DIRECT_RULES, EMPTY_RULES, STILL_RULES, additive_ca, averaged_walk, coarse_grained,
    coarse_search, conserved_count, cycling, direct_rule, emulation_scale, jump, linear,
    sparse_nested, whole_state,
)

BIG = 10**18
random.seed(1)


def check(translation, real_step, start, upto, every=1, watch=None):
    """Compare the engine with step-by-step running, at every step it can answer."""
    every = max(every, 1 if whole_state(translation) else translation.period)
    state = start
    for n in range(1, upto + 1):
        state = real_step(state)
        if n % every:
            continue
        predicted, _ = jump(translation, start, n, real_step)
        actual = state if whole_state(translation) else translation.feature(state)
        if translation.close:
            assert translation.close(predicted, actual), f"too far apart at step {n}"
        else:
            assert predicted == actual, f"mismatch at step {n}"
        if watch:
            watch(predicted, actual)


def check_split(translation, start, real_step=None):
    """For jumps too long to run by brute force: a jump of a+b steps must
    equal a jump of a steps followed by a jump of b steps."""
    for _ in range(20):
        a = random.randrange(1, BIG) * translation.period
        b = random.randrange(1, BIG)
        whole, _ = jump(translation, start, a + b, real_step)
        first, _ = jump(translation, start, a, real_step)
        second, _ = jump(translation, first, b, real_step)
        assert whole == second, "split check failed"


# --- brute-force reference systems, written independently of the translators ---

def fib_step(modulus):
    def step(state):
        a, b = state
        return (b, (a + b) % modulus if modulus else a + b)
    return step


def eca_step(rule, width):
    """One step of an elementary cellular automaton on a ring, cell by cell."""
    def step(cells):
        out = 0
        for i in range(width):
            left = (cells >> ((i - 1) % width)) & 1
            centre = (cells >> i) & 1
            right = (cells >> ((i + 1) % width)) & 1
            out |= ((rule >> (4 * left + 2 * centre + right)) & 1) << i
        return out
    return step


def rule30_fast(width):
    full = (1 << width) - 1
    def step(cells):
        left = ((cells << 1) | (cells >> (width - 1))) & full
        right = ((cells >> 1) | (cells << (width - 1))) & full
        return left ^ (cells | right)
    return step


def blotchy(width):
    """A random state made of solid runs, so blurred features have something to show."""
    state, position, colour = 0, 0, random.getrandbits(1)
    while position < width:
        run = random.randrange(1, 14)
        if colour:
            state |= ((1 << run) - 1) << position
        position += run
        colour ^= 1
    return state & ((1 << width) - 1)


rows = []
notes = []


def record(kind, system, translation, start, verified, extras="none", big_n=BIG, real_step=None):
    big_n -= (big_n - translation.lead) % translation.period
    t0 = time.perf_counter()
    _, result = jump(translation, start, big_n, real_step)
    seconds = time.perf_counter() - t0
    if translation.work:  # the object is a recipe; its cost is the cache it filled
        largest = f"{translation.work():,} entries"
    else:
        largest = f"{result.largest:,}"
        if translation.note:
            notes.append(f"{system}: {translation.note}")
    rows.append((kind, system, extras, verified, big_n, result.combines, largest,
                 translation.steps_run, seconds))


# 1. Self-combining rules: Fibonacci
MOD = 1_000_000_007
fib = [[0, 1], [1, 1]]
t = linear(fib, MOD)
check(t, fib_step(MOD), (0, 1), 5000)
check_split(t, (0, 1))
record("self-combining", "Fibonacci mod 1e9+7", t, (0, 1), 5000)

t = linear(fib)
check(t, fib_step(None), (0, 1), 2000)
record("self-combining", "Fibonacci, exact", t, (0, 1), 2000, big_n=10**6)

# 2. Self-combining rules / nesting: additive cellular automata on a ring
WIDTH = 101
for rule, offsets in ((90, (-1, 1)), (60, (-1, 0)), (150, (-1, 0, 1))):
    t = additive_ca(offsets, WIDTH)
    for _ in range(3):
        start = random.getrandbits(WIDTH)
        check(t, eca_step(rule, WIDTH), start, 600)
    check_split(t, start)
    record("self-combining", f"rule {rule}, ring of {WIDTH}", t, start, 600)

#    ... and the same form in a second arithmetic, where colour spreads
for rule in DIRECT_RULES:  # every rule the engine claims to run directly
    t = direct_rule(rule, WIDTH)
    for start in (random.getrandbits(WIDTH), blotchy(WIDTH)):
        check(t, eca_step(rule, WIDTH), start, 80)
t = direct_rule(128, WIDTH)
start = blotchy(WIDTH)
check_split(t, start)
record("self-combining", f"rule 128, ring of {WIDTH}", t, start, 80)

# 3. Repetition: rule 30 is irreducible in general, but on a small ring it must loop
WIDTH30 = 18
step30 = rule30_fast(WIDTH30)
assert all(step30(s) == eca_step(30, WIDTH30)(s) for s in random.sample(range(1 << WIDTH30), 500))
start = 1
t = cycling(step30, start)
check(t, step30, start, 3 * t.steps_run + 100)
check_split(t, start)
record("repetition", f"rule 30, ring of {WIDTH30}", t, start, 3 * t.steps_run + 100,
       extras="state map")

# 4. Nesting that depends on the starting state: rules that are not additive
#    but hide a copy of rule 90 when the black cells are spread thinly
WIDTH_N = 96


def thin_state(spacing):
    """A random state whose black cells all sit in one class mod `spacing`."""
    offset = random.randrange(spacing)
    state = 0
    for p in range(offset, WIDTH_N, spacing):
        if random.random() < 0.5:
            state |= 1 << p
    return state


scales = {rule: emulation_scale(rule) for rule in range(256)}
found = {rule: s for rule, s in scales.items() if s}
for rule, s in found.items():  # every rule the proof-by-windows accepts, checked by brute force too
    t = sparse_nested(rule, WIDTH_N)
    real = eca_step(rule, WIDTH_N)
    check(t, real, 1 << (WIDTH_N // 2), 150)
    check(t, real, thin_state(2 * s), 150)

for rule in (18, 22):
    t = sparse_nested(rule, WIDTH_N)
    real = eca_step(rule, WIDTH_N)
    single_cell = 1 << (WIDTH_N // 2)
    check(t, real, single_cell, 600)
    check_split(t, single_cell, real)

    # The pocket belongs to the starting state: a crowded start is refused,
    # and forcing it through gives wrong answers.
    crowded = random.getrandbits(WIDTH_N)
    assert not t.accepts(crowded)
    state, wrong = crowded, 0
    for n in range(1, 41):
        state = real(state)
        wrong += jump(t, crowded, n, real, force=True)[0] != state
    assert wrong > 30, "forcing a crowded start should give wrong answers"

    extras = "start condition" if t.period == 1 else f"start condition, state map, {t.period} steps per pocket step"
    record("nesting (start-dependent)", f"rule {rule}, ring of {WIDTH_N}", t, single_cell, 600,
           extras=extras, real_step=real)

# 5. Invariants: the pocket predicts one number and the pocket system does nothing
counted = [rule for rule in range(256) if conserved_count(rule, 100)]
for rule in counted:
    t = conserved_count(rule, 100)
    check(t, eca_step(rule, 100), random.getrandbits(100), 100)
t = conserved_count(184, 100)
start = random.getrandbits(100)
check(t, eca_step(184, 100), start, 600)
record("invariant", "rule 184 (traffic), ring of 100", t, start, 600, extras="feature")

# 6. Blurring: an exact coarse version of a rule the engine cannot run directly
kinds = {"moves": [], "still": [], "cannot run": [], "empty": [], "none": []}
for rule in range(256):
    if rule in DIRECT_RULES:
        continue
    targets = {g for _, _, g in coarse_search(rule)}
    runnable = {g for g in targets if g in DIRECT_RULES and g not in EMPTY_RULES}
    if runnable - set(STILL_RULES):
        kinds["moves"].append(rule)
    elif runnable:
        kinds["still"].append(rule)
    elif targets - set(EMPTY_RULES):
        kinds["cannot run"].append(rule)
    elif targets:
        kinds["empty"].append(rule)
    else:
        kinds["none"].append(rule)
    t = coarse_grained(rule, WIDTH_N)
    if t:  # every blurred version the proof-by-windows accepts, checked by brute force too
        for start in (random.getrandbits(WIDTH_N), blotchy(WIDTH_N), blotchy(WIDTH_N)):
            check(t, eca_step(rule, WIDTH_N), start, 36)

t = coarse_grained(146, 99)
real = eca_step(146, 99)
for _ in range(4):
    start = blotchy(99)
    check(t, real, start, 300)
record("blurring", "rule 146 (chaotic), ring of 99", t, start, 300,
       extras=f"feature, {t.period} steps per pocket step")

# 7. Averaging out: a crowd of random walkers; only the shape of the crowd is predicted
WIDTH_W, CROWD = 51, 20_000
rng = random.Random(7)


def walk(lean=0.5):
    def step(positions):
        return [(p + (1 if rng.random() < lean else -1)) % WIDTH_W for p in positions]
    return step


t = averaged_walk(WIDTH_W, CROWD)
start = [WIDTH_W // 2] * CROWD
worst = [0.0]


def noise_units(predicted, actual):
    for p, a in zip(predicted, actual):
        if p * CROWD >= 10:
            worst[0] = max(worst[0], abs(a - p) / (p * (1 - p) / CROWD) ** 0.5)


check(t, walk(), start, 300, every=3, watch=noise_units)
state, caught = start, 0
lopsided = walk(lean=0.6)  # a crowd that drifts must NOT pass as matching the prediction
for n in range(1, 61):
    state = lopsided(state)
    caught += not t.close(jump(t, start, n)[0], t.feature(state))
assert caught > 40, "a drifting crowd should fail the tolerance"
record("averaging", f"{CROWD:,} random walkers, ring of {WIDTH_W}", t, start, 300,
       extras="feature, tolerance")

# 8. Reuse: one translator for every rule (first the 128 that keep a white row
#    white; the rest are checked in section 10). It is given no proof and no
#    knowledge of the rule; a cache finds the repeats.
def line_step(rule):
    """One step on an endless white line. A state is (offset, bits)."""
    def step(state):
        offset, bits = state
        if not bits:
            return state
        x = bits << 1
        mask = (1 << (x.bit_length() + 1)) - 1
        left, centre, right = x << 1, x, x >> 1
        out = 0
        for index in range(1, 8):
            if (rule >> index) & 1:
                term = mask
                term &= left if index & 4 else ~left
                term &= centre if index & 2 else ~centre
                term &= right if index & 1 else ~right
                out |= term
        if not out:
            return (0, 0)
        shift = (out & -out).bit_length() - 1
        return (offset - 1 + shift, out >> shift)
    return step


def patch():
    return (random.randrange(-50, 50), random.getrandbits(40) | 1 | (1 << 39))


EVEN = range(0, 256, 2)
for rule in random.sample(EVEN, 12):  # the line stepper itself, against cell-by-cell stepping
    line, ring = (0, random.getrandbits(30) | 1), None
    ring = line[1] << 180
    for _ in range(60):
        line, ring = line_step(rule)(line), eca_step(rule, 400)(ring)
        assert ring == (line[1] << (180 + line[0]) if line[1] else 0)

for rule in EVEN:  # every rule it accepts, against step-by-step running
    whole, counting, world = reuse_line(rule)
    for start in ((0, 1), patch(), patch()):
        check(whole, line_step(rule), start, 70)
        check(counting, line_step(rule), start, 70, every=7)

one_cell = (0, 1)
for rule, upto, every in ((90, 2000, 13), (126, 2000, 13), (110, 5000, 37), (30, 600, 7)):
    whole, counting, world = reuse_line(rule)
    check(whole, line_step(rule), one_cell, upto, every=every)


def reuse_split(rule):
    """A jump of a+b steps must leave exactly the same cells black as a jump
    of a steps followed by a jump of b steps."""
    whole, _, world = reuse_line(rule)
    pocket = whole.pocket
    start = whole.encode(one_cell)
    for _ in range(3):
        a, b = random.randrange(1, BIG), random.randrange(1, BIG)
        together = pocket.apply(fast_forward(pocket, a + b).obj, start)
        apart = pocket.apply(fast_forward(pocket, b).obj, pocket.apply(fast_forward(pocket, a).obj, start))
        assert world.fingerprint(together) == world.fingerprint(apart)
        assert world.black(together) == world.black(apart)


def runs_of_ones(n):
    return [len(run) for run in bin(n)[2:].split("0") if run]


for rule in (90, 18, 22, 54, 126, 150, 182, 110):
    reuse_split(rule)
    _, counting, world = reuse_line(rule)
    black, _ = jump(counting, one_cell, BIG)
    if rule in (90, 18):  # known formula: 2 to the number of 1s in n written in binary
        assert black == 2 ** BIG.bit_count()
    if rule == 150:       # known formula: a product over the runs of 1s in n
        expected = 1
        for length in runs_of_ones(BIG):
            expected *= (2 ** (length + 2) - (-1) ** length) // 3
        assert black == expected
    if rule in (90, 126, 110):
        record("reuse", f"rule {rule} from one cell, endless line", reuse_line(rule)[1], one_cell,
               {90: 2000, 126: 2000, 110: 5000}[rule], extras="recipes, cache")


growth = {}
for rule in (90, 30):
    for n in (1000, 3000):
        _, counting, world = reuse_line(rule)
        jump(counting, one_cell, n)
        growth[rule, n] = world.filled

# 9. Clever algorithms: multiplying two large numbers.
#    Repeated addition fits the form unchanged, and the engine turns it into
#    the school method. The fast method beats that and does not fit.
def big_number(bits):
    return random.getrandbits(bits) | (1 << (bits - 1)) | 1


for _ in range(200):  # the fast method itself, against Python's own multiplication
    a, b = random.getrandbits(random.randrange(600)), random.getrandbits(random.randrange(600))
    assert fast(a, b, Meter()) == school(a, b, Meter()) == a * b

a, b = big_number(10_000), big_number(10_000)
t = repeated_addition(a, Meter())
check(t, lambda total: total + a, 0, 2000)
check_split(t, 0)
assert jump(t, 0, b)[0] == a * b
record("self-combining", "add a 10,000-bit number over and over", t, 0, 2000, big_n=b)

t = one_step(a, Meter())
check(t, lambda x: x * a, b, 3)
record("clever algorithm", "the same product by the fast method", t, b, 3,
       extras="does not fit: one step, engine idle", big_n=1)

multiplying = []
for bits in (1_000, 10_000, 100_000):
    a, b = big_number(bits), big_number(bits)
    doubling, by_school, by_fast = Meter(), Meter(), Meter()
    assert jump(repeated_addition(a, doubling), 0, b)[0] == a * b
    assert school(a, b, by_school) == a * b
    assert fast(a, b, by_fast) == a * b
    multiplying.append((bits, doubling.bits, by_school.bits, by_fast.bits))
for (_, d1, s1, f1), (_, d2, s2, f2) in zip(multiplying, multiplying[1:]):
    assert 90 < d2 / d1 < 110 and 90 < s2 / s1 < 110, "ten times the digits should cost about 100 times"
    assert 30 < f2 / f1 < 45, "the fast method should cost about 38 times"
    assert d2 / f2 > 2 * d1 / f1, "the engine should fall further behind as the numbers grow"


# 10. The pocket finder: every automatic route, tried on all 256 rules with no
#     knowledge of the rule. First the checks on the routes that are new here.
for rule in range(256):  # the fast ring stepper, against cell-by-cell stepping
    for _ in range(4):
        cells = random.getrandbits(37)
        assert ring_step(rule, 37)(cells) == eca_step(rule, 37)(cells)


def line_rows(rule, start, upto):
    """Rows 0 to `upto` on an endless white line, each as (offset, the cells
    that differ from the background), worked out on a ring too wide for the
    pattern to wrap round."""
    offset, bits = start
    width = bits.bit_length() + 2 * upto + 8
    full = (1 << width) - 1
    home = upto + 4  # where the start's first cell sits on the ring
    step = ring_step(rule, width)
    cells, background, found_rows = bits << home, 0, []
    for _ in range(upto + 1):
        differ = cells ^ (full if background else 0)
        if differ:
            shift = (differ & -differ).bit_length() - 1
            found_rows.append((offset + shift - home, differ >> shift))
        else:
            found_rows.append((0, 0))
        cells = step(cells)
        background = (rule >> (7 * background)) & 1
    return found_rows


def check_reuse(rule, start, upto, every=1):
    """Reuse against the wide ring, at every step it can answer."""
    whole, counting, _ = reuse_line(rule)
    actual = line_rows(rule, start, upto)
    for n in range(max(whole.lead, whole.period), upto + 1, whole.period * every):
        assert jump(whole, start, n)[0] == actual[n], f"rule {rule}: mismatch at step {n}"
        assert jump(counting, start, n)[0] == actual[n][1].bit_count()


for rule in range(256):  # all three kinds of background
    for start in (one_cell, patch(), patch()):
        check_reuse(rule, start, 70)
for rule, upto in ((105, 2000), (129, 2000), (45, 400)):  # blinking, turning black, blinking and chaotic
    check_reuse(rule, one_cell, upto, every=11)
for rule in (126, 110, 137):  # from a random patch, where reuse succeeding was a surprise
    check_reuse(rule, patch(), 3000, every=41)

for rule in (105, 129, 1, 57):
    reuse_split(rule)
expected = 1  # two steps of rule 105 are two steps of rule 150, so its count follows the same formula
for length in runs_of_ones(BIG):
    expected *= (2 ** (length + 2) - (-1) ** length) // 3
assert jump(reuse_line(105)[1], one_cell, BIG)[0] == expected
# rule 129 is rule 126 with the colours swapped
assert jump(reuse_line(129)[1], one_cell, BIG)[0] == jump(reuse_line(126)[1], one_cell, BIG)[0]
record("reuse", "rule 105 from one cell, endless line", reuse_line(105)[1], one_cell, 2000,
       extras="recipes, cache, 2 steps per pocket step")
record("reuse", "rule 129 from one cell, endless line", reuse_line(129)[1], one_cell, 2000,
       extras="recipes, cache, head start")

finder_rng = random.Random(2026)
census = {rule: find(rule, finder_rng) for rule in range(256)}
route_counts = Counter(f.route for found_here in census.values() for f in found_here)
has = {route: {rule for rule in range(256) if any(f.route == route for f in census[rule])}
       for route in ROUTES}
grouped = {g: [rule for rule in range(256) if group(census[rule]) == g] for g in GROUPS}

for rule in has["settles"]:  # every rule said to settle, against step-by-step running
    step = ring_step(rule, 61)
    start = random.getrandbits(61)
    t = cycling(step, start, budget=20 * 61)
    if t:
        check(t, step, start, 2 * t.steps_run + 40, every=7)
assert cycling(ring_step(30, 61), 1, budget=20 * 61) is None

# A mirror image or a colour swap cannot change whether a rule settles, and a
# mirror image cannot change what reuse finds. Where the finder disagrees with
# itself, the rule sits close to a budget.
borderline = sorted(
    rule for rule in range(256)
    if any((rule in has["settles"]) != (other in has["settles"]) for other in (mirror(rule), twin(rule)))
    or any((rule in has[route]) != (mirror(rule) in has[route]) for route in ("reuse, one cell", "reuse, patches"))
)

# What the finder missed: rules 105, 153, 165 and 195 are rules 150, 102, 90
# and 60 with the output colour flipped, so a whole-row formula exists for them.
missed = []
for rule in (105, 153, 165, 195):
    plain = direct_rule(255 - rule, WIDTH)
    real = eca_step(rule, WIDTH)
    state = start = random.getrandbits(WIDTH)
    for n in range(1, 41):
        state = real(state)
        flip = n % 2 if rule == 105 else 1
        assert state == jump(plain, start, n)[0] ^ (((1 << WIDTH) - 1) * flip)
    if "direct" not in {f.route for f in census[rule]}:
        missed.append(rule)


def short(n):
    if n < 1000:
        return str(n)
    return f"{n:.0e}" if n < 10**300 else f"over 2^{n.bit_length() - 1:,}"


# --- scoreboard ---
header = ("kind", "system", "added to the form", "checked to n", "jump to n", "combines",
          "largest object (bits)", "steps translator ran", "seconds")
table = [header] + [
    (k, s, x, f"{v:,}", short(n), str(c), big, f"{ran:,}", f"{sec:.4f}")
    for k, s, x, v, n, c, big, ran, sec in rows
]
widths = [max(len(r[i]) for r in table) for i in range(len(header))]
for r in table:
    print("  ".join(cell.ljust(w) for cell, w in zip(r, widths)))

print("\nWhat the partial pockets predict:")
for note in notes:
    print(f"  {note}")
print(f"  random walkers: largest gap seen was {worst[0]:.1f} times the expected sampling noise")

print(f"\nRules the engine runs directly on every start: {len(DIRECT_RULES)} of 256")
print(f"  {sorted(DIRECT_RULES)}")
print("\nElementary rules hiding a copy of rule 90 on thinly spread states, by scale:")
for s in sorted(set(found.values())):
    print(f"  scale {s}: {sorted(r for r, v in found.items() if v == s)}")
print(f"\nRules whose number of black cells never changes: {counted}")
print(f"\nExact blurred versions (blocks of 2 or 3) of the other {256 - len(DIRECT_RULES)} rules:")
labels = {
    "moves": "blurred rule moves and the engine can run it",
    "still": "blurred picture only freezes or shifts",
    "cannot run": "blurred rule exists but the engine cannot run it",
    "empty": "only the empty kind (some pattern never appears)",
    "none": "none found",
}
for key, label in labels.items():
    print(f"  {label}: {len(kinds[key])}")
    if key in ("moves", "cannot run"):
        print(f"    {kinds[key]}")
print("\nReuse, table entries filled from one cell:")
for rule in (90, 30):
    print(f"  rule {rule}: {growth[rule, 1000]:,} for 1,000 steps, {growth[rule, 3000]:,} for 3,000 steps")
print("\nMultiplying two numbers, counted in single-bit additions")
print("(adding one at a time would take about 2 to the power of the number of bits):")
sweep = [("bits", "engine on repeated addition", "school method", "fast method", "engine / fast")] + [
    (f"{bits:,}", f"{d:,}", f"{s:,}", f"{f:,}", f"{d / f:.1f}") for bits, d, s, f in multiplying
]
widths = [max(len(r[i]) for r in sweep) for i in range(5)]
for r in sweep:
    print("  " + "  ".join(cell.ljust(w) for cell, w in zip(r, widths)))
print("\nPocket finder: all 256 rules, each tried with no knowledge of the rule")
described = {
    "direct": "proved: the engine runs the rule itself, from every start",
    "hidden rule 90": "proved: the whole row, from thinly spread starts",
    "count": "proved: the number of black cells, from every start",
    "blur": "proved: a blurred picture, from every start",
    "settles": "measured: in a loop within 20 ring-widths of steps, from 6 random starts on each of 3 ring sizes",
    "reuse, one cell": "measured: reaches step 1e18 within 100,000 table entries from one black cell",
    "reuse, patches": "measured: the same from every one of 12 random 40-cell patches",
}
for route in ROUTES:
    print(f"  {route.ljust(16)} {route_counts[route]:>3} rules   {described[route]}")
print("  the strongest thing found for each rule:")
for g in GROUPS:
    rules = grouped[g]
    listing = f": {rules}" if 0 < len(rules) <= 40 else ""
    print(f"    {g}: {len(rules)}{listing}")
print(f"  rules that fail from one cell: {sorted(set(range(256)) - has['reuse, one cell'])}")
print(f"  rules that fail from some patch: {sorted(set(range(256)) - has['reuse, patches'])}")
print(f"  rules that do not settle: {sorted(set(range(256)) - has['settles'])}")
print(f"  close to a budget (the finder disagrees with itself across mirror images): {borderline}")
print(f"  a whole-row formula exists but the finder did not find it: {missed}")
print("\nAll checks passed.")
