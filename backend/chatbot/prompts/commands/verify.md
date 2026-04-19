# Command: Verify

The user asked to **verify** the content of their document.

## CRITICAL: Read-Before-Verify Principle

You MUST carefully re-read the DOCUMENT CONTENT in full before making any verification claims. Never confirm or deny something
without tracing it back to the actual document text.

## Instructions

1. **Read the entire document** carefully, section by section.
2. **For code blocks**:
   - Trace through the logic step by step
   - Check for syntax errors, logical bugs, or anti-patterns
   - Verify that code matches any descriptions or comments around it
   - Confirm imports, function signatures, and return values are consistent
3. **For factual claims**:
   - Check internal consistency (does the document contradict itself?)
   - Flag any claims that seem unsupported or ambiguous
4. **For structure**:
   - Verify heading hierarchy is logical
   - Check that links / references are present (even if you can't follow them)
   - Confirm table formatting and list consistency
5. **Produce a verification report**:
   - ✅ What checks out correctly
   - ⚠️ Potential issues or inconsistencies
   - ❌ Definite errors found
   - 💡 Suggestions for improvement

## If the Document Is Empty

Inform the user there is nothing to verify.