"""
Chatbot/agent.py
Core chatbot logic - loads the system prompts, injects the current 
markdown document as context, and calls the LLM.
Automatically switches between standered OpenAI and Azure OpenAI based 
on the settings in backend/.env

NOTE: This module provides a simplified ``chat()`` interface. The full 
lifescyle (slash commands, tools, streaming, session) is handled by 
``lifecycle.py`` -> ``llm_clinet.py``. ``chat()`` is kept for backward 
compatibility and simple intergration.
"""

from openai import AsyncOpenAI, AsyncAzureOpenAI
from chatbot.config import (
    OPENAI_API_KEY, 
    OPENAI_MODEL,
    OPENAI_BASE_URL,
    AZURE_API_VERSION,
    AZURE_DEPLOYMENT,
    IS_AZURE,
    MAX_TOKENS,
)
from chatbot.prompt_builder import load_prompt

# Load System Prompt once at import time - from the new prompts/ directory
_SYSTEM_PROMPT = load_prompt("system_main.md")

# Initialize the correct async LLM client based on the .env configuration
if IS_AZURE:
    _client = AsyncAzureOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL,
        api_version=AZURE_API_VERSION,
    )
    # Azure use the deployment name as the model identifier
    _model = AZURE_DEPLOYMENT
else:
    _client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_BASE_URL, 
    )
    _model = OPENAI_MODEL

async def chat(
    user_message: str, 
    context_md: str,
    history: list[dict], 
    ) -> str:

    """
    Send a message to the LLM and return the assistent's response.

    Parameters:
    -----------

    user_message: str - the latest message from the user
    document_md: str - the current markdown text from the editor.
    history: Previous turns as [{}role: "user"/"assistant", content: "message text"}]
    """

    system_message = {
        f"{_SYSTEM_PROMPT}\n\n"
        f"---\n"
        f"## DOCUMENT CONTEXT (current editor state)\n\n"
        f"{context_md if context_md.strip() else '*(empty - no content yet)*'}\n"
        f"---"    
    }

    messages = [{"role": "system", "content": system_message}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})  
    
    response = await _client.chat(
        model=_model,
        messages=messages,
        max_tokens=MAX_TOKENS,
    )
    return response.choices[0].message.content