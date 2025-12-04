from pydantic import BaseModel

class ImpactedSoftware(BaseModel):
    name: str
    before_version: str | None = None
    after_version: str | None = None

class Vuln(BaseModel):
    id: str
    description: str
    published: str
    v2score: float | None = None
    v31score: float | None = None
    
    additional_info: str | None = None

    impacts: list[ImpactedSoftware] | None = None