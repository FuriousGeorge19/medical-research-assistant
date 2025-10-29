import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """You are an AI assistant specialized in medical research literature with access to a comprehensive database of peer-reviewed medical research papers.

**IMPORTANT MEDICAL DISCLAIMER:**
- You provide information from medical research for educational purposes only
- Your responses are NOT medical advice and should NOT replace consultation with qualified healthcare professionals
- Always remind users to consult with their healthcare provider for medical decisions

Search Tool Usage:
- Use the search tool for questions about medical conditions, treatments, clinical research, or health topics covered in the literature
- **One search per query maximum**
- Synthesize research findings into clear, evidence-based summaries
- If search yields no results, state this clearly and explain the limitation
- You may optionally use filters (topic, paper_type, year) when appropriate for the query

Response Protocol:
- **Medical research questions**: Search the literature first, then provide evidence-based answer
- **General health questions**: Use existing knowledge but search if specific evidence is requested
- **Treatment questions**: Always cite research and include publication years
- **No meta-commentary**:
  - Provide direct, evidence-based answers
  - Do not mention "based on the search results" or explain your search process
  - Focus on the medical evidence and findings

All responses must be:
1. **Evidence-based** - Ground answers in research findings with appropriate context
2. **Clear and accessible** - Use plain language while maintaining medical accuracy
3. **Balanced** - Present multiple perspectives when research shows varying results
4. **Contextual** - Include relevant limitations, study types, and publication years
5. **Brief and focused** - Get to the key findings quickly

When citing research, naturally incorporate publication year context (e.g., "Recent studies from 2023 show...") without being verbose.
"""
    
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 2048  # Increased from 800 to handle tool results better
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.
        
        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            
        Returns:
            Generated response as string
        """
        
        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history 
            else self.SYSTEM_PROMPT
        )
        
        # Prepare API call parameters efficiently
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }
        
        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
        
        # Get response from Claude
        response = self.client.messages.create(**api_params)
        
        # Handle tool execution if needed
        if response.stop_reason == "tool_use" and tool_manager:
            return self._handle_tool_execution(response, api_params, tool_manager)
        
        # Return direct response
        return response.content[0].text
    
    def _handle_tool_execution(self, initial_response, base_params: Dict[str, Any], tool_manager):
        """
        Handle execution of tool calls and get follow-up response.

        Args:
            initial_response: The response containing tool use requests
            base_params: Base API parameters
            tool_manager: Manager to execute tools

        Returns:
            Final response text after tool execution
        """
        # Start with existing messages
        messages = base_params["messages"].copy()

        # Add AI's tool use response
        messages.append({"role": "assistant", "content": initial_response.content})

        # Execute all tool calls and collect results
        tool_results = []
        for content_block in initial_response.content:
            if content_block.type == "tool_use":
                tool_result = tool_manager.execute_tool(
                    content_block.name,
                    **content_block.input
                )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": content_block.id,
                    "content": tool_result
                })
        
        # Add tool results as single message
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        
        # Prepare final API call without tools
        final_params = {
            **self.base_params,
            "messages": messages,
            "system": base_params["system"]
        }

        # Get final response with retry logic
        max_retries = 1
        for attempt in range(max_retries + 1):
            try:
                final_response = self.client.messages.create(**final_params)

                # Validate response has content
                if not final_response.content:
                    if attempt < max_retries:
                        print(f"Warning: Empty content in response (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                        continue
                    else:
                        print(f"Error: Empty content after {max_retries + 1} attempts")
                        return "I apologize, but I encountered an issue generating a response. Please try again."

                # Validate first content block has text
                if not hasattr(final_response.content[0], 'text'):
                    if attempt < max_retries:
                        print(f"Warning: Response missing text attribute (attempt {attempt + 1}/{max_retries + 1}), retrying...")
                        continue
                    else:
                        print(f"Error: Response missing text attribute after {max_retries + 1} attempts")
                        return "I apologize, but I encountered an issue generating a response. Please try again."

                # Success - return the text
                return final_response.content[0].text

            except Exception as e:
                if attempt < max_retries:
                    print(f"API error (attempt {attempt + 1}/{max_retries + 1}): {e}, retrying...")
                    continue
                else:
                    print(f"API error after {max_retries + 1} attempts: {e}")
                    raise

        # Fallback (should never reach here)
        return "I apologize, but I encountered an issue generating a response. Please try again."