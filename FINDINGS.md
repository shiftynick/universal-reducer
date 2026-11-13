# Can one algorithm exploit every pocket of reducibility?

Findings as of 13 November 2026. Every number here comes from the code in this folder and can be reproduced; see "Running it" at the end.

## The question

Stephen Wolfram's idea of computational irreducibility says that for many systems the only way to learn what they do at step n is to run all n steps. Where a shortcut does exist, he calls it a pocket of reducibility.

The question explored here: **can every pocket, from any system, be translated into one common form, so that a single fixed algorithm performs the shortcut?**

Terms as used throughout:

- A **reducer** predicts the state at step n faster than running n steps. Predicting the whole state, one exact feature of it, or an approximate summary all count.
- A **translator** rewrites one system's pocket into the common form. Finding the translation is treated as a separate job from carrying out the shortcut.
- **Universal** was meant in the strongest sense: any system, every pocket, and as good as any reducer built specially for the job.

One answer is true but hollow. Any shortcut is a program, so "an algorithm that runs any program" is a universal reducer that does none of the reducing itself. The useful question is how much of the work one small algorithm can do and how much is left to the translator. The test agreed at the start: if the common form has to grow into "run any program", the result is hollow.

## The short answer

Not in the strongest sense, as far as these tests show.

- **One form does stretch across many kinds of pocket.** Seven kinds fit a single form, and the algorithm's code never changed. The form itself needed seven additions along the way.
- **The algorithm often does little of the reducing.** The insight that makes each pocket work always sat in the translator. In one case the translator ran the real steps itself, and in another the algorithm was idle.
- **It is not as good as a specialised reducer.** Fast multiplication beats it by a margin that keeps growing, and only fits the form with the algorithm idle.
- **Finding pockets automatically works by noticing repeats.** That found a pocket for 96% of the simplest family of rules but about 66% of a larger family. Pockets that rest on a formula were found only inside families of formulas a person had already designed.

## Method

The single algorithm is doubling, in [engine.py](engine.py). It is given a "step object" that stands for "advance one step" and a way to combine two such objects into "do one, then the other". It builds objects for 2, 4, 8 steps and so on, and reaches step n in at most about twice as many combines as n has binary digits. Step 10^18 takes 82.

A translator supplies four things: the step object, how to combine two of them, how to carry one out on a state, and how large one is.

Kinds of pocket were added one at a time, starting from a catalogue of eight: repetition, nesting, self-combining rules, disguise, invariants, compressible states, averaging out, and emergent objects. For each, the scoreboard records what had to be added to the common form. Every result was checked against running the system step by step.

Most test systems are elementary cellular automata: a row of black and white cells in which each cell's next colour depends on itself and its two neighbours. There are 256 such rules, known by number. A "ring" is a row with its ends joined.

## Scoreboard

| Kind of pocket | Example tested | Added to the form | Result |
|---|---|---|---|
| Self-combining rules | Fibonacci numbers; rules 60, 90, 128 and 150 on a ring of 101 cells | Nothing | Fits. 16 of the 256 rules can be run this way from every start. |
| Repetition | Rule 30 on a ring of 18 cells | A map between real states and pocket states | Fits, but the translator ran 3,569 real steps to find the loop, so it did the real work. |
| Nesting that depends on the start | Rules 18 and 22 | A condition on the starting state; several real steps per pocket step | Fits. Nine rules hide a copy of rule 90 when the black cells are thinly spread. A crowded start is correctly refused. |
| Invariants | The number of cars in rule 184, a traffic model | A feature: the pocket predicts one number, not the state | Fits, with the algorithm idle. Five rules keep their count of black cells. |
| Blurring | Rule 146, which is chaotic, blurs exactly to rule 128 in blocks of three cells | Nothing new | Fits. 35 rules have an exact blurred version that moves and that the algorithm can run. |
| Averaging out | 20,000 random walkers on a ring of 51 cells | A tolerance: how close counts as right | Fits. The largest gap was 3.8 times the expected sampling noise, and a drifting crowd correctly fails. |
| Reuse | Rules 90, 126 and 110 from one black cell on an endless line | Recipes and a cache; later a head start | Fits in a weaker sense; see below. |
| Clever algorithms | Multiplying two large numbers | Nothing would do | Does not fit; see below. |

