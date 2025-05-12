import requests
import os
import json
import re


class MyCustomError(Exception):
    pass


prefix = "http://localhost:8080/"
run_in_terminal = "mitmproxy -s cacher_forever.py --mode reverse:http://www.sofascore.com --listen-port 8080"

CACHE_DIR = "./cache"

ultimatum = input("Would you like to use caching? (y/n)\n")
if ultimatum == "y":

    print(f"Caching is enabled: Prefix = {prefix}")
    print(f"Run the following command in a terminal to start the proxy:\n{run_in_terminal}")


    def remove_prefix(string):
        prefix = "http://localhost:8080/"
        if string.startswith(prefix):
            return string.removeprefix(prefix)
        return string


    def url_to_filename(url: str) -> str:
        # Replace characters that are not safe in filenames
        safe_filename = re.sub(r'[<>:"/\\|?*\s]', '-', url)
        return os.path.join(CACHE_DIR, f"{safe_filename}.bin").replace("\\", "/")


    def compare_residuals(target, player):
        target_summed = sum(target)
        player_summed = sum(player)
        coefficent = target_summed / player_summed
        for i in range(len(player)):
            player[i] = player[i] * coefficent
        residuals = 0
        for i in range(len(target)):
            residuals += ((target[i] - player[i]) ** 2)
        return residuals


    search_network = input(
        "Would you like the program to search for players that arent already stored in the cache - apart from the target player - (y/n)?\n")
    if search_network == "y":

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
            alteredname = league_name.replace(" ", "%20")
            leagueid = \
                fetch_and_parse_json_cached(prefix + f"api/v1/search/all?q={alteredname}&page=0")['results'][0][
                    'entity']['id']
            seasonid = \
                fetch_and_parse_json_cached(prefix + f"api/v1/unique-tournament/{leagueid}/seasons")['seasons'][0][
                    'id']
            return leagueid, seasonid


        def get_teamids(leagueid, seasonid):
            teamids = []
            teams = \
                fetch_and_parse_json_cached(
                    prefix + f"api/v1/unique-tournament/{leagueid}/season/{seasonid}/standings/total")[
                    'standings'][0][
                    'rows']
            for team in teams:
                teamids.append(team['team']['id'])
            return teamids


        def get_playerids(teamid):
            playerids = []
            players = fetch_and_parse_json_cached(prefix + f"api/v1/team/{teamid}/players")['players']
            for player in players:
                playerids.append((player['player']['id'], player['player']['name']))
            return playerids


        def get_playerid_from_name(name):
            alteredname = name.replace(" ", "%20")
            playerid = \
                fetch_and_parse_json_cached(prefix + f"api/v1/search/player-team-persons?q={alteredname}&page=0")[
                    'results'][
                    0][
                    'entity'][
                    'id']
            return playerid


        def get_player_attributes(playerid):
            player_attributes = check_website_and_assign_cached(
                prefix + f"api/v1/player/{playerid}/attribute-overviews")
            if player_attributes is not None:
                player_attributes = player_attributes['playerAttributeOverviews'][0]
                if 'attacking' in player_attributes and 'creativity' in player_attributes and 'defending' in player_attributes and 'tactical' in player_attributes and 'technical' in player_attributes:
                    return [player_attributes['attacking'], player_attributes['creativity'],
                            player_attributes['defending'],
                            player_attributes['tactical'], player_attributes['technical']]
            return None


        playername = input("Enter the name of the player you want to compare with: ")
        leaguename = input("Enter the name of the league you want to find similar players from: ")
        leagueid, seasonid = get_league_id_and_season_id(leaguename)
        teamids = get_teamids(leagueid, seasonid)
        players = []
        for teamid in teamids:
            playerids = get_playerids(teamid)
            players.extend(playerids)

        targetid = get_playerid_from_name(playername)
        target = (targetid, get_player_attributes(targetid))

        all = []
        for player, name in players:
            attributes = get_player_attributes(player)
            if attributes is not None:
                all.append((player, attributes, name))
        residuals_with_ids = []
        for x in all:
            if x[0] != target[0]:
                residuals = compare_residuals(target[1], x[1])
                residuals_with_ids.append((x[2], residuals))

        residuals_with_ids.sort(key=lambda x: x[1])
        for j in range(10):
            if j == 0:
                suffix = "st"
            elif j == 1:
                suffix = "nd"
            elif j == 2:
                suffix = "rd"
            else:
                suffix = "th"
            print(
                f"{j + 1}{suffix} Closest Player: {residuals_with_ids[j][0]}, Residuals: {round(residuals_with_ids[j][1], 1)}")

    elif search_network == "n":
        print("Skipping search for non-target players")


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
                print(f"{remove_prefix(url)} not in cache, ignoring")

            return None


        def fetch_and_parse_json_cached_regular(url: str, headers=None):
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
                print(f"{remove_prefix(url)} not in cache, ignoring")
            return fetched


        def get_league_id_and_season_id(league_name):
            alteredname = league_name.replace(" ", "%20")
            leagueid = \
                fetch_and_parse_json_cached(prefix + f"api/v1/search/all?q={alteredname}&page=0")['results'][0][
                    'entity']['id']
            seasonid = \
                fetch_and_parse_json_cached(prefix + f"api/v1/unique-tournament/{leagueid}/seasons")['seasons'][0][
                    'id']
            return leagueid, seasonid


        def get_teamids(leagueid, seasonid):
            teamids = []
            teams = \
                fetch_and_parse_json_cached(
                    prefix + f"api/v1/unique-tournament/{leagueid}/season/{seasonid}/standings/total")[
                    'standings'][0][
                    'rows']
            for team in teams:
                teamids.append(team['team']['id'])
            return teamids


        def get_playerids(teamid):
            playerids = []
            players = fetch_and_parse_json_cached(prefix + f"api/v1/team/{teamid}/players")['players']
            for player in players:
                playerids.append((player['player']['id'], player['player']['name']))
            return playerids


        def get_playerid_from_name(name):
            alteredname = name.replace(" ", "%20")
            playerid = \
                fetch_and_parse_json_cached_regular(
                    prefix + f"api/v1/search/player-team-persons?q={alteredname}&page=0")[
                    'results'][0][
                    'entity'][
                    'id']
            return playerid


        def get_player_attributes(playerid):
            player_attributes = check_website_and_assign_cached(
                prefix + f"api/v1/player/{playerid}/attribute-overviews")
            if player_attributes is not None:
                player_attributes = player_attributes['playerAttributeOverviews'][0]
                if 'attacking' in player_attributes and 'creativity' in player_attributes and 'defending' in player_attributes and 'tactical' in player_attributes and 'technical' in player_attributes:
                    return [player_attributes['attacking'], player_attributes['creativity'],
                            player_attributes['defending'],
                            player_attributes['tactical'], player_attributes['technical']]
            return None


        #

        playername = input("Enter the name of the player you want to compare with: ")
        leaguename = input("Enter the name of the league you want to find similar players from: ")
        leagueid, seasonid = get_league_id_and_season_id(leaguename)
        teamids = get_teamids(leagueid, seasonid)
        players = []
        for teamid in teamids:
            playerids = get_playerids(teamid)
            players.extend(playerids)

        if any(char.isdigit() for char in playername):
            print("Using hypothetical player")
            target = (0, list(map(int, playername.split())))
        else:

            targetid = get_playerid_from_name(playername)
            target = (targetid, get_player_attributes(targetid))
            if target[1] is None:
                raise MyCustomError("Target player has no attributes, please try again with a different player")
        all = []
        for player, name in players:
            attributes = get_player_attributes(player)
            if attributes is not None:
                all.append((player, attributes, name))
        residuals_with_ids = []
        for x in all:
            if x[0] != target[0]:
                residuals = compare_residuals(target[1], x[1])
                residuals_with_ids.append((x[2], residuals))

        residuals_with_ids.sort(key=lambda x: x[1])
        for j in range(10):
            if j == 0:
                suffix = "st"
            elif j == 1:
                suffix = "nd"
            elif j == 2:
                suffix = "rd"
            else:
                suffix = "th"
            print(
                f"{j + 1}{suffix} Closest Player: {residuals_with_ids[j][0]}, Residuals: {round(residuals_with_ids[j][1], 1)}")

else:

    print("Caching is disabled")
    print("Fetching data directly from the website")


    def fetch_and_parse_json(url):
        response = requests.get(url)
        response.raise_for_status()  # Ensure we raise an error for bad status codes
        data = response.json()
        return data


    def check_website_and_assign(url):
        try:
            response = requests.get(url)
            # Check if the response status code is 200 (OK)
            if response.status_code == 200:
                variable = response.json()
            else:
                variable = None
        except requests.RequestException as e:
            # Handle any exceptions (like network errors)
            print(f"Error checking {url}: {e}")
            variable = None

        return variable


    def get_league_id_and_season_id(league_name):
        leagueid = \
            fetch_and_parse_json(f"http://www.sofascore.com/api/v1/search/all?q={league_name}&page=0")['results'][0][
                'entity']['id']
        seasonid = \
            fetch_and_parse_json(f"http://www.sofascore.com/api/v1/unique-tournament/{leagueid}/seasons")['seasons'][0][
                'id']
        return leagueid, seasonid


    def get_teamids(leagueid, seasonid):
        teamids = []
        teams = fetch_and_parse_json(
            f"http://www.sofascore.com/api/v1/unique-tournament/{leagueid}/season/{seasonid}/standings/total")[
            'standings'][0][
            'rows']
        for team in teams:
            teamids.append(team['team']['id'])
        return teamids


    def get_playerids(teamid):
        playerids = []
        players = fetch_and_parse_json(f"http://www.sofascore.com/api/v1/team/{teamid}/players")['players']
        for player in players:
            playerids.append((player['player']['id'], player['player']['name']))
        return playerids


    def get_playerid_from_name(name):
        alteredname = name.replace(" ", "%20")
        playerid = \
            fetch_and_parse_json(f"http://www.sofascore.com/api/v1/search/player-team-persons?q={alteredname}&page=0")[
                'results'][0]['entity'][
                'id']
        return playerid


    def get_player_attributes(playerid):
        player_attributes = check_website_and_assign(
            f"http://www.sofascore.com/api/v1/player/{playerid}/attribute-overviews")
        if player_attributes is not None:
            player_attributes = player_attributes['playerAttributeOverviews'][0]
            if 'attacking' in player_attributes and 'creativity' in player_attributes and 'defending' in player_attributes and 'tactical' in player_attributes and 'technical' in player_attributes:
                return [player_attributes['attacking'], player_attributes['creativity'], player_attributes['defending'],
                        player_attributes['tactical'], player_attributes['technical']]
        return None


    def compare_residuals(target, player):
        target_summed = sum(target)
        player_summed = sum(player)
        coefficent = target_summed / player_summed
        for i in range(len(player)):
            player[i] = player[i] * coefficent
        residuals = 0
        for i in range(len(target)):
            residuals += ((target[i] - player[i]) ** 2)
        return residuals


    playername = input("Enter the name of the player you want to compare with: ")
    leaguename = input("Enter the name of the league you want to find similar players from: ")
    leagueid, seasonid = get_league_id_and_season_id(leaguename)
    teamids = get_teamids(leagueid, seasonid)
    players = []
    for teamid in teamids:
        playerids = get_playerids(teamid)
        players.extend(playerids)

    targetid = get_playerid_from_name(playername)
    target = (targetid, get_player_attributes(targetid))

    all = []
    for player, name in players:
        attributes = get_player_attributes(player)
        if attributes is not None:
            all.append((player, attributes, name))
    residuals_with_ids = []
    for x in all:
        if x[0] != target[0]:
            residuals = compare_residuals(target[1], x[1])
            residuals_with_ids.append((x[2], residuals))

    residuals_with_ids.sort(key=lambda x: x[1])
    for j in range(10):
        if j == 0:
            suffix = "st"
        elif j == 1:
            suffix = "nd"
        elif j == 2:
            suffix = "rd"
        else:
            suffix = "th"
        print(
            f"{j + 1}{suffix} Closest Player: {residuals_with_ids[j][0]}, Residuals: {round(residuals_with_ids[j][1], 1)}")
