"""
evo_entrants_crawler.py

EVO 이벤트 전체 참가자(entrants) 리스트 크롤링
"""
import os
from typing import List, Dict, Any

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
PAT = os.getenv("STARTGG_API_TOKEN")
STARTGG_API = "https://api.start.gg/gql/alpha"
HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
    "Authorization": f"Bearer {PAT}",
}

def run_graphql_query(query: str, variables: Dict[str, Any] = None) -> Dict[str, Any]:
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    response = requests.post(STARTGG_API, json=payload, headers=HEADERS)
    response.raise_for_status()
    return response.json()

def get_event_id(event_slug: str) -> int:
    query = """
    query getEventId($slug: String) {
      event(slug: $slug) {
        id
        name
      }
    }
    """
    variables = {"slug": event_slug}
    data = run_graphql_query(query, variables)
    return int(data.get("data", {}).get("event", {}).get("id"))

def get_all_entrants(event_id: int) -> List[Dict[str, Any]]:
    """
    event(id)로 entrants(참가자) 전체 리스트 반환 (페이지네이션)
    """
    entrants = []
    page = 1
    per_page = 100  # start.gg 쿼리 최대 100
    while True:
        query = """
        query getEntrants($eventId: ID!, $page: Int!, $perPage: Int!) {
          event(id: $eventId) {
            entrants(query: {page: $page, perPage: $perPage}) {
              pageInfo {
                totalPages
                total
              }
              nodes {
                id
                name
                participants {
                  gamerTag
                }
              }
            }
          }
        }
        """
        variables = {"eventId": event_id, "page": page, "perPage": per_page}
        data = run_graphql_query(query, variables)
        entrants_nodes = (
            data.get("data", {})
                .get("event", {})
                .get("entrants", {})
                .get("nodes", [])
        )
        if not entrants_nodes:
            break
        entrants.extend(entrants_nodes)

        # 페이지네이션 종료 체크
        page_info = (
            data.get("data", {})
                .get("event", {})
                .get("entrants", {})
                .get("pageInfo", {})
        )
        if page >= page_info.get("totalPages", 0):
            break
        page += 1
    return entrants

def save_entrants_to_csv(entrants: List[Dict[str, Any]], filename: str):
    rows = []
    for entrant in entrants:
        raw_name = entrant.get("name", "")
        if "|" in raw_name:
            team, player = map(str.strip, raw_name.split("|", 1))
        else:
            team, player = "", raw_name.strip()
        for part in entrant.get("participants", []):
            gamerTag = part.get("gamerTag", "")
            rows.append({"Team": team, "name": player, "gamerTag": gamerTag})
    df = pd.DataFrame(rows)
    df.to_csv(filename, index=False, encoding="utf-8-sig")
    print(f"✅ 참가자 {len(df)}명 저장 완료: {filename}")


def main():
    event_slug = "tournament/evo-2025/event/tekken-8"  # 예시 slug
    event_id = get_event_id(event_slug)
    print("event_id:", event_id)
    entrants = get_all_entrants(event_id)
    print("전체 참가자 수:", len(entrants))
    save_entrants_to_csv(entrants, "data/evo2025_tekken8_entrants.csv")

if __name__ == "__main__":
    main()
