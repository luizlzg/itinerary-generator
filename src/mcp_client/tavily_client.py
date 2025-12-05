"""MCP client for Tavily web search operations."""
import json
from typing import Optional, Dict, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from src.utils.logger import LOGGER


class MCPTavilyClient:
    """
    Client for Tavily MCP server.
    Provides web search capabilities for gathering information about tourist attractions.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize MCP Tavily client.

        Args:
            api_key: Tavily API key (if not set as environment variable)
        """
        import os
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY must be set in environment or passed as parameter")

        self.session: Optional[ClientSession] = None
        # MCP server for Tavily
        self.server_params = StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-tavily"
            ],
            env={
                "TAVILY_API_KEY": self.api_key
            }
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self):
        """Connect to MCP Tavily server."""
        self._context = stdio_client(self.server_params)
        streams = await self._context.__aenter__()
        read_stream, write_stream = streams
        self.session = ClientSession(read_stream, write_stream)
        await self.session.__aenter__()

    async def disconnect(self):
        """Disconnect from MCP Tavily server."""
        if hasattr(self, 'session') and self.session:
            await self.session.__aexit__(None, None, None)
        if hasattr(self, '_context') and self._context:
            await self._context.__aexit__(None, None, None)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_images: bool = False
    ) -> Dict[str, Any]:
        """
        Search the web using Tavily.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            search_depth: "basic" or "advanced" search depth
            include_images: If True, include image URLs in results

        Returns:
            Dictionary with 'results' (list of search results) and 'images' (list of image URLs)
        """
        if not self.session:
            LOGGER.warning("Not connected to MCP server")
            return {"results": [], "images": []}

        try:
            result = await self.session.call_tool(
                "tavily_search",
                arguments={
                    "query": query,
                    "max_results": max_results,
                    "search_depth": search_depth,
                    "include_images": include_images
                }
            )

            # Parse MCP response
            if result.content and len(result.content) > 0:
                content_item = result.content[0]
                if hasattr(content_item, 'text'):
                    content_text = content_item.text
                    # Try to parse as JSON
                    try:
                        data = json.loads(content_text)
                        # Tavily returns: {"results": [...], "images": [...]}
                        return {
                            "results": data.get("results", []),
                            "images": data.get("images", [])
                        }
                    except json.JSONDecodeError:
                        # If not JSON, return as single result
                        return {
                            "results": [{"content": content_text, "url": "", "title": query}],
                            "images": []
                        }

            return {"results": [], "images": []}

        except Exception as e:
            LOGGER.error(f"Error searching with Tavily: {e}")
            return {"results": [], "images": []}


class SimplifiedTavilySearch:
    """
    Simplified Tavily search using direct API calls.
    Fallback when MCP is not available.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Tavily API key."""
        import os
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY must be set")

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_images: bool = False,
        include_raw_content: bool = False,
        include_image_descriptions: bool = False,
        chunks_per_source: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search using Tavily API directly.

        Args:
            query: Search query
            max_results: Maximum results (default: 5)
            search_depth: "basic" or "advanced" (default: "basic")
            include_images: If True, include image URLs
            include_raw_content: If True, include full page content
            include_image_descriptions: If True, include image descriptions
            chunks_per_source: Number of content chunks per source (default: 3)
            **kwargs: Additional parameters to pass to Tavily API

        Returns:
            Dictionary with 'results' and 'images' keys
        """
        try:
            import requests

            # Build request payload
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
                "include_images": include_images,
                "include_raw_content": include_raw_content,
                "include_image_descriptions": include_image_descriptions,
            }

            # Add chunks_per_source only if include_raw_content is True
            if include_raw_content:
                payload["chunks_per_source"] = chunks_per_source

            # Add any additional kwargs
            payload.update(kwargs)

            response = requests.post(
                "https://api.tavily.com/search",
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "results": data.get("results", []),
                    "images": data.get("images", [])
                }
            else:
                LOGGER.error(f"Tavily API error: {response.status_code}")
                return {"results": [], "images": []}

        except Exception as e:
            LOGGER.error(f"Error with Tavily API: {e}")
            return {"results": [], "images": []}