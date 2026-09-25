# Design

## Decision 1: The existing four classes are frozen

New classes reference old ones. No old class gains a slot, loses a slot,
or changes a description.

The alternative — adding `Donor.collection_site`, `Sample.storage_location`
and so on — models the domain slightly more naturally. It was rejected
because it destroys the experiment. If `Donor` gains two slots *and* the
schema gains eleven classes, and d03 starts failing, we cannot say
whether the planner was confused by more candidates or by a changed
`Donor`. Freezing the four makes candidate count the sole independent
variable.

The cost is a little artificiality: `Aliquot → Sample` reads slightly
oddly compared to `Sample → StorageLocation`, and `RunConfiguration` is a
bridge class that exists partly to attach `Instrument` and `ReagentLot`
to `Workflow` without editing `Workflow`. That is an acceptable price for
an interpretable measurement, and the edges can be inverted later in a
change whose purpose is domain fidelity rather than scaling.

## Decision 2: d01–d11 are frozen as the comparison arm

The headline number is the *existing* eval set, unmodified, run against
both schema sizes. Today's baseline is 5/11 at four collections; it must
be re-recorded before any schema edit, on the current model and prompt.

New cases covering the new collections (including the toxicology
question) are written, but scored **separately** and never folded into
the headline. Folding them in would mean comparing an 11-case score to a
20-case score and calling the difference "scaling."

One bookkeeping rule: a new class can legitimately give an existing case
a second correct answer. `Diagnosis` and `Assessment` both plausibly bear
on the head-injury question that d03/d09 probe. Widening an `expect_slots`
for that reason is allowed, but it is recorded as **"right answer
changed,"** not as a pass or a regression. Without that distinction,
degradation and bookkeeping are indistinguishable.

## Decision 3: Every new class carries at least one unambiguous slot

Near-miss slot names are the thing being tested — several classes with a
`notes`, a status enum and a date is exactly the confusion that stresses
selection. But a class made *only* of near-misses cannot be the subject
of a gradeable eval case, because no question has a single right answer.

So each new class also gets at least one slot no other class could own:
`substances_detected`, `braak_stage`, `raw_score`, `withdrawn_at`,
`thaw_count`, `freezer_id`, `software_version`, `serial_number`,
`lot_number`, `severity`, `doi`.

## Decision 4: Grounding cost is measured, not projected

The current figure — ~580 tokens per entity — comes from four unusually
slot-heavy classes (`Dataset` alone carries eight slots, an inlined value
object and four enum value lists). A four-slot dimension class like
`Instrument` costs a fraction of that. A naive `580 × 15` projection
would be wrong in a direction we cannot predict.

The token cost at both sizes is therefore a **measurement task**, taken
from `messages.count_tokens` against the assembled grounding block, not a
number asserted in advance.

## Decision 5: Dimension tables are small, never empty

The user asked how a collection could have no rows. Mechanically it can:
`mosaic migrate` creates the table from the schema, and `generate.py`
simply emits no instances. The `ExternalID` override already in
`demo.yaml` documents the accidental version of this — a class Mosaic
does not exclude and the schema does not mark `abstract` becomes a
permanently empty Aperture collection.

Empty is useless here. No query against an empty collection returns
anything, so no discovery eval case can be graded on it, and the panel
and nav render a dead entry. Instead the dimension tables are
deliberately **small**: 9 instruments, 24 storage locations, 40
publications, 75 reagent lots. Small keeps generation and load time flat
while the grounding surface — the thing under test — grows by ~4x.

## Decision 6: `DemoBundle` parity is enforced in code

`generation_schema.yaml` hand-mirrors one multivalued slot per entity
class. At four classes this was a latent rot hazard; at fifteen it is a
live one, and its failure mode is silent — a missing pool generates an
empty collection with no error.

`generate.py` gains a check, run before generation, that every concrete
`is_a: Entity` class in `demo.yaml` has a matching `DemoBundle` slot, and
raises if not. Cheaper than the discipline it replaces.
