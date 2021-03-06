# The file handles the problem instances.

import xml.etree.ElementTree as et
from xml.dom import minidom
import gurobipy as gp
from collections import defaultdict

# pylint: disable=no-name-in-module, no-member

class TwoRRProblem():
    # Represents a double round robin problem.
    # The structure is based on the RobinX format.
    def __init__(self, name, contributor, year):
        self.name = name
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
        my_str += "Contributor: " + self.contributor + "\n"
        my_str += "Year: " + self.year + "\n"
        my_str += "Game mode: " + self.game_mode + "\n"
        my_str += "Objective: " + self.objective + "\n"
        my_str += "Num teams: " + str(len(self.teams)) + "\n"
        my_str += "Num slots: " + str(len(self.slots)) + "\n"
        my_str += "Num constraints: " + str(len(self.constraints)) + "\n"
        return my_str

def read_instance(file_name):
    # Reads an instance from the RobinX XML format
    tree = et.parse(file_name)
    root = tree.getroot()
    meta = root.find("MetaData")
    prob = TwoRRProblem(meta.find("InstanceName").text, meta.find("Contributor").text, meta.find("Date").attrib["year"])
    prob.game_mode = root.find("Structure").find("Format").find("gameMode").text
    prob.objective = root.find("ObjectiveFunction").find("Objective").text
    for child in root.find("Resources").find("Teams"):
        prob.teams.append(child.attrib["name"])
    for child in root.find("Resources").find("Slots"):
        prob.slots.append(child.attrib["name"])
    for child in root.find("Constraints"):
        for constraint in child:
            prob.constraints.append((constraint.tag, constraint.attrib))

    return prob


def write_solution_tuples(file_name, prob, tuples, objective):
    # Write a solution file in XML format
    solution = et.Element("Solution")
    meta_data = et.SubElement(solution, "MetaData")
    instance_name = et.SubElement(meta_data, "InstanceName")
    instance_name.text = prob.name
    solution_name = et.SubElement(meta_data, "SolutionName")
    solution_name.text = file_name
    objective_value = et.SubElement(meta_data, "ObjectiveValue")
    objective_value.attrib["infeasibility"] = "0"
    objective_value.attrib["objective"] = str(int(objective))
    games = et.SubElement(solution, "Games")
    for slot,teams in enumerate(tuples):
        for t1,t2 in teams:
            game = et.SubElement(games, "ScheduledMatch")
            game.attrib["home"] = str(t1)
            game.attrib["away"] = str(t2)
            game.attrib["slot"] = str(slot)

    with open(file_name, "w") as myxml:
        myxml.write(minidom.parseString(et.tostring(solution)).toprettyxml())

def write_solution(file_name, prob, m_vars, objective):
    # Write a solution file in XML format
    solution = et.Element("Solution")
    meta_data = et.SubElement(solution, "MetaData")
    instance_name = et.SubElement(meta_data, "InstanceName")
    instance_name.text = prob.name
    solution_name = et.SubElement(meta_data, "SolutionName")
    solution_name.text = file_name
    objective_value = et.SubElement(meta_data, "ObjectiveValue")
    objective_value.attrib["infeasibility"] = "0"
    objective_value.attrib["objective"] = str(int(objective))
    games = et.SubElement(solution, "Games")
    for slot in range(len(prob.slots)):
        for h_team in range(len(prob.teams)):
            for a_team in range(len(prob.teams)):
                if h_team == a_team:
                    continue
                var_value = m_vars[h_team, a_team, slot]
                if isinstance(var_value, gp.Var):
                    var_value = var_value.x
                if var_value > 0.5:
                    game = et.SubElement(games, "ScheduledMatch")
                    game.attrib["home"] = str(h_team)
                    game.attrib["away"] = str(a_team)
                    game.attrib["slot"] = str(slot)

    with open(file_name, "w") as myxml:
        myxml.write(minidom.parseString(et.tostring(solution)).toprettyxml())
        
def read_multiple_solutions(file_name):
    tree = et.parse(file_name)
    root = tree.getroot()
    assert(root.tag == "MultipleSchedules")
    return [read_solution_element(e) for e in root.findall('Solution')]

def read_solution(file_name):
    tree = et.parse(file_name)
    root = tree.getroot()
    return read_solution_element(root)

def read_solution_element(root):
    assert(root.tag == "Solution")
    games = root.find("Games")
    slots = defaultdict(list)
    for m in games.findall('ScheduledMatch'):
        slots[int(m.attrib['slot'])].append((int(m.attrib['home']), int(m.attrib['away'])))
    return [matchings for i,matchings in sorted(list(slots.items()))]
