import sys
sys.stdout.reconfigure(encoding='utf-8')

"""
startgg_crawler.py

start.gg 사이트에서 특정 선수의 대회 참가/결과를 크롤링하는 기본 코드 구조
Python 3.11.9, gql, requests, pandas 등 사용
"""

import os
from typing import List, Dict, Any

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
PAT = os.getenv("STARTGG_API_TOKEN")

# GraphQL 엔드포인트
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

def get_event_info(event_slug: str) -> Dict[str, Any]:
    """
    event(slug: ...) 쿼리로 event id, name 등 정보 획득
    """
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
    return data.get("data", {}).get("event", {})


def get_event_status(event_id: int) -> Dict[str, Any]:
    """
    event(id: ...)로 진행 상황(standings, state 등) 정보 획득
    """
    query = """
    query getEventStatus($eventId: ID!) {
      event(id: $eventId) {
        id
        name
        state
        numEntrants
        standings(query: {perPage: 8, page: 1}) {
          nodes {
            placement
            entrant {
              name
            }
          }
        }
        phaseGroups {
          id
          displayIdentifier
          state
          rounds {
            id
            number
            bestOf
          }
        }
      }
    }
    """
    variables = {"eventId": event_id}
    data = run_graphql_query(query, variables)
    return data.get("data", {}).get("event", {})

def print_event_status_full(event_status: Dict[str, Any]) -> None:
    """
    진행상황 전체(raw) 보기 (A)
    """
    print("=== [이벤트 전체 진행상황] ===")
    from pprint import pprint
    pprint(event_status)

def print_event_status_brief(event_status: Dict[str, Any]) -> None:
    """
    Top8, 참가자 수, state만 간단히 요약 (B)
    """
    print("\n=== [이벤트 요약] ===")
    print("이벤트명:", event_status.get("name"))
    print("진행상태(state):", event_status.get("state"))
    print("총 참가자수:", event_status.get("numEntrants"))

    standings = event_status.get("standings", {}).get("nodes", [])
    print("Top 8:")
    for player in standings:
        rank = player.get("placement")
        name = player.get("entrant", {}).get("name")
        print(f"  #{rank}: {name}")

def main():
    # 예시: 제네시스9 Smash Ultimate Singles 이벤트 slug
    event_slug = "tournament/evo-2025/event/tekken-8"
    info = get_event_info(event_slug)
    print("이벤트 정보:", info)
    if not info or "id" not in info:
        print("이벤트 ID를 찾을 수 없습니다.")
        return

    event_id = int(info["id"])
    status = get_event_status(event_id)
    # print_event_status_full(status)
    print_event_status_brief(status)

if __name__ == "__main__":
    main()
