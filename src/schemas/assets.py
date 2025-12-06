"""Pydantic models for Asset data.

This module provides Pydantic models for representing assets (hardware and software)
and their dependencies discovered during security analysis.

Asset Types:
- Hardware: Physical or virtual servers with installed services
- Software: Source code projects with open-source dependencies
"""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel


# ============ Hardware Asset Models ============

class InstalledService(BaseModel):
    """A service/software installed on a hardware asset."""
    name: str
    version: str
    vendor: Optional[str] = None
    exposed_port: Optional[int] = None  # 暴露的端口
    protocol: Optional[str] = None  # tcp, udp, http, https


class HardwareAsset(BaseModel):
    """A hardware asset (physical/virtual server)."""
    id: str
    name: str
    description: Optional[str] = None
    os: str  # 操作系统
    os_version: str
    ip_address: Optional[str] = None
    services: list[InstalledService] = []
    tags: list[str] = []


# ============ Software Asset Models ============

class Dependency(BaseModel):
    """An open-source dependency used by a software project."""
    name: str
    version: str
    package_manager: str  # maven, npm, pip, go, cargo, etc.
    scope: Optional[str] = None  # compile, runtime, test, dev


class SoftwareAsset(BaseModel):
    """A software asset (source code project)."""
    id: str
    name: str
    description: Optional[str] = None
    language: str  # Java, Python, JavaScript, Go, etc.
    repository: Optional[str] = None  # Git repository URL
    dependencies: list[Dependency] = []
    tags: list[str] = []


# ============ Unified Asset Model ============

class Asset(BaseModel):
    """Unified asset reference for listing."""
    id: str
    name: str
    asset_type: Literal["hardware", "software"]
    description: Optional[str] = None
    tags: list[str] = []


# ============ Sample Data ============

SAMPLE_HARDWARE_ASSETS: list[HardwareAsset] = [
    HardwareAsset(
        id="hw-001",
        name="prod-web-server-01",
        description="Production web application server",
        os="Ubuntu",
        os_version="22.04 LTS",
        ip_address="192.168.1.10",
        services=[
            InstalledService(name="Apache Tomcat", version="9.0.50", vendor="Apache", exposed_port=8080, protocol="http"),
            InstalledService(name="Nginx", version="1.18.0", vendor="Nginx Inc", exposed_port=443, protocol="https"),
            InstalledService(name="OpenSSH", version="8.9p1", vendor="OpenBSD", exposed_port=22, protocol="tcp"),
            InstalledService(name="Redis", version="6.2.6", vendor="Redis Labs", exposed_port=6379, protocol="tcp"),
        ],
        tags=["production", "web", "dmz"]
    ),
    HardwareAsset(
        id="hw-002",
        name="prod-db-server-01",
        description="Production database server",
        os="CentOS",
        os_version="8.5",
        ip_address="192.168.1.20",
        services=[
            InstalledService(name="MySQL", version="8.0.28", vendor="Oracle", exposed_port=3306, protocol="tcp"),
            InstalledService(name="OpenSSH", version="8.0p1", vendor="OpenBSD", exposed_port=22, protocol="tcp"),
        ],
        tags=["production", "database", "internal"]
    ),
    HardwareAsset(
        id="hw-003",
        name="dev-jenkins-01",
        description="CI/CD Jenkins server",
        os="Ubuntu",
        os_version="20.04 LTS",
        ip_address="192.168.2.50",
        services=[
            InstalledService(name="Jenkins", version="2.375.1", vendor="Jenkins", exposed_port=8080, protocol="http"),
            InstalledService(name="Docker", version="20.10.21", vendor="Docker Inc", exposed_port=2375, protocol="tcp"),
            InstalledService(name="OpenSSH", version="8.2p1", vendor="OpenBSD", exposed_port=22, protocol="tcp"),
        ],
        tags=["development", "ci-cd", "internal"]
    ),
    HardwareAsset(
        id="hw-004",
        name="prod-api-gateway-01",
        description="API Gateway server",
        os="Alpine Linux",
        os_version="3.17",
        ip_address="192.168.1.5",
        services=[
            InstalledService(name="Kong", version="3.1.0", vendor="Kong Inc", exposed_port=8000, protocol="http"),
            InstalledService(name="Kong Admin", version="3.1.0", vendor="Kong Inc", exposed_port=8001, protocol="http"),
            InstalledService(name="PostgreSQL", version="14.6", vendor="PostgreSQL", exposed_port=5432, protocol="tcp"),
        ],
        tags=["production", "api", "gateway"]
    ),
]

