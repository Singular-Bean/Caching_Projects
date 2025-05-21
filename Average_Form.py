import requests
import os
import json
import re

prefix = "http://localhost:8080/"
run_in_terminal = "mitmproxy -s cacher_forever.py --mode reverse:http://www.sofascore.com --listen-port 8080"

CACHE_DIR = "./cache"


def remove_prefix(string):
    prefix = "http://localhost:8080/"
    if string.startswith(prefix):
        return string.removeprefix(prefix)
    return string


def url_to_filename(url: str) -> str:
    # Replace characters that are not safe in filenames
    safe_filename = re.sub(r'[<>:"/\\|?*\s]', '-', url)
    return os.path.join(CACHE_DIR, f"{safe_filename}.bin").replace("\\", "/")


def fetch_and_parse_json_cached(url: str, headers=None):
    filename = url_to_filename(url)
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            data = f.read()
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            print(f"[CACHE ERROR] Failed to parse cached data for {remove_prefix(url)}: {e}")
            # fallback to re-fetch
    else:
        print(f"Fetching {remove_prefix(url)} from network")

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    return response.json()


def check_website_and_assign_cached(url, headers=None):
    fetched = None
    filename = url_to_filename(url)
    if os.path.exists(filename):
        with open(filename, "rb") as f:
            data = f.read()
        try:
            fetched = json.loads(data)
        except json.JSONDecodeError as e:
            print(f"[CACHE ERROR] Failed to parse cached data for {remove_prefix(url)}: {e}")
            # fallback to re-fetch
    else:
        print(f"Fetching {remove_prefix(url)} from network")

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            fetched = response.json()
        else:
            fetched = None
    return fetched


def get_league_id_and_season_id(league_name):
    league_name = league_name.replace(" ", "%20")
    leagueid = \
        fetch_and_parse_json_cached(prefix + f"api/v1/search/all?q={league_name}&page=0")['results'][0]['entity']['id']
    seasonid = fetch_and_parse_json_cached(prefix + f"api/v1/unique-tournament/{leagueid}/seasons")['seasons'][0]['id']
    return leagueid, seasonid


def get_matchids(leagueid, seasonid, rounds):
    matchlist = []
    for i in range(2, rounds + 1):
        games = \
        fetch_and_parse_json_cached(f"{prefix}api/v1/unique-tournament/{leagueid}/season/{seasonid}/events/round/{i}")[
            'events']
        for game in games:
            matchid = game['id']
            pregame = check_website_and_assign_cached(f"{prefix}api/v1/event/{matchid}/pregame-form")
            if game['status']['code'] != 60 and pregame != None:
                matchlist.append((game['awayTeam']['name'], game['id'], game['homeTeam']['name']))
    return matchlist


def roundcalc(leagueid, seasonid):
    teamnum = len(
        fetch_and_parse_json_cached(f"{prefix}api/v1/unique-tournament/{leagueid}/season/{seasonid}/standings/total")[
            'standings'][0]['rows'])
    return (teamnum - 1) * 2


def get_match_forms(away_id_home):
    matchid = away_id_home[1]
    formdata = fetch_and_parse_json_cached(f"{prefix}api/v1/event/{matchid}/pregame-form")
    homepoints = 0
    games_in_last_5 = len(formdata['homeTeam']['form'])
    for x in formdata['homeTeam']['form']:
        if x == "W":
            homepoints += 3
        elif x == "D":
            homepoints += 1
    formdata['homeTeam']['form'] = homepoints / games_in_last_5

    awaypoints = 0
    games_in_last_5 = len(formdata['awayTeam']['form'])
    for y in formdata['awayTeam']['form']:
        if y == "W":
            awaypoints += 3
        elif y == "D":
            awaypoints += 1
    formdata['awayTeam']['form'] = awaypoints / games_in_last_5

    return away_id_home[2], formdata['homeTeam']['form'], away_id_home[0], formdata['awayTeam']['form']


leagueid, seasonid = get_league_id_and_season_id(
    input("Enter the name of the league you want to know the average form of teams against from "))
finished = input("Has the season finished? (y/n) ")
if finished == "y":
    rounds = roundcalc(leagueid, seasonid)
else:
    rounds = int(input("Enter the number of rounds played in the season: "))

formlist = []
matchids = get_matchids(leagueid, seasonid, rounds)
for z in matchids:
    formlist.append(get_match_forms(z))
teamlist = []
for x in formlist:
    if x[0] not in teamlist:
        teamlist.append(x[0])

standings = {}

for a in teamlist:
    for b in formlist:
        if a == b[0]:
            if a not in standings:
                standings[a] = [b[3]]
            else:
                standings[a][0] += b[3]
        elif a == b[2]:
            if a not in standings:
                standings[a] = [b[1]]
            else:
                standings[a][0] += b[1]
    for x in matchids:
        if x[0] == a or x[2] == a:
            if len(standings[a]) == 1:
                standings[a].append(1)
            else:
                standings[a][1] += 1


sorted_standings = sorted(standings.items(), key=lambda x: x[1][0]/x[1][1], reverse=True)

for team, points in sorted_standings:
    print(f"{team}: {points[0]/points[1]:.2f} ({points[1]} games included)")
