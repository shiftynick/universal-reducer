"""The pocket finder: try every automatic route on a rule, knowing nothing about it.

Given only the number of an elementary rule, `find` tries each translator
that needs no human insight and reports what it found. Two kinds of route:

  proved    A small exhaustive check that holds for every size and all time
            (direct, hidden rule 90, count, blur).
  measured  An experiment within a budget, on particular sizes and starts
            (settles, reuse). A pass is evidence, not a guarantee, and the
            budgets below are a choice: a few rules sit close to them.

The measured routes need nothing designed for a particular family of rules,
so `measured` also takes rules with a wider neighbourhood (radius 2).

Every pocket found goes through the same engine as everything else.
"""

from dataclasses import dataclass
from random import Random

from reuse import OverBudget, reuse_line
from translators import (
    DIRECT_RULES, EMPTY_RULES, STILL_RULES, coarse_grained, coarse_search, conserved_count,
    cycling, emulation_scale, jump,
)

FAR = 10**18
REUSE_BUDGET = 100_000        # table entries allowed for a jump to step FAR
PATCHES = 12                  # random patches tried; every one must succeed
RING_WIDTHS = (61, 122, 244)  # for the "settles" route
SETTLE_WITHIN = 20            # ring-widths of steps allowed before the row must be in a loop
RING_STARTS = 6               # random starts per ring size; every one must settle
ONE_CELL = (0, 1)


@dataclass(frozen=True)
class Found:
    route: str
    starts: str     # the starting states it holds for
    predicts: str
    proved: bool
    detail: str = ""


def ring_step(rule: int, width: int, radius: int = 1):
    """One step of a rule on a ring, all cells at once."""
    full = (1 << width) - 1
    span = 2 * radius + 1
    cases = [[(index >> (span - 1 - j)) & 1 for j in range(span)]
             for index in range(1 << span) if (rule >> index) & 1]

    def step(cells):
        # planes[j] holds, for every cell at once, its j-th neighbour counting from the left
        planes = [((cells << d) | (cells >> (width - d))) & full for d in range(radius, 0, -1)]
        planes.append(cells)
        planes += [((cells >> d) | (cells << (width - d))) & full for d in range(1, radius + 1)]
        inverse = [~plane for plane in planes]
        out = 0
        for wanted in cases:
            term = full
            for j, black in enumerate(wanted):
                term &= planes[j] if black else inverse[j]
            out |= term
        return out
    return step


def mirror(rule: int) -> int:
    """The same rule with left and right swapped."""
    return sum(((rule >> (4 * (i & 1) + (i & 2) + (i >> 2))) & 1) << i for i in range(8))


def twin(rule: int) -> int:
    """The same rule with black and white swapped."""
    return sum((1 - ((rule >> (7 - i)) & 1)) << i for i in range(8))


def patch(rng: Random):
    """A random 40-cell patch on the endless white line."""
    return (rng.randrange(-50, 50), rng.getrandbits(40) | 1 | (1 << 39))


def settles(rule: int, rng: Random, radius: int = 1) -> float | None:
    """From random starts on rings of three sizes, does the row always fall
    into a loop within SETTLE_WITHIN ring-widths of steps? Returns the worst
    case seen, in ring-widths, or None as soon as one start runs past it."""
    worst = 0.0
    for width in RING_WIDTHS:
        step = ring_step(rule, width, radius)
        for _ in range(RING_STARTS):
            translation = cycling(step, rng.getrandbits(width), budget=SETTLE_WITHIN * width)
            if translation is None:
                return None
            worst = max(worst, translation.steps_run / width)
    return worst


def reaches(rule: int, start, radius: int = 1) -> int | None:
    """Table entries reuse fills jumping to step FAR from this start, or None
    if it passes the budget."""
    _, counting, world = reuse_line(rule, REUSE_BUDGET, radius)
    try:
        jump(counting, start, FAR)
    except OverBudget:
        return None
    return world.filled


def find(rule: int, rng: Random) -> list[Found]:
    found = []
    if rule in DIRECT_RULES:
        family, offsets = DIRECT_RULES[rule]
        found.append(Found("direct", "every start", "the whole row", True,
                           f"the engine runs the rule itself ({family}, neighbours {offsets})"))
    scale = emulation_scale(rule)
    if scale:
        found.append(Found("hidden rule 90", "thinly spread starts", "the whole row", True,
                           f"at scale {scale}"))
    if conserved_count(rule, 96):
        found.append(Found("count", "every start", "the number of black cells", True))
    if rule not in DIRECT_RULES:
        targets = {coarse for _, _, coarse in coarse_search(rule)}
        runnable = {g for g in targets if g in DIRECT_RULES and g not in EMPTY_RULES}
        if runnable:
            moves = bool(runnable - set(STILL_RULES))
            found.append(Found("blur", "every start",
                               "a blurred picture" if moves else "a blurred picture that only freezes or shifts",
                               True, coarse_grained(rule, 96).note))
    return found + measured(rule, rng)


def measured(rule: int, rng: Random, radius: int = 1) -> list[Found]:
    """The routes that need no design: watching for a loop, and reuse."""
    found = []
    worst = settles(rule, rng, radius)
    if worst is not None:
        found.append(Found("settles", "random starts on a ring", "the whole row", False,
                           f"in a loop within {worst:.1f} ring-widths of steps"))
    entries = reaches(rule, ONE_CELL, radius)
    if entries is not None:
        found.append(Found("reuse, one cell", "one black cell on an endless line", "the whole row",
                           False, f"{entries:,} table entries to reach step 1e18"))
    most = 0
    for _ in range(PATCHES):
        entries = reaches(rule, patch(rng), radius)
        if entries is None:
            break
        most = max(most, entries)
    else:
        found.append(Found("reuse, patches", "random 40-cell patches on an endless line",
                           "the whole row", False, f"at most {most:,} table entries to reach step 1e18"))
    return found


ROUTES = ("direct", "hidden rule 90", "count", "blur", "settles", "reuse, one cell", "reuse, patches")
GROUPS = (
    "the whole row from crowded random starts",
    "the whole row, but only from small patches on a blank line",
    "the whole row, but only from special starts",
    "a summary only",
    "nothing",
)


def group(found: list[Found]) -> str:
    """The strongest thing the finder got for a rule."""
    routes = {f.route for f in found}
    if routes & {"direct", "settles"}:
        return GROUPS[0]
    if "reuse, patches" in routes:
        return GROUPS[1]
    if routes & {"hidden rule 90", "reuse, one cell"}:
        return GROUPS[2]
    if routes:
        return GROUPS[3]
    return GROUPS[4]
