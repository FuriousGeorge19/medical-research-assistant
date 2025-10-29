from typing import Dict, Any, Optional, Protocol
from abc import ABC, abstractmethod
from vector_store import VectorStore, SearchResults


class Tool(ABC):
    """Abstract base class for all tools"""

    @abstractmethod
    def get_tool_definition(self) -> Dict[str, Any]:
        """Return Anthropic tool definition for this tool"""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> str:
        """Execute the tool with given parameters"""
        pass


class MedicalLiteratureSearchTool(Tool):
    """Tool for searching medical research literature with topic and filtering"""

    def __init__(self, vector_store: VectorStore):
        self.store = vector_store
        self.last_sources = []  # Track sources from last search

    def get_tool_definition(self) -> Dict[str, Any]:
        """Return Anthropic tool definition for this tool"""
        return {
            "name": "search_medical_literature",
            "description": "Search medical research papers with optional filters for topic, paper type, and publication year",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What to search for in the medical literature (e.g., 'diabetes treatment', 'hypertension management')"
                    },
                    "topic": {
                        "type": "string",
                        "description": "Filter by specific topic (e.g., 'Type 2 Diabetes Management', 'Mental Health', 'Cardiovascular Health')"
                    },
                    "paper_type": {
                        "type": "string",
                        "description": "Filter by paper type (e.g., 'Review', 'Meta-Analysis', 'Systematic Review')"
                    },
                    "min_year": {
                        "type": "integer",
                        "description": "Minimum publication year to include (e.g., 2020)"
                    },
                    "max_year": {
                        "type": "integer",
                        "description": "Maximum publication year to include (e.g., 2025)"
                    }
                },
                "required": ["query"]
            }
        }

    def execute(self, query: str, topic: Optional[str] = None, paper_type: Optional[str] = None,
                min_year: Optional[int] = None, max_year: Optional[int] = None) -> str:
        """
        Execute the search tool with given parameters.

        Args:
            query: What to search for
            topic: Optional topic filter
            paper_type: Optional paper type filter
            min_year: Optional minimum year
            max_year: Optional maximum year

        Returns:
            Formatted search results or error message
        """

        # Build year_range tuple if min or max year provided
        year_range = None
        if min_year is not None or max_year is not None:
            min_y = min_year if min_year is not None else 1900
            max_y = max_year if max_year is not None else 2100
            year_range = (min_y, max_y)

        # Use the vector store's search interface
        results = self.store.search(
            query=query,
            topic=topic,
            paper_type=paper_type,
            year_range=year_range
        )

        # Handle errors
        if results.error:
            return results.error

        # Handle empty results
        if results.is_empty():
            filter_info = ""
            if topic:
                filter_info += f" in topic '{topic}'"
            if paper_type:
                filter_info += f" of type '{paper_type}'"
            if year_range:
                filter_info += f" from years {year_range[0]}-{year_range[1]}"
            return f"No relevant medical literature found{filter_info}."

        # Format and return results
        return self._format_results(results)

    def _format_results(self, results: SearchResults) -> str:
        """Format search results with paper metadata"""
        formatted = []
        sources = {}  # Track unique sources by paper_title (deduplicates automatically)

        for doc, meta in zip(results.documents, results.metadata):
            paper_title = meta.get('paper_title', 'Unknown Paper')
            journal = meta.get('journal', 'Unknown Journal')
            year = meta.get('year', 'Unknown Year')
            section = meta.get('section_title', '')

            # Build context header showing where this content came from
            header = f"[{paper_title}"
            if section:
                header += f" | {section}"
            header += "]"

            # Only add source if we haven't seen this paper yet
            if paper_title not in sources:
                # Build source text in format: "Title - Year - Journal"
                source_text = f"{paper_title} - {year} - {journal}"

                # Get URL from vector store
                url = self.store.get_paper_url(paper_title)

                # Create source object with text and URL
                sources[paper_title] = {"text": source_text, "url": url}

            formatted.append(f"{header}\n{doc}")

        # Store unique sources for retrieval (convert dict values to list)
        self.last_sources = list(sources.values())

        return "\n\n".join(formatted)


class ToolManager:
    """Manages available tools for the AI"""

    def __init__(self):
        self.tools = {}

    def register_tool(self, tool: Tool):
        """Register any tool that implements the Tool interface"""
        tool_def = tool.get_tool_definition()
        tool_name = tool_def.get("name")
        if not tool_name:
            raise ValueError("Tool must have a 'name' in its definition")
        self.tools[tool_name] = tool


    def get_tool_definitions(self) -> list:
        """Get all tool definitions for Anthropic tool calling"""
        return [tool.get_tool_definition() for tool in self.tools.values()]

    def execute_tool(self, tool_name: str, **kwargs) -> str:
        """Execute a tool by name with given parameters"""
        if tool_name not in self.tools:
            return f"Tool '{tool_name}' not found"

        return self.tools[tool_name].execute(**kwargs)

    def get_last_sources(self) -> list:
        """Get sources from the last search operation"""
        # Check all tools for last_sources attribute
        for tool in self.tools.values():
            if hasattr(tool, 'last_sources') and tool.last_sources:
                return tool.last_sources
        return []

    def reset_sources(self):
        """Reset sources from all tools that track sources"""
        for tool in self.tools.values():
            if hasattr(tool, 'last_sources'):
                tool.last_sources = []
