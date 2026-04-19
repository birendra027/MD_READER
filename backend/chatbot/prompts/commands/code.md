Here’s the text from the image:

# Command: Code Analysis

The user asked for a **code analysis** of their document.

## CRITICAL: Code-First Principle

You MUST read and reference the actual code blocks in the DOCUMENT CONTENT before producing any analysis. Do NOT speculate about
code that isn't present.

## Instructions

1. **Extract all code blocks** from the document first. Identify the language, purpose, and location of each block.
2. **Analyse each code block**:
   - What does it do? (one-line summary)
   - What language / framework is it written in?
   - Are there any obvious issues (bugs, anti-patterns, missing error handling)?
   - How does it relate to the surrounding Markdown text?
3. **Cross-reference** — If the document describes what the code should do, verify that the code actually does it.
4. **Produce a structured report**:
   - List of code blocks with language tags
   - Per-block analysis
   - Overall assessment (code quality, completeness, correctness)
   - Suggestions for improvement (if any)

## If No Code Is Found

If the document contains no code blocks, inform the user:
> "I didn't find any code blocks in your document. Add fenced code blocks (\`\`\`language ... \`\`\`) and I'll analyse them for you."


Let me know if there are more images!