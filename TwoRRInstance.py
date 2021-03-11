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
    
    def __repr__(self):
        str = ""
        str += "Name: " + self.name + "\n"
        str += "Data type: " + self.data_type + "\n"
        str += "Contributor: " + self.contributor + "\n"
        str += "Year: " + self.year + "\n"
        return str

def read_instance(file_name):
    tree = et.parse(file_name)
    root = tree.getroot()
    for child in root:
        print(child.tag, child.attrib)
    for child in root[0]:
        print(child.tag, child.attrib, child.text)
    test = Instance(root[0][0].text, root[0][1].text, root[0][2].text, root[0][3].attrib["year"])
    print(test)
        