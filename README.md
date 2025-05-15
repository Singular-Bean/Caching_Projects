These projects were made in response to a problem whereby my sofascore requests were returning a 403 
error if I hit the API too many times in a day.

# Possible Finishes:

Relatively simple script to determine the possible finishing positions of every team in a league, 
given the league name. In the beginning, the program asks the user if they would like to use caching,
skip the caching and fetch from the website, or use a pre-prepared dataset from the premier league.
I added the last option because if the season is finished, it's just going to output the final 
league positions as the possible finishing positions, which is pointless. So this last option is for 
during the summer when there are no leagues playing. The program then outputs what the league table 
looks like currently, with a separate column showing the teams' finishing position ranges:

```
Pos Team                   Points GD   GS   GP   Possible Finishes
1   Liverpool              79     44   75   33   1-2              
2   Arsenal                67     34   63   34   1-7              
3   Newcastle United       62     21   65   34   2-10             
4   Manchester City        61     23   66   34   2-10             
5   Chelsea                60     19   59   34   2-11             
6   Nottingham Forest      60     14   53   33   2-11             
7   Aston Villa            57     5    54   34   2-12             
8   Fulham                 51     4    50   34   3-15             
9   Brighton & Hove Albion 51     1    56   34   3-15             
10  Bournemouth            49     12   52   33   3-16             
11  Brentford              46     6    56   33   4-17             
12  Crystal Palace         45     -4   43   34   7-17             
13  Wolverhampton          41     -10  51   34   8-17             
14  Everton                38     -7   34   34   10-17            
15  Manchester United      38     -8   38   33   8-17             
16  Tottenham Hotspur      37     10   61   33   8-17             
17  West Ham United        36     -19  39   34   11-17            
18  Ipswich Town           21     -41  33   34   18-20            
19  Leicester City         18     -49  27   34   18-20            
20  Southampton            11     -55  25   34   18-20            
```

(this is the data from the premier league on the 26th of April 2025)

Columns are: Current position, team name, points, goal difference, goals scored, games played, and 
the possible finishing positions.

The program works by finding teams which are currently below the selected team, teams which are 
currently above the selected team, and teams which are irrelevant to the selected team (teams which 
either can't overtake or be overtaken by the selected team). Then, to find the team's highest 
possible finishing position, it simulates the remaining games with teams above the selected team 
losing all their games, and teams below the selected team winning all their games. To make up for 
any differences in goal difference making an effect, the simulation makes winning teams win by the 
largest winning margin in premier league history (9–0). For matches between teams which are either 
both above or both below the selected team, it simulates every possible outcome and then finds 
the maximum finishing position. This whole process is then repeated to find the lowest possible
finishing position, but the other way round.

Finally, to get the final league table, this is done on all the teams in the league.

In the future I would like to change the part where if the season is not finished, the user has to 
manually input the number of rounds played. Automating this would mean not using the caching for 
this bit of code because the number of rounds played will change regularly.

# Similar Profiles:

Again, this is a very simple project which utilises sofascore's "attribute pentagons" to find 
players with similar profilesto a selected player.

The program first asks the user whether they would like to use caching. It then asks for the 
player who they would like to compare with other players. It then asks the user for a league to 
compare the players from, getting all the information of players from that league, including their 
attribute pentagon. The program converts each pentagon into five numerical values representing the
attributes: attacking, creativity, defending, tactical, and technical. To compare two players, the 
program first normalizes the example player's attributes so that their total matches that of the
target player. This is done by scaling each of the example player's attributes proportionally. 
Once normalized, the program calculates the squared difference between each corresponding attribute 
and sums them to produce a single "residual" score. The lower this residual, the more similar the 
example player is to the target. By doing it this way it finds the player whose pentagon is the 
most similar in shape without taking into account the size of the pentagon. The program then 
outputs the top 10 players with the most similar profiles to the selected player. This example is 
finding players from the premier league who are similar in profile to Lamine Yamal:

```
1st Closest Player: Noni Madueke, Residuals: 31.4
2nd Closest Player: Eberechi Eze, Residuals: 61.1
3rd Closest Player: Ross Barkley, Residuals: 74.5
4th Closest Player: Marcus Rashford, Residuals: 77.8
5th Closest Player: John McGinn, Residuals: 97.1
6th Closest Player: Callum Hudson-Odoi, Residuals: 102.9
7th Closest Player: Willian, Residuals: 110.0
8th Closest Player: Bukayo Saka, Residuals: 115.1
9th Closest Player: Cody Gakpo, Residuals: 119.0
10th Closest Player: Marco Asensio, Residuals: 119.9
```

Although the program is only using 5 numbers, I think this has worked quite well because it has 
mainly returned wingers, or other very technically minded players. This could potentially be used to 
find replacements for players who are aging or on their way out, with players from leagues which are 
maybe undervalued in the transfer market. Another way this could potentially be used is to see how 
rare aplayer's profile is. For example, if you run the program and all of the returned residuals are 
very high, it could mean that the player has a unique profile.

Below is a screenshot from sofascore's "compare attribute penetagons" feature, comparing Lamine
Yamal (green) with Noni Madueke (blue). I think that this shows that the pentagons have similar
shapes, even though the sizes are different because of the different skill levels of the players:

![img.png](img.png)