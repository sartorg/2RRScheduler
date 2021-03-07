# The file handles the problem instances.

class Instance():
    def __init__(self, name, dataType, contributor, year):
        self.name = name
        self.dataType = dataType
        self.contributor = contributor
        self.year = year
        self.gameMode = "P"
        self.objective = "SC"
        self.leagues = []
        self.teams = []
        self.slots = []
        self.constraints = []
    


