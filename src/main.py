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

import time, pprint

# 딴 파일에서 들고왓
from matches import get_event_sets, analyze_player_progress

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

def get_entrants(event_id: int) -> List[Dict[str, Any]]:
    """
    entrants 전체 리스트(페이지네이션)
    """
    entrants = []
    page = 1
    per_page = 100
    while True:
        query = """
        query getEntrants($eventId: ID!, $page: Int!, $perPage: Int!) {
          event(id: $eventId) {
            entrants(query: {page: $page, perPage: $perPage}) {
              pageInfo { totalPages }
              nodes { id name participants { gamerTag } }
            }
          }
        }
        """
        variables = {"eventId": event_id, "page": page, "perPage": per_page}
        data = run_graphql_query(query, variables)
        nodes = data.get("data", {}).get("event", {}).get("entrants", {}).get("nodes", [])
        if not nodes:
            break
        entrants.extend(nodes)
        pageInfo = data.get("data", {}).get("event", {}).get("entrants", {}).get("pageInfo", {})
        if page >= pageInfo.get("totalPages", 0):
            break
        page += 1
    return entrants

def get_standings(event_id: int) -> List[Dict[str, Any]]:
    standings = []
    page = 1
    per_page = 100
    while True:
        query = """
        query getStandings($eventId: ID!, $page: Int!, $perPage: Int!) {
          event(id: $eventId) {
            standings(query: {perPage: $perPage, page: $page}) {
              pageInfo { totalPages }
              nodes {
                placement
                entrant { id name participants { gamerTag } }
                stats { phaseGroupId finalPlacement dq }
              }
            }
          }
        }
        """
        variables = {"eventId": event_id, "page": page, "perPage": per_page}
        data = run_graphql_query(query, variables)
        nodes = data.get("data", {}).get("event", {}).get("standings", {}).get("nodes", [])
        if not nodes:
            break
        standings.extend(nodes)
        pageInfo = data.get("data", {}).get("event", {}).get("standings", {}).get("pageInfo", {})
        if page >= pageInfo.get("totalPages", 0):
            break
        page += 1
    return standings

def get_entrant_sets(entrant_id: int) -> List[Dict[str, Any]]:
    sets = []
    page = 1
    per_page = 50
    while True:
        query = """
        query getEntrantSets($entrantId: ID!, $page: Int!, $perPage: Int!) {
          entrant(id: $entrantId) {
            sets(page: $page, perPage: $perPage, filters: { hideByes: true }) {
              pageInfo { totalPages }
              nodes {
                id
                round
                state
                winnerId
                slots { entrant { id name } }
              }
            }
          }
        }
        """
        variables = {"entrantId": entrant_id, "page": page, "perPage": per_page}
        data = run_graphql_query(query, variables)
        nodes = data.get("data", {}).get("entrant", {}).get("sets", {}).get("nodes", [])
        if not nodes:
            break
        sets.extend(nodes)
        pageInfo = data.get("data", {}).get("entrant", {}).get("sets", {}).get("pageInfo", {})
        if page >= pageInfo.get("totalPages", 0):
            break
        page += 1
    return sets

