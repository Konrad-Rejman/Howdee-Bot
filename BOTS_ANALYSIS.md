# Tournament Bot Analysis

A plain-English breakdown of every bot in the tournament (the entries in `bots/`, plus
`Howdee-Bot` from `logic.py`): what each one does, what it got right, and what could be
improved. Written so that anyone — whatever bot they wrote — can understand the field and
learn from it.

> Quick orientation on the engine: `phevaluator`'s `evaluate_cards(...)` returns a
> number where **lower = stronger** (1 = Royal Flush, 7462 = worst high card). The
> `HandRank` enum works the same way (lower value = better). It's easy to get the
> comparison backwards.

---

## The shared vocabulary (simple level)

Almost every bot is built from the same handful of ideas. If you understand these five,
you understand all the bots:

| Concept | What it means | How bots use it |
|---|---|---|
| **Equity** | Your % chance of winning the hand if it went to showdown right now | The single most important number — drives bet/call/fold |
| **Pot odds** | `to_call / (pot + to_call)` — the price you're being offered | Call only when your equity beats the price |
| **Position** | Are you "on the button" (act last) or not? | Acting last = more info = play more hands |
| **Hand range** | The *set* of hands a player would play this way | Lets you guess what the opponent has |
| **Aggression / tendencies** | Is the opponent passive or a maniac? Can they fold? | Adapt: bluff folders, value-bet stations |

The bots mainly differ in **how they estimate equity** (Monte Carlo vs. lookup tables vs.
hand categories), **how much they adapt** to the opponent, and whether they play a
**fixed** or a **randomized** strategy.

---

## 1. CrAAcked (ALL-IN) — `bots/craacked.py`

**One line:** Goes all-in. Every single hand. No exceptions.

### How it works
The `move()` method does some (buggy) opponent-aggression bookkeeping and then just
`return Move.ALL_IN`. All the sophisticated-looking strategy methods below it
(`SBpreFlopAction`, `BBPostFlopAction`, hand ranges, etc.) are **dead code — never called**.

### What it did right
- **It exploits the field.** In testing this bot *wins the most*. That's the real lesson:
  most of the other bots fold far too often, so relentless pressure prints money against them.
- **Free speed** — sub-microsecond decisions, never times out, never crashes.
- Shows that a "dumb" strategy that targets a population's weakness can beat "smart" bots.

### What could be improved
- **It has no actual edge.** The moment it's called, it's at best a coin flip and usually
  behind (a thinking opponent only calls with hands that *beat* a random shove). A single
  opponent that calls all-ins with, say, the top ~15% of hands turns this into a losing bot.
- It's a **meta-exploit, not a strategy** — it ranks #1 only because the rest of the field is
  too tight. Beatable by design.
- The dead code is a maintenance trap (someone will think the bot is doing all that).

---

## 2. CrAAcked (REAL) — `bots/craacked.py`

**One line:** The "proper" version — range-based preflop, equity-based postflop — but
sabotaged by bugs.

### How it works
Classifies the starting hand into tiers (`UltraPremiums`, `premiums`, `Playable`, `weak`),
plays position-aware preflop lines (small-blind vs big-blind), and postflop bets sized by an
enumerated equity estimate.

### What it did right
- **Good intentions / structure:** separate preflop tiers, separate SB/BB logic,
  bet sizing that scales with hand strength and opponent aggression. This is the right
  *shape* for a poker bot.

### What could be improved (this bot finishes near the bottom — the bugs are why)
- **Hand keys aren't normalized.** `key = cards[0][0] + cards[1][0]` — if the cards arrive
  as `K, A` the key is `"KA"`, which is in *none* of the lists, so the function returns
  `None` → illegal move → **forced fold**. Roughly half of all hands are misread. Fix:
  always order high-card-first (`"AK"`).
- **Broken range lists.** Missing commas make adjacent strings concatenate
  (`"T5" "98"` → `"T598"`), so chunks of the `Playable` range silently vanish.
