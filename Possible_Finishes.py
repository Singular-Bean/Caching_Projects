import itertools
import copy
import requests
import os
import json
import re

prefix = "http://localhost:8080/"
run_in_terminal = "mitmproxy -s cacher_forever.py --mode reverse:http://www.sofascore.com --listen-port 8080"

CACHE_DIR = "./cache"

ultimatum = input(
    "What would you like to do?\n1. Use caching\n2. Fetch from the website\n3. Use an example dataset (data from the premier league 26/04/25)\n")

if ultimatum == "1":

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


    def fetch_and_parse_json(url: str, headers=None):
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


    def get_league_id_and_season_id(league_name):
        leagueid = \
            fetch_and_parse_json(f"{prefix}api/v1/search/all?q={league_name}&page=0")['results'][0]['entity'][
                'id']
        seasonid = fetch_and_parse_json(f"{prefix}api/v1/unique-tournament/{leagueid}/seasons")['seasons'][0]['id']
        return leagueid, seasonid


    def get_results_and_remaining_matches(leagueid, seasonid):
        matchlist = []
        completed = []
        remaining = []
        data = fetch_and_parse_json(
            f"{prefix}api/v1/unique-tournament/{leagueid}/season/{seasonid}/events/round/{1}")['events']
        matchlist.append(data)
        rounds = ((len(matchlist[0]) * 2) - 1) * 2
        for i in range(2, rounds + 1):
            matchlist.append(fetch_and_parse_json(
                f"{prefix}api/v1/unique-tournament/{leagueid}/season/{seasonid}/events/round/{i}")['events'])
        for i in matchlist:
            for j in i:
                if j['status']['code'] == 100:
                    completed.append([j['homeTeam']['name'], [j['homeScore']['current'], j['awayScore']['current']],
                                      j['awayTeam']['name']])
                elif j['status']['code'] == 0:
                    remaining.append([j['homeTeam']['name'], j['awayTeam']['name']])
        return completed, remaining


    def create_league_table(matches):
        # Initialize a dictionary to store team statistics
        league_table = {}

        for match in matches:
            home_team, home_score, away_score, away_team = match[0], match[1][0], match[1][1], match[2]

            # Initialize teams
            for team in [home_team, away_team]:
                if team not in league_table:
                    league_table[team] = {'points': 0, 'goal_difference': 0, 'goals_scored': 0, 'games_played': 0}

            # Update stats
            league_table[home_team]['games_played'] += 1
            league_table[away_team]['games_played'] += 1
            league_table[home_team]['goals_scored'] += home_score
            league_table[away_team]['goals_scored'] += away_score
            league_table[home_team]['goal_difference'] += (home_score - away_score)
            league_table[away_team]['goal_difference'] += (away_score - home_score)

            # Update points
            if home_score > away_score:
                league_table[home_team]['points'] += 3
            elif home_score < away_score:
                league_table[away_team]['points'] += 3
            else:
                league_table[home_team]['points'] += 1
                league_table[away_team]['points'] += 1

        # Sort by points, goal difference, then goals scored
        sorted_teams = sorted(league_table.items(),
                              key=lambda x: (x[1]['points'], x[1]['goal_difference'], x[1]['goals_scored']),
                              reverse=True)

        return sorted_teams


    def games_in_hand_below(table, target):
        league_by_games_played = sorted(table, key=lambda x: (x[1]['games_played']), reverse=True)
        for x in league_by_games_played:
            if x[0] == target:
                target_games_played = x[1]['games_played']
                target_points = x[1]['points']
                table.remove(x)
                break
        teams_above = []
        teams_below = []
        for team, stats in table:
            difference_in_games_played = target_games_played - stats['games_played']
            if stats['games_played'] < target_games_played and stats[
                'points'] + difference_in_games_played * 3 < target_points:
                teams_below.append(team)
            elif stats['games_played'] >= target_games_played and stats['points'] < target_points:
                teams_below.append(team)
            else:
                teams_above.append(team)
        return teams_above, teams_below


    def maximum_points(table, target, remaining):
        number_of_games = 0
        for j in remaining:
            if j[0] == target or j[1] == target:
                number_of_games += 1
        for i in table:
            if i[0] == target:
                target_points = i[1]['points']
                break
        return target_points + (number_of_games * 3)


    def irrelevant_teams(table, target, remaining):
        standings = [team for team, _ in table]
        target_index = standings.index(target)
        teams_below = standings[target_index + 1:]
        teams_above = standings[:target_index]
        irrelevant = []
        current = table[target_index][1]['points']
        maximum = maximum_points(table, target, remaining)
        for i in teams_below:
            if maximum_points(table, i, remaining) < current:
                irrelevant.append(i)
        for i in teams_above:
            above_index = standings.index(i)
            above_current = table[above_index][1]['points']
            if maximum < above_current:
                irrelevant.append(i)
        return irrelevant


    def simulate_match_outcomes(matches, outcome_codes):
        simulated = []
        for match, outcome in zip(matches, outcome_codes):
            home, away = match
            if outcome == 0:  # home win
                simulated.append([home, [1, 0], away])
            elif outcome == 1:  # draw
                simulated.append([home, [0, 0], away])
            elif outcome == 2:  # away win
                simulated.append([home, [0, 1], away])
        return simulated


    def get_best_possible_position(target_team, current_matches, games_remaining):
        # Step 1: Generate current table
        initial_table = create_league_table(current_matches)
        standings = [team for team, _ in initial_table]
        if target_team not in standings:
            return None
        irrelevants = irrelevant_teams(initial_table, target_team, games_remaining)
        teams_above, teams_below = games_in_hand_below(initial_table, target_team)
        for a in teams_above:
            if a in irrelevants:
                teams_above.remove(a)
        for b in teams_below:
            if b in irrelevants:
                teams_below.remove(b)
        # Step 2: Apply "favorable" results to help target team
        adjusted_matches = copy.deepcopy(current_matches)
        reduced_games_remaining = []

        for home, away in games_remaining:
            home_above = home in teams_above
            away_above = away in teams_above
            home_below = home in teams_below
            away_below = away in teams_below
            home_target = home == target_team
            away_target = away == target_team
            home_irrelevant = home in irrelevants
            away_irrelevant = away in irrelevants

            # Favorable case: team above vs team below/target
            if (home_above and away_below) or (home_above and away_target) or (home_above and away_irrelevant):
                adjusted_matches.append([home, [0, 9], away])  # home loses
            elif (away_above and home_below) or (away_above and home_target) or (away_above and home_irrelevant):
                adjusted_matches.append([home, [9, 0], away])  # away loses
            elif (home_below and away_target) or (home_irrelevant and away_target):
                adjusted_matches.append([home, [0, 9], away])
            elif (away_below and home_target) or (away_irrelevant and home_target):
                adjusted_matches.append([home, [9, 0], away])
            elif home_above and away_above:
                reduced_games_remaining.append((home, away))  # leave this match to simulate
            else:
                adjusted_matches.append([home, [0, 0], away])  # draw
            # else: match doesn't involve teams above, doesn't affect best case, skip it
        # Step 3: Simulate remaining games between teams above
        all_outcomes = itertools.product([0, 1, 2], repeat=len(reduced_games_remaining))
        best_position = len(standings)

        for outcome in all_outcomes:
            future_matches = simulate_match_outcomes(reduced_games_remaining, outcome)
            full_matches = copy.deepcopy(adjusted_matches) + future_matches
            final_table = create_league_table(full_matches)
            for idx, (team, _) in enumerate(final_table, 1):
                if team == target_team:
                    best_position = min(best_position, idx)
                    break

        return best_position


    def get_worst_possible_position(target_team, current_matches, games_remaining):
        # Step 1: Generate current table
        initial_table = create_league_table(current_matches)
        standings = [team for team, _ in initial_table]
        if target_team not in standings:
            return None

        target_index = standings.index(target_team)
        teams_above = standings[:target_index]
        teams_below = standings[target_index + 1:]
        irrelevants = irrelevant_teams(initial_table, target_team, games_remaining)
        for a in teams_above:
            if a in irrelevants:
                teams_above.remove(a)
        for b in teams_below:
            if b in irrelevants:
                teams_below.remove(b)
        # Step 2: Apply "favorable" results to help target team
        adjusted_matches = copy.deepcopy(current_matches)
        reduced_games_remaining = []

        for home, away in games_remaining:
            home_above = home in teams_above
            away_above = away in teams_above
            home_below = home in teams_below
            away_below = away in teams_below
            home_target = home == target_team
            away_target = away == target_team
            home_irrelevant = home in irrelevants
            away_irrelevant = away in irrelevants

            # Favorable case: team above vs team below/target
            if (home_above and away_below) or (home_target and away_below) or (home_irrelevant and away_below):
                adjusted_matches.append([home, [0, 9], away])  # home loses
            elif (away_above and home_below) or (away_target and home_below) or (away_irrelevant and home_below):
                adjusted_matches.append([home, [9, 0], away])  # away loses
            elif (home_above and away_target) or (home_irrelevant and away_target):
                adjusted_matches.append([home, [9, 0], away])
            elif (away_above and home_target) or (away_irrelevant and home_target):
                adjusted_matches.append([home, [0, 9], away])
            elif home_below and away_below:
                reduced_games_remaining.append((home, away))  # leave this match to simulate
            else:
                adjusted_matches.append([home, [0, 0], away])
            # else: match doesn't involve teams above, doesn't affect best case, skip it
        # Step 3: Simulate remaining games between teams above
        all_outcomes = itertools.product([0, 1, 2], repeat=len(reduced_games_remaining))

        worst_position = 1

        for outcome in all_outcomes:
            future_matches = simulate_match_outcomes(reduced_games_remaining, outcome)
            full_matches = copy.deepcopy(adjusted_matches) + future_matches
            final_table = create_league_table(full_matches)
            for idx, (team, _) in enumerate(final_table, 1):
                if team == target_team:
                    worst_position = max(worst_position, idx)
                    break

        return worst_position


    def get_possible_positions(target_team, current_matches, games_remaining):
        best = get_best_possible_position(target_team, current_matches, games_remaining)
        worst = get_worst_possible_position(target_team, current_matches, games_remaining)
        return best, worst


    def create_league_table_and_print(matches, remaining):
        # Initialize a dictionary to store team statistics
        league_table = {}
        teams = []
        for match in matches:
            home_team, home_score, away_score, away_team = match[0], match[1][0], match[1][1], match[2]

            # Initialize teams
            for team in [home_team, away_team]:
                if team not in league_table:
                    league_table[team] = {'points': 0, 'goal_difference': 0, 'goals_scored': 0, 'games_played': 0,
                                          'best_possible_position': 0, 'worst_possible_position': 0}
                    teams.append(team)

            # Update stats
            league_table[home_team]['games_played'] += 1
            league_table[away_team]['games_played'] += 1
            league_table[home_team]['goals_scored'] += home_score
            league_table[away_team]['goals_scored'] += away_score
            league_table[home_team]['goal_difference'] += (home_score - away_score)
            league_table[away_team]['goal_difference'] += (away_score - home_score)

            # Update points
            if home_score > away_score:
                league_table[home_team]['points'] += 3
            elif home_score < away_score:
                league_table[away_team]['points'] += 3
            else:
                league_table[home_team]['points'] += 1
                league_table[away_team]['points'] += 1
        for team in teams:
            best, worst = get_possible_positions(team, matches, remaining)
            league_table[team]['best_possible_position'] = best
            league_table[team]['worst_possible_position'] = worst
        # Sort by points, goal difference, then goals scored
        sorted_teams = sorted(league_table.items(),
                              key=lambda x: (x[1]['points'], x[1]['goal_difference'], x[1]['goals_scored']),
                              reverse=True)
        # Print table
        print(f"{'Pos':<3} {'Team':<22} {'Points':<6} {'GD':<4} {'GS':<4} {'GP':<4} {'Possible Finishes':<17}")
        for team, stats in sorted_teams:
            if stats['best_possible_position'] != stats['worst_possible_position']:
                print(
                    f"{sorted_teams.index((team, stats)) + 1:<2}  {team:<22} {stats['points']:<6} {stats['goal_difference']:<4} {stats['goals_scored']:<4} {stats['games_played']:<4} {f"{stats['best_possible_position']}-{stats['worst_possible_position']}":<17}")
            else:
                print(
                    f"{sorted_teams.index((team, stats)) + 1:<2}  {team:<22} {stats['points']:<6} {stats['goal_difference']:<4} {stats['goals_scored']:<4} {stats['games_played']:<4} {f"{stats['best_possible_position']}":<17}")


    matches = [['Manchester United', [1, 0], 'Fulham'], ['Ipswich Town', [0, 2], 'Liverpool'],
               ['Arsenal', [2, 0], 'Wolverhampton'], ['Everton', [0, 3], 'Brighton & Hove Albion'],
               ['Newcastle United', [1, 0], 'Southampton'], ['Nottingham Forest', [1, 1], 'Bournemouth'],
               ['West Ham United', [1, 2], 'Aston Villa'], ['Brentford', [2, 1], 'Crystal Palace'],
               ['Chelsea', [0, 2], 'Manchester City'], ['Leicester City', [1, 1], 'Tottenham Hotspur'],
               ['Brighton & Hove Albion', [2, 1], 'Manchester United'], ['Crystal Palace', [0, 2], 'West Ham United'],
               ['Fulham', [2, 1], 'Leicester City'], ['Manchester City', [4, 1], 'Ipswich Town'],
               ['Southampton', [0, 1], 'Nottingham Forest'], ['Tottenham Hotspur', [4, 0], 'Everton'],
               ['Aston Villa', [0, 2], 'Arsenal'], ['Bournemouth', [1, 1], 'Newcastle United'],
               ['Wolverhampton', [2, 6], 'Chelsea'], ['Liverpool', [2, 0], 'Brentford'],
               ['Arsenal', [1, 1], 'Brighton & Hove Albion'], ['Brentford', [3, 1], 'Southampton'],
               ['Everton', [2, 3], 'Bournemouth'], ['Ipswich Town', [1, 1], 'Fulham'],
               ['Leicester City', [1, 2], 'Aston Villa'], ['Nottingham Forest', [1, 1], 'Wolverhampton'],
               ['West Ham United', [1, 3], 'Manchester City'], ['Chelsea', [1, 1], 'Crystal Palace'],
               ['Newcastle United', [2, 1], 'Tottenham Hotspur'], ['Manchester United', [0, 3], 'Liverpool'],
               ['Southampton', [0, 3], 'Manchester United'], ['Brighton & Hove Albion', [0, 0], 'Ipswich Town'],
               ['Crystal Palace', [2, 2], 'Leicester City'], ['Fulham', [1, 1], 'West Ham United'],
               ['Liverpool', [0, 1], 'Nottingham Forest'], ['Manchester City', [2, 1], 'Brentford'],
               ['Aston Villa', [3, 2], 'Everton'], ['Bournemouth', [0, 1], 'Chelsea'],
               ['Tottenham Hotspur', [0, 1], 'Arsenal'], ['Wolverhampton', [1, 2], 'Newcastle United'],
               ['West Ham United', [0, 3], 'Chelsea'], ['Aston Villa', [3, 1], 'Wolverhampton'],
               ['Fulham', [3, 1], 'Newcastle United'], ['Leicester City', [1, 1], 'Everton'],
               ['Liverpool', [3, 0], 'Bournemouth'], ['Southampton', [1, 1], 'Ipswich Town'],
               ['Tottenham Hotspur', [3, 1], 'Brentford'], ['Crystal Palace', [0, 0], 'Manchester United'],
               ['Brighton & Hove Albion', [2, 2], 'Nottingham Forest'], ['Manchester City', [2, 2], 'Arsenal'],
               ['Newcastle United', [1, 1], 'Manchester City'], ['Arsenal', [4, 2], 'Leicester City'],
               ['Brentford', [1, 1], 'West Ham United'], ['Chelsea', [4, 2], 'Brighton & Hove Albion'],
               ['Everton', [2, 1], 'Crystal Palace'], ['Nottingham Forest', [0, 1], 'Fulham'],
               ['Wolverhampton', [1, 2], 'Liverpool'], ['Ipswich Town', [2, 2], 'Aston Villa'],
               ['Manchester United', [0, 3], 'Tottenham Hotspur'], ['Bournemouth', [3, 1], 'Southampton'],
               ['Crystal Palace', [0, 1], 'Liverpool'], ['Arsenal', [3, 1], 'Southampton'],
               ['Brentford', [5, 3], 'Wolverhampton'], ['Leicester City', [1, 0], 'Bournemouth'],
               ['Manchester City', [3, 2], 'Fulham'], ['West Ham United', [4, 1], 'Ipswich Town'],
               ['Everton', [0, 0], 'Newcastle United'], ['Aston Villa', [0, 0], 'Manchester United'],
               ['Chelsea', [1, 1], 'Nottingham Forest'], ['Brighton & Hove Albion', [3, 2], 'Tottenham Hotspur'],
               ['Tottenham Hotspur', [4, 1], 'West Ham United'], ['Fulham', [1, 3], 'Aston Villa'],
               ['Manchester United', [2, 1], 'Brentford'], ['Newcastle United', [0, 1], 'Brighton & Hove Albion'],
               ['Southampton', [2, 3], 'Leicester City'], ['Ipswich Town', [0, 2], 'Everton'],
               ['Bournemouth', [2, 0], 'Arsenal'], ['Wolverhampton', [1, 2], 'Manchester City'],
               ['Liverpool', [2, 1], 'Chelsea'], ['Nottingham Forest', [1, 0], 'Crystal Palace'],
               ['Leicester City', [1, 3], 'Nottingham Forest'], ['Aston Villa', [1, 1], 'Bournemouth'],
               ['Brentford', [4, 3], 'Ipswich Town'], ['Brighton & Hove Albion', [2, 2], 'Wolverhampton'],
               ['Manchester City', [1, 0], 'Southampton'], ['Everton', [1, 1], 'Fulham'],
               ['Chelsea', [2, 1], 'Newcastle United'], ['Crystal Palace', [1, 0], 'Tottenham Hotspur'],
               ['West Ham United', [2, 1], 'Manchester United'], ['Arsenal', [2, 2], 'Liverpool'],
               ['Newcastle United', [1, 0], 'Arsenal'], ['Bournemouth', [2, 1], 'Manchester City'],
               ['Ipswich Town', [1, 1], 'Leicester City'], ['Liverpool', [2, 1], 'Brighton & Hove Albion'],
               ['Nottingham Forest', [3, 0], 'West Ham United'], ['Southampton', [1, 0], 'Everton'],
               ['Wolverhampton', [2, 2], 'Crystal Palace'], ['Tottenham Hotspur', [4, 1], 'Aston Villa'],
               ['Manchester United', [1, 1], 'Chelsea'], ['Fulham', [2, 1], 'Brentford'],
               ['Brentford', [3, 2], 'Bournemouth'], ['Crystal Palace', [0, 2], 'Fulham'],
               ['West Ham United', [0, 0], 'Everton'], ['Wolverhampton', [2, 0], 'Southampton'],
               ['Brighton & Hove Albion', [2, 1], 'Manchester City'], ['Liverpool', [2, 0], 'Aston Villa'],
               ['Manchester United', [3, 0], 'Leicester City'], ['Nottingham Forest', [1, 3], 'Newcastle United'],
               ['Tottenham Hotspur', [1, 2], 'Ipswich Town'], ['Chelsea', [1, 1], 'Arsenal'],
               ['Leicester City', [1, 2], 'Chelsea'], ['Arsenal', [3, 0], 'Nottingham Forest'],
               ['Aston Villa', [2, 2], 'Crystal Palace'], ['Bournemouth', [1, 2], 'Brighton & Hove Albion'],
               ['Everton', [0, 0], 'Brentford'], ['Fulham', [1, 4], 'Wolverhampton'],
               ['Manchester City', [0, 4], 'Tottenham Hotspur'], ['Southampton', [2, 3], 'Liverpool'],
               ['Ipswich Town', [1, 1], 'Manchester United'], ['Newcastle United', [0, 2], 'West Ham United'],
               ['Brighton & Hove Albion', [1, 1], 'Southampton'], ['Brentford', [4, 1], 'Leicester City'],
               ['Crystal Palace', [1, 1], 'Newcastle United'], ['Nottingham Forest', [1, 0], 'Ipswich Town'],
               ['Wolverhampton', [2, 4], 'Bournemouth'], ['West Ham United', [2, 5], 'Arsenal'],
               ['Chelsea', [3, 0], 'Aston Villa'], ['Manchester United', [4, 0], 'Everton'],
               ['Tottenham Hotspur', [1, 1], 'Fulham'], ['Liverpool', [2, 0], 'Manchester City'],
               ['Ipswich Town', [0, 1], 'Crystal Palace'], ['Leicester City', [3, 1], 'West Ham United'],
               ['Everton', [4, 0], 'Wolverhampton'], ['Manchester City', [3, 0], 'Nottingham Forest'],
               ['Newcastle United', [3, 3], 'Liverpool'], ['Southampton', [1, 5], 'Chelsea'],
               ['Arsenal', [2, 0], 'Manchester United'], ['Aston Villa', [3, 1], 'Brentford'],
               ['Fulham', [3, 1], 'Brighton & Hove Albion'], ['Bournemouth', [1, 0], 'Tottenham Hotspur'],
               ['Aston Villa', [1, 0], 'Southampton'], ['Brentford', [4, 2], 'Newcastle United'],
               ['Crystal Palace', [2, 2], 'Manchester City'], ['Manchester United', [2, 3], 'Nottingham Forest'],
               ['Fulham', [1, 1], 'Arsenal'], ['Ipswich Town', [1, 2], 'Bournemouth'],
               ['Leicester City', [2, 2], 'Brighton & Hove Albion'], ['Tottenham Hotspur', [3, 4], 'Chelsea'],
               ['West Ham United', [2, 1], 'Wolverhampton'], ['Everton', [2, 2], 'Liverpool'],
               ['Arsenal', [0, 0], 'Everton'], ['Liverpool', [2, 2], 'Fulham'],
               ['Newcastle United', [4, 0], 'Leicester City'], ['Wolverhampton', [1, 2], 'Ipswich Town'],
               ['Nottingham Forest', [2, 1], 'Aston Villa'], ['Brighton & Hove Albion', [1, 3], 'Crystal Palace'],
               ['Manchester City', [1, 2], 'Manchester United'], ['Chelsea', [2, 1], 'Brentford'],
               ['Southampton', [0, 5], 'Tottenham Hotspur'], ['Bournemouth', [1, 1], 'West Ham United'],
               ['Aston Villa', [2, 1], 'Manchester City'], ['Brentford', [0, 2], 'Nottingham Forest'],
               ['Ipswich Town', [0, 4], 'Newcastle United'], ['West Ham United', [1, 1], 'Brighton & Hove Albion'],
               ['Crystal Palace', [1, 5], 'Arsenal'], ['Everton', [0, 0], 'Chelsea'], ['Fulham', [0, 0], 'Southampton'],
               ['Leicester City', [0, 3], 'Wolverhampton'], ['Manchester United', [0, 3], 'Bournemouth'],
               ['Tottenham Hotspur', [3, 6], 'Liverpool'], ['Manchester City', [1, 1], 'Everton'],
               ['Bournemouth', [0, 0], 'Crystal Palace'], ['Chelsea', [1, 2], 'Fulham'],
               ['Newcastle United', [3, 0], 'Aston Villa'], ['Nottingham Forest', [1, 0], 'Tottenham Hotspur'],
               ['Southampton', [0, 1], 'West Ham United'], ['Wolverhampton', [2, 0], 'Manchester United'],
               ['Liverpool', [3, 1], 'Leicester City'], ['Brighton & Hove Albion', [0, 0], 'Brentford'],
               ['Arsenal', [1, 0], 'Ipswich Town'], ['Leicester City', [0, 2], 'Manchester City'],
               ['Crystal Palace', [2, 1], 'Southampton'], ['Everton', [0, 2], 'Nottingham Forest'],
               ['Fulham', [2, 2], 'Bournemouth'], ['Tottenham Hotspur', [2, 2], 'Wolverhampton'],
               ['West Ham United', [0, 5], 'Liverpool'], ['Aston Villa', [2, 2], 'Brighton & Hove Albion'],
               ['Ipswich Town', [2, 0], 'Chelsea'], ['Manchester United', [0, 2], 'Newcastle United'],
               ['Brentford', [1, 3], 'Arsenal'], ['Tottenham Hotspur', [1, 2], 'Newcastle United'],
               ['Aston Villa', [2, 1], 'Leicester City'], ['Bournemouth', [1, 0], 'Everton'],
               ['Crystal Palace', [1, 1], 'Chelsea'], ['Manchester City', [4, 1], 'West Ham United'],
               ['Southampton', [0, 5], 'Brentford'], ['Brighton & Hove Albion', [1, 1], 'Arsenal'],
               ['Fulham', [2, 2], 'Ipswich Town'], ['Liverpool', [2, 2], 'Manchester United'],
               ['Wolverhampton', [0, 3], 'Nottingham Forest'], ['Brentford', [2, 2], 'Manchester City'],
               ['Chelsea', [2, 2], 'Bournemouth'], ['West Ham United', [3, 2], 'Fulham'],
               ['Nottingham Forest', [1, 1], 'Liverpool'], ['Everton', [0, 1], 'Aston Villa'],
               ['Leicester City', [0, 2], 'Crystal Palace'], ['Newcastle United', [3, 0], 'Wolverhampton'],
               ['Arsenal', [2, 1], 'Tottenham Hotspur'], ['Ipswich Town', [0, 2], 'Brighton & Hove Albion'],
               ['Manchester United', [3, 1], 'Southampton'], ['Newcastle United', [1, 4], 'Bournemouth'],
               ['Brentford', [0, 2], 'Liverpool'], ['Leicester City', [0, 2], 'Fulham'],
               ['West Ham United', [0, 2], 'Crystal Palace'], ['Arsenal', [2, 2], 'Aston Villa'],
               ['Everton', [3, 2], 'Tottenham Hotspur'], ['Manchester United', [1, 3], 'Brighton & Hove Albion'],
               ['Nottingham Forest', [3, 2], 'Southampton'], ['Ipswich Town', [0, 6], 'Manchester City'],
               ['Chelsea', [3, 1], 'Wolverhampton'], ['Bournemouth', [5, 0], 'Nottingham Forest'],
               ['Brighton & Hove Albion', [0, 1], 'Everton'], ['Liverpool', [4, 1], 'Ipswich Town'],
               ['Southampton', [1, 3], 'Newcastle United'], ['Wolverhampton', [0, 1], 'Arsenal'],
               ['Manchester City', [3, 1], 'Chelsea'], ['Crystal Palace', [1, 2], 'Brentford'],
               ['Tottenham Hotspur', [1, 2], 'Leicester City'], ['Aston Villa', [1, 1], 'West Ham United'],
               ['Fulham', [0, 1], 'Manchester United'], ['Nottingham Forest', [7, 0], 'Brighton & Hove Albion'],
               ['Bournemouth', [0, 2], 'Liverpool'], ['Everton', [4, 0], 'Leicester City'],
               ['Ipswich Town', [1, 2], 'Southampton'], ['Newcastle United', [1, 2], 'Fulham'],
               ['Wolverhampton', [2, 0], 'Aston Villa'], ['Brentford', [0, 2], 'Tottenham Hotspur'],
               ['Manchester United', [0, 2], 'Crystal Palace'], ['Arsenal', [5, 1], 'Manchester City'],
               ['Chelsea', [2, 1], 'West Ham United'], ['Brighton & Hove Albion', [3, 0], 'Chelsea'],
               ['Leicester City', [0, 2], 'Arsenal'], ['Aston Villa', [1, 1], 'Ipswich Town'],
               ['Fulham', [2, 1], 'Nottingham Forest'], ['Manchester City', [4, 0], 'Newcastle United'],
               ['Southampton', [1, 3], 'Bournemouth'], ['West Ham United', [0, 1], 'Brentford'],
               ['Crystal Palace', [1, 2], 'Everton'], ['Liverpool', [2, 1], 'Wolverhampton'],
               ['Tottenham Hotspur', [1, 0], 'Manchester United'], ['Leicester City', [0, 4], 'Brentford'],
               ['Everton', [2, 2], 'Manchester United'], ['Arsenal', [0, 1], 'West Ham United'],
               ['Bournemouth', [0, 1], 'Wolverhampton'], ['Fulham', [0, 2], 'Crystal Palace'],
               ['Ipswich Town', [1, 4], 'Tottenham Hotspur'], ['Southampton', [0, 4], 'Brighton & Hove Albion'],
               ['Aston Villa', [2, 1], 'Chelsea'], ['Newcastle United', [4, 3], 'Nottingham Forest'],
               ['Manchester City', [0, 2], 'Liverpool'], ['Brighton & Hove Albion', [2, 1], 'Bournemouth'],
               ['Crystal Palace', [4, 1], 'Aston Villa'], ['Wolverhampton', [1, 2], 'Fulham'],
               ['Chelsea', [4, 0], 'Southampton'], ['Brentford', [1, 1], 'Everton'],
               ['Manchester United', [3, 2], 'Ipswich Town'], ['Nottingham Forest', [0, 0], 'Arsenal'],
               ['Tottenham Hotspur', [0, 1], 'Manchester City'], ['Liverpool', [2, 0], 'Newcastle United'],
               ['West Ham United', [2, 0], 'Leicester City'], ['Nottingham Forest', [1, 0], 'Manchester City'],
               ['Brighton & Hove Albion', [2, 1], 'Fulham'], ['Crystal Palace', [1, 0], 'Ipswich Town'],
               ['Liverpool', [3, 1], 'Southampton'], ['Brentford', [0, 1], 'Aston Villa'],
               ['Wolverhampton', [1, 1], 'Everton'], ['Chelsea', [1, 0], 'Leicester City'],
               ['Tottenham Hotspur', [2, 2], 'Bournemouth'], ['Manchester United', [1, 1], 'Arsenal'],
               ['West Ham United', [0, 1], 'Newcastle United'], ['Aston Villa', [2, 2], 'Liverpool'],
               ['Everton', [1, 1], 'West Ham United'], ['Ipswich Town', [2, 4], 'Nottingham Forest'],
               ['Manchester City', [2, 2], 'Brighton & Hove Albion'], ['Southampton', [1, 2], 'Wolverhampton'],
               ['Bournemouth', [1, 2], 'Brentford'], ['Arsenal', [1, 0], 'Chelsea'],
               ['Fulham', [2, 0], 'Tottenham Hotspur'], ['Leicester City', [0, 3], 'Manchester United'],
               ['Newcastle United', [5, 0], 'Crystal Palace'], ['Arsenal', [2, 1], 'Fulham'],
               ['Wolverhampton', [1, 0], 'West Ham United'], ['Nottingham Forest', [1, 0], 'Manchester United'],
               ['Bournemouth', [1, 2], 'Ipswich Town'], ['Brighton & Hove Albion', [0, 3], 'Aston Villa'],
               ['Manchester City', [2, 0], 'Leicester City'], ['Newcastle United', [2, 1], 'Brentford'],
               ['Southampton', [1, 1], 'Crystal Palace'], ['Liverpool', [1, 0], 'Everton'],
               ['Chelsea', [1, 0], 'Tottenham Hotspur'], ['Everton', [1, 1], 'Arsenal'],
               ['Crystal Palace', [2, 1], 'Brighton & Hove Albion'], ['Ipswich Town', [1, 2], 'Wolverhampton'],
               ['West Ham United', [2, 2], 'Bournemouth'], ['Aston Villa', [2, 1], 'Nottingham Forest'],
               ['Brentford', [0, 0], 'Chelsea'], ['Fulham', [3, 2], 'Liverpool'],
               ['Tottenham Hotspur', [3, 1], 'Southampton'], ['Manchester United', [0, 0], 'Manchester City'],
               ['Leicester City', [0, 3], 'Newcastle United'], ['Manchester City', [5, 2], 'Crystal Palace'],
               ['Brighton & Hove Albion', [2, 2], 'Leicester City'], ['Nottingham Forest', [0, 1], 'Everton'],
               ['Southampton', [0, 3], 'Aston Villa'], ['Arsenal', [1, 1], 'Brentford'],
               ['Chelsea', [2, 2], 'Ipswich Town'], ['Liverpool', [2, 1], 'West Ham United'],
               ['Wolverhampton', [4, 2], 'Tottenham Hotspur'], ['Newcastle United', [4, 1], 'Manchester United'],
               ['Bournemouth', [1, 0], 'Fulham'], ['Brentford', [4, 2], 'Brighton & Hove Albion'],
               ['Crystal Palace', [0, 0], 'Bournemouth'], ['Everton', [0, 2], 'Manchester City'],
               ['West Ham United', [1, 1], 'Southampton'], ['Aston Villa', [4, 1], 'Newcastle United'],
               ['Fulham', [1, 2], 'Chelsea'], ['Ipswich Town', [0, 4], 'Arsenal'],
               ['Manchester United', [0, 1], 'Wolverhampton'], ['Leicester City', [0, 1], 'Liverpool'],
               ['Tottenham Hotspur', [1, 2], 'Nottingham Forest'], ['Manchester City', [2, 1], 'Aston Villa'],
               ['Arsenal', [2, 2], 'Crystal Palace'], ['Chelsea', [1, 0], 'Everton'],
               ['Brighton & Hove Albion', [3, 2], 'West Ham United'], ['Newcastle United', [3, 0], 'Ipswich Town'],
               ['Southampton', [1, 2], 'Fulham'], ['Wolverhampton', [3, 0], 'Leicester City']]

    games_remaining = [['Bournemouth', 'Manchester United'], ['Liverpool', 'Tottenham Hotspur'],
                       ['Nottingham Forest', 'Brentford'], ['Manchester City', 'Wolverhampton'],
                       ['Aston Villa', 'Fulham'],
                       ['Everton', 'Ipswich Town'], ['Leicester City', 'Southampton'], ['Arsenal', 'Bournemouth'],
                       ['Brentford', 'Manchester United'], ['Brighton & Hove Albion', 'Newcastle United'],
                       ['West Ham United', 'Tottenham Hotspur'], ['Chelsea', 'Liverpool'],
                       ['Crystal Palace', 'Nottingham Forest'], ['Fulham', 'Everton'], ['Ipswich Town', 'Brentford'],
                       ['Southampton', 'Manchester City'], ['Wolverhampton', 'Brighton & Hove Albion'],
                       ['Bournemouth', 'Aston Villa'], ['Newcastle United', 'Chelsea'],
                       ['Manchester United', 'West Ham United'], ['Nottingham Forest', 'Leicester City'],
                       ['Tottenham Hotspur', 'Crystal Palace'], ['Liverpool', 'Arsenal'],
                       ['Chelsea', 'Manchester United'],
                       ['Everton', 'Southampton'], ['Aston Villa', 'Tottenham Hotspur'],
                       ['West Ham United', 'Nottingham Forest'], ['Brentford', 'Fulham'],
                       ['Crystal Palace', 'Wolverhampton'], ['Leicester City', 'Ipswich Town'],
                       ['Arsenal', 'Newcastle United'], ['Manchester City', 'Bournemouth'],
                       ['Brighton & Hove Albion', 'Liverpool'], ['Bournemouth', 'Leicester City'],
                       ['Fulham', 'Manchester City'], ['Ipswich Town', 'West Ham United'],
                       ['Liverpool', 'Crystal Palace'],
                       ['Manchester United', 'Aston Villa'], ['Newcastle United', 'Everton'],
                       ['Nottingham Forest', 'Chelsea'], ['Southampton', 'Arsenal'],
                       ['Tottenham Hotspur', 'Brighton & Hove Albion'], ['Wolverhampton', 'Brentford']]

    leagueid, seasonid = get_league_id_and_season_id(input("Enter league name: "))

    matches, games_remaining = get_results_and_remaining_matches(leagueid, seasonid)

    create_league_table_and_print(matches, games_remaining)

