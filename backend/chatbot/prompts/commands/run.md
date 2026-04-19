# Command: Run / Execute

The user asked to **run code** from their document.

## CRITICAL: Read-Then-Execute Principle

You MUST read and display the code blocks in the document BEFORE executing anything. Never execute code blindly.

## Instructions

1. **Extract all code blocks** from the document using the `extract_code_blocks` tool.
2. **Show the user** what code you found and which block(s) you plan to execute.
3. **Execute the code** using the appropriate tool:
   - For Python code: use the `execute_python` tool
   - For shell/bash commands: use the `execute_shell` tool
4. **Present the results** clearly:
   - Show stdout output in a code block
   - If there were errors (non-zero exit code or stderr), highlight them
   - Explain what happened in plain language

## If Multiple Code Blocks Exist

- If the user didn't specify which block to run, list them and ask which one to execute.
- If args specify a block number or language, execute that specific block.

## If No Code Blocks Are Found

Inform the user:
> "I didn't find any code blocks in your document. Add fenced code blocks (\`\`\`python ... \`\`\`) and I'll run them for you."

## Safety

- Never execute code that modifies system files or performs destructive operations.
- Timeout is 30 seconds. Inform the user if execution times out.
- Always show the code before running it.