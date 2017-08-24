import re

import numpy as np
import pandas as pd
from pyquery import PyQuery as pq

import sportsref

__all__ = [
    'team_names',
    'team_ids',
    'list_teams',
    'Team',
]


@sportsref.decorators.memoized
def team_names(year):
    """Returns a mapping from team ID to full team name for a given season.
    Example of a full team name: "New England Patriots"

    :year: The year of the season in question (as an int).
    :returns: A dictionary with teamID keys and full team name values.
    """
    doc = pq(sportsref.utils.get_html(sportsref.nfl.BASE_URL + '/teams/'))
    active_table = doc('table#teams_active')
    active_df = sportsref.utils.parse_table(active_table)
    inactive_table = doc('table#teams_inactive')
    inactive_df = sportsref.utils.parse_table(inactive_table)
    df = pd.concat((active_df, inactive_df))
    df = df.loc[~df['has_class_partial_table']]
    ids = df.team_id.str[:3].values
    names = [tr('th a') for tr in active_table('tr').items()]
    names.extend(tr('th a') for tr in inactive_table('tr').items())
    names = filter(None, names)
    names = [lst[0].text_content() for lst in names]
    # combine IDs and team names into pandas series
    series = pd.Series(names, index=ids)
    # create a mask to filter to teams from the given year
    mask = ((df.year_min <= year) & (year <= df.year_max)).values
    # filter, convert to a dict, and return
    return series[mask].to_dict()


@sportsref.decorators.memoized
def team_ids(year):
    """Returns a mapping from team name to team ID for a given season. Inverse
    mapping of team_names. Example of a full team name: "New England Patriots"

    :year: The year of the season in question (as an int).
    :returns: A dictionary with full team name keys and teamID values.
    """
    names = team_names(year)
    return {v: k for k, v in names.iteritems()}


@sportsref.decorators.memoized
def list_teams(year):
    """Returns a list of team IDs for a given season.

    :year: The year of the season in question (as an int).
    :returns: A list of team IDs.
    """
    return team_names(year).keys()