elif ultimatum == "2":

    print("Caching is disabled")
    print("Fetching data directly from the website")


    def fetch_and_parse_json(url):
        response = requests.get(url)
        response.raise_for_status()  # Ensure we raise an error for bad status codes
        data = response.json()
        return data


    def get_league_id_and_season_id(league_name):
        leagueid = \
            fetch_and_parse_json(f"http://www.sofascore.com/api/v1/search/all?q={league_name}&page=0")['results'][0][
                'entity'][
                'id']
        seasonid = \
            fetch_and_parse_json(f"http://www.sofascore.com/api/v1/unique-tournament/{leagueid}/seasons")['seasons'][0][
                'id']
        return leagueid, seasonid


    def get_results_and_remaining_matches(leagueid, seasonid):
        matchlist = []
        completed = []
        remaining = []
        data = fetch_and_parse_json(
            f"http://www.sofascore.com/api/v1/unique-tournament/{leagueid}/season/{seasonid}/events/round/{1}")[
            'events']
        matchlist.append(data)
        rounds = ((len(matchlist[0]) * 2) - 1) * 2
        for i in range(2, rounds + 1):
            matchlist.append(fetch_and_parse_json(
                f"http://www.sofascore.com/api/v1/unique-tournament/{leagueid}/season/{seasonid}/events/round/{i}")[
                                 'events'])
        for i in matchlist:
            for j in i:
                if j['status']['code'] == 100:
                    completed.append([j['homeTeam']['name'], [j['homeScore']['current'], j['awayScore']['current']],
                                      j['awayTeam']['name']])
                elif j['status']['code'] == 0:
                    remaining.append([j['homeTeam']['name'], j['awayTeam']['name']])
        return completed, remaining


    def create_league_table(matches):
        # Initialize a dictionary to store team statistics
        league_table = {}

        for match in matches:
            home_team, home_score, away_score, away_team = match[0], match[1][0], match[1][1], match[2]

            # Initialize teams
            for team in [home_team, away_team]:
                if team not in league_table:
                    league_table[team] = {'points': 0, 'goal_difference': 0, 'goals_scored': 0, 'games_played': 0}

            # Update stats
            league_table[home_team]['games_played'] += 1
            league_table[away_team]['games_played'] += 1
            league_table[home_team]['goals_scored'] += home_score
            league_table[away_team]['goals_scored'] += away_score
            league_table[home_team]['goal_difference'] += (home_score - away_score)
            league_table[away_team]['goal_difference'] += (away_score - home_score)

            # Update points
            if home_score > away_score:
                league_table[home_team]['points'] += 3
            elif home_score < away_score:
                league_table[away_team]['points'] += 3
            else:
                league_table[home_team]['points'] += 1
                league_table[away_team]['points'] += 1

        # Sort by points, goal difference, then goals scored
        sorted_teams = sorted(league_table.items(),
                              key=lambda x: (x[1]['points'], x[1]['goal_difference'], x[1]['goals_scored']),
                              reverse=True)

        return sorted_teams


    def games_in_hand_below(table, target):
        league_by_games_played = sorted(table, key=lambda x: (x[1]['games_played']), reverse=True)
        for x in league_by_games_played:
            if x[0] == target:
                target_games_played = x[1]['games_played']
                target_points = x[1]['points']
                table.remove(x)
                break
        teams_above = []
        teams_below = []
        for team, stats in table:
            difference_in_games_played = target_games_played - stats['games_played']
            if stats['games_played'] < target_games_played and stats[
                'points'] + difference_in_games_played * 3 < target_points:
                teams_below.append(team)
            elif stats['games_played'] >= target_games_played and stats['points'] < target_points:
                teams_below.append(team)
            else:
                teams_above.append(team)
        return teams_above, teams_below


    def maximum_points(table, target, remaining):
        number_of_games = 0
        for j in remaining:
            if j[0] == target or j[1] == target:
                number_of_games += 1
        for i in table:
            if i[0] == target:
                target_points = i[1]['points']
                break
        return target_points + (number_of_games * 3)


    def irrelevant_teams(table, target, remaining):
        standings = [team for team, _ in table]
        target_index = standings.index(target)
        teams_below = standings[target_index + 1:]
        teams_above = standings[:target_index]
        irrelevant = []
        current = table[target_index][1]['points']
        maximum = maximum_points(table, target, remaining)
        for i in teams_below:
            if maximum_points(table, i, remaining) < current:
                irrelevant.append(i)
        for i in teams_above:
            above_index = standings.index(i)
            above_current = table[above_index][1]['points']
            if maximum < above_current:
                irrelevant.append(i)
        return irrelevant


    def simulate_match_outcomes(matches, outcome_codes):
        simulated = []
        for match, outcome in zip(matches, outcome_codes):
            home, away = match
            if outcome == 0:  # home win
                simulated.append([home, [1, 0], away])
            elif outcome == 1:  # draw
                simulated.append([home, [0, 0], away])
            elif outcome == 2:  # away win
                simulated.append([home, [0, 1], away])
        return simulated


    def get_best_possible_position(target_team, current_matches, games_remaining):
        # Step 1: Generate current table
        initial_table = create_league_table(current_matches)
        standings = [team for team, _ in initial_table]
        if target_team not in standings:
            return None
        irrelevants = irrelevant_teams(initial_table, target_team, games_remaining)
        teams_above, teams_below = games_in_hand_below(initial_table, target_team)
        for a in teams_above:
            if a in irrelevants:
                teams_above.remove(a)
        for b in teams_below:
            if b in irrelevants:
                teams_below.remove(b)
        # Step 2: Apply "favorable" results to help target team
        adjusted_matches = copy.deepcopy(current_matches)
        reduced_games_remaining = []

        for home, away in games_remaining:
            home_above = home in teams_above
            away_above = away in teams_above
            home_below = home in teams_below
            away_below = away in teams_below
            home_target = home == target_team
            away_target = away == target_team
            home_irrelevant = home in irrelevants
            away_irrelevant = away in irrelevants

            # Favorable case: team above vs team below/target
            if (home_above and away_below) or (home_above and away_target) or (home_above and away_irrelevant):
                adjusted_matches.append([home, [0, 9], away])  # home loses
            elif (away_above and home_below) or (away_above and home_target) or (away_above and home_irrelevant):
                adjusted_matches.append([home, [9, 0], away])  # away loses
            elif (home_below and away_target) or (home_irrelevant and away_target):
                adjusted_matches.append([home, [0, 9], away])
            elif (away_below and home_target) or (away_irrelevant and home_target):
                adjusted_matches.append([home, [9, 0], away])
            elif home_above and away_above:
                reduced_games_remaining.append((home, away))  # leave this match to simulate
            else:
                adjusted_matches.append([home, [0, 0], away])  # draw
            # else: match doesn't involve teams above, doesn't affect best case, skip it
        # Step 3: Simulate remaining games between teams above
        all_outcomes = itertools.product([0, 1, 2], repeat=len(reduced_games_remaining))
        best_position = len(standings)

        for outcome in all_outcomes:
            future_matches = simulate_match_outcomes(reduced_games_remaining, outcome)
            full_matches = copy.deepcopy(adjusted_matches) + future_matches
            final_table = create_league_table(full_matches)
            for idx, (team, _) in enumerate(final_table, 1):
                if team == target_team:
                    best_position = min(best_position, idx)
                    break

        return best_position


    def get_worst_possible_position(target_team, current_matches, games_remaining):
        # Step 1: Generate current table
        initial_table = create_league_table(current_matches)
        standings = [team for team, _ in initial_table]
        if target_team not in standings:
            return None

        target_index = standings.index(target_team)
        teams_above = standings[:target_index]
        teams_below = standings[target_index + 1:]
        irrelevants = irrelevant_teams(initial_table, target_team, games_remaining)
        for a in teams_above:
            if a in irrelevants:
                teams_above.remove(a)
        for b in teams_below:
            if b in irrelevants:
                teams_below.remove(b)
        # Step 2: Apply "favorable" results to help target team
        adjusted_matches = copy.deepcopy(current_matches)
        reduced_games_remaining = []

        for home, away in games_remaining:
            home_above = home in teams_above
            away_above = away in teams_above
            home_below = home in teams_below
            away_below = away in teams_below
            home_target = home == target_team
            away_target = away == target_team
            home_irrelevant = home in irrelevants
            away_irrelevant = away in irrelevants

            # Favorable case: team above vs team below/target
            if (home_above and away_below) or (home_target and away_below) or (home_irrelevant and away_below):
                adjusted_matches.append([home, [0, 9], away])  # home loses
            elif (away_above and home_below) or (away_target and home_below) or (away_irrelevant and home_below):
                adjusted_matches.append([home, [9, 0], away])  # away loses
            elif (home_above and away_target) or (home_irrelevant and away_target):
                adjusted_matches.append([home, [9, 0], away])
            elif (away_above and home_target) or (away_irrelevant and home_target):
                adjusted_matches.append([home, [0, 9], away])
            elif home_below and away_below:
                reduced_games_remaining.append((home, away))  # leave this match to simulate
            else:
                adjusted_matches.append([home, [0, 0], away])
            # else: match doesn't involve teams above, doesn't affect best case, skip it
        # Step 3: Simulate remaining games between teams above
        all_outcomes = itertools.product([0, 1, 2], repeat=len(reduced_games_remaining))

        worst_position = 1

        for outcome in all_outcomes:
            future_matches = simulate_match_outcomes(reduced_games_remaining, outcome)
            full_matches = copy.deepcopy(adjusted_matches) + future_matches
            final_table = create_league_table(full_matches)
            for idx, (team, _) in enumerate(final_table, 1):
                if team == target_team:
                    worst_position = max(worst_position, idx)
                    break

        return worst_position


    def get_possible_positions(target_team, current_matches, games_remaining):
        best = get_best_possible_position(target_team, current_matches, games_remaining)
        worst = get_worst_possible_position(target_team, current_matches, games_remaining)
        return best, worst


    def create_league_table_and_print(matches, remaining):
        # Initialize a dictionary to store team statistics
        league_table = {}
        teams = []
        for match in matches:
            home_team, home_score, away_score, away_team = match[0], match[1][0], match[1][1], match[2]

            # Initialize teams
            for team in [home_team, away_team]:
                if team not in league_table:
                    league_table[team] = {'points': 0, 'goal_difference': 0, 'goals_scored': 0, 'games_played': 0,
                                          'best_possible_position': 0, 'worst_possible_position': 0}
                    teams.append(team)

            # Update stats
            league_table[home_team]['games_played'] += 1
            league_table[away_team]['games_played'] += 1
            league_table[home_team]['goals_scored'] += home_score
            league_table[away_team]['goals_scored'] += away_score
            league_table[home_team]['goal_difference'] += (home_score - away_score)
            league_table[away_team]['goal_difference'] += (away_score - home_score)

            # Update points
            if home_score > away_score:
                league_table[home_team]['points'] += 3
            elif home_score < away_score:
                league_table[away_team]['points'] += 3
            else:
                league_table[home_team]['points'] += 1
                league_table[away_team]['points'] += 1
        for team in teams:
            best, worst = get_possible_positions(team, matches, remaining)
            league_table[team]['best_possible_position'] = best
            league_table[team]['worst_possible_position'] = worst
        # Sort by points, goal difference, then goals scored
        sorted_teams = sorted(league_table.items(),
                              key=lambda x: (x[1]['points'], x[1]['goal_difference'], x[1]['goals_scored']),
                              reverse=True)
        # Print table
        print(f"{'Pos':<3} {'Team':<22} {'Points':<6} {'GD':<4} {'GS':<4} {'GP':<4} {'Possible Finishes':<17}")
        for team, stats in sorted_teams:
            if stats['best_possible_position'] != stats['worst_possible_position']:
                print(
                    f"{sorted_teams.index((team, stats)) + 1:<2}  {team:<22} {stats['points']:<6} {stats['goal_difference']:<4} {stats['goals_scored']:<4} {stats['games_played']:<4} {f"{stats['best_possible_position']}-{stats['worst_possible_position']}":<17}")
            else:
                print(
                    f"{sorted_teams.index((team, stats)) + 1:<2}  {team:<22} {stats['points']:<6} {stats['goal_difference']:<4} {stats['goals_scored']:<4} {stats['games_played']:<4} {f"{stats['best_possible_position']}":<17}")


    leagueid, seasonid = get_league_id_and_season_id(input("Enter league name: "))

    matches, games_remaining = get_results_and_remaining_matches(leagueid, seasonid)

    create_league_table_and_print(matches, games_remaining)

