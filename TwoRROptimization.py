# This file contains the various optimization procedures
# for a TwoRRProblem.

# pylint: disable=no-name-in-module, no-member

import os
#os.environ["GRB_LICENSE_FILE"] = "C:\\gurobi\\gurobi-ac.lic"
import gurobipy as gp
from gurobipy import GRB
from TwoRRProblem import TwoRRProblem, write_solution

def solve_naive(prob: TwoRRProblem):
    # Set up and solve with Gurobi a "naive" model 
    # for the TwoRRProblem. The model is naive in
    # the sense that il follows the standard integer
    # programming techniques, building a large complex
    # model and hope that Gurobi will be able to handle
    # it. This works only for simple problems.

    debug = True
    n_teams = len(prob.teams)
    if debug:
        print(n_teams)
    n_slots = len(prob.slots)
    if debug:
        print(n_slots)

    # Create Gurobi model
    model = gp.Model(prob.name)
    model.setParam("Threads", 2)

    if debug:
        print("Creating binary variables...")

    # Create variables and store them in a dictionary:
    # m_vars[home_team, away_team, slot]
    m_vars = dict()
    for team1 in range(n_teams):
        for team2 in range(n_teams):
            if team1 == team2:
                continue
            for slot in range(n_slots):
                m_vars[team1, team2, slot] = \
                    model.addVar(vtype=GRB.BINARY, name="x_" + str(team1) + "_" + str(team2) + "_" + str(slot))

    if debug:
        print("Adding basic 2RR constraints...")

    # Add constraints to force each team to play at least once
    # per slot
    for team in range(n_teams):
        for slot in range(n_slots):
            model.addConstr(gp.quicksum([m_vars[team, i, slot] for i in range(n_teams) if i != team]) + \
                            gp.quicksum([m_vars[i, team, slot] for i in range(n_teams)if i != team]) == 1)
    
    # Add constraints that force each team to play against
    # another team at most once per slot.
    for team1 in range(n_teams):
        for team2 in range(team1 + 1, n_teams):
            for slot in range(n_slots):
                model.addConstr(m_vars[team1, team2, slot] + m_vars[team2, team1, slot] <= 1)
    
    # Add constraints that force the correct number of matches
    # in each slot.
    for slot in range(n_slots):
        model.addConstr(gp.quicksum([m_vars[i,j,slot] 
                                        for i in range(n_teams) 
                                        for j in range(n_teams) if i != j]) == n_teams / 2)

    # Add constraints that force the each time to play at most twice against
    # another team, one at home and one away.
    for team1 in range(n_teams):
            for team2 in range(n_teams):
                if (team1 == team2):
                    continue
                model.addConstr(gp.quicksum([m_vars[team1,team2,slot] 
                                    for slot in range(n_slots)]) == 1)
    
    # If phased, the teams must play in separate intervals, i.e., once in each
    # n_slots/2 interval.
    if (prob.game_mode == "P"):
        for team1 in range(n_teams):
            for team2 in range(team1 + 1, n_teams):
                model.addConstr(gp.quicksum([m_vars[team1,team2,slot] + m_vars[team2,team1,slot] 
                                    for slot in range(int(n_slots/2))]) == 1)
                model.addConstr(gp.quicksum([m_vars[team1,team2,slot] + m_vars[team2,team1,slot] 
                                    for slot in range(int(n_slots/2), n_slots)]) == 1)
    
    
    bh_vars = dict() # Home breaks
    ba_vars = dict() # Away breaks

    def get_break_var(team, slot, away=False):
        if away:
            if (team, slot) not in ba_vars:
                ba_var = model.addVar(vtype=GRB.BINARY, name="ba_" + str(team) + "_" + str(slot))
                ba_vars[team, slot] = ba_var
                model.addConstr(gp.quicksum([m_vars[i,team,j] 
                                    for i in range(n_teams) if i != team
                                    for j in [slot - 1, slot]]) - 1 <= ba_var)
            return ba_vars[team, slot]
        else:
            if (team, slot) not in bh_vars:
                bh_var = model.addVar(vtype=GRB.BINARY, name="bh_" + str(team) + "_" + str(slot))
                bh_vars[team, slot] = bh_var
                model.addConstr(gp.quicksum([m_vars[team,i,j] 
                                    for i in range(n_teams) if i != team
                                    for j in [slot - 1, slot]]) - 1 <= bh_var)
            return bh_vars[team, slot]


    for team in range(n_teams):
        for slot in range(1, n_slots):
            bh_var = model.addVar(vtype=GRB.BINARY, name="bh_" + str(team) + "_" + str(slot))
            bh_vars[team, slot] = bh_var
            model.addConstr(gp.quicksum([m_vars[team,i,j] 
                                for i in range(n_teams) if i != team
                                for j in [slot - 1, slot]]) - 1 <= bh_var)
            ba_var = model.addVar(vtype=GRB.BINARY, name="ba_" + str(team) + "_" + str(slot))
            ba_vars[team, slot] = ba_var
            model.addConstr(gp.quicksum([m_vars[i,team,j] 
                                for i in range(n_teams) if i != team
                                for j in [slot - 1, slot]]) - 1 <= ba_var)

    if debug:
        print("Adding problem specific constraints...")

    # Add problem specific constraints
    for (c_name, constraint) in prob.constraints:
        # Capacity constraints:
        if c_name == "CA1":
            slots = [int(s) for s in constraint["slots"].split(';')]
            teams = [int(t) for t in constraint["teams"].split(';')]
            c_min = int(constraint["min"])
            c_max = int(constraint["max"])
            penalty = int(constraint["penalty"])
            if (c_min > 0):
                raise Exception("Min value in CA1 not implemented!")
            for team in teams:
                if constraint["type"] == "HARD":
                    if constraint["mode"] == "A":
                        model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                        for i in range(n_teams) if i != team 
                                        for j in slots]) <= c_max)
                    elif constraint["mode"] == "H":
                        model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                        for i in range(n_teams) if i != team 
                                        for j in slots]) <= c_max)
                    else:
                        raise Exception("Mode HA for CA1 not implemented!")
                else:
                    slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                    if constraint["mode"] == "A":
                        model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                        for i in range(n_teams) if i != team  
                                        for j in slots]) - slack <= c_max)
                    elif constraint["mode"] == "H": 
                        model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                        for i in range(n_teams) if i != team 
                                        for j in slots]) - slack <= c_max)
                    else:
                        raise Exception("Mode HA for CA1 not implemented!")
        if c_name == "CA2":
            slots = [int(s) for s in constraint["slots"].split(';')]
            teams1 = [int(t) for t in constraint["teams1"].split(';')]
            teams2 = [int(t) for t in constraint["teams2"].split(';')]
            c_min = int(constraint["min"])
            c_max = int(constraint["max"])
            penalty = int(constraint["penalty"])
            if (c_min > 0):
                raise Exception("Min value in CA2 not implemented!")
            for team in teams1:
                if constraint["type"] == "HARD":
                    if constraint["mode1"] == "A":
                        model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) <= c_max)
                    elif constraint["mode1"] == "H":
                        model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) <= c_max)
                    else:
                        model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) + 
                                        gp.quicksum([m_vars[i, team, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) <= c_max)
                else:
                    slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                    if constraint["mode1"] == "A":
                        model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) - slack <= c_max)
                    elif constraint["mode1"] == "H":
                        model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) - slack <= c_max)
                    else:
                        model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) + 
                                        gp.quicksum([m_vars[i, team, j] 
                                        for i in teams2 if i != team
                                        for j in slots]) - slack <= c_max)
        if c_name == "CA3":
            teams1 = [int(t) for t in constraint["teams1"].split(';')]
            teams2 = [int(t) for t in constraint["teams2"].split(';')]
            c_min = int(constraint["min"])
            c_max = int(constraint["max"])
            intp = int(constraint["intp"])
            penalty = int(constraint["penalty"])
            if (c_min > 0):
                raise Exception("Min value in CA3 not implemented!")
            for team in teams1:
                if constraint["type"] == "HARD":
                    if constraint["mode1"] == "A":
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) <= c_max)
                    elif constraint["mode1"] == "H":
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) <= c_max)
                    else:
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) + 
                                            gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) <= c_max)
                else:
                    slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                    if constraint["mode1"] == "A":
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 
                                            for j in slots]) - slack <= c_max)
                    elif constraint["mode1"] == "H":
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2
                                            for j in slots]) - slack <= c_max)
                    else:
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2
                                            for j in slots]) + 
                                            gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 
                                            for j in slots]) - slack <= c_max)
        if c_name == "CA4":
            slots = [int(s) for s in constraint["slots"].split(';')]
            teams1 = [int(t) for t in constraint["teams1"].split(';')]
            teams2 = [int(t) for t in constraint["teams2"].split(';')]
            c_min = int(constraint["min"])
            c_max = int(constraint["max"])
            penalty = int(constraint["penalty"])
            if (c_min > 0):
                raise Exception("Min value in CA4 not implemented!")
            if constraint["type"] == "HARD":
                if constraint["mode1"] == "A":
                    if constraint["mode2"] == "GLOBAL":
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) <= c_max)
                    else:
                        for slot in slots:
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams2
                                        for j in teams1 if i != j]) <= c_max)
                elif constraint["mode1"] == "H":
                    if constraint["mode2"] == "GLOBAL":
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams1
                                        for j in teams2 if i != j
                                        for z in slots]) <= c_max)
                    else:
                        for slot in slots:
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams1
                                        for j in teams2 if i != j]) <= c_max)
                else:
                    if constraint["mode2"] == "GLOBAL":
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams1
                                        for j in teams2 if i != j
                                        for z in slots]) + 
                                        gp.quicksum([m_vars[i, j, z] 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) <= c_max)
                    else:
                        for slot in slots:
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams1
                                        for j in teams2 if i != j])  + 
                                        gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams2
                                        for j in teams1 if i != j]) <= c_max)
            else:
                if constraint["mode1"] == "A":
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) - slack <= c_max)
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams2
                                        for j in teams1 if i != j]) - slack <= c_max)
                elif constraint["mode1"] == "H":
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams1
                                        for j in teams2 if i != j
                                        for z in slots]) - slack<= c_max)
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams1
                                        for j in teams2 if i != j]) - slack <= c_max)
                else:
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams1
                                        for j in teams2 if i != j
                                        for z in slots]) + 
                                        gp.quicksum([m_vars[i, j, z] 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) - slack <= c_max)
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams1
                                        for j in teams2 if i != j])  + 
                                        gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams2
                                        for j in teams1 if i != j]) - slack <= c_max)
        # Game constraints
        if c_name == "GA1":
            slots = [int(s) for s in constraint["slots"].split(';')]
            games = [(int(t[0]), int(t[2])) for t in constraint["meetings"].split(';') if len(t) > 0]
            c_min = int(constraint["min"])
            c_max = int(constraint["max"])
            penalty = int(constraint["penalty"])
            if constraint["type"] == "HARD":
                model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) <= c_max)
                model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) >= c_min)
            else:
                slack_plus = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) - slack_plus <= c_max)
                slack_minus = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) + slack_minus >= c_min)
        # Break constraints
        if c_name == "BR1":
            teams = [int(t) for t in constraint["teams"].split(';')]
            slots = [int(s) for s in constraint["slots"].split(';')]
            mode = constraint["mode2"]
            intp = int(constraint["intp"])
            penalty = int(constraint["penalty"])
            if constraint["type"] == "HARD":
                if mode == "A":
                    for team in teams:
                        model.addConstr(gp.quicksum([get_break_var(team, slot, away=True) 
                                            for slot in slots if slot != 0]) <= intp)
                elif mode == "H":
                    for team in teams:
                        model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) 
                                            for slot in slots if slot != 0]) <= intp)
                else:
                    for team in teams:
                        model.addConstr(gp.quicksum([get_break_var(team, slot, away=False)  + get_break_var(team, slot, away=True)
                                            for slot in slots if slot != 0]) <= intp)
            else:
                if mode == "A":
                    for team in teams:
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(gp.quicksum([get_break_var(team, slot, away=True) 
                                            for slot in slots if slot != 0]) - slack <= intp)
                elif mode == "H":
                    for team in teams:
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) 
                                            for slot in slots if slot != 0]) - slack <= intp)
                else:
                    for team in teams:
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(gp.quicksum([get_break_var(team, slot, away=False)  + get_break_var(team, slot, away=True)
                                            for slot in slots if slot != 0]) - slack <= intp)
        if c_name == "BR2":
            teams = [int(t) for t in constraint["teams"].split(';')]
            slots = [int(s) for s in constraint["slots"].split(';')]
            intp = int(constraint["intp"])
            penalty = int(constraint["penalty"])
            if constraint["type"] == "HARD":
                model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
                                    for team in teams
                                    for slot in slots if slot != 0]) <= intp)
            else:
                slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
                                    for team in teams
                                    for slot in slots if slot != 0]) - slack <= intp)
        # Fairness constraints
        if c_name == "FA2":
            if constraint["type"] == "HARD":
                pass
            else:
                pass
        # Separation constraints
        if c_name == "SE1":
            if constraint["type"] == "HARD":
                pass
            else:
                pass
    
    if debug:
        model.update()
        print("Num vars: " + str(model.NumVars))
        print("Num constraints: " + str(model.NumConstrs))

    if debug:
        print("Setting the objective...")

    if debug:
        model.write("problem.lp")

    #model.setParam("OutputFlag", 0)

    if debug:
        print("Solving...")
    model.optimize()

    write_status(model)

    if (debug and model.status == GRB.OPTIMAL):
        print_solution(m_vars, n_teams, n_slots)
    
    if (model.status == GRB.OPTIMAL):
        write_solution("solution.xml", prob, m_vars, model.objVal)


def write_status(model: gp.Model):
    # Displays the status of Gurobi in a more human readable format
    if model.status == GRB.OPTIMAL:
        print('Optimal objective: %g' % model.objVal)
    elif model.status == GRB.INF_OR_UNBD:
        print('Model is infeasible or unbounded')
    elif model.status == GRB.INFEASIBLE:
        print('Model is infeasible')
    elif model.status == GRB.UNBOUNDED:
        print('Model is unbounded')
    else:
        print('Optimization ended with status %d' % model.status)


def print_solution(m_vars, n_teams, n_slots):
    # Displays the solution in a more human readble format
    for slot in range(n_slots):
        print("Slot " + str(slot) + ":")
        for team1 in range(n_teams):
            for team2 in range(n_teams):
                if team1 == team2:
                    continue
                if (m_vars[team1, team2, slot].x > 0.5):
                    print("({},{})".format(str(team1), str(team2)), end=' ')
        print("")
        