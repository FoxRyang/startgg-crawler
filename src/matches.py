import os
import requests
from typing import List, Dict, Any
from dotenv import load_dotenv

import time

# 환경 변수에서 PAT 불러오기
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
    trycount=5
    while trycount > 0:
      try:
        response = requests.post(STARTGG_API, json=payload, headers=HEADERS)
        response.raise_for_status()
        break
      except requests.exceptions.HTTPError as e:
        print(e)
        print("Error occured. try again. wait 2 secs.")
        trycount = trycount - 1
        time.sleep(2)
    if trycount == 0:
      return {}
      
    return response.json()

def get_event_sets(event_id: int, entrant_id: int) -> List[Dict[str, Any]]:
    sets = []
    page = 1
    per_page = 50
    while True:
        query = """
        query getEventSets(
            $eventId: ID!,
            $entrantId: ID!,
            $page: Int!,
            $perPage: Int!
          ) {
          event(id: $eventId) {
            sets(page: $page, perPage: $perPage,
              filters: {
                entrantIds: [$entrantId]
              }) {
              pageInfo { totalPages }
              nodes {
                id
                fullRoundText
                winnerId
                slots {
                  entrant { id name
                  	standing {
                      placement
                    }
                  }
                }
                phaseGroup {
                  phase { name }
                }
              }
            }
          }
        }
        """
        variables = {
          "eventId": event_id,
          "page": page,
          "perPage": per_page,
          "entrantId": entrant_id,
        }
        data = None
        data = run_graphql_query(query, variables)
        nodes = data.get("data", {}).get("event", {}).get("sets", {}).get("nodes", [])
        if not nodes:
            break
        sets.extend(nodes)
        page_info = data.get("data", {}).get("event", {}).get("sets", {}).get("pageInfo", {})
        if page >= page_info.get("totalPages", 0):
            break
        page += 1
    return sets

def filter_sets_by_entrant(sets: List[Dict[str, Any]], entrant_id: int) -> List[Dict[str, Any]]:
    result = []
    for s in sets:
        slot_entrant_ids = [slot["entrant"]["id"] for slot in s.get("slots", []) if slot.get("entrant") and "id" in slot["entrant"]]
        if int(entrant_id) in [int(i) for i in slot_entrant_ids]:
            result.append(s)
    return result

def analyze_player_progress(matches: list, my_name: str, my_id: int):
    losses = []
    next_match_info = None

    for match in matches:
        winner_id = match.get("winnerId")
        match_id = str(match.get("id", ""))
        slots = match.get("slots", [])
        # 내 상대 찾기
        f_slots = list(filter(lambda x: x["entrant"] is not None, slots))
        opponents = [s["entrant"]["name"] for s in f_slots if int(s["entrant"]["id"]) != my_id]
        opponent = opponents[0] if opponents else ""
        my_entrant = [s["entrant"] for s in f_slots if int(s["entrant"]["id"]) == my_id][0]
        phase = match.get("phaseGroup", {}).get("phase", {}).get("name", "")
        roundtext = match.get("fullRoundText", "")

        # 1. 다음 경기 예측: id에 preview이거나 winnerId 없음
        if "preview" in match_id or winner_id is None:
            next_match_info = {
                "phase": phase,
                "fullRoundText": roundtext,
                "opponent": opponent
            }
        # 2. 패배 기록
        elif int(winner_id) != my_id:
            losses.append({
                "phase": phase,
                "fullRoundText": roundtext,
                "opponent": opponent
            })

    is_eliminated = len(losses) >= 2
    standing_info = None
    if is_eliminated:
      standing_info = int(my_entrant["standing"]["placement"])

    result = {
        "my_name" : my_name,
        "loss_count": len(losses),
        "is_eliminated": is_eliminated,
        "first_losses": losses[0] if losses else [],
        "last_losses": losses[1] if losses and len(losses)>1 else [],
        "next_match": next_match_info,
        "last_standing": standing_info
    }
    return result

def print_matches_info(matches: List[Dict[str, Any]], entrant_id: int):
    print(f"\n=== Entrant ID {entrant_id}의 경기 목록 ===")
    for m in matches:
        print(f"- Match(Set) ID: {m['id']}, 라운드: {m.get('fullRoundText')}, 상태: {m.get('state')}")
        # 상대 정보/점수 요약
        for slot in m["slots"]:
            e = slot.get("entrant")
            eid = e["id"] if e else "?"
            ename = e["name"] if e else "?"
            marker = "<YOU>" if str(eid) == str(entrant_id) else ""
            print(f"   > (entrant id: {eid}) {marker}")
        print(f"   승자 entrant id: {m.get('winnerId')}")
        print("-" * 35)

def main():
    event_id = 1300416
    entrant_id = 19859160
    print("sets 크롤링중...")
    sets = get_event_sets(event_id, entrant_id)
    print(sets)
    matches = filter_sets_by_entrant(sets, entrant_id)
    print(f"총 {len(matches)}경기 추출됨")
    print_matches_info(matches, entrant_id)

if __name__ == "__main__":
    main()