## Two routes under one form

The first six kinds are the **formula route**. The translator proves that the pocket exists and hands over a finished small object. The cost is known in advance, and each kind needs its own translator.

Reuse is the **memory route**, in [reuse.py](reuse.py). It follows the idea behind the Hashlife algorithm: store the row as a tree of pieces with identical pieces stored once, and remember the result of advancing each piece. Where the pattern repeats in space or time, no work is done twice. One translator serves every rule and is given no proof and no knowledge of the rule.

The price is that the step object is no longer a finished thing. It is a recipe ("this, then that"), and all the work happens when the recipe is applied. The cost is known only afterwards, as the number of cache entries filled.

| | Formula route | Memory route |
|---|---|---|
| Translator | One per kind, and it must prove the pocket | One for all rules, and it knows nothing |
| Cost | Known in advance | Known only afterwards |
| When there is no pocket | It refuses | It fills memory until stopped |

Reuse reached step 10^18 from one black cell with 436 cache entries for rule 90, 910 for rule 126 and 53,065 for rule 110. Rule 30 gets no help: 23,269 entries for 1,000 steps and 119,612 for 3,000 steps, against 63 and 79 for rule 90.

Neither route covers the other. The memory route cannot do Fibonacci or averaging. The formula route cannot find a pocket nobody has proved.

## Where the form breaks: fast multiplication

Multiplying is adding a number to itself many times. Given only that, the algorithm turned about 10^3,010 additions into about 15,000 combines for two 10,000-bit numbers. That is the school method of multiplication, which it arrived at by itself.

Karatsuba's fast method gets the same product with less work, and the gap grows: 7 times less at 1,000 bits, 18 times at 10,000 and 47 times at 100,000, counted in single-bit additions.

The fast method only goes through the algorithm as a single step, with the whole method inside the translator and the algorithm idle. The reason offered: doubling works along a chain, where a jump of 2k steps is two copies of the same k-step jump, worked out once. The fast method splits one product into three different smaller products, which do not collapse into one. The only change that would admit it is letting the translator say how to split a problem and merge the answers, and an algorithm that accepts that runs any program.

The fast method was also already hiding inside the first row of the scoreboard. Exact Fibonacci multiplies huge numbers with Python's built-in multiplication, which is itself a fast method.

## Can finding the translator be automated?

[finder.py](finder.py) takes a rule number and tries every route that needs no human insight. Four routes carry a proof (direct, hidden rule 90, count, blur). Two are measurements within a budget: watching for the row to settle into a loop, and reuse.

On all 256 elementary rules it found a pocket for 245.

| Strongest thing found for a rule | Rules |
|---|---|
| The whole row, from crowded random starts | 221 |
| The whole row, but only from a small patch on a blank line | 15 |
| The whole row, but only from special starts such as one black cell | 9 |
| Nothing | 11 |

- **Most rules are simply tame.** 217 of the 221 settle into a loop quickly.
- **Chaotic rules turned predictable from small starts.** Rules 18, 122, 126, 146 and 182 are chaotic from a crowded start, yet reuse reached step 10^18 from every one of 12 random 40-cell patches.
- **Nothing found** for rule 30's family (30, 86, 135, 149), rule 45's family (45, 75, 89, 101), and rules 73, 169 and 225. This is not proof that no pocket exists. Whether rule 30 has one is an open problem that Wolfram has put prize money on.
- **It missed formulas a person knows.** Rules 105, 153, 165 and 195 are additive rules with the output colour flipped, so an exact formula exists from every start. The finder got only a blurred version and the small-patch pocket.
- **Formulas were found only where someone had looked.** The proof-carrying routes found something for 97 rules, each inside a family of formulas designed by hand in the earlier steps.

The two routes that need no design were then run on a larger family, in [wider.py](wider.py): rules where each cell looks at two neighbours on each side, of which there are about four billion.

| Family | Settles into a loop | Restless, but reducible from every small patch | Restless, reducible only from one cell | Nothing found |
|---|---|---|---|---|
| Elementary (all 256) | 85% | 7% | 4% | 4% |
| Wider, depending only on the number of black cells (all 64) | 53% | 6% | 20% | 20% |
| Wider, random (300 sampled) | 38% | 12% | 16% | 34% |

The high success rate on elementary rules was largely a fact about how tame they are. The middle column holds up: rules that never settle, yet are predictable from any small patch tried, are no rarer in the larger family.

## Limits, and what was not verified

- **Success cannot prove universality.** It can only show how far one form stretches and where it stops.
- **"Does not fit" is not a proof.** For fast multiplication it rests on the reasoning above and a failed search for a fit.
- **The world tested is small.** Apart from Fibonacci, random walkers and multiplication, every test was on one-dimensional, two-colour cellular automata.
- **Emergent objects were never tested on their own.** Gliders and the like would mean moving to two dimensions. This is the one kind in the catalogue left untried.
- **The catalogue came from memory, not a literature search.** It lists the kinds of pocket people have found, and people find the kinds they already have tricks for.
- **The measured routes depend on chosen budgets.** A few rules sit close to them. Rule 110's family settles on rings up to 244 cells, but slowly, and one start on a 976-cell ring had not settled after 200 ring-widths of steps, so it is counted as not settling. Rule 41's family lands on both sides of the settling limit.
- **The patch test is all-or-nothing.** In a separate run, rules 54, 137 and 147 passed 10 of 12 patches and rule 73 passed 5 of 12, yet they sit in the bottom two rows of the census.
- **Jumps to step 10^18 cannot be checked by running the system.** They are checked by step-by-step running for the first few thousand steps, by known formulas for the number of black cells (rules 18, 90, 105 and 150), and by testing that a jump of a+b steps equals a jump of a steps followed by one of b.
- **The wider family is only partly checked.** The sample of 300 gives an error of about 5 percentage points either way. Of the 36 restless-but-reducible random rules, 8 were confirmed against step-by-step running to step 1,500. The formula routes were not run on wider rules at all, so "nothing found" there includes any rule with a formula nobody looked for.
- **A claim about rule 110 was not confirmed.** Early on it was said that Israeli and Goldenfeld (2004) found predictable blurred versions of rule 110. The search here found none for blocks of two to four cells, and at five cells only a trivial one. Their paper was not checked.
- **The random walkers used a random number generator**, not a system whose own details average out.

## Open directions

- Emergent objects, by trying reuse on a two-dimensional system such as the Game of Life.
- A search for formulas on the wider rules, to learn how much of the 34% is truly without a pocket.
- Whether formula-type pockets can be found without a person first choosing the family of formulas to search.

## Running it

Needs Python 3.10 or later and nothing else.

- `python3 run.py` checks every pocket against step-by-step running, then prints the scoreboard and the census of all 256 rules. About 20 seconds.
- `python3 wider.py` runs the experiment on the larger family. About six minutes.

| File | What it holds |
|---|---|
| [engine.py](engine.py) | The single algorithm. Unchanged since the first step. |
| [translators.py](translators.py) | The common form and the translators of the formula route. |
| [reuse.py](reuse.py) | The memory route. |
| [clever.py](clever.py) | Multiplication three ways. |
| [finder.py](finder.py) | The pocket finder. |
| [run.py](run.py) | All checks, the scoreboard and the census. |
| [wider.py](wider.py) | The larger family of rules. |
