from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode
from schemas.assets import get_all_assets, get_hardware_asset_info, get_software_asset_info

@tool
def get_all_assets_tool() -> str:
    """Get all assets in the organization, including both hardware servers and software projects.
    
    Returns a list of all assets with their basic information (id, name, type, description, tags).
    Use this to get an overview of all assets before diving into specific ones.
    """
    assets = get_all_assets()
    result_parts = ["# All Assets\n"]
    
    hardware_assets = [a for a in assets if a.asset_type == "hardware"]
    software_assets = [a for a in assets if a.asset_type == "software"]
    
    result_parts.append(f"## Hardware Assets ({len(hardware_assets)})\n")
    for asset in hardware_assets:
        result_parts.append(f"- **{asset.id}**: {asset.name} - {asset.description or 'N/A'} (tags: {', '.join(asset.tags)})")
    
    result_parts.append(f"\n## Software Assets ({len(software_assets)})\n")
    for asset in software_assets:
        result_parts.append(f"- **{asset.id}**: {asset.name} - {asset.description or 'N/A'} (tags: {', '.join(asset.tags)})")
    
    return "\n".join(result_parts)


@tool
def get_hardware_asset_info_tool(asset_id: str) -> str:
    """Get detailed information about a hardware server asset.
    
    Returns the server's OS, installed services/software with versions, and exposed ports.
    This is useful for identifying potential vulnerabilities in server software.
    
    Args:
        asset_id: The ID or name of the hardware asset (e.g., "hw-001" or "prod-web-server-01")
    """
    hw = get_hardware_asset_info(asset_id)
    if not hw:
        return f"Hardware asset '{asset_id}' not found."
    
    result_parts = [
        f"# Hardware Asset: {hw.name}",
        f"- **ID**: {hw.id}",
        f"- **Description**: {hw.description or 'N/A'}",
        f"- **OS**: {hw.os} {hw.os_version}",
        f"- **IP Address**: {hw.ip_address or 'N/A'}",
        f"- **Tags**: {', '.join(hw.tags)}",
        f"\n## Installed Services ({len(hw.services)})\n",
    ]
    
    for svc in hw.services:
        port_info = f"Port {svc.exposed_port}/{svc.protocol}" if svc.exposed_port else "No exposed port"
        result_parts.append(f"- **{svc.name}** v{svc.version} ({svc.vendor or 'Unknown'}) - {port_info}")
    
    return "\n".join(result_parts)


@tool  
def get_software_asset_info_tool(asset_id: str) -> str:
    """Get detailed information about a software project asset.
    
    Returns the project's language, repository, and open-source dependencies with versions.
    This is useful for identifying potential vulnerabilities in third-party libraries.
    
    Args:
        asset_id: The ID or name of the software asset (e.g., "sw-001" or "ecommerce-backend")
    """
    sw = get_software_asset_info(asset_id)
    if not sw:
        return f"Software asset '{asset_id}' not found."
    
    result_parts = [
        f"# Software Asset: {sw.name}",
        f"- **ID**: {sw.id}",
        f"- **Description**: {sw.description or 'N/A'}",
        f"- **Language**: {sw.language}",
        f"- **Repository**: {sw.repository or 'N/A'}",
        f"- **Tags**: {', '.join(sw.tags)}",
        f"\n## Dependencies ({len(sw.dependencies)})\n",
    ]
    
    # Group by package manager
    deps_by_pm: dict[str, list] = {}
    for dep in sw.dependencies:
        if dep.package_manager not in deps_by_pm:
            deps_by_pm[dep.package_manager] = []
        deps_by_pm[dep.package_manager].append(dep)
    
    for pm, deps in deps_by_pm.items():
        result_parts.append(f"### {pm.upper()}")
        for dep in deps:
            scope_info = f" ({dep.scope})" if dep.scope else ""
            result_parts.append(f"- {dep.name}: {dep.version}{scope_info}")
    
    return "\n".join(result_parts)


asset_tools = [get_all_assets_tool, get_hardware_asset_info_tool, get_software_asset_info_tool]
