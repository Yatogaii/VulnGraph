from nvdlib import searchCVE
from logger import logger

def get_cve_details(cve_id: str):
    """Fetch CVE details from NVD using nvdlib."""
    try:
        results = searchCVE(cveId=cve_id)
        for cve in results:
            if cve.id == cve_id:
                return {
                    "id": cve.id,
                    "descriptions": cve.descriptions[0].value if cve.descriptions else "",
                    "published": cve.published,
                    "v2score": cve.v2score if hasattr(cve, "v2score") and cve.v2score else None,
                    "v31score": cve.v31score if hasattr(cve, "v31score") and cve.v31score else None,
                }
        return None
    except Exception as e:
        logger.error(f"Error fetching CVE details for {cve_id}: {e}")
        return None
