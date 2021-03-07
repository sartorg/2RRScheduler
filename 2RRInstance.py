# The file handles the problem instances.

import xml.etree.ElementTree as et 

class Instance():
    def __init__(self, name, data_type, contributor, year):
        self.name = name
        self.data_type = data_type
        self.contributor = contributor
        self.year = year
        self.game_mode = "P"
        self.objective = "SC"
        self.leagues = []
        self.teams = []
        self.slots = []
        self.constraints = []