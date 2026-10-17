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
x      = anchors.x      - 32        STICKY_PADDING
y      = anchors.y      - 32 - 64   plus STICKY_HEADER_HEIGHT
width  = anchors.width  + 64
height = anchors.height + 64 + 64
```

snapped to the 16px grid. The 64px of headroom on top is where the title renders clear of the nodes, and the nodes draw on top of the note. That is the intended look, not an overlap bug.

Anchors are recorded by node **id**, so renaming a member afterward is safe.

**Every sticky gets anchors. There is no good unanchored note on create.** A hand-written `position` is guessing, because coordinates are fixed before layout runs and describe a canvas that does not exist yet. Leaving both out is worse: the fallback centers the note under the entire graph (pre-layout every node sits at the origin, so an unanchored note counts as covering all of them) and then pushes it down past any sticky it lands on. The result is a note floating below the flow with no relationship to anything, which is the single most common way a canvas ends up looking wrong.

If you cannot name the nodes a note is about, it does not belong on the canvas.

## The rules that still produce a mess

- **Declared size wins dimension by dimension.** `{ width: 400 }` on an anchored note keeps your width and takes the derived height. Give both and anchoring only positions it. Give neither and it is fully derived, which is almost always what you want.
- **A pinned note is never moved, including out of another note's way.** Pinned means it has an explicit `position` *or* anchors. Only free-floating notes get de-overlapped, and that pass pushes them **down past other stickies only**, never past nodes. So a free-floating note can land on top of nodes, and two anchored notes whose anchor sets interleave overlap forever. Anchor each note to a disjoint run.
- **Stickies are invisible to layout.** Nodes are never spread apart to make room for a note.
- **Two zones cannot sit on vertically adjacent rows.** A zone reaches 32px below its anchors and 96px above them, so stacked zones need **128px of clear space between the node boxes**. Dagre stacks sibling branches `NODE_Y_SPACING` apart, which is 96. So giving each branch of an If or Switch its own zone overlaps by exactly 32px, every time, and both are pinned so neither yields. Anchor the whole fan as one zone, or zone one branch and leave the other bare.
- **Anchor whole stages, not single nodes.** One note per group or stage. A note per node reproduces the node names in a second typeface and buries the one callout that mattered.

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

To frame a run of nodes the way create does, read their positions from `get_workflow_details` and build the same box by hand: left edge minus 32, top minus 96, width plus 64, height plus 128, every value rounded to a multiple of 16.

## Content, and where the overflow goes

`### Title` on the first line, then one short line. The title carries the point of the callout, not the names of the nodes under it: a reader can already see `Set, If, Set`.

**One line is the whole budget.** Text renders from the note's top-left and only the top 64px clears the anchors, so anything longer renders *behind* the nodes where nobody reads it. The budget is not negotiable by making the note bigger, because a taller box just extends further behind the nodes.

So prose that does not fit goes somewhere else, and n8n has two better places for it:

- **Node `notes`** for why one node is configured the way it is. This is the right home for a retry policy, a rate limit, or a workaround.
- **The workflow `description`** for why the workflow exists at all.

Neither competes for canvas space, and both survive a reader who never scrolls left.

## Color

| | | | |
|---|---|---|---|
| 1 | yellow (default) | 5 | blue |
| 2 | gold | 6 | purple |
| 3 | red | 7 | gray |
| 4 | green | | |

One meaning per color per workflow, and match the palette already used by nearby workflows before inventing one. Color that varies by note rather than by role is noise.

## Constants

`GRID_SIZE` 16, `DEFAULT_STICKY_SIZE` 240x160, `STICKY_PADDING` 32, `STICKY_HEADER_HEIGHT` 64.
