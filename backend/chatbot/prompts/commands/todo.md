# Command: Todo Extraction

The user asked for **TODO / task extraction** from their document.

## Instructions

1. **Scan the DOCUMENT CONTENT** for any task-like items:
   - Markdown checkboxes: `- [ ]` (incomplete) and `- [x]` (complete)
   - TODO markers: lines containing `TODO:`, `FIXME:`, `HACK:`, `XXX:`
   - Action items: sentences that imply work to be done (e.g. "we need to...", "should be implemented...")
2. **Categorise** each item:
   - ✅ **Done** — completed checkboxes `[x]`
   - ⬜ **Pending** — incomplete checkboxes `[ ]`
   - 📌 **Inline TODO** — `TODO:` / `FIXME:` markers
   - 💡 **Implied** — action items inferred from the text
3. **Present a structured list** grouped by category.
4. **Add a progress summary** at the top: "X of Y tasks complete (Z%)".

## If No Tasks Are Found

If the document contains no recognisable tasks, inform the user:
> "I didn't find any tasks or TODOs in your document. You can add task lists with `- [ ] item` syntax."