# Sticky notes

Read before placing or editing one. The two entry points take different shapes, and only the create path computes geometry for you.

| Tool | Shape | Geometry |
|---|---|---|
| `create_workflow_from_code` | SDK `sticky(content, nodes?, config?)` | Derived from the anchors, after layout |
| `update_workflow` | `addNode` with `type: 'n8n-nodes-base.stickyNote'` | Yours to compute, in full |

## On create: anchor, never position

```ts
const note = sticky('### Enrich order\nCustomer lookup feeds the tier multiplier used by pricing.', [lookup, price], { color: 5 });
workflow('id', 'name').add(lookup.to(price)).add(note);
```

The second argument is the anchor list. It **only sizes and places the note**: those nodes are not added to the workflow by being listed, and the sticky is not added by wrapping them. All of it still needs `.add(...)`.

Anchored, the note is a **background zone**. The serializer lays the graph out first, then wraps the box around wherever the anchors actually landed:

```
x      = anchors.x      - 32       # STICKY_PADDING
y      = anchors.y      - 96       # STICKY_PADDING + STICKY_HEADER_HEIGHT
width  = anchors.width  + 64       # STICKY_PADDING both sides
height = anchors.height + 128      # both sides, plus the header
```

snapped to the 16px grid. The 64px of headroom on top is where the title renders clear of the nodes, and the nodes draw on top of the note. That is the intended look, not an overlap bug.

Anchors are recorded by node **id**, so renaming a member afterward is safe.

**Every sticky gets anchors. There is no good unanchored note on create.** A hand-written `position` is guessing, because coordinates are fixed before layout runs and describe a canvas that does not exist yet. Leaving both out is worse: the fallback centers the note under the entire graph (pre-layout every node sits at the origin, so an unanchored note counts as covering all of them) and then pushes it down past any sticky it lands on. The result is a note floating below the flow with no relationship to anything, which is the single most common way a canvas ends up looking wrong.

If you cannot name the nodes a note is about, it does not belong on the canvas.

## Where a note goes: pick the role, the role picks the anchors

The anchor set **is** the placement decision, so choosing it at random is what makes a canvas look randomly annotated. There are only three roles, and each fixes its own anchors:

| Role | Anchors | Color | Title |
|---|---|---|---|
| **Stage zone** | every node of one stage | what the stage does, below | `### Stage name` |
| **Callout** | the single node it is about | 3 red for a warning, else 1 yellow | `### Point`, and nothing else: over a plain node the box is only 160px wide |
| **Title band** | every node in the flow | 7 gray | `## What this workflow is` |

A title band is the rare one. It only earns its place on a large canvas you are deliberately leaving ungrouped, because a grouped canvas gets its heading from the group names and an ungrouped canvas under 7 boxes already has the workflow name in the breadcrumb. When you do use one, it wraps the whole flow and the stage zones nest inside it, with no care needed on your part: n8n z-orders stickies by area, largest behind, so the band sits behind the zones and both sit behind the nodes.

**A color is a symbol, not decoration.** It stands for what happens in the part of the flow it covers, so a reader can decode the shape of a workflow from color alone. Decide the meaning once and hold it for the whole workflow:

| | |
|---|---|
| 4 green | something is created, or a person is in the loop: form intake, approval gate, manual review |
| 3 red | destructive or irreversible: deletes, error paths, anything that pages a human, critical config |
| 5 blue | routing and data transformation, the neutral middle of a pipeline |
| 7 gray | the documentation layer: title band, reference panel |
| 2 gold | an outer frame |
| 6 purple | domain accents, sparingly |
| 1 yellow | the default, a note with no particular role |

**Precedence, highest first: what the user asked for, then the palette already used in nearby workflows (`search_workflows` plus `get_workflow_details`), then the table above.** A convention the reader already knows beats a better one they do not, so never override a stated preference or a visible house style with this default.

## How many, and at what scale

Count boxes the way the grouping rule does: the trigger, each group, and each ungrouped node.

- **Under about 5 nodes.** No stickies. The canvas already reads in one glance, and annotating it is noise.
- **5 to 7 boxes.** One zone per stage, so 2 to 4 of them, colored by role.
- **Over 7 boxes.** Node groups do the sectioning (see `NODE_GROUPS.md`) and they do the documenting too, through their own `description`. **Anchor nothing to a grouped node.** When groups exist, layout places collapsed chips and packs members into chip-sized slots, so member positions are cramped (adjacent members can overlap outright) and are not what the reader sees anyway. A sticky anchored to them draws over the group when it is expanded and lines up with nothing when it is collapsed. That leaves stickies almost nothing to do on a grouped canvas, which is correct.

## Giving the zone room

The derived 32px on the sides and bottom measures the node box only. A node's name renders below that box and a subtitle (`GET: https://...`) below the name, so both hang off the bottom edge.

Fix the bottom by declaring a height, which keeps the derived width and the derived position. Node boxes are 96px tall and rows sit 192px apart, so:

| Anchors | Derived height | Declare |
|---|---|---|
| all on one row | 224 | `height: 272` |
| spanning a branch fan, two rows | 416 | `height: 464` |

Each extra row adds 192 to both. The one node taller than 96 is Message an Agent v2 and up, at 128, which raises both numbers by 32.

The sides cannot be fixed the same way, because a declared width keeps the left edge and grows only to the right, eating the gutter to the next zone. If a canvas is worth polishing, widen the zones in a second pass: read the boxes back with `get_workflow_details`, then one `update_workflow` call moving each zone 24px left and adding 48 to its width. That takes the side padding to 56 and leaves a 16px gutter. **56 is the ceiling**, not a preference: the subtitle overhangs the node box by about 45px each side, and dagre's column pitch leaves only 128px between node boxes to split between two paddings and a gutter.

## The rules that still produce a mess

- **Declared size wins dimension by dimension.** `{ width: 400 }` on an anchored note keeps your width and takes the derived height. Give both and anchoring only positions it. Give neither and it is fully derived.
- **A pinned note is never moved, including out of another note's way.** Pinned means it has an explicit `position` *or* anchors. Only free-floating notes get de-overlapped, and that pass pushes them **down past other stickies only**, never past nodes. So a free-floating note can land on top of nodes, and two anchored notes whose anchor sets interleave overlap forever. Anchor each note to a disjoint run.
- **Stickies are invisible to layout.** Nodes are never spread apart to make room for a note.
- **Two zones cannot sit on vertically adjacent rows.** A zone reaches 96px above its anchors and 32px below, so stacked zones need **128px of clear space between the node boxes**. Dagre stacks sibling branches `NODE_Y_SPACING` apart, which is 96. So giving each branch of an If or Switch its own zone overlaps by exactly 32px, every time, and both are pinned so neither yields. Anchor the whole fan as one zone, or zone one branch and leave the other bare.
- **Anchor whole stages, not single nodes.** One zone per stage. A note per node reproduces the node names in a second typeface and buries the one callout that mattered.

## On update: there is no sticky operation

`update_workflow` offers `addNode`, `setNodePosition`, and `updateNodeParameters`, and runs no layout pass. A sticky is an ordinary node:

```json
{ "type": "addNode", "node": {
  "name": "Note: retry policy", "type": "n8n-nodes-base.stickyNote", "typeVersion": 1,
  "position": [-320, 160],
  "parameters": { "content": "### Retry policy\nThe API 429s above 10 rps.", "width": 480, "height": 240, "color": 3 }
}}
```

`content`, `width`, `height`, and `color` all live in `parameters`, not at the top level. **An omitted `position` becomes `[0, 0]`**, dropping a default 240x160 note at the canvas origin on top of whatever is there.

To frame a run of nodes the way create does, build the same box by hand. `get_workflow_details` gives positions but not sizes, and a position is the node's **top-left**, so you need the dimensions too: a plain node is 96x96, a node with configurable inputs is 256x96, and Message an Agent v2 and up is 320x128. Then:

```
left = min(x)            top    = min(y)
right = max(x + width)   bottom = max(y + height)

sticky.x = left - 32     sticky.width  = right - left + 64
sticky.y = top - 96      sticky.height = bottom - top + 128
```

Round every value to a multiple of 16.

## Content, and where the overflow goes

`###` on the first line for a zone or a callout, `##` for a title band, carrying the point of the note rather than the names of the nodes under it: a reader can already see `Set, If, Set`. Then one short line.

**One line is the whole budget, and it is a budget at the zone's width.** Text renders from the note's top-left and only the top 64px clears the anchors, so anything longer renders *behind* the nodes where nobody reads it. A taller box does not help: it just extends further behind them. A zone over one plain node is 96 + 64 = 160px wide, where even a short sentence wraps three ways, so those get a title and nothing else. Wider node types give a wider zone (256px-wide configurable nodes, 320px for Message an Agent v2 and up), but not enough to change the advice.

Prose that does not fit goes somewhere else, and n8n has two better places for it:

- **Node `notes`** for why one node is configured the way it is: a retry policy, a rate limit, a workaround.
- **The workflow `description`** for why the workflow exists at all.

Neither competes for canvas space, and both survive a reader who never scrolls left.

## Constants

`GRID_SIZE` 16, `DEFAULT_STICKY_SIZE` 240x160, `STICKY_PADDING` 32, `STICKY_HEADER_HEIGHT` 64, `NODE_Y_SPACING` 96.
