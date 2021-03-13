# The file handles the problem instances.

import xml.etree.ElementTree as et 

class TwoRRProb():
    def __init__(self, name, data_type, contributor, year):
        self.name = name
        self.data_type = data_type
        self.contributor = contributor
        self.year = year
        self.game_mode = "-"
        self.objective = "-"
        self.teams = []
        self.slots = []
        self.constraints = []
    
    def __repr__(self):
        my_str = ""
        my_str += "Name: " + self.name + "\n"
        my_str += "Data type: " + self.data_type + "\n"
        my_str += "Contributor: " + self.contributor + "\n"
        my_str += "Year: " + self.year + "\n"
        my_str += "Game mode: " + self.game_mode + "\n"
        my_str += "Objective: " + self.objective + "\n"
        my_str += "Teams:" + str(self.teams) + "\n"
        my_str += "Slots:" + str(self.slots) + "\n"
        my_str += "Constraints:" + "\n"
        for constraint in self.constraints:
            my_str += "  " + constraint + "\n"
        return my_str

def read_instance(file_name):
    tree = et.parse(file_name)
    root = tree.getroot()
    for child in root:
        print(child.tag, child.attrib)
    for child in root[0]:
        print(child.tag, child.attrib, child.text)
    prob = TwoRRProb(root[0][0].text, root[0][1].text, root[0][2].text, root[0][3].attrib["year"])
    prob.game_mode = root[1][0][2].text
    prob.objective = root[2][0].text
    for child in root[3][1]:
        prob.teams.append(child.attrib["name"])
    for child in root[3][2]:
        prob.slots.append(child.attrib["name"])
    print(prob)
        