import os
import httpx
import logging
import asyncio
import json
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".octopart_cache"
CACHE_DIR.mkdir(exist_ok=True)
CACHE_ENABLED = True

NEXAR_API_KEY = os.environ.get("NEXAR_API_KEY")
NEXAR_API_URL = "https://api.nexar.com/graphql"

if not NEXAR_API_KEY:
    logger.warning(
        "NEXAR_API_KEY environment variable not set. Octopart client will not be able to authenticate."
    )

# --- GraphQL Queries ---
# This query searches for alternative parts by one or more MPNs.
# It retrieves detailed specs, datasheets, and pricing information.
SEARCH_MPN_QUERY = """
query findAlternativePart($mpn: String!) {
      #Try changing the mpn from "SY55855VKG" to find alternative parts of your own
      supSearchMpn(
        q: $mpn,
        #By design, when searching queries the API will return a default of 10 parts. Remove or change the limit parameter from "5" to return the number of parts you want
        limit: 1) {
        #The total number of results that the search returns
        hits
        results {
          part {
            similarParts {
          #For this query, we have chosen to return the similar part names, the octopartURL & MPN 
              #Press CTRL+space to find out what else you can return
              name
              mpn
              manufacturer {
                name
                id
              }
              descriptions {
                text
                
              }
              specs {
                attribute {
                  name
                }
                value
                siValue
                units
                unitsName
                
              }
              category {
                id
                name
                relevantAttributes {
                  name
                  valueType
                  unitsName
                }
              }
              sellers {
                country
                company {
                  id
                  name
                }
                offers {
                  prices {
                    quantity
                    convertedPrice
                    convertedCurrency
                  }
                }
              }
              estimatedFactoryLeadDays
            }
          }
        }
      }
    }
"""


async def find_alternative_part_by_mpn(mpn: str, sema: asyncio.Semaphore):
    """
    Queries the Nexar/Octopart API for a specific MPN, with file-based caching.
    """
    if not mpn:
        return None

    # Sanitize MPN for use as a filename
    safe_mpn_filename = quote_plus(mpn) + ".json"
    cache_path = CACHE_DIR / safe_mpn_filename

    # 1. Check cache first
    if CACHE_ENABLED and cache_path.exists():
        logger.info(f"Cache HIT for MPN: '{mpn}'. Reading from cache.")
        try:
            with open(cache_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(
                f"Could not read cache file for '{mpn}': {e}. Fetching from API."
            )

    logger.info(f"Cache MISS for MPN: '{mpn}'.")

    if not NEXAR_API_KEY:
        logger.error("Cannot query Octopart: NEXAR_API_KEY is not set.")
        return None

    headers = {
        "Content-Type": "application/json",
        "token": NEXAR_API_KEY,
    }

    payload = {"query": SEARCH_MPN_QUERY, "variables": {"mpn": mpn}}

    async with sema, httpx.AsyncClient() as client:
        try:
            logger.info(f"Querying Octopart for MPN: {mpn}")
            response = await client.post(
                NEXAR_API_URL, json=payload, headers=headers, timeout=20.0
            )
            response.raise_for_status()

            data = response.json()
            if "errors" in data:
                logger.error(
                    f"Octopart API returned errors for {mpn}: {data['errors']}"
                )
                return None

            results = data.get("data", {}).get("supSearchMpn", {}).get("results", [])
            part_data = results[0]["part"] if results else None

            # 3. Write to cache if successful and data is found
            if CACHE_ENABLED and part_data:
                try:
                    with open(cache_path, "w") as f:
                        json.dump(part_data, f, indent=2)
                    logger.info(f"Successfully wrote to cache for MPN: '{mpn}'")
                except IOError as e:
                    logger.error(f"Could not write to cache file for '{mpn}': {e}")

            return part_data

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error for {mpn}: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            logger.error(f"Network error for {mpn}: {e}")
        except Exception as e:
            logger.error(
                f"Unexpected error in Octopart client for {mpn}: {e}", exc_info=True
            )

    return None
