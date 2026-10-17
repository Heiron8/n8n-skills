# Sticky notes

Read before placing or editing one. The two entry points take different shapes, and only the create path computes geometry for you.

| Tool | Shape | Geometry |
|---|---|---|
| `create_workflow_from_code` | SDK `sticky(content, nodes?, config?)` | Derived from the anchors, after layout |
| `update_workflow` | `addNode` with `type: 'n8n-nodes-base.stickyNote'` | Yours to compute, in full |

## On create: anchor, never position

```ts
const note = sticky('## Enrich order\nLooks up the customer in Postgres before pricing.', [lookup, price], { color: 5 });
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

A hand-positioned sticky is guessing: coordinates are fixed before layout runs, so they describe a canvas that does not exist yet. Anchor instead, and only set `position` for a note that belongs to no particular node (a title banner, a workflow-level TODO).

## The four rules that still produce a mess

- **Declared size wins dimension by dimension.** `{ width: 400 }` on an anchored note keeps your width and takes the derived height. Give both and anchoring only positions it. Give neither and it is fully derived, which is almost always what you want.
- **A pinned note is never moved, including out of another note's way.** Pinned means it has an explicit `position` *or* anchors. Only free-floating notes get de-overlapped, and that pass pushes them **down past other stickies only**, never past nodes. So a free-floating note can land on top of nodes, and two anchored notes whose anchor sets interleave overlap forever. Anchor each note to a disjoint run.
- **Stickies are invisible to layout.** Nodes are never spread apart to make room for a note.
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

## Content

`### Title` on the first line, then 1 to 3 sentences. The title carries the point of the callout, not the names of the nodes under it: a reader can already see `Set, If, Set`. Markdown renders, so a short list or a `code` span is fine; a wall of prose is not, because the note is read at a glance over the canvas.

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
