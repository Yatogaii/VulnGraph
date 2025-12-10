from langchain_core.tools import tool
from tools.search import search_topic_by_ddgs
from tools.vuln_analyzer import get_cve_details

@tool
def search_ddgs_tool(query: str):
    """Search for a topic using DuckDuckGo."""
    return search_topic_by_ddgs(query)

@tool
def search_cve_tool(cve_id: str):
    """Search for a CVE by ID using NVD."""
    return get_cve_details(cve_id)

vuln_tools = [search_ddgs_tool, search_cve_tool]