@sportsref.decorators.memoized
class Team:

    def __init__(self, teamID):
        self.teamID = teamID

    def __eq__(self, other):
        return (self.teamID == other.teamID)

    def __hash__(self):
        return hash(self.teamID)

    def __repr__(self):
        return 'Team({})'.format(self.teamID)

    def __str__(self):
        return self.name()

    def __reduce__(self):
        return Team, (self.teamID,)

    @sportsref.decorators.memoized
    def team_year_url(self, yr_str):
        return (sportsref.nfl.BASE_URL +
                '/teams/{}/{}.htm'.format(self.teamID, yr_str))

    @sportsref.decorators.memoized
    def get_main_doc(self):
        relURL = '/teams/{}'.format(self.teamID)
        teamURL = sportsref.nfl.BASE_URL + relURL
        mainDoc = pq(sportsref.utils.get_html(teamURL))
        return mainDoc

    @sportsref.decorators.memoized
    def get_year_doc(self, yr_str):
        return pq(sportsref.utils.get_html(self.team_year_url(yr_str)))

    @sportsref.decorators.memoized
    def name(self):
        """Returns the real name of the franchise given the team ID.

        Examples:
        'nwe' -> 'New England Patriots'
        'sea' -> 'Seattle Seahawks'

        :returns: A string corresponding to the team's full name.
        """
        doc = self.get_main_doc()
        headerwords = doc('div#meta h1')[0].text_content().split()
        lastIdx = headerwords.index('Franchise')
        teamwords = headerwords[:lastIdx]
        return ' '.join(teamwords)

    @sportsref.decorators.memoized
    def injury_status(self, year):
        """Returns the player's injury status each week of the given year.

        :year: The year for which we want the injury report;
        :returns: A DataFrame containing player's injury status for that year.
        """
        doc = self.get_year_doc(str(year) + '_injuries')
        table = doc('table#team_injuries')
        columns = [c.attrib['data-stat']
                   for c in table('thead tr:not([class]) th[data-stat]')]

        # get data
        rows = list(table('tbody tr')
                    .not_('.thead, .stat_total, .stat_average')
                    .items())
        data = [
            [str(int(td.has_class('dnp'))) +
             str(sportsref.utils.flatten_links(td)) for td in row.items('th,td')
            ]
            for row in rows
        ]

        # make DataFrame and a few small fixes
        df = pd.DataFrame(data, columns=columns, dtype='float')
        if not df.empty:
            df.rename(columns={'player': 'playerID'}, inplace=True)
            df['playerID'] = df.playerID.str[1:]
            df = pd.melt(df, id_vars=['playerID'])
            df['season'] = year
            df['week'] = pd.to_numeric(df.variable.str[5:])
            df['team'] = self.teamID
            statusMap = {
                'P':'Probable',
                'Q':'Questionable',
                'D':'Doubfult',
                'O':'Out',
                'PUP':'Physically Unable to Perform',
                'IR':'Injured Reserve',
                'None':'None'
            }
            df['status'] = df.value.str[1:].map(statusMap)
            didNotPlayMap = {
                '1':True,
                '0':False
            }
            df['didNotPlay'] = df.value.str[0].map(didNotPlayMap)
            #df['didNotPlay'] = df['didNotPlay'].astype(bool)
            #df.drop(['variable','value'], axis=1, inplace=True)
            df['season'] = df['season'].astype(int)
            df['week'] = df['week'].astype(int)
            # drop rows if player is None
            df = df[df['playerID'] != 'None'].reset_index(drop=True)
            df['player_id'] = df['playerID']
        # set col order
        cols = ['season', 'week', 'team', 'player_id', 'status', 'didNotPlay']
        for col in cols:
            if col not in df: df[col] = np.nan
        df = df[cols]
        return df

    @sportsref.decorators.memoized
    def roster(self, year):
        """Returns the roster table for the given year.

        :year: The year for which we want the roster;
        :returns: A DataFrame containing roster information for that year.
        """
        doc = self.get_year_doc('{}_roster'.format(year))
        table = doc('table#games_played_team')
        df = sportsref.utils.parse_table(table)
        if not df.empty:
            df['season'] = int(year)
            df['team'] = self.teamID
            playerNames = [c.text for c in table('tbody tr td a[href]') 
                           if c.attrib['href'][1:8]=='players']
            if len(df) == len(playerNames):
                df['playerName'] = playerNames
            df.rename(columns={'pos':'position',
                               'uniform_number':'uniformNumber',
                               'g':'gamesPlayed',
                               'gs':'gamesStarted',
                               'birth_date_mod':'birthDate',
                               'av':'pfrApproxValue',
                               'college_id':'college',
                               'draft_info':'draftInfo'
                              }, inplace=True)
        cols = ['season', 'team', 'player_id',
                'playerName', 'position', 'uniformNumber', 'gamesPlayed', 'gamesStarted',
                'pfrApproxValue', 'experience', 'age', 'birthDate', 'height', 'weight',
                'college', 'draftInfo', 'salary',]
        for col in cols:
            if col not in df: df[col] = np.nan
        df = df[cols]
        return df

    @sportsref.decorators.memoized
    def boxscores(self, year):
        """Gets list of BoxScore objects corresponding to the box scores from
        that year.

        :year: The year for which we want the boxscores; defaults to current
        year.
        :returns: np.array of strings representing boxscore IDs.
        """
        doc = self.get_year_doc(year)
        table = doc('table#games')
        df = sportsref.utils.parse_table(table)
        if df.empty:
            return np.array([])
        return df.boxscore_id.values

    # TODO: add functions for OC, DC, PF, PA, W-L, etc.
    # TODO: Also give a function at BoxScore.homeCoach and BoxScore.awayCoach
    # TODO: BoxScore needs a gameNum function to do this?

    @sportsref.decorators.memoized
    def head_coaches_by_game(self, year):
        """Returns head coach data by game.

        :year: An int representing the season in question.
        :returns: An array with an entry per game of the season that the team
        played (including playoffs). Each entry is the head coach's ID for that
        game in the season.
        """
        doc = self.get_year_doc(year)
        coaches = (doc('div#meta p')
                   .filter(lambda i, e: 'Coach:' in e.text_content()))
        coachStr = sportsref.utils.flatten_links(coaches)
        regex = r'(\S+?) \((\d+)-(\d+)-(\d+)\)'
        coachAndTenure = []
        while coachStr:
            m = re.search(regex, coachStr)
            coachID, wins, losses, ties = m.groups()
            nextIndex = m.end(4) + 1
            coachStr = coachStr[nextIndex:]
            tenure = int(wins) + int(losses) + int(ties)
            coachAndTenure.append((coachID, tenure))

        coachIDs = [[cID for _ in xrange(games)]
                    for cID, games in coachAndTenure]
        coachIDs = [cID for sublist in coachIDs for cID in sublist]
        return np.array(coachIDs[::-1])

    @sportsref.decorators.memoized
    def srs(self, year):
        """Returns the SRS (Simple Rating System) for a team in a year.

        :year: The year for the season in question.
        :returns: A float of SRS.
        """
        doc = self.get_year_doc(year)
        srsText = (doc('div#meta p')
                   .filter(lambda i, e: 'SRS' in e.text_content())
                   .text())
        m = re.match(r'SRS\s*?:\s*?(\S+)', srsText)
        if m:
            return float(m.group(1))
        else:
            return np.nan

    @sportsref.decorators.memoized
    def sos(self, year):
        """Returns the SOS (Strength of Schedule) for a team in a year, based
        on SRS.

        :year: The year for the season in question.
        :returns: A float of SOS.
        """
        doc = self.get_year_doc(year)
        sosText = (doc('div#meta p')
                   .filter(lambda i, e: 'SOS' in e.text_content())
                   .text())
        m = re.search(r'SOS\s*?:\s*?(\S+)', sosText)
        if m:
            return float(m.group(1))
        else:
            return np.nan

    @sportsref.decorators.memoized
    def stadium(self, year):
        """Returns the ID for the stadium in which the team played in a given
        year.

        :year: The year in question.
        :returns: A string representing the stadium ID.
        """
        doc = self.get_year_doc(year)
        anchor = (doc('div#meta p')
                  .filter(lambda i, e: 'Stadium' in e.text_content())
                  )('a')
        return sportsref.utils.rel_url_to_id(anchor.attr['href'])

    @sportsref.decorators.memoized
    def team_stats(self, year):
        """Returns a Series (dict-like) of team stats from the team-season
        page.

        :year: Int representing the season.
        :returns: A Series of team stats.
        """
        doc = self.get_year_doc(year)
        table = doc('table#team_stats')
        df = sportsref.utils.parse_table(table)
        return df.ix[df.player_id == 'Team Stats'].iloc[0]

    @sportsref.decorators.memoized
    def opp_stats(self, year):
        """Returns a Series (dict-like) of the team's opponent's stats from the
        team-season page.

        :year: Int representing the season.
        :returns: A Series of team stats.
        """
        doc = self.get_year_doc(year)
        table = doc('table#team_stats')
        df = sportsref.utils.parse_table(table)
        return df.ix[df.player_id == 'Opp. Stats'].iloc[0]

    @sportsref.decorators.memoized
    def passing(self, year):
        doc = self.get_year_doc(year)
        table = doc('table#passing')
        df = sportsref.utils.parse_table(table)
        return df

    @sportsref.decorators.memoized
    def rushing_and_receiving(self, year):
        doc = self.get_year_doc(year)
        table = doc('#rushing_and_receiving')
        df = sportsref.utils.parse_table(table)
        return df