def analyze_player_status(player_name: str, entrants: List[Dict[str, Any]], standings: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    entrants: 전체 참가자 리스트
    standings: 전체 순위 리스트
    player_name: players.csv의 player(영문)
    
    결과: 진행상황, 승자/패자조, 최근 경기, 탈락 시 패배 내역 등 dict
    """
    result = {
        "player": player_name,
        "state": "N/A",
        "bracket": "",
        "placement": "",
        "eliminated_by": "",
        "last_match_round": "",
        "last_match_result": "",
        "last_match_opponent": ""
    }
    # entrant 매칭 (gamerTag 또는 name 대소문자 무시)
    player_lower = player_name.lower().strip()
    entrant_obj = None
    for entrant in entrants:
        # 참가자 이름, gamerTag 모두 비교
        e_name = (entrant.get("name") or "").lower().strip()
        for part in entrant.get("participants", []):
            gtag = (part.get("gamerTag") or "").lower().strip()
            if player_lower == e_name or player_lower == gtag:
                entrant_obj = entrant
                break
        if entrant_obj:
            break
    if not entrant_obj:
        result["state"] = "Not Found"
        return result
    entrant_id = int(entrant_obj.get("id"))
    # standings에서 찾기
    standing = None
    for node in standings:
        ent = node.get("entrant", {})
        if int(ent.get("id", -1)) == entrant_id:
            standing = node
            break
    # 기본 정보
    if standing:
        result["placement"] = standing.get("placement")
    # 세트 정보에서 마지막 경기 확인
    sets = get_entrant_sets(entrant_id)
    if sets:
        last_set = sets[-1]
        result["last_match_round"] = last_set.get("round")
        slots = last_set.get("slots", [])
        opp = ""
        for s in slots:
            ent = s.get("entrant", {})
            if int(ent.get("id", -1)) != entrant_id:
                opp = ent.get("name")
        result["last_match_opponent"] = opp
        # 경기 결과
        state = last_set.get("state")
        winner = last_set.get("winnerId")
        if winner is None:
            result["last_match_result"] = state
        elif int(winner) == entrant_id:
            result["last_match_result"] = "Win"
        else:
            result["last_match_result"] = "Lose"
            result["eliminated_by"] = opp
        # 브래킷: 라운드명으로 간주 (Losers/Finals 등 포함시 패자조로)
        round_str = (last_set.get("round") or "").lower()
        if "losers" in round_str:
            result["bracket"] = "Losers"
        elif "winners" in round_str:
            result["bracket"] = "Winners"
        else:
            result["bracket"] = last_set.get("round", "")
        # 상태
        if state in ["COMPLETED", "FINISHED"] and result["last_match_result"] == "Lose":
            result["state"] = "Eliminated"
        else:
            result["state"] = "Active"
    else:
        result["state"] = "No matches"
    return result
  
def get_entrant_id_map(entrants):
    # entrants: get_entrants(event_id) 결과
    # 반환: {lowercase_gamerTag_or_name: entrant_id}
    id_map = {}
    for e in entrants:
        name = (e.get("name") or "").strip().lower()
        id_map[name] = int(e["id"])
        for p in e.get("participants", []):
            tag = (p.get("gamerTag") or "").strip().lower()
            id_map[tag] = int(e["id"])
    return id_map

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

def pretty_print_entrants(entrants, count=3):
    print("\n=== entrants 구조 샘플 ===")
    for i, e in enumerate(entrants[:count]):
        print(f"[{i}]")
        pprint.pprint(e)
        print("-" * 40)

def pretty_print_standings(standings, count=3):
    print("\n=== standings 구조 샘플 ===")
    for i, s in enumerate(standings[:count]):
        print(f"[{i}]")
        pprint.pprint(s)
        print("-" * 40)

def main():
    # 예시: 제네시스9 Smash Ultimate Singles 이벤트 slug
    event_name = "evo-2025"
    #형식 달라지면 다시 보기
    event_slug = f"tournament/{event_name}/event/tekken-8"
    print(f"이벤트 정보 가져오는 중... {event_slug}")
    info = get_event_info(event_slug)
    print("이벤트 정보:", info)
    if not info or "id" not in info:
        print("이벤트 ID를 찾을 수 없습니다.")
        return
    event_id = int(info["id"])
      
    # 기본 정보 출력 
    print(f"get_event_status...")
    status = get_event_status(event_id)
    
    # print_event_status_full(status)
    print_event_status_brief(status)
    
    # print(f"get_standings...")
    # standings = get_standings(event_id)
    
    # players.csv 불러오기
    players_df = pd.read_csv("data/players.csv")
    players_filtered = []
    
    for idx, elem in players_df.iterrows():
      player_name = elem["player"].strip().lower()
      entrant_id =  int(elem["entrant_id"]) if elem["entrant_id"] > 0 else 0
      
      players_filtered.append(
        {
          "name": player_name,
          "id": entrant_id,
        }
      )
    
    empty_id_players = list(filter(lambda x: x["id"] == 0, players_filtered))
    
    if(len(empty_id_players) > 0):
      print(f"id 갱신 필요한 유저 발견. 귀찮으니 스스로 하시오. 프로그램 종료")
      print(empty_id_players)
      
      return

    results = []
    file_name=f"data/{event_name}.csv"    
    for elem in players_filtered:
      player_name = elem["name"]
      entrant_id = elem["id"]      
    
      if not entrant_id:
          print(f"{player_name}의 entrant id를 찾을 수 없음")
          continue
      matches = get_event_sets(event_id, entrant_id)
      print(f"=== {player_name} ({entrant_id}) ===")
      # for m in matches:
      #     # m의 구조에 따라 라운드, 상대, 점수 등 출력
      #     print(m)
      progress = analyze_player_progress(matches, player_name, entrant_id)
      results.append(progress)
      result_df = pd.DataFrame(results)
      result_df.to_csv(file_name, index=False, encoding="utf-8")
      
    
    print(f"{file_name}.csv 저장 완료!")

if __name__ == "__main__":
    main()