- **Functions fall through to `None`.** Several branches (e.g. equity exactly on a threshold)
  return nothing → illegal move → fold. Every code path must return a legal move.
- **Float bet sizes** (`min_bet * (1 + ...)`) — risky; bet amounts should be `int`.
- **Equity is category-only and slow.** It compares *hand categories* (all one-pairs look
  equal) and enumerates ~2,700 combos per call **without dealing future community cards** —
  both inaccurate and far too slow.

**General takeaway:** great architecture is worthless if a return path can yield `None` or a
mis-keyed hand. Always normalize inputs and guarantee a legal return.

---

## 3. Azalea — `bots/azalea.py`

**One line:** The most complete "real poker" bot in the field.

### How it works
Monte Carlo equity that **deals out the rest of the board** (true equity, not just current
strength), detects flush and straight draws (open-ended vs gutshot), profiles the opponent
from hands they've shown, and makes pot-odds-aware decisions with pot-proportional bet sizing.
Clearly separated preflop and postflop logic.

### What it did right
- **Proper equity** — simulates future cards, so a flush draw is correctly valued as having
  outs rather than as a weak high card.
- **Draw awareness** — semi-bluffs and defends draws at the right price.
- **Pot-odds discipline** — defend/call thresholds are derived from the price, not guessed.
- **Position + opponent profiling** — adjusts thresholds for tight/loose opponents.
- Heuristics are **clamped and centralized**, which makes them tunable.

### What could be improved
- **Speed.** Only 48–96 samples per decision, and it still risks blowing the ~1ms budget;
  it's one of the slower bots. Sample count is also low enough to make equity **noisy**.
- **Magic numbers everywhere** (`0.84`, `0.66`, `0.46`…) — hand-tuned, not derived, so they
  may be over-fit to whatever it was tested against.
- **Thin opponent model** — only averages the *preflop* strength of shown hands; ignores
  bet-sizing and frequency tells.
- Against the all-in bot it still loses chips it shouldn't, suggesting its calling ranges vs.
  extreme aggression are too tight.

---

## 4. Ultra-Adaptive-duoduo — `bots/duoduo.py`

**One line:** Monte Carlo equity + "bluff-catcher" that calls down maniacs.

### How it works
400-iteration Monte Carlo equity, tracks opponent aggression as a running ratio, and has a
dedicated **river bluff-catch** mode: if the opponent is aggressive and shoves the river while
the bot has modest equity, it calls. Value-raises strong hands (jams into maniacs), steals
occasionally vs. passive players.

### What it did right
- **Real equity** (with runouts) and a genuinely good adaptive idea: *call down players who
  over-bluff*. Bluff-catching is an advanced concept most of the field ignores.
- Adjusts behavior by opponent aggression rather than playing a fixed style.

### What could be improved
- **Way too slow** — 400 iterations *and* a full `random.shuffle` of the deck on every single
  decision. This is the heaviest per-move cost in the field and will overrun the time budget.
  Drop to ~100–150 samples and use `random.sample` instead of shuffling.
- **Hand-wavy pot odds** — the bluff-catch uses `min_bet / (min_bet + max_bet)` as "pot odds,"
  which isn't really pot odds. It should reconstruct the actual pot from `round_history`.
- **Crude preflop formula** (`r1 * 1.6 + r2 ...`) with arbitrary constants.
- **No position awareness**, and value-bet sizing is a fixed fraction of the stack.

---

## 5. Long Story Short, Its over — `bots/long_story_short.py`

**One line:** Solid, well-rounded heuristic bot — stack-aware, tendency-aware, pot-odds-aware.

### How it works
Preflop hand-strength score; postflop sampled equity (200 samples). Classifies the opponent as
tight/loose/neutral from the *quality of hands they show at showdown*, adjusts calling
thresholds accordingly, shoves when short-stacked with a decent hand, and folds clearly weak
preflop hands. Detects position and bluffs selectively.

### What it did right
- **Clean, readable structure** that ties together the right ideas: equity, pot odds, opponent
  tendency, stack depth, and position.
