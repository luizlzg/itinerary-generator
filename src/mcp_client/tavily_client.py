"""
MCP client for Tavily web search using remote MCP server.

Connects to Tavily's remote MCP server at:
https://mcp.tavily.com/mcp/?tavilyApiKey=<your-api-key>

Available tools:
- tavily-search: Real-time web search with filtering options
"""
import os
import json
import asyncio
from typing import Optional, Dict, Any
from src.utils.logger import LOGGER

# MCP imports
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class TavilyMCPClient:
    """
    Client for Tavily's remote MCP server.

    Uses Streamable HTTP transport to connect to the remote server.
    """

    REMOTE_SERVER_URL = "https://mcp.tavily.com/mcp/?tavilyApiKey={api_key}"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Tavily MCP client.

        Args:
            api_key: Tavily API key. If not provided, reads from TAVILY_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("TAVILY_API_KEY must be set in environment or passed as parameter")

        self.server_url = self.REMOTE_SERVER_URL.format(api_key=self.api_key)
        self._session: Optional[ClientSession] = None
        self._client_context = None

    async def connect(self) -> bool:
        """
        Connect to Tavily's remote MCP server.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            LOGGER.info("Connecting to Tavily remote MCP server...")

            self._client_context = streamable_http_client(url=self.server_url)
            streams = await self._client_context.__aenter__()
            read_stream, write_stream, _ = streams

            self._session = ClientSession(read_stream, write_stream)
            await self._session.__aenter__()
            await self._session.initialize()

            tools_response = await self._session.list_tools()
            tool_names = [tool.name for tool in tools_response.tools]
            LOGGER.info(f"Connected to Tavily MCP. Available tools: {tool_names}\n{tools_response.tools}")

            return True

        except Exception as e:
            LOGGER.error(f"Failed to connect to Tavily MCP server: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Tavily MCP server."""
        try:
            if self._session:
                await self._session.__aexit__(None, None, None)
                self._session = None
            if self._client_context:
                await self._client_context.__aexit__(None, None, None)
                self._client_context = None
            LOGGER.info("Disconnected from Tavily MCP server")
        except Exception as e:
            LOGGER.error(f"Error disconnecting from Tavily MCP: {e}")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._session is not None

    async def search_async(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_images: bool = False,
        include_image_descriptions: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search the web using Tavily MCP (async version).

        Args:
            query: Search query string
            max_results: Maximum number of results (default: 5)
            search_depth: "basic" or "advanced" (default: "basic")
            include_images: Include image URLs in results (default: False)
            include_image_descriptions: Include image descriptions (default: False)

        Returns:
            Dictionary with 'results' and 'images' keys
        """
        if not self.is_connected:
            LOGGER.error("Not connected to Tavily MCP server")
            return {"results": [], "images": []}

        try:
            arguments = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
                "include_images": include_images,
            }

            if include_image_descriptions:
                arguments["include_image_descriptions"] = include_image_descriptions

            arguments.update(kwargs)

            LOGGER.info(f"MCP tavily_search: {query[:50]}...")

            result = await self._session.call_tool("tavily_search", arguments=arguments)

            if result.content and len(result.content) > 0:
                content_item = result.content[0]
                if hasattr(content_item, 'text'):
                    try:
                        data = json.loads(content_item.text)
                        return {
                            "results": data.get("results", []),
                            "images": data.get("images", [])
                        }
                    except json.JSONDecodeError:
                        return {
                            "results": [{"content": content_item.text, "url": "", "title": query}],
                            "images": []
                        }

            return {"results": [], "images": []}

        except Exception as e:
            LOGGER.error(f"Error calling tavily-search via MCP: {e}")
            return {"results": [], "images": []}

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        include_images: bool = False,
        include_image_descriptions: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search the web using Tavily MCP (sync version).

        Connects, searches, and disconnects in one call.
        """
        async def _run():
            async with TavilyMCPClient(self.api_key) as client:
                return await client.search_async(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                    include_images=include_images,
                    include_image_descriptions=include_image_descriptions,
                    **kwargs
                )

        try:
            return asyncio.run(_run())
        except Exception as e:
            LOGGER.error(f"Error in sync search: {e}")
            return {"results": [], "images": []}