elif ultimatum == "3":

    def create_league_table(matches):
        # Initialize a dictionary to store team statistics
        league_table = {}

        for match in matches:
            home_team, home_score, away_score, away_team = match[0], match[1][0], match[1][1], match[2]

            # Initialize teams
            for team in [home_team, away_team]:
                if team not in league_table:
                    league_table[team] = {'points': 0, 'goal_difference': 0, 'goals_scored': 0, 'games_played': 0}

            # Update stats
            league_table[home_team]['games_played'] += 1
            league_table[away_team]['games_played'] += 1
            league_table[home_team]['goals_scored'] += home_score
            league_table[away_team]['goals_scored'] += away_score
            league_table[home_team]['goal_difference'] += (home_score - away_score)
            league_table[away_team]['goal_difference'] += (away_score - home_score)

            # Update points
            if home_score > away_score:
                league_table[home_team]['points'] += 3
            elif home_score < away_score:
                league_table[away_team]['points'] += 3
            else:
                league_table[home_team]['points'] += 1
                league_table[away_team]['points'] += 1

        # Sort by points, goal difference, then goals scored
        sorted_teams = sorted(league_table.items(),
                              key=lambda x: (x[1]['points'], x[1]['goal_difference'], x[1]['goals_scored']),
                              reverse=True)

        return sorted_teams


    def games_in_hand_below(table, target):
        league_by_games_played = sorted(table, key=lambda x: (x[1]['games_played']), reverse=True)
        for x in league_by_games_played:
            if x[0] == target:
                target_games_played = x[1]['games_played']
                target_points = x[1]['points']
                table.remove(x)
                break
        teams_above = []
        teams_below = []
        for team, stats in table:
            difference_in_games_played = target_games_played - stats['games_played']
            if stats['games_played'] < target_games_played and stats[
                'points'] + difference_in_games_played * 3 < target_points:
                teams_below.append(team)
            elif stats['games_played'] >= target_games_played and stats['points'] < target_points:
                teams_below.append(team)
            else:
                teams_above.append(team)
        return teams_above, teams_below


    def maximum_points(table, target, remaining):
        number_of_games = 0
        for j in remaining:
            if j[0] == target or j[1] == target:
                number_of_games += 1
        for i in table:
            if i[0] == target:
                target_points = i[1]['points']
                break
        return target_points + (number_of_games * 3)


    def irrelevant_teams(table, target, remaining):
        standings = [team for team, _ in table]
        target_index = standings.index(target)
        teams_below = standings[target_index + 1:]
        teams_above = standings[:target_index]
        irrelevant = []
        current = table[target_index][1]['points']
        maximum = maximum_points(table, target, remaining)
        for i in teams_below:
            if maximum_points(table, i, remaining) < current:
                irrelevant.append(i)
        for i in teams_above:
            above_index = standings.index(i)
            above_current = table[above_index][1]['points']
            if maximum < above_current:
                irrelevant.append(i)
        return irrelevant


    def simulate_match_outcomes(matches, outcome_codes):
        simulated = []
        for match, outcome in zip(matches, outcome_codes):
            home, away = match
            if outcome == 0:  # home win
                simulated.append([home, [1, 0], away])
            elif outcome == 1:  # draw
                simulated.append([home, [0, 0], away])
            elif outcome == 2:  # away win
                simulated.append([home, [0, 1], away])
        return simulated


    def get_best_possible_position(target_team, current_matches, games_remaining):
        # Step 1: Generate current table
        initial_table = create_league_table(current_matches)
        standings = [team for team, _ in initial_table]
        if target_team not in standings:
            return None
        irrelevants = irrelevant_teams(initial_table, target_team, games_remaining)
        teams_above, teams_below = games_in_hand_below(initial_table, target_team)
        for a in teams_above:
            if a in irrelevants:
                teams_above.remove(a)
        for b in teams_below:
            if b in irrelevants:
                teams_below.remove(b)
        # Step 2: Apply "favorable" results to help target team
        adjusted_matches = copy.deepcopy(current_matches)
        reduced_games_remaining = []

        for home, away in games_remaining:
            home_above = home in teams_above
            away_above = away in teams_above
            home_below = home in teams_below
            away_below = away in teams_below
            home_target = home == target_team
            away_target = away == target_team
            home_irrelevant = home in irrelevants
            away_irrelevant = away in irrelevants

            # Favorable case: team above vs team below/target
            if (home_above and away_below) or (home_above and away_target) or (home_above and away_irrelevant):
                adjusted_matches.append([home, [0, 9], away])  # home loses
            elif (away_above and home_below) or (away_above and home_target) or (away_above and home_irrelevant):
                adjusted_matches.append([home, [9, 0], away])  # away loses
            elif (home_below and away_target) or (home_irrelevant and away_target):
                adjusted_matches.append([home, [0, 9], away])
            elif (away_below and home_target) or (away_irrelevant and home_target):
                adjusted_matches.append([home, [9, 0], away])
            elif home_above and away_above:
                reduced_games_remaining.append((home, away))  # leave this match to simulate
            else:
                adjusted_matches.append([home, [0, 0], away])  # draw
            # else: match doesn't involve teams above, doesn't affect best case, skip it
        # Step 3: Simulate remaining games between teams above
        all_outcomes = itertools.product([0, 1, 2], repeat=len(reduced_games_remaining))
        best_position = len(standings)

        for outcome in all_outcomes:
            future_matches = simulate_match_outcomes(reduced_games_remaining, outcome)
            full_matches = copy.deepcopy(adjusted_matches) + future_matches
            final_table = create_league_table(full_matches)
            for idx, (team, _) in enumerate(final_table, 1):
                if team == target_team:
                    best_position = min(best_position, idx)
                    break

        return best_position


    def get_worst_possible_position(target_team, current_matches, games_remaining):
        # Step 1: Generate current table
        initial_table = create_league_table(current_matches)
        standings = [team for team, _ in initial_table]
        if target_team not in standings:
            return None

        target_index = standings.index(target_team)
        teams_above = standings[:target_index]
        teams_below = standings[target_index + 1:]
        irrelevants = irrelevant_teams(initial_table, target_team, games_remaining)
        for a in teams_above:
            if a in irrelevants:
                teams_above.remove(a)
        for b in teams_below:
            if b in irrelevants:
                teams_below.remove(b)
        # Step 2: Apply "favorable" results to help target team
        adjusted_matches = copy.deepcopy(current_matches)
        reduced_games_remaining = []

        for home, away in games_remaining:
            home_above = home in teams_above
            away_above = away in teams_above
            home_below = home in teams_below
            away_below = away in teams_below
            home_target = home == target_team
            away_target = away == target_team
            home_irrelevant = home in irrelevants
            away_irrelevant = away in irrelevants

            # Favorable case: team above vs team below/target
            if (home_above and away_below) or (home_target and away_below) or (home_irrelevant and away_below):
                adjusted_matches.append([home, [0, 9], away])  # home loses
            elif (away_above and home_below) or (away_target and home_below) or (away_irrelevant and home_below):
                adjusted_matches.append([home, [9, 0], away])  # away loses
            elif (home_above and away_target) or (home_irrelevant and away_target):
                adjusted_matches.append([home, [9, 0], away])
            elif (away_above and home_target) or (away_irrelevant and home_target):
                adjusted_matches.append([home, [0, 9], away])
            elif home_below and away_below:
                reduced_games_remaining.append((home, away))  # leave this match to simulate
            else:
                adjusted_matches.append([home, [0, 0], away])
            # else: match doesn't involve teams above, doesn't affect best case, skip it
        # Step 3: Simulate remaining games between teams above
        all_outcomes = itertools.product([0, 1, 2], repeat=len(reduced_games_remaining))

        worst_position = 1

        for outcome in all_outcomes:
            future_matches = simulate_match_outcomes(reduced_games_remaining, outcome)
            full_matches = copy.deepcopy(adjusted_matches) + future_matches
            final_table = create_league_table(full_matches)
            for idx, (team, _) in enumerate(final_table, 1):
                if team == target_team:
                    worst_position = max(worst_position, idx)
                    break

        return worst_position


    def get_possible_positions(target_team, current_matches, games_remaining):
        best = get_best_possible_position(target_team, current_matches, games_remaining)
        worst = get_worst_possible_position(target_team, current_matches, games_remaining)
        return best, worst


    def create_league_table_and_print(matches, remaining):
        # Initialize a dictionary to store team statistics
        league_table = {}
        teams = []
        for match in matches:
            home_team, home_score, away_score, away_team = match[0], match[1][0], match[1][1], match[2]

            # Initialize teams
            for team in [home_team, away_team]:
                if team not in league_table:
                    league_table[team] = {'points': 0, 'goal_difference': 0, 'goals_scored': 0, 'games_played': 0,
                                          'best_possible_position': 0, 'worst_possible_position': 0}
                    teams.append(team)

            # Update stats
            league_table[home_team]['games_played'] += 1
            league_table[away_team]['games_played'] += 1
            league_table[home_team]['goals_scored'] += home_score
            league_table[away_team]['goals_scored'] += away_score
            league_table[home_team]['goal_difference'] += (home_score - away_score)
            league_table[away_team]['goal_difference'] += (away_score - home_score)

            # Update points
            if home_score > away_score:
                league_table[home_team]['points'] += 3
            elif home_score < away_score:
                league_table[away_team]['points'] += 3
            else:
                league_table[home_team]['points'] += 1
                league_table[away_team]['points'] += 1
        for team in teams:
            best, worst = get_possible_positions(team, matches, remaining)
            league_table[team]['best_possible_position'] = best
            league_table[team]['worst_possible_position'] = worst
        # Sort by points, goal difference, then goals scored
        sorted_teams = sorted(league_table.items(),
                              key=lambda x: (x[1]['points'], x[1]['goal_difference'], x[1]['goals_scored']),
                              reverse=True)
        # Print table
        print(f"{'Pos':<3} {'Team':<22} {'Points':<6} {'GD':<4} {'GS':<4} {'GP':<4} {'Possible Finishes':<17}")
        for team, stats in sorted_teams:
            if stats['best_possible_position'] != stats['worst_possible_position']:
                print(
                    f"{sorted_teams.index((team, stats)) + 1:<2}  {team:<22} {stats['points']:<6} {stats['goal_difference']:<4} {stats['goals_scored']:<4} {stats['games_played']:<4} {f"{stats['best_possible_position']}-{stats['worst_possible_position']}":<17}")
            else:
                print(
                    f"{sorted_teams.index((team, stats)) + 1:<2}  {team:<22} {stats['points']:<6} {stats['goal_difference']:<4} {stats['goals_scored']:<4} {stats['games_played']:<4} {f"{stats['best_possible_position']}":<17}")


    matches = [['Manchester United', [1, 0], 'Fulham'], ['Ipswich Town', [0, 2], 'Liverpool'],
               ['Arsenal', [2, 0], 'Wolverhampton'], ['Everton', [0, 3], 'Brighton & Hove Albion'],
               ['Newcastle United', [1, 0], 'Southampton'], ['Nottingham Forest', [1, 1], 'Bournemouth'],
               ['West Ham United', [1, 2], 'Aston Villa'], ['Brentford', [2, 1], 'Crystal Palace'],
               ['Chelsea', [0, 2], 'Manchester City'], ['Leicester City', [1, 1], 'Tottenham Hotspur'],
               ['Brighton & Hove Albion', [2, 1], 'Manchester United'], ['Crystal Palace', [0, 2], 'West Ham United'],
               ['Fulham', [2, 1], 'Leicester City'], ['Manchester City', [4, 1], 'Ipswich Town'],
               ['Southampton', [0, 1], 'Nottingham Forest'], ['Tottenham Hotspur', [4, 0], 'Everton'],
               ['Aston Villa', [0, 2], 'Arsenal'], ['Bournemouth', [1, 1], 'Newcastle United'],
               ['Wolverhampton', [2, 6], 'Chelsea'], ['Liverpool', [2, 0], 'Brentford'],
               ['Arsenal', [1, 1], 'Brighton & Hove Albion'], ['Brentford', [3, 1], 'Southampton'],
               ['Everton', [2, 3], 'Bournemouth'], ['Ipswich Town', [1, 1], 'Fulham'],
               ['Leicester City', [1, 2], 'Aston Villa'], ['Nottingham Forest', [1, 1], 'Wolverhampton'],
               ['West Ham United', [1, 3], 'Manchester City'], ['Chelsea', [1, 1], 'Crystal Palace'],
               ['Newcastle United', [2, 1], 'Tottenham Hotspur'], ['Manchester United', [0, 3], 'Liverpool'],
               ['Southampton', [0, 3], 'Manchester United'], ['Brighton & Hove Albion', [0, 0], 'Ipswich Town'],
               ['Crystal Palace', [2, 2], 'Leicester City'], ['Fulham', [1, 1], 'West Ham United'],
               ['Liverpool', [0, 1], 'Nottingham Forest'], ['Manchester City', [2, 1], 'Brentford'],
               ['Aston Villa', [3, 2], 'Everton'], ['Bournemouth', [0, 1], 'Chelsea'],
               ['Tottenham Hotspur', [0, 1], 'Arsenal'], ['Wolverhampton', [1, 2], 'Newcastle United'],
               ['West Ham United', [0, 3], 'Chelsea'], ['Aston Villa', [3, 1], 'Wolverhampton'],
               ['Fulham', [3, 1], 'Newcastle United'], ['Leicester City', [1, 1], 'Everton'],
               ['Liverpool', [3, 0], 'Bournemouth'], ['Southampton', [1, 1], 'Ipswich Town'],
               ['Tottenham Hotspur', [3, 1], 'Brentford'], ['Crystal Palace', [0, 0], 'Manchester United'],
               ['Brighton & Hove Albion', [2, 2], 'Nottingham Forest'], ['Manchester City', [2, 2], 'Arsenal'],
               ['Newcastle United', [1, 1], 'Manchester City'], ['Arsenal', [4, 2], 'Leicester City'],
               ['Brentford', [1, 1], 'West Ham United'], ['Chelsea', [4, 2], 'Brighton & Hove Albion'],
               ['Everton', [2, 1], 'Crystal Palace'], ['Nottingham Forest', [0, 1], 'Fulham'],
               ['Wolverhampton', [1, 2], 'Liverpool'], ['Ipswich Town', [2, 2], 'Aston Villa'],
               ['Manchester United', [0, 3], 'Tottenham Hotspur'], ['Bournemouth', [3, 1], 'Southampton'],
               ['Crystal Palace', [0, 1], 'Liverpool'], ['Arsenal', [3, 1], 'Southampton'],
               ['Brentford', [5, 3], 'Wolverhampton'], ['Leicester City', [1, 0], 'Bournemouth'],
               ['Manchester City', [3, 2], 'Fulham'], ['West Ham United', [4, 1], 'Ipswich Town'],
               ['Everton', [0, 0], 'Newcastle United'], ['Aston Villa', [0, 0], 'Manchester United'],
               ['Chelsea', [1, 1], 'Nottingham Forest'], ['Brighton & Hove Albion', [3, 2], 'Tottenham Hotspur'],
               ['Tottenham Hotspur', [4, 1], 'West Ham United'], ['Fulham', [1, 3], 'Aston Villa'],
               ['Manchester United', [2, 1], 'Brentford'], ['Newcastle United', [0, 1], 'Brighton & Hove Albion'],
               ['Southampton', [2, 3], 'Leicester City'], ['Ipswich Town', [0, 2], 'Everton'],
               ['Bournemouth', [2, 0], 'Arsenal'], ['Wolverhampton', [1, 2], 'Manchester City'],
               ['Liverpool', [2, 1], 'Chelsea'], ['Nottingham Forest', [1, 0], 'Crystal Palace'],
               ['Leicester City', [1, 3], 'Nottingham Forest'], ['Aston Villa', [1, 1], 'Bournemouth'],
               ['Brentford', [4, 3], 'Ipswich Town'], ['Brighton & Hove Albion', [2, 2], 'Wolverhampton'],
               ['Manchester City', [1, 0], 'Southampton'], ['Everton', [1, 1], 'Fulham'],
               ['Chelsea', [2, 1], 'Newcastle United'], ['Crystal Palace', [1, 0], 'Tottenham Hotspur'],
               ['West Ham United', [2, 1], 'Manchester United'], ['Arsenal', [2, 2], 'Liverpool'],
               ['Newcastle United', [1, 0], 'Arsenal'], ['Bournemouth', [2, 1], 'Manchester City'],
               ['Ipswich Town', [1, 1], 'Leicester City'], ['Liverpool', [2, 1], 'Brighton & Hove Albion'],
               ['Nottingham Forest', [3, 0], 'West Ham United'], ['Southampton', [1, 0], 'Everton'],
               ['Wolverhampton', [2, 2], 'Crystal Palace'], ['Tottenham Hotspur', [4, 1], 'Aston Villa'],
               ['Manchester United', [1, 1], 'Chelsea'], ['Fulham', [2, 1], 'Brentford'],
               ['Brentford', [3, 2], 'Bournemouth'], ['Crystal Palace', [0, 2], 'Fulham'],
               ['West Ham United', [0, 0], 'Everton'], ['Wolverhampton', [2, 0], 'Southampton'],
               ['Brighton & Hove Albion', [2, 1], 'Manchester City'], ['Liverpool', [2, 0], 'Aston Villa'],
               ['Manchester United', [3, 0], 'Leicester City'], ['Nottingham Forest', [1, 3], 'Newcastle United'],
               ['Tottenham Hotspur', [1, 2], 'Ipswich Town'], ['Chelsea', [1, 1], 'Arsenal'],
               ['Leicester City', [1, 2], 'Chelsea'], ['Arsenal', [3, 0], 'Nottingham Forest'],
               ['Aston Villa', [2, 2], 'Crystal Palace'], ['Bournemouth', [1, 2], 'Brighton & Hove Albion'],
               ['Everton', [0, 0], 'Brentford'], ['Fulham', [1, 4], 'Wolverhampton'],
               ['Manchester City', [0, 4], 'Tottenham Hotspur'], ['Southampton', [2, 3], 'Liverpool'],
               ['Ipswich Town', [1, 1], 'Manchester United'], ['Newcastle United', [0, 2], 'West Ham United'],
               ['Brighton & Hove Albion', [1, 1], 'Southampton'], ['Brentford', [4, 1], 'Leicester City'],
               ['Crystal Palace', [1, 1], 'Newcastle United'], ['Nottingham Forest', [1, 0], 'Ipswich Town'],
               ['Wolverhampton', [2, 4], 'Bournemouth'], ['West Ham United', [2, 5], 'Arsenal'],
               ['Chelsea', [3, 0], 'Aston Villa'], ['Manchester United', [4, 0], 'Everton'],
               ['Tottenham Hotspur', [1, 1], 'Fulham'], ['Liverpool', [2, 0], 'Manchester City'],
               ['Ipswich Town', [0, 1], 'Crystal Palace'], ['Leicester City', [3, 1], 'West Ham United'],
               ['Everton', [4, 0], 'Wolverhampton'], ['Manchester City', [3, 0], 'Nottingham Forest'],
               ['Newcastle United', [3, 3], 'Liverpool'], ['Southampton', [1, 5], 'Chelsea'],
               ['Arsenal', [2, 0], 'Manchester United'], ['Aston Villa', [3, 1], 'Brentford'],
               ['Fulham', [3, 1], 'Brighton & Hove Albion'], ['Bournemouth', [1, 0], 'Tottenham Hotspur'],
               ['Aston Villa', [1, 0], 'Southampton'], ['Brentford', [4, 2], 'Newcastle United'],
               ['Crystal Palace', [2, 2], 'Manchester City'], ['Manchester United', [2, 3], 'Nottingham Forest'],
               ['Fulham', [1, 1], 'Arsenal'], ['Ipswich Town', [1, 2], 'Bournemouth'],
               ['Leicester City', [2, 2], 'Brighton & Hove Albion'], ['Tottenham Hotspur', [3, 4], 'Chelsea'],
               ['West Ham United', [2, 1], 'Wolverhampton'], ['Everton', [2, 2], 'Liverpool'],
               ['Arsenal', [0, 0], 'Everton'], ['Liverpool', [2, 2], 'Fulham'],
               ['Newcastle United', [4, 0], 'Leicester City'], ['Wolverhampton', [1, 2], 'Ipswich Town'],
               ['Nottingham Forest', [2, 1], 'Aston Villa'], ['Brighton & Hove Albion', [1, 3], 'Crystal Palace'],
               ['Manchester City', [1, 2], 'Manchester United'], ['Chelsea', [2, 1], 'Brentford'],
               ['Southampton', [0, 5], 'Tottenham Hotspur'], ['Bournemouth', [1, 1], 'West Ham United'],
               ['Aston Villa', [2, 1], 'Manchester City'], ['Brentford', [0, 2], 'Nottingham Forest'],
               ['Ipswich Town', [0, 4], 'Newcastle United'], ['West Ham United', [1, 1], 'Brighton & Hove Albion'],
               ['Crystal Palace', [1, 5], 'Arsenal'], ['Everton', [0, 0], 'Chelsea'], ['Fulham', [0, 0], 'Southampton'],
               ['Leicester City', [0, 3], 'Wolverhampton'], ['Manchester United', [0, 3], 'Bournemouth'],
               ['Tottenham Hotspur', [3, 6], 'Liverpool'], ['Manchester City', [1, 1], 'Everton'],
               ['Bournemouth', [0, 0], 'Crystal Palace'], ['Chelsea', [1, 2], 'Fulham'],
               ['Newcastle United', [3, 0], 'Aston Villa'], ['Nottingham Forest', [1, 0], 'Tottenham Hotspur'],
               ['Southampton', [0, 1], 'West Ham United'], ['Wolverhampton', [2, 0], 'Manchester United'],
               ['Liverpool', [3, 1], 'Leicester City'], ['Brighton & Hove Albion', [0, 0], 'Brentford'],
               ['Arsenal', [1, 0], 'Ipswich Town'], ['Leicester City', [0, 2], 'Manchester City'],
               ['Crystal Palace', [2, 1], 'Southampton'], ['Everton', [0, 2], 'Nottingham Forest'],
               ['Fulham', [2, 2], 'Bournemouth'], ['Tottenham Hotspur', [2, 2], 'Wolverhampton'],
               ['West Ham United', [0, 5], 'Liverpool'], ['Aston Villa', [2, 2], 'Brighton & Hove Albion'],
               ['Ipswich Town', [2, 0], 'Chelsea'], ['Manchester United', [0, 2], 'Newcastle United'],
               ['Brentford', [1, 3], 'Arsenal'], ['Tottenham Hotspur', [1, 2], 'Newcastle United'],
               ['Aston Villa', [2, 1], 'Leicester City'], ['Bournemouth', [1, 0], 'Everton'],
               ['Crystal Palace', [1, 1], 'Chelsea'], ['Manchester City', [4, 1], 'West Ham United'],
               ['Southampton', [0, 5], 'Brentford'], ['Brighton & Hove Albion', [1, 1], 'Arsenal'],
               ['Fulham', [2, 2], 'Ipswich Town'], ['Liverpool', [2, 2], 'Manchester United'],
               ['Wolverhampton', [0, 3], 'Nottingham Forest'], ['Brentford', [2, 2], 'Manchester City'],
               ['Chelsea', [2, 2], 'Bournemouth'], ['West Ham United', [3, 2], 'Fulham'],
               ['Nottingham Forest', [1, 1], 'Liverpool'], ['Everton', [0, 1], 'Aston Villa'],
               ['Leicester City', [0, 2], 'Crystal Palace'], ['Newcastle United', [3, 0], 'Wolverhampton'],
               ['Arsenal', [2, 1], 'Tottenham Hotspur'], ['Ipswich Town', [0, 2], 'Brighton & Hove Albion'],
               ['Manchester United', [3, 1], 'Southampton'], ['Newcastle United', [1, 4], 'Bournemouth'],
               ['Brentford', [0, 2], 'Liverpool'], ['Leicester City', [0, 2], 'Fulham'],
               ['West Ham United', [0, 2], 'Crystal Palace'], ['Arsenal', [2, 2], 'Aston Villa'],
               ['Everton', [3, 2], 'Tottenham Hotspur'], ['Manchester United', [1, 3], 'Brighton & Hove Albion'],
               ['Nottingham Forest', [3, 2], 'Southampton'], ['Ipswich Town', [0, 6], 'Manchester City'],
               ['Chelsea', [3, 1], 'Wolverhampton'], ['Bournemouth', [5, 0], 'Nottingham Forest'],
               ['Brighton & Hove Albion', [0, 1], 'Everton'], ['Liverpool', [4, 1], 'Ipswich Town'],
               ['Southampton', [1, 3], 'Newcastle United'], ['Wolverhampton', [0, 1], 'Arsenal'],
               ['Manchester City', [3, 1], 'Chelsea'], ['Crystal Palace', [1, 2], 'Brentford'],
               ['Tottenham Hotspur', [1, 2], 'Leicester City'], ['Aston Villa', [1, 1], 'West Ham United'],
               ['Fulham', [0, 1], 'Manchester United'], ['Nottingham Forest', [7, 0], 'Brighton & Hove Albion'],
               ['Bournemouth', [0, 2], 'Liverpool'], ['Everton', [4, 0], 'Leicester City'],
               ['Ipswich Town', [1, 2], 'Southampton'], ['Newcastle United', [1, 2], 'Fulham'],
               ['Wolverhampton', [2, 0], 'Aston Villa'], ['Brentford', [0, 2], 'Tottenham Hotspur'],
               ['Manchester United', [0, 2], 'Crystal Palace'], ['Arsenal', [5, 1], 'Manchester City'],
               ['Chelsea', [2, 1], 'West Ham United'], ['Brighton & Hove Albion', [3, 0], 'Chelsea'],
               ['Leicester City', [0, 2], 'Arsenal'], ['Aston Villa', [1, 1], 'Ipswich Town'],
               ['Fulham', [2, 1], 'Nottingham Forest'], ['Manchester City', [4, 0], 'Newcastle United'],
               ['Southampton', [1, 3], 'Bournemouth'], ['West Ham United', [0, 1], 'Brentford'],
               ['Crystal Palace', [1, 2], 'Everton'], ['Liverpool', [2, 1], 'Wolverhampton'],
               ['Tottenham Hotspur', [1, 0], 'Manchester United'], ['Leicester City', [0, 4], 'Brentford'],
               ['Everton', [2, 2], 'Manchester United'], ['Arsenal', [0, 1], 'West Ham United'],
               ['Bournemouth', [0, 1], 'Wolverhampton'], ['Fulham', [0, 2], 'Crystal Palace'],
               ['Ipswich Town', [1, 4], 'Tottenham Hotspur'], ['Southampton', [0, 4], 'Brighton & Hove Albion'],
               ['Aston Villa', [2, 1], 'Chelsea'], ['Newcastle United', [4, 3], 'Nottingham Forest'],
               ['Manchester City', [0, 2], 'Liverpool'], ['Brighton & Hove Albion', [2, 1], 'Bournemouth'],
               ['Crystal Palace', [4, 1], 'Aston Villa'], ['Wolverhampton', [1, 2], 'Fulham'],
               ['Chelsea', [4, 0], 'Southampton'], ['Brentford', [1, 1], 'Everton'],
               ['Manchester United', [3, 2], 'Ipswich Town'], ['Nottingham Forest', [0, 0], 'Arsenal'],
               ['Tottenham Hotspur', [0, 1], 'Manchester City'], ['Liverpool', [2, 0], 'Newcastle United'],
               ['West Ham United', [2, 0], 'Leicester City'], ['Nottingham Forest', [1, 0], 'Manchester City'],
               ['Brighton & Hove Albion', [2, 1], 'Fulham'], ['Crystal Palace', [1, 0], 'Ipswich Town'],
               ['Liverpool', [3, 1], 'Southampton'], ['Brentford', [0, 1], 'Aston Villa'],
               ['Wolverhampton', [1, 1], 'Everton'], ['Chelsea', [1, 0], 'Leicester City'],
               ['Tottenham Hotspur', [2, 2], 'Bournemouth'], ['Manchester United', [1, 1], 'Arsenal'],
               ['West Ham United', [0, 1], 'Newcastle United'], ['Aston Villa', [2, 2], 'Liverpool'],
               ['Everton', [1, 1], 'West Ham United'], ['Ipswich Town', [2, 4], 'Nottingham Forest'],
               ['Manchester City', [2, 2], 'Brighton & Hove Albion'], ['Southampton', [1, 2], 'Wolverhampton'],
               ['Bournemouth', [1, 2], 'Brentford'], ['Arsenal', [1, 0], 'Chelsea'],
               ['Fulham', [2, 0], 'Tottenham Hotspur'], ['Leicester City', [0, 3], 'Manchester United'],
               ['Newcastle United', [5, 0], 'Crystal Palace'], ['Arsenal', [2, 1], 'Fulham'],
               ['Wolverhampton', [1, 0], 'West Ham United'], ['Nottingham Forest', [1, 0], 'Manchester United'],
               ['Bournemouth', [1, 2], 'Ipswich Town'], ['Brighton & Hove Albion', [0, 3], 'Aston Villa'],
               ['Manchester City', [2, 0], 'Leicester City'], ['Newcastle United', [2, 1], 'Brentford'],
               ['Southampton', [1, 1], 'Crystal Palace'], ['Liverpool', [1, 0], 'Everton'],
               ['Chelsea', [1, 0], 'Tottenham Hotspur'], ['Everton', [1, 1], 'Arsenal'],
               ['Crystal Palace', [2, 1], 'Brighton & Hove Albion'], ['Ipswich Town', [1, 2], 'Wolverhampton'],
               ['West Ham United', [2, 2], 'Bournemouth'], ['Aston Villa', [2, 1], 'Nottingham Forest'],
               ['Brentford', [0, 0], 'Chelsea'], ['Fulham', [3, 2], 'Liverpool'],
               ['Tottenham Hotspur', [3, 1], 'Southampton'], ['Manchester United', [0, 0], 'Manchester City'],
               ['Leicester City', [0, 3], 'Newcastle United'], ['Manchester City', [5, 2], 'Crystal Palace'],
               ['Brighton & Hove Albion', [2, 2], 'Leicester City'], ['Nottingham Forest', [0, 1], 'Everton'],
               ['Southampton', [0, 3], 'Aston Villa'], ['Arsenal', [1, 1], 'Brentford'],
               ['Chelsea', [2, 2], 'Ipswich Town'], ['Liverpool', [2, 1], 'West Ham United'],
               ['Wolverhampton', [4, 2], 'Tottenham Hotspur'], ['Newcastle United', [4, 1], 'Manchester United'],
               ['Bournemouth', [1, 0], 'Fulham'], ['Brentford', [4, 2], 'Brighton & Hove Albion'],
               ['Crystal Palace', [0, 0], 'Bournemouth'], ['Everton', [0, 2], 'Manchester City'],
               ['West Ham United', [1, 1], 'Southampton'], ['Aston Villa', [4, 1], 'Newcastle United'],
               ['Fulham', [1, 2], 'Chelsea'], ['Ipswich Town', [0, 4], 'Arsenal'],
               ['Manchester United', [0, 1], 'Wolverhampton'], ['Leicester City', [0, 1], 'Liverpool'],
               ['Tottenham Hotspur', [1, 2], 'Nottingham Forest'], ['Manchester City', [2, 1], 'Aston Villa'],
               ['Arsenal', [2, 2], 'Crystal Palace'], ['Chelsea', [1, 0], 'Everton'],
               ['Brighton & Hove Albion', [3, 2], 'West Ham United'], ['Newcastle United', [3, 0], 'Ipswich Town'],
               ['Southampton', [1, 2], 'Fulham'], ['Wolverhampton', [3, 0], 'Leicester City']]

    games_remaining = [['Bournemouth', 'Manchester United'], ['Liverpool', 'Tottenham Hotspur'],
                       ['Nottingham Forest', 'Brentford'], ['Manchester City', 'Wolverhampton'],
                       ['Aston Villa', 'Fulham'],
                       ['Everton', 'Ipswich Town'], ['Leicester City', 'Southampton'], ['Arsenal', 'Bournemouth'],
                       ['Brentford', 'Manchester United'], ['Brighton & Hove Albion', 'Newcastle United'],
                       ['West Ham United', 'Tottenham Hotspur'], ['Chelsea', 'Liverpool'],
                       ['Crystal Palace', 'Nottingham Forest'], ['Fulham', 'Everton'], ['Ipswich Town', 'Brentford'],
                       ['Southampton', 'Manchester City'], ['Wolverhampton', 'Brighton & Hove Albion'],
                       ['Bournemouth', 'Aston Villa'], ['Newcastle United', 'Chelsea'],
                       ['Manchester United', 'West Ham United'], ['Nottingham Forest', 'Leicester City'],
                       ['Tottenham Hotspur', 'Crystal Palace'], ['Liverpool', 'Arsenal'],
                       ['Chelsea', 'Manchester United'],
                       ['Everton', 'Southampton'], ['Aston Villa', 'Tottenham Hotspur'],
                       ['West Ham United', 'Nottingham Forest'], ['Brentford', 'Fulham'],
                       ['Crystal Palace', 'Wolverhampton'], ['Leicester City', 'Ipswich Town'],
                       ['Arsenal', 'Newcastle United'], ['Manchester City', 'Bournemouth'],
                       ['Brighton & Hove Albion', 'Liverpool'], ['Bournemouth', 'Leicester City'],
                       ['Fulham', 'Manchester City'], ['Ipswich Town', 'West Ham United'],
                       ['Liverpool', 'Crystal Palace'],
                       ['Manchester United', 'Aston Villa'], ['Newcastle United', 'Everton'],
                       ['Nottingham Forest', 'Chelsea'], ['Southampton', 'Arsenal'],
                       ['Tottenham Hotspur', 'Brighton & Hove Albion'], ['Wolverhampton', 'Brentford']]

    create_league_table_and_print(matches, games_remaining)

else:
    print('Invalid choice')