SAMPLE_SOFTWARE_ASSETS: list[SoftwareAsset] = [
    SoftwareAsset(
        id="sw-001",
        name="ecommerce-backend",
        description="E-commerce platform backend service",
        language="Java",
        repository="https://github.com/company/ecommerce-backend",
        dependencies=[
            Dependency(name="org.apache.logging.log4j:log4j-core", version="2.14.1", package_manager="maven", scope="compile"),
            Dependency(name="org.springframework.boot:spring-boot-starter-web", version="2.6.1", package_manager="maven", scope="compile"),
            Dependency(name="org.springframework.boot:spring-boot-starter-data-jpa", version="2.6.1", package_manager="maven", scope="compile"),
            Dependency(name="com.fasterxml.jackson.core:jackson-databind", version="2.13.0", package_manager="maven", scope="compile"),
            Dependency(name="mysql:mysql-connector-java", version="8.0.27", package_manager="maven", scope="runtime"),
        ],
        tags=["production", "backend", "java"]
    ),
    SoftwareAsset(
        id="sw-002",
        name="ecommerce-frontend",
        description="E-commerce platform frontend application",
        language="JavaScript",
        repository="https://github.com/company/ecommerce-frontend",
        dependencies=[
            Dependency(name="react", version="17.0.2", package_manager="npm", scope="runtime"),
            Dependency(name="axios", version="0.24.0", package_manager="npm", scope="runtime"),
            Dependency(name="lodash", version="4.17.20", package_manager="npm", scope="runtime"),
            Dependency(name="webpack", version="5.64.0", package_manager="npm", scope="dev"),
            Dependency(name="node-sass", version="6.0.1", package_manager="npm", scope="dev"),
        ],
        tags=["production", "frontend", "javascript"]
    ),
    SoftwareAsset(
        id="sw-003",
        name="data-processing-service",
        description="Data analytics and processing microservice",
        language="Python",
        repository="https://github.com/company/data-processing",
        dependencies=[
            Dependency(name="pandas", version="1.3.5", package_manager="pip", scope="runtime"),
            Dependency(name="numpy", version="1.21.0", package_manager="pip", scope="runtime"),
            Dependency(name="flask", version="2.0.2", package_manager="pip", scope="runtime"),
            Dependency(name="requests", version="2.26.0", package_manager="pip", scope="runtime"),
            Dependency(name="pyyaml", version="5.4.1", package_manager="pip", scope="runtime"),
        ],
        tags=["production", "backend", "python", "data"]
    ),
    SoftwareAsset(
        id="sw-004",
        name="internal-tools-api",
        description="Internal tooling and automation API",
        language="Go",
        repository="https://github.com/company/internal-tools",
        dependencies=[
            Dependency(name="github.com/gin-gonic/gin", version="v1.7.7", package_manager="go", scope="runtime"),
            Dependency(name="github.com/go-redis/redis/v8", version="v8.11.4", package_manager="go", scope="runtime"),
            Dependency(name="github.com/sirupsen/logrus", version="v1.8.1", package_manager="go", scope="runtime"),
            Dependency(name="gorm.io/gorm", version="v1.22.4", package_manager="go", scope="runtime"),
        ],
        tags=["internal", "backend", "go"]
    ),
]


# ============ Tool Functions ============

def get_all_assets() -> list[Asset]:
    """Get all assets (both hardware and software).
    
    Returns a unified list of asset references.
    """
    assets: list[Asset] = []
    
    # Add hardware assets
    for hw in SAMPLE_HARDWARE_ASSETS:
        assets.append(Asset(
            id=hw.id,
            name=hw.name,
            asset_type="hardware",
            description=hw.description,
            tags=hw.tags,
        ))
    
    # Add software assets
    for sw in SAMPLE_SOFTWARE_ASSETS:
        assets.append(Asset(
            id=sw.id,
            name=sw.name,
            asset_type="software",
            description=sw.description,
            tags=sw.tags,
        ))
    
    return assets


def get_hardware_asset_info(asset_id: str) -> Optional[HardwareAsset]:
    """Get detailed information about a hardware asset.
    
    Args:
        asset_id: The ID of the hardware asset (e.g., "hw-001")
        
    Returns:
        HardwareAsset with installed services and exposed ports, or None if not found.
    """
    for hw in SAMPLE_HARDWARE_ASSETS:
        if hw.id == asset_id or hw.name == asset_id:
            return hw
    return None


def get_software_asset_info(asset_id: str) -> Optional[SoftwareAsset]:
    """Get detailed information about a software asset.
    
    Args:
        asset_id: The ID of the software asset (e.g., "sw-001")
        
    Returns:
        SoftwareAsset with open-source dependencies, or None if not found.
    """
    for sw in SAMPLE_SOFTWARE_ASSETS:
        if sw.id == sw.id or sw.name == asset_id:
            return sw
    return None


__all__ = [
    # Models
    "Asset",
    "HardwareAsset",
    "SoftwareAsset", 
    "InstalledService",
    "Dependency",
    # Tool functions
    "get_all_assets",
    "get_hardware_asset_info",
    "get_software_asset_info",
    # Sample data
    "SAMPLE_HARDWARE_ASSETS",
    "SAMPLE_SOFTWARE_ASSETS",
]
