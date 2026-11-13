"""Translators: each turns one kind of pocket into the engine's common form.

A translator returns a Translation: the Pocket, how to carry a real state
into the pocket's form and back, and how many real steps of the system the
translator itself had to run. That last number is the translator's share of
the work; if it is large, the translator did the reducing, not the engine.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Sequence

from engine import Pocket, fast_forward


def _same(x):
    return x


def _always(_state):
    return True


@dataclass(frozen=True)
class Translation:
    pocket: Pocket
    encode: Callable[[Any], Any]  # real state -> pocket state
    decode: Callable[[Any], Any]  # pocket state -> the prediction
    steps_run: int                # real steps the translator ran
    period: int = 1               # real steps covered by one pocket step
    accepts: Callable[[Any], bool] = _always  # starting states the pocket holds for
    # What the prediction is a prediction of. None means the whole state; a
    # pocket that throws detail away predicts only this summary of the state.
    feature: Callable[[Any], Any] | None = None
    # For approximate pockets: close(predicted, actual) says whether the two
    # agree. None means the prediction must be exactly right.
    close: Callable[[Any, Any], bool] | None = None
    # For pockets whose cost is only known afterwards: work() reports how
    # many cache entries have been filled so far.
    work: Callable[[], int] | None = None
    # Real steps that `encode` itself runs before the pocket takes over, so
    # the pocket can only answer from this step on.
    lead: int = 0
    note: str = ""


def whole_state(translation: Translation) -> bool:
    """True if the pocket predicts the full state rather than a summary of it."""
    return translation.feature is None


def jump(translation: Translation, state, n: int, real_step=None, force: bool = False):
    """The prediction for n steps ahead, using the engine.

    If one pocket step covers several real steps, leftover real steps are run
    directly with `real_step`. A pocket that predicts only a summary has no
    full state to run them on, so it can only answer at whole pocket steps.
    """
    if not force and not translation.accepts(state):
        raise ValueError("this starting state is outside the pocket")
    if n < translation.lead:
        raise ValueError("this pocket only answers after its head start")
    pocket = translation.pocket
    whole, leftover = divmod(n - translation.lead, translation.period)
    if leftover and (real_step is None or not whole_state(translation)):
        raise ValueError("this pocket only answers at whole pocket steps")
    result = None
    if whole:
        result = fast_forward(pocket, whole)
        state = translation.decode(pocket.apply(result.obj, translation.encode(state)))
    elif translation.lead:
        state = translation.decode(translation.encode(state))
    elif not whole_state(translation):
        state = translation.feature(state)
    for _ in range(leftover):
        state = real_step(state)
    return state, result


def linear(matrix: Sequence[Sequence[int]], modulus: int | None = None) -> Translation:
    """Self-combining rules: next state = matrix times state.

    The step object is the matrix; combining two is matrix multiplication.
    """
    size = len(matrix)

    def reduce(x):
        return x % modulus if modulus else x

    def combine(a, b):  # "a then b" is the matrix product b * a
        return tuple(
            tuple(reduce(sum(b[i][k] * a[k][j] for k in range(size))) for j in range(size))
            for i in range(size)
        )

    def apply(m, state):
        return tuple(reduce(sum(m[i][k] * state[k] for k in range(size))) for i in range(size))

    def bits(m):
        return sum(max(1, x.bit_length()) for row in m for x in row)

    step = tuple(tuple(reduce(x) for x in row) for row in matrix)
    return Translation(Pocket(step, combine, apply, bits), _same, _same, 0)


def additive_ca(offsets: Sequence[int], width: int) -> Translation:
    """Self-combining rules (and nesting): a cellular automaton on a ring where
    each new cell is the XOR of the old cells at the given offsets.

    Rule 90 is offsets (-1, +1), rule 60 is (-1, 0), rule 150 is (-1, 0, +1).
    A state is an integer whose bit i is cell i. The step object is a mask
    saying which cells get XORed in; combining two masks, and applying a mask
    to a state, are the same operation (multiplication without carries,
    wrapped around the ring).
    """
    full = (1 << width) - 1

    def multiply(a, b):
        out = 0
        shift = 0
        while a:
            if a & 1:
                out ^= ((b << shift) | (b >> (width - shift))) & full
            a >>= 1
            shift += 1
        return out

    step = 0
    for d in offsets:
        step ^= 1 << ((-d) % width)
    return Translation(Pocket(step, multiply, multiply, lambda m: width), _same, _same, 0)


def cycling(step_fn: Callable[[Any], Any], start: Any, budget: int | None = None) -> Translation | None:
    """Repetition: run the system from `start` until a state repeats.

    The pocket's states are positions along the recorded path. The step
    object is a count of steps; combining two counts is addition that wraps
    around the loop once it is past the lead-in. With a budget, gives up
    (returns None) if no state has repeated within that many steps.
    """
    path = []
    seen = {}
    state = start
    while state not in seen:
        if budget is not None and len(path) >= budget:
            return None
        seen[state] = len(path)
        path.append(state)
        state = step_fn(state)
    lead_in = seen[state]
    period = len(path) - lead_in

    def wrap(k):
        return k if k < lead_in + period else lead_in + (k - lead_in) % period

    pocket = Pocket(
        step=1,
        combine=lambda a, b: wrap(a + b),
        apply=lambda k, position: wrap(position + k),
        size=lambda k: max(1, k.bit_length()),
    )
    return Translation(pocket, seen.__getitem__, path.__getitem__, len(path))


def _black(state: int) -> list[int]:
    """Positions of the black cells in a state."""
    cells = []
    position = 0
    while state:
        if state & 1:
            cells.append(position)
        state >>= 1
        position += 1
    return cells


def _shrink(rule: int, cells: list[int]) -> list[int]:
    """One step of an elementary rule on a row; the row comes back two cells shorter."""
    return [
        (rule >> (4 * cells[i - 1] + 2 * cells[i] + cells[i + 1])) & 1
        for i in range(1, len(cells) - 1)
    ]


@lru_cache(maxsize=None)
def emulation_scale(rule: int, max_scale: int = 4) -> int | None:
    """Smallest s for which the rule hides a copy of rule 90 at scale s.

    The claim checked: on any state whose black cells all sit in one class of
    positions mod 2s, running the rule for s steps gives the same result as
    one step of rule 90 on a grid s times coarser. A cell after s steps
    depends only on the 2s+1 cells around it, so trying every possible
    window proves the claim for all such states, of any size, for all time.
    """
    for s in range(1, max_scale + 1):
        if _emulates(rule, s):
            return s
    return None


def _emulates(rule: int, s: int) -> bool:
    spacing = 2 * s
    for centre in range(spacing):  # where the predicted cell sits; black class is 0
        slots = [i for i in range(spacing + 1) if (centre - s + i) % spacing == 0]
        for filled in range(1 << len(slots)):
            window = [0] * (spacing + 1)
            for k, slot in enumerate(slots):
                window[slot] = (filled >> k) & 1
            row = window
            for _ in range(s):
                row = _shrink(rule, row)
            expected = window[0] ^ window[-1] if centre == s else 0
            if row[0] != expected:
                return False
    return True


def sparse_nested(rule: int, width: int) -> Translation | None:
    """Nesting that depends on the starting state, not just the rule.

    Uses emulation_scale to find a hidden rule 90, then hands the engine
    rule 90 on the coarser grid. The pocket only holds for thinly spread
    starting states (see `accepts`), and one pocket step covers s real steps.
    Returns None if the rule has no such pocket or the ring width does not
    divide evenly.
    """
    s = emulation_scale(rule)
    if s is None or width % (2 * s):
        return None
    inner = additive_ca((-1, 1), width // s).pocket

    def accepts(state):
        cells = _black(state)
        return all((p - cells[0]) % (2 * s) == 0 for p in cells)

    def encode(state):
        cells = _black(state)
        offset = cells[0] % s if cells else 0
        small = 0
        for p in cells:
            small |= 1 << ((p - offset) // s)
        return (offset, small)

    def decode(pocket_state):
        offset, small = pocket_state
        state = 0
        for j in _black(small):
            state |= 1 << (offset + s * j)
        return state

    pocket = Pocket(
        step=inner.step,
        combine=inner.combine,
        apply=lambda mask, st: (st[0], inner.apply(mask, st[1])),
        size=inner.size,
    )
    return Translation(pocket, encode, decode, 0, period=s, accepts=accepts)


# --- rules the engine can run directly, in three kinds of arithmetic ---------

def spreading_ca(offsets: Sequence[int], width: int, black_wins: bool) -> Translation:
    """Self-combining rules where colour spreads instead of cancelling.

    black_wins=True: a new cell is black if ANY of the old cells at the given
    offsets is black (rule 254 is offsets -1, 0, +1). black_wins=False: a new
    cell is black only if ALL of them are (rule 128). The step object is the
    same kind of mask as in additive_ca; combining masks works the same way
    except that overlaps pile up instead of cancelling.
    """
    full = (1 << width) - 1

    def multiply(a, b):
        out = 0
        shift = 0
        while a:
            if a & 1:
                out |= ((b << shift) | (b >> (width - shift))) & full
            a >>= 1
            shift += 1
        return out

    def apply(mask, state):
        return multiply(mask, state) if black_wins else full ^ multiply(mask, full ^ state)

    step = 0
    for d in offsets:
        step |= 1 << ((-d) % width)
    return Translation(Pocket(step, multiply, apply, lambda m: width), _same, _same, 0)


def _rule_number(offsets, how):
    number = 0
    for index in range(8):
        cell = {-1: (index >> 2) & 1, 0: (index >> 1) & 1, 1: index & 1}
        number |= how([cell[d] for d in offsets]) << index
    return number


def _direct_rules():
    subsets = [(), (-1,), (0,), (1,), (-1, 0), (0, 1), (-1, 1), (-1, 0, 1)]
    table = {}
    for offsets in subsets:
        table[_rule_number(offsets, lambda v: sum(v) % 2)] = ("cancel", offsets)
    for offsets in subsets:
        if len(offsets) > 1:
            table[_rule_number(offsets, lambda v: int(any(v)))] = ("any", offsets)
            table[_rule_number(offsets, lambda v: int(all(v)))] = ("all", offsets)
    return table


# Elementary rule number -> how the engine can run it on every starting state.
DIRECT_RULES = _direct_rules()


def direct_rule(rule: int, width: int) -> Translation | None:
    """The translation for an elementary rule the engine can run directly."""
    if rule not in DIRECT_RULES:
        return None
    family, offsets = DIRECT_RULES[rule]
    if family == "cancel":
        return additive_ca(offsets, width)
    return spreading_ca(offsets, width, black_wins=(family == "any"))


# --- pockets that throw detail away ---------------------------------------

def conserved_count(rule: int, width: int) -> Translation | None:
    """Invariant: the number of black cells never changes.

    Proved by finding a flow J with  new cell - old cell = J(left, cell) -
    J(cell, right)  for all eight neighbourhoods; summed round a ring the
    flows cancel. The pocket system does nothing at all, so the engine is
    handed a step that leaves the count alone.
    """
    def f(a, b, c):
        return (rule >> (4 * a + 2 * b + c)) & 1

    flow = {(0, 0): 0, (0, 1): -f(0, 0, 1), (1, 0): f(1, 0, 0)}
    flow[(1, 1)] = f(1, 1, 0) - 1 + flow[(1, 0)]
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                if f(a, b, c) - b != flow[(a, b)] - flow[(b, c)]:
                    return None

    def count(state):
        return state.bit_count()

    idle = Pocket(step=0, combine=lambda a, b: 0, apply=lambda obj, x: x, size=lambda obj: 1)
    return Translation(idle, count, _same, 0, feature=count,
                       note="predicts only the number of black cells")


@lru_cache(maxsize=None)
def coarse_search(rule: int, max_block: int = 3) -> list[tuple[int, int, int]]:
    """Every exact blurred version of an elementary rule, as (block, P, coarse rule).

    P turns each block of cells into one coarse cell (bit b of P is the coarse
    colour of block b). The claim checked: blurring after `block` real steps
    equals one step of the coarse rule on the blurred state, for EVERY state.
    A block after `block` steps depends only on itself and its two neighbours,
    so trying all windows of three blocks proves it.
    """
    found = []
    for block in range(2, max_block + 1):
        blocks = 1 << block
        windows = []
        for w in range(1 << (3 * block)):
            row = [(w >> i) & 1 for i in range(3 * block)]
            for _ in range(block):
                row = _shrink(rule, row)
            out = sum(bit << i for i, bit in enumerate(row))
            windows.append((w & (blocks - 1), (w >> block) & (blocks - 1), w >> (2 * block), out))
        for P in range(1, (1 << blocks) - 1):  # skip the two blurs that ignore the state
            coarse = [None] * 8
            for left, mid, right, out in windows:
                key = 4 * ((P >> left) & 1) + 2 * ((P >> mid) & 1) + ((P >> right) & 1)
                value = (P >> out) & 1
                if coarse[key] is None:
                    coarse[key] = value
                elif coarse[key] != value:
                    break
            else:
                found.append((block, P, sum(v << k for k, v in enumerate(coarse))))
    return found


STILL_RULES = (204, 170, 240)  # coarse rules that only freeze or shift the picture
EMPTY_RULES = (0, 255)         # coarse rules that say "this pattern never appears"


def coarse_grained(rule: int, width: int, max_block: int = 3) -> Translation | None:
    """Exact blurring: the engine runs the coarse rule and predicts the blurred state.

    Prefers a coarse rule that actually moves over one that freezes or shifts.
    Returns None if no blurred version exists that the engine can run.
    """
    usable = [
        (g in STILL_RULES, block, P.bit_count(), P, g)
        for block, P, g in coarse_search(rule, max_block)
        if g in DIRECT_RULES and g not in EMPTY_RULES and width % block == 0
    ]
    if not usable:
        return None
    _, block, _, P, g = min(usable)  # among equals, the blur with fewest black blocks
    blocks = 1 << block

    def blur(state):
        coarse = 0
        for j in range(width // block):
            if (P >> ((state >> (j * block)) & (blocks - 1))) & 1:
                coarse |= 1 << j
        return coarse

    black = [format(b, f"0{block}b")[::-1] for b in range(blocks) if (P >> b) & 1]
    return Translation(
        direct_rule(g, width // block).pocket, blur, _same, 0, period=block, feature=blur,
        note=f"blocks of {block}; coarse cell is black for {black}; coarse rule {g}",
    )


def diffusion(moves: dict[int, float], width: int) -> Pocket:
    """Self-combining rule in ordinary arithmetic: a spread of probability
    over a ring, where `moves` gives the chance of each move per step.

    The step object is that spread; combining two is the same wrap-around
    multiplication as in additive_ca, with real numbers in place of XOR.
    """
    def multiply(a, b):
        out = [0.0] * width
        for i, x in enumerate(a):
            if x:
                for j, y in enumerate(b):
                    out[(i + j) % width] += x * y
        return out

    step = [0.0] * width
    for move, chance in moves.items():
        step[move % width] += chance
    return Pocket(step, multiply, multiply, lambda obj: 64 * width)


def averaged_walk(width: int, walkers: int) -> Translation:
    """Averaging out: a crowd of random walkers on a ring.

    Where any one walker ends up is not predicted. The share of the crowd in
    each cell is, by the spread a single walker's chances follow. The match
    is only approximate; `close` allows five times the expected sampling
    noise plus three walkers.
    """
    def shares(positions):
        counts = [0] * width
        for p in positions:
            counts[p] += 1
        return [c / walkers for c in counts]

    def close(predicted, actual):
        return all(
            abs(a - p) <= 5 * (max(p * (1 - p), 0.0) / walkers) ** 0.5 + 3 / walkers
            for p, a in zip(predicted, actual)
        )

    return Translation(diffusion({1: 0.5, -1: 0.5}, width), shares, _same, 0,
                       feature=shares, close=close,
                       note="predicts the share of walkers in each cell, within sampling noise")