- **Tendency-adjusted thresholds** — calls wider vs. loose players, tighter vs. tight players.
- **Stack awareness** — switches to a shove-or-fold gear when short, which is correct poker.

### What could be improved
- **Equity bug:** `if my_rank <= opp_rank: wins += 1` counts a tie as the *opponent* winning,
  systematically **under-estimating** equity (and the comparison direction reads as "wins" but
  is really counting losses). This makes the bot too timid.
- **Equity ignores future cards** — it only samples the opponent's two cards against the
  *current* board, so draws are undervalued.
- **Bet sizing is mostly fixed** (`min_bet * 3`, `200`, `150`) rather than pot-proportional, so
  it's readable and easy to exploit.
- Position detection (`len(round_history) == 2`) is fragile and breaks on non-standard lines.

---

## 6. THÊ Jokêrs — `bots/jokers.py`

**One line:** The fast, exploit-driven bot — no Monte Carlo, bluffs *only* opponents who fold.

### How it works
Skips Monte Carlo entirely: it maps the `phevaluator` rank into a 0–100 **strength bucket**
(quads = 95, two pair = 70, …) for instant decisions. Tracks **whether the opponent is even
capable of folding**, and only fires pure bluffs against opponents who do. Separates *pure
bluffs* (air) from *semi-bluffs* (draws), and handles all-ins via pot odds.

### What it did right
- **Genuinely fast** — comfortably inside the 1ms budget while everyone else struggles. Smart
  engineering trade-off.
- **Best adaptive idea in the field:** *don't bluff a calling station.* Detecting fold capacity
  and gating bluffs on it is exactly how you beat both random and thinking opponents.
- Distinguishes pure bluff from semi-bluff — conceptually correct.

### What could be improved
- **"Equity" is just the strength bucket** (`equity = strength / 100`). A flush draw reads as a
  weak high card, so it under-defends and under-semi-bluffs draws. A cheap real-equity estimate
  (even ~50 samples) would help a lot.
- **Semi-bluff is detected by strength bucket, not actual draws** — it bets "medium" hands and
  calls them draws, which isn't the same thing.
- **Preflop equity is capped at 0.60**, so it never properly values premiums like AA preflop.
- The fold-detection reset (`% 50 hands`) can make it re-learn the opponent repeatedly.

---

## 7. Howdee-Bot — `logic.py`

**One line:** The only bot playing a deliberately **randomized (mixed) strategy** — it rolls
weighted dice over its legal moves instead of picking one deterministically.

### How it works
Estimates a 0–1 hand strength from the **hand category plus a high-card bonus**
(`0.8 * category + 0.2 * card_value`), buckets it into three tiers (weak `< 0.33`, medium
`< 0.66`, strong otherwise), and each tier carries a table of **weights** over the six moves.
It then nudges the weights toward aggression (doubles bet/raise, ×1.5 all-in, halves fold) and
finally picks a move at random in proportion to those weights (`random.choices`). Bet size
blends a stack-fraction term with a pot-fraction term, both scaled by strength.

The per-tier weight tables aren't hand-guessed — they were **fitted with a regression model
trained against the Rocky and Random example bots**, so each tier's mix is empirically tuned to
maximise results versus those two opponents.

### What it did right
- **Fast** — like Jokers, it's a category lookup with no Monte Carlo, so it's well inside the
  1ms budget.
