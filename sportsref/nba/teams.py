import numpy as np
from pyquery import PyQuery as pq

from sportsref import decorators, nba, utils


@decorators.memoized
class Team:

    def __init__(self, teamID):
        self.teamID = teamID

    def __eq__(self, other):
        return (self.teamID == other.teamID)

    def __hash__(self):
        return hash(self.teamID)

    @decorators.memoized
    def team_year_url(self, yr_str):
        return nba.BASE_URL + '/teams/{}/{}.htm'.format(self.teamID, yr_str)

    @decorators.memoized
    def get_main_doc(self):
        relURL = '/teams/{}'.format(self.teamID)
        teamURL = nba.BASE_URL + relURL
        mainDoc = pq(utils.get_html(teamURL))
        return mainDoc

    @decorators.memoized
    def get_year_doc(self, yr_str):
        return pq(utils.get_html(self.team_year_url(yr_str)))

    @decorators.memoized
    def name(self):
        """Returns the real name of the franchise given the team ID.

        Examples:
        'BOS' -> 'Boston Celtics'
        'NJN' -> 'Brooklyn Nets'

        :returns: A string corresponding to the team's full name.
        """
        doc = self.get_main_doc()
        headerwords = doc('div#info_box h1')[0].text_content().split()
        lastIdx = headerwords.index('Franchise')
        teamwords = headerwords[:lastIdx]
        return ' '.join(teamwords)

    @decorators.memoized
    def roster(self, year):
        """Returns the roster table for the given year.

        :year: The year for which we want the roster; defaults to current year.
        :returns: A DataFrame containing roster information for that year.
        """
        raise NotImplementedError('roster')

    @decorators.memoized
    def boxscores(self, year):
        """Gets list of BoxScore objects corresponding to the box scores from
        that year.

        :year: The year for which we want the boxscores; defaults to current
        year.
        :returns: np.array of strings representing boxscore IDs.
        """
        doc = self.get_year_doc('{}_games'.format(year))
        table = doc('table#teams_games')
        df = utils.parse_table(table)
        if df.empty:
            return np.array([])
        return df.box_score_text.dropna().values