- **Hard to read / hard to exploit.** A randomized strategy has no fixed fold pattern, so
  opponents that try to model it (e.g. Jokers' "can this player fold?" detector) get confused.
  Mixing your actions is a legitimate game-theory idea most of the field never attempts.
- **Built-in aggression bias** (more betting, less folding), which — as the all-in bot proves —
  is exactly what beats an over-folding field. It also keeps meaningful call/all-in weight even
  in the weak tier, so it isn't easily farmed by a jam-bot.
- **Always returns a legal move** (it filters the weights down to `valid_moves`). Robust.

### What could be improved
- **It doesn't compute real equity.** Strength is hand-category + high-card bonus, with no
  draws and no future cards. Preflop it only distinguishes *pair vs. non-pair*, so `72o` and
  `AKs` look almost identical (separated only by the small card bonus) — preflop hand selection
  is very crude.
- **No pot odds.** Calls and folds come from fixed random weights regardless of the bet size,
  so it calls big bets too freely with weak hands and sometimes folds to tiny ones. Tying the
  call/fold weights to `to_call` vs. the pot would be the single biggest upgrade.
- **The weights are tuned to a narrow, weak opponent set.** They were fitted by regression
  against only the Rocky and Random bots — both extremely exploitable — so they're at risk of
  **overfitting** to that population and may not transfer to stronger, adaptive opponents.
  Re-fitting (or at least validating) against the full tournament field would make them far
  more trustworthy. Randomness also cuts both ways under any weighting: in the strong tier the
  bot can randomly just `CHECK`/`CALL` a monster (leaving value on the table), and in the weak
  tier it can still occasionally shove trash.
- **No position and no opponent modeling.** `self.hands_shown` is available but unused, so it
  can't bluff-catch maniacs or pressure folders the way DuoDuo and Jokers do.
- **Pot estimate is rough** — `sum(amount for _, amount in round_history)` adds up cumulative
  commitments, which isn't the true pot (the same pot-reconstruction issue several bots share).

---

## Cross-cutting lessons (what the whole field teaches)

| Theme | Who did it well | Who to learn the mistake from |
|---|---|---|
| **Always return a legal move** | Jokers, Azalea, Howdee-Bot | CrAAcked (REAL) (returns `None` → forced folds) |
| **Normalize your inputs** (hand keys, card order) | Azalea (uses rank values) | CrAAcked (REAL) (`"KA"` ≠ `"AK"`) |
| **Equity must include future cards** | Azalea, DuoDuo | Long Story Short, Jokers, Howdee-Bot (current board only) |
| **Respect the ~1ms budget** | Jokers, Howdee-Bot (no Monte Carlo) | DuoDuo (400 iters + shuffle), Azalea |
| **Use real pot odds, not guesses** | Azalea, Long Story Short | DuoDuo (`min_bet/(min_bet+max_bet)`), Howdee-Bot (none) |
| **Adapt to the opponent** | Jokers (fold detection), DuoDuo (bluff-catch) | CrAAcked (ALL-IN), Howdee-Bot (ignore opponent) |
| **Mix your actions to avoid being read** | Howdee-Bot (randomized) | Every deterministic bot |
| **Aggression beats over-folding** | CrAAcked (ALL-IN), Howdee-Bot | The tight callers they crush |

### The single biggest insight
The bot that *wins* this field is the one that just **goes all-in every hand**. That's not
because jamming is good poker — it's because **the rest of the field folds too much**. Two
practical conclusions for any bot author:

1. **Don't be exploitable by relentless aggression.** Call all-ins / big bets with a sensibly
   wide value range. Many bots in this field bleed chips by folding too often.
2. **Apply that same pressure yourself, selectively.** Aggression with even a small real edge
   (Azalea/Jokers style) beats passive equity-counting.

### Where the most points are left on the table
Most bots in this field share the same two weaknesses, so fixing either is a quick way to climb:

- **No true equity** (draws and runouts ignored) — affects Jokers, Long Story Short, and
  Howdee-Bot. Even ~50–100 Monte Carlo samples close most of the gap.
- **No real pot odds** — affects DuoDuo and Howdee-Bot. Reconstruct the pot from
  `round_history` and call only when equity beats the price.

### How to read this against the live results
Run `python main.py` (100 matches/pairing, parallel). Expect roughly: **CrAAcked (ALL-IN)**
near the top (exploits the folders), **Azalea** strong (best fundamentals), **CrAAcked (REAL)**
near the bottom (bugs). Treat any single short run as noisy — only large samples are meaningful.
